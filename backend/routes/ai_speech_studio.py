"""Voice Studio (Feature 17) — enterprise-grade speech coaching workspace APIs."""

from __future__ import annotations

import base64
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from routes.db import User, db, get_current_user
from utils.access_control_engine import compute_effective_plan
from utils.llm_helper import generate_verified_text

from emergentintegrations.llm.openai import OpenAISpeechToText, OpenAITextToSpeech

router = APIRouter(prefix="/ai-speech-studio", tags=["Voice Studio"])
logger = logging.getLogger("routes.ai_speech_studio")

FEATURE_ID = "ai-speech"
FEATURE_NAME = "Voice Studio"
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

COLL_PROJECTS = "ai_speech_projects"
COLL_ANALYSES = "ai_speech_analyses"
COLL_DAILY_USAGE = "ai_speech_daily_usage"
COLL_TRANSCRIPTIONS = "ai_speech_transcriptions"
COLL_SYNTHESIS = "ai_speech_synthesis"
COLL_AUDIO_BLOBS = "ai_speech_audio_blobs"
COLL_PRESETS = "ai_speech_voice_presets"
COLL_IDEMPOTENCY = "ai_speech_idempotency"

TIER_LIMITS: Dict[str, Dict[str, int]] = {
    "free": {
        "projects_per_month": 2,
        "analyses_per_day": 5,
        "transcriptions_per_day": 3,
        "synthesis_per_day": 2,
        "voice_presets": 1,
        "history_retention_days": 7,
        "max_prompt_chars": 1200,
    },
    "basic": {
        "projects_per_month": 30,
        "analyses_per_day": 120,
        "transcriptions_per_day": 60,
        "synthesis_per_day": 40,
        "voice_presets": 10,
        "history_retention_days": 90,
        "max_prompt_chars": 5000,
    },
    "premium": {
        "projects_per_month": -1,
        "analyses_per_day": -1,
        "transcriptions_per_day": -1,
        "synthesis_per_day": -1,
        "voice_presets": -1,
        "history_retention_days": -1,
        "max_prompt_chars": 12000,
    },
    "admin": {
        "projects_per_month": -1,
        "analyses_per_day": -1,
        "transcriptions_per_day": -1,
        "synthesis_per_day": -1,
        "voice_presets": -1,
        "history_retention_days": -1,
        "max_prompt_chars": 12000,
    },
    "enterprise": {
        "projects_per_month": -1,
        "analyses_per_day": -1,
        "transcriptions_per_day": -1,
        "synthesis_per_day": -1,
        "voice_presets": -1,
        "history_retention_days": -1,
        "max_prompt_chars": 12000,
    },
}


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    brief: Optional[str] = Field(default=None, max_length=1200)
    objective: Optional[str] = Field(default="presentation", max_length=80)
    fallback_user_id: Optional[str] = None


class AnalyzeRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=12000)
    target: Literal["project", "latest"] = "project"
    fallback_user_id: Optional[str] = None


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=3, max_length=12000)
    voice: str = Field(default="alloy", max_length=80)
    format: Literal["mp3", "wav"] = "mp3"
    idempotency_key: Optional[str] = Field(default=None, max_length=120)
    fallback_user_id: Optional[str] = None


class VoicePresetUpdateRequest(BaseModel):
    voice: str = Field(default="alloy", max_length=80)
    style_notes: Optional[str] = Field(default=None, max_length=600)
    language: str = Field(default="en", max_length=20)
    fallback_user_id: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _normalize_idempotency_key(value: Optional[str]) -> str:
    raw = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9._-]", "", raw)[:100]


def _scope_label(plan: str) -> str:
    if plan in {"premium", "admin", "enterprise"}:
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


def _required_upgrade_plan(plan: str) -> str:
    if plan == "free":
        return "basic"
    if plan == "basic":
        return "premium"
    return "premium"


def _extract_user_id(owner_id: str) -> str:
    return owner_id.replace("auth:", "").replace("guest:", "")


def _resolve_owner_id(user: Optional[User], fallback_user_id: Optional[str]) -> str:
    if user and getattr(user, "user_id", None):
        return f"auth:{user.user_id}"

    fallback = str(fallback_user_id or "").strip()
    if fallback:
        if not GUEST_ID_RE.match(fallback):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "ai_speech_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "ai_speech_auth_required",
            "message": "Login required or provide fallback_user_id for guest access",
        },
    )


