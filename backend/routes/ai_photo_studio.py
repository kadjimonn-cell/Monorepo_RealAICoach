"""Image & Design Studio (Feature 16) — enterprise-grade visual workspace APIs."""

from __future__ import annotations

import base64
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from routes.db import EMERGENT_LLM_KEY, User, db, get_current_user
from utils.access_control_engine import compute_effective_plan
from utils.llm_helper import generate_verified_text

router = APIRouter(prefix="/ai-photo-studio", tags=["Image & Design Studio"])
logger = logging.getLogger("routes.ai_photo_studio")

FEATURE_ID = "ai-photo"
FEATURE_NAME = "Image & Design Studio"
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

COLL_PROJECTS = "ai_photo_projects"
COLL_GENERATIONS = "ai_photo_generations"
COLL_ASSETS = "ai_photo_assets"
COLL_DAILY_USAGE = "ai_photo_daily_usage"
COLL_BRAND_PRESETS = "ai_photo_brand_presets"

TIER_LIMITS: Dict[str, Dict[str, int]] = {
    "free": {
        "projects_per_month": 2,
        "generations_per_day": 4,
        "analyses_per_day": 4,
        "remixes_per_day": 2,
        "max_prompt_chars": 650,
    },
    "basic": {
        "projects_per_month": 30,
        "generations_per_day": 120,
        "analyses_per_day": 120,
        "remixes_per_day": 60,
        "max_prompt_chars": 2000,
    },
    "premium": {
        "projects_per_month": -1,
        "generations_per_day": -1,
        "analyses_per_day": -1,
        "remixes_per_day": -1,
        "max_prompt_chars": 6000,
    },
    "admin": {
        "projects_per_month": -1,
        "generations_per_day": -1,
        "analyses_per_day": -1,
        "remixes_per_day": -1,
        "max_prompt_chars": 6000,
    },
}

STYLE_PACKS: List[Dict[str, str]] = [
    {"id": "cinematic", "label": "Cinematic"},
    {"id": "studio", "label": "Studio"},
    {"id": "editorial", "label": "Editorial"},
    {"id": "illustration", "label": "Illustration"},
    {"id": "clarity", "label": "Clarity"},
]

QUALITY_PACKS: List[Dict[str, str]] = [
    {"id": "standard", "label": "Standard"},
    {"id": "ultra", "label": "Ultra"},
]

STYLE_PROMPTS = {
    "cinematic": "Cinematic lighting, dramatic depth of field, rich contrast, filmic grading.",
    "studio": "Clean studio lighting, high precision composition, crisp product-shot quality.",
    "editorial": "Editorial photography style, balanced tones, realistic natural-light finish.",
    "illustration": "High-detail illustration style, clean geometry, polished concept-art aesthetics.",
    "clarity": "Accessibility-first composition, high legibility, low visual clutter.",
}

QUALITY_PROMPTS = {
    "standard": "High resolution, crisp details, minimal artifacts.",
    "ultra": "Ultra-high resolution, premium detail fidelity, pristine quality.",
}


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    brief: Optional[str] = Field(default=None, max_length=1200)
    style_pack: Optional[str] = Field(default="cinematic", max_length=40)
    quality: Optional[str] = Field(default="ultra", max_length=40)
    fallback_user_id: Optional[str] = None


class FavoriteRequest(BaseModel):
    favorite: bool
    fallback_user_id: Optional[str] = None


class GenerationRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=6000)
    style_pack: Optional[str] = Field(default=None, max_length=40)
    quality: Optional[str] = Field(default=None, max_length=40)
    remix_from_generation_id: Optional[str] = Field(default=None, max_length=60)
    idempotency_key: Optional[str] = Field(default=None, max_length=120)
    fallback_user_id: Optional[str] = None


class AnalyzeRequest(BaseModel):
    target: Literal["latest", "project", "generation"] = "latest"
    generation_id: Optional[str] = Field(default=None, max_length=60)
    prompt: Optional[str] = Field(default=None, max_length=1200)
    fallback_user_id: Optional[str] = None


class BrandPresetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    primary_goal: str = Field(min_length=1, max_length=220)
    audience: Optional[str] = Field(default=None, max_length=180)
    visual_constraints: Optional[str] = Field(default=None, max_length=500)
    fallback_user_id: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _resolve_owner_id(user: Optional[User], fallback_user_id: Optional[str]) -> str:
    if user and getattr(user, "user_id", None):
        return f"auth:{user.user_id}"

    fallback = str(fallback_user_id or "").strip()
    if fallback:
        if not GUEST_ID_RE.match(fallback):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "ai_photo_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "ai_photo_auth_required",
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


def _extract_user_id(owner_id: str) -> str:
    return owner_id.replace("auth:", "").replace("guest:", "")


def _scope_label(plan: str) -> str:
    if plan in {"premium", "admin"}:
        return "Full unlimited access"
    if plan == "basic":
        return "Almost unlimited access"
    return "Limited access"


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
    if effective in {"premium", "basic"}:
        return effective
    return "free"


def _tier_limits(plan: str) -> Dict[str, int]:
    return TIER_LIMITS.get(plan, TIER_LIMITS["free"])


def _check_limit(current: int, limit: int, error_code: str, message: str) -> None:
    if limit >= 0 and current >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": error_code,
                "message": message,
            },
        )


async def _get_today_usage(owner_id: str) -> Dict[str, int]:
    row = await db[COLL_DAILY_USAGE].find_one(
        {"owner_id": owner_id, "day_key": _today_key()},
        {"_id": 0, "usage": 1},
    )
    return (row or {}).get("usage") or {}


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


async def _check_generation_limits(owner_id: str, plan: str, is_remix: bool) -> Dict[str, int]:
    usage = await _get_today_usage(owner_id)
    limits = _tier_limits(plan)

    _check_limit(
        usage.get("generations", 0),
        int(limits.get("generations_per_day", -1)),
        "ai_photo_generation_limit",
        f"{_scope_label(plan)}: daily generation limit reached.",
    )
    if is_remix:
        _check_limit(
            usage.get("remixes", 0),
            int(limits.get("remixes_per_day", -1)),
            "ai_photo_remix_limit",
            f"{_scope_label(plan)}: daily remix limit reached.",
        )

    return usage


async def _check_analysis_limit(owner_id: str, plan: str) -> Dict[str, int]:
    usage = await _get_today_usage(owner_id)
    limits = _tier_limits(plan)
    _check_limit(
        usage.get("analyses", 0),
        int(limits.get("analyses_per_day", -1)),
        "ai_photo_analysis_limit",
        f"{_scope_label(plan)}: daily analysis limit reached.",
    )
    return usage


async def _check_project_limit(owner_id: str, plan: str) -> None:
    limit = int(_tier_limits(plan).get("projects_per_month", -1))
    if limit < 0:
        return
    current_month = _month_key()
    count = await db[COLL_PROJECTS].count_documents(
        {"owner_id": owner_id, "created_at": {"$regex": f"^{current_month}"}}
    )
    _check_limit(
        count,
        limit,
        "ai_photo_project_limit",
        f"{_scope_label(plan)}: monthly project limit reached.",
    )


def _build_enhanced_prompt(
    prompt: str,
    style_pack: str,
    quality: str,
    brand_preset: Optional[Dict[str, Any]],
) -> str:
    style_note = STYLE_PROMPTS.get(style_pack, STYLE_PROMPTS["cinematic"])
    quality_note = QUALITY_PROMPTS.get(quality, QUALITY_PROMPTS["ultra"])
    brand_bits: List[str] = []
    if brand_preset:
        if brand_preset.get("primary_goal"):
            brand_bits.append(f"Design objective: {brand_preset['primary_goal']}")
        if brand_preset.get("audience"):
            brand_bits.append(f"Audience: {brand_preset['audience']}")
        if brand_preset.get("visual_constraints"):
            brand_bits.append(f"Constraints: {brand_preset['visual_constraints']}")

    base_parts = [
        "Professional grade image output.",
        quality_note,
        style_note,
        f"Subject: {prompt.strip()}",
        "Avoid artifacts, watermark text, duplicated anatomy, low-detail output.",
    ]
    if brand_bits:
        base_parts.append(" ".join(brand_bits))
    return " ".join(base_parts)


