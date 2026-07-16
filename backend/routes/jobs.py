"""Jobs & Employee System — Smart Job Discovery, Applications, Resume Intelligence."""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import uuid
import os
import json
import logging
import asyncio
import hashlib

from dotenv import load_dotenv

load_dotenv()

from .db import db
from .jobs_employer_console_sla import (
    build_sla_auto_trigger_items,
    execute_sla_auto_trigger_item,
)
from .jobs_employer_console_models import (
    BulkPipelineActionRequest,
    CommunicationSequenceAdvanceRequest,
    CommunicationSequenceStartRequest,
    CopilotExecuteRequest,
    InterviewKitShareRequest,
    InterviewScorecardSubmitRequest,
    OfferApprovalRequest,
    OfferDraftRequest,
    OfferESignRequest,
    OfferSendRequest,
    RediscoveryReengageRequest,
    SlaAutoTriggerRunRequest,
)
from .jobs_employer_console_realtime import broadcast_employer_pipeline_event
from .jobs_shared import (
    EMERGENT_KEY,
    ai_call,
    append_application_timeline_event,
    build_copilot_actions,
    build_sequence_steps,
    clamp_score_1_5,
    compute_candidate_match,
    get_owned_application_for_employer,
    normalize_pipeline_status,
    normalize_offer_status,
    normalize_recommendation,
    record_hiring_workflow_event,
    require_auth,
    require_employer,
    require_hiring_plan,
    safe_days_since,
    send_candidate_followup_email,
    send_candidate_notification_with_optional_email,
    stage_target_days,
    validate_offer_transition,
    validate_application_transition,
)
from .jobs_read_service import (
    build_alert_preferences_update,
    employee_analytics_read,
    get_alert_preferences_read,
    get_employee_profile_read,
    get_job_recommendations_read,
    get_jobs_portal_summary_read,
    get_my_applications_read,
    get_resume_score_read,
    get_saved_jobs_read,
    get_smart_alerts_read,
    search_jobs_read,
)
from .jobs_pipeline_read_service import (
    export_pipeline_audit_csv_read,
    export_pipeline_audit_pdf_read,
    get_communication_sequence_read,
    get_employer_hiring_forecast_read,
    get_employer_kpi_header_read,
    get_employer_pipeline_board_read,
    get_employer_pipeline_timeline_read,
    get_employer_sla_alerts_read,
    get_employer_sla_auto_triggers_read,
    get_interview_scorecards_read,
    get_pipeline_audit_download_history_read,
    get_recruiter_copilot_suggestions_read,
    get_talent_rediscovery_candidates_read,
    list_employer_offers_read,
    suggest_auto_scheduler_slots_read,
)

router = APIRouter(prefix="/jobs")
logger = logging.getLogger("routes.jobs")


DEFAULT_F26_ROLLOUT_CONTROLS: Dict[str, Any] = {
    "key": "feature26_legacy_write_rollout",
    "feature_number": 26,
    "feature_id": "jobs-portal",
    "canary_enabled": False,
    "legacy_allow_pct": 100,
    "auto_rollback_enabled": True,
    "rollback_window_hours": 6,
    "rollback_legacy_event_threshold": 500,
    "soft_disable_operations": [],
    "admin_override_user_ids": [],
    "legacy_retirement_enabled": False,
    "retirement_phase": "observe",
    "retired_legacy_route_families": [],
    "retirement_gate_lookback_hours": 72,
    "retirement_gate_max_events": 20,
    "retirement_gate_max_active_users": 10,
    "retirement_force_apply": False,
    "retirement_override_user_ids": [],
}

F26_OPERATION_V2_ENDPOINT: Dict[str, str] = {
    "candidate_apply": "/api/hiring/v2/candidate/apply",
    "candidate_save_job": "/api/hiring/v2/candidate/save/{job_id}",
    "candidate_profile_update": "/api/hiring/v2/candidate/profile/update",
    "candidate_resume_upload": "/api/hiring/v2/candidate/resume/upload",
    "employer_offer_build": "/api/hiring/v2/employer/offers/build",
    "employer_offer_submit_approval": "/api/hiring/v2/employer/offers/{offer_id}/submit-approval",
    "employer_offer_approve": "/api/hiring/v2/employer/offers/{offer_id}/approve",
    "employer_offer_send": "/api/hiring/v2/employer/offers/{offer_id}/send",
    "employer_copilot_execute": "/api/hiring/v2/employer/pipeline/{application_id}/copilot-execute",
    "employer_pipeline_bulk_action": "/api/hiring/v2/employer/pipeline/bulk-action",
    "employer_status_update": "/api/hiring/v2/employer/pipeline/bulk-action",
}

F26_RETIREMENT_PHASE_TO_FAMILIES: Dict[str, List[str]] = {
    "observe": [],
    "phase1_jobs_writes": ["jobs"],
    "phase2_jobs_employers_writes": ["jobs", "employers"],
}

F26_RETIREMENT_FAMILY_PATH_PREFIX: Dict[str, str] = {
    "jobs": r"^/api/jobs",
    "employers": r"^/api/employers",
}


def _stable_bucket_for_rollout(user_id: str, operation: str) -> int:
    digest = hashlib.sha256(f"{user_id}:{operation}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _normalize_retirement_phase(raw: Any) -> str:
    phase = str(raw or "observe").strip().lower()
    if phase in F26_RETIREMENT_PHASE_TO_FAMILIES:
        return phase
    return "observe"


def _target_retired_route_families(controls: Dict[str, Any]) -> List[str]:
    if not bool(controls.get("legacy_retirement_enabled")):
        return []
    phase = _normalize_retirement_phase(controls.get("retirement_phase"))
    return list(F26_RETIREMENT_PHASE_TO_FAMILIES.get(phase, []))


def _legacy_family_telemetry_query(route_family: str, since_iso: str) -> Dict[str, Any]:
    family = str(route_family or "jobs").strip().lower()
    path_prefix = F26_RETIREMENT_FAMILY_PATH_PREFIX.get(family, r"^/api/jobs")
    return {
        "created_at": {"$gte": since_iso},
        "$or": [
            {"route_family": family},
            {
                "$and": [
                    {"route_family": {"$exists": False}},
                    {"legacy_path": {"$regex": path_prefix}},
                ]
            },
        ],
    }


async def _compute_legacy_retirement_gate_status(
    controls: Dict[str, Any],
    route_family: str,
    lookback_hours_override: Optional[int] = None,
) -> Dict[str, Any]:
    lookback_hours = max(
        1,
        min(
            _safe_int(
                lookback_hours_override,
                _safe_int(controls.get("retirement_gate_lookback_hours"), 72),
            ),
            24 * 30,
        ),
    )
    max_events = max(0, _safe_int(controls.get("retirement_gate_max_events"), 20))
    max_active_users = max(0, _safe_int(controls.get("retirement_gate_max_active_users"), 10))

    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(hours=lookback_hours)).isoformat()
    query = _legacy_family_telemetry_query(route_family, since_iso)

    rows = (
        await db.hiring_v2_deprecation_telemetry
        .find(query, {"_id": 0, "user_id": 1, "operation": 1, "legacy_path": 1, "created_at": 1})
        .sort("created_at", -1)
        .limit(20000)
        .to_list(20000)
    )

    active_users = {str(row.get("user_id") or "") for row in rows if str(row.get("user_id") or "").strip()}
    by_operation: Dict[str, int] = {}
    for row in rows:
        operation = str(row.get("operation") or "unknown")
        by_operation[operation] = by_operation.get(operation, 0) + 1

    total_events = len(rows)
    active_user_count = len(active_users)
    gate_met = total_events <= max_events and active_user_count <= max_active_users

    events_score = 100.0 if max_events == 0 and total_events == 0 else max(0.0, min(100.0, (max_events / max(total_events, 1)) * 100))
    users_score = 100.0 if max_active_users == 0 and active_user_count == 0 else max(0.0, min(100.0, (max_active_users / max(active_user_count, 1)) * 100))
    readiness_score = 100.0 if gate_met else round((events_score + users_score) / 2, 2)

    return {
        "route_family": str(route_family),
        "lookback_hours": lookback_hours,
        "since": since_iso,
        "total_events": total_events,
        "active_users": active_user_count,
        "gate_thresholds": {
            "max_events": max_events,
            "max_active_users": max_active_users,
        },
        "gate_met": gate_met,
        "readiness_score": readiness_score,
        "top_operations": sorted(
            [{"operation": key, "count": value} for key, value in by_operation.items()],
            key=lambda item: item["count"],
            reverse=True,
        )[:10],
    }


async def _load_f26_rollout_controls() -> Dict[str, Any]:
    existing = await db.hiring_v2_rollout_controls.find_one(
        {"key": "feature26_legacy_write_rollout"},
        {"_id": 0},
    )
    controls = {**DEFAULT_F26_ROLLOUT_CONTROLS, **(existing or {})}
    return controls