async def _get_current_user_or_none(request: Request) -> Optional[User]:
    try:
        return await get_current_user(request)
    except HTTPException as exc:
        if int(exc.status_code) == 401:
            return None
        raise


def _tier_limits(plan: str) -> Dict[str, int]:
    return TIER_LIMITS.get(plan, TIER_LIMITS["free"])


async def _get_user_plan(user: Optional[User]) -> str:
    if not user:
        return "free"

    if bool(getattr(user, "is_admin", False)):
        return "premium"

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    effective = compute_effective_plan(user_doc or {})
    return effective if effective in TIER_LIMITS else "free"


def _raise_limit(
    plan: str,
    current_usage: int,
    limit: int,
    error_code: str,
    message: str,
) -> None:
    raise HTTPException(
        status_code=429,
        detail={
            "error_code": error_code,
            "message": message,
            "current_usage": current_usage,
            "limit": limit,
            "current_plan": plan,
            "required_plan": _required_upgrade_plan(plan),
            "scope_label": _scope_label(plan),
        },
    )


def _check_limit(
    plan: str,
    current_usage: int,
    limit: int,
    error_code: str,
    message: str,
) -> None:
    if limit >= 0 and current_usage >= limit:
        _raise_limit(plan, current_usage, limit, error_code, message)


async def _get_today_usage(owner_id: str) -> Dict[str, int]:
    row = await db[COLL_DAILY_USAGE].find_one(
        {"owner_id": owner_id, "day_key": _today_key()},
        {"_id": 0, "usage": 1},
    )
    return (row or {}).get("usage") or {}


async def _require_project(owner_id: str, project_id: str) -> Dict[str, Any]:
    project = await db[COLL_PROJECTS].find_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"_id": 0},
    )
    if not project:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ai_speech_project_not_found",
                "message": "Project not found",
            },
        )
    return project


def _voice_whitelist() -> set[str]:
    return {"alloy", "verse", "aria", "sage", "amber", "nova", "echo", "fable", "onyx", "shimmer"}


def _validate_voice_or_raise(voice: str) -> str:
    normalized = str(voice or "alloy").strip().lower()
    if normalized not in _voice_whitelist():
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "ai_speech_invalid_voice",
                "message": "Unsupported voice preset",
                "supported_voices": sorted(_voice_whitelist()),
            },
        )
    return normalized


def _safe_content_type(fmt: str) -> str:
    return "audio/wav" if fmt == "wav" else "audio/mpeg"


def _decode_b64_audio(value: str) -> bytes:
    try:
        payload = value.split(",", 1)[1] if value.startswith("data:") else value
        return base64.b64decode(payload)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={"error_code": "ai_speech_audio_decode_failed", "message": "Could not decode generated audio"},
        )