def _normalize_generation_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    image_id = doc.get("image_id")
    return {
        **doc,
        "image_url": f"/api/ai-photo-studio/file/{image_id}" if image_id else None,
    }


@router.get("/health")
async def ai_photo_studio_health() -> Dict[str, Any]:
    return {"status": "healthy", "feature": FEATURE_NAME, "feature_id": FEATURE_ID}


@router.get("/bootstrap")
async def ai_photo_bootstrap(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)
    limits = _tier_limits(plan)
    usage = await _get_today_usage(owner_id)

    projects = (
        await db[COLL_PROJECTS]
        .find({"owner_id": owner_id}, {"_id": 0})
        .sort("updated_at", -1)
        .limit(30)
        .to_list(30)
    )
    recent_generations_raw = (
        await db[COLL_GENERATIONS]
        .find({"owner_id": owner_id, "status": "completed"}, {"_id": 0})
        .sort("created_at", -1)
        .limit(24)
        .to_list(24)
    )
    recent_generations = [_normalize_generation_doc(item) for item in recent_generations_raw]
    brand_preset = await db[COLL_BRAND_PRESETS].find_one({"owner_id": owner_id}, {"_id": 0})

    return {
        "success": True,
        "feature_id": FEATURE_ID,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "limits": limits,
        "usage": usage,
        "projects": projects,
        "recent_generations": recent_generations,
        "brand_preset": brand_preset,
        "style_packs": STYLE_PACKS,
        "quality_packs": QUALITY_PACKS,
        "features": {
            "project_workspace": True,
            "one_click_remix": True,
            "brand_preset": True,
            "analysis": True,
            "history": True,
        },
    }


