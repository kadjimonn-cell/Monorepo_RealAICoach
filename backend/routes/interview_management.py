"""Interview Management System — Full CRUD for interview booking, scheduling, feedback.

Supports: schedule, cancel, reschedule, confirm, reject, complete, rate.
Interview types: video, audio, chat, physical.
Auto reminders, real-time notifications via WebSocket.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import uuid
import logging

from .db import db, require_auth, require_admin
from .integrations import _get_google_service, _get_selected_calendar_id
from .jobs_employer_console_realtime import broadcast_employer_pipeline_event
from utils.ws_manager import ws_manager, push_admin_alert

router = APIRouter(prefix="/interviews")
logger = logging.getLogger("routes.interviews")

INTERVIEW_TYPES = ["video", "audio", "chat", "physical"]
INTERVIEW_STATUSES = [
    "scheduled",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled",
    "rescheduled",
    "no_show",
]


class ScheduleInterview(BaseModel):
    application_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    candidate_id: str
    job_id: str
    interview_type: str = "video"
    scheduled_date: str
    scheduled_time: str
    timezone: str = "UTC"
    duration_minutes: int = 30
    location: Optional[str] = None
    notes: Optional[str] = None
    interviewer_name: Optional[str] = None
    interviewer_email: Optional[str] = None


class RescheduleInterview(BaseModel):
    new_date: str
    new_time: str
    timezone: Optional[str] = None
    reason: Optional[str] = None


class InterviewFeedback(BaseModel):
    overall_rating: int  # 1-5
    technical_score: Optional[int] = None  # 0-100
    communication_score: Optional[int] = None
    cultural_fit_score: Optional[int] = None
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    recommendation: str = "maybe"  # strong_hire, hire, maybe, pass
    notes: Optional[str] = None


async def _notify_user(user_id: str, event_type: str, data: dict):
    """Send real-time WebSocket notification to user."""
    await ws_manager.send_to_user(
        user_id,
        {
            "type": "interview_update",
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def _log_activity(interview_id: str, action: str, actor_id: str, details: str = ""):
    """Log interview activity for audit trail."""
    await db.interview_activity_log.insert_one(
        {
            "log_id": f"ilog_{uuid.uuid4().hex[:10]}",
            "interview_id": interview_id,
            "action": action,
            "actor_id": actor_id,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


async def _append_application_timeline_event(
    *,
    application_id: Optional[str],
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
    await db.job_application_timeline_events.insert_one(
        {
            "event_id": f"apptl_{uuid.uuid4().hex[:14]}",
            "application_id": application_id,
            "job_id": job_id,
            "actor_user_id": actor_user_id,
            "event_type": event_type,
            "title": title,
            "description": description,
            "status": status,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _build_interview_calendar_description(interview: Dict[str, Any]) -> str:
    lines: List[str] = []
    candidate_name = interview.get("candidate_name") or "Candidate"
    employer_name = interview.get("employer_name") or "Employer"
    interview_type = interview.get("interview_type") or "interview"
    lines.append(f"{interview_type.title()} interview between {employer_name} and {candidate_name}.")

    if interview.get("notes"):
        lines.append(f"Notes: {interview.get('notes')}")
    if interview.get("meeting_link"):
        lines.append(f"Meeting Link: {interview.get('meeting_link')}")
    if interview.get("interview_id"):
        lines.append(f"Interview ID: {interview.get('interview_id')}")

    return "\n\n".join(lines)


def _format_calendar_event_time(dt_value: str, timezone_name: str) -> Dict[str, str]:
    return {
        "dateTime": dt_value,
        "timeZone": timezone_name or "UTC",
    }


async def _find_interview_calendar_event(
    *, employer_id: str, interview_id: str, explicit_event_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    if explicit_event_id:
        existing = await db.calendar_events.find_one(
            {"id": explicit_event_id, "user_id": employer_id},
            {"_id": 0},
        )
        if existing:
            return existing

    return await db.calendar_events.find_one(
        {
            "user_id": employer_id,
            "metadata.kind": "interview_booking",
            "metadata.interview_id": interview_id,
        },
        {"_id": 0},
    )


async def _sync_interview_calendar_event(interview: Dict[str, Any], action: str) -> Dict[str, Any]:
    employer_id = interview.get("employer_id")
    interview_id = interview.get("interview_id")
    if not employer_id or not interview_id:
        return {
            "success": False,
            "skipped": True,
            "reason": "missing_employer_or_interview",
        }

    explicit_event_id = interview.get("calendar_event_id")
    existing = await _find_interview_calendar_event(
        employer_id=employer_id,
        interview_id=interview_id,
        explicit_event_id=explicit_event_id,
    )

    if action == "delete":
        if not existing:
            return {"success": True, "action": "delete", "skipped": True, "source": "none"}

        google_error = None
        google_event_id = existing.get("google_event_id")
        try:
            if google_event_id:
                service = await _get_google_service(employer_id)
                if service:
                    calendar_id = existing.get("calendar_id") or await _get_selected_calendar_id(employer_id)
                    service.events().delete(calendarId=calendar_id, eventId=google_event_id).execute()
        except Exception as exc:
            google_error = str(exc)
            logger.warning(
                "Interview calendar delete failed for %s (event %s): %s",
                interview_id,
                google_event_id,
                google_error,
            )

        await db.calendar_events.delete_one({"id": existing.get("id"), "user_id": employer_id})
        return {
            "success": google_error is None,
            "action": "delete",
            "event_id": existing.get("id"),
            "google_event_id": google_event_id,
            "source": existing.get("source") or "local",
            "warning": "calendar_delete_non_blocking_failure" if google_error else None,
            "error": google_error,
        }

    timezone_name = interview.get("timezone") or "UTC"
    now_iso = datetime.now(timezone.utc).isoformat()
    event_id = (existing or {}).get("id") or explicit_event_id or f"ivcal_{uuid.uuid4().hex[:12]}"
    calendar_id = (existing or {}).get("calendar_id")
    google_event_id = (existing or {}).get("google_event_id") or interview.get("calendar_google_event_id")

    title = "Interview"
    if interview.get("candidate_name") and interview.get("job_title"):
        title = f"Interview • {interview.get('candidate_name')} • {interview.get('job_title')}"
    elif interview.get("candidate_name"):
        title = f"Interview • {interview.get('candidate_name')}"

    description = _build_interview_calendar_description(interview)
    event_body = {
        "summary": title,
        "start": _format_calendar_event_time(interview.get("scheduled_start", ""), timezone_name),
        "end": _format_calendar_event_time(interview.get("scheduled_end", ""), timezone_name),
        "location": interview.get("location") or "",
        "description": description,
    }

    google_error = None
    service = await _get_google_service(employer_id)
    if service:
        calendar_id = await _get_selected_calendar_id(employer_id)
        try:
            if google_event_id:
                service.events().update(
                    calendarId=calendar_id,
                    eventId=google_event_id,
                    body=event_body,
                ).execute()
            else:
                created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
                google_event_id = created.get("id")
        except Exception as exc:
            if google_event_id:
                try:
                    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
                    google_event_id = created.get("id")
                except Exception as retry_exc:
                    google_error = str(retry_exc)
            else:
                google_error = str(exc)
            if google_error:
                logger.warning(
                    "Interview calendar upsert failed for %s (event %s): %s",
                    interview_id,
                    google_event_id,
                    google_error,
                )

    event_doc = {
        "id": event_id,
        "user_id": employer_id,
        "google_event_id": google_event_id,
        "calendar_id": calendar_id,
        "title": title,
        "start": interview.get("scheduled_start") or "",
        "end": interview.get("scheduled_end") or "",
        "description": description,
        "location": interview.get("location") or "",
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]},
        "reminder_minutes": 30,
        "reminder_sent": False,
        "notes": interview.get("notes") or "",
        "category": "interview",
        "color": "",
        "recurrence": "none",
        "recurrence_end": None,
        "series_id": None,
        "timezone": timezone_name,
        "metadata": {
            "kind": "interview_booking",
            "interview_id": interview_id,
            "application_id": interview.get("application_id") or "",
            "job_id": interview.get("job_id") or "",
            "candidate_id": interview.get("candidate_id") or "",
            "interview_type": interview.get("interview_type") or "",
        },
        "created_at": (existing or {}).get("created_at") or now_iso,
        "updated_at": now_iso,
        "source": "google" if google_event_id else "local",
    }

    await db.calendar_events.update_one(
        {"id": event_id, "user_id": employer_id},
        {"$set": event_doc},
        upsert=True,
    )

    return {
        "success": google_error is None,
        "action": "upsert",
        "event_id": event_id,
        "google_event_id": google_event_id,
        "source": event_doc["source"],
        "warning": "calendar_upsert_non_blocking_failure" if google_error else None,
        "error": google_error,
    }


# ═══════════════════════════════════════════════════════════════
# SCHEDULE / CREATE INTERVIEW
# ═══════════════════════════════════════════════════════════════


@router.post("/schedule")
async def schedule_interview(payload: ScheduleInterview, request: Request):
    """Employer: Schedule an interview with a candidate."""
    user = await require_auth(request)

    if payload.interview_type not in INTERVIEW_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type. Use: {INTERVIEW_TYPES}")

    # Validate candidate exists
    candidate = await db.users.find_one({"user_id": payload.candidate_id}, {"_id": 0, "name": 1, "email": 1})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job = await db.jobs.find_one({"job_id": payload.job_id}, {"_id": 0, "title": 1, "company_name": 1})

    now = datetime.now(timezone.utc).isoformat()
    interview_id = f"intv_{uuid.uuid4().hex[:12]}"

    # Build start/end datetime
    try:
        start_dt = datetime.fromisoformat(f"{payload.scheduled_date}T{payload.scheduled_time}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time format")

    end_dt = start_dt + timedelta(minutes=payload.duration_minutes)

    interview = {
        "interview_id": interview_id,
        "application_id": payload.application_id or "",
        "pipeline_id": payload.pipeline_id or "",
        "job_id": payload.job_id,
        "job_title": (job or {}).get("title", ""),
        "company_name": (job or {}).get("company_name", ""),
        "candidate_id": payload.candidate_id,
        "candidate_name": candidate.get("name", ""),
        "candidate_email": candidate.get("email", ""),
        "employer_id": user.user_id,
        "employer_name": user.name,
        "interviewer_name": payload.interviewer_name or user.name,
        "interviewer_email": payload.interviewer_email or user.email,
        "interview_type": payload.interview_type,
        "status": "scheduled",
        "scheduled_start": start_dt.isoformat(),
        "scheduled_end": end_dt.isoformat(),
        "timezone": payload.timezone,
        "duration_minutes": payload.duration_minutes,
        "location": payload.location,
        "notes": payload.notes,
        "meeting_link": f"https://meet.realaicoach.app/{interview_id}"
        if payload.interview_type in ["video", "audio"]
        else None,
        "feedback": None,
        "reschedule_history": [],
        "reminder_sent": False,
        "created_at": now,
        "updated_at": now,
    }

    await db.interview_bookings.insert_one({**interview})
    await _log_activity(interview_id, "scheduled", user.user_id, f"Interview scheduled for {payload.scheduled_date}")
    await _append_application_timeline_event(
        application_id=payload.application_id,
        job_id=payload.job_id,
        actor_user_id=user.user_id,
        event_type="interview_scheduled",
        title="Interview Scheduled",
        description=f"{payload.interview_type.title()} interview scheduled for {payload.scheduled_date} {payload.scheduled_time}.",
        status="interview",
        metadata={
            "interview_id": interview_id,
            "interview_type": payload.interview_type,
            "scheduled_start": start_dt.isoformat(),
            "timezone": payload.timezone,
        },
    )

    # Notify candidate via WebSocket
    await _notify_user(
        payload.candidate_id,
        "interview_scheduled",
        {
            "interview_id": interview_id,
            "job_title": interview["job_title"],
            "company": interview["company_name"],
            "date": payload.scheduled_date,
            "time": payload.scheduled_time,
            "type": payload.interview_type,
        },
    )

    # Notify admin
    await push_admin_alert(
        "interview_scheduled",
        "New Interview Scheduled",
        f"{user.name} scheduled {payload.interview_type} interview with {candidate.get('name', '')} for {interview['job_title']}",
        "info",
    )

    # Update pipeline stage if exists
    if payload.pipeline_id:
        await db.hiring_pipeline.update_one(
            {"pipeline_id": payload.pipeline_id},
            {"$set": {"current_stage": "interview_scheduling", "updated_at": now}},
        )

    calendar_sync = await _sync_interview_calendar_event(interview, "upsert")
    if calendar_sync.get("event_id"):
        await db.interview_bookings.update_one(
            {"interview_id": interview_id},
            {
                "$set": {
                    "calendar_event_id": calendar_sync.get("event_id"),
                    "calendar_google_event_id": calendar_sync.get("google_event_id"),
                    "calendar_sync_source": calendar_sync.get("source"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        interview["calendar_event_id"] = calendar_sync.get("event_id")
        interview["calendar_google_event_id"] = calendar_sync.get("google_event_id")
        interview["calendar_sync_source"] = calendar_sync.get("source")

    await broadcast_employer_pipeline_event(
        user.user_id,
        {
            "event_type": "interview_scheduled",
            "actor_user_id": user.user_id,
            "actor_name": user.name or "Recruiter",
            "application_id": payload.application_id or "",
            "job_id": payload.job_id,
            "interview_id": interview_id,
            "candidate_name": candidate.get("name", "Candidate"),
            "message": f"{user.name or 'Recruiter'} scheduled an interview with {candidate.get('name', 'Candidate')}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {"interview": interview, "success": True, "calendar_sync": calendar_sync}


# ═══════════════════════════════════════════════════════════════
# GET / LIST INTERVIEWS
# ═══════════════════════════════════════════════════════════════


@router.get("/my")
async def get_my_interviews(request: Request, role: str = "candidate"):
    """Get interviews for the current user (as candidate or employer)."""
    user = await require_auth(request)
    field = "candidate_id" if role == "candidate" else "employer_id"
    interviews = (
        await db.interview_bookings.find({field: user.user_id}, {"_id": 0}).sort("scheduled_start", -1).to_list(100)
    )
    return {"interviews": interviews, "total": len(interviews), "role": role}


@router.get("/{interview_id}")
async def get_interview(interview_id: str, request: Request):
    """Get interview details."""
    await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    # Get activity log
    logs = (
        await db.interview_activity_log.find({"interview_id": interview_id}, {"_id": 0})
        .sort("timestamp", -1)
        .to_list(50)
    )

    return {"interview": interview, "activity_log": logs}


@router.get("/job/{job_id}")
async def get_interviews_for_job(job_id: str, request: Request):
    """Employer: Get all interviews for a job."""
    await require_auth(request)
    interviews = (
        await db.interview_bookings.find({"job_id": job_id}, {"_id": 0}).sort("scheduled_start", -1).to_list(200)
    )
    return {"interviews": interviews, "total": len(interviews)}


# ═══════════════════════════════════════════════════════════════
# CANDIDATE ACTIONS
# ═══════════════════════════════════════════════════════════════


@router.post("/{interview_id}/accept")
async def accept_interview(interview_id: str, request: Request):
    """Candidate: Accept/confirm interview."""
    user = await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.interview_bookings.update_one(
        {"interview_id": interview_id},
        {"$set": {"status": "confirmed", "updated_at": now}},
    )
    await _log_activity(interview_id, "confirmed", user.user_id, "Candidate confirmed attendance")
    await _append_application_timeline_event(
        application_id=interview.get("application_id"),
        job_id=interview.get("job_id", ""),
        actor_user_id=user.user_id,
        event_type="interview_confirmed",
        title="Interview Confirmed",
        description="Candidate confirmed interview attendance.",
        status="interview",
        metadata={"interview_id": interview_id},
    )
    await _notify_user(
        interview["employer_id"],
        "interview_confirmed",
        {
            "interview_id": interview_id,
            "candidate_name": interview["candidate_name"],
        },
    )
    await broadcast_employer_pipeline_event(
        interview.get("employer_id") or "",
        {
            "event_type": "interview_confirmed",
            "actor_user_id": user.user_id,
            "actor_name": user.name or interview.get("candidate_name") or "Candidate",
            "application_id": interview.get("application_id") or "",
            "job_id": interview.get("job_id") or "",
            "interview_id": interview_id,
            "candidate_name": interview.get("candidate_name") or "Candidate",
            "message": f"{interview.get('candidate_name') or 'Candidate'} confirmed the interview.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"success": True, "status": "confirmed"}


@router.post("/{interview_id}/decline")
async def decline_interview(interview_id: str, request: Request):
    """Candidate: Decline interview."""
    user = await require_auth(request)
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    reason = body.get("reason", "")

    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.interview_bookings.update_one(
        {"interview_id": interview_id},
        {"$set": {"status": "cancelled", "cancel_reason": reason, "cancelled_by": "candidate", "updated_at": now}},
    )
    await _log_activity(interview_id, "declined", user.user_id, f"Candidate declined: {reason}")
    await _append_application_timeline_event(
        application_id=interview.get("application_id"),
        job_id=interview.get("job_id", ""),
        actor_user_id=user.user_id,
        event_type="interview_declined",
        title="Interview Declined",
        description=reason or "Candidate declined the interview.",
        status="interview",
        metadata={"interview_id": interview_id},
    )
    await _notify_user(
        interview["employer_id"],
        "interview_declined",
        {
            "interview_id": interview_id,
            "candidate_name": interview["candidate_name"],
            "reason": reason,
        },
    )
    await broadcast_employer_pipeline_event(
        interview.get("employer_id") or "",
        {
            "event_type": "interview_declined",
            "actor_user_id": user.user_id,
            "actor_name": user.name or interview.get("candidate_name") or "Candidate",
            "application_id": interview.get("application_id") or "",
            "job_id": interview.get("job_id") or "",
            "interview_id": interview_id,
            "candidate_name": interview.get("candidate_name") or "Candidate",
            "message": f"{interview.get('candidate_name') or 'Candidate'} declined the interview.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"success": True, "status": "cancelled"}


@router.post("/{interview_id}/reschedule-request")
async def candidate_reschedule_request(interview_id: str, payload: RescheduleInterview, request: Request):
    """Candidate: Request reschedule."""
    user = await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.interview_bookings.update_one(
        {"interview_id": interview_id},
        {
            "$set": {"status": "rescheduled", "updated_at": now},
            "$push": {
                "reschedule_history": {
                    "requested_by": "candidate",
                    "old_date": interview["scheduled_start"],
                    "new_date": f"{payload.new_date}T{payload.new_time}",
                    "reason": payload.reason,
                    "timestamp": now,
                }
            },
        },
    )
    await _log_activity(interview_id, "reschedule_requested", user.user_id, payload.reason or "")
    await _append_application_timeline_event(
        application_id=interview.get("application_id"),
        job_id=interview.get("job_id", ""),
        actor_user_id=user.user_id,
        event_type="interview_reschedule_requested",
        title="Interview Reschedule Requested",
        description=payload.reason or "Candidate requested interview reschedule.",
        status="interview",
        metadata={
            "interview_id": interview_id,
            "new_date": payload.new_date,
            "new_time": payload.new_time,
        },
    )
    await _notify_user(
        interview["employer_id"],
        "reschedule_requested",
        {
            "interview_id": interview_id,
            "candidate_name": interview["candidate_name"],
            "new_date": payload.new_date,
            "new_time": payload.new_time,
        },
    )
    await broadcast_employer_pipeline_event(
        interview.get("employer_id") or "",
        {
            "event_type": "interview_reschedule_requested",
            "actor_user_id": user.user_id,
            "actor_name": user.name or interview.get("candidate_name") or "Candidate",
            "application_id": interview.get("application_id") or "",
            "job_id": interview.get("job_id") or "",
            "interview_id": interview_id,
            "candidate_name": interview.get("candidate_name") or "Candidate",
            "message": f"{interview.get('candidate_name') or 'Candidate'} requested a new interview time.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"success": True, "status": "rescheduled"}


# ═══════════════════════════════════════════════════════════════
# EMPLOYER ACTIONS
# ═══════════════════════════════════════════════════════════════


@router.post("/{interview_id}/cancel")
async def cancel_interview(interview_id: str, request: Request):
    """Employer: Cancel interview."""
    user = await require_auth(request)
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    reason = body.get("reason", "")

    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.interview_bookings.update_one(
        {"interview_id": interview_id},
        {"$set": {"status": "cancelled", "cancel_reason": reason, "cancelled_by": "employer", "updated_at": now}},
    )
    await _log_activity(interview_id, "cancelled", user.user_id, f"Employer cancelled: {reason}")
    await _append_application_timeline_event(
        application_id=interview.get("application_id"),
        job_id=interview.get("job_id", ""),
        actor_user_id=user.user_id,
        event_type="interview_cancelled",
        title="Interview Cancelled",
        description=reason or "Employer cancelled the interview.",
        status="interview",
        metadata={"interview_id": interview_id},
    )
    await _notify_user(
        interview["candidate_id"],
        "interview_cancelled",
        {
            "interview_id": interview_id,
            "job_title": interview["job_title"],
            "reason": reason,
        },
    )
    await push_admin_alert(
        "interview_cancelled",
        "Interview Cancelled",
        f"{user.name} cancelled interview for {interview['job_title']}",
        "warning",
    )

    cancelled_snapshot = {**interview, "status": "cancelled"}
    calendar_sync = await _sync_interview_calendar_event(cancelled_snapshot, "delete")

    await broadcast_employer_pipeline_event(
        user.user_id,
        {
            "event_type": "interview_cancelled",
            "actor_user_id": user.user_id,
            "actor_name": user.name or "Recruiter",
            "application_id": interview.get("application_id") or "",
            "job_id": interview.get("job_id") or "",
            "interview_id": interview_id,
            "candidate_name": interview.get("candidate_name") or "Candidate",
            "message": f"{user.name or 'Recruiter'} cancelled the interview for {interview.get('candidate_name') or 'Candidate'}.",
            "undo_window_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
            "undo_kind": "cancel",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {"success": True, "status": "cancelled", "calendar_sync": calendar_sync}


@router.post("/{interview_id}/reschedule")
async def reschedule_interview(interview_id: str, payload: RescheduleInterview, request: Request):
    """Employer: Reschedule interview."""
    user = await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    try:
        new_start = datetime.fromisoformat(f"{payload.new_date}T{payload.new_time}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time format")

    new_end = new_start + timedelta(minutes=interview.get("duration_minutes", 30))
    tz = payload.timezone or interview.get("timezone", "UTC")
    now = datetime.now(timezone.utc).isoformat()

    await db.interview_bookings.update_one(
        {"interview_id": interview_id},
        {
            "$set": {
                "status": "scheduled",
                "scheduled_start": new_start.isoformat(),
                "scheduled_end": new_end.isoformat(),
                "timezone": tz,
                "reminder_sent": False,
                "updated_at": now,
            },
            "$push": {
                "reschedule_history": {
                    "requested_by": "employer",
                    "old_date": interview["scheduled_start"],
                    "new_date": new_start.isoformat(),
                    "reason": payload.reason,
                    "timestamp": now,
                }
            },
        },
    )
    await _log_activity(interview_id, "rescheduled", user.user_id, payload.reason or "")
    await _append_application_timeline_event(
        application_id=interview.get("application_id"),
        job_id=interview.get("job_id", ""),
        actor_user_id=user.user_id,
        event_type="interview_rescheduled",
        title="Interview Rescheduled",
        description=payload.reason or "Interview schedule updated by employer.",
        status="interview",
        metadata={
            "interview_id": interview_id,
            "new_date": payload.new_date,
            "new_time": payload.new_time,
        },
    )
    await _notify_user(
        interview["candidate_id"],
        "interview_rescheduled",
        {
            "interview_id": interview_id,
            "job_title": interview["job_title"],
            "new_date": payload.new_date,
            "new_time": payload.new_time,
        },
    )

    refreshed_interview = {
        **interview,
        "status": "scheduled",
        "scheduled_start": new_start.isoformat(),
        "scheduled_end": new_end.isoformat(),
        "timezone": tz,
    }
    calendar_sync = await _sync_interview_calendar_event(refreshed_interview, "upsert")
    if calendar_sync.get("event_id"):
        await db.interview_bookings.update_one(
            {"interview_id": interview_id},
            {
                "$set": {
                    "calendar_event_id": calendar_sync.get("event_id"),
                    "calendar_google_event_id": calendar_sync.get("google_event_id"),
                    "calendar_sync_source": calendar_sync.get("source"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    is_undo_restore = str(payload.reason or "").lower().startswith("undo ")
    await broadcast_employer_pipeline_event(
        user.user_id,
        {
            "event_type": "interview_action_undone" if is_undo_restore else "interview_rescheduled",
            "actor_user_id": user.user_id,
            "actor_name": user.name or "Recruiter",
            "application_id": interview.get("application_id") or "",
            "job_id": interview.get("job_id") or "",
            "interview_id": interview_id,
            "candidate_name": interview.get("candidate_name") or "Candidate",
            "message": (
                f"{user.name or 'Recruiter'} restored the previous interview slot for {interview.get('candidate_name') or 'Candidate'}."
                if is_undo_restore
                else f"{user.name or 'Recruiter'} rescheduled the interview for {interview.get('candidate_name') or 'Candidate'}."
            ),
            **({"undo_window_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(), "undo_kind": "reschedule"} if not is_undo_restore else {}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "success": True,
        "status": "scheduled",
        "new_start": new_start.isoformat(),
        "calendar_sync": calendar_sync,
    }


@router.post("/{interview_id}/complete")
async def complete_interview(interview_id: str, request: Request):
    """Employer: Mark interview as completed."""
    user = await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.interview_bookings.update_one(
        {"interview_id": interview_id},
        {"$set": {"status": "completed", "completed_at": now, "updated_at": now}},
    )
    await _log_activity(interview_id, "completed", user.user_id)
    await _append_application_timeline_event(
        application_id=interview.get("application_id"),
        job_id=interview.get("job_id", ""),
        actor_user_id=user.user_id,
        event_type="interview_completed",
        title="Interview Completed",
        description="Employer marked interview as completed.",
        status="interview",
        metadata={"interview_id": interview_id},
    )
    await _notify_user(
        interview["candidate_id"],
        "interview_completed",
        {
            "interview_id": interview_id,
            "job_title": interview["job_title"],
        },
    )

    # Update pipeline if exists
    if interview.get("pipeline_id"):
        await db.hiring_pipeline.update_one(
            {"pipeline_id": interview["pipeline_id"]},
            {"$set": {"current_stage": "interview_analysis", "updated_at": now}},
        )

    return {"success": True, "status": "completed"}


@router.post("/{interview_id}/reject")
async def reject_candidate(interview_id: str, request: Request):
    """Employer: Reject candidate after interview."""
    user = await require_auth(request)
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    reason = body.get("reason", "")

    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.interview_bookings.update_one(
        {"interview_id": interview_id},
        {"$set": {"status": "completed", "candidate_rejected": True, "reject_reason": reason, "updated_at": now}},
    )
    await _log_activity(interview_id, "candidate_rejected", user.user_id, reason)
    await _append_application_timeline_event(
        application_id=interview.get("application_id"),
        job_id=interview.get("job_id", ""),
        actor_user_id=user.user_id,
        event_type="candidate_rejected",
        title="Candidate Rejected",
        description=reason or "Candidate was rejected after interview.",
        status="rejected",
        metadata={"interview_id": interview_id},
    )
    await _notify_user(
        interview["candidate_id"],
        "application_rejected",
        {
            "interview_id": interview_id,
            "job_title": interview["job_title"],
        },
    )

    # Update application status
    if interview.get("application_id"):
        await db.job_applications.update_one(
            {"application_id": interview["application_id"]},
            {"$set": {"status": "rejected", "updated_at": now}},
        )

    return {"success": True}


@router.post("/{interview_id}/move-stage")
async def move_hiring_stage(interview_id: str, request: Request):
    """Employer: Move candidate to a specific hiring stage."""
    user = await require_auth(request)
    body = await request.json()
    new_stage = body.get("stage", "")

    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    now = datetime.now(timezone.utc).isoformat()
    if interview.get("pipeline_id"):
        await db.hiring_pipeline.update_one(
            {"pipeline_id": interview["pipeline_id"]},
            {
                "$set": {"current_stage": new_stage, "updated_at": now},
                "$push": {"stage_history": {"stage": new_stage, "timestamp": now, "auto": False}},
            },
        )

    await _log_activity(interview_id, "stage_moved", user.user_id, f"Moved to {new_stage}")
    await _append_application_timeline_event(
        application_id=interview.get("application_id"),
        job_id=interview.get("job_id", ""),
        actor_user_id=user.user_id,
        event_type="pipeline_stage_moved",
        title="Pipeline Stage Updated",
        description=f"Hiring stage moved to {new_stage}.",
        status=new_stage,
        metadata={"interview_id": interview_id, "new_stage": new_stage},
    )
    await _notify_user(
        interview["candidate_id"],
        "hiring_stage_updated",
        {
            "interview_id": interview_id,
            "job_title": interview["job_title"],
            "new_stage": new_stage,
        },
    )
    return {"success": True, "new_stage": new_stage}


# ═══════════════════════════════════════════════════════════════
# FEEDBACK & RATING
# ═══════════════════════════════════════════════════════════════


@router.post("/{interview_id}/feedback")
async def submit_feedback(interview_id: str, payload: InterviewFeedback, request: Request):
    """Employer: Submit interview feedback and rating."""
    user = await require_auth(request)
    interview = await db.interview_bookings.find_one({"interview_id": interview_id}, {"_id": 0})
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    now = datetime.now(timezone.utc).isoformat()
    feedback = {
        "feedback_id": f"fb_{uuid.uuid4().hex[:10]}",
        "interview_id": interview_id,
        "reviewer_id": user.user_id,
        "reviewer_name": user.name,
        "overall_rating": payload.overall_rating,
        "technical_score": payload.technical_score,
        "communication_score": payload.communication_score,
        "cultural_fit_score": payload.cultural_fit_score,
        "strengths": payload.strengths or [],
        "weaknesses": payload.weaknesses or [],
        "recommendation": payload.recommendation,
        "notes": payload.notes,
        "submitted_at": now,
    }

    await db.interview_feedback.insert_one({**feedback})
    await db.interview_bookings.update_one(
        {"interview_id": interview_id},
        {"$set": {"feedback": feedback, "updated_at": now}},
    )
    await _log_activity(
        interview_id,
        "feedback_submitted",
        user.user_id,
        f"Rating: {payload.overall_rating}/5, Rec: {payload.recommendation}",
    )
    return {"success": True, "feedback": feedback}


@router.get("/{interview_id}/feedback")
async def get_feedback(interview_id: str, request: Request):
    """Get feedback for an interview."""
    await require_auth(request)
    feedbacks = await db.interview_feedback.find({"interview_id": interview_id}, {"_id": 0}).to_list(20)
    return {"feedbacks": feedbacks, "total": len(feedbacks)}


# ═══════════════════════════════════════════════════════════════
# ADMIN ANALYTICS
# ═══════════════════════════════════════════════════════════════


@router.get("/admin/analytics")
async def admin_interview_analytics(request: Request):
    """Admin: Get interview analytics dashboard data."""
    await require_admin(request)

    total = await db.interview_bookings.count_documents({})
    by_status = {}
    for s in INTERVIEW_STATUSES:
        by_status[s] = await db.interview_bookings.count_documents({"status": s})

    by_type = {}
    for t in INTERVIEW_TYPES:
        by_type[t] = await db.interview_bookings.count_documents({"interview_type": t})

    completed = by_status.get("completed", 0)
    total_feedback = await db.interview_feedback.count_documents({})

    # Avg ratings
    pipeline = [
        {
            "$group": {
                "_id": None,
                "avg_rating": {"$avg": "$overall_rating"},
                "avg_tech": {"$avg": "$technical_score"},
                "avg_comm": {"$avg": "$communication_score"},
                "avg_culture": {"$avg": "$cultural_fit_score"},
            }
        }
    ]
    avg_result = await db.interview_feedback.aggregate(pipeline).to_list(1)
    avgs = avg_result[0] if avg_result else {}

    # Recommendation breakdown
    rec_breakdown = {}
    for r in ["strong_hire", "hire", "maybe", "pass"]:
        rec_breakdown[r] = await db.interview_feedback.count_documents({"recommendation": r})

    # Active employers (who scheduled interviews)
    active_employers = len(await db.interview_bookings.distinct("employer_id"))

    # Candidate participation rate
    confirmed = by_status.get("confirmed", 0) + completed
    participation_rate = round(confirmed / max(total, 1) * 100, 1)

    # Hiring conversion (completed interviews that led to hire recommendation)
    hired = rec_breakdown.get("strong_hire", 0) + rec_breakdown.get("hire", 0)
    conversion_rate = round(hired / max(completed, 1) * 100, 1)

    # Top employers by interviews
    emp_pipeline = [
        {"$group": {"_id": "$employer_id", "count": {"$sum": 1}, "name": {"$first": "$employer_name"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_employers = await db.interview_bookings.aggregate(emp_pipeline).to_list(10)

    # Recent activity
    recent = await db.interview_activity_log.find({}, {"_id": 0}).sort("timestamp", -1).limit(20).to_list(20)

    # Weekly trend (last 4 weeks)
    weekly_trend = []
    for w in range(4):
        start = datetime.now(timezone.utc) - timedelta(weeks=w + 1)
        end = datetime.now(timezone.utc) - timedelta(weeks=w)
        count = await db.interview_bookings.count_documents(
            {"created_at": {"$gte": start.isoformat(), "$lt": end.isoformat()}}
        )
        weekly_trend.append({"week": f"W-{w}", "count": count})

    return {
        "total_interviews": total,
        "status_breakdown": by_status,
        "type_breakdown": by_type,
        "total_feedback": total_feedback,
        "avg_ratings": {
            "overall": round(avgs.get("avg_rating", 0) or 0, 1),
            "technical": round(avgs.get("avg_tech", 0) or 0, 1),
            "communication": round(avgs.get("avg_comm", 0) or 0, 1),
            "cultural_fit": round(avgs.get("avg_culture", 0) or 0, 1),
        },
        "recommendation_breakdown": rec_breakdown,
        "active_employers": active_employers,
        "participation_rate": participation_rate,
        "hiring_conversion_rate": conversion_rate,
        "top_employers": [{"name": e.get("name", ""), "count": e["count"]} for e in top_employers],
        "recent_activity": recent,
        "weekly_trend": weekly_trend,
    }


@router.post("/admin/suspend/{employer_id}")
async def admin_suspend_employer_booking(employer_id: str, request: Request):
    """Admin: Suspend employer's booking rights."""
    await require_admin(request)
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"user_id": employer_id},
        {"$set": {"booking_suspended": True, "booking_suspended_at": now}},
    )
    await push_admin_alert(
        "employer_suspended", "Employer Suspended", f"Booking rights suspended for employer {employer_id}", "critical"
    )
    return {"success": True}


@router.post("/admin/unsuspend/{employer_id}")
async def admin_unsuspend_employer_booking(employer_id: str, request: Request):
    """Admin: Restore employer's booking rights."""
    await require_admin(request)
    await db.users.update_one(
        {"user_id": employer_id},
        {"$set": {"booking_suspended": False}},
    )
    return {"success": True}