async def _track_usage(owner_id: str, plan: str, action_key: str) -> Dict[str, int]:
    now = _now_iso()
    await db[COLL_DAILY_USAGE].update_one(
        {"owner_id": owner_id, "day_key": _today_key()},
        {
            "$set": {
                "owner_id": owner_id,
                "day_key": _today_key(),
                "plan": plan,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
            "$inc": {f"usage.{action_key}": 1},
        },
        upsert=True,
    )
    return await _get_today_usage(owner_id)


async def _month_project_count(owner_id: str) -> int:
    month_prefix = _month_key()
    return await db[COLL_PROJECTS].count_documents(
        {
            "owner_id": owner_id,
            "created_at": {"$regex": f"^{month_prefix}"},
        }
    )


async def _check_transcription_limits(owner_id: str, plan: str) -> Dict[str, int]:
    usage = await _get_today_usage(owner_id)
    limits = _tier_limits(plan)
    _check_limit(
        plan,
        int(usage.get("transcriptions", 0) or 0),
        int(limits.get("transcriptions_per_day", -1)),
        "ai_speech_transcription_limit_reached",
        "Daily transcription limit reached for current plan.",
    )
    return usage


async def _check_synthesis_limits(owner_id: str, plan: str) -> Dict[str, int]:
    usage = await _get_today_usage(owner_id)
    limits = _tier_limits(plan)
    _check_limit(
        plan,
        int(usage.get("synthesis", 0) or 0),
        int(limits.get("synthesis_per_day", -1)),
        "ai_speech_synthesis_limit_reached",
        "Daily synthesis limit reached for current plan.",
    )
    return usage


async def _check_voice_preset_limits(owner_id: str, plan: str) -> int:
    limits = _tier_limits(plan)
    total = await db[COLL_PRESETS].count_documents({"owner_id": owner_id})
    _check_limit(
        plan,
        int(total),
        int(limits.get("voice_presets", -1)),
        "ai_speech_preset_limit_reached",
        "Voice preset limit reached for current plan.",
    )
    return int(total)


async def _idempotency_replay(owner_id: str, endpoint: str, key: str) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    row = await db[COLL_IDEMPOTENCY].find_one(
        {
            "owner_id": owner_id,
            "endpoint": endpoint,
            "idempotency_key": key,
        },
        {"_id": 0, "response": 1},
    )
    if not row:
        return None
    replay = dict((row or {}).get("response") or {})
    if replay:
        replay["idempotent_replay"] = True
    return replay if replay else None


async def _save_idempotency(owner_id: str, endpoint: str, key: str, response: Dict[str, Any]) -> None:
    if not key:
        return
    now = _now_iso()
    await db[COLL_IDEMPOTENCY].update_one(
        {
            "owner_id": owner_id,
            "endpoint": endpoint,
            "idempotency_key": key,
        },
        {
            "$set": {
                "owner_id": owner_id,
                "endpoint": endpoint,
                "idempotency_key": key,
                "response": response,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def _check_create_project_limits(owner_id: str, plan: str) -> None:
    limits = _tier_limits(plan)
    project_count = await _month_project_count(owner_id)
    _check_limit(
        plan,
        project_count,
        int(limits.get("projects_per_month", -1)),
        "ai_speech_project_limit_reached",
        "Monthly project limit reached for current plan.",
    )


async def _check_analyze_limits(owner_id: str, plan: str, prompt_chars: int) -> Dict[str, int]:
    usage = await _get_today_usage(owner_id)
    limits = _tier_limits(plan)

    _check_limit(
        plan,
        usage.get("analyses", 0),
        int(limits.get("analyses_per_day", -1)),
        "ai_speech_analysis_limit_reached",
        "Daily analysis limit reached for current plan.",
    )

    max_chars = int(limits.get("max_prompt_chars", 1200))
    if max_chars >= 0 and prompt_chars > max_chars:
        raise HTTPException(
            status_code=413,
            detail={
                "error_code": "ai_speech_prompt_too_long",
                "message": f"Prompt exceeds plan limit of {max_chars} characters.",
                "current_plan": plan,
                "required_plan": _required_upgrade_plan(plan),
                "scope_label": _scope_label(plan),
                "limit": max_chars,
                "current_usage": prompt_chars,
            },
        )

    return usage


def _build_history_filter(owner_id: str, plan: str, project_id: Optional[str]) -> Dict[str, Any]:
    query: Dict[str, Any] = {"owner_id": owner_id}
    if project_id:
        query["project_id"] = project_id

    retention_days = int(_tier_limits(plan).get("history_retention_days", -1))
    if retention_days >= 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        query["created_at"] = {"$gte": cutoff}

    return query


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "healthy", "feature": FEATURE_NAME, "feature_id": FEATURE_ID}


@router.get("/bootstrap")
async def bootstrap(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)
    limits = _tier_limits(plan)
    usage = await _get_today_usage(owner_id)

    projects_cursor = (
        db[COLL_PROJECTS]
        .find({"owner_id": owner_id}, {"_id": 0})
        .sort("updated_at", -1)
        .limit(30)
    )
    projects = await projects_cursor.to_list(length=30)

    history_query = _build_history_filter(owner_id, plan, None)
    recent_history = await (
        db[COLL_ANALYSES]
        .find(history_query, {"_id": 0})
        .sort("created_at", -1)
        .limit(12)
        .to_list(length=12)
    )

    return {
        "success": True,
        "feature_id": FEATURE_ID,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limits": limits,
        "usage": {
            "projects_this_month": await _month_project_count(owner_id),
            "analyses_today": int(usage.get("analyses", 0) or 0),
            "transcriptions_today": int(usage.get("transcriptions", 0) or 0),
            "synthesis_today": int(usage.get("synthesis", 0) or 0),
        },
        "projects": projects,
        "recent_history": recent_history,
        "features": {
            "project_workspace": True,
            "analysis": True,
            "history": True,
            "transcribe": True,
            "synthesize": True,
            "voice_preset": True,
            "exports": True,
        },
    }


@router.post("/projects/create")
async def create_project(request: Request, payload: ProjectCreateRequest) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)

    await _check_create_project_limits(owner_id, plan)

    now = _now_iso()
    project_id = f"aivs_{uuid.uuid4().hex[:12]}"
    doc = {
        "project_id": project_id,
        "owner_id": owner_id,
        "title": payload.title.strip(),
        "brief": (payload.brief or "").strip() or None,
        "objective": (payload.objective or "presentation").strip() or "presentation",
        "analysis_count": 0,
        "last_analysis": None,
        "last_analysis_at": None,
        "created_at": now,
        "updated_at": now,
    }
    await db[COLL_PROJECTS].insert_one(dict(doc))

    return {
        "success": True,
        "project": doc,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limits": _tier_limits(plan),
    }


@router.post("/projects/{project_id}/analyze")
async def analyze_project(
    project_id: str,
    payload: AnalyzeRequest,
    request: Request,
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)

    await _require_project(owner_id, project_id)

    prompt = payload.prompt.strip()
    await _check_analyze_limits(owner_id, plan, len(prompt))

    system_prompt = (
        "You are Voice Studio's enterprise communication coach. "
        "Provide practical, concise speech guidance with three sections: "
        "(1) Delivery strengths, (2) Risks to fix, (3) Next rehearsal plan. "
        "Use clear bullet points and keep the advice actionable."
    )
    session_id = f"ai-speech-studio-analysis-{uuid.uuid4().hex[:10]}"

    try:
        analysis = await generate_verified_text(prompt, system_prompt, session_id)
    except Exception as exc:
        logger.error("Voice Studio analysis failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "ai_speech_analysis_failed",
                "message": "Voice analysis failed. Please retry.",
            },
        )

    now = _now_iso()
    analysis_id = f"ana_{uuid.uuid4().hex[:12]}"
    analysis_doc = {
        "analysis_id": analysis_id,
        "project_id": project_id,
        "owner_id": owner_id,
        "prompt": prompt,
        "analysis": analysis,
        "created_at": now,
    }
    await db[COLL_ANALYSES].insert_one(dict(analysis_doc))

    await db[COLL_PROJECTS].update_one(
        {"project_id": project_id, "owner_id": owner_id},
        {
            "$set": {
                "last_analysis": analysis,
                "last_analysis_at": now,
                "updated_at": now,
            },
            "$inc": {"analysis_count": 1},
        },
    )

    usage = await _track_usage(owner_id, plan, "analyses")

    return {
        "success": True,
        "analysis": analysis,
        "analysis_id": analysis_id,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "usage": {
            "analyses_today": int(usage.get("analyses", 0) or 0),
        },
        "daily_limit": int(_tier_limits(plan).get("analyses_per_day", -1)),
    }


@router.post("/projects/{project_id}/transcribe")
async def transcribe_project_audio(
    project_id: str,
    request: Request,
    audio: UploadFile = File(...),
    fallback_user_id: Optional[str] = Query(default=None),
    idempotency_key: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)
    await _require_project(owner_id, project_id)

    idem = _normalize_idempotency_key(idempotency_key)
    replay = await _idempotency_replay(owner_id, f"transcribe:{project_id}", idem)
    if replay:
        return replay

    await _check_transcription_limits(owner_id, plan)
    content = await audio.read()
    if len(content) < 10:
        raise HTTPException(status_code=400, detail={"error_code": "ai_speech_audio_empty", "message": "Audio appears empty"})
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "ai_speech_audio_too_large", "message": "Audio too large. Max 25MB."},
        )

    ext = "webm"
    if audio.filename and "." in audio.filename:
        ext = audio.filename.rsplit(".", 1)[-1].lower()

    text = ""
    last_error: Optional[Exception] = None
    max_attempts = 2
    for _ in range(max_attempts):
        temp_path = ""
        try:
            api_key = os.environ.get("EMERGENT_LLM_KEY")
            if not api_key:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error_code": "ai_speech_provider_not_configured",
                        "message": "Speech transcription provider is not configured.",
                    },
                )

            stt = OpenAISpeechToText(api_key=api_key)
            tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
            tmp.write(content)
            tmp.close()
            temp_path = tmp.name
            with open(temp_path, "rb") as audio_file:
                response = await stt.transcribe(file=audio_file, model="whisper-1", response_format="json")
                text = str(getattr(response, "text", "") or "").strip()
            if text:
                break
        except Exception as exc:
            last_error = exc
            logger.warning("Voice Studio transcribe attempt failed: %s", exc)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    if not text:
        logger.error("Voice Studio transcribe failed after retries: %s", last_error)
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "ai_speech_transcription_failed",
                "message": "Transcription provider failed after retries.",
            },
        )

    now = _now_iso()
    transcript_id = f"trn_{uuid.uuid4().hex[:12]}"
    transcript_doc = {
        "transcript_id": transcript_id,
        "project_id": project_id,
        "owner_id": owner_id,
        "source_filename": audio.filename or "recording.webm",
        "source_content_type": audio.content_type or "audio/webm",
        "text": text,
        "created_at": now,
    }
    await db[COLL_TRANSCRIPTIONS].insert_one(dict(transcript_doc))
    await db[COLL_PROJECTS].update_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"$set": {"last_transcript": text, "last_transcript_at": now, "updated_at": now}},
    )
    usage = await _track_usage(owner_id, plan, "transcriptions")

    response = {
        "success": True,
        "transcript_id": transcript_id,
        "transcript": text,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "usage": {"transcriptions_today": int(usage.get("transcriptions", 0) or 0)},
        "daily_limit": int(_tier_limits(plan).get("transcriptions_per_day", -1)),
        "idempotent_replay": False,
    }
    await _save_idempotency(owner_id, f"transcribe:{project_id}", idem, response)
    return response