@router.post("/projects/create")
async def ai_photo_create_project(payload: ProjectCreateRequest, request: Request) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)

    await _check_project_limit(owner_id, plan)

    now = _now_iso()
    project_id = f"aip_{uuid.uuid4().hex[:12]}"
    project = {
        "project_id": project_id,
        "owner_id": owner_id,
        "title": payload.title.strip(),
        "brief": (payload.brief or "").strip(),
        "style_pack": (payload.style_pack or "cinematic").strip().lower(),
        "quality": (payload.quality or "ultra").strip().lower(),
        "favorite": False,
        "generation_count": 0,
        "last_generation_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db[COLL_PROJECTS].insert_one(project)
    await _track_usage(owner_id, plan, "projects")
    project.pop("_id", None)
    return {"success": True, "project": project, "plan": plan, "scope_label": _scope_label(plan)}


@router.get("/projects")
async def ai_photo_list_projects(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=80),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    rows = (
        await db[COLL_PROJECTS]
        .find({"owner_id": owner_id}, {"_id": 0})
        .sort("updated_at", -1)
        .skip(offset)
        .limit(limit)
        .to_list(limit)
    )
    total = await db[COLL_PROJECTS].count_documents({"owner_id": owner_id})
    return {"success": True, "projects": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/projects/{project_id}")
async def ai_photo_get_project(
    project_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    project = await db[COLL_PROJECTS].find_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"_id": 0},
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    generations_raw = (
        await db[COLL_GENERATIONS]
        .find({"project_id": project_id, "owner_id": owner_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(40)
        .to_list(40)
    )
    generations = [_normalize_generation_doc(item) for item in generations_raw]
    return {"success": True, "project": project, "generations": generations}


@router.post("/projects/{project_id}/favorite")
async def ai_photo_toggle_favorite(
    project_id: str,
    payload: FavoriteRequest,
    request: Request,
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    update_result = await db[COLL_PROJECTS].update_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"$set": {"favorite": bool(payload.favorite), "updated_at": _now_iso()}},
    )
    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    updated = await db[COLL_PROJECTS].find_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"_id": 0},
    )
    return {"success": True, "project": updated}


@router.post("/projects/{project_id}/generate")
async def ai_photo_generate(
    project_id: str,
    payload: GenerationRequest,
    request: Request,
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    limits = _tier_limits(plan)
    is_remix = bool(payload.remix_from_generation_id)
    await _check_generation_limits(owner_id, plan, is_remix=is_remix)

    project = await db[COLL_PROJECTS].find_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"_id": 0},
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    prompt = payload.prompt.strip()
    max_prompt_chars = int(limits.get("max_prompt_chars", 650))
    if max_prompt_chars >= 0 and len(prompt) > max_prompt_chars:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "ai_photo_prompt_too_long",
                "message": f"Prompt exceeds limit for current plan ({max_prompt_chars} chars).",
            },
        )

    style_pack = (payload.style_pack or project.get("style_pack") or "cinematic").strip().lower()
    quality = (payload.quality or project.get("quality") or "ultra").strip().lower()
    idempotency_key = str(payload.idempotency_key or "").strip() or None

    if idempotency_key:
        existing = await db[COLL_GENERATIONS].find_one(
            {
                "owner_id": owner_id,
                "project_id": project_id,
                "idempotency_key": idempotency_key,
                "status": "completed",
            },
            {"_id": 0},
        )
        if existing:
            return {
                "success": True,
                "idempotent_hit": True,
                "generation": _normalize_generation_doc(existing),
                "plan": plan,
                "scope_label": _scope_label(plan),
                "daily_limit": limits.get("generations_per_day", -1),
            }

    brand_preset = await db[COLL_BRAND_PRESETS].find_one({"owner_id": owner_id}, {"_id": 0})
    enhanced_prompt = _build_enhanced_prompt(prompt, style_pack, quality, brand_preset)

    api_key = os.environ.get("EMERGENT_LLM_KEY") or EMERGENT_LLM_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY not configured")

    image_gen = OpenAIImageGeneration(api_key=api_key)
    try:
        images = await image_gen.generate_images(
            prompt=enhanced_prompt,
            model="gpt-image-1",
            number_of_images=1,
        )
    except Exception as exc:
        logger.error("ai-photo generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Image generation failed")

    if not images:
        raise HTTPException(status_code=500, detail="No image generated")

    now = _now_iso()
    image_id = f"img_{uuid.uuid4().hex[:16]}"
    generation_id = f"gen_{uuid.uuid4().hex[:12]}"

    await db[COLL_ASSETS].insert_one(
        {
            "image_id": image_id,
            "owner_id": owner_id,
            "project_id": project_id,
            "content_type": "image/png",
            "bytes_b64": base64.b64encode(images[0]).decode("utf-8"),
            "created_at": now,
        }
    )

    generation_doc = {
        "generation_id": generation_id,
        "project_id": project_id,
        "owner_id": owner_id,
        "prompt": prompt,
        "enhanced_prompt": enhanced_prompt,
        "style_pack": style_pack,
        "quality": quality,
        "plan": plan,
        "status": "completed",
        "image_id": image_id,
        "remix_from_generation_id": payload.remix_from_generation_id,
        "idempotency_key": idempotency_key,
        "created_at": now,
        "updated_at": now,
    }
    await db[COLL_GENERATIONS].insert_one(generation_doc)

    await db[COLL_PROJECTS].update_one(
        {"project_id": project_id, "owner_id": owner_id},
        {
            "$set": {"updated_at": now, "last_generation_id": generation_id, "style_pack": style_pack, "quality": quality},
            "$inc": {"generation_count": 1},
        },
    )

    usage = await _track_usage(owner_id, plan, "generations")
    if is_remix:
        usage = await _track_usage(owner_id, plan, "remixes")

    generation_doc.pop("_id", None)
    return {
        "success": True,
        "generation": _normalize_generation_doc(generation_doc),
        "plan": plan,
        "scope_label": _scope_label(plan),
        "usage": usage,
        "daily_limit": limits.get("generations_per_day", -1),
    }


