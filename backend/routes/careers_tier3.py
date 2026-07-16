"""
Careers ATS — Tier 3 enhancements (autonomous batch).

Features shipped:
  1. Auto-score on ingest            — resume-score triggered inside /careers/apply
  2. Async Video Questions           — public pre-screen recording + admin review
  3. Offer Counteroffer Studio       — candidate public counter + admin decision
  4. Talent Pool / Silver Medalist   — auto-tag + nurture email cadence
  5. Portal link in status emails    — (wired inline in careers.py status-update handler)
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from routes.db import db, require_admin
from routes.careers_common import offer_public_token_query
from utils.file_security_service import enforce_file_security

logger = logging.getLogger(__name__)
router = APIRouter()

APPS_COL = "careers_applications"
VIDEO_QA_COL = "careers_video_qa"
OFFERS_COL = "careers_offers"
NURTURE_COL = "careers_nurture_log"
VIDEO_QA_MEDIA_DIR = Path("/app/backend/media/careers_video_qa")
VIDEO_QA_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_QA_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50MB


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_base(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "realaicoach.app"
    scheme = request.headers.get("x-forwarded-proto") or "https"
    return f"{scheme}://{host}"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Auto-score on ingest — helper called from /careers/apply
# ─────────────────────────────────────────────────────────────────────────────


async def auto_score_on_ingest(app_id: str) -> None:
    """Fire-and-forget: compute + persist AI resume score on the new application.
    Never raises — silently logs failures so the apply flow is never blocked."""
    try:
        doc = await db[APPS_COL].find_one({"application_id": app_id})
        if not doc:
            return
        # Lazy-import to dodge circular deps and to keep the apply path fast on LLM-less builds.
        from routes.careers_tier1 import _extract_resume_text
        from routes.careers_enhancements import _resolve_role_rubric
        from utils.llm_helper import generate_verified_json

        resume_text = _extract_resume_text(doc)
        if len(resume_text) < 40:
            logger.info(f"[careers/auto-score] {app_id}: insufficient resume text ({len(resume_text)}ch), skipping")
            return
        role_title = doc.get("role_title") or "Open role"
        rubric = _resolve_role_rubric(role_title)
        criteria_ids = [c["id"] for c in rubric["criteria"]]
        system = (
            "You are a senior recruiter scoring a resume against a role. Return strict JSON: "
            '{"score": <0-100>, "fit_score": <0-100>, "cultural_fit_pct": <0-100>, '
            '"rubric_scores": {<id>: <1-5>}, "skills_matched": [<str>], "skills_missing": [<str>], '
            '"top_strengths": [<str>], "top_gaps": [<str>], "one_liner_summary": "<1 sentence>"}. '
            "Be rigorous — reserve 90+ for exceptional fits."
        )
        prompt = (
            f"ROLE: {role_title}\nRUBRIC ids: {', '.join(criteria_ids)}\n\nRESUME:\n{resume_text}\n\n"
            f"Produce the JSON score."
        )
        result = await generate_verified_json(
            prompt=prompt,
            system_message=system,
            session_id=f"auto-score-{app_id[-8:]}",
            model="gpt-4o",
            feature="careers_auto_score_on_ingest",
        )
        def _clamp(v, lo, hi, d):
            try:
                return max(lo, min(hi, int(v)))
            except Exception:
                return d
        score = _clamp((result or {}).get("score"), 0, 100, 50)
        fit = _clamp((result or {}).get("fit_score"), 0, 100, score)
        cultural = _clamp((result or {}).get("cultural_fit_pct"), 0, 100, 50)
        rubric_scores = {cid: _clamp(((result or {}).get("rubric_scores") or {}).get(cid, 3), 1, 5, 3) for cid in criteria_ids}
        payload = {
            "score": score,
            "fit_score": fit,
            "cultural_fit_pct": cultural,
            "rubric_key": rubric["role_key"],
            "rubric_scores": rubric_scores,
            "skills_matched": list(map(str, (result or {}).get("skills_matched") or []))[:20],
            "skills_missing": list(map(str, (result or {}).get("skills_missing") or []))[:20],
            "top_strengths": list(map(str, (result or {}).get("top_strengths") or []))[:5],
            "top_gaps": list(map(str, (result or {}).get("top_gaps") or []))[:5],
            "one_liner_summary": str((result or {}).get("one_liner_summary") or "")[:400],
            "source": "auto_on_ingest",
            "model": "gpt-4o",
            "generated_at": _now_iso(),
        }
        await db[APPS_COL].update_one(
            {"application_id": app_id},
            {"$set": {"resume_score": payload}},
        )
        logger.info(f"[careers/auto-score] {app_id}: scored {score}/100 on ingest")
    except Exception as e:
        logger.warning(f"[careers/auto-score] {app_id}: failed silently — {str(e)[:140]}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Async Video Questions — pre-screen recordings
# ─────────────────────────────────────────────────────────────────────────────

ROLE_VIDEO_QUESTIONS: dict[str, list[str]] = {
    "engineering": [
        "Walk me through the most technically complex system you've built, and what you'd do differently today.",
        "Describe a time you had to debug a hard production issue. What was your process?",
        "Why this role, and why now? What specifically excites you about what we're building?",
    ],
    "sales": [
        "Tell me about the most challenging deal you've closed and what made it hard.",
        "How do you handle an objection from a skeptical, technically-savvy buyer?",
        "Why this role, and why now? What specifically excites you about what we're building?",
    ],
    "marketing": [
        "Describe a growth experiment you ran. What was the hypothesis, result, and what did you learn?",
        "How do you balance brand-building vs. short-term performance marketing?",
        "Why this role, and why now? What specifically excites you about what we're building?",
    ],
    "design": [
        "Walk me through a design decision you made that was difficult to defend but you believed was right.",
        "How do you balance design craft with fast iteration and stakeholder constraints?",
        "Why this role, and why now? What specifically excites you about what we're building?",
    ],
    "operations": [
        "Tell me about a process you built from scratch. How did you know it was working?",
        "Describe a time you had to coordinate across 3+ stakeholders with conflicting priorities.",
        "Why this role, and why now? What specifically excites you about what we're building?",
    ],
    "generic": [
        "Tell me about yourself — the 90-second version.",
        "What's the most meaningful work you've done in the last year?",
        "Why this role, and why now? What specifically excites you about what we're building?",
    ],
}


class VideoInviteBody(BaseModel):
    role_key: Optional[str] = None  # let server resolve from role_title when omitted


@router.post("/careers/applications/{app_id}/video-qa/invite")
async def admin_create_video_invite(request: Request, app_id: str, body: VideoInviteBody):
    """Admin creates a video-qa invitation (magic link) for an applicant."""
    await require_admin(request)
    app_doc = await db[APPS_COL].find_one({"application_id": app_id})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")

    from routes.careers_enhancements import _resolve_role_rubric
    role_title = app_doc.get("role_title") or "Open Role"
    role_key = body.role_key or _resolve_role_rubric(role_title)["role_key"]
    questions = ROLE_VIDEO_QUESTIONS.get(role_key) or ROLE_VIDEO_QUESTIONS["generic"]
    token = secrets.token_urlsafe(24)
    invite = {
        "invite_id": f"vqa_{uuid.uuid4().hex[:12]}",
        "application_id": app_id,
        "candidate_email": app_doc.get("email") or "",
        "candidate_name": app_doc.get("name") or "Candidate",
        "role_title": role_title,
        "role_key": role_key,
        "token": token,
        "questions": questions,
        "answers": [],
        "status": "invited",
        "created_at": _now_iso(),
    }
    await db[VIDEO_QA_COL].insert_one(invite)
    invite.pop("_id", None)
    base = _public_base(request)
    return {"ok": True, "invite": invite, "public_url": f"{base}/careers/video-qa/{token}"}


@router.get("/careers/video-qa/{token}")
async def public_video_qa_view(token: str):
    """PUBLIC — candidate fetches their questions + status. No auth."""
    if not token or len(token) < 16:
        raise HTTPException(status_code=404, detail="Invalid invite")
    doc = await db[VIDEO_QA_COL].find_one({"token": token}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Invite not found")
    answered_indices = {a.get("question_index") for a in (doc.get("answers") or [])}
    return {
        "invite_id": doc.get("invite_id"),
        "candidate_name": doc.get("candidate_name"),
        "role_title": doc.get("role_title"),
        "questions": [
            {
                "index": i,
                "prompt": q,
                "answered": i in answered_indices,
                "max_seconds": 120,
            } for i, q in enumerate(doc.get("questions") or [])
        ],
        "status": doc.get("status"),
        "submitted_at": doc.get("submitted_at"),
    }


class VideoAnswerBody(BaseModel):
    question_index: int = Field(..., ge=0, le=10)
    video_data_url: str = Field(..., min_length=20, max_length=20_000_000)
    duration_seconds: float = Field(0, ge=0, le=600)


def _video_extension(filename: str | None, content_type: str | None) -> str:
    ct = str(content_type or "").strip().lower()
    ext = os.path.splitext(str(filename or ""))[1].lower()
    if ext in {".webm", ".mp4", ".mov", ".mkv", ".avi", ".m4v"}:
        return ext
    mapping = {
        "video/webm": ".webm",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-matroska": ".mkv",
        "video/x-msvideo": ".avi",
    }
    return mapping.get(ct, ".webm")


def _is_allowed_video_mime(content_type: str) -> bool:
    ct = str(content_type or "").strip().lower()
    return ct.startswith("video/") or ct == "application/octet-stream"


@router.post("/careers/video-qa/{token}/answer")
async def public_video_qa_submit_answer(
    token: str,
    request: Request,
    question_index: int | None = Form(default=None),
    duration_seconds: float = Form(default=0),
    video_file: UploadFile | None = File(default=None),
):
    """PUBLIC — candidate uploads one video answer.

    Supports multipart uploads (`video_file`) and legacy JSON data-url payloads.
    """
    if not token or len(token) < 16:
        raise HTTPException(status_code=404, detail="Invalid invite")
    doc = await db[VIDEO_QA_COL].find_one({"token": token})
    if not doc:
        raise HTTPException(status_code=404, detail="Invite not found")
    if doc.get("status") == "submitted":
        raise HTTPException(status_code=409, detail="Already submitted")

    content_type_header = str(request.headers.get("content-type") or "").lower()
    raw: bytes
    resolved_question_index: int
    resolved_duration_seconds: float
    resolved_content_type: str
    upload_filename: str

    if "multipart/form-data" in content_type_header:
        if video_file is None:
            raise HTTPException(status_code=400, detail="video_file is required")
        if question_index is None:
            raise HTTPException(status_code=400, detail="question_index is required")
        resolved_question_index = int(question_index)
        resolved_duration_seconds = float(duration_seconds or 0)
        resolved_content_type = str(video_file.content_type or "application/octet-stream").lower()
        if not _is_allowed_video_mime(resolved_content_type):
            raise HTTPException(status_code=400, detail=f"Invalid video content type: {resolved_content_type}")
        raw = await video_file.read()
        upload_filename = str(video_file.filename or "answer.webm")
    else:
        try:
            payload_json = await request.json()
            payload = VideoAnswerBody(**payload_json)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON upload payload")
        resolved_question_index = int(payload.question_index)
        resolved_duration_seconds = float(payload.duration_seconds or 0)
        data = payload.video_data_url
        if not data.startswith("data:video/") and not data.startswith("data:application/octet-stream"):
            raise HTTPException(status_code=400, detail="video_data_url must be a data:video/* base64 URL")
        try:
            header, b64 = data.split(",", 1)
            raw = base64.b64decode(b64, validate=True)
            mime_raw = header.split(";", 1)[0].replace("data:", "").strip().lower()
            resolved_content_type = mime_raw or "application/octet-stream"
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 payload")
        upload_filename = f"legacy-{resolved_question_index}.webm"

    size = len(raw)
    if size <= 0:
        raise HTTPException(status_code=400, detail="Empty upload payload")
    if size > VIDEO_QA_MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Video exceeds 50MB — please upload a smaller clip")
    if resolved_question_index < 0 or resolved_question_index > 10:
        raise HTTPException(status_code=400, detail="question_index must be between 0 and 10")
    if resolved_duration_seconds < 0 or resolved_duration_seconds > 600:
        raise HTTPException(status_code=400, detail="duration_seconds must be between 0 and 600")

    try:
        antivirus = enforce_file_security(
            content=raw,
            claimed_content_type=resolved_content_type,
            allowed_content_types={
                "application/octet-stream",
                "video/webm",
                "video/mp4",
                "video/quicktime",
                "video/x-matroska",
                "video/x-msvideo",
            },
            allow_unrecognized_signatures=True,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Upload failed security scan")

    ext = _video_extension(upload_filename, resolved_content_type)
    answer_id = f"vqaans_{uuid.uuid4().hex[:14]}"
    disk_name = f"{answer_id}{ext}"
    disk_path = VIDEO_QA_MEDIA_DIR / disk_name
    with open(disk_path, "wb") as fp:
        fp.write(raw)

    relative_video_url = f"/api/media/careers_video_qa/{disk_name}"

    answers: list[dict[str, Any]] = list(doc.get("answers") or [])
    # Replace any existing answer for the same index
    replaced_answers = [a for a in answers if a.get("question_index") == resolved_question_index]
    for existing in replaced_answers:
        existing_path = str(existing.get("storage_path") or "").strip()
        if existing_path:
            try:
                os.remove(existing_path)
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning("[careers/video-qa] failed to remove replaced answer media: %s", e)

    answers = [a for a in answers if a.get("question_index") != resolved_question_index]
    answers.append({
        "question_index": resolved_question_index,
        "answer_id": answer_id,
        "video_url": relative_video_url,
        "storage_path": str(disk_path),
        "storage_backend": "filesystem",
        "content_type": resolved_content_type,
        "duration_seconds": round(max(0.0, resolved_duration_seconds), 1),
        "size_bytes": size,
        "security_scan": antivirus,
        "submitted_at": _now_iso(),
    })
    answers.sort(key=lambda a: a["question_index"])
    total = len(doc.get("questions") or [])
    all_done = len(answers) >= total
    update = {"answers": answers, "status": "submitted" if all_done else "in_progress"}
    if all_done:
        update["submitted_at"] = _now_iso()
    await db[VIDEO_QA_COL].update_one({"token": token}, {"$set": update})
    return {"ok": True, "answered": len(answers), "total": total, "status": update["status"]}


@router.get("/media/careers_video_qa/{filename}")
async def serve_video_qa_media(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = VIDEO_QA_MEDIA_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return FileResponse(
        str(file_path),
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/careers/applications/{app_id}/video-qa")
async def admin_list_video_qa(request: Request, app_id: str):
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db[VIDEO_QA_COL].find({"application_id": app_id}, {"_id": 0}).sort("created_at", -1):
        items.append(d)
    return {"items": items, "count": len(items)}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Offer Counteroffer Studio
# ─────────────────────────────────────────────────────────────────────────────


class PublicCounterBody(BaseModel):
    base_salary_request: Optional[float] = Field(None, ge=0, le=10_000_000)
    equity_request: Optional[str] = Field(None, max_length=200)
    signing_bonus_request: Optional[float] = Field(None, ge=0, le=5_000_000)
    start_date_request: Optional[str] = Field(None, max_length=40)
    message: str = Field(..., min_length=10, max_length=2000)


@router.post("/careers/offers/public/{token}/counter")
async def public_offer_counter(token: str, body: PublicCounterBody):
    """PUBLIC — candidate submits a counter from the public offer page."""
    if not token or len(token) < 12:
        raise HTTPException(status_code=404, detail="Invalid token")
    offer = await db[OFFERS_COL].find_one(offer_public_token_query(token))
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.get("status") in ("accepted", "declined", "expired", "rescinded"):
        raise HTTPException(status_code=409, detail=f"Offer already {offer.get('status')}")
    now = _now_iso()
    counter = {
        "counter_id": f"cnt_{uuid.uuid4().hex[:10]}",
        "base_salary_request": body.base_salary_request,
        "equity_request": body.equity_request,
        "signing_bonus_request": body.signing_bonus_request,
        "start_date_request": body.start_date_request,
        "message": body.message,
        "submitted_at": now,
        "decision": "pending",
    }
    counters: list[dict[str, Any]] = list(offer.get("counters") or [])
    counters.append(counter)
    await db[OFFERS_COL].update_one(
        {"offer_id": offer.get("offer_id")},
        {"$set": {
            "counters": counters,
            "status": "countered",
            "counter_pending": True,
            "counter_submitted_at": now,
        }},
    )
    logger.info(f"[careers/offers] counter submitted for offer={offer.get('offer_id')} by candidate")
    return {"ok": True, "counter_id": counter["counter_id"], "status": "countered"}


class CounterDecisionBody(BaseModel):
    counter_id: str = Field(..., min_length=4)
    decision: str = Field(..., pattern="^(approve|reject|revise)$")
    revised_base_salary: Optional[float] = Field(None, ge=0, le=10_000_000)
    revised_equity: Optional[str] = Field(None, max_length=200)
    revised_signing_bonus: Optional[float] = Field(None, ge=0, le=5_000_000)
    admin_note: Optional[str] = Field(None, max_length=2000)


@router.post("/careers/offers/{offer_id}/counter/decide")
async def admin_decide_counter(request: Request, offer_id: str, body: CounterDecisionBody):
    """Admin approves / rejects / revises a candidate counter."""
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    offer = await db[OFFERS_COL].find_one({"offer_id": offer_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    counters: list[dict[str, Any]] = list(offer.get("counters") or [])
    idx = next((i for i, c in enumerate(counters) if c.get("counter_id") == body.counter_id), -1)
    if idx == -1:
        raise HTTPException(status_code=404, detail="Counter not found on offer")
    if counters[idx].get("decision") != "pending":
        raise HTTPException(status_code=409, detail=f"Counter already {counters[idx].get('decision')}")

    now = _now_iso()
    counters[idx] = {
        **counters[idx],
        "decision": body.decision,
        "decided_at": now,
        "decided_by": actor,
        "admin_note": body.admin_note or "",
        "revised_base_salary": body.revised_base_salary,
        "revised_equity": body.revised_equity,
        "revised_signing_bonus": body.revised_signing_bonus,
    }

    update: dict[str, Any] = {"counters": counters, "counter_pending": False}
    # If approve → adopt the candidate's ask into the offer terms.
    # If revise → adopt the revised_* terms.
    # If reject → no-op on offer terms, just mark.
    if body.decision == "approve":
        c = counters[idx]
        if c.get("base_salary_request") is not None:
            update["base_salary"] = c["base_salary_request"]
        if c.get("equity_request"):
            update["equity"] = c["equity_request"]
        if c.get("signing_bonus_request") is not None:
            update["signing_bonus"] = c["signing_bonus_request"]
        if c.get("start_date_request"):
            update["start_date"] = c["start_date_request"]
        update["status"] = "countered_approved"
    elif body.decision == "revise":
        if body.revised_base_salary is not None:
            update["base_salary"] = body.revised_base_salary
        if body.revised_equity:
            update["equity"] = body.revised_equity
        if body.revised_signing_bonus is not None:
            update["signing_bonus"] = body.revised_signing_bonus
        update["status"] = "countered_revised"
    else:
        update["status"] = "countered_rejected"

    await db[OFFERS_COL].update_one({"offer_id": offer_id}, {"$set": update})
    return {"ok": True, "decision": body.decision, "offer_id": offer_id, "counter_id": body.counter_id}


@router.get("/careers/offers/counter-queue")
async def admin_counter_queue(request: Request):
    """Admin dashboard feed of all offers with pending candidate counters."""
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db[OFFERS_COL].find({"counter_pending": True}, {"_id": 0}).sort("counter_submitted_at", 1).limit(100):
        counters = d.get("counters") or []
        pending = [c for c in counters if c.get("decision") == "pending"]
        if pending:
            items.append({
                "offer_id": d.get("offer_id"),
                "application_id": d.get("application_id"),
                "candidate_name": d.get("candidate_name") or "",
                "role_title": d.get("role_title") or "",
                "current_base_salary": d.get("base_salary"),
                "current_equity": d.get("equity"),
                "current_signing_bonus": d.get("signing_bonus"),
                "pending_counter": pending[-1],
                "counter_submitted_at": d.get("counter_submitted_at"),
                "ai_recommendation": d.get("counter_ai_recommendation"),
            })
    return {"items": items, "count": len(items)}


# ─────────────────────────────────────────────────────────────────────────────
# 3b. AI-Assisted Counteroffer Decision Helper (GPT-4o)
# ─────────────────────────────────────────────────────────────────────────────

_COUNTER_AI_CACHE_TTL_SEC = 3600  # 1 hour

@router.post("/careers/offers/{offer_id}/counter/ai-analyze")
async def admin_counter_ai_analyze(request: Request, offer_id: str):
    """Use GPT-4o to recommend accept/reject/revise for a pending counteroffer.

    Returns:
      - recommendation: 'accept' | 'reject' | 'revise'
      - confidence: 0-100
      - rationale: one-line explanation (≤ 180 chars)
      - fair_counter: optional suggested revised numbers (base/equity/signing)
      - cached: bool — True if served from the 1-hour result cache

    The result is persisted on the offer document as `counter_ai_recommendation`
    so the queue endpoint can show it without re-billing GPT on every refresh.
    """
    await require_admin(request)
    offer = await db[OFFERS_COL].find_one({"offer_id": offer_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    counters = offer.get("counters") or []
    pending = next((c for c in counters if c.get("decision") == "pending"), None)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending counter on this offer")

    # Serve from cache if fresh
    cached = offer.get("counter_ai_recommendation")
    if cached and cached.get("counter_id") == pending.get("counter_id"):
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(cached.get("generated_at").replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - ts).total_seconds() < _COUNTER_AI_CACHE_TTL_SEC:
                return {**cached, "cached": True}
        except Exception:
            pass

    # Gather context
    candidate_app = None
    if offer.get("application_id"):
        candidate_app = await db[APPS_COL].find_one(
            {"application_id": offer["application_id"]},
            {"_id": 0, "resume_score": 1, "role_title": 1, "full_name": 1},
        )
    resume_score = ((candidate_app or {}).get("resume_score") or {})

    ask_base = pending.get("base_salary_request")
    ask_equity = pending.get("equity_request")
    ask_signing = pending.get("signing_bonus_request")
    current_base = offer.get("base_salary")
    current_equity = offer.get("equity")
    current_signing = offer.get("signing_bonus")

    delta_base_pct = None
    if isinstance(ask_base, (int, float)) and isinstance(current_base, (int, float)) and current_base:
        delta_base_pct = round((ask_base - current_base) / current_base * 100, 1)

    from utils.llm_helper import generate_verified_json

    system = (
        "You are a senior compensation strategist at a Series-B startup. "
        "Given a candidate's counteroffer against a current offer, and their AI-scored resume, "
        "recommend whether the hiring manager should accept, revise, or reject. "
        "Return STRICT JSON ONLY in this shape: "
        '{"recommendation":"accept|revise|reject","confidence":0-100,'
        '"rationale":"<=180 chars single sentence",'
        '"fair_counter":{"base_salary":<number|null>,"equity":<str|null>,"signing_bonus":<number|null>}} '
        "Guidance: resume score ≥ 85 + ≤10% base bump → lean 'accept'. "
        "Ask 10-20% above current + score 70-85 → lean 'revise' with a midpoint. "
        "Ask > 25% above current OR score < 60 → 'reject'. "
        "Weight candidate tenure signals in the counter_message when present."
    )
    prompt = (
        f"ROLE: {offer.get('role_title') or '(unknown)'}\n"
        f"CANDIDATE: {offer.get('candidate_name') or (candidate_app or {}).get('full_name') or '(anon)'}\n"
        f"AI RESUME SCORE: overall={resume_score.get('score')}, fit={resume_score.get('fit_score')}, cultural={resume_score.get('cultural_fit_pct')}\n"
        f"TOP STRENGTHS: {', '.join((resume_score.get('top_strengths') or [])[:3]) or '—'}\n"
        f"TOP GAPS: {', '.join((resume_score.get('top_gaps') or [])[:3]) or '—'}\n"
        f"CURRENT OFFER — base:{current_base} equity:{current_equity} signing:{current_signing}\n"
        f"CANDIDATE COUNTER — base:{ask_base} equity:{ask_equity} signing:{ask_signing}\n"
        f"BASE DELTA: {delta_base_pct}%\n"
        f"COUNTER MESSAGE: {pending.get('counter_message') or '—'}\n\n"
        "Produce the JSON recommendation."
    )

    try:
        result = await generate_verified_json(
            prompt=prompt,
            system_message=system,
            session_id=f"counter-ai-{offer_id[-8:]}",
            model="gpt-4o",
            feature="careers_counter_ai_analyze",
        )
    except Exception as exc:
        logger.warning("counter_ai_analyze LLM failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI analysis temporarily unavailable")

    rec = (result or {}).get("recommendation") or "revise"
    if rec not in ("accept", "revise", "reject"):
        rec = "revise"
    try:
        conf = max(0, min(100, int((result or {}).get("confidence") or 60)))
    except Exception:
        conf = 60
    rationale = str((result or {}).get("rationale") or "")[:180]
    fair = (result or {}).get("fair_counter") or {}

    payload = {
        "counter_id": pending.get("counter_id"),
        "recommendation": rec,
        "confidence": conf,
        "rationale": rationale,
        "fair_counter": {
            "base_salary": fair.get("base_salary") if isinstance(fair.get("base_salary"), (int, float)) else None,
            "equity": (str(fair.get("equity"))[:200]) if fair.get("equity") else None,
            "signing_bonus": fair.get("signing_bonus") if isinstance(fair.get("signing_bonus"), (int, float)) else None,
        },
        "model": "gpt-4o",
        "generated_at": _now_iso(),
    }

    await db[OFFERS_COL].update_one(
        {"offer_id": offer_id},
        {"$set": {"counter_ai_recommendation": payload}},
    )
    return {**payload, "cached": False}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Talent Pool / Silver Medalist Nurture
# ─────────────────────────────────────────────────────────────────────────────


SILVER_MEDALIST_TAG = "silver-medalist"
FUTURE_FIT_TAG = "future-fit"
NURTURE_INTERVAL_DAYS = 180
NURTURE_CADENCE_LIMIT = 3


async def auto_tag_silver_medalist(app_id: str) -> None:
    """Heuristic: on reject, tag 'silver-medalist' + 'future-fit' if the candidate
    scored ≥70 on AI resume-score OR had any scorecard rec of 'lean_hire' or
    higher. Never raises."""
    try:
        doc = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
        if not doc or doc.get("status") != "rejected":
            return
        if doc.get("merged_into") or doc.get("gdpr_purged_at") or doc.get("gdpr_soft_deleted_at"):
            return
        rs = doc.get("resume_score") or {}
        high_score = int(rs.get("score") or 0) >= 70
        strong_interview = False
        async for sc in db["interview_scorecards"].find({"application_id": app_id}, {"_id": 0, "hire_recommendation": 1}):
            if sc.get("hire_recommendation") in ("strong_hire", "lean_hire"):
                strong_interview = True
                break
        if not (high_score or strong_interview):
            return
        tags = list(doc.get("tags") or [])
        changed = False
        for t in (SILVER_MEDALIST_TAG, FUTURE_FIT_TAG):
            if t not in tags:
                tags.append(t)
                changed = True
        if changed:
            await db[APPS_COL].update_one(
                {"application_id": app_id},
                {"$set": {"tags": tags, "silver_medalist_tagged_at": _now_iso()}},
            )
            logger.info(f"[careers/talent-pool] {app_id}: auto-tagged silver-medalist (score={rs.get('score')}, strong_iv={strong_interview})")
    except Exception as e:
        logger.warning(f"[careers/talent-pool] auto-tag failed for {app_id}: {str(e)[:120]}")


@router.get("/careers/talent-pool")
async def admin_talent_pool(request: Request):
    """List all silver-medalist candidates, ranked by score desc."""
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for d in db[APPS_COL].find(
        {"tags": SILVER_MEDALIST_TAG, "merged_into": {"$exists": False}, "gdpr_purged_at": {"$exists": False}},
        {"_id": 0, "application_id": 1, "name": 1, "email": 1, "role_title": 1, "status": 1,
         "resume_score": 1, "tags": 1, "silver_medalist_tagged_at": 1, "last_nurture_at": 1, "nurture_count": 1},
    ).limit(500):
        rs = d.get("resume_score") or {}
        items.append({
            "application_id": d.get("application_id"),
            "name": d.get("name") or "",
            "email": d.get("email") or "",
            "role_title": d.get("role_title") or "",
            "status": d.get("status") or "",
            "score": rs.get("score"),
            "tags": d.get("tags") or [],
            "tagged_at": d.get("silver_medalist_tagged_at") or "",
            "last_nurture_at": d.get("last_nurture_at") or "",
            "nurture_count": int(d.get("nurture_count") or 0),
        })
    items.sort(key=lambda x: -(x.get("score") or 0))
    return {"items": items, "count": len(items), "tag": SILVER_MEDALIST_TAG}


@router.post("/careers/talent-pool/{app_id}/tag")
async def admin_manual_tag_silver(request: Request, app_id: str):
    """Manual add/remove to silver-medalist pool."""
    await require_admin(request)
    doc = await db[APPS_COL].find_one({"application_id": app_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    tags = list(doc.get("tags") or [])
    if SILVER_MEDALIST_TAG in tags:
        tags = [t for t in tags if t not in (SILVER_MEDALIST_TAG, FUTURE_FIT_TAG)]
        await db[APPS_COL].update_one({"application_id": app_id}, {"$set": {"tags": tags}, "$unset": {"silver_medalist_tagged_at": ""}})
        return {"ok": True, "action": "removed", "tags": tags}
    tags.extend([SILVER_MEDALIST_TAG, FUTURE_FIT_TAG])
    await db[APPS_COL].update_one(
        {"application_id": app_id},
        {"$set": {"tags": tags, "silver_medalist_tagged_at": _now_iso()}},
    )
    return {"ok": True, "action": "added", "tags": tags}


async def _send_nurture_email(app_doc: dict[str, Any]) -> bool:
    """Send one nurture email. Returns True on success."""
    try:
        from utils.email_service import send_email
        from utils.email_templates import TEMPLATE_CATALOG
        email = (app_doc.get("email") or "").strip()
        if not email or "@" not in email:
            return False
        tpl_entry = TEMPLATE_CATALOG.get("career_status_update") or {}
        builder = tpl_entry.get("builder")
        if not builder:
            return False
        name = app_doc.get("name") or "there"
        role_title = app_doc.get("role_title") or "a role at RealAICoach"
        count = int(app_doc.get("nurture_count") or 0) + 1
        note = (
            f"Hi {name.split()[0] if name else 'there'}, your application for {role_title} really stood out "
            "to our hiring team. We wanted to keep in touch because new roles open up every quarter that may "
            "match your background. This is nurture email "
            f"#{count} of {NURTURE_CADENCE_LIMIT} — no action needed, just wanted you to know you're on our radar."
        )
        tpl = builder(
            applicant_name=name,
            role_title=role_title,
            application_id=app_doc.get("application_id"),
            notes=note,
        )
        await send_email(
            recipient_email=email,
            recipient_name=name,
            subject=tpl.subject,
            content=tpl.html,
            content_text=tpl.text,
            template_key="career_status_update",
        )
        return True
    except Exception as e:
        logger.warning(f"[careers/nurture] email send failed: {str(e)[:140]}")
        return False


async def scheduled_silver_medalist_nurture() -> dict[str, Any]:
    """APScheduler daily job: send nurture emails to silver medalists whose
    last_nurture_at is ≥180 days ago AND nurture_count < 3. Never raises."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=NURTURE_INTERVAL_DAYS)).isoformat()
        q = {
            "tags": SILVER_MEDALIST_TAG,
            "merged_into": {"$exists": False},
            "gdpr_purged_at": {"$exists": False},
            "gdpr_soft_deleted_at": {"$exists": False},
            "$and": [
                {"$or": [
                    {"last_nurture_at": {"$exists": False}},
                    {"last_nurture_at": {"$lte": cutoff}},
                ]},
                {"$or": [
                    {"nurture_count": {"$exists": False}},
                    {"nurture_count": {"$lt": NURTURE_CADENCE_LIMIT}},
                ]},
            ],
        }
        sent = 0
        skipped = 0
        async for d in db[APPS_COL].find(q, {"_id": 0}).limit(200):
            ok = await _send_nurture_email(d)
            if ok:
                sent += 1
                now = _now_iso()
                await db[APPS_COL].update_one(
                    {"application_id": d.get("application_id")},
                    {
                        "$set": {"last_nurture_at": now},
                        "$inc": {"nurture_count": 1},
                    },
                )
                await db[NURTURE_COL].insert_one({
                    "nurture_id": f"nurt_{uuid.uuid4().hex[:12]}",
                    "application_id": d.get("application_id"),
                    "sent_at": now,
                    "sequence_num": int(d.get("nurture_count") or 0) + 1,
                    "trigger": "scheduled_180d",
                })
            else:
                skipped += 1
        logger.info(f"[careers/nurture] scheduled run: sent={sent}, skipped={skipped}")
        return {"ok": True, "sent": sent, "skipped": skipped, "ran_at": _now_iso()}
    except Exception as e:
        logger.warning(f"[careers/nurture] scheduled run failed: {str(e)[:140]}")
        return {"ok": False, "reason": "exception", "detail": str(e)[:140]}


@router.post("/careers/talent-pool/nurture/run-now")
async def admin_trigger_nurture(request: Request):
    await require_admin(request)
    return await scheduled_silver_medalist_nurture()