@router.post("/projects/{project_id}/synthesize")
async def synthesize_project_audio(
    project_id: str,
    payload: SynthesizeRequest,
    request: Request,
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    await _require_project(owner_id, project_id)

    idem = _normalize_idempotency_key(payload.idempotency_key)
    replay = await _idempotency_replay(owner_id, f"synthesize:{project_id}", idem)
    if replay:
        return replay

    await _check_synthesis_limits(owner_id, plan)
    voice = _validate_voice_or_raise(payload.voice)
    fmt = payload.format

    max_attempts = 2
    audio_bytes: bytes = b""
    last_error: Optional[Exception] = None
    for _ in range(max_attempts):
        try:
            api_key = os.environ.get("EMERGENT_LLM_KEY")
            if not api_key:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error_code": "ai_speech_provider_not_configured",
                        "message": "Speech synthesis provider is not configured.",
                    },
                )

            tts = OpenAITextToSpeech(api_key=api_key)
            audio_bytes = await tts.generate_speech(
                text=payload.text,
                model="tts-1",
                voice=voice,
                response_format=fmt,
            )
            if audio_bytes:
                break
        except Exception as exc:
            last_error = exc
            logger.warning("Voice Studio synthesis attempt failed: %s", exc)

    if not audio_bytes:
        logger.error("Voice Studio synthesis failed after retries: %s", last_error)
        raise HTTPException(
            status_code=502,
            detail={
                "error_code": "ai_speech_synthesis_failed",
                "message": "Synthesis provider failed after retries.",
            },
        )

    now = _now_iso()
    audio_id = f"aud_{uuid.uuid4().hex[:12]}"
    synthesis_id = f"syn_{uuid.uuid4().hex[:12]}"
    audio_doc = {
        "audio_id": audio_id,
        "owner_id": owner_id,
        "project_id": project_id,
        "content_type": _safe_content_type(fmt),
        "filename": f"voice_{audio_id}.{fmt}",
        "blob": audio_bytes,
        "size_bytes": len(audio_bytes),
        "created_at": now,
    }
    await db[COLL_AUDIO_BLOBS].insert_one(dict(audio_doc))
    synthesis_doc = {
        "synthesis_id": synthesis_id,
        "audio_id": audio_id,
        "owner_id": owner_id,
        "project_id": project_id,
        "voice": voice,
        "format": fmt,
        "text": payload.text,
        "char_count": len(payload.text),
        "created_at": now,
    }
    await db[COLL_SYNTHESIS].insert_one(dict(synthesis_doc))
    await db[COLL_PROJECTS].update_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"$set": {"last_synthesis_id": synthesis_id, "last_audio_id": audio_id, "updated_at": now}},
    )
    usage = await _track_usage(owner_id, plan, "synthesis")

    response = {
        "success": True,
        "synthesis_id": synthesis_id,
        "audio_id": audio_id,
        "audio_url": f"/api/ai-speech-studio/file/{audio_id}",
        "voice": voice,
        "format": fmt,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "usage": {"synthesis_today": int(usage.get("synthesis", 0) or 0)},
        "daily_limit": int(_tier_limits(plan).get("synthesis_per_day", -1)),
        "idempotent_replay": False,
    }
    await _save_idempotency(owner_id, f"synthesize:{project_id}", idem, response)
    return response


