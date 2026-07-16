"""SLA auto-trigger helpers for the employer console."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import logging
import uuid

from fastapi import HTTPException

from .db import User, db
from .jobs_shared import (
    append_application_timeline_event,
    compute_candidate_match,
    get_owned_application_for_employer,
    normalize_pipeline_status,
    safe_days_since,
    send_candidate_followup_email,
    send_candidate_notification_with_optional_email,
    stage_target_days,
)

logger = logging.getLogger("routes.jobs.sla")


async def compute_slot_suggestions_for_candidate(employer_user_id: str, candidate_user_id: str) -> List[Dict[str, Any]]:
    if not employer_user_id or not candidate_user_id:
        return []
    try:
        from .smart_scheduler import _find_available_slots, _get_user_busy_slots

        now = datetime.now(timezone.utc)
        start_date_str = now.isoformat()
        end_date_str = (now + timedelta(days=7)).isoformat()
        employer_busy = await _get_user_busy_slots(employer_user_id, start_date_str, end_date_str)
        candidate_busy = await _get_user_busy_slots(candidate_user_id, start_date_str, end_date_str)
        return list(_find_available_slots(employer_busy, candidate_busy, now, 7, 9, 18, 45)[:3])
    except Exception as exc:
        logger.warning("slot suggestion preview failed: %s", exc)
        return []


def determine_sla_auto_trigger(*, stage: str, age_days: int, target_days: int, match_score: int) -> Dict[str, Any] | None:
    overdue_by = max(0, age_days - target_days)
    if stage in {"hired", "rejected"} or target_days >= 900 or overdue_by <= 0:
        return None
    if stage == "interview":
        return {
            "trigger_action": "open_slot_suggestion",
            "trigger_label": "Auto-open slot suggestion",
            "reason": "Interview stage is beyond SLA; send fresh booking windows automatically.",
        }
    if stage == "viewed" and match_score >= 70 and overdue_by >= 2:
        return {
            "trigger_action": "rediscovery",
            "trigger_label": "Auto-rediscovery outreach",
            "reason": "High-match candidate stalled in review; reopen the conversation proactively.",
        }
    return {
        "trigger_action": "send_followup",
        "trigger_label": "Auto-send follow-up",
        "reason": "Candidate is stalled beyond SLA and needs a recruiter nudge.",
    }


async def build_sla_auto_trigger_items(
    user: User,
    *,
    application_id: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(limit, 30))
    jobs = await db.jobs.find(
        {"poster_user_id": user.user_id},
        {"_id": 0, "job_id": 1, "title": 1, "company_name": 1, "location": 1, "skills": 1, "remote": 1, "experience_years": 1},
    ).to_list(500)
    jobs_by_id = {row.get("job_id"): row for row in jobs if row.get("job_id")}
    job_ids = list(jobs_by_id.keys())
    if not job_ids:
        return []

    query: Dict[str, Any] = {"job_id": {"$in": job_ids}, "status": {"$nin": ["hired"]}}
    if application_id:
        query["application_id"] = application_id

    apps = await db.job_applications.find(
        query,
        {
            "_id": 0,
            "application_id": 1,
            "job_id": 1,
            "user_id": 1,
            "candidate_id": 1,
            "candidate_name": 1,
            "candidate_email": 1,
            "status": 1,
            "skills": 1,
            "updated_at": 1,
            "created_at": 1,
        },
    ).sort("updated_at", 1).limit(300).to_list(300)
    if not apps:
        return []

    candidate_ids = list({app.get("candidate_id") or app.get("user_id") for app in apps if app.get("candidate_id") or app.get("user_id")})
    users = await db.users.find({"user_id": {"$in": candidate_ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(len(candidate_ids) or 1)
    profiles = await db.employee_profiles.find(
        {"user_id": {"$in": candidate_ids}},
        {"_id": 0, "user_id": 1, "skills": 1, "resume_score": 1, "experience_years": 1, "preferred_location": 1, "remote_only": 1},
    ).to_list(len(candidate_ids) or 1)
    users_by_id = {row.get("user_id"): row for row in users if row.get("user_id")}
    profiles_by_id = {row.get("user_id"): row for row in profiles if row.get("user_id")}

    recent_cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    app_ids = [row.get("application_id") for row in apps if row.get("application_id")]
    recent_logs = await db.employer_sla_auto_trigger_logs.find(
        {
            "employer_user_id": user.user_id,
            "application_id": {"$in": app_ids},
            "created_at": {"$gte": recent_cutoff},
        },
        {"_id": 0, "application_id": 1, "trigger_action": 1, "created_at": 1},
    ).to_list(500)
    recent_log_map = {
        (row.get("application_id"), row.get("trigger_action")): row
        for row in recent_logs
        if row.get("application_id") and row.get("trigger_action")
    }

    items: List[Dict[str, Any]] = []
    for app in apps:
        stage = normalize_pipeline_status(app.get("status"))
        age_days = safe_days_since(app.get("updated_at") or app.get("created_at"))
        target_days = stage_target_days(stage)
        job = jobs_by_id.get(app.get("job_id"), {})
        candidate_id = app.get("candidate_id") or app.get("user_id")
        profile = profiles_by_id.get(candidate_id, {})
        candidate_doc = users_by_id.get(candidate_id, {})
        match = compute_candidate_match(job_doc=job, application_doc=app, profile_doc=profile)
        trigger = determine_sla_auto_trigger(
            stage=stage,
            age_days=age_days,
            target_days=target_days,
            match_score=int(match.get("match_score") or 0),
        )
        if not trigger:
            continue

        recent_log = recent_log_map.get((app.get("application_id"), trigger["trigger_action"]))
        suggested_slots = []
        if trigger["trigger_action"] == "open_slot_suggestion":
            suggested_slots = await compute_slot_suggestions_for_candidate(user.user_id, candidate_id)

        items.append(
            {
                "trigger_id": f"slatrg_{uuid.uuid4().hex[:12]}",
                "application_id": app.get("application_id"),
                "job_id": app.get("job_id"),
                "job_title": job.get("title") or "Untitled Role",
                "candidate_id": candidate_id,
                "candidate_name": app.get("candidate_name") or candidate_doc.get("name") or "Candidate",
                "candidate_email": app.get("candidate_email") or candidate_doc.get("email") or "",
                "stage": stage,
                "age_days": age_days,
                "target_days": target_days,
                "overdue_by_days": max(0, age_days - target_days),
                "match_score": int(match.get("match_score") or 0),
                "trigger_action": trigger["trigger_action"],
                "trigger_label": trigger["trigger_label"],
                "reason": trigger["reason"],
                "suggested_slots": suggested_slots,
                "status": "cooldown_active" if recent_log else "pending",
                "last_executed_at": recent_log.get("created_at") if recent_log else None,
            }
        )

    items.sort(key=lambda row: (int(row.get("overdue_by_days") or 0), int(row.get("match_score") or 0)), reverse=True)
    return items[:safe_limit]


async def execute_sla_auto_trigger_item(user: User, item: Dict[str, Any]) -> Dict[str, Any]:
    application_id = str(item.get("application_id") or "")
    if not application_id:
        raise HTTPException(status_code=400, detail="application_id missing for auto-trigger item")
    owned = await get_owned_application_for_employer(user, application_id)
    app = owned["application"]
    job = owned["job"]
    action = str(item.get("trigger_action") or "").strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    candidate_id = app.get("user_id") or app.get("candidate_id") or ""
    candidate_email = app.get("candidate_email") or ""
    candidate_name = app.get("candidate_name") or "Candidate"
    job_title = job.get("title") or "Role"
    suggested_slots = item.get("suggested_slots") or []

    if action == "send_followup":
        note = f"Hi {candidate_name}, we're keeping your application for {job_title} warm and wanted to check in on next steps."
        if candidate_email:
            await send_candidate_followup_email(
                candidate_email=candidate_email,
                candidate_name=candidate_name,
                employer_name=user.name or "Hiring Team",
                role_title=job_title,
                note=note,
            )
        elif candidate_id:
            await send_candidate_notification_with_optional_email(
                user_id=candidate_id,
                email="",
                title=f"Follow-up for {job_title}",
                message=note,
                notif_type="sla_auto_followup",
                send_email=False,
            )
        await append_application_timeline_event(
            application_id=application_id,
            job_id=job.get("job_id") or "",
            actor_user_id=user.user_id,
            event_type="sla_auto_followup_sent",
            title="SLA Auto Follow-up Sent",
            description=note,
            status=app.get("status"),
            metadata={"trigger_action": action},
        )
    elif action == "open_slot_suggestion":
        if not suggested_slots:
            suggested_slots = await compute_slot_suggestions_for_candidate(user.user_id, candidate_id)
        slot_lines = [f"{slot.get('date')} {slot.get('time')}" for slot in suggested_slots[:3] if slot.get("date") and slot.get("time")]
        message = f"We opened fresh interview slot suggestions for {job_title}: {', '.join(slot_lines) if slot_lines else 'new windows are available shortly.'}"
        await send_candidate_notification_with_optional_email(
            user_id=candidate_id,
            email=candidate_email,
            title=f"Interview Slots Opened · {job_title}",
            message=message,
            notif_type="sla_auto_slot_suggestion",
            send_email=True,
        )
        await append_application_timeline_event(
            application_id=application_id,
            job_id=job.get("job_id") or "",
            actor_user_id=user.user_id,
            event_type="sla_auto_slot_suggestion_sent",
            title="SLA Auto Slot Suggestion Sent",
            description=message,
            status="interview",
            metadata={"trigger_action": action, "slot_count": len(suggested_slots)},
        )
    elif action == "rediscovery":
        message = (
            f"Hi {candidate_name}, we'd like to reopen the conversation for {job_title}. "
            "Your profile is still a strong match and we'd love to fast-track the next step."
        )
        await send_candidate_notification_with_optional_email(
            user_id=candidate_id,
            email=candidate_email,
            title=f"Re-opened Conversation · {job_title}",
            message=message,
            notif_type="sla_auto_rediscovery",
            send_email=True,
        )
        await db.talent_rediscovery_actions.insert_one(
            {
                "action_id": f"redis_auto_{uuid.uuid4().hex[:12]}",
                "candidate_id": candidate_id,
                "candidate_email": candidate_email,
                "job_id": job.get("job_id") or "",
                "job_title": job_title,
                "employer_user_id": user.user_id,
                "message": message,
                "source": "sla_auto_trigger",
                "created_at": now_iso,
            }
        )
        await append_application_timeline_event(
            application_id=application_id,
            job_id=job.get("job_id") or "",
            actor_user_id=user.user_id,
            event_type="sla_auto_rediscovery_sent",
            title="SLA Auto Rediscovery Sent",
            description=message,
            status=app.get("status"),
            metadata={"trigger_action": action},
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported SLA auto-trigger action")

    log_doc = {
        "trigger_log_id": f"slarun_{uuid.uuid4().hex[:12]}",
        "employer_user_id": user.user_id,
        "application_id": application_id,
        "job_id": job.get("job_id") or "",
        "candidate_id": candidate_id,
        "trigger_action": action,
        "trigger_label": item.get("trigger_label") or action,
        "reason": item.get("reason") or "",
        "suggested_slots": suggested_slots[:3],
        "created_at": now_iso,
    }
    await db.employer_sla_auto_trigger_logs.insert_one({**log_doc})
    return log_doc