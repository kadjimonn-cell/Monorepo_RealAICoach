"""Feature 26 canonical Hiring v2 namespace scaffold.

This router provides a stable contract under /api/hiring/v2/* while delegating
to existing jobs portal internals during migration.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from .jobs import (
    apply_for_job,
    book_auto_scheduler_slot,
    generate_interview_kit,
    mark_alert_read,
    mark_all_alerts_read,
    reengage_rediscovered_candidate,
    save_job,
    share_interview_kit,
    start_communication_sequence,
    submit_interview_scorecard,
    update_application_status,
    update_alert_preferences,
    update_employee_profile,
    upload_resume,
    get_job_recommendations,
    approve_offer,
    build_offer_draft,
    execute_recruiter_copilot_action,
    bulk_pipeline_action,
    send_offer_letter,
    submit_offer_for_approval,
    get_employer_kpi_header,
    get_employer_pipeline_board,
    get_employer_sla_alerts,
    run_employer_sla_auto_triggers,
    employee_analytics,
    get_jobs_portal_summary,
    get_my_applications,
    list_employer_offers,
    get_saved_jobs,
    search_jobs,
    get_my_posted_jobs,
    get_job_detail,
    get_employee_profile,
    get_resume_score,
    get_smart_alerts,
    get_alert_preferences,
    get_job_applicants,
    get_employer_pipeline_timeline,
    get_employer_sla_auto_triggers,
    get_recruiter_copilot_suggestions,
    get_interview_scorecards,
    suggest_auto_scheduler_slots,
    get_communication_sequence,
    get_employer_hiring_forecast,
    get_talent_rediscovery_candidates,
    export_pipeline_audit_csv,
    export_pipeline_audit_pdf,
    get_pipeline_audit_download_history,
    DEFAULT_F26_ROLLOUT_CONTROLS,
    _load_f26_rollout_controls,
    _stable_bucket_for_rollout,
    F26_OPERATION_V2_ENDPOINT,
    _compute_legacy_retirement_gate_status,
    _normalize_retirement_phase,
    _target_retired_route_families,
    F26_RETIREMENT_PHASE_TO_FAMILIES,
    advance_communication_sequence,
)
from .employers import (
    AccessControlAction,
    AdminReviewAction,
    EmployerApplication,
    ThreadMessage,
    admin_access_control,
    admin_add_note,
    admin_review_application,
    admin_run_ai_risk_assessment,
    post_employer_message,
    resubmit_employer_info,
    start_reverification,
    submit_employer_application,
    upload_employer_document,
    get_my_application,
    download_employer_document,
    get_my_permissions,
    admin_employer_stats,
    admin_list_applications,
    admin_get_application,
    admin_command_center,
    admin_employer_communications,
    get_employer_messages,
    check_reverify_status,
)
from .global_miniapps import (
    EmployerProfileRequest,
    JobAIDescriptionRequest,
    JobAISalaryRequest,
    JobCreateRequest,
    JobUpdateRequest,
    ai_job_description,
    ai_rank_candidates,
    ai_salary_recommendation,
    create_job,
    register_employer,
    update_job,
)
from .job_ai_services import TranslateRequest, translate_text
from .job_platform import (
    AdminDecisionRequest,
    EmployerApprovalRequest,
    admin_decide_approval,
    resubmit_employer_approval,
    submit_employer_approval,
)
from .jobs_shared import require_auth, resolve_hiring_effective_plan
from .db import db
from .jobs_employer_console_models import (
    BulkPipelineActionRequest,
    CopilotExecuteRequest,
    CommunicationSequenceAdvanceRequest,
    CommunicationSequenceStartRequest,
    InterviewKitShareRequest,
    InterviewScorecardSubmitRequest,
    OfferApprovalRequest,
    OfferDraftRequest,
    OfferSendRequest,
    RediscoveryReengageRequest,
    SlaAutoTriggerRunRequest,
)
from models.jobs import JobApplication, ResumeProfile

router = APIRouter(prefix="/hiring/v2")

LEGACY_REMOVAL_MONITOR_WINDOWS = [
    {"label": "72h", "hours": 72},
    {"label": "7d", "hours": 24 * 7},
    {"label": "14d", "hours": 24 * 14},
    {"label": "30d", "hours": 24 * 30},
]

LEGACY_REMOVAL_SYNTHETIC_TOKENS = (
    "test_",
    "/test",
    "nonexistent",
    "smoke",
    "fixture",
)


class CandidateActionCompleteRequest(BaseModel):
    action_key: str
    idempotency_key: str | None = None


def _safe_iso_day(iso_value: str | None) -> str | None:
    if not iso_value:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except Exception:
        return None


def _compute_consecutive_streak(days_desc: list[str]) -> int:
    if not days_desc:
        return 0
    parsed_days: list[datetime] = []
    for item in days_desc:
        try:
            parsed_days.append(datetime.fromisoformat(item))
        except Exception:
            continue
    if not parsed_days:
        return 0
    parsed_days = sorted(parsed_days, reverse=True)
    streak = 1
    cursor = parsed_days[0]
    for day in parsed_days[1:]:
        delta = (cursor.date() - day.date()).days
        if delta == 1:
            streak += 1
            cursor = day
        elif delta == 0:
            continue
        else:
            break
    return streak


def _parse_simulator_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    else:
        text = str(raw).replace("\n", ",")
        values = [segment.strip() for segment in text.split(",")]
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _clamp_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        resolved = int(value)
    except Exception:
        resolved = default
    return max(minimum, min(resolved, maximum))


def _to_json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    return str(value)


def _legacy_route_family_from_event(row: dict) -> str:
    route_family = str(row.get("route_family") or "").strip().lower()
    if route_family in {"jobs", "employers"}:
        return route_family
    path = str(row.get("legacy_path") or "").strip().lower()
    if path.startswith("/api/jobs"):
        return "jobs"
    if path.startswith("/api/employers"):
        return "employers"
    return "unknown"


def _is_synthetic_legacy_event(row: dict) -> bool:
    path = str(row.get("legacy_path") or "").strip().lower()
    operation = str(row.get("operation") or "").strip().lower()
    if operation.startswith("test"):
        return True
    return any(token in path or token in operation for token in LEGACY_REMOVAL_SYNTHETIC_TOKENS)


async def _compute_legacy_removal_window_family_readiness(
    route_family: str,
    lookback_hours: int,
    *,
    exclude_synthetic: bool,
    mode: str,
    near_zero_max_events: int,
    near_zero_max_active_users: int,
) -> dict:
    family = str(route_family or "jobs").strip().lower()
    safe_hours = max(1, min(int(lookback_hours or 72), 24 * 30))
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(hours=safe_hours)).isoformat()
    path_prefix = r"^/api/jobs" if family == "jobs" else r"^/api/employers"

    query = {
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
    rows = (
        await db.hiring_v2_deprecation_telemetry
        .find(query, {"_id": 0, "operation": 1, "legacy_path": 1, "user_id": 1, "created_at": 1, "route_family": 1})
        .sort("created_at", -1)
        .limit(20000)
        .to_list(20000)
    )

    filtered_rows = [row for row in rows if not (exclude_synthetic and _is_synthetic_legacy_event(row))]
    synthetic_excluded_count = max(0, len(rows) - len(filtered_rows))
    users = {str(row.get("user_id") or "") for row in filtered_rows if str(row.get("user_id") or "").strip()}
    by_operation: dict[str, int] = defaultdict(int)
    for row in filtered_rows:
        operation = str(row.get("operation") or "unknown")
        by_operation[operation] += 1

    total_events = len(filtered_rows)
    active_users = len(users)

    if mode == "near_zero":
        gate_met = total_events <= near_zero_max_events and active_users <= near_zero_max_active_users
        events_score = 100.0 if near_zero_max_events <= 0 else max(0.0, min(100.0, (near_zero_max_events / max(total_events, 1)) * 100))
        users_score = 100.0 if near_zero_max_active_users <= 0 else max(0.0, min(100.0, (near_zero_max_active_users / max(active_users, 1)) * 100))
        readiness_score = 100.0 if gate_met else round((events_score + users_score) / 2, 2)
    else:
        gate_met = total_events == 0 and active_users == 0
        readiness_score = 100.0 if gate_met else round(max(0.0, 100.0 - (total_events * 18.0) - (active_users * 35.0)), 2)

    return {
        "route_family": family,
        "lookback_hours": safe_hours,
        "since": since_iso,
        "raw_total_events": len(rows),
        "total_events": total_events,
        "synthetic_excluded_count": synthetic_excluded_count,
        "active_users": active_users,
        "gate_met": gate_met,
        "readiness_score": readiness_score,
        "top_operations": [
            {"operation": key, "count": value}
            for key, value in sorted(by_operation.items(), key=lambda item: item[1], reverse=True)[:6]
        ],
    }


@router.get("/health")
async def hiring_v2_health() -> dict:
    return {
        "ok": True,
        "service": "hiring-v2",
        "version": "v2",
        "feature_id": "jobs-portal",
        "feature_number": 26,
    }


@router.get("/candidate/jobs/search")
async def hiring_v2_candidate_search(
    request: Request,
    q: str = "",
    location: str = "",
    country: str = "",
    job_type: str = "",
    remote: str = "",
    industry: str = "",
    salary_min: int = 0,
    visa: str = "",
    page: int = 1,
    limit: int = 20,
):
    return await search_jobs(
        request=request,
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


@router.get("/candidate/applications")
async def hiring_v2_candidate_applications(request: Request, status: str = "all"):
    return await get_my_applications(request=request, status=status)


@router.get("/candidate/saved-jobs")
async def hiring_v2_candidate_saved_jobs(request: Request):
    return await get_saved_jobs(request=request)


@router.get("/candidate/analytics")
async def hiring_v2_candidate_analytics(request: Request):
    return await employee_analytics(request=request)


@router.get("/candidate/recommendations")
async def hiring_v2_candidate_recommendations(request: Request):
    return await get_job_recommendations(request=request)


@router.get("/candidate/jobs/detail/{job_id}")
async def hiring_v2_candidate_job_detail(job_id: str):
    return await get_job_detail(job_id=job_id)


@router.get("/candidate/profile")
async def hiring_v2_candidate_profile(request: Request):
    return await get_employee_profile(request=request)


@router.get("/candidate/resume-score")
async def hiring_v2_candidate_resume_score(request: Request):
    return await get_resume_score(request=request)


@router.get("/candidate/alerts")
async def hiring_v2_candidate_alerts(request: Request, unread_only: bool = False, limit: int = 50):
    return await get_smart_alerts(request=request, unread_only=unread_only, limit=limit)


@router.get("/candidate/alerts/preferences")
async def hiring_v2_candidate_alert_preferences_read(request: Request):
    return await get_alert_preferences(request=request)


@router.get("/candidate/action-center")
async def hiring_v2_candidate_action_center(request: Request):
    user = await require_auth(request)
    user_id = str(user.user_id or "")

    profile = await db.employee_profiles.find_one({"user_id": user_id}, {"_id": 0, "skills": 1})
    application_count = await db.job_applications.count_documents({"user_id": user_id})
    interview_count = await db.job_applications.count_documents({"user_id": user_id, "status": "interview"})
    saved_jobs = await db.saved_jobs.count_documents({"user_id": user_id})
    recommendations = await get_job_recommendations(request=request)
    recommendation_count = int(recommendations.get("total") or 0)

    recent_events = await db.hiring_candidate_action_events.find(
        {"user_id": user_id},
        {"_id": 0, "action_key": 1, "created_at": 1},
    ).sort("created_at", -1).limit(60).to_list(60)

    unique_days: list[str] = []
    seen_days: set[str] = set()
    for event in recent_events:
        day = _safe_iso_day(event.get("created_at"))
        if not day or day in seen_days:
            continue
        seen_days.add(day)
        unique_days.append(day)
    streak_days = _compute_consecutive_streak(unique_days)

    completed_actions = {str(row.get("action_key") or "") for row in recent_events if str(row.get("action_key") or "").strip()}

    next_actions = [
        {
            "action_key": "refresh-job-search",
            "label": "Refresh job matches",
            "description": "Run a fresh search to capture new matching roles.",
            "completed": "refresh-job-search" in completed_actions,
        },
        {
            "action_key": "save-one-job",
            "label": "Save one role",
            "description": "Keep shortlist quality high by saving one role.",
            "completed": saved_jobs > 0 or "save-one-job" in completed_actions,
        },
        {
            "action_key": "submit-one-application",
            "label": "Submit one application",
            "description": "Maintain pipeline momentum with one application.",
            "completed": application_count > 0 or "submit-one-application" in completed_actions,
        },
    ]

    completed_count = sum(1 for row in next_actions if row.get("completed"))
    momentum_score = min(100, max(0, (completed_count * 30) + min(20, streak_days * 5) + min(20, interview_count * 10)))

    effective_plan = await resolve_hiring_effective_plan(user)

    return {
        "feature_number": 26,
        "feature_id": "jobs-portal",
        "user_id": user_id,
        "effective_plan": effective_plan,
        "streak_days": streak_days,
        "momentum_score": momentum_score,
        "summary": {
            "applications": application_count,
            "interviews": interview_count,
            "saved_jobs": saved_jobs,
            "recommendations": recommendation_count,
            "skills_count": len(profile.get("skills", [])) if profile else 0,
        },
        "next_actions": next_actions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/candidate/action-center/complete")
async def hiring_v2_candidate_action_complete(payload: CandidateActionCompleteRequest, request: Request):
    user = await require_auth(request)
    user_id = str(user.user_id or "")
    action_key = str(payload.action_key or "").strip().lower()
    if not action_key:
        raise HTTPException(status_code=400, detail="action_key required")

    today = datetime.now(timezone.utc).date().isoformat()
    idempotency_key = str(payload.idempotency_key or "").strip() or f"{user_id}:{action_key}:{today}"

    existing = await db.hiring_candidate_action_events.find_one(
        {
            "user_id": user_id,
            "action_key": action_key,
            "idempotency_key": idempotency_key,
        },
        {"_id": 0, "event_id": 1, "created_at": 1},
    )
    if existing:
        return {
            "success": True,
            "idempotent": True,
            "event": existing,
        }

    event = {
        "event_id": f"f26act_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "feature_number": 26,
        "feature_id": "jobs-portal",
        "user_id": user_id,
        "action_key": action_key,
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.hiring_candidate_action_events.insert_one(event)
    response_event = {k: v for k, v in event.items() if k != "_id"}
    return {
        "success": True,
        "idempotent": False,
        "event": response_event,
    }


@router.post("/candidate/apply")
async def hiring_v2_candidate_apply(payload: JobApplication, request: Request):
    return await apply_for_job(application=payload, request=request)


@router.post("/candidate/save/{job_id}")
async def hiring_v2_candidate_save(job_id: str, request: Request):
    return await save_job(job_id=job_id, request=request)


@router.post("/candidate/profile/update")
async def hiring_v2_candidate_profile_update(payload: ResumeProfile, request: Request):
    return await update_employee_profile(profile=payload, request=request)


@router.post("/candidate/resume/upload")
async def hiring_v2_candidate_resume_upload(request: Request, file: UploadFile = File(...)):
    return await upload_resume(request=request, file=file)


@router.post("/candidate/alerts/{alert_id}/read")
async def hiring_v2_candidate_alert_read(alert_id: str, request: Request):
    return await mark_alert_read(alert_id=alert_id, request=request)


@router.post("/candidate/alerts/read-all")
async def hiring_v2_candidate_alerts_read_all(request: Request):
    return await mark_all_alerts_read(request=request)


@router.post("/candidate/alerts/preferences")
async def hiring_v2_candidate_alert_preferences(request: Request):
    return await update_alert_preferences(request=request)


@router.get("/dashboard/summary")
async def hiring_v2_dashboard_summary(request: Request):
    return await get_jobs_portal_summary(request=request)


@router.get("/employer/offers")
async def hiring_v2_employer_offers(request: Request, application_id: str | None = None, limit: int = 120):
    return await list_employer_offers(request=request, application_id=application_id, limit=limit)


@router.get("/employer/pipeline-board")
async def hiring_v2_employer_pipeline_board(request: Request, limit: int = 120):
    return await get_employer_pipeline_board(request=request, limit=limit)


@router.get("/employer/jobs")
async def hiring_v2_employer_jobs(request: Request):
    return await get_my_posted_jobs(request=request)


@router.get("/employer/applicants/{job_id}")
async def hiring_v2_employer_applicants(job_id: str, request: Request):
    return await get_job_applicants(job_id=job_id, request=request)


@router.get("/employer/pipeline-board/{application_id}/timeline")
async def hiring_v2_employer_pipeline_timeline_read(application_id: str, request: Request, limit: int = 150):
    return await get_employer_pipeline_timeline(application_id=application_id, request=request, limit=limit)


@router.get("/employer/pipeline-health")
async def hiring_v2_employer_pipeline_health(request: Request):
    user = await require_auth(request)

    if user.is_admin:
        roles_query = {"status": "active"}
    else:
        approved_access = bool(
            getattr(user, "approved_employer_access", False)
            or str(getattr(user, "platform_role", "") or "").lower() in {"employer", "approved_employer"}
            or getattr(user, "full_access", False)
        )
        if not approved_access:
            return {
                "feature_number": 26,
                "feature_id": "jobs-portal",
                "access_state": "pending_approval",
                "open_roles": 0,
                "active_pipeline": 0,
                "interviews": 0,
                "offers": 0,
                "bottlenecks": 0,
                "pipeline_health_score": 0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        roles_query = {"status": "active", "poster_user_id": user.user_id}

    jobs = await db.jobs.find(roles_query, {"_id": 0, "job_id": 1}).to_list(400)
    job_ids = [row.get("job_id") for row in jobs if row.get("job_id")]
    open_roles = len(job_ids)

    if not job_ids:
        return {
            "feature_number": 26,
            "feature_id": "jobs-portal",
            "open_roles": 0,
            "active_pipeline": 0,
            "interviews": 0,
            "offers": 0,
            "bottlenecks": 0,
            "pipeline_health_score": 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    apps = await db.job_applications.find({"job_id": {"$in": job_ids}}, {"_id": 0, "status": 1, "updated_at": 1}).to_list(1000)
    active_pipeline = len([row for row in apps if str(row.get("status") or "").lower() not in {"rejected", "hired"}])
    interviews = len([row for row in apps if str(row.get("status") or "").lower() == "interview"])
    offers = len([row for row in apps if str(row.get("status") or "").lower() == "offer"])

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    bottlenecks = 0
    for row in apps:
        status = str(row.get("status") or "").lower()
        if status in {"rejected", "hired"}:
            continue
        updated_at = row.get("updated_at")
        if not updated_at:
            continue
        try:
            dt = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                bottlenecks += 1
        except Exception:
            continue

    completion_signal = max(0, 100 - (bottlenecks * 12))
    load_signal = max(0, 100 - max(0, active_pipeline - (open_roles * 6)) * 2)
    conversion_signal = min(100, (offers * 20) + (interviews * 8))
    pipeline_health_score = int(round((completion_signal * 0.45) + (load_signal * 0.25) + (conversion_signal * 0.30)))

    return {
        "feature_number": 26,
        "feature_id": "jobs-portal",
        "open_roles": open_roles,
        "active_pipeline": active_pipeline,
        "interviews": interviews,
        "offers": offers,
        "bottlenecks": bottlenecks,
        "pipeline_health_score": max(0, min(100, pipeline_health_score)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/employer/kpi-header")
async def hiring_v2_employer_kpi_header(request: Request, window_days: int = 30):
    return await get_employer_kpi_header(request=request, window_days=window_days)


@router.get("/employer/sla-alerts")
async def hiring_v2_employer_sla_alerts(request: Request, limit: int = 120):
    return await get_employer_sla_alerts(request=request, limit=limit)


@router.get("/employer/sla-auto-triggers")
async def hiring_v2_employer_sla_auto_triggers_read(request: Request, application_id: Optional[str] = None, limit: int = 12):
    return await get_employer_sla_auto_triggers(request=request, application_id=application_id, limit=limit)


@router.get("/employer/copilot/{application_id}/suggestions")
async def hiring_v2_employer_copilot_suggestions_read(application_id: str, request: Request):
    return await get_recruiter_copilot_suggestions(application_id=application_id, request=request)


@router.get("/employer/scorecards/{application_id}")
async def hiring_v2_employer_scorecards_read(application_id: str, request: Request):
    return await get_interview_scorecards(application_id=application_id, request=request)


@router.get("/employer/auto-scheduler/{application_id}/suggest")
async def hiring_v2_employer_auto_scheduler_suggest_read(
    application_id: str,
    request: Request,
    days_ahead: int = 7,
    duration_minutes: int = 45,
):
    return await suggest_auto_scheduler_slots(
        application_id=application_id,
        request=request,
        days_ahead=days_ahead,
        duration_minutes=duration_minutes,
    )


@router.get("/employer/communication-sequences/{application_id}")
async def hiring_v2_employer_communication_sequences_read(application_id: str, request: Request):
    return await get_communication_sequence(application_id=application_id, request=request)


@router.get("/employer/hiring-forecast")
async def hiring_v2_employer_hiring_forecast_read(request: Request, window_days: int = 45):
    return await get_employer_hiring_forecast(request=request, window_days=window_days)


@router.get("/employer/talent-rediscovery")
async def hiring_v2_employer_talent_rediscovery_read(request: Request, job_id: Optional[str] = None, limit: int = 20):
    return await get_talent_rediscovery_candidates(request=request, job_id=job_id, limit=limit)


@router.get("/employer/pipeline-board/{application_id}/audit-export.csv")
async def hiring_v2_employer_pipeline_audit_export_csv(
    application_id: str,
    request: Request,
    range_key: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    return await export_pipeline_audit_csv(
        application_id=application_id,
        request=request,
        range_key=range_key,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/employer/pipeline-board/{application_id}/audit-export.pdf")
async def hiring_v2_employer_pipeline_audit_export_pdf(
    application_id: str,
    request: Request,
    range_key: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    return await export_pipeline_audit_pdf(
        application_id=application_id,
        request=request,
        range_key=range_key,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/employer/pipeline-board/{application_id}/audit-download-history")
async def hiring_v2_employer_pipeline_audit_download_history_read(application_id: str, request: Request, limit: int = 8):
    return await get_pipeline_audit_download_history(application_id=application_id, request=request, limit=limit)


@router.post("/employer/offers/build")
async def hiring_v2_employer_build_offer(payload: OfferDraftRequest, request: Request):
    return await build_offer_draft(payload=payload, request=request)


@router.post("/employer/offers/{offer_id}/submit-approval")
async def hiring_v2_employer_submit_offer(offer_id: str, payload: OfferApprovalRequest, request: Request):
    return await submit_offer_for_approval(offer_id=offer_id, payload=payload, request=request)


@router.post("/employer/offers/{offer_id}/approve")
async def hiring_v2_employer_approve_offer(offer_id: str, payload: OfferApprovalRequest, request: Request):
    return await approve_offer(offer_id=offer_id, payload=payload, request=request)


@router.post("/employer/offers/{offer_id}/send")
async def hiring_v2_employer_send_offer(offer_id: str, payload: OfferSendRequest, request: Request):
    return await send_offer_letter(offer_id=offer_id, payload=payload, request=request)


@router.post("/employer/pipeline/bulk-action")
async def hiring_v2_employer_pipeline_bulk_action(payload: BulkPipelineActionRequest, request: Request):
    user = await require_auth(request)
    if user.is_admin:
        return {
            "success": True,
            "processed": 0,
            "failed": 0,
            "results": [],
            "message": "No matching applications found for admin context",
        }
    return await bulk_pipeline_action(payload=payload, request=request)


@router.post("/employer/pipeline/{application_id}/copilot-execute")
async def hiring_v2_employer_pipeline_copilot_execute(application_id: str, payload: CopilotExecuteRequest, request: Request):
    return await execute_recruiter_copilot_action(
        application_id=application_id,
        payload=payload,
        request=request,
    )


@router.post("/employer/applications/{job_id}/{application_id}/status")
async def hiring_v2_employer_application_status_update(job_id: str, application_id: str, request: Request):
    return await update_application_status(job_id=job_id, application_id=application_id, request=request)


@router.post("/employer/interview-kit/{application_id}/generate")
async def hiring_v2_employer_generate_interview_kit(application_id: str, request: Request):
    return await generate_interview_kit(application_id=application_id, request=request)


@router.post("/employer/interview-kit/{application_id}/share")
async def hiring_v2_employer_share_interview_kit(application_id: str, payload: InterviewKitShareRequest, request: Request):
    return await share_interview_kit(application_id=application_id, payload=payload, request=request)


@router.post("/employer/scorecards/{application_id}")
async def hiring_v2_employer_submit_scorecard(application_id: str, payload: InterviewScorecardSubmitRequest, request: Request):
    return await submit_interview_scorecard(application_id=application_id, payload=payload, request=request)


@router.post("/employer/auto-scheduler/{application_id}/book")
async def hiring_v2_employer_book_auto_scheduler(application_id: str, request: Request):
    return await book_auto_scheduler_slot(application_id=application_id, request=request)


@router.post("/employer/communication-sequences/{application_id}/start")
async def hiring_v2_employer_start_communication_sequence(
    application_id: str,
    payload: CommunicationSequenceStartRequest,
    request: Request,
):
    return await start_communication_sequence(application_id=application_id, payload=payload, request=request)


@router.post("/employer/communication-sequences/{application_id}/advance")
async def hiring_v2_employer_advance_communication_sequence(
    application_id: str,
    payload: CommunicationSequenceAdvanceRequest,
    request: Request,
):
    return await advance_communication_sequence(application_id=application_id, payload=payload, request=request)


@router.post("/employer/talent-rediscovery/{candidate_id}/reengage")
async def hiring_v2_employer_reengage_candidate(candidate_id: str, payload: RediscoveryReengageRequest, request: Request):
    return await reengage_rediscovered_candidate(candidate_id=candidate_id, payload=payload, request=request)


@router.post("/employer/application/apply")
async def hiring_v2_employer_application_apply(payload: EmployerApplication, request: Request):
    return await submit_employer_application(application=payload, request=request)


@router.post("/employer/application/upload-document")
async def hiring_v2_employer_application_upload_document(
    request: Request,
    document_type: str = Form(...),
    document_role: str | None = Form(None),
    file: UploadFile = File(...),
):
    return await upload_employer_document(
        request=request,
        document_type=document_type,
        document_role=document_role,
        file=file,
    )


@router.post("/employer/application/resubmit-info")
async def hiring_v2_employer_application_resubmit_info(payload: EmployerApplication, request: Request):
    return await resubmit_employer_info(payload=payload, request=request)


@router.post("/employer/application/reverify")
async def hiring_v2_employer_application_reverify(request: Request):
    return await start_reverification(request=request)


@router.post("/employer/application/messages/{employer_id}")
async def hiring_v2_employer_application_post_message(employer_id: str, payload: ThreadMessage, request: Request):
    return await post_employer_message(employer_id=employer_id, payload=payload, request=request)


@router.get("/employer/application/current")
async def hiring_v2_employer_application_current(request: Request):
    return await get_my_application(request=request)


@router.get("/employer/application/permissions")
async def hiring_v2_employer_application_permissions(request: Request):
    return await get_my_permissions(request=request)


@router.get("/employer/application/reverify-status")
async def hiring_v2_employer_application_reverify_status(request: Request):
    return await check_reverify_status(request=request)


@router.get("/employer/application/messages/{employer_id}")
async def hiring_v2_employer_application_messages(employer_id: str, request: Request):
    return await get_employer_messages(employer_id=employer_id, request=request)


@router.get("/employer/application/documents/{employer_id}/{doc_id}/download")
async def hiring_v2_employer_application_document_download(employer_id: str, doc_id: str, request: Request):
    return await download_employer_document(employer_id=employer_id, doc_id=doc_id, request=request)


@router.post("/admin/employers/review/{employer_id}")
async def hiring_v2_admin_employer_review(employer_id: str, payload: AdminReviewAction, request: Request):
    return await admin_review_application(employer_id=employer_id, payload=payload, request=request)


@router.post("/admin/employers/access-control/{employer_id}")
async def hiring_v2_admin_employer_access_control(employer_id: str, payload: AccessControlAction, request: Request):
    return await admin_access_control(employer_id=employer_id, payload=payload, request=request)


@router.post("/admin/employers/risk-assess/{employer_id}")
async def hiring_v2_admin_employer_risk_assess(employer_id: str, request: Request):
    return await admin_run_ai_risk_assessment(employer_id=employer_id, request=request)


@router.post("/admin/employers/add-note/{employer_id}")
async def hiring_v2_admin_employer_add_note(employer_id: str, request: Request):
    return await admin_add_note(employer_id=employer_id, request=request)


@router.post("/admin/employers/messages/{employer_id}")
async def hiring_v2_admin_employer_post_message(employer_id: str, payload: ThreadMessage, request: Request):
    return await post_employer_message(employer_id=employer_id, payload=payload, request=request)


@router.get("/admin/employers/stats")
async def hiring_v2_admin_employers_stats(request: Request):
    return await admin_employer_stats(request=request)


@router.get("/admin/employers/applications")
async def hiring_v2_admin_employers_applications(
    request: Request,
    status: str = "all",
    risk_level: str = "all",
    page: int = 1,
    limit: int = 20,
):
    return await admin_list_applications(
        request=request,
        status=status,
        risk_level=risk_level,
        page=page,
        limit=limit,
    )


@router.get("/admin/employers/application/{employer_id}")
async def hiring_v2_admin_employers_application(employer_id: str, request: Request):
    return await admin_get_application(employer_id=employer_id, request=request)


@router.get("/admin/employers/command-center")
async def hiring_v2_admin_employers_command_center(request: Request, status: str = "all", limit: int = 30):
    return await admin_command_center(request=request, status=status, limit=limit)


@router.get("/admin/employers/communications/{employer_id}")
async def hiring_v2_admin_employers_communications(employer_id: str, request: Request):
    return await admin_employer_communications(employer_id=employer_id, request=request)


@router.post("/admin/approvals/decide")
async def hiring_v2_admin_approvals_decide(payload: AdminDecisionRequest, request: Request):
    return await admin_decide_approval(payload=payload, request=request)


@router.post("/employer/approval/submit")
async def hiring_v2_employer_approval_submit(payload: EmployerApprovalRequest, request: Request):
    return await submit_employer_approval(payload=payload, request=request)


@router.post("/employer/approval/resubmit")
async def hiring_v2_employer_approval_resubmit(request: Request):
    return await resubmit_employer_approval(request=request)


@router.post("/employer/register")
async def hiring_v2_employer_register(payload: EmployerProfileRequest, request: Request):
    return await register_employer(request=payload, req=request)


@router.post("/employer/jobs/create")
async def hiring_v2_employer_create_job(payload: JobCreateRequest, request: Request):
    return await create_job(request=payload, req=request)


@router.put("/employer/jobs/{job_id}")
async def hiring_v2_employer_update_job(job_id: str, payload: JobUpdateRequest, request: Request):
    return await update_job(job_id=job_id, request=payload, req=request)


@router.post("/ai/description")
async def hiring_v2_ai_description(payload: JobAIDescriptionRequest, request: Request):
    return await ai_job_description(request=payload, req=request)


@router.post("/ai/salary")
async def hiring_v2_ai_salary(payload: JobAISalaryRequest, request: Request):
    return await ai_salary_recommendation(request=payload, req=request)


@router.post("/ai/rank-candidates")
async def hiring_v2_ai_rank_candidates(request: Request, job_id: str = Form(...)):
    return await ai_rank_candidates(req=request, job_id=job_id)


@router.post("/ai/translate")
async def hiring_v2_ai_translate(payload: TranslateRequest, request: Request):
    return await translate_text(payload=payload, request=request)


@router.post("/employer/sla-auto-triggers/run")
async def hiring_v2_employer_sla_auto_triggers_run(payload: SlaAutoTriggerRunRequest, request: Request):
    return await run_employer_sla_auto_triggers(payload=payload, request=request)


@router.post("/candidate/priority-apply/{application_id}")
async def hiring_v2_candidate_priority_apply(application_id: str, request: Request):
    user = await require_auth(request)

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "subscription_plan": 1, "is_admin": 1}) or {}
    plan = str(user_doc.get("subscription_plan") or "free").strip().lower()
    if not bool(user_doc.get("is_admin")) and plan not in {"basic", "premium"}:
        raise HTTPException(status_code=403, detail="Priority apply is available on Basic and Premium plans")

    application = await db.job_applications.find_one(
        {"application_id": application_id, "$or": [{"candidate_id": user.user_id}, {"user_id": user.user_id}]},
        {"_id": 0, "application_id": 1, "status": 1, "job_id": 1},
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.job_applications.update_one(
        {"application_id": application_id},
        {
            "$set": {
                "priority_apply": True,
                "priority_apply_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )
    await db.hiring_premium_events.insert_one(
        {
            "event_id": f"hprem_{application_id}_{int(datetime.now(timezone.utc).timestamp())}",
            "event_type": "priority_apply",
            "user_id": user.user_id,
            "application_id": application_id,
            "job_id": application.get("job_id"),
            "plan": plan,
            "created_at": now_iso,
        }
    )
    return {"success": True, "application_id": application_id, "priority_apply": True}


@router.post("/candidate/boost-profile")
async def hiring_v2_candidate_boost_profile(request: Request):
    user = await require_auth(request)
    body = await request.json()
    boost_hours = int(body.get("boost_hours") or 72)
    boost_hours = max(24, min(boost_hours, 168))

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "subscription_plan": 1, "is_admin": 1}) or {}
    plan = str(user_doc.get("subscription_plan") or "free").strip().lower()
    if not bool(user_doc.get("is_admin")) and plan not in {"basic", "premium"}:
        raise HTTPException(status_code=403, detail="Boosted profile is available on Basic and Premium plans")

    now = datetime.now(timezone.utc)
    until_iso = (now + timedelta(hours=boost_hours)).isoformat()
    await db.employee_profiles.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "boosted_profile": True,
                "boosted_until": until_iso,
                "updated_at": now.isoformat(),
            }
        },
        upsert=True,
    )
    await db.hiring_premium_events.insert_one(
        {
            "event_id": f"hboost_{user.user_id}_{int(now.timestamp())}",
            "event_type": "boosted_profile",
            "user_id": user.user_id,
            "plan": plan,
            "boost_hours": boost_hours,
            "created_at": now.isoformat(),
        }
    )
    return {"success": True, "boosted_profile": True, "boosted_until": until_iso}


@router.get("/employer/shortlist/explainability")
async def hiring_v2_employer_shortlist_explainability(request: Request, limit: int = 20):
    user = await require_auth(request)
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "subscription_plan": 1, "is_admin": 1}) or {}
    plan = str(user_doc.get("subscription_plan") or "free").strip().lower()
    if not bool(user_doc.get("is_admin")) and plan not in {"premium"}:
        raise HTTPException(status_code=403, detail="Shortlist explainability is available on Premium plan")

    board = await get_employer_pipeline_board(request=request, limit=max(1, min(limit, 100)))
    rows = board.get("applications") or []
    explainability = []
    for row in rows[:limit]:
        explainability.append(
            {
                "application_id": row.get("application_id"),
                "candidate_name": row.get("candidate_name"),
                "match_score": row.get("match_score") or 0,
                "match_reasons": row.get("match_reasons") or [],
                "recommendation": row.get("recommendation") or "lean_hire",
            }
        )
    return {"total": len(explainability), "items": explainability}


@router.get("/employer/premium-analytics/events")
async def hiring_v2_employer_premium_analytics_events(request: Request, lookback_days: int = 30, limit: int = 200):
    user = await require_auth(request)
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "subscription_plan": 1, "is_admin": 1}) or {}
    plan = str(user_doc.get("subscription_plan") or "free").strip().lower()
    if not bool(user_doc.get("is_admin")) and plan not in {"premium"}:
        raise HTTPException(status_code=403, detail="Premium analytics events are available on Premium plan")

    days = max(1, min(lookback_days, 180))
    safe_limit = max(1, min(limit, 1000))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    events = (
        await db.hiring_premium_events
        .find({"created_at": {"$gte": since_iso}}, {"_id": 0})
        .sort("created_at", -1)
        .limit(safe_limit)
        .to_list(safe_limit)
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "total": len(events),
        "events": events,
    }


@router.get("/admin/workflow-events")
async def hiring_v2_admin_workflow_events(
    request: Request,
    event_type: str = "",
    user_id: str = "",
    include_metadata: bool = False,
    lookback_hours: int = Query(default=72, ge=1, le=24 * 30),
    limit: int = Query(default=100, ge=1, le=500),
):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    since_iso = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    query: dict = {"created_at": {"$gte": since_iso}}
    if event_type:
        query["event_type"] = event_type
    if user_id:
        query["user_id"] = user_id

    projection = {
        "_id": 0,
        "event_id": 1,
        "event_type": 1,
        "user_id": 1,
        "path": 1,
        "method": 1,
        "correlation_id": 1,
        "created_at": 1,
    }
    if include_metadata:
        projection["metadata"] = 1

    events = (
        await db.hiring_workflow_events
        .find(query, projection)
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )

    safe_events = [_to_json_safe(event) for event in events]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_hours": lookback_hours,
        "filters": {
            "event_type": event_type or None,
            "user_id": user_id or None,
        },
        "include_metadata": include_metadata,
        "total": len(safe_events),
        "events": safe_events,
    }



@router.post("/admin/canary-simulator")
async def hiring_v2_admin_canary_simulator(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json()
    current_controls = await _load_f26_rollout_controls()

    proposed_controls = {
        "canary_enabled": bool(body.get("canary_enabled", current_controls.get("canary_enabled", False))),
        "legacy_allow_pct": _clamp_int(body.get("legacy_allow_pct", current_controls.get("legacy_allow_pct", 100)), 100, 0, 100),
        "auto_rollback_enabled": bool(body.get("auto_rollback_enabled", current_controls.get("auto_rollback_enabled", True))),
        "rollback_window_hours": _clamp_int(body.get("rollback_window_hours", current_controls.get("rollback_window_hours", 6)), 6, 1, 24 * 14),
        "rollback_legacy_event_threshold": max(1, _clamp_int(body.get("rollback_legacy_event_threshold", current_controls.get("rollback_legacy_event_threshold", 500)), 500, 1, 2000000)),
        "soft_disable_operations": _parse_simulator_list(body.get("soft_disable_operations", current_controls.get("soft_disable_operations") or [])),
        "admin_override_user_ids": _parse_simulator_list(body.get("admin_override_user_ids", current_controls.get("admin_override_user_ids") or [])),
    }

    lookback_hours = _clamp_int(
        body.get("lookback_hours", max(72, int(current_controls.get("rollback_window_hours", 6)))),
        72,
        1,
        24 * 30,
    )
    top_users_limit = _clamp_int(body.get("top_users_limit", 5), 5, 1, 20)
    requested_operations = _parse_simulator_list(body.get("operations", []))

    since_iso = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    telemetry_query: dict = {"created_at": {"$gte": since_iso}}
    if requested_operations:
        telemetry_query["operation"] = {"$in": requested_operations}

    rows = await db.hiring_v2_deprecation_telemetry.find(
        telemetry_query,
        {
            "_id": 0,
            "operation": 1,
            "user_id": 1,
            "legacy_path": 1,
            "method": 1,
            "created_at": 1,
        },
    ).limit(20000).to_list(20000)

    available_operations = sorted({str(row.get("operation") or "unknown") for row in rows if str(row.get("operation") or "").strip()})
    operation_scope = requested_operations or available_operations or sorted(F26_OPERATION_V2_ENDPOINT.keys())

    soft_disabled_ops = set(proposed_controls["soft_disable_operations"])
    override_users = set(proposed_controls["admin_override_user_ids"])
    canary_enabled = bool(proposed_controls["canary_enabled"])
    allow_pct = int(proposed_controls["legacy_allow_pct"])

    rows_by_operation: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        operation = str(row.get("operation") or "unknown")
        rows_by_operation[operation].append(row)

    operation_outputs: list[dict] = []
    aggregate_allowed = 0
    aggregate_blocked = 0
    impacted_users_global: set[str] = set()

    for operation in operation_scope:
        op_rows = rows_by_operation.get(operation, [])
        unique_users = {str(item.get("user_id") or "") for item in op_rows if str(item.get("user_id") or "").strip()}
        blocked_user_counts: dict[str, int] = defaultdict(int)
        reason_counts: dict[str, int] = defaultdict(int)
        allowed_events = 0
        blocked_events = 0

        for row in op_rows:
            user_id = str(row.get("user_id") or "")
            is_override = bool(user_id and user_id in override_users)

            if operation in soft_disabled_ops and not is_override:
                blocked_events += 1
                reason_counts["soft_disabled_operation"] += 1
                if user_id:
                    blocked_user_counts[user_id] += 1
                continue

            if canary_enabled and allow_pct < 100 and not is_override and user_id:
                bucket = _stable_bucket_for_rollout(user_id, operation)
                if bucket >= allow_pct:
                    blocked_events += 1
                    reason_counts["canary_rollout_block"] += 1
                    blocked_user_counts[user_id] += 1
                    continue

            allowed_events += 1

        impacted_users = set(blocked_user_counts.keys())
        impacted_users_global.update(impacted_users)
        aggregate_allowed += allowed_events
        aggregate_blocked += blocked_events
        total_events = len(op_rows)
        blocked_pct = round((blocked_events / total_events) * 100, 2) if total_events else 0.0

        operation_outputs.append(
            {
                "operation": operation,
                "v2_endpoint": F26_OPERATION_V2_ENDPOINT.get(operation),
                "total_events": total_events,
                "unique_users": len(unique_users),
                "projected_allowed_events": allowed_events,
                "projected_blocked_events": blocked_events,
                "projected_blocked_pct": blocked_pct,
                "projected_blocked_users": len(impacted_users),
                "top_impacted_users": [
                    {"user_id": uid, "blocked_events": count}
                    for uid, count in sorted(blocked_user_counts.items(), key=lambda item: item[1], reverse=True)[:top_users_limit]
                ],
                "block_reasons": [
                    {"reason": reason, "count": count}
                    for reason, count in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)
                ],
            }
        )

    operation_outputs.sort(key=lambda item: item["projected_blocked_events"], reverse=True)

    strict_controls_present = bool(canary_enabled) or bool(soft_disabled_ops)
    rollback_window_hours = int(proposed_controls["rollback_window_hours"])
    rollback_since_iso = (datetime.now(timezone.utc) - timedelta(hours=rollback_window_hours)).isoformat()
    rollback_query = {"created_at": {"$gte": rollback_since_iso}}
    if requested_operations:
        rollback_query["operation"] = {"$in": requested_operations}
    rollback_window_legacy_events = await db.hiring_v2_deprecation_telemetry.count_documents(rollback_query)

    rollback_threshold = int(proposed_controls["rollback_legacy_event_threshold"])
    would_trigger_auto_rollback = bool(
        proposed_controls["auto_rollback_enabled"]
        and strict_controls_present
        and rollback_window_legacy_events >= rollback_threshold
    )

    total_events = len(rows)
    blocked_pct_total = round((aggregate_blocked / total_events) * 100, 2) if total_events else 0.0
    if would_trigger_auto_rollback or blocked_pct_total >= 70:
        risk_level = "high"
    elif blocked_pct_total >= 35:
        risk_level = "medium"
    else:
        risk_level = "low"

    if would_trigger_auto_rollback:
        recommendation = "Proposed policy likely triggers automatic rollback. Relax allow-percent or raise threshold before enabling."
    elif risk_level == "high":
        recommendation = "High impact forecast. Use phased rollout and monitor top impacted operations/users first."
    elif risk_level == "medium":
        recommendation = "Moderate impact forecast. Enable canary incrementally with tighter operation scope."
    else:
        recommendation = "Low impact forecast. Safe to trial with standard monitoring cadence."

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_number": 26,
        "feature_id": "jobs-portal",
        "telemetry_window": {
            "lookback_hours": lookback_hours,
            "since": since_iso,
            "total_legacy_events": total_events,
        },
        "current_controls": {
            **DEFAULT_F26_ROLLOUT_CONTROLS,
            **current_controls,
        },
        "proposed_controls": {
            **proposed_controls,
            "operations": operation_scope,
        },
        "summary": {
            "operations_covered": len(operation_scope),
            "projected_allowed_events": aggregate_allowed,
            "projected_blocked_events": aggregate_blocked,
            "projected_blocked_pct": blocked_pct_total,
            "projected_impacted_users": len(impacted_users_global),
            "rollback_window_hours": rollback_window_hours,
            "rollback_legacy_event_threshold": rollback_threshold,
            "rollback_window_legacy_events": rollback_window_legacy_events,
            "would_trigger_auto_rollback": would_trigger_auto_rollback,
            "rollback_risk_level": risk_level,
            "recommendation": recommendation,
        },
        "operations": operation_outputs,
    }


@router.get("/admin/deprecation-telemetry")
async def hiring_v2_admin_deprecation_telemetry(
    request: Request,
    lookback_days: int = Query(default=14, ge=1, le=90),
    limit: int = Query(default=1000, ge=1, le=5000),
):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    since_iso = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    query = {"created_at": {"$gte": since_iso}}
    safe_limit = max(1, min(limit, 5000))
    rows = (
        await db.hiring_v2_deprecation_telemetry
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(safe_limit)
        .to_list(safe_limit)
    )

    by_operation: dict[str, int] = {}
    by_endpoint: dict[str, int] = {}
    by_route_family: dict[str, int] = {}
    users = set()
    for row in rows:
        op = str(row.get("operation") or "unknown")
        by_operation[op] = by_operation.get(op, 0) + 1
        endpoint = str(row.get("legacy_path") or "")
        if endpoint:
            by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + 1
        uid = str(row.get("user_id") or "")
        if uid:
            users.add(uid)

        route_family = str(row.get("route_family") or "").strip().lower()
        if not route_family:
            if endpoint.startswith("/api/jobs"):
                route_family = "jobs"
            elif endpoint.startswith("/api/employers"):
                route_family = "employers"
            else:
                route_family = "unknown"
        by_route_family[route_family] = by_route_family.get(route_family, 0) + 1

    remaining_ops = sorted([k for k, v in by_operation.items() if v > 0])
    migration_progress_pct = 100.0 if not rows else max(0.0, min(99.0, 100.0 - min(95.0, float(len(remaining_ops) * 4))))
    controls = await _load_f26_rollout_controls()
    retirement_phase = _normalize_retirement_phase(controls.get("retirement_phase"))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "total_events": len(rows),
        "active_legacy_users": len(users),
        "remaining_legacy_operations": remaining_ops,
        "migration_progress_pct": round(migration_progress_pct, 2),
        "top_operations": sorted(
            [{"operation": k, "count": v} for k, v in by_operation.items()],
            key=lambda item: item["count"],
            reverse=True,
        )[:20],
        "top_legacy_endpoints": sorted(
            [{"endpoint": k, "count": v} for k, v in by_endpoint.items()],
            key=lambda item: item["count"],
            reverse=True,
        )[:20],
        "route_family_breakdown": sorted(
            [{"route_family": key, "count": value} for key, value in by_route_family.items()],
            key=lambda item: item["count"],
            reverse=True,
        ),
        "retirement_phase": retirement_phase,
        "legacy_retirement_enabled": bool(controls.get("legacy_retirement_enabled")),
        "retired_legacy_route_families": _target_retired_route_families(controls),
        "events": rows[:100],
    }


@router.get("/admin/canary-controls")
async def hiring_v2_admin_canary_controls(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    controls = await _load_f26_rollout_controls()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "controls": controls,
        "defaults": DEFAULT_F26_ROLLOUT_CONTROLS,
    }


@router.get("/admin/legacy-retirement-readiness")
async def hiring_v2_admin_legacy_retirement_readiness(
    request: Request,
    lookback_hours: int = Query(default=72, ge=1, le=24 * 30),
):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    controls = await _load_f26_rollout_controls()
    phase = _normalize_retirement_phase(controls.get("retirement_phase"))
    target_families = F26_RETIREMENT_PHASE_TO_FAMILIES.get(phase, []) if bool(controls.get("legacy_retirement_enabled")) else []

    jobs_readiness = await _compute_legacy_retirement_gate_status(controls, "jobs", lookback_hours)
    employers_readiness = await _compute_legacy_retirement_gate_status(controls, "employers", lookback_hours)
    family_readiness = [jobs_readiness, employers_readiness]

    recommended_phase = "observe"
    if jobs_readiness.get("gate_met") and employers_readiness.get("gate_met"):
        recommended_phase = "phase2_jobs_employers_writes"
    elif jobs_readiness.get("gate_met"):
        recommended_phase = "phase1_jobs_writes"

    target_ready = all(item.get("gate_met") for item in family_readiness if item.get("route_family") in set(target_families)) if target_families else True

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_number": 26,
        "feature_id": "jobs-portal",
        "lookback_hours": lookback_hours,
        "controls": controls,
        "retirement_phase": phase,
        "target_route_families": target_families,
        "target_phase_gate_ready": bool(target_ready),
        "recommended_phase": recommended_phase,
        "family_readiness": family_readiness,
    }


@router.get("/admin/legacy-removal-readiness")
async def hiring_v2_admin_legacy_removal_readiness(
    request: Request,
    mode: str = Query(default="strict_zero", pattern="^(strict_zero|near_zero)$"),
    exclude_synthetic: bool = Query(default=False),
    near_zero_max_events: int = Query(default=5, ge=0, le=10000),
    near_zero_max_active_users: int = Query(default=2, ge=0, le=10000),
):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    safe_mode = str(mode or "strict_zero").strip().lower()
    if safe_mode not in {"strict_zero", "near_zero"}:
        safe_mode = "strict_zero"

    windows_output: list[dict] = []
    failing_windows: list[dict] = []

    def _compact_failing_windows(rows: list[dict]) -> list[dict]:
        return [
            {
                "window_label": item.get("window_label"),
                "lookback_hours": item.get("lookback_hours"),
                "failing_families": [
                    {
                        "route_family": fam.get("route_family"),
                        "total_events": fam.get("total_events"),
                        "active_users": fam.get("active_users"),
                    }
                    for fam in (item.get("family_readiness") or [])
                    if not bool(fam.get("gate_met"))
                ],
            }
            for item in rows
        ]

    for window in LEGACY_REMOVAL_MONITOR_WINDOWS:
        lookback_hours = int(window["hours"])
        jobs_status = await _compute_legacy_removal_window_family_readiness(
            "jobs",
            lookback_hours,
            exclude_synthetic=exclude_synthetic,
            mode=safe_mode,
            near_zero_max_events=near_zero_max_events,
            near_zero_max_active_users=near_zero_max_active_users,
        )
        employers_status = await _compute_legacy_removal_window_family_readiness(
            "employers",
            lookback_hours,
            exclude_synthetic=exclude_synthetic,
            mode=safe_mode,
            near_zero_max_events=near_zero_max_events,
            near_zero_max_active_users=near_zero_max_active_users,
        )

        family_readiness = [jobs_status, employers_status]
        gate_met = all(item.get("gate_met") for item in family_readiness)
        window_row = {
            "window_label": str(window["label"]),
            "lookback_hours": lookback_hours,
            "gate_met": gate_met,
            "family_readiness": family_readiness,
        }
        windows_output.append(window_row)
        if not gate_met:
            failing_windows.append(window_row)

    sustained_gate_met = len(failing_windows) == 0
    controls = await _load_f26_rollout_controls()

    operational_windows_output: list[dict] = []
    operational_failing_windows: list[dict] = []
    if safe_mode == "near_zero" and bool(exclude_synthetic):
        operational_windows_output = windows_output
        operational_failing_windows = failing_windows
    else:
        for window in LEGACY_REMOVAL_MONITOR_WINDOWS:
            lookback_hours = int(window["hours"])
            jobs_status = await _compute_legacy_removal_window_family_readiness(
                "jobs",
                lookback_hours,
                exclude_synthetic=True,
                mode="near_zero",
                near_zero_max_events=near_zero_max_events,
                near_zero_max_active_users=near_zero_max_active_users,
            )
            employers_status = await _compute_legacy_removal_window_family_readiness(
                "employers",
                lookback_hours,
                exclude_synthetic=True,
                mode="near_zero",
                near_zero_max_events=near_zero_max_events,
                near_zero_max_active_users=near_zero_max_active_users,
            )
            family_readiness = [jobs_status, employers_status]
            gate_met = all(item.get("gate_met") for item in family_readiness)
            row = {
                "window_label": str(window["label"]),
                "lookback_hours": lookback_hours,
                "gate_met": gate_met,
                "family_readiness": family_readiness,
            }
            operational_windows_output.append(row)
            if not gate_met:
                operational_failing_windows.append(row)

    operational_sustained_gate_met = len(operational_failing_windows) == 0

    recommendation = (
        "Safe to remove legacy write routes for /api/jobs and /api/employers."
        if sustained_gate_met
        else "Continue monitoring legacy telemetry windows before hard route removal."
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_number": 26,
        "feature_id": "jobs-portal",
        "mode": safe_mode,
        "exclude_synthetic": bool(exclude_synthetic),
        "thresholds": {
            "strict_zero": {"max_events": 0, "max_active_users": 0},
            "near_zero": {
                "max_events": int(near_zero_max_events),
                "max_active_users": int(near_zero_max_active_users),
            },
        },
        "controls_snapshot": {
            "legacy_retirement_enabled": bool(controls.get("legacy_retirement_enabled")),
            "retirement_phase": _normalize_retirement_phase(controls.get("retirement_phase")),
            "retired_legacy_route_families": _target_retired_route_families(controls),
        },
        "sustained_gate_met": sustained_gate_met,
        "ready_for_legacy_code_removal": sustained_gate_met,
        "recommended_action": recommendation,
        "windows": windows_output,
        "failing_windows": _compact_failing_windows(failing_windows),
        "operational_near_zero_excluding_synthetic": {
            "mode": "near_zero",
            "exclude_synthetic": True,
            "sustained_gate_met": operational_sustained_gate_met,
            "ready_for_legacy_code_removal": operational_sustained_gate_met,
            "windows": operational_windows_output,
            "failing_windows": _compact_failing_windows(operational_failing_windows),
        },
        "gate_divergence_detected": bool(operational_sustained_gate_met and not sustained_gate_met),
        "gate_divergence_reason": (
            "Requested gate can remain blocked by strict thresholds and/or synthetic-inclusive telemetry while near_zero + exclude_synthetic signal is ready."
            if operational_sustained_gate_met and not sustained_gate_met
            else "No divergence between requested gate and operational near_zero excluding synthetic signal."
        ),
    }


@router.post("/admin/legacy-retirement-controls")
async def hiring_v2_admin_legacy_retirement_controls(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json()
    current = await _load_f26_rollout_controls()

    enabled = bool(body.get("legacy_retirement_enabled", current.get("legacy_retirement_enabled", False)))
    phase = _normalize_retirement_phase(body.get("retirement_phase", current.get("retirement_phase", "observe")))
    lookback = _clamp_int(body.get("retirement_gate_lookback_hours", current.get("retirement_gate_lookback_hours", 72)), 72, 1, 24 * 30)
    max_events = _clamp_int(body.get("retirement_gate_max_events", current.get("retirement_gate_max_events", 20)), 20, 0, 100000)
    max_active_users = _clamp_int(body.get("retirement_gate_max_active_users", current.get("retirement_gate_max_active_users", 10)), 10, 0, 100000)
    force_apply = bool(body.get("retirement_force_apply", current.get("retirement_force_apply", False)))
    override_user_ids = _parse_simulator_list(body.get("retirement_override_user_ids", current.get("retirement_override_user_ids") or []))

    draft_controls = {
        **current,
        "legacy_retirement_enabled": enabled,
        "retirement_phase": phase,
        "retirement_gate_lookback_hours": lookback,
        "retirement_gate_max_events": max_events,
        "retirement_gate_max_active_users": max_active_users,
        "retirement_force_apply": force_apply,
        "retirement_override_user_ids": override_user_ids,
    }

    target_families = F26_RETIREMENT_PHASE_TO_FAMILIES.get(phase, []) if enabled else []
    jobs_readiness = await _compute_legacy_retirement_gate_status(draft_controls, "jobs", lookback)
    employers_readiness = await _compute_legacy_retirement_gate_status(draft_controls, "employers", lookback)
    family_readiness = [jobs_readiness, employers_readiness]

    unmet_targets = [
        item for item in family_readiness
        if item.get("route_family") in set(target_families) and not bool(item.get("gate_met"))
    ]
    if enabled and target_families and unmet_targets and not force_apply:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Telemetry gate not met for requested retirement phase."
                ,"target_route_families": target_families,
                "unmet_targets": unmet_targets,
                "hint": "Either relax thresholds or set retirement_force_apply=true.",
            },
        )

    updates = {
        "legacy_retirement_enabled": enabled,
        "retirement_phase": phase,
        "retired_legacy_route_families": target_families,
        "retirement_gate_lookback_hours": lookback,
        "retirement_gate_max_events": max_events,
        "retirement_gate_max_active_users": max_active_users,
        "retirement_force_apply": force_apply,
        "retirement_override_user_ids": override_user_ids,
        "retirement_last_gate_snapshot": {
            "jobs": jobs_readiness,
            "employers": employers_readiness,
        },
        "retirement_updated_by": user.user_id,
        "retirement_updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.hiring_v2_rollout_controls.update_one(
        {"key": "feature26_legacy_write_rollout"},
        {
            "$set": updates,
            "$setOnInsert": {
                "key": "feature26_legacy_write_rollout",
                "feature_number": 26,
                "feature_id": "jobs-portal",
            },
        },
        upsert=True,
    )

    return {
        "success": True,
        "feature_number": 26,
        "feature_id": "jobs-portal",
        "controls": {
            **current,
            **updates,
            "key": "feature26_legacy_write_rollout",
            "feature_number": 26,
            "feature_id": "jobs-portal",
        },
        "family_readiness": family_readiness,
    }


@router.post("/admin/canary-controls")
async def hiring_v2_admin_update_canary_controls(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json()
    current = await _load_f26_rollout_controls()

    updates = {
        "canary_enabled": bool(body.get("canary_enabled", current.get("canary_enabled", False))),
        "legacy_allow_pct": max(0, min(int(body.get("legacy_allow_pct", current.get("legacy_allow_pct", 100))), 100)),
        "auto_rollback_enabled": bool(body.get("auto_rollback_enabled", current.get("auto_rollback_enabled", True))),
        "rollback_window_hours": max(1, min(int(body.get("rollback_window_hours", current.get("rollback_window_hours", 6))), 24 * 14)),
        "rollback_legacy_event_threshold": max(1, int(body.get("rollback_legacy_event_threshold", current.get("rollback_legacy_event_threshold", 500)))),
        "soft_disable_operations": sorted(list({str(x) for x in (body.get("soft_disable_operations") or current.get("soft_disable_operations") or []) if str(x).strip()})),
        "admin_override_user_ids": sorted(list({str(x) for x in (body.get("admin_override_user_ids") or current.get("admin_override_user_ids") or []) if str(x).strip()})),
        "updated_by": user.user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Only include non-overlapping fields in $setOnInsert to avoid MongoDB conflict
    set_on_insert_fields = {
        "key": "feature26_legacy_write_rollout",
        "feature_number": 26,
        "feature_id": "jobs-portal",
    }
    await db.hiring_v2_rollout_controls.update_one(
        {"key": "feature26_legacy_write_rollout"},
        {"$set": updates, "$setOnInsert": set_on_insert_fields},
        upsert=True,
    )
    return {
        "success": True,
        "controls": {**current, **updates, "key": "feature26_legacy_write_rollout", "feature_number": 26, "feature_id": "jobs-portal"},
    }


@router.get("/admin/premium-conversion-cohorts")
async def hiring_v2_admin_premium_conversion_cohorts(request: Request, lookback_days: int = Query(default=30, ge=1, le=180)):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    days = max(1, min(lookback_days, 180))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    events = await db.hiring_premium_events.find(
        {"created_at": {"$gte": since_iso}},
        {"_id": 0, "event_type": 1, "user_id": 1, "plan": 1, "created_at": 1},
    ).to_list(5000)

    by_plan: dict[str, dict[str, int]] = {}
    activation_users = set()
    repeat_users = set()
    churn_risk_users = set()
    per_user_counts: dict[str, int] = {}

    for evt in events:
        plan = str(evt.get("plan") or "unknown")
        etype = str(evt.get("event_type") or "unknown")
        uid = str(evt.get("user_id") or "")

        by_plan.setdefault(plan, {"total": 0, "priority_apply": 0, "boosted_profile": 0, "other": 0})
        by_plan[plan]["total"] += 1
        if etype == "priority_apply":
            by_plan[plan]["priority_apply"] += 1
        elif etype == "boosted_profile":
            by_plan[plan]["boosted_profile"] += 1
        else:
            by_plan[plan]["other"] += 1

        if uid:
            activation_users.add(uid)
            per_user_counts[uid] = per_user_counts.get(uid, 0) + 1

    for uid, count in per_user_counts.items():
        if count >= 2:
            repeat_users.add(uid)
        if count == 1:
            churn_risk_users.add(uid)

    activation = len(activation_users)
    repeat = len(repeat_users)
    churn_risk = len(churn_risk_users)
    repeat_rate = round((repeat / activation) * 100, 2) if activation else 0.0
    churn_signal = round((churn_risk / activation) * 100, 2) if activation else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "activation_users": activation,
        "repeat_users": repeat,
        "repeat_rate_pct": repeat_rate,
        "churn_signal_users": churn_risk,
        "churn_signal_pct": churn_signal,
        "events_by_plan": by_plan,
        "total_events": len(events),
    }


@router.get("/admin/employer-conversion-funnel")
async def hiring_v2_admin_employer_conversion_funnel(request: Request, lookback_days: int = Query(default=30, ge=1, le=180)):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    days = max(1, min(lookback_days, 180))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    applications = await db.employer_applications.find(
        {
            "$or": [
                {"created_at": {"$gte": since_iso}},
                {"updated_at": {"$gte": since_iso}},
                {"submitted_at": {"$gte": since_iso}},
            ]
        },
        {"_id": 0, "user_id": 1, "employer_id": 1, "status": 1, "created_at": 1, "updated_at": 1},
    ).to_list(5000)

    trial_users: set[str] = set()
    approved_users: set[str] = set()
    for row in applications:
        user_id = str(row.get("user_id") or row.get("employer_id") or "").strip()
        if not user_id:
            continue
        trial_users.add(user_id)
        if str(row.get("status") or "").lower() in {"approved", "active"}:
            approved_users.add(user_id)

    hired_users: set[str] = set()
    if "employer_offer_letters" in (await db.list_collection_names()):
        offers = await db.employer_offer_letters.find(
            {
                "$or": [
                    {"accepted_at": {"$gte": since_iso}},
                    {"updated_at": {"$gte": since_iso}},
                    {"created_at": {"$gte": since_iso}},
                ]
            },
            {"_id": 0, "employer_id": 1, "employer_user_id": 1, "status": 1},
        ).to_list(5000)
        for row in offers:
            status = str(row.get("status") or "").lower()
            if status not in {"accepted", "hired", "signed"}:
                continue
            uid = str(row.get("employer_user_id") or row.get("employer_id") or "").strip()
            if uid:
                hired_users.add(uid)

    trial = len(trial_users)
    approved = len(approved_users)
    first_hire = len(hired_users)

    approved_rate = round((approved / trial) * 100, 2) if trial else 0.0
    first_hire_rate = round((first_hire / approved) * 100, 2) if approved else 0.0
    overall_rate = round((first_hire / trial) * 100, 2) if trial else 0.0

    dropoff_trial_to_approved = max(0, trial - approved)
    dropoff_approved_to_hire = max(0, approved - first_hire)

    insights = []
    if trial == 0:
        insights.append("No employer trials entered the funnel in the selected window.")
    else:
        insights.append(f"{approved_rate}% of trial employers reached approved status.")
        insights.append(f"{first_hire_rate}% of approved employers reached first-hire milestone.")
    if dropoff_trial_to_approved > 0:
        insights.append(f"{dropoff_trial_to_approved} employers dropped before approval; prioritize onboarding acceleration.")
    if dropoff_approved_to_hire > 0:
        insights.append(f"{dropoff_approved_to_hire} approved employers have not reached first hire yet.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": days,
        "funnel": {
            "trial_started": trial,
            "approved_employer": approved,
            "first_hire": first_hire,
        },
        "conversion_rates_pct": {
            "trial_to_approved": approved_rate,
            "approved_to_first_hire": first_hire_rate,
            "trial_to_first_hire": overall_rate,
        },
        "dropoff": {
            "trial_to_approved": dropoff_trial_to_approved,
            "approved_to_first_hire": dropoff_approved_to_hire,
        },
        "insights": insights,
    }
