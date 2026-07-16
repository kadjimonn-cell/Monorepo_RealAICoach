"""Shared helpers for jobs and employer-console routes."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage
from fastapi import HTTPException, Request

from .db import User, db, get_current_user
from utils.access_control_engine import PLAN_LEVEL, compute_effective_plan, normalize_plan

logger = logging.getLogger("routes.jobs.shared")

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

PIPELINE_STAGES: List[str] = ["applied", "viewed", "interview", "offer", "hired", "rejected"]
PIPELINE_STAGE_SET = set(PIPELINE_STAGES)
PIPELINE_STAGE_ORDER = {stage: idx for idx, stage in enumerate(PIPELINE_STAGES)}

OFFER_STATUS_ORDER: Dict[str, int] = {
    "draft": 0,
    "pending_approval": 1,
    "approved": 2,
    "sent": 3,
    "accepted": 4,
    "declined": 4,
    "expired": 4,
}
OFFER_STATUS_SET = set(OFFER_STATUS_ORDER.keys())


def is_terminal_application_status(status: Optional[str]) -> bool:
    return normalize_pipeline_status(status) in {"hired", "rejected"}


def validate_application_transition(current_status: Optional[str], new_status: Optional[str]) -> Dict[str, Any]:
    current = normalize_pipeline_status(current_status)
    new = normalize_pipeline_status(new_status)

    if current == new:
        return {"allowed": True, "reason": "noop"}

    if is_terminal_application_status(current):
        return {"allowed": False, "reason": f"terminal_status:{current}"}

    if new == "rejected":
        return {"allowed": True, "reason": "allowed_terminal_reject"}

    if new not in PIPELINE_STAGE_ORDER:
        return {"allowed": False, "reason": "invalid_target_status"}

    if new == "hired" and current not in {"interview", "offer"}:
        return {"allowed": False, "reason": f"hired_requires_interview_or_offer:{current}"}

    current_rank = PIPELINE_STAGE_ORDER.get(current, 0)
    new_rank = PIPELINE_STAGE_ORDER.get(new, 0)
    if new_rank < current_rank:
        return {"allowed": False, "reason": f"reverse_transition:{current}->{new}"}

    return {"allowed": True, "reason": "forward_transition"}


def normalize_offer_status(status: Optional[str]) -> str:
    candidate = str(status or "draft").strip().lower()
    return candidate if candidate in OFFER_STATUS_SET else "draft"


def validate_offer_transition(current_status: Optional[str], new_status: Optional[str], approval_status: Optional[str] = None) -> Dict[str, Any]:
    current = normalize_offer_status(current_status)
    new = normalize_offer_status(new_status)
    approval = str(approval_status or "").strip().lower()

    if current == new:
        return {"allowed": True, "reason": "noop"}

    if current in {"accepted", "declined", "expired"}:
        return {"allowed": False, "reason": f"terminal_offer_status:{current}"}

    if new == "approved" and approval != "approved":
        return {"allowed": False, "reason": "approved_requires_approval_status_approved"}

    if new == "sent" and approval != "approved":
        return {"allowed": False, "reason": "sent_requires_approval"}

    if new in {"accepted", "declined"} and current != "sent":
        return {"allowed": False, "reason": f"decision_requires_sent_offer:{current}"}

    if new == "pending_approval" and current != "draft":
        return {"allowed": False, "reason": f"pending_approval_requires_draft:{current}"}

    current_rank = OFFER_STATUS_ORDER.get(current, 0)
    new_rank = OFFER_STATUS_ORDER.get(new, 0)
    if new_rank < current_rank:
        return {"allowed": False, "reason": f"reverse_offer_transition:{current}->{new}"}

    return {"allowed": True, "reason": "forward_offer_transition"}


async def require_auth(request: Request) -> User:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def resolve_hiring_effective_plan(user: User) -> str:
    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {
            "_id": 0,
            "user_id": 1,
            "is_admin": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "payment_verified": 1,
            "pending_subscription_transition": 1,
        },
    )
    return normalize_plan(compute_effective_plan(user_doc or {}))


async def require_hiring_plan(request: Request, *, min_plan: str = "free") -> Dict[str, Any]:
    user = await require_auth(request)
    effective_plan = await resolve_hiring_effective_plan(user)
    target_plan = normalize_plan(min_plan)
    if PLAN_LEVEL.get(effective_plan, 0) < PLAN_LEVEL.get(target_plan, 0):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Subscription Required",
                "message": f"This hiring workflow requires a {target_plan.title()} plan or higher.",
                "current_plan": effective_plan,
                "required_plan": target_plan,
                "upgrade_url": "/subscription/plans",
            },
        )
    return {"user": user, "effective_plan": effective_plan}


async def record_hiring_workflow_event(
    *,
    request: Optional[Request],
    event_type: str,
    user_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        path = str(request.url.path) if request else ""
        method = str(request.method) if request else ""
        correlation_id = ""
        if request:
            correlation_id = (
                request.headers.get("x-correlation-id")
                or request.headers.get("x-request-id")
                or ""
            )

        await db.hiring_workflow_events.insert_one(
            {
                "event_id": f"hwe_{uuid.uuid4().hex[:14]}",
                "event_type": str(event_type or "unknown"),
                "user_id": str(user_id or ""),
                "path": path,
                "method": method,
                "correlation_id": correlation_id,
                "metadata": metadata or {},
                "created_at": now_iso,
            }
        )
    except Exception as exc:
        logger.warning("hiring workflow event log failed: %s", exc)


async def require_employer(request: Request) -> User:
    user = await require_auth(request)
    app = await db.employer_applications.find_one(
        {"user_id": user.user_id, "status": "approved"}, {"_id": 0, "permissions": 1}
    )
    if not app or "post_job" not in app.get("permissions", []):
        raise HTTPException(status_code=403, detail="Approved employer access required")
    return user


async def ai_call(system_msg: str, user_msg: str, session_id: str | None = None) -> str:
    if not EMERGENT_KEY:
        return "{}"
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=session_id or f"jobs_{uuid.uuid4().hex[:8]}",
            system_message=system_msg,
        ).with_model("openai", "gpt-5.2")
        return await chat.send_message(UserMessage(text=user_msg))
    except Exception as exc:
        logger.warning("AI call failed: %s", exc)
        return "{}"


def normalize_pipeline_status(status: Optional[str]) -> str:
    normalized = str(status or "applied").strip().lower()
    return normalized if normalized in PIPELINE_STAGE_SET else "applied"


async def append_application_timeline_event(
    *,
    application_id: str,
    job_id: str,
    actor_user_id: str,
    event_type: str,
    title: str,
    description: str,
    status: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not application_id:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.job_application_timeline_events.insert_one(
        {
            "event_id": f"apptl_{uuid.uuid4().hex[:14]}",
            "application_id": application_id,
            "job_id": job_id,
            "actor_user_id": actor_user_id,
            "event_type": event_type,
            "title": title,
            "description": description,
            "status": normalize_pipeline_status(status) if status else None,
            "metadata": metadata or {},
            "created_at": now_iso,
        }
    )


def safe_days_since(iso_value: Optional[str]) -> int:
    if not iso_value:
        return 0
    try:
        dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 0


def stage_target_days(stage: str) -> int:
    mapping = {
        "applied": 3,
        "viewed": 2,
        "interview": 5,
        "offer": 4,
        "hired": 999,
        "rejected": 999,
    }
    return mapping.get(normalize_pipeline_status(stage), 3)


def compute_candidate_match(
    *,
    job_doc: Dict[str, Any],
    application_doc: Dict[str, Any],
    profile_doc: Dict[str, Any],
) -> Dict[str, Any]:
    job_skills = {str(s).strip().lower() for s in (job_doc.get("skills") or []) if str(s).strip()}
    app_skills = {str(s).strip().lower() for s in (application_doc.get("skills") or []) if str(s).strip()}
    profile_skills = {str(s).strip().lower() for s in (profile_doc.get("skills") or []) if str(s).strip()}
    candidate_skills = app_skills or profile_skills
    overlap = sorted(job_skills & candidate_skills)

    score = 0.0
    reasons: List[str] = []
    if job_skills:
        skill_ratio = len(overlap) / max(len(job_skills), 1)
        score += 55.0 * skill_ratio
        if overlap:
            reasons.append(f"Skill overlap: {', '.join(overlap[:4])}")
    else:
        score += 35.0
        reasons.append("Role has no mandatory skill constraints")

    resume_score = float(profile_doc.get("resume_score") or 0)
    score += min(20.0, resume_score * 0.2)
    reasons.append(f"Resume quality score: {int(resume_score)}/100")

    location = str(job_doc.get("location") or "").lower()
    candidate_pref = str(profile_doc.get("preferred_location") or "").lower()
    if candidate_pref and location and candidate_pref in location:
        score += 10
        reasons.append("Location preference match")
    elif bool(job_doc.get("remote")) or bool(profile_doc.get("remote_only")):
        score += 8
        reasons.append("Remote compatibility")

    experience_required = int(job_doc.get("experience_years") or 0)
    experience_candidate = int(profile_doc.get("experience_years") or 0)
    if experience_required <= 0:
        score += 10
        reasons.append("No minimum experience gate")
    elif experience_candidate >= experience_required:
        score += 15
        reasons.append(f"Experience fit ({experience_candidate}y vs required {experience_required}y)")
    else:
        gap_penalty = min(10, max(1, experience_required - experience_candidate) * 2)
        score -= gap_penalty
        reasons.append(f"Experience gap ({experience_candidate}y vs required {experience_required}y)")

    normalized = int(max(0, min(100, round(score))))
    tier = "high" if normalized >= 75 else "medium" if normalized >= 50 else "low"
    return {"match_score": normalized, "match_tier": tier, "match_reasons": reasons[:5]}


def build_copilot_actions(*, stage: str, sla_breached: bool, match_score: int, has_interview: bool) -> List[Dict[str, Any]]:
    stage_norm = normalize_pipeline_status(stage)
    actions: List[Dict[str, Any]] = []
    if stage_norm == "applied":
        actions.append({"action_key": "move_viewed", "label": "Mark as Viewed", "type": "status", "priority": "high"})
    if stage_norm in {"viewed", "applied"} and match_score >= 60:
        actions.append({"action_key": "move_interview", "label": "Move to Interview", "type": "status", "priority": "high"})
    if stage_norm == "interview" and has_interview:
        actions.append({"action_key": "send_followup", "label": "Send Interview Follow-up", "type": "communication", "priority": "medium"})
    if stage_norm == "interview" and match_score >= 70:
        actions.append({"action_key": "move_offer", "label": "Move to Offer", "type": "status", "priority": "high"})
    if stage_norm == "offer":
        actions.append({"action_key": "move_hired", "label": "Mark as Hired", "type": "status", "priority": "high"})
    if sla_breached:
        actions.append({"action_key": "send_followup", "label": "Send Priority Follow-up", "type": "communication", "priority": "high"})
    if stage_norm not in {"hired", "rejected"}:
        actions.append({"action_key": "reject_candidate", "label": "Reject Candidate", "type": "status", "priority": "low"})
    dedup: Dict[str, Dict[str, Any]] = {}
    for action in actions:
        dedup[action["action_key"]] = action
    return list(dedup.values())[:6]


async def get_owned_application_for_employer(user: User, application_id: str) -> Dict[str, Any]:
    app = await db.job_applications.find_one({"application_id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    job = await db.jobs.find_one({"job_id": app.get("job_id"), "poster_user_id": user.user_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=403, detail="Not authorized for this application")
    return {"application": app, "job": job}


async def send_candidate_followup_email(
    *,
    candidate_email: str,
    candidate_name: str,
    employer_name: str,
    role_title: str,
    note: str,
) -> Dict[str, Any]:
    from utils.email_service import send_catalog_template

    body = f"Recruiter update from {employer_name or 'Hiring Team'} for {role_title}: {note or 'Please check your latest hiring update.'}"
    return await send_catalog_template(
        candidate_email,
        "user_notification_alert",
        candidate_name or "Candidate",
        alert_title=f"Recruiter update — {role_title}",
        message=body,
        context_type="recruiter_followup",
        action_url="/job-platform",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def normalize_recommendation(value: Optional[str]) -> str:
    allowed = {"strong_hire", "hire", "lean_hire", "no_hire"}
    candidate = str(value or "lean_hire").strip().lower()
    return candidate if candidate in allowed else "lean_hire"


def clamp_score_1_5(value: Any) -> int:
    try:
        score = int(value)
    except Exception:
        score = 3
    return max(1, min(5, score))


def build_sequence_steps(app: Dict[str, Any], job: Dict[str, Any], employer_name: str) -> List[Dict[str, str]]:
    candidate_name = app.get("candidate_name") or "Candidate"
    role_title = job.get("title") or "the role"
    stage = normalize_pipeline_status(app.get("status"))
    return [
        {
            "key": "warm_acknowledgement",
            "title": f"Thanks for your interest in {role_title}",
            "message": (
                f"Hi {candidate_name}, thanks for your continued interest in {role_title}. "
                f"{employer_name or 'Our hiring team'} is reviewing your profile and will share next steps shortly."
            ),
        },
        {
            "key": "stage_context",
            "title": f"Current stage: {stage.title()}",
            "message": (
                f"Quick update: your application is currently in '{stage}' stage for {role_title}. "
                "If your availability changed, please reply with your preferred schedule windows."
            ),
        },
        {
            "key": "final_touchpoint",
            "title": "Final check-in from recruiting",
            "message": (
                f"We're keeping your profile active for {role_title}. "
                "Please share any recent achievements or portfolio updates to strengthen your candidacy."
            ),
        },
    ]


async def send_candidate_notification_with_optional_email(
    *,
    user_id: str,
    email: str,
    title: str,
    message: str,
    notif_type: str,
    send_email: bool,
) -> None:
    if send_email:
        from utils.notification_helper import create_notification_for_email

        await create_notification_for_email(user_id, email, title, message, notif_type)
        return

    from utils.notification_helper import create_notification

    await create_notification(user_id, title, message, notif_type, {})