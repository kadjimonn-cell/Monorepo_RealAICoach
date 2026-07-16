"""Feature 26 Phase-2 advanced employer pipeline read services."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import uuid

from fastapi import HTTPException, Response

from .db import db
from .jobs_employer_console_exports import (
    build_audit_download_signature,
    collect_application_audit_rows,
    filter_audit_rows_by_range,
    render_application_audit_csv,
    render_application_audit_pdf,
    resolve_audit_date_range,
)
from .jobs_employer_console_sla import build_sla_auto_trigger_items
from .jobs_shared import (
    PIPELINE_STAGE_ORDER,
    PIPELINE_STAGES,
    build_copilot_actions,
    compute_candidate_match,
    get_owned_application_for_employer,
    normalize_pipeline_status,
    safe_days_since,
    stage_target_days,
)
from utils.pdf_v15_filename import build_pdf_v15_filename


async def get_employer_pipeline_board_read(user: Any, limit: int = 300) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    jobs = await db.jobs.find(
        {"poster_user_id": user.user_id},
        {"_id": 0, "job_id": 1, "title": 1, "company_name": 1, "location": 1},
    ).to_list(500)
    jobs_by_id = {job.get("job_id"): job for job in jobs if job.get("job_id")}
    job_ids = list(jobs_by_id.keys())

    apps = await db.job_applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0},
    ).sort("updated_at", -1).limit(safe_limit).to_list(safe_limit)

    if not apps:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stages": PIPELINE_STAGES,
            "counts": {stage: 0 for stage in PIPELINE_STAGES},
            "jobs": jobs,
            "applications": [],
            "total": 0,
        }

    candidate_ids = list({app.get("candidate_id") or app.get("user_id") for app in apps if (app.get("candidate_id") or app.get("user_id"))})
    users = await db.users.find({"user_id": {"$in": candidate_ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(len(candidate_ids) or 1)
    profiles = await db.employee_profiles.find({"user_id": {"$in": candidate_ids}}, {"_id": 0, "user_id": 1, "skills": 1, "resume_score": 1}).to_list(len(candidate_ids) or 1)
    users_by_id = {u.get("user_id"): u for u in users if u.get("user_id")}
    profiles_by_id = {p.get("user_id"): p for p in profiles if p.get("user_id")}

    application_ids = [a.get("application_id") for a in apps if a.get("application_id")]
    interview_rows = await db.interview_bookings.find(
        {"application_id": {"$in": application_ids}},
        {"_id": 0, "application_id": 1, "interview_id": 1, "status": 1, "interview_type": 1, "scheduled_start": 1, "timezone": 1, "meeting_link": 1, "updated_at": 1, "created_at": 1},
    ).sort("scheduled_start", -1).to_list(1000)
    latest_interview_by_application: Dict[str, Dict[str, Any]] = {}
    for row in interview_rows:
        app_id = row.get("application_id")
        if not app_id or app_id in latest_interview_by_application:
            continue
        latest_interview_by_application[app_id] = row

    timeline_rows = await db.job_application_timeline_events.find(
        {"application_id": {"$in": application_ids}},
        {"_id": 0},
    ).sort("created_at", -1).limit(min(safe_limit * 5, 2500)).to_list(min(safe_limit * 5, 2500))
    timeline_preview: Dict[str, List[Dict[str, Any]]] = {}
    for row in timeline_rows:
        app_id = row.get("application_id")
        if not app_id:
            continue
        timeline_preview.setdefault(app_id, [])
        if len(timeline_preview[app_id]) < 4:
            timeline_preview[app_id].append(row)

    items: List[Dict[str, Any]] = []
    counts = {stage: 0 for stage in PIPELINE_STAGES}
    sla_by_stage = {stage: 0 for stage in PIPELINE_STAGES}
    sla_alert_items: List[Dict[str, Any]] = []
    for app in apps:
        app_id = app.get("application_id")
        job_id = app.get("job_id")
        stage = normalize_pipeline_status(app.get("status"))
        counts[stage] = counts.get(stage, 0) + 1
        candidate_id = app.get("candidate_id") or app.get("user_id")
        user_doc = users_by_id.get(candidate_id, {})
        profile_doc = profiles_by_id.get(candidate_id, {})
        job_doc = jobs_by_id.get(job_id, {})
        match = compute_candidate_match(job_doc=job_doc, application_doc=app, profile_doc=profile_doc)
        age_days = safe_days_since(app.get("updated_at") or app.get("created_at"))
        target_days = stage_target_days(stage)
        sla_breached = target_days < 900 and age_days > target_days
        if sla_breached:
            sla_by_stage[stage] = sla_by_stage.get(stage, 0) + 1
            sla_alert_items.append({
                "application_id": app_id,
                "candidate_name": app.get("candidate_name") or user_doc.get("name") or "Candidate",
                "job_title": job_doc.get("title") or app.get("job_title") or "Untitled Role",
                "status": stage,
                "age_days": age_days,
                "target_days": target_days,
            })

        latest_interview = latest_interview_by_application.get(app_id)
        copilot_actions = build_copilot_actions(
            stage=stage,
            sla_breached=sla_breached,
            match_score=match.get("match_score", 0),
            has_interview=bool(latest_interview and latest_interview.get("interview_id")),
        )

        items.append(
            {
                "application_id": app_id,
                "job_id": job_id,
                "job_title": job_doc.get("title") or app.get("job_title") or "Untitled Role",
                "company_name": job_doc.get("company_name") or app.get("company_name") or "",
                "location": job_doc.get("location") or "",
                "candidate_id": candidate_id,
                "candidate_name": app.get("candidate_name") or user_doc.get("name") or "Candidate",
                "candidate_email": app.get("candidate_email") or user_doc.get("email") or "",
                "status": stage,
                "stage_rank": PIPELINE_STAGE_ORDER.get(stage, 0),
                "cover_letter": app.get("cover_letter") or "",
                "skills": app.get("skills") or profile_doc.get("skills") or [],
                "resume_score": profile_doc.get("resume_score") or 0,
                "applied_at": app.get("applied_at") or app.get("created_at"),
                "updated_at": app.get("updated_at") or app.get("created_at"),
                "latest_interview": latest_interview,
                "timeline_preview": timeline_preview.get(app_id, []),
                "match_score": match.get("match_score", 0),
                "match_tier": match.get("match_tier", "low"),
                "match_reasons": match.get("match_reasons", []),
                "sla_age_days": age_days,
                "sla_target_days": target_days,
                "sla_breached": sla_breached,
                "copilot_actions": copilot_actions,
            }
        )

    items.sort(key=lambda row: (PIPELINE_STAGE_ORDER.get(row.get("status", "applied"), 0), str(row.get("updated_at") or "")), reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stages": PIPELINE_STAGES,
        "counts": counts,
        "sla_alerts": {"overdue_total": int(sum(sla_by_stage.values())), "overdue_by_stage": sla_by_stage, "items": sla_alert_items[:25]},
        "jobs": jobs,
        "applications": items,
        "total": len(items),
    }


async def get_employer_pipeline_timeline_read(user: Any, application_id: str, limit: int = 150) -> Dict[str, Any]:
    safe_limit = max(10, min(limit, 400))
    app = await db.job_applications.find_one({"application_id": application_id}, {"_id": 0})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    job_id = app.get("job_id")
    job = await db.jobs.find_one({"job_id": job_id, "poster_user_id": user.user_id}, {"_id": 0, "job_id": 1, "title": 1, "company_name": 1})
    if not job:
        raise HTTPException(status_code=403, detail="Not authorized for this application")

    base_events = await db.job_application_timeline_events.find({"application_id": application_id}, {"_id": 0}).sort("created_at", -1).limit(safe_limit).to_list(safe_limit)
    interviews = await db.interview_bookings.find(
        {"application_id": application_id},
        {"_id": 0, "interview_id": 1, "status": 1, "interview_type": 1, "scheduled_start": 1, "scheduled_end": 1, "timezone": 1, "meeting_link": 1, "created_at": 1, "updated_at": 1},
    ).sort("scheduled_start", -1).to_list(100)

    interview_ids = [i.get("interview_id") for i in interviews if i.get("interview_id")]
    activity_rows = await db.interview_activity_log.find({"interview_id": {"$in": interview_ids}}, {"_id": 0}).sort("timestamp", -1).to_list(300) if interview_ids else []
    interview_events: List[Dict[str, Any]] = []

    for interview in interviews:
        interview_id = interview.get("interview_id")
        interview_events.append(
            {
                "event_id": f"iv_{interview_id}_scheduled",
                "application_id": application_id,
                "job_id": job_id,
                "event_type": "interview_scheduled",
                "title": "Interview Scheduled",
                "description": f"{str(interview.get('interview_type') or 'interview').title()} interview scheduled.",
                "status": app.get("status"),
                "metadata": {
                    "interview_id": interview_id,
                    "interview_status": interview.get("status"),
                    "scheduled_start": interview.get("scheduled_start"),
                    "scheduled_end": interview.get("scheduled_end"),
                    "timezone": interview.get("timezone"),
                    "meeting_link": interview.get("meeting_link"),
                },
                "created_at": interview.get("created_at") or interview.get("scheduled_start") or interview.get("updated_at"),
            }
        )

    action_titles = {
        "scheduled": "Interview Scheduled",
        "confirmed": "Interview Confirmed",
        "declined": "Interview Declined",
        "reschedule_requested": "Interview Reschedule Requested",
        "rescheduled": "Interview Rescheduled",
        "cancelled": "Interview Cancelled",
        "completed": "Interview Completed",
        "candidate_rejected": "Candidate Rejected",
        "stage_moved": "Hiring Stage Updated",
    }
    for row in activity_rows:
        action = str(row.get("action") or "activity")
        interview_events.append(
            {
                "event_id": row.get("log_id") or f"ivlog_{uuid.uuid4().hex[:10]}",
                "application_id": application_id,
                "job_id": job_id,
                "event_type": f"interview_{action}",
                "title": action_titles.get(action, "Interview Activity"),
                "description": row.get("details") or action.replace("_", " "),
                "status": app.get("status"),
                "metadata": {"interview_id": row.get("interview_id"), "action": action, "actor_id": row.get("actor_id")},
                "created_at": row.get("timestamp"),
            }
        )

    merged_events = [*base_events, *interview_events]
    merged_events.sort(key=lambda e: str(e.get("created_at") or ""), reverse=True)
    candidate_id = app.get("candidate_id") or app.get("user_id")
    candidate_user = await db.users.find_one({"user_id": candidate_id}, {"_id": 0, "name": 1, "email": 1}) or {}
    return {
        "application_id": application_id,
        "job": job,
        "candidate": {
            "candidate_id": candidate_id,
            "name": app.get("candidate_name") or candidate_user.get("name") or "Candidate",
            "email": app.get("candidate_email") or candidate_user.get("email") or "",
        },
        "current_status": normalize_pipeline_status(app.get("status")),
        "events": merged_events[:safe_limit],
        "total": len(merged_events),
    }


async def list_employer_offers_read(user: Any, application_id: Optional[str] = None, limit: int = 120) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 300))
    jobs = await db.jobs.find({"poster_user_id": user.user_id}, {"_id": 0, "job_id": 1}).to_list(400)
    job_ids = [j.get("job_id") for j in jobs if j.get("job_id")]
    query: Dict[str, Any] = {"job_id": {"$in": job_ids}}
    if application_id:
        query["application_id"] = application_id
    offers = await db.employer_offer_letters.find(query, {"_id": 0}).sort("created_at", -1).limit(safe_limit).to_list(safe_limit)
    return {"offers": offers, "total": len(offers)}


async def get_employer_sla_alerts_read(user: Any, limit: int = 120) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    jobs = await db.jobs.find({"poster_user_id": user.user_id}, {"_id": 0, "job_id": 1, "title": 1}).to_list(500)
    jobs_by_id = {j.get("job_id"): j for j in jobs if j.get("job_id")}
    job_ids = list(jobs_by_id.keys())
    apps = await db.job_applications.find(
        {"job_id": {"$in": job_ids}},
        {"_id": 0, "application_id": 1, "job_id": 1, "candidate_name": 1, "status": 1, "updated_at": 1, "created_at": 1},
    ).sort("updated_at", -1).limit(safe_limit).to_list(safe_limit)

    overdue_items: List[Dict[str, Any]] = []
    by_stage = {stage: 0 for stage in PIPELINE_STAGES}
    for app in apps:
        stage = normalize_pipeline_status(app.get("status"))
        age_days = safe_days_since(app.get("updated_at") or app.get("created_at"))
        target = stage_target_days(stage)
        if target < 900 and age_days > target:
            by_stage[stage] = by_stage.get(stage, 0) + 1
            overdue_items.append(
                {
                    "application_id": app.get("application_id"),
                    "candidate_name": app.get("candidate_name") or "Candidate",
                    "job_title": jobs_by_id.get(app.get("job_id"), {}).get("title") or "Untitled Role",
                    "status": stage,
                    "age_days": age_days,
                    "target_days": target,
                }
            )

    bottlenecks = sorted(
        [{"stage": stage, "overdue_count": count} for stage, count in by_stage.items() if count > 0 and stage not in {"hired", "rejected"}],
        key=lambda row: row["overdue_count"],
        reverse=True,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds_days": {"applied": 3, "viewed": 2, "interview": 5, "offer": 4},
        "overdue_total": len(overdue_items),
        "overdue_by_stage": by_stage,
        "bottlenecks": bottlenecks,
        "items": overdue_items[:40],
    }


async def get_employer_sla_auto_triggers_read(user: Any, application_id: Optional[str] = None, limit: int = 12) -> Dict[str, Any]:
    items = await build_sla_auto_trigger_items(user, application_id=application_id, limit=limit)
    summary = {
        "pending_total": sum(1 for row in items if row.get("status") == "pending"),
        "cooldown_total": sum(1 for row in items if row.get("status") == "cooldown_active"),
        "by_action": {},
    }
    for item in items:
        action_key = str(item.get("trigger_action") or "unknown")
        summary["by_action"][action_key] = summary["by_action"].get(action_key, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "application_id": application_id,
        "summary": summary,
        "items": items,
        "total": len(items),
    }


async def get_employer_kpi_header_read(user: Any, window_days: int = 30) -> Dict[str, Any]:
    safe_window = max(1, min(window_days, 365))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=safe_window)).isoformat()
    jobs = await db.jobs.find({"poster_user_id": user.user_id}, {"_id": 0, "job_id": 1, "title": 1}).to_list(600)
    job_ids = [job.get("job_id") for job in jobs if job.get("job_id")]
    if not job_ids:
        return {
            "window_days": safe_window,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "kpis": {"time_to_hire_days": 0.0, "stage_conversion_pct": 0.0, "offer_acceptance_pct": 0.0, "active_bottlenecks": 0},
            "counts": {"total_applications": 0, "progressed_applications": 0, "offers_sent": 0, "offers_accepted": 0},
        }

    apps = await db.job_applications.find(
        {"job_id": {"$in": job_ids}, "created_at": {"$gte": since_iso}},
        {"_id": 0, "application_id": 1, "status": 1, "created_at": 1, "updated_at": 1},
    ).to_list(2000)

    total_apps = len(apps)
    progressed = 0
    hired_durations: List[float] = []
    active_bottlenecks = 0
    for app in apps:
        stage = normalize_pipeline_status(app.get("status"))
        if stage != "applied":
            progressed += 1
        if stage == "hired":
            try:
                start_dt = datetime.fromisoformat(str(app.get("created_at")).replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(str(app.get("updated_at") or app.get("created_at")).replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                hired_durations.append(max(0.0, (end_dt - start_dt).total_seconds() / 86400.0))
            except Exception:
                pass
        age_days = safe_days_since(app.get("updated_at") or app.get("created_at"))
        target = stage_target_days(stage)
        if stage not in {"hired", "rejected"} and target < 900 and age_days > target:
            active_bottlenecks += 1

    offers = await db.employer_offer_letters.find(
        {"job_id": {"$in": job_ids}, "sent_at": {"$gte": since_iso}},
        {"_id": 0, "status": 1, "decision": 1, "sent_at": 1},
    ).to_list(2000)
    offers_sent = len(offers)
    offers_accepted = sum(1 for offer in offers if str(offer.get("decision") or "").lower() == "accept" or str(offer.get("status") or "").lower() == "accepted")
    stage_conversion_pct = round((progressed / total_apps) * 100, 1) if total_apps else 0.0
    offer_acceptance_pct = round((offers_accepted / offers_sent) * 100, 1) if offers_sent else 0.0
    time_to_hire_days = round(sum(hired_durations) / len(hired_durations), 1) if hired_durations else 0.0
    return {
        "window_days": safe_window,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kpis": {
            "time_to_hire_days": time_to_hire_days,
            "stage_conversion_pct": stage_conversion_pct,
            "offer_acceptance_pct": offer_acceptance_pct,
            "active_bottlenecks": int(active_bottlenecks),
        },
        "counts": {
            "total_applications": int(total_apps),
            "progressed_applications": int(progressed),
            "offers_sent": int(offers_sent),
            "offers_accepted": int(offers_accepted),
        },
    }


async def get_recruiter_copilot_suggestions_read(user: Any, application_id: str) -> Dict[str, Any]:
    owned = await get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]
    profile = await db.employee_profiles.find_one({"user_id": app.get("candidate_id") or app.get("user_id")}, {"_id": 0, "skills": 1, "resume_score": 1, "experience_years": 1}) or {}
    match = compute_candidate_match(job_doc=job, application_doc=app, profile_doc=profile)
    stage = normalize_pipeline_status(app.get("status"))
    age_days = safe_days_since(app.get("updated_at") or app.get("created_at"))
    sla_target = stage_target_days(stage)
    has_interview = bool(await db.interview_bookings.find_one({"application_id": application_id}, {"_id": 0, "interview_id": 1}))
    actions = build_copilot_actions(stage=stage, sla_breached=sla_target < 900 and age_days > sla_target, match_score=match.get("match_score", 0), has_interview=has_interview)
    rationale = f"Candidate is in '{stage}' stage for {age_days} day(s); match score {match.get('match_score', 0)}. Prioritize high-confidence next steps to reduce pipeline delay."
    return {
        "application_id": application_id,
        "current_stage": stage,
        "match_score": match.get("match_score", 0),
        "match_reasons": match.get("match_reasons", []),
        "sla_age_days": age_days,
        "sla_target_days": sla_target,
        "actions": actions,
        "rationale": rationale,
    }


async def get_interview_scorecards_read(user: Any, application_id: str) -> Dict[str, Any]:
    owned = await get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    scorecards = await db.interview_scorecards.find({"application_id": application_id}, {"_id": 0}).sort("created_at", -1).to_list(120)
    panel_debrief = await db.interview_panel_debriefs.find_one({"application_id": application_id}, {"_id": 0}) or {}
    avg_overall = round(sum(float(s.get("overall_score") or 0) for s in scorecards) / max(len(scorecards), 1), 2) if scorecards else 0.0
    return {
        "application_id": application_id,
        "candidate_name": app.get("candidate_name") or "Candidate",
        "scorecards": scorecards,
        "summary": {
            "count": len(scorecards),
            "average_overall_score": avg_overall,
            "latest_recommendation": scorecards[0].get("recommendation") if scorecards else None,
        },
        "panel_debrief": panel_debrief,
    }


async def suggest_auto_scheduler_slots_read(user: Any, application_id: str, days_ahead: int = 7, duration_minutes: int = 45) -> Dict[str, Any]:
    owned = await get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    from .smart_scheduler import _find_available_slots, _get_user_busy_slots

    candidate_id = app.get("candidate_id") or app.get("user_id")
    if not candidate_id:
        raise HTTPException(status_code=400, detail="Candidate unavailable for scheduling")

    safe_days = max(3, min(int(days_ahead), 21))
    safe_duration = max(20, min(int(duration_minutes), 120))
    now = datetime.now(timezone.utc)
    start_date_str = now.isoformat()
    end_date_str = (now + timedelta(days=safe_days)).isoformat()
    employer_busy = await _get_user_busy_slots(user.user_id, start_date_str, end_date_str)
    candidate_busy = await _get_user_busy_slots(candidate_id, start_date_str, end_date_str)
    slots = _find_available_slots(employer_busy, candidate_busy, now, safe_days, 9, 18, safe_duration)
    for idx, slot in enumerate(slots):
        slot["rank"] = idx + 1
        slot["ai_recommended"] = idx == 0
    return {
        "application_id": application_id,
        "candidate_id": candidate_id,
        "total": len(slots),
        "duration_minutes": safe_duration,
        "slots": slots[:10],
        "insight": "Top slots prioritize low-conflict windows for both interviewer and candidate.",
    }


async def get_communication_sequence_read(user: Any, application_id: str) -> Dict[str, Any]:
    await get_owned_application_for_employer(user, application_id)
    sequence = await db.employer_candidate_communication_sequences.find_one({"application_id": application_id, "employer_user_id": user.user_id}, {"_id": 0})
    return {"sequence": sequence or None}


async def get_employer_hiring_forecast_read(user: Any, window_days: int = 45) -> Dict[str, Any]:
    safe_window = max(14, min(window_days, 180))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=safe_window)).isoformat()
    jobs = await db.jobs.find({"poster_user_id": user.user_id}, {"_id": 0, "job_id": 1, "title": 1}).to_list(800)
    job_ids = [job.get("job_id") for job in jobs if job.get("job_id")]
    if not job_ids:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_days": safe_window,
            "forecast": {"predicted_days_to_fill": 0, "predicted_hires_next_30_days": 0, "risk_level": "low", "confidence": 0.0},
            "bottlenecks": [],
            "stage_velocity_days": {},
            "recommendations": [],
        }

    apps = await db.job_applications.find(
        {"job_id": {"$in": job_ids}, "created_at": {"$gte": since_iso}},
        {"_id": 0, "application_id": 1, "status": 1, "created_at": 1, "updated_at": 1},
    ).to_list(4000)

    stage_counts = {stage: 0 for stage in PIPELINE_STAGES}
    stage_ages: Dict[str, List[int]] = {stage: [] for stage in PIPELINE_STAGES}
    bottlenecks: List[Dict[str, Any]] = []
    hired_count = 0
    for app in apps:
        stage = normalize_pipeline_status(app.get("status"))
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        age_days = safe_days_since(app.get("updated_at") or app.get("created_at"))
        stage_ages.setdefault(stage, []).append(age_days)
        target_days = stage_target_days(stage)
        if stage not in {"hired", "rejected"} and target_days < 900 and age_days > target_days:
            bottlenecks.append({"application_id": app.get("application_id"), "stage": stage, "age_days": age_days, "target_days": target_days})
        if stage == "hired":
            hired_count += 1

    stage_velocity_days = {stage: round(sum(days) / max(len(days), 1), 1) if days else 0.0 for stage, days in stage_ages.items()}
    default_remaining = {"applied": 12.0, "viewed": 9.0, "interview": 6.0, "offer": 3.0, "hired": 0.0, "rejected": 0.0}
    active_apps = [a for a in apps if normalize_pipeline_status(a.get("status")) not in {"hired", "rejected"}]
    remaining_days = [max(1.0, default_remaining.get(normalize_pipeline_status(a.get("status")), 8.0)) for a in active_apps]
    predicted_days_to_fill = round(sum(remaining_days) / max(len(remaining_days), 1), 1) if remaining_days else 0.0
    total_apps = len(apps)
    hire_rate = hired_count / max(total_apps, 1)
    predicted_hires_next_30 = int(round(max(0.0, len(active_apps) * hire_rate * 0.6)))
    bottleneck_ratio = len(bottlenecks) / max(len(active_apps), 1) if active_apps else 0.0
    risk_level = "high" if bottleneck_ratio > 0.45 else "medium" if bottleneck_ratio > 0.2 else "low"
    confidence = round(min(0.95, 0.35 + (total_apps / 120.0)), 2)
    recommendations: List[str] = []
    if stage_counts.get("applied", 0) > stage_counts.get("viewed", 0) * 2:
        recommendations.append("Review inbox SLAs daily; applied-stage buildup is slowing pipeline throughput.")
    if stage_counts.get("interview", 0) > 0 and stage_velocity_days.get("interview", 0) > 6:
        recommendations.append("Use auto-scheduling orchestrator to reduce interview coordination delays.")
    if stage_counts.get("offer", 0) > 0 and stage_velocity_days.get("offer", 0) > 4:
        recommendations.append("Trigger offer follow-up sequences to improve acceptance speed.")
    if not recommendations:
        recommendations.append("Pipeline health is stable. Keep interview and offer SLAs under current thresholds.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": safe_window,
        "counts": {
            "total_applications": total_apps,
            "active_applications": len(active_apps),
            "hired_applications": hired_count,
            "bottleneck_items": len(bottlenecks),
            "stage_counts": stage_counts,
        },
        "forecast": {
            "predicted_days_to_fill": predicted_days_to_fill,
            "predicted_hires_next_30_days": predicted_hires_next_30,
            "risk_level": risk_level,
            "confidence": confidence,
        },
        "stage_velocity_days": stage_velocity_days,
        "bottlenecks": bottlenecks[:20],
        "recommendations": recommendations,
    }


async def get_talent_rediscovery_candidates_read(user: Any, job_id: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 50))
    jobs = await db.jobs.find({"poster_user_id": user.user_id}, {"_id": 0, "job_id": 1, "title": 1, "skills": 1, "location": 1, "remote": 1, "experience_years": 1}).to_list(800)
    jobs_by_id = {j.get("job_id"): j for j in jobs if j.get("job_id")}
    if not jobs_by_id:
        return {"target_job": None, "candidates": [], "total": 0}

    target_job_id = job_id or next(iter(jobs_by_id.keys()))
    if target_job_id not in jobs_by_id:
        raise HTTPException(status_code=404, detail="Target job not found")
    target_job = jobs_by_id[target_job_id]

    historical_apps = await db.job_applications.find(
        {"job_id": {"$in": list(jobs_by_id.keys())}, "status": {"$in": ["interview", "offer", "rejected"]}},
        {"_id": 0, "application_id": 1, "job_id": 1, "status": 1, "candidate_id": 1, "user_id": 1, "candidate_name": 1, "candidate_email": 1, "skills": 1, "updated_at": 1, "created_at": 1},
    ).sort("updated_at", -1).to_list(3000)

    latest_per_candidate: Dict[str, Dict[str, Any]] = {}
    for app in historical_apps:
        candidate_id = app.get("candidate_id") or app.get("user_id")
        if candidate_id and candidate_id not in latest_per_candidate:
            latest_per_candidate[candidate_id] = app

    candidate_ids = list(latest_per_candidate.keys())
    profiles = await db.employee_profiles.find({"user_id": {"$in": candidate_ids}}, {"_id": 0, "user_id": 1, "skills": 1, "resume_score": 1, "experience_years": 1, "preferred_location": 1, "remote_only": 1}).to_list(len(candidate_ids) or 1)
    profiles_by_id = {p.get("user_id"): p for p in profiles if p.get("user_id")}
    users = await db.users.find({"user_id": {"$in": candidate_ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(len(candidate_ids) or 1)
    users_by_id = {u.get("user_id"): u for u in users if u.get("user_id")}

    rediscovered: List[Dict[str, Any]] = []
    for candidate_id, app in latest_per_candidate.items():
        profile = profiles_by_id.get(candidate_id, {})
        user_doc = users_by_id.get(candidate_id, {})
        match = compute_candidate_match(job_doc=target_job, application_doc=app, profile_doc=profile)
        if int(match.get("match_score") or 0) < 55:
            continue
        rediscovered.append(
            {
                "candidate_id": candidate_id,
                "candidate_name": app.get("candidate_name") or user_doc.get("name") or "Candidate",
                "candidate_email": app.get("candidate_email") or user_doc.get("email") or "",
                "previous_application_id": app.get("application_id"),
                "previous_job_id": app.get("job_id"),
                "previous_stage": normalize_pipeline_status(app.get("status")),
                "last_seen_at": app.get("updated_at") or app.get("created_at"),
                "match_score": int(match.get("match_score") or 0),
                "match_reasons": match.get("match_reasons") or [],
            }
        )

    rediscovered.sort(key=lambda row: (int(row.get("match_score") or 0), str(row.get("last_seen_at") or "")), reverse=True)
    return {"target_job": {"job_id": target_job_id, "title": target_job.get("title") or ""}, "candidates": rediscovered[:safe_limit], "total": len(rediscovered)}


async def export_pipeline_audit_csv_read(
    user: Any,
    application_id: str,
    range_key: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Response:
    owned = await get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]
    rows = await collect_application_audit_rows(application_id)
    start_dt, end_dt, range_label = resolve_audit_date_range(range_key, start_date, end_date)
    filtered_rows = filter_audit_rows_by_range(rows, start_dt, end_dt)
    created_at = datetime.now(timezone.utc).isoformat()
    signature = build_audit_download_signature(application_id=application_id, exporter_user_id=user.user_id, export_format="csv", range_label=range_label, row_count=len(filtered_rows), created_at=created_at)
    await db.employer_audit_export_history.insert_one(
        {
            "export_id": f"audexp_{uuid.uuid4().hex[:12]}",
            "application_id": application_id,
            "job_id": job.get("job_id") or "",
            "job_title": job.get("title") or "",
            "candidate_name": app.get("candidate_name") or "Candidate",
            "format": "csv",
            "range_key": range_key,
            "range_label": range_label,
            "start_at": start_dt.isoformat() if start_dt else None,
            "end_at": end_dt.isoformat() if end_dt else None,
            "row_count": len(filtered_rows),
            "signature_id": signature["signature_id"],
            "signature": signature["signature"],
            "exported_by_user_id": user.user_id,
            "exported_by_name": user.name or user.email or "Recruiter",
            "created_at": created_at,
        }
    )
    filename = build_pdf_v15_filename("hiring-audit", application_id).replace(".pdf", ".csv")
    return Response(
        content=render_application_audit_csv(filtered_rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Audit-Signature-Id": signature["signature_id"],
            "X-Audit-Signature": signature["signature"],
            "X-Audit-Range": range_label,
        },
    )


async def export_pipeline_audit_pdf_read(
    user: Any,
    application_id: str,
    range_key: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Response:
    owned = await get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]
    rows = await collect_application_audit_rows(application_id)
    start_dt, end_dt, range_label = resolve_audit_date_range(range_key, start_date, end_date)
    filtered_rows = filter_audit_rows_by_range(rows, start_dt, end_dt)
    created_at = datetime.now(timezone.utc).isoformat()
    signature = build_audit_download_signature(application_id=application_id, exporter_user_id=user.user_id, export_format="pdf", range_label=range_label, row_count=len(filtered_rows), created_at=created_at)
    await db.employer_audit_export_history.insert_one(
        {
            "export_id": f"audexp_{uuid.uuid4().hex[:12]}",
            "application_id": application_id,
            "job_id": job.get("job_id") or "",
            "job_title": job.get("title") or "",
            "candidate_name": app.get("candidate_name") or "Candidate",
            "format": "pdf",
            "range_key": range_key,
            "range_label": range_label,
            "start_at": start_dt.isoformat() if start_dt else None,
            "end_at": end_dt.isoformat() if end_dt else None,
            "row_count": len(filtered_rows),
            "signature_id": signature["signature_id"],
            "signature": signature["signature"],
            "exported_by_user_id": user.user_id,
            "exported_by_name": user.name or user.email or "Recruiter",
            "created_at": created_at,
        }
    )
    filename = build_pdf_v15_filename("hiring-audit", application_id)
    return Response(
        content=render_application_audit_pdf(
            rows=filtered_rows,
            candidate_name=app.get("candidate_name") or "Candidate",
            job_title=job.get("title") or "Selected Role",
            exported_by=user.name or user.email or "Recruiter",
        ),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Audit-Signature-Id": signature["signature_id"],
            "X-Audit-Signature": signature["signature"],
            "X-Audit-Range": range_label,
        },
    )


async def get_pipeline_audit_download_history_read(user: Any, application_id: str, limit: int = 8) -> Dict[str, Any]:
    await get_owned_application_for_employer(user, application_id)
    safe_limit = max(1, min(limit, 20))
    entries = await db.employer_audit_export_history.find(
        {"application_id": application_id, "exported_by_user_id": user.user_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(safe_limit).to_list(safe_limit)
    return {
        "application_id": application_id,
        "entries": entries,
        "total": len(entries),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