@router.post("/projects/{project_id}/analyze")
async def ai_photo_analyze(
    project_id: str,
    payload: AnalyzeRequest,
    request: Request,
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    limits = _tier_limits(plan)
    await _check_analysis_limit(owner_id, plan)

    project = await db[COLL_PROJECTS].find_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"_id": 0},
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    generation_doc: Optional[Dict[str, Any]] = None
    if payload.target == "generation" and payload.generation_id:
        generation_doc = await db[COLL_GENERATIONS].find_one(
            {
                "generation_id": payload.generation_id,
                "project_id": project_id,
                "owner_id": owner_id,
            },
            {"_id": 0},
        )
    else:
        generation_doc = await db[COLL_GENERATIONS].find_one(
            {"project_id": project_id, "owner_id": owner_id},
            {"_id": 0},
            sort=[("created_at", -1)],
        )

    contextual_prompt = payload.prompt or "Provide actionable composition and conversion-focused visual improvements."
    generation_summary = ""
    if generation_doc:
        generation_summary = (
            f"Latest generated image context:\n"
            f"- Prompt: {generation_doc.get('prompt', '')}\n"
            f"- Style: {generation_doc.get('style_pack', '')}\n"
            f"- Quality: {generation_doc.get('quality', '')}\n"
        )

    system_message = (
        "You are an Enterprise Creative Director. Return concise, high-impact visual guidance with: "
        "1) composition fixes, 2) style adjustments, 3) conversion-focused ideas, 4) next remix prompt. "
        "Use markdown bullets."
    )
    user_message = (
        f"Project title: {project.get('title')}\n"
        f"Project brief: {project.get('brief', '')}\n"
        f"Plan scope: {_scope_label(plan)}\n"
        f"{generation_summary}\n"
        f"User ask: {contextual_prompt}"
    )

    session_seed = _extract_user_id(owner_id).replace(":", "-")
    analysis_text = await generate_verified_text(
        prompt=user_message,
        system_message=system_message,
        session_id=f"ai-photo-analysis-{session_seed}-{uuid.uuid4().hex[:8]}",
        feature="ai_photo_studio_analysis",
        user_id=_extract_user_id(owner_id),
    )

    now = _now_iso()
    await db[COLL_PROJECTS].update_one(
        {"project_id": project_id, "owner_id": owner_id},
        {
            "$set": {
                "last_analysis": analysis_text,
                "last_analysis_at": now,
                "updated_at": now,
            }
        },
    )
    usage = await _track_usage(owner_id, plan, "analyses")
    return {
        "success": True,
        "analysis": analysis_text,
        "plan": plan,
        "scope_label": _scope_label(plan),
        "usage": usage,
        "daily_limit": limits.get("analyses_per_day", -1),
    }


@router.get("/history")
async def ai_photo_history(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
    project_id: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    query: Dict[str, Any] = {"owner_id": owner_id}
    if project_id:
        query["project_id"] = project_id

    rows = (
        await db[COLL_GENERATIONS]
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
        .to_list(limit)
    )
    total = await db[COLL_GENERATIONS].count_documents(query)
    return {
        "success": True,
        "history": [_normalize_generation_doc(item) for item in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.put("/brand-preset")
async def ai_photo_save_brand_preset(payload: BrandPresetRequest, request: Request) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    now = _now_iso()
    preset_doc = {
        "owner_id": owner_id,
        "name": payload.name.strip(),
        "primary_goal": payload.primary_goal.strip(),
        "audience": (payload.audience or "").strip(),
        "visual_constraints": (payload.visual_constraints or "").strip(),
        "updated_at": now,
    }
    await db[COLL_BRAND_PRESETS].update_one(
        {"owner_id": owner_id},
        {"$set": preset_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    saved = await db[COLL_BRAND_PRESETS].find_one({"owner_id": owner_id}, {"_id": 0})
    return {"success": True, "brand_preset": saved}


@router.get("/brand-preset")
async def ai_photo_get_brand_preset(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    user = await _get_current_user_or_none(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    preset = await db[COLL_BRAND_PRESETS].find_one({"owner_id": owner_id}, {"_id": 0})
    return {"success": True, "brand_preset": preset}


@router.get("/file/{image_id}")
async def ai_photo_get_file(image_id: str) -> Response:
    row = await db[COLL_ASSETS].find_one({"image_id": image_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")
    blob = base64.b64decode(row.get("bytes_b64") or "")
    return Response(content=blob, media_type=row.get("content_type") or "image/png")