# ── Models ──
# Canonical schemas moved to `/app/backend/models/jobs.py` (Phase 2 model
# migration). Re-imported here to keep the existing API surface unchanged.
from models.jobs import JobApplication, JobPost, ResumeProfile  # noqa: F401


# ── Helpers ──

_ai_call = ai_call
_normalize_pipeline_status = normalize_pipeline_status
_append_application_timeline_event = append_application_timeline_event
_safe_days_since = safe_days_since
_stage_target_days = stage_target_days
_build_sla_auto_trigger_items = build_sla_auto_trigger_items
_execute_sla_auto_trigger_item = execute_sla_auto_trigger_item
_compute_candidate_match = compute_candidate_match
_build_copilot_actions = build_copilot_actions
_get_owned_application_for_employer = get_owned_application_for_employer
_send_candidate_followup_email = send_candidate_followup_email
_normalize_recommendation = normalize_recommendation
_clamp_score_1_5 = clamp_score_1_5
_build_sequence_steps = build_sequence_steps
_send_candidate_notification_with_optional_email = send_candidate_notification_with_optional_email


# ── Job CRUD (Employer) ──


@router.post("/post")
async def post_job(job: JobPost, request: Request):
    """Employer: Post a new job listing."""
    user = await require_auth(request)

    # Admin can post directly, others need employer approval
    emp = None
    if not getattr(user, "is_admin", False):
        emp = await db.employer_applications.find_one(
            {"user_id": user.user_id, "status": "approved"}, {"_id": 0, "employer_id": 1, "business_name": 1}
        )
        if not emp:
            raise HTTPException(status_code=403, detail="Approved employer access required")
    else:
        emp = {"employer_id": f"admin_{user.user_id}", "business_name": "Admin"}

    now_iso = datetime.now(timezone.utc).isoformat()
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    job_doc = {
        "job_id": job_id,
        "employer_id": emp["employer_id"],
        "poster_user_id": user.user_id,
        "company_name": job.company_name or emp.get("business_name", ""),
        "title": job.title,
        "description": job.description,
        "requirements": job.requirements,
        "location": job.location,
        "country": job.country,
        "job_type": job.job_type,
        "remote": job.remote,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "industry": job.industry,
        "skills": job.skills,
        "experience_years": job.experience_years,
        "visa_sponsorship": job.visa_sponsorship,
        "application_deadline": job.application_deadline,
        "status": "active",
        "views": 0,
        "applications_count": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    await db.jobs.insert_one(job_doc)
    job_doc.pop("_id", None)

    # Smart Alerts: notify matching employees
    notify_matching_task = asyncio.create_task(_notify_matching_employees(job_doc))
    notify_matching_task.add_done_callback(
        lambda t: logger.error("Task failed", exc_info=t.exception()) if t.exception() else None
    )

    return {"success": True, "job_id": job_id, "job": job_doc}


async def get_my_posted_jobs(request: Request):
    """Employer: Get jobs posted by the current user."""
    user = await require_employer(request)
    jobs = await db.jobs.find({"poster_user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"jobs": jobs, "total": len(jobs)}


@router.put("/update/{job_id}")
async def update_job(job_id: str, job: JobPost, request: Request):
    """Employer: Update a job listing."""
    user = await require_employer(request)
    existing = await db.jobs.find_one({"job_id": job_id, "poster_user_id": user.user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    update = {k: v for k, v in job.dict().items() if v is not None}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.jobs.update_one({"job_id": job_id}, {"$set": update})
    return {"success": True}


@router.delete("/delete/{job_id}")
async def delete_job(job_id: str, request: Request):
    """Employer: Delete/close a job listing."""
    user = await require_employer(request)
    result = await db.jobs.update_one(
        {"job_id": job_id, "poster_user_id": user.user_id},
        {"$set": {"status": "closed", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True}


# ── Job Search & Discovery (Employee) ──


async def search_jobs(
    request: Request,
    q: str = "",
    location: str = "",
    country: str = "",
    job_type: str = "",
    remote: str = "",
    industry: str = "",
    salary_min: float = 0,
    visa: str = "",
    page: int = 1,
    limit: int = 20,
):
    return await search_jobs_read(
        q=q,
        location=location,
        country=country,
        job_type=job_type,
        remote=remote,
        industry=industry,
        salary_min=salary_min,
        visa=visa,
        page=page,
        limit=limit,
    )


async def get_job_detail(job_id: str):
    """Get full job details."""
    job = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.jobs.update_one({"job_id": job_id}, {"$inc": {"views": 1}})
    return {"job": job}


async def get_job_recommendations(request: Request):
    user = await require_auth(request)
    return await get_job_recommendations_read(user_id=user.user_id)


# ── Job Applications ──


@router.post("/apply")
async def apply_for_job(application: JobApplication, request: Request):
    """Employee: Apply for a job."""
    auth_ctx = await require_hiring_plan(request, min_plan="free")
    user = auth_ctx["user"]

    job = await db.jobs.find_one({"job_id": application.job_id, "status": "active"}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or no longer active")

    existing = await db.job_applications.find_one({"user_id": user.user_id, "job_id": application.job_id})
    if existing:
        raise HTTPException(status_code=400, detail="You have already applied for this job")

    now_iso = datetime.now(timezone.utc).isoformat()
    app_id = f"japp_{uuid.uuid4().hex[:12]}"

    app_doc = {
        "application_id": app_id,
        "user_id": user.user_id,
        "candidate_id": user.user_id,
        "candidate_name": user.name,
        "candidate_email": user.email,
        "employer_user_id": job.get("poster_user_id", ""),
        "job_id": application.job_id,
        "job_title": job.get("title", ""),
        "company_name": job.get("company_name", ""),
        "cover_letter": application.cover_letter,
        "status": "applied",  # applied, viewed, interview, offer, rejected
        "applied_at": now_iso,
        "updated_at": now_iso,
    }

    await db.job_applications.insert_one(app_doc)
    await db.jobs.update_one({"job_id": application.job_id}, {"$inc": {"applications_count": 1}})

    await record_hiring_workflow_event(
        request=request,
        event_type="candidate_application_submitted",
        user_id=user.user_id,
        metadata={
            "application_id": app_id,
            "job_id": application.job_id,
            "effective_plan": auth_ctx.get("effective_plan"),
        },
    )

    try:
        await _append_application_timeline_event(
            application_id=app_id,
            job_id=application.job_id,
            actor_user_id=user.user_id,
            event_type="application_submitted",
            title="Application Submitted",
            description=f"{user.name or 'Candidate'} submitted an application.",
            status="applied",
        )
    except Exception as e:
        logger.warning(f"application timeline event failed: {e}")

    await db.notifications.insert_one(
        {
            "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "type": "job_application_submitted",
            "title": "Application Submitted",
            "body": f"Your application for '{job.get('title', '')}' has been submitted successfully.",
            "read": False,
            "created_at": now_iso,
        }
    )

    employer_user_id = job.get("poster_user_id")
    if employer_user_id:
        await db.notifications.insert_one(
            {
                "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                "user_id": employer_user_id,
                "type": "job_new_application",
                "title": "New Job Application",
                "body": f"{user.name or 'A candidate'} applied for '{job.get('title', '')}'.",
                "read": False,
                "created_at": now_iso,
            }
        )

    try:
        from utils.email_service import send_catalog_template

        await send_catalog_template(
            user.email,
            "career_status_received",
            user.name,
            applicant_name=user.name,
            role_title=job.get("title") or "Selected Role",
            application_id=app_id,
        )

        if employer_user_id:
            employer_user = await db.users.find_one(
                {"user_id": employer_user_id},
                {"_id": 0, "email": 1, "name": 1},
            )
            if employer_user and employer_user.get("email"):
                await send_catalog_template(
                    employer_user.get("email"),
                    "career_admin_notify",
                    employer_user.get("name") or "Employer",
                    applicant_name=user.name,
                    position=job.get("title") or "Selected Role",
                    application_id=app_id,
                )
    except Exception as e:
        logger.warning(f"jobs/apply email notification failed: {e}")

    # Auto-create ARIS hiring pipeline
    auto_pipeline_task = asyncio.create_task(_auto_create_pipeline(app_id, user, job))
    auto_pipeline_task.add_done_callback(
        lambda t: logger.error("Task failed", exc_info=t.exception()) if t.exception() else None
    )

    app_doc.pop("_id", None)
    return {"success": True, "application_id": app_id, "application": app_doc}


async def get_my_applications(request: Request, status: str = "all"):
    user = await require_auth(request)
    return await get_my_applications_read(user_id=user.user_id, status=status)


async def get_saved_jobs(request: Request):
    user = await require_auth(request)
    return await get_saved_jobs_read(user_id=user.user_id)


@router.post("/save/{job_id}")
async def save_job(job_id: str, request: Request):
    """Employee: Save/bookmark a job."""
    user = await require_auth(request)
    existing = await db.saved_jobs.find_one({"user_id": user.user_id, "job_id": job_id})
    if existing:
        await db.saved_jobs.delete_one({"user_id": user.user_id, "job_id": job_id})
        return {"saved": False}
    await db.saved_jobs.insert_one(
        {
            "user_id": user.user_id,
            "job_id": job_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"saved": True}


# ── Resume / Profile ──


@router.post("/profile/update")
async def update_employee_profile(profile: ResumeProfile, request: Request):
    """Update employee job profile/preferences."""
    user = await require_auth(request)
    now_iso = datetime.now(timezone.utc).isoformat()

    await db.employee_profiles.update_one(
        {"user_id": user.user_id},
        {"$set": {**profile.dict(), "updated_at": now_iso}},
        upsert=True,
    )
    return {"success": True}


async def get_employee_profile(request: Request):
    user = await require_auth(request)
    return await get_employee_profile_read(user_id=user.user_id)


@router.post("/resume/upload")
async def upload_resume(request: Request, file: UploadFile = File(...)):
    """Upload resume for AI parsing and scoring."""
    user = await require_auth(request)

    allowed = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Allowed formats: PDF, DOC, DOCX, TXT")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Max file size: 5MB")

    upload_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "resumes", user.user_id
    )
    os.makedirs(upload_dir, exist_ok=True)

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "pdf"
    filename = f"resume_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(upload_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    # Extract text for AI analysis (for TXT files)
    resume_text = ""
    if file.content_type == "text/plain":
        resume_text = content.decode("utf-8", errors="ignore")[:3000]

    now_iso = datetime.now(timezone.utc).isoformat()
    resume_doc = {
        "user_id": user.user_id,
        "filename": filename,
        "file_size": len(content),
        "content_type": file.content_type,
        "uploaded_at": now_iso,
        "ai_analysis": None,
    }

    # AI resume analysis
    if resume_text and EMERGENT_KEY:
        try:
            ai_response = await _ai_call(
                'You are a resume analyst. Extract skills, experience level, and provide a quality score. Return JSON: {"skills":[],"experience_years":0,"education":"...","score":0,"improvements":[],"strengths":[]}',
                f"Resume text:\n{resume_text}",
            )
            analysis = json.loads(ai_response)
            resume_doc["ai_analysis"] = analysis

            # Auto-update profile with extracted data
            if analysis.get("skills"):
                await db.employee_profiles.update_one(
                    {"user_id": user.user_id},
                    {
                        "$set": {
                            "skills": analysis["skills"],
                            "experience_years": analysis.get("experience_years"),
                            "education": analysis.get("education"),
                            "resume_score": analysis.get("score", 0),
                            "updated_at": now_iso,
                        }
                    },
                    upsert=True,
                )
        except Exception as e:
            logger.warning(f"Resume AI analysis failed: {e}")

    await db.resumes.update_one({"user_id": user.user_id}, {"$set": resume_doc}, upsert=True)
    resume_doc.pop("_id", None)
    return {"success": True, "resume": resume_doc}


async def get_resume_score(request: Request):
    user = await require_auth(request)
    return await get_resume_score_read(user_id=user.user_id)


# ── Employee Analytics ──


async def employee_analytics(request: Request):
    user = await require_auth(request)
    return await employee_analytics_read(user_id=user.user_id)


async def get_jobs_portal_summary(request: Request):
    user = await require_auth(request)
    return await get_jobs_portal_summary_read(user_id=user.user_id)


# ── Employer: View Applicants ──


async def get_job_applicants(job_id: str, request: Request):
    """Employer: View applicants for a posted job."""
    user = await require_employer(request)
    job = await db.jobs.find_one({"job_id": job_id, "poster_user_id": user.user_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    apps = await db.job_applications.find({"job_id": job_id}, {"_id": 0}).sort("applied_at", -1).to_list(200)

    # Enrich with user info
    for a in apps:
        user_doc = await db.users.find_one({"user_id": a["user_id"]}, {"_id": 0, "name": 1, "email": 1})
        profile = await db.employee_profiles.find_one(
            {"user_id": a["user_id"]}, {"_id": 0, "skills": 1, "resume_score": 1}
        )
        a["applicant_name"] = user_doc.get("name", "Unknown") if user_doc else "Unknown"
        a["applicant_email"] = user_doc.get("email", "") if user_doc else ""
        a["skills"] = profile.get("skills", []) if profile else []
        a["resume_score"] = profile.get("resume_score", 0) if profile else 0

    return {"applicants": apps, "total": len(apps), "job": {"title": job["title"], "job_id": job_id}}


async def get_employer_pipeline_board(request: Request, limit: int = 300):
    user = await require_employer(request)
    return await get_employer_pipeline_board_read(user=user, limit=limit)


async def get_employer_pipeline_timeline(application_id: str, request: Request, limit: int = 150):
    user = await require_employer(request)
    return await get_employer_pipeline_timeline_read(user=user, application_id=application_id, limit=limit)


@router.post("/employer/interview-kit/{application_id}/generate")
async def generate_interview_kit(application_id: str, request: Request):
    """Generate interview kit (questions + panel brief) for selected candidate."""
    user = await require_employer(request)
    owned = await _get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]

    candidate_name = app.get("candidate_name") or "Candidate"
    role_title = job.get("title") or "Role"
    skills = app.get("skills") or job.get("skills") or []

    default_questions = {
        "technical_questions": [
            f"Walk us through a project where you applied {skills[0] if skills else 'core engineering skills'} to solve a difficult problem.",
            "How do you design APIs for reliability and observability under production load?",
            "Describe your strategy for debugging intermittent integration failures.",
        ],
        "behavioral_questions": [
            "Tell us about a time you resolved a conflict with a stakeholder while keeping delivery on track.",
            "How do you prioritize when multiple urgent tasks arrive simultaneously?",
            "Share an example where you mentored a teammate through a complex technical issue.",
        ],
        "focus_areas": ["System design", "Execution quality", "Ownership", "Communication"],
        "panel_brief": (
            f"Interview focus for {candidate_name} applying to {role_title}: validate role-critical skills,"
            " production incident handling, and collaboration maturity."
        ),
    }

    generated = default_questions
    try:
        ai_prompt = (
            "Create an interview kit as strict JSON with keys: technical_questions (3), behavioral_questions (3),"
            " focus_areas (max 4), panel_brief."
            f" Candidate={candidate_name}; Role={role_title}; Skills={skills}; CoverLetter={app.get('cover_letter') or ''}"
        )
        ai_text = await _ai_call(
            "You generate concise enterprise interview kits in valid JSON only.",
            ai_prompt,
            session_id=f"interview_kit_{application_id}",
        )
        match = re.search(r"\{.*\}", str(ai_text), re.S)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                generated = {
                    "technical_questions": parsed.get("technical_questions") or default_questions["technical_questions"],
                    "behavioral_questions": parsed.get("behavioral_questions") or default_questions["behavioral_questions"],
                    "focus_areas": parsed.get("focus_areas") or default_questions["focus_areas"],
                    "panel_brief": parsed.get("panel_brief") or default_questions["panel_brief"],
                }
    except Exception as e:
        logger.warning(f"interview kit AI generation fallback used: {e}")

    now_iso = datetime.now(timezone.utc).isoformat()
    kit_doc = {
        "kit_id": f"ikit_{uuid.uuid4().hex[:12]}",
        "application_id": application_id,
        "job_id": app.get("job_id"),
        "candidate_id": app.get("candidate_id") or app.get("user_id"),
        "candidate_name": candidate_name,
        "candidate_email": app.get("candidate_email") or "",
        "job_title": role_title,
        "generated_by": user.user_id,
        "technical_questions": generated.get("technical_questions", []),
        "behavioral_questions": generated.get("behavioral_questions", []),
        "focus_areas": generated.get("focus_areas", []),
        "panel_brief": generated.get("panel_brief", ""),
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.employer_interview_kits.update_one(
        {"application_id": application_id},
        {"$set": kit_doc},
        upsert=True,
    )

    await _append_application_timeline_event(
        application_id=application_id,
        job_id=app.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="interview_kit_generated",
        title="Interview Kit Generated",
        description="Recruiter generated an interview kit with suggested questions.",
        status=app.get("status"),
    )

    return {"success": True, "interview_kit": kit_doc}


@router.post("/employer/interview-kit/{application_id}/share")
async def share_interview_kit(application_id: str, payload: InterviewKitShareRequest, request: Request):
    """Share generated interview kit with panelists via email."""
    user = await require_employer(request)
    owned = await _get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]

    kit = await db.employer_interview_kits.find_one({"application_id": application_id}, {"_id": 0})
    if not kit:
        raise HTTPException(status_code=404, detail="Interview kit not found. Generate kit first.")

    panel_emails = sorted({str(email).strip().lower() for email in payload.panel_emails if str(email).strip()})
    if not panel_emails:
        raise HTTPException(status_code=400, detail="At least one panel email is required")

    from utils.email_service import send_catalog_template

    sent = 0
    failed = 0
    for panel_email in panel_emails:
        result = await send_catalog_template(
            panel_email,
            "user_notification_alert",
            panel_email.split("@")[0],
            alert_title=f"Interview Kit — {job.get('title') or 'Role'}",
            message=(
                f"Panel brief for {app.get('candidate_name') or 'Candidate'}: {kit.get('panel_brief') or ''}\n"
                f"Top focus areas: {', '.join(kit.get('focus_areas') or [])}\n"
                f"Recruiter note: {payload.note or 'Please review before the interview.'}"
            ),
            context_type="interview_kit",
            action_url="/job-platform",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        if result.get("success"):
            sent += 1
        else:
            failed += 1

    share_doc = {
        "share_id": f"ikshare_{uuid.uuid4().hex[:12]}",
        "application_id": application_id,
        "job_id": app.get("job_id"),
        "shared_by": user.user_id,
        "panel_emails": panel_emails,
        "note": payload.note or "",
        "sent_count": sent,
        "failed_count": failed,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.employer_interview_kit_shares.insert_one({**share_doc})

    await _append_application_timeline_event(
        application_id=application_id,
        job_id=app.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="interview_kit_shared",
        title="Interview Kit Shared",
        description=f"Interview kit shared with {sent} panelist(s).",
        status=app.get("status"),
        metadata={"panel_count": len(panel_emails), "sent": sent, "failed": failed},
    )

    return {"success": True, "sent_count": sent, "failed_count": failed, "share": {**share_doc}}


@router.post("/employer/offers/build")
async def build_offer_draft(payload: OfferDraftRequest, request: Request):
    """Create offer draft for an application with expiry and e-sign readiness."""
    user = await require_employer(request)
    owned = await _get_owned_application_for_employer(user, payload.application_id)
    app = owned["application"]
    job = owned["job"]

    now_iso = datetime.now(timezone.utc).isoformat()
    offer_id = f"offer_{uuid.uuid4().hex[:12]}"
    offer_doc = {
        "offer_id": offer_id,
        "application_id": payload.application_id,
        "job_id": app.get("job_id"),
        "candidate_id": app.get("candidate_id") or app.get("user_id"),
        "candidate_name": app.get("candidate_name") or "Candidate",
        "candidate_email": app.get("candidate_email") or "",
        "role_title": job.get("title") or "Role",
        "base_salary_usd": int(payload.base_salary_usd),
        "start_date": payload.start_date,
        "expires_at": payload.expires_at,
        "personal_message": payload.personal_message or "",
        "status": "draft",
        "approval_status": "not_submitted",
        "esign_token": None,
        "created_by": user.user_id,
        "approved_by": None,
        "approved_at": None,
        "sent_at": None,
        "signed_at": None,
        "decision": None,
        "decision_signer": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.employer_offer_letters.insert_one({**offer_doc})

    await _append_application_timeline_event(
        application_id=payload.application_id,
        job_id=app.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="offer_draft_created",
        title="Offer Draft Created",
        description=f"Offer draft created with ${int(payload.base_salary_usd):,} base salary.",
        status="offer",
        metadata={"offer_id": offer_id},
    )

    return {"success": True, "offer": {**offer_doc}}


@router.post("/employer/offers/{offer_id}/submit-approval")
async def submit_offer_for_approval(offer_id: str, payload: OfferApprovalRequest, request: Request):
    user = await require_employer(request)
    offer = await db.employer_offer_letters.find_one({"offer_id": offer_id}, {"_id": 0})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    offer_transition = validate_offer_transition(
        offer.get("status"),
        "pending_approval",
        approval_status=offer.get("approval_status"),
    )
    if not offer_transition.get("allowed"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Invalid offer lifecycle transition",
                "offer_id": offer_id,
                "current_status": normalize_offer_status(offer.get("status")),
                "target_status": "pending_approval",
                "reason": offer_transition.get("reason"),
            },
        )

    owned = await _get_owned_application_for_employer(user, offer.get("application_id") or "")
    app = owned["application"]

    await db.employer_offer_letters.update_one(
        {"offer_id": offer_id},
        {
            "$set": {
                "approval_status": "pending",
                "status": "pending_approval",
                "approval_note": payload.note or "",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    await _append_application_timeline_event(
        application_id=offer.get("application_id") or "",
        job_id=offer.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="offer_submitted_for_approval",
        title="Offer Submitted for Approval",
        description="Offer draft submitted into approval queue.",
        status=app.get("status"),
        metadata={"offer_id": offer_id},
    )
    return {"success": True, "offer_id": offer_id, "approval_status": "pending"}


@router.post("/employer/offers/{offer_id}/approve")
async def approve_offer(offer_id: str, payload: OfferApprovalRequest, request: Request):
    user = await require_employer(request)
    offer = await db.employer_offer_letters.find_one({"offer_id": offer_id}, {"_id": 0})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    offer_transition = validate_offer_transition(
        offer.get("status"),
        "approved",
        approval_status="approved",
    )
    if not offer_transition.get("allowed"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Invalid offer lifecycle transition",
                "offer_id": offer_id,
                "current_status": normalize_offer_status(offer.get("status")),
                "target_status": "approved",
                "reason": offer_transition.get("reason"),
            },
        )

    await _get_owned_application_for_employer(user, offer.get("application_id") or "")

    approver_name = payload.approver_name or user.name or "Approver"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.employer_offer_letters.update_one(
        {"offer_id": offer_id},
        {
            "$set": {
                "approval_status": "approved",
                "status": "approved",
                "approved_by": approver_name,
                "approved_by_user_id": user.user_id,
                "approved_note": payload.note or "",
                "approved_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )

    await _append_application_timeline_event(
        application_id=offer.get("application_id") or "",
        job_id=offer.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="offer_approved",
        title="Offer Approved",
        description=f"Offer approved by {approver_name}.",
        status="offer",
        metadata={"offer_id": offer_id},
    )
    return {"success": True, "offer_id": offer_id, "approval_status": "approved"}


@router.post("/employer/offers/{offer_id}/send")
async def send_offer_letter(offer_id: str, payload: OfferSendRequest, request: Request):
    user = await require_employer(request)
    offer = await db.employer_offer_letters.find_one({"offer_id": offer_id}, {"_id": 0})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    offer_transition = validate_offer_transition(
        offer.get("status"),
        "sent",
        approval_status=offer.get("approval_status"),
    )
    if not offer_transition.get("allowed"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Invalid offer lifecycle transition",
                "offer_id": offer_id,
                "current_status": normalize_offer_status(offer.get("status")),
                "target_status": "sent",
                "reason": offer_transition.get("reason"),
            },
        )

    await _get_owned_application_for_employer(user, offer.get("application_id") or "")

    if offer.get("approval_status") != "approved":
        raise HTTPException(status_code=409, detail="Offer must be approved before sending")

    token = f"esig_{uuid.uuid4().hex}"
    confirm_url = payload.confirmation_url or f"/job-platform?offer_token={token}"
    now_iso = datetime.now(timezone.utc).isoformat()

    from utils.email_service import send_catalog_template

    send_result = await send_catalog_template(
        offer.get("candidate_email") or "",
        "career_offer_sent",
        offer.get("candidate_name") or "Candidate",
        applicant_name=offer.get("candidate_name") or "Candidate",
        role_title=offer.get("role_title") or "Role",
        base_salary_usd=int(offer.get("base_salary_usd") or 0),
        start_date=offer.get("start_date") or "",
        expires_at=offer.get("expires_at") or "",
        confirm_url=confirm_url,
        personal_message=offer.get("personal_message") or "",
    )

    await db.employer_offer_letters.update_one(
        {"offer_id": offer_id},
        {
            "$set": {
                "status": "sent",
                "sent_at": now_iso,
                "updated_at": now_iso,
                "esign_token": token,
                "confirmation_url": confirm_url,
                "delivery_status": "sent" if send_result.get("success") else "failed",
            }
        },
    )

    await _append_application_timeline_event(
        application_id=offer.get("application_id") or "",
        job_id=offer.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="offer_sent",
        title="Offer Sent",
        description="Offer letter sent to candidate with e-sign link.",
        status="offer",
        metadata={"offer_id": offer_id, "delivery": send_result.get("success", False)},
    )
    return {"success": True, "offer_id": offer_id, "delivery": send_result}


@router.post("/offers/esign")
async def e_sign_offer(payload: OfferESignRequest):
    """Candidate e-sign endpoint for offer acceptance or decline."""
    decision = str(payload.decision or "").strip().lower()
    if decision not in {"accept", "decline"}:
        raise HTTPException(status_code=400, detail="decision must be accept or decline")

    offer = await db.employer_offer_letters.find_one({"esign_token": payload.offer_token}, {"_id": 0})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer token invalid")

    target_offer_status = "accepted" if decision == "accept" else "declined"
    offer_transition = validate_offer_transition(
        offer.get("status"),
        target_offer_status,
        approval_status=offer.get("approval_status"),
    )
    if not offer_transition.get("allowed"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Invalid offer lifecycle transition",
                "offer_id": offer.get("offer_id"),
                "current_status": normalize_offer_status(offer.get("status")),
                "target_status": target_offer_status,
                "reason": offer_transition.get("reason"),
            },
        )

    expires_at = str(offer.get("expires_at") or "")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at)
            now_dt = datetime.now(timezone.utc)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if now_dt > exp_dt:
                await db.employer_offer_letters.update_one(
                    {"offer_id": offer.get("offer_id")},
                    {"$set": {"status": "expired", "updated_at": now_dt.isoformat()}},
                )
                raise HTTPException(status_code=410, detail="Offer has expired")
        except HTTPException:
            raise
        except Exception:
            pass

    now_iso = datetime.now(timezone.utc).isoformat()
    new_status = "accepted" if decision == "accept" else "declined"
    await db.employer_offer_letters.update_one(
        {"offer_id": offer.get("offer_id")},
        {
            "$set": {
                "status": new_status,
                "decision": decision,
                "decision_signer": payload.signer_name,
                "signed_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )

    app_id = offer.get("application_id") or ""
    if app_id:
        if decision == "accept":
            await db.job_applications.update_one(
                {"application_id": app_id},
                {"$set": {"status": "hired", "updated_at": now_iso}},
            )

        await _append_application_timeline_event(
            application_id=app_id,
            job_id=offer.get("job_id") or "",
            actor_user_id=offer.get("candidate_id") or "candidate",
            event_type="offer_esign_completed",
            title="Offer Decision Recorded",
            description=f"Candidate {decision}ed the offer via e-sign.",
            status="hired" if decision == "accept" else "offer",
            metadata={"offer_id": offer.get("offer_id"), "decision": decision, "signer": payload.signer_name},
        )

    return {
        "success": True,
        "offer_id": offer.get("offer_id"),
        "decision": decision,
        "signed_at": now_iso,
    }


async def list_employer_offers(request: Request, application_id: Optional[str] = None, limit: int = 120):
    user = await require_employer(request)
    return await list_employer_offers_read(user=user, application_id=application_id, limit=limit)


async def get_employer_sla_alerts(request: Request, limit: int = 120):
    user = await require_employer(request)
    return await get_employer_sla_alerts_read(user=user, limit=limit)


async def get_employer_sla_auto_triggers(request: Request, application_id: Optional[str] = None, limit: int = 12):
    user = await require_employer(request)
    return await get_employer_sla_auto_triggers_read(user=user, application_id=application_id, limit=limit)


@router.post("/employer/sla-auto-triggers/run")
async def run_employer_sla_auto_triggers(payload: SlaAutoTriggerRunRequest, request: Request):
    user = await require_employer(request)
    items = await _build_sla_auto_trigger_items(
        user,
        application_id=payload.application_id,
        limit=max(1, min(int(payload.max_items or 12), 20)),
    )
    pending_items = [row for row in items if row.get("status") == "pending"]
    if payload.application_id and not pending_items:
        raise HTTPException(status_code=404, detail="No pending SLA auto-trigger found for application")

    executed: List[Dict[str, Any]] = []
    for item in pending_items:
        executed.append(await _execute_sla_auto_trigger_item(user, item))

    if executed:
        await broadcast_employer_pipeline_event(
            user.user_id,
            {
                "event_type": "sla_auto_trigger_executed",
                "actor_user_id": user.user_id,
                "actor_name": user.name or "Recruiter",
                "application_ids": [row.get("application_id") for row in executed if row.get("application_id")],
                "message": f"{len(executed)} SLA auto-trigger(s) executed.",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return {
        "success": True,
        "executed_count": len(executed),
        "executed": executed,
    }


async def get_employer_kpi_header(request: Request, window_days: int = 30):
    user = await require_employer(request)
    return await get_employer_kpi_header_read(user=user, window_days=window_days)


async def get_recruiter_copilot_suggestions(application_id: str, request: Request):
    user = await require_employer(request)
    return await get_recruiter_copilot_suggestions_read(user=user, application_id=application_id)


@router.post("/employer/copilot/{application_id}/execute")
async def execute_recruiter_copilot_action(application_id: str, payload: CopilotExecuteRequest, request: Request):
    user = await require_employer(request)
    owned = await _get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]
    action_key = str(payload.action_key or "").strip().lower()

    status_map = {
        "move_viewed": "viewed",
        "move_interview": "interview",
        "move_offer": "offer",
        "move_hired": "hired",
        "reject_candidate": "rejected",
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    result: Dict[str, Any] = {"action_key": action_key, "application_id": application_id}

    if action_key in status_map:
        new_status = status_map[action_key]
        await db.job_applications.update_one(
            {"application_id": application_id},
            {"$set": {"status": new_status, "updated_at": now_iso}},
        )

        status_labels = {
            "viewed": "Application Viewed",
            "interview": "Interview Invitation",
            "offer": "Job Offer",
            "hired": "Hiring Confirmed",
            "rejected": "Application Update",
        }
        await db.notifications.insert_one(
            {
                "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                "user_id": app.get("user_id"),
                "type": f"job_{new_status}",
                "title": status_labels.get(new_status, "Application Update"),
                "body": f"Your application for '{job.get('title', '')}' has been updated to: {new_status}",
                "read": False,
                "created_at": now_iso,
            }
        )

        candidate_email = app.get("candidate_email")
        if candidate_email:
            try:
                from utils.email_service import send_catalog_template

                template_map = {
                    "viewed": "career_status_under_review",
                    "interview": "career_status_interview",
                    "offer": "career_status_offer",
                    "hired": "career_status_update",
                    "rejected": "career_status_rejected",
                }
                template_key = template_map.get(new_status)
                if template_key:
                    candidate_name = app.get("candidate_name") or "Candidate"
                    role_title = job.get("title") or "Selected Role"
                    kwargs = {
                        "applicant_name": candidate_name,
                        "role_title": role_title,
                        "application_id": application_id,
                    }
                    if new_status == "hired":
                        kwargs = {
                            "applicant_name": candidate_name,
                            "position": role_title,
                            "application_id": application_id,
                            "status": "hired",
                            "status_label": "Hired",
                        }
                    await send_catalog_template(
                        candidate_email,
                        template_key,
                        candidate_name,
                        **kwargs,
                    )
            except Exception as e:
                logger.warning(f"copilot status email notification failed: {e}")

        await _append_application_timeline_event(
            application_id=application_id,
            job_id=job.get("job_id") or "",
            actor_user_id=user.user_id,
            event_type="copilot_status_move",
            title="Copilot Action Executed",
            description=f"Recruiter copilot moved candidate to '{new_status}'.",
            status=new_status,
            metadata={"action_key": action_key, "note": payload.note or ""},
        )
        result["status"] = new_status
    elif action_key == "send_followup":
        candidate_email = app.get("candidate_email")
        if not candidate_email:
            raise HTTPException(status_code=400, detail="Candidate email unavailable for follow-up")
        await _send_candidate_followup_email(
            candidate_email=candidate_email,
            candidate_name=app.get("candidate_name") or "Candidate",
            employer_name=user.name or "Hiring Team",
            role_title=job.get("title") or "Role",
            note=payload.note or "Quick follow-up from recruiter copilot.",
        )
        await _append_application_timeline_event(
            application_id=application_id,
            job_id=job.get("job_id") or "",
            actor_user_id=user.user_id,
            event_type="copilot_followup_sent",
            title="Copilot Follow-up Sent",
            description=payload.note or "Recruiter follow-up sent to candidate.",
            status=app.get("status"),
            metadata={"action_key": action_key},
        )
        result["status"] = "followup_sent"
    else:
        raise HTTPException(status_code=400, detail="Unsupported copilot action")

    log_doc = {
        "log_id": f"copilot_{uuid.uuid4().hex[:12]}",
        "application_id": application_id,
        "job_id": job.get("job_id"),
        "actor_user_id": user.user_id,
        "action_key": action_key,
        "note": payload.note or "",
        "result": result,
        "created_at": now_iso,
    }
    await db.recruiter_copilot_action_logs.insert_one(log_doc)
    return {"success": True, "result": result, "log": {k: v for k, v in log_doc.items() if k != "_id"}}


@router.post("/employer/pipeline-board/bulk-action")
async def bulk_pipeline_action(payload: BulkPipelineActionRequest, request: Request):
    """Bulk candidate operations for high-volume hiring workflows."""
    user = await require_employer(request)
    action = str(payload.action or "").strip().lower()
    app_ids = list({str(a).strip() for a in (payload.application_ids or []) if str(a).strip()})
    if not app_ids:
        raise HTTPException(status_code=400, detail="application_ids required")
    if len(app_ids) > 120:
        raise HTTPException(status_code=400, detail="Maximum 120 applications per bulk action")
    if action not in {"move_stage", "reject", "send_followup"}:
        raise HTTPException(status_code=400, detail="Unsupported bulk action")

    jobs = await db.jobs.find({"poster_user_id": user.user_id}, {"_id": 0, "job_id": 1, "title": 1}).to_list(800)
    jobs_by_id = {j.get("job_id"): j for j in jobs if j.get("job_id")}
    job_ids = list(jobs_by_id.keys())

    apps = await db.job_applications.find(
        {
            "application_id": {"$in": app_ids},
            "job_id": {"$in": job_ids},
        },
        {"_id": 0},
    ).to_list(len(app_ids))
    if not apps:
        raise HTTPException(status_code=404, detail="No matching applications found for employer")

    target_status = None
    if action == "move_stage":
        target_status = _normalize_pipeline_status(payload.target_status or "")
        if target_status not in {"viewed", "interview", "offer", "hired", "rejected"}:
            raise HTTPException(status_code=400, detail="target_status required for move_stage")
    if action == "reject":
        target_status = "rejected"

    now_iso = datetime.now(timezone.utc).isoformat()
    results: List[Dict[str, Any]] = []
    success_count = 0

    for app in apps:
        app_id = app.get("application_id") or ""
        job_id = app.get("job_id") or ""
        job_title = jobs_by_id.get(job_id, {}).get("title") or "Selected Role"
        candidate_name = app.get("candidate_name") or "Candidate"
        candidate_email = app.get("candidate_email") or ""
        candidate_user_id = app.get("user_id") or app.get("candidate_id") or ""

        try:
            if action in {"move_stage", "reject"} and target_status:
                await db.job_applications.update_one(
                    {"application_id": app_id},
                    {"$set": {"status": target_status, "updated_at": now_iso}},
                )
                if candidate_user_id:
                    await _send_candidate_notification_with_optional_email(
                        user_id=candidate_user_id,
                        email=candidate_email,
                        title="Application Status Updated",
                        message=f"Your application for '{job_title}' moved to {target_status} stage.",
                        notif_type="job_status_update",
                        send_email=True,
                    )

                await _append_application_timeline_event(
                    application_id=app_id,
                    job_id=job_id,
                    actor_user_id=user.user_id,
                    event_type="bulk_status_update",
                    title="Bulk Status Update",
                    description=f"Moved to '{target_status}' via bulk action.",
                    status=target_status,
                    metadata={
                        "bulk_action": action,
                        "note": payload.note or "",
                    },
                )
                success_count += 1
                results.append({"application_id": app_id, "status": target_status, "success": True})
                continue

            if action == "send_followup":
                if not candidate_email:
                    results.append({"application_id": app_id, "success": False, "error": "candidate_email_missing"})
                    continue
                note = payload.note or "Quick recruiter follow-up from Employer Console bulk action."
                await _send_candidate_followup_email(
                    candidate_email=candidate_email,
                    candidate_name=candidate_name,
                    employer_name=user.name or "Hiring Team",
                    role_title=job_title,
                    note=note,
                )
                await _append_application_timeline_event(
                    application_id=app_id,
                    job_id=job_id,
                    actor_user_id=user.user_id,
                    event_type="bulk_followup_sent",
                    title="Bulk Follow-up Sent",
                    description=note,
                    status=app.get("status"),
                    metadata={"bulk_action": action},
                )
                success_count += 1
                results.append({"application_id": app_id, "status": "followup_sent", "success": True})
                continue

            results.append({"application_id": app_id, "success": False, "error": "unsupported_action"})
        except Exception as exc:
            logger.warning(f"bulk pipeline action failed for {app_id}: {exc}")
            results.append({"application_id": app_id, "success": False, "error": str(exc)[:160]})

    if success_count:
        await broadcast_employer_pipeline_event(
            user.user_id,
            {
                "event_type": "bulk_action_completed",
                "actor_user_id": user.user_id,
                "actor_name": user.name or "Recruiter",
                "application_ids": [row.get("application_id") for row in results if row.get("success")],
                "message": f"Bulk action '{action}' updated {success_count} candidate(s).",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )


    return {
        "success": True,
        "action": action,
        "target_status": target_status,
        "processed": len(apps),
        "success_count": success_count,
        "failed_count": max(0, len(apps) - success_count),
        "results": results,
    }


@router.post("/employer/scorecards/{application_id}")
async def submit_interview_scorecard(application_id: str, payload: InterviewScorecardSubmitRequest, request: Request):
    """Structured interviewer scorecard + panel debrief capture."""
    user = await require_employer(request)
    owned = await _get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]

    interview_id = payload.interview_id
    if not interview_id:
        latest_interview = await db.interview_bookings.find_one(
            {"application_id": application_id},
            {"_id": 0, "interview_id": 1},
            sort=[("scheduled_start", -1)],
        )
        interview_id = (latest_interview or {}).get("interview_id")

    technical = _clamp_score_1_5(payload.technical_score)
    communication = _clamp_score_1_5(payload.communication_score)
    problem_solving = _clamp_score_1_5(payload.problem_solving_score)
    culture_fit = _clamp_score_1_5(payload.culture_fit_score)
    overall = round((technical + communication + problem_solving + culture_fit) / 4.0, 2)
    recommendation = _normalize_recommendation(payload.recommendation)

    now_iso = datetime.now(timezone.utc).isoformat()
    scorecard_doc = {
        "scorecard_id": f"iscore_{uuid.uuid4().hex[:12]}",
        "application_id": application_id,
        "job_id": job.get("job_id"),
        "interview_id": interview_id,
        "candidate_id": app.get("candidate_id") or app.get("user_id"),
        "candidate_name": app.get("candidate_name") or "Candidate",
        "reviewer_user_id": user.user_id,
        "reviewer_name": user.name,
        "technical_score": technical,
        "communication_score": communication,
        "problem_solving_score": problem_solving,
        "culture_fit_score": culture_fit,
        "overall_score": overall,
        "strengths": (payload.strengths or [])[:8],
        "concerns": (payload.concerns or [])[:8],
        "recommendation": recommendation,
        "debrief_summary": payload.debrief_summary or "",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.interview_scorecards.insert_one({**scorecard_doc})

    all_scorecards = await db.interview_scorecards.find(
        {"application_id": application_id},
        {"_id": 0, "overall_score": 1, "recommendation": 1, "reviewer_name": 1, "created_at": 1, "debrief_summary": 1},
    ).sort("created_at", -1).to_list(100)

    recommendation_counts = {
        "strong_hire": 0,
        "hire": 0,
        "lean_hire": 0,
        "no_hire": 0,
    }
    overall_scores: List[float] = []
    for row in all_scorecards:
        rec = _normalize_recommendation(row.get("recommendation"))
        recommendation_counts[rec] = recommendation_counts.get(rec, 0) + 1
        try:
            overall_scores.append(float(row.get("overall_score") or 0))
        except Exception:
            pass

    avg_overall = round(sum(overall_scores) / max(len(overall_scores), 1), 2)
    majority_recommendation = max(recommendation_counts.items(), key=lambda item: item[1])[0] if all_scorecards else "lean_hire"
    panel_debrief = {
        "debrief_id": f"debrief_{uuid.uuid4().hex[:12]}",
        "application_id": application_id,
        "job_id": job.get("job_id"),
        "candidate_name": app.get("candidate_name") or "Candidate",
        "scorecards_count": len(all_scorecards),
        "average_overall_score": avg_overall,
        "recommendation_counts": recommendation_counts,
        "majority_recommendation": majority_recommendation,
        "summary": payload.debrief_summary
        or f"Panel consensus is {majority_recommendation.replace('_', ' ')} with average score {avg_overall}/5.",
        "updated_at": now_iso,
    }
    await db.interview_panel_debriefs.update_one(
        {"application_id": application_id},
        {"$set": panel_debrief},
        upsert=True,
    )

    await _append_application_timeline_event(
        application_id=application_id,
        job_id=job.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="interview_scorecard_submitted",
        title="Interview Scorecard Submitted",
        description=f"Structured panel scorecard submitted ({overall}/5 · {recommendation.replace('_', ' ')}).",
        status=app.get("status"),
        metadata={
            "scorecard_id": scorecard_doc["scorecard_id"],
            "interview_id": interview_id,
        },
    )

    return {
        "success": True,
        "scorecard": scorecard_doc,
        "panel_debrief": panel_debrief,
    }


async def get_interview_scorecards(application_id: str, request: Request):
    user = await require_employer(request)
    return await get_interview_scorecards_read(user=user, application_id=application_id)


async def suggest_auto_scheduler_slots(application_id: str, request: Request, days_ahead: int = 7, duration_minutes: int = 45):
    user = await require_employer(request)
    return await suggest_auto_scheduler_slots_read(
        user=user,
        application_id=application_id,
        days_ahead=days_ahead,
        duration_minutes=duration_minutes,
    )


@router.post("/employer/auto-scheduler/{application_id}/book")
async def book_auto_scheduler_slot(application_id: str, request: Request):
    """One-click schedule using suggested slot while preserving interview workflow integrations."""
    user = await require_employer(request)
    owned = await _get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]
    body = await request.json()

    start = str(body.get("start") or "").strip()
    interview_type = str(body.get("interview_type") or "video").strip().lower() or "video"
    timezone_name = str(body.get("timezone") or "UTC").strip() or "UTC"
    notes = str(body.get("notes") or "Scheduled via Auto-Scheduler Orchestrator").strip()
    duration_minutes = int(body.get("duration_minutes") or 45)
    if not start:
        raise HTTPException(status_code=400, detail="start is required")

    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid slot start datetime")

    from .interview_management import ScheduleInterview, schedule_interview

    payload = ScheduleInterview(
        application_id=application_id,
        candidate_id=app.get("candidate_id") or app.get("user_id"),
        job_id=job.get("job_id") or "",
        interview_type=interview_type,
        scheduled_date=start_dt.date().isoformat(),
        scheduled_time=start_dt.strftime("%H:%M"),
        timezone=timezone_name,
        duration_minutes=max(20, min(duration_minutes, 120)),
        notes=notes,
    )
    schedule_result = await schedule_interview(payload, request)

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.job_applications.update_one(
        {"application_id": application_id},
        {"$set": {"status": "interview", "updated_at": now_iso}},
    )
    await _append_application_timeline_event(
        application_id=application_id,
        job_id=job.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="auto_scheduler_booked",
        title="Auto-Scheduler Booking Confirmed",
        description=f"Interview booked from orchestrator slot at {start_dt.isoformat()}.",
        status="interview",
        metadata={"source": "auto_scheduler_orchestrator"},
    )

    return {
        "success": True,
        "application_id": application_id,
        "scheduled_start": start_dt.isoformat(),
        "schedule_result": schedule_result,
    }


@router.post("/employer/communication-sequences/{application_id}/start")
async def start_communication_sequence(application_id: str, payload: CommunicationSequenceStartRequest, request: Request):
    """Start stage-aware communication drip for a candidate (email + in-app by default)."""
    user = await require_employer(request)
    owned = await _get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]

    candidate_user_id = app.get("user_id") or app.get("candidate_id")
    candidate_email = app.get("candidate_email") or ""
    if not candidate_user_id:
        raise HTTPException(status_code=400, detail="Candidate unavailable for communication sequence")

    steps = _build_sequence_steps(app, job, user.name or "Hiring Team")
    now_iso = datetime.now(timezone.utc).isoformat()
    channel = str(payload.channel or "email_inapp").strip().lower()
    if channel not in {"email_inapp", "inapp"}:
        channel = "email_inapp"

    first_step = steps[0]
    opening = (payload.custom_opening or "").strip()
    first_message = f"{opening}\n\n{first_step['message']}" if opening else first_step["message"]
    await _send_candidate_notification_with_optional_email(
        user_id=candidate_user_id,
        email=candidate_email,
        title=first_step["title"],
        message=first_message,
        notif_type="recruiter_sequence",
        send_email=channel == "email_inapp",
    )

    sequence_doc = {
        "sequence_id": f"cseq_{uuid.uuid4().hex[:12]}",
        "application_id": application_id,
        "job_id": job.get("job_id"),
        "candidate_id": candidate_user_id,
        "candidate_name": app.get("candidate_name") or "Candidate",
        "candidate_email": candidate_email,
        "employer_user_id": user.user_id,
        "channel": channel,
        "track": payload.track or "stage_progression",
        "status": "active",
        "steps": steps,
        "current_step_index": 0,
        "history": [
            {
                "step_index": 0,
                "step_key": first_step["key"],
                "title": first_step["title"],
                "message": first_message,
                "sent_at": now_iso,
            }
        ],
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.employer_candidate_communication_sequences.update_one(
        {"application_id": application_id, "employer_user_id": user.user_id},
        {"$set": sequence_doc},
        upsert=True,
    )

    await _append_application_timeline_event(
        application_id=application_id,
        job_id=job.get("job_id") or "",
        actor_user_id=user.user_id,
        event_type="communication_sequence_started",
        title="Communication Sequence Started",
        description="Smart recruiter communication sequence was started.",
        status=app.get("status"),
        metadata={"channel": channel, "track": payload.track or "stage_progression"},
    )

    return {"success": True, "sequence": sequence_doc}


@router.post("/employer/communication-sequences/{application_id}/advance")
async def advance_communication_sequence(application_id: str, payload: CommunicationSequenceAdvanceRequest, request: Request):
    user = await require_employer(request)
    seq = await db.employer_candidate_communication_sequences.find_one(
        {"application_id": application_id, "employer_user_id": user.user_id},
        {"_id": 0},
    )
    if not seq:
        raise HTTPException(status_code=404, detail="Communication sequence not found")
    if seq.get("status") != "active":
        raise HTTPException(status_code=400, detail="Communication sequence is not active")

    steps = seq.get("steps") or []
    current_idx = int(seq.get("current_step_index") or 0)
    next_idx = current_idx + 1
    if next_idx >= len(steps):
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.employer_candidate_communication_sequences.update_one(
            {"sequence_id": seq.get("sequence_id")},
            {"$set": {"status": "completed", "updated_at": now_iso}},
        )
        return {"success": True, "status": "completed", "message": "All sequence steps already sent"}

    step = steps[next_idx]
    message = payload.note or step.get("message") or "Recruiter follow-up"
    await _send_candidate_notification_with_optional_email(
        user_id=seq.get("candidate_id") or "",
        email=seq.get("candidate_email") or "",
        title=step.get("title") or "Recruiter Update",
        message=message,
        notif_type="recruiter_sequence",
        send_email=str(seq.get("channel") or "email_inapp") == "email_inapp",
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.employer_candidate_communication_sequences.update_one(
        {"sequence_id": seq.get("sequence_id")},
        {
            "$set": {
                "current_step_index": next_idx,
                "updated_at": now_iso,
            },
            "$push": {
                "history": {
                    "step_index": next_idx,
                    "step_key": step.get("key"),
                    "title": step.get("title"),
                    "message": message,
                    "sent_at": now_iso,
                }
            },
        },
    )

    return {
        "success": True,
        "status": "active",
        "current_step_index": next_idx,
        "next_step_index": next_idx + 1 if next_idx + 1 < len(steps) else None,
    }


async def get_communication_sequence(application_id: str, request: Request):
    user = await require_employer(request)
    return await get_communication_sequence_read(user=user, application_id=application_id)


async def get_employer_hiring_forecast(request: Request, window_days: int = 45):
    user = await require_employer(request)
    return await get_employer_hiring_forecast_read(user=user, window_days=window_days)


async def get_talent_rediscovery_candidates(request: Request, job_id: Optional[str] = None, limit: int = 20):
    user = await require_employer(request)
    return await get_talent_rediscovery_candidates_read(user=user, job_id=job_id, limit=limit)


@router.post("/employer/talent-rediscovery/{candidate_id}/reengage")
async def reengage_rediscovered_candidate(candidate_id: str, payload: RediscoveryReengageRequest, request: Request):
    user = await require_employer(request)
    candidate_user = await db.users.find_one(
        {"user_id": candidate_id},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1},
    )
    if not candidate_user:
        raise HTTPException(status_code=404, detail="Candidate not found")

    jobs = await db.jobs.find(
        {"poster_user_id": user.user_id},
        {"_id": 0, "job_id": 1, "title": 1},
    ).to_list(500)
    jobs_by_id = {j.get("job_id"): j for j in jobs if j.get("job_id")}
    selected_job_id = payload.job_id or (next(iter(jobs_by_id.keys())) if jobs_by_id else None)
    if not selected_job_id or selected_job_id not in jobs_by_id:
        raise HTTPException(status_code=400, detail="Valid job_id is required for re-engagement")

    role_title = jobs_by_id[selected_job_id].get("title") or "an open role"
    candidate_name = candidate_user.get("name") or "Candidate"
    body = payload.message or (
        f"Hi {candidate_name}, we'd love to reconnect with you for {role_title}. "
        "Your previous profile stood out and we'd like to fast-track a fresh discussion."
    )

    await _send_candidate_notification_with_optional_email(
        user_id=candidate_user.get("user_id") or "",
        email=candidate_user.get("email") or "",
        title=f"New Opportunity: {role_title}",
        message=body,
        notif_type="talent_rediscovery",
        send_email=True,
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    log_doc = {
        "action_id": f"redis_{uuid.uuid4().hex[:12]}",
        "candidate_id": candidate_id,
        "candidate_email": candidate_user.get("email") or "",
        "job_id": selected_job_id,
        "job_title": role_title,
        "employer_user_id": user.user_id,
        "message": body,
        "created_at": now_iso,
    }
    await db.talent_rediscovery_actions.insert_one({**log_doc})

    return {
        "success": True,
        "action": {k: v for k, v in log_doc.items() if k != "_id"},
    }


async def export_pipeline_audit_csv(
    application_id: str,
    request: Request,
    range_key: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    user = await require_employer(request)
    return await export_pipeline_audit_csv_read(
        user=user,
        application_id=application_id,
        range_key=range_key,
        start_date=start_date,
        end_date=end_date,
    )


async def export_pipeline_audit_pdf(
    application_id: str,
    request: Request,
    range_key: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    user = await require_employer(request)
    return await export_pipeline_audit_pdf_read(
        user=user,
        application_id=application_id,
        range_key=range_key,
        start_date=start_date,
        end_date=end_date,
    )


async def get_pipeline_audit_download_history(application_id: str, request: Request, limit: int = 8):
    user = await require_employer(request)
    return await get_pipeline_audit_download_history_read(user=user, application_id=application_id, limit=limit)


@router.post("/applicants/{job_id}/{application_id}/status")
async def update_application_status(job_id: str, application_id: str, request: Request):
    """Employer: Update applicant status."""
    user = await require_employer(request)
    body = await request.json()
    new_status = body.get("status", "")

    if new_status not in ["viewed", "interview", "offer", "hired", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    job = await db.jobs.find_one({"job_id": job_id, "poster_user_id": user.user_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    app_before = await db.job_applications.find_one({"application_id": application_id, "job_id": job_id}, {"_id": 0})
    if not app_before:
        raise HTTPException(status_code=404, detail="Application not found")

    transition = validate_application_transition(app_before.get("status"), new_status)
    if not transition.get("allowed"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Invalid application status transition",
                "current_status": app_before.get("status"),
                "target_status": new_status,
                "reason": transition.get("reason"),
            },
        )

    result = await db.job_applications.update_one(
        {"application_id": application_id, "job_id": job_id},
        {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Application not found")

    # Notify applicant
    app = await db.job_applications.find_one({"application_id": application_id}, {"_id": 0})
    if app:
        status_labels = {
            "viewed": "Application Viewed",
            "interview": "Interview Invitation",
            "offer": "Job Offer",
            "hired": "Hiring Confirmed",
            "rejected": "Application Update",
        }
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.notifications.insert_one(
            {
                "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                "user_id": app["user_id"],
                "type": f"job_{new_status}",
                "title": status_labels.get(new_status, "Application Update"),
                "body": f"Your application for '{job.get('title', '')}' has been updated to: {new_status}",
                "read": False,
                "created_at": now_iso,
            }
        )

        try:
            from utils.email_service import send_catalog_template

            template_map = {
                "viewed": "career_status_under_review",
                "interview": "career_status_interview",
                "offer": "career_status_offer",
                "hired": "career_status_update",
                "rejected": "career_status_rejected",
            }
            template_key = template_map.get(new_status)
            candidate_email = app.get("candidate_email")
            if template_key and candidate_email:
                candidate_name = app.get("candidate_name") or "Candidate"
                role_title = job.get("title") or "Selected Role"
                kwargs = {
                    "applicant_name": candidate_name,
                    "role_title": role_title,
                    "application_id": application_id,
                }
                if new_status == "hired":
                    kwargs = {
                        "applicant_name": candidate_name,
                        "position": role_title,
                        "application_id": application_id,
                        "status": "hired",
                        "status_label": "Hired",
                    }

                await send_catalog_template(
                    candidate_email,
                    template_key,
                    candidate_name,
                    **kwargs,
                )
        except Exception as e:
            logger.warning(f"jobs/status email notification failed: {e}")

        try:
            await _append_application_timeline_event(
                application_id=application_id,
                job_id=job_id,
                actor_user_id=user.user_id,
                event_type="status_updated",
                title=status_labels.get(new_status, "Status Updated"),
                description=f"Application moved to '{new_status}'.",
                status=new_status,
                metadata={"job_title": job.get("title", "")},
            )
        except Exception as e:
            logger.warning(f"status timeline event failed: {e}")

    await broadcast_employer_pipeline_event(
        user.user_id,
        {
            "event_type": "application_status_updated",
            "actor_user_id": user.user_id,
            "actor_name": user.name or "Recruiter",
            "application_id": application_id,
            "job_id": job_id,
            "status": new_status,
            "message": f"{user.name or 'Recruiter'} moved a candidate to {new_status}.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    await record_hiring_workflow_event(
        request=request,
        event_type="employer_application_status_updated",
        user_id=user.user_id,
        metadata={
            "application_id": application_id,
            "job_id": job_id,
            "from_status": app_before.get("status"),
            "to_status": new_status,
            "transition_reason": transition.get("reason"),
        },
    )

    return {"success": True}


async def _auto_create_pipeline(application_id: str, user, job: dict):
    """Background: auto-create ARIS hiring pipeline for new application."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        pipeline = {
            "pipeline_id": f"pipe_{uuid.uuid4().hex[:12]}",
            "application_id": application_id,
            "job_id": job.get("job_id", ""),
            "job_title": job.get("title", ""),
            "company_name": job.get("company_name", ""),
            "candidate_id": user.user_id,
            "candidate_name": user.name,
            "candidate_email": user.email,
            "employer_id": job.get("poster_user_id", ""),
            "current_stage": "application_received",
            "stage_history": [{"stage": "application_received", "timestamp": now, "auto": True}],
            "ai_scores": {},
            "prediction": None,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        await db.hiring_pipeline.insert_one(pipeline)
        logger.info(f"ARIS pipeline created: {pipeline['pipeline_id']} for application {application_id}")
    except Exception as e:
        logger.warning(f"ARIS auto-pipeline failed: {e}")


# ── Smart Alerts System ──


async def _notify_matching_employees(job_doc: dict):
    """Background task: find employees whose profile matches the new job and send alerts."""
    try:
        job_skills = set(s.lower() for s in (job_doc.get("skills") or []))
        job_industry = (job_doc.get("industry") or "").lower()
        job_location = (job_doc.get("location") or "").lower()
        job_type = (job_doc.get("job_type") or "").lower()
        job_remote = job_doc.get("remote", False)

        profiles = await db.employee_profiles.find({}, {"_id": 0}).to_list(500)
        now_iso = datetime.now(timezone.utc).isoformat()
        alerts_sent = 0

        for profile in profiles:
            user_id = profile.get("user_id")
            if not user_id or user_id == job_doc.get("poster_user_id"):
                continue

            # Check alert preferences
            prefs = profile.get("alert_preferences", {})
            if not prefs.get("enabled", True):
                continue

            # Calculate match score
            score = 0
            reasons = []

            # Skill match (most important)
            profile_skills = set(s.lower() for s in (profile.get("skills") or []))
            skill_overlap = job_skills & profile_skills
            if skill_overlap:
                score += 40 * (len(skill_overlap) / max(len(job_skills), 1))
                reasons.append(f"Skills: {', '.join(list(skill_overlap)[:3])}")

            # Industry match
            pref_industry = (profile.get("preferred_industry") or "").lower()
            if pref_industry and job_industry and pref_industry in job_industry:
                score += 20
                reasons.append("Industry match")

            # Location match
            pref_location = (profile.get("preferred_location") or "").lower()
            if pref_location and job_location and pref_location in job_location:
                score += 15
                reasons.append("Location match")

            # Job type match
            pref_type = (profile.get("preferred_job_type") or "").lower()
            if pref_type and job_type and pref_type == job_type:
                score += 15
                reasons.append("Job type match")

            # Remote preference
            if profile.get("remote_only") and job_remote:
                score += 10
                reasons.append("Remote available")

            min_threshold = prefs.get("min_match_score", 20)
            if score >= min_threshold:
                alert_doc = {
                    "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "type": "job_match",
                    "job_id": job_doc["job_id"],
                    "job_title": job_doc["title"],
                    "company_name": job_doc.get("company_name", ""),
                    "match_score": round(score),
                    "match_reasons": reasons,
                    "read": False,
                    "created_at": now_iso,
                }
                await db.smart_alerts.insert_one(alert_doc)
                alert_doc.pop("_id", None)
                alerts_sent += 1

        logger.info(f"Smart Alerts: sent {alerts_sent} alerts for job {job_doc['job_id']}")
    except Exception as e:
        logger.error(f"Smart Alerts error: {e}")


async def get_smart_alerts(request: Request, unread_only: bool = False, limit: int = 50):
    user = await require_auth(request)
    return await get_smart_alerts_read(user_id=user.user_id, unread_only=unread_only, limit=limit)


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str, request: Request):
    """Mark a smart alert as read."""
    user = await require_auth(request)
    result = await db.smart_alerts.update_one(
        {"alert_id": alert_id, "user_id": user.user_id},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": result.modified_count > 0}


@router.post("/alerts/read-all")
async def mark_all_alerts_read(request: Request):
    """Mark all smart alerts as read."""
    user = await require_auth(request)
    result = await db.smart_alerts.update_many(
        {"user_id": user.user_id, "read": False},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True, "marked": result.modified_count}


@router.post("/alerts/preferences")
async def update_alert_preferences(request: Request):
    user = await require_auth(request)
    body = await request.json()
    prefs = await build_alert_preferences_update(user_id=user.user_id, body=body)
    return {"success": True, "preferences": prefs}


async def get_alert_preferences(request: Request):
    user = await require_auth(request)
    return await get_alert_preferences_read(user_id=user.user_id)