@router.get("/voice-preset")
async def get_voice_presets(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)
    rows = await (
        db[COLL_PRESETS]
        .find({"owner_id": owner_id}, {"_id": 0})
        .sort("updated_at", -1)
        .limit(40)
        .to_list(length=40)
    )
    return {
        "success": True,
        "presets": rows,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limit": int(_tier_limits(plan).get("voice_presets", -1)),
        "used": len(rows),
    }


@router.put("/voice-preset")
async def upsert_voice_preset(
    payload: VoicePresetUpdateRequest,
    request: Request,
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    voice = _validate_voice_or_raise(payload.voice)

    existing = await db[COLL_PRESETS].find_one({"owner_id": owner_id, "voice": voice}, {"_id": 0})
    if not existing:
        await _check_voice_preset_limits(owner_id, plan)

    now = _now_iso()
    preset_id = (existing or {}).get("preset_id") or f"vp_{uuid.uuid4().hex[:12]}"
    doc_for_set = {
        "preset_id": preset_id,
        "owner_id": owner_id,
        "voice": voice,
        "style_notes": (payload.style_notes or "").strip() or None,
        "language": (payload.language or "en").strip() or "en",
        "updated_at": now,
    }
    await db[COLL_PRESETS].update_one(
        {"owner_id": owner_id, "voice": voice},
        {"$set": doc_for_set, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    used = await db[COLL_PRESETS].count_documents({"owner_id": owner_id})
    persisted = await db[COLL_PRESETS].find_one({"owner_id": owner_id, "voice": voice}, {"_id": 0})
    doc = persisted or {**doc_for_set, "created_at": now}
    return {
        "success": True,
        "preset": doc,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limit": int(_tier_limits(plan).get("voice_presets", -1)),
        "used": int(used),
    }


@router.get("/file/{audio_id}")
async def get_audio_file(
    audio_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
) -> Response:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    row = await db[COLL_AUDIO_BLOBS].find_one(
        {"audio_id": audio_id, "owner_id": owner_id},
        {"_id": 0, "blob": 1, "content_type": 1},
    )
    if not row:
        raise HTTPException(status_code=404, detail={"error_code": "ai_speech_audio_not_found", "message": "Audio file not found"})
    blob = row.get("blob")
    if not blob:
        raise HTTPException(status_code=404, detail={"error_code": "ai_speech_audio_not_found", "message": "Audio file missing"})
    return Response(content=blob, media_type=row.get("content_type") or "audio/mpeg")


@router.get("/projects/{project_id}/exports")
async def export_project_outputs(
    project_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
    include_analysis: bool = Query(default=True),
    include_transcripts: bool = Query(default=True),
    include_synthesis: bool = Query(default=True),
    limit: int = Query(default=25, ge=1, le=100),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)
    await _require_project(owner_id, project_id)

    payload: Dict[str, Any] = {
        "success": True,
        "project_id": project_id,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "exported_at": _now_iso(),
    }
    if include_analysis:
        payload["analyses"] = await (
            db[COLL_ANALYSES]
            .find({"owner_id": owner_id, "project_id": project_id}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
            .to_list(length=limit)
        )
    if include_transcripts:
        payload["transcripts"] = await (
            db[COLL_TRANSCRIPTIONS]
            .find({"owner_id": owner_id, "project_id": project_id}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
            .to_list(length=limit)
        )
    if include_synthesis:
        synth_rows = await (
            db[COLL_SYNTHESIS]
            .find({"owner_id": owner_id, "project_id": project_id}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
            .to_list(length=limit)
        )
        payload["synthesis"] = [
            {
                **row,
                "audio_url": f"/api/ai-speech-studio/file/{row.get('audio_id')}",
            }
            for row in synth_rows
        ]
    return payload


@router.get("/history")
async def history(
    request: Request,
    project_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    fallback_user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)

    query = _build_history_filter(owner_id, plan, project_id)
    total = await db[COLL_ANALYSES].count_documents(query)
    rows = await (
        db[COLL_ANALYSES]
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
        .to_list(length=limit)
    )

    return {
        "success": True,
        "history": rows,
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "plan": plan,
        "scope_label": _scope_label(plan),
    }
