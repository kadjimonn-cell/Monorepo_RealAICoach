"""Careers ATS — Phase 1 scheduling (applicant self-serve, TZ-aware).

Problem: applicants in diverse time zones + admin team scheduling = an
enormous hidden drain. This router solves it with three primitives:

  1. Interviewer availability windows (per-interviewer, in their TZ).
  2. Public slot page the applicant opens via a magic-link: the server
     generates free slots translated into the applicant's browser TZ, the
     applicant taps one, the server locks in the UTC instant and sends
     TZ-aware ICS invites to BOTH sides.
  3. Dual-ICS + Google/Outlook deep-link confirmation email so no
     calendar client silently re-converts the time.

All stored instants are UTC. Local-time display is computed on the fly
from the stored TZID → never lose the source-of-truth UTC.

Public endpoints are unauthenticated (magic-link is the auth):
  - GET  /api/careers/schedule/{token}
  - GET  /api/careers/schedule/{token}/slots?tz=...
  - POST /api/careers/schedule/{token}/book
  - POST /api/careers/schedule/{token}/reschedule

Admin endpoints:
  - GET  /api/careers/scheduling/my-availability
  - PUT  /api/careers/scheduling/my-availability
  - POST /api/careers/applications/{app_id}/scheduling-invite
  - GET  /api/careers/scheduling/interview/{app_id}  (read-back)
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from routes.careers_common import APPS_COL
from routes.db import db, require_admin
from utils.ics_builder import (
    build_interview_ics_tzaware,
    google_calendar_link,
    ics_attachment,
    outlook_calendar_link,
)

logger = logging.getLogger(__name__)
router = APIRouter()

AVAIL_COL = "careers_interviewer_availability"
SCHED_INVITE_COL = "careers_schedule_invites"
INTERVIEWS_COL = "careers_interviews"

DEFAULT_WEEKDAYS = [0, 1, 2, 3, 4]  # Mon=0 .. Fri=4
DEFAULT_SLOT_MIN = 30
DEFAULT_BUFFER_MIN = 15
DEFAULT_MAX_PER_DAY = 6
DEFAULT_WORK_START = "09:00"
DEFAULT_WORK_END = "17:00"
DEFAULT_TZ = "UTC"
DEFAULT_SLOT_LOOKAHEAD_DAYS = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


def _frontend_base() -> str:
    return (
        os.environ.get("REACT_APP_BACKEND_URL")
        or os.environ.get("FRONTEND_URL")
        or ""
    ).rstrip("/")


# ─────────────────────────────────────────────────────────────────────────────
# Availability — admin CRUD
# ─────────────────────────────────────────────────────────────────────────────


class WeekdayWindow(BaseModel):
    """A contiguous availability window within a single weekday."""
    weekday: int = Field(..., ge=0, le=6, description="0=Mon ... 6=Sun")
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class AvailabilityBody(BaseModel):
    tz: str = Field(default=DEFAULT_TZ, description="IANA tz name e.g. 'Africa/Porto-Novo'")
    windows: list[WeekdayWindow] = Field(default_factory=list)
    slot_minutes: int = Field(default=DEFAULT_SLOT_MIN, ge=15, le=240)
    buffer_minutes: int = Field(default=DEFAULT_BUFFER_MIN, ge=0, le=120)
    max_per_day: int = Field(default=DEFAULT_MAX_PER_DAY, ge=1, le=24)


def _default_availability_for(user_id: str, email: str, name: str) -> dict[str, Any]:
    return {
        "owner_user_id": user_id,
        "owner_email": email,
        "owner_name": name,
        "tz": DEFAULT_TZ,
        "windows": [
            {"weekday": d, "start": DEFAULT_WORK_START, "end": DEFAULT_WORK_END}
            for d in DEFAULT_WEEKDAYS
        ],
        "slot_minutes": DEFAULT_SLOT_MIN,
        "buffer_minutes": DEFAULT_BUFFER_MIN,
        "max_per_day": DEFAULT_MAX_PER_DAY,
        "updated_at": _now_iso(),
    }


@router.get("/careers/scheduling/my-availability")
async def admin_get_my_availability(request: Request):
    admin = await require_admin(request)
    uid = getattr(admin, "user_id", None) or getattr(admin, "id", None) or ""
    email = getattr(admin, "email", "") or ""
    name = getattr(admin, "name", "") or email.split("@")[0]
    doc = await db[AVAIL_COL].find_one({"owner_user_id": uid}, {"_id": 0})
    if not doc:
        doc = _default_availability_for(uid, email, name)
    return {"availability": doc}


@router.put("/careers/scheduling/my-availability")
async def admin_put_my_availability(request: Request, body: AvailabilityBody):
    admin = await require_admin(request)
    uid = getattr(admin, "user_id", None) or getattr(admin, "id", None) or ""
    email = getattr(admin, "email", "") or ""
    name = getattr(admin, "name", "") or email.split("@")[0]
    # Validate TZ (fail loudly if the admin pastes a typo — DST correctness
    # depends on zoneinfo resolving correctly).
    try:
        ZoneInfo(body.tz)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Unknown IANA timezone: {body.tz!r}")
    # Validate each window (start < end)
    for w in body.windows:
        if w.start >= w.end:
            raise HTTPException(
                status_code=422,
                detail=f"Window weekday={w.weekday} has start >= end ({w.start} >= {w.end}).",
            )
    doc = {
        "owner_user_id": uid,
        "owner_email": email,
        "owner_name": name,
        "tz": body.tz,
        "windows": [w.model_dump() for w in body.windows],
        "slot_minutes": body.slot_minutes,
        "buffer_minutes": body.buffer_minutes,
        "max_per_day": body.max_per_day,
        "updated_at": _now_iso(),
    }
    await db[AVAIL_COL].update_one(
        {"owner_user_id": uid}, {"$set": doc}, upsert=True,
    )
    return {"availability": doc}


# ─────────────────────────────────────────────────────────────────────────────
# Scheduling invite — admin mints a magic link for an applicant
# ─────────────────────────────────────────────────────────────────────────────


class SchedInviteBody(BaseModel):
    interviewer_user_id: Optional[str] = Field(
        None, description="Defaults to the admin issuing the invite"
    )
    duration_minutes: int = Field(default=45, ge=15, le=240)
    interview_type: str = Field(default="video")
    video_url: Optional[str] = Field(default=None)
    lookahead_days: int = Field(default=DEFAULT_SLOT_LOOKAHEAD_DAYS, ge=1, le=30)
    notes: Optional[str] = Field(default=None, max_length=2000)


@router.post("/careers/applications/{app_id}/scheduling-invite")
async def admin_mint_scheduling_invite(
    request: Request, app_id: str, body: SchedInviteBody
):
    admin = await require_admin(request)
    admin_uid = getattr(admin, "user_id", None) or getattr(admin, "id", None) or ""
    app = await db[APPS_COL].find_one({"application_id": app_id}, {"_id": 0})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    interviewer_uid = body.interviewer_user_id or admin_uid
    avail = await db[AVAIL_COL].find_one(
        {"owner_user_id": interviewer_uid}, {"_id": 0}
    )
    if not avail:
        raise HTTPException(
            status_code=422,
            detail=(
                "Interviewer has no availability configured. "
                "Set it via PUT /api/careers/scheduling/my-availability first."
            ),
        )
    token = f"sch_{secrets.token_urlsafe(24)}"
    now = _now_iso()
    invite_doc = {
        "token": token,
        "application_id": app_id,
        "candidate_email": app.get("email") or "",
        "candidate_name": app.get("candidate_name") or app.get("name") or "",
        "role_title": app.get("role_title") or app.get("role") or "",
        "interviewer_user_id": interviewer_uid,
        "interviewer_email": avail.get("owner_email") or "",
        "interviewer_name": avail.get("owner_name") or "",
        "interviewer_tz": avail.get("tz") or DEFAULT_TZ,
        "duration_minutes": body.duration_minutes,
        "interview_type": body.interview_type,
        "video_url": body.video_url or "",
        "lookahead_days": body.lookahead_days,
        "notes": body.notes or "",
        "status": "pending",  # pending | booked | rescheduled | cancelled
        "created_at": now,
        "created_by": getattr(admin, "email", None) or "admin",
        "booked_at": None,
        "booked_slot_utc": None,
        "applicant_tz": None,
        "history": [],
    }
    await db[SCHED_INVITE_COL].insert_one(invite_doc)

    # Send the magic link — reuse the existing catalog template if present,
    # else fall back to a plain send. Fail-safe.
    public_link = f"{_frontend_base()}/careers/schedule/{token}"
    email_payload = {
        "applicant_name": invite_doc["candidate_name"] or "there",
        "role_title": invite_doc["role_title"] or "the role",
        "interviewer_name": invite_doc["interviewer_name"] or "the team",
        "schedule_link": public_link,
        "duration_minutes": body.duration_minutes,
    }
    try:
        from utils.email_service import is_email_configured, send_catalog_template
        if is_email_configured() and invite_doc["candidate_email"]:
            await send_catalog_template(
                recipient_email=invite_doc["candidate_email"],
                template_key="careers_scheduling_invite",
                recipient_name=invite_doc["candidate_name"] or "",
                **email_payload,
            )
    except Exception as e:
        logger.warning(f"[careers/scheduling] invite email failed: {e}")

    return {
        "ok": True,
        "token": token,
        "public_link": public_link,
        "lookahead_days": body.lookahead_days,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: applicant slot page
# ─────────────────────────────────────────────────────────────────────────────


async def _load_invite_or_404(token: str) -> dict[str, Any]:
    inv = await db[SCHED_INVITE_COL].find_one({"token": token}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invalid or expired scheduling link")
    return inv


async def _load_availability(user_id: str) -> Optional[dict[str, Any]]:
    return await db[AVAIL_COL].find_one({"owner_user_id": user_id}, {"_id": 0})


@router.get("/careers/schedule/{token}")
async def public_get_scheduling_invite(token: str):
    inv = await _load_invite_or_404(token)
    out = {
        "application_id": inv["application_id"],
        "candidate_name": inv.get("candidate_name") or "",
        "role_title": inv.get("role_title") or "",
        "interviewer_name": inv.get("interviewer_name") or "",
        "interviewer_tz": inv.get("interviewer_tz") or DEFAULT_TZ,
        "duration_minutes": inv.get("duration_minutes") or 45,
        "interview_type": inv.get("interview_type") or "video",
        "status": inv.get("status") or "pending",
        "booked_slot_utc": inv.get("booked_slot_utc"),
        "applicant_tz": inv.get("applicant_tz"),
    }
    return out


def _generate_free_slots_utc(
    *,
    avail: dict[str, Any],
    busy_utc: list[tuple[datetime, datetime]],
    lookahead_days: int,
    duration_minutes: int,
    starting_from_utc: datetime,
) -> list[datetime]:
    """DST-aware slot generation. Steps:
      1. For each day in [today, today+lookahead_days] we take the interviewer's
         LOCAL weekday (in their TZ) and look up matching windows.
      2. Within each window we step in `slot_minutes` increments, ensuring
         `slot_minutes + buffer_minutes` fits.
      3. We convert each candidate slot from interviewer-local to UTC via
         zoneinfo (DST handled automatically — the `fold` parameter handles
         ambiguous times on fall-back by choosing the first occurrence).
      4. Filter out: in-the-past, conflicting with busy intervals (slot start
         or end falls inside any busy interval), past the daily max.
    """
    tz = _resolve_tz(avail.get("tz") or DEFAULT_TZ)
    windows_by_wd: dict[int, list[dict[str, str]]] = {}
    for w in (avail.get("windows") or []):
        windows_by_wd.setdefault(int(w["weekday"]), []).append(
            {"start": w["start"], "end": w["end"]}
        )
    slot_minutes = int(avail.get("slot_minutes") or DEFAULT_SLOT_MIN)
    buffer_minutes = int(avail.get("buffer_minutes") or DEFAULT_BUFFER_MIN)
    max_per_day = int(avail.get("max_per_day") or DEFAULT_MAX_PER_DAY)

    def _conflicts(slot_start_utc: datetime, slot_end_utc: datetime) -> bool:
        for b0, b1 in busy_utc:
            if slot_start_utc < b1 and slot_end_utc > b0:
                return True
        return False

    results: list[datetime] = []
    # Anchor "today" in the interviewer's TZ so the day roll-over happens
    # correctly even across UTC midnight.
    today_local = starting_from_utc.astimezone(tz).date()
    for day_offset in range(0, lookahead_days):
        day = today_local + timedelta(days=day_offset)
        wd = day.weekday()  # Mon=0
        day_windows = windows_by_wd.get(wd) or []
        if not day_windows:
            continue
        day_slots_so_far = 0
        for w in sorted(day_windows, key=lambda x: x["start"]):
            sh, sm = [int(x) for x in w["start"].split(":")]
            eh, em = [int(x) for x in w["end"].split(":")]
            local_start = datetime(day.year, day.month, day.day, sh, sm, tzinfo=tz)
            local_end = datetime(day.year, day.month, day.day, eh, em, tzinfo=tz)
            cursor = local_start
            step = timedelta(minutes=slot_minutes + buffer_minutes)
            while cursor + timedelta(minutes=slot_minutes) <= local_end:
                slot_utc = cursor.astimezone(timezone.utc)
                end_utc = slot_utc + timedelta(minutes=duration_minutes)
                if slot_utc < starting_from_utc:
                    cursor = cursor + step
                    continue
                if _conflicts(slot_utc, end_utc):
                    cursor = cursor + step
                    continue
                if day_slots_so_far >= max_per_day:
                    break
                results.append(slot_utc)
                day_slots_so_far += 1
                cursor = cursor + step
            if day_slots_so_far >= max_per_day:
                break
    return results


@router.get("/careers/schedule/{token}/slots")
async def public_list_slots(token: str, tz: str = Query(default=DEFAULT_TZ)):
    inv = await _load_invite_or_404(token)
    if inv.get("status") in ("booked", "cancelled") and inv.get("booked_slot_utc"):
        return {"slots": [], "already_booked": True, "booked_slot_utc": inv["booked_slot_utc"]}
    applicant_tz = _resolve_tz(tz)
    avail = await _load_availability(inv["interviewer_user_id"])
    if not avail:
        raise HTTPException(
            status_code=409,
            detail="Interviewer availability is no longer configured.",
        )
    # Gather other booked slots for this interviewer in the next N days so we
    # don't double-book them.
    now_utc = datetime.now(timezone.utc)
    horizon = now_utc + timedelta(days=int(inv.get("lookahead_days") or DEFAULT_SLOT_LOOKAHEAD_DAYS))
    busy: list[tuple[datetime, datetime]] = []
    async for other in db[INTERVIEWS_COL].find(
        {
            "interviewer_user_id": inv["interviewer_user_id"],
            "status": {"$in": ["booked", "rescheduled"]},
            "slot_utc_iso": {"$gte": now_utc.isoformat(), "$lt": horizon.isoformat()},
        },
        {"_id": 0, "slot_utc_iso": 1, "duration_minutes": 1},
    ).limit(500):
        try:
            s = datetime.fromisoformat(str(other["slot_utc_iso"]).replace("Z", "+00:00"))
            d = timedelta(minutes=int(other.get("duration_minutes") or 45))
            busy.append((s, s + d))
        except Exception:
            continue

    slots_utc = _generate_free_slots_utc(
        avail=avail,
        busy_utc=busy,
        lookahead_days=int(inv.get("lookahead_days") or DEFAULT_SLOT_LOOKAHEAD_DAYS),
        duration_minutes=int(inv.get("duration_minutes") or 45),
        starting_from_utc=now_utc + timedelta(minutes=30),  # min 30 min lead time
    )
    # Render each slot in BOTH the applicant's TZ and the interviewer's TZ.
    interviewer_tz = _resolve_tz(inv.get("interviewer_tz") or DEFAULT_TZ)
    out = []
    for s_utc in slots_utc:
        out.append({
            "utc": s_utc.isoformat(),
            "applicant_local": s_utc.astimezone(applicant_tz).strftime("%Y-%m-%d %H:%M"),
            "applicant_label": s_utc.astimezone(applicant_tz).strftime("%a %b %d · %H:%M"),
            "interviewer_local": s_utc.astimezone(interviewer_tz).strftime("%Y-%m-%d %H:%M"),
            "interviewer_label": s_utc.astimezone(interviewer_tz).strftime("%a %b %d · %H:%M"),
        })
    return {
        "slots": out,
        "duration_minutes": int(inv.get("duration_minutes") or 45),
        "applicant_tz": str(applicant_tz),
        "interviewer_tz": str(interviewer_tz),
        "already_booked": False,
    }


class BookBody(BaseModel):
    slot_utc: str = Field(..., description="ISO-8601 UTC instant from /slots list")
    applicant_tz: str = Field(..., description="IANA zone (Intl.DateTimeFormat resolved)")
    applicant_notes: Optional[str] = Field(default=None, max_length=500)


async def _send_booking_confirmations(
    *,
    inv: dict[str, Any],
    slot_utc: datetime,
    applicant_tz: str,
):
    """Dispatch BOTH ICS invites + the confirmation email. Fail-safe."""
    try:
        from utils.email_service import is_email_configured, send_catalog_template
    except Exception as e:
        logger.warning(f"[careers/scheduling] email import failed: {e}")
        return

    if not is_email_configured():
        logger.info("[careers/scheduling] email not configured — skipping confirmations")
        return

    end_utc = slot_utc + timedelta(minutes=inv.get("duration_minutes") or 45)
    # Dual TZ-aware ICS — one rendered in the applicant's TZ, one in the
    # interviewer's. Each side's mail client renders its own ICS correctly
    # without silently re-converting.
    ics_app = build_interview_ics_tzaware(
        application_id=inv["application_id"],
        candidate_name=inv.get("candidate_name") or "",
        candidate_email=inv.get("candidate_email") or "",
        role_title=inv.get("role_title") or "",
        start_utc=slot_utc,
        duration_minutes=inv.get("duration_minutes") or 45,
        display_tz=applicant_tz,
        interview_type=inv.get("interview_type") or "video",
        video_url=inv.get("video_url") or "",
        organizer_email=inv.get("interviewer_email") or "hiring@realaicoach.app",
        organizer_name=inv.get("interviewer_name") or "RealAICoach Hiring",
        notes=inv.get("notes") or "",
        uid_suffix="applicant",
    )
    ics_int = build_interview_ics_tzaware(
        application_id=inv["application_id"],
        candidate_name=inv.get("candidate_name") or "",
        candidate_email=inv.get("candidate_email") or "",
        role_title=inv.get("role_title") or "",
        start_utc=slot_utc,
        duration_minutes=inv.get("duration_minutes") or 45,
        display_tz=inv.get("interviewer_tz") or DEFAULT_TZ,
        interview_type=inv.get("interview_type") or "video",
        video_url=inv.get("video_url") or "",
        organizer_email=inv.get("interviewer_email") or "hiring@realaicoach.app",
        organizer_name=inv.get("interviewer_name") or "RealAICoach Hiring",
        notes=inv.get("notes") or "",
        uid_suffix="interviewer",
    )

    title = f"Interview: {inv.get('role_title') or 'role'} · RealAICoach"
    details = (
        f"Interview for {inv.get('role_title') or 'the role'} at RealAICoach. "
        f"Candidate: {inv.get('candidate_name') or ''}. "
        f"Format: {(inv.get('interview_type') or 'video').title()}."
    )
    location = inv.get("video_url") or ""
    gcal = google_calendar_link(
        title=title, start_utc=slot_utc, end_utc=end_utc,
        details=details, location=location,
    )
    outlook = outlook_calendar_link(
        title=title, start_utc=slot_utc, end_utc=end_utc,
        details=details, location=location,
    )

    payload = {
        "applicant_name": inv.get("candidate_name") or "there",
        "interviewer_name": inv.get("interviewer_name") or "the team",
        "role_title": inv.get("role_title") or "the role",
        "slot_utc_iso": slot_utc.isoformat(),
        "applicant_local_str": slot_utc.astimezone(_resolve_tz(applicant_tz)).strftime(
            "%A %b %d, %Y · %H:%M %Z"
        ),
        "interviewer_local_str": slot_utc.astimezone(
            _resolve_tz(inv.get("interviewer_tz") or DEFAULT_TZ)
        ).strftime("%A %b %d, %Y · %H:%M %Z"),
        "duration_minutes": inv.get("duration_minutes") or 45,
        "google_calendar_url": gcal,
        "outlook_calendar_url": outlook,
        "video_url": inv.get("video_url") or "",
        "interview_type": inv.get("interview_type") or "video",
    }

    # Applicant confirmation
    if inv.get("candidate_email"):
        try:
            attachments = []
            if ics_app:
                attachments.append(ics_attachment(ics_app, filename="interview-your-time.ics"))
            await send_catalog_template(
                recipient_email=inv["candidate_email"],
                template_key="careers_scheduling_confirmation_applicant",
                recipient_name=inv.get("candidate_name") or "",
                attachments=attachments or None,
                **payload,
            )
        except Exception as e:
            logger.warning(f"[careers/scheduling] applicant confirm failed: {e}")

    # Interviewer confirmation (CC: none — goes straight to the interviewer)
    if inv.get("interviewer_email"):
        try:
            attachments = []
            if ics_int:
                attachments.append(ics_attachment(ics_int, filename="interview-interviewer.ics"))
            await send_catalog_template(
                recipient_email=inv["interviewer_email"],
                template_key="careers_scheduling_confirmation_interviewer",
                recipient_name=inv.get("interviewer_name") or "",
                attachments=attachments or None,
                **payload,
            )
        except Exception as e:
            logger.warning(f"[careers/scheduling] interviewer confirm failed: {e}")


@router.post("/careers/schedule/{token}/book")
async def public_book_slot(token: str, body: BookBody):
    inv = await _load_invite_or_404(token)
    if inv.get("status") in ("booked", "cancelled") and inv.get("booked_slot_utc"):
        raise HTTPException(
            status_code=409,
            detail=f"This interview is already {inv.get('status')}.",
        )
    try:
        slot_utc = datetime.fromisoformat(body.slot_utc.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid slot_utc ISO value")
    if slot_utc.tzinfo is None:
        slot_utc = slot_utc.replace(tzinfo=timezone.utc)
    if slot_utc < datetime.now(timezone.utc) + timedelta(minutes=15):
        raise HTTPException(status_code=422, detail="Slot is in the past or too soon")
    try:
        ZoneInfo(body.applicant_tz)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Unknown applicant timezone {body.applicant_tz!r}")

    now_iso = _now_iso()
    history = list(inv.get("history") or [])
    history.append({
        "event": "booked" if not inv.get("booked_slot_utc") else "rescheduled",
        "slot_utc": slot_utc.isoformat(),
        "applicant_tz": body.applicant_tz,
        "at": now_iso,
    })

    # Persist on the invite
    await db[SCHED_INVITE_COL].update_one(
        {"token": token},
        {"$set": {
            "status": "booked",
            "booked_slot_utc": slot_utc.isoformat(),
            "booked_at": now_iso,
            "applicant_tz": body.applicant_tz,
            "applicant_notes": (body.applicant_notes or "")[:500],
            "history": history,
        }},
    )

    # Also materialize an entry in careers_interviews so other parts of the
    # ATS (Upcoming Interviews widget, bulk-ICS, reminders) see it.
    interview_doc = {
        "interview_id": f"iv_{secrets.token_hex(6)}",
        "application_id": inv["application_id"],
        "scheduling_token": token,
        "slot_utc_iso": slot_utc.isoformat(),
        "duration_minutes": inv.get("duration_minutes") or 45,
        "interview_type": inv.get("interview_type") or "video",
        "video_url": inv.get("video_url") or "",
        "interviewer_user_id": inv.get("interviewer_user_id") or "",
        "interviewer_email": inv.get("interviewer_email") or "",
        "interviewer_name": inv.get("interviewer_name") or "",
        "interviewer_tz": inv.get("interviewer_tz") or DEFAULT_TZ,
        "candidate_email": inv.get("candidate_email") or "",
        "candidate_name": inv.get("candidate_name") or "",
        "applicant_tz": body.applicant_tz,
        "status": "booked",
        "created_at": now_iso,
        "self_booked": True,
    }
    await db[INTERVIEWS_COL].update_one(
        {"scheduling_token": token},
        {"$set": interview_doc},
        upsert=True,
    )

    # Also bump the application status so the ATS Kanban / status timeline
    # reflects the scheduled interview.
    try:
        await db[APPS_COL].update_one(
            {"application_id": inv["application_id"]},
            {"$set": {
                "status": "interview_scheduled",
                "last_status_change_at": now_iso,
                "next_interview_at_utc": slot_utc.isoformat(),
            }},
        )
    except Exception as e:
        logger.warning(f"[careers/scheduling] app status bump failed: {e}")

    # Fire confirmations (ICS + deep-links). Fail-safe.
    await _send_booking_confirmations(
        inv=inv, slot_utc=slot_utc, applicant_tz=body.applicant_tz,
    )

    return {
        "ok": True,
        "status": "booked",
        "slot_utc": slot_utc.isoformat(),
        "applicant_tz": body.applicant_tz,
    }


@router.post("/careers/schedule/{token}/reschedule")
async def public_reschedule_slot(token: str, body: BookBody):
    """Same effect as book(), but the invite must already be in 'booked'
    state — marks the previous booking with an audit entry."""
    inv = await _load_invite_or_404(token)
    if inv.get("status") != "booked":
        raise HTTPException(
            status_code=409,
            detail="Nothing booked yet — use /book instead of /reschedule.",
        )
    return await public_book_slot(token, body)  # reuses the write path


@router.get("/careers/scheduling/interview/{app_id}")
async def admin_get_interview(request: Request, app_id: str):
    """Admin read-back for the Upcoming Interviews widget + audit log."""
    await require_admin(request)
    iv = await db[INTERVIEWS_COL].find_one(
        {"application_id": app_id}, {"_id": 0}, sort=[("slot_utc_iso", -1)]
    )
    invites: list[dict[str, Any]] = []
    async for i in db[SCHED_INVITE_COL].find(
        {"application_id": app_id}, {"_id": 0},
    ).sort("created_at", -1).limit(10):
        invites.append(i)
    return {"interview": iv, "invites": invites}


# ─────────────────────────────────────────────────────────────────────────────
# Timezone-pain heatmap — aggregates booked slots into a weekday × hour grid
# rendered in the admin's (interviewer's) own TZ. Highlights which hours of
# their week get picked most by applicants, and reports the top applicant
# timezones driving demand. Turns Phase-1's stored instants into
# compounding scheduling intelligence.
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/careers/scheduling/tz-heatmap")
async def admin_get_tz_heatmap(
    request: Request,
    weeks: int = Query(12, ge=1, le=52, description="Window in weeks to look back."),
    interviewer_user_id: Optional[str] = Query(
        None, description="Override — defaults to the calling admin.",
    ),
):
    admin = await require_admin(request)
    admin_uid = getattr(admin, "user_id", None) or getattr(admin, "id", None) or ""
    uid = interviewer_user_id or admin_uid

    avail = await db[AVAIL_COL].find_one({"owner_user_id": uid}, {"_id": 0})
    display_tz_name = (avail or {}).get("tz") or DEFAULT_TZ
    display_tz = _resolve_tz(display_tz_name)

    since = datetime.now(timezone.utc) - timedelta(weeks=int(weeks))
    # Grid[weekday (0=Mon..6=Sun)][hour 0-23] = count
    grid: list[list[int]] = [[0] * 24 for _ in range(7)]
    applicant_tz_counter: dict[str, int] = {}
    total = 0

    async for iv in db[INTERVIEWS_COL].find(
        {
            "interviewer_user_id": uid,
            "status": {"$in": ["booked", "rescheduled"]},
            "slot_utc_iso": {"$gte": since.isoformat()},
        },
        {"_id": 0, "slot_utc_iso": 1, "applicant_tz": 1},
    ).limit(5000):
        try:
            s = datetime.fromisoformat(str(iv["slot_utc_iso"]).replace("Z", "+00:00"))
            local = s.astimezone(display_tz)
            grid[local.weekday()][local.hour] += 1
            total += 1
            tz = str(iv.get("applicant_tz") or "").strip() or "(unknown)"
            applicant_tz_counter[tz] = applicant_tz_counter.get(tz, 0) + 1
        except Exception:
            continue

    # Top 5 applicant timezones
    top_applicant_tzs = sorted(
        applicant_tz_counter.items(), key=lambda kv: kv[1], reverse=True
    )[:5]

    # Peak cell + suggestions
    peak_weekday = 0
    peak_hour = 9
    peak_count = 0
    for wd in range(7):
        for h in range(24):
            if grid[wd][h] > peak_count:
                peak_count = grid[wd][h]
                peak_weekday, peak_hour = wd, h

    # Build a compact insight string if we have real signal.
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    insight: str | None = None
    if total >= 3 and peak_count >= 2:
        pct = round(100 * peak_count / max(total, 1))
        insight = (
            f"{pct}% of booked interviews cluster at {weekday_labels[peak_weekday]} "
            f"{peak_hour:02d}:00 in {display_tz_name} — consider widening that hour "
            "and tightening low-demand cells."
        )
    elif total == 0:
        insight = (
            "No bookings in the look-back window yet. The heatmap will light up as "
            "applicants start self-booking via the scheduler."
        )

    return {
        "window_weeks": int(weeks),
        "interviewer_user_id": uid,
        "display_tz": display_tz_name,
        "total_bookings": total,
        "grid": grid,  # [weekday][hour] -> count
        "peak": {
            "weekday": peak_weekday,
            "weekday_label": weekday_labels[peak_weekday],
            "hour": peak_hour,
            "count": peak_count,
        },
        "top_applicant_tzs": [
            {"tz": tz, "count": n, "percent": round(100 * n / max(total, 1))}
            for tz, n in top_applicant_tzs
        ],
        "insight": insight,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-recruiter TZ-heatmap drill-down.
# Returns one summary row per interviewer so admins can switch the
# heatmap's `interviewer_user_id` filter from a dropdown instead of
# typing UIDs. Each row carries the interviewer's booking total, peak
# weekday/hour, and their #1 applicant timezone, so the picker itself
# acts as a mini leaderboard of "where is the TZ pain concentrated?".
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/careers/scheduling/tz-heatmap-recruiters")
async def admin_list_tz_heatmap_recruiters(
    request: Request,
    weeks: int = Query(12, ge=1, le=52),
):
    await require_admin(request)
    since = datetime.now(timezone.utc) - timedelta(weeks=int(weeks))
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Build per-interviewer accumulators in one pass.
    per_uid: dict[str, dict[str, Any]] = {}
    async for iv in db[INTERVIEWS_COL].find(
        {
            "status": {"$in": ["booked", "rescheduled"]},
            "slot_utc_iso": {"$gte": since.isoformat()},
        },
        {"_id": 0, "interviewer_user_id": 1, "slot_utc_iso": 1, "applicant_tz": 1},
    ).limit(10000):
        uid = str(iv.get("interviewer_user_id") or "").strip()
        if not uid:
            continue
        rec = per_uid.setdefault(uid, {
            "interviewer_user_id": uid,
            "total_bookings": 0,
            "grid": [[0] * 24 for _ in range(7)],
            "applicant_tzs": {},
            "display_tz": DEFAULT_TZ,
        })
        try:
            s = datetime.fromisoformat(str(iv["slot_utc_iso"]).replace("Z", "+00:00"))
            # NOTE: we need each recruiter's own TZ to render peak; look
            # it up lazily below (avoid an N+1 here — do it once per uid
            # after the scan).
            rec["_utc"] = rec.get("_utc", [])
            rec["_utc"].append(s)
            rec["total_bookings"] += 1
            tz = str(iv.get("applicant_tz") or "").strip() or "(unknown)"
            rec["applicant_tzs"][tz] = rec["applicant_tzs"].get(tz, 0) + 1
        except Exception:
            continue

    # Resolve display_tz per recruiter + compute peak in that TZ.
    avail_cache: dict[str, str] = {}
    if per_uid:
        async for a in db[AVAIL_COL].find(
            {"owner_user_id": {"$in": list(per_uid.keys())}},
            {"_id": 0, "owner_user_id": 1, "tz": 1},
        ):
            avail_cache[str(a.get("owner_user_id") or "")] = str(a.get("tz") or DEFAULT_TZ)

    # Pull recruiter display names in bulk so the dropdown shows a
    # human-friendly label instead of opaque UIDs.
    users_cache: dict[str, dict[str, str]] = {}
    if per_uid:
        async for u in db.users.find(
            {"user_id": {"$in": list(per_uid.keys())}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "full_name": 1},
        ):
            uid = str(u.get("user_id") or "")
            users_cache[uid] = {
                "email": str(u.get("email") or ""),
                "name": str(u.get("name") or u.get("full_name") or u.get("email") or uid),
            }

    out: list[dict[str, Any]] = []
    for uid, rec in per_uid.items():
        tz_name = avail_cache.get(uid, DEFAULT_TZ)
        tz_obj = _resolve_tz(tz_name)
        grid = [[0] * 24 for _ in range(7)]
        for s in rec.get("_utc", []):
            local = s.astimezone(tz_obj)
            grid[local.weekday()][local.hour] += 1
        peak_wd, peak_h, peak_c = 0, 9, 0
        for wd in range(7):
            for h in range(24):
                if grid[wd][h] > peak_c:
                    peak_c = grid[wd][h]
                    peak_wd, peak_h = wd, h

        top_tz_items = sorted(rec["applicant_tzs"].items(), key=lambda kv: kv[1], reverse=True)
        top_applicant_tz = top_tz_items[0][0] if top_tz_items else None

        u = users_cache.get(uid, {})
        out.append({
            "interviewer_user_id": uid,
            "email": u.get("email", ""),
            "display_name": u.get("name", uid),
            "display_tz": tz_name,
            "total_bookings": rec["total_bookings"],
            "peak": {
                "weekday": peak_wd,
                "weekday_label": weekday_labels[peak_wd],
                "hour": peak_h,
                "count": peak_c,
            },
            "top_applicant_tz": top_applicant_tz,
        })

    out.sort(key=lambda r: (-r["total_bookings"], r["display_name"].lower()))
    return {"window_weeks": int(weeks), "recruiters": out, "count": len(out)}


# ─────────────────────────────────────────────────────────────────────────────
# CSV export for the TZ-heatmap (single recruiter or all recruiters).
# Produces a long-format row-per-cell dataset that drops cleanly into
# Google Sheets / Excel / Looker — one row per (recruiter, weekday, hour)
# with the booking count. Paired with a second sheet of top-applicant-TZ
# rows so recruiters can scan both the hot cells and the applicant-side
# TZ distribution in one file.
#
# Shape — single CSV file with two sections separated by a blank row:
#
#   Section 1 — density grid:
#     recruiter_user_id,recruiter_name,recruiter_tz,weekday,weekday_label,hour,bookings
#
#   Section 2 — applicant-TZ distribution:
#     recruiter_user_id,recruiter_name,applicant_tz,bookings,percent
#
# Admin-only. When ``interviewer_user_id`` is omitted, exports every
# recruiter who has bookings in the window — this is the "Compliance CSV"
# deliverable the user asked for.
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/careers/scheduling/tz-heatmap.csv")
async def admin_tz_heatmap_csv(
    request: Request,
    weeks: int = Query(12, ge=1, le=52),
    interviewer_user_id: Optional[str] = Query(None),
):
    import csv
    import io

    from fastapi.responses import StreamingResponse

    admin = await require_admin(request)
    admin_uid = getattr(admin, "user_id", None) or getattr(admin, "id", None) or ""

    # Determine which recruiters to include.
    if interviewer_user_id:
        target_uids = [interviewer_user_id]
    else:
        # Every interviewer with any booking in the window.
        since_iso = (
            datetime.now(timezone.utc) - timedelta(weeks=int(weeks))
        ).isoformat()
        target_uids = []
        async for row in db[INTERVIEWS_COL].aggregate(
            [
                {
                    "$match": {
                        "status": {"$in": ["booked", "rescheduled"]},
                        "slot_utc_iso": {"$gte": since_iso},
                    }
                },
                {"$group": {"_id": "$interviewer_user_id"}},
            ]
        ):
            if row.get("_id"):
                target_uids.append(row["_id"])
        if not target_uids:
            target_uids = [admin_uid]  # still emit a header-only CSV

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    since = datetime.now(timezone.utc) - timedelta(weeks=int(weeks))

    # Recruiter name / TZ lookup
    users_cache: Dict[str, Dict[str, Any]] = {}
    async for u in db["users"].find(
        {"user_id": {"$in": target_uids}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1},
    ):
        users_cache[u["user_id"]] = u

    # Build the CSV in memory.
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "# Careers TZ Heatmap — Compliance CSV",
            f"window_weeks={int(weeks)}",
            f"generated_at={datetime.now(timezone.utc).isoformat()}",
            f"recruiter_count={len(target_uids)}",
        ]
    )
    w.writerow([])
    w.writerow(
        [
            "recruiter_user_id",
            "recruiter_name",
            "recruiter_tz",
            "weekday",
            "weekday_label",
            "hour",
            "bookings",
        ]
    )

    # Second-section buffer: collect applicant-TZ rows while iterating.
    tz_rows: list[list[Any]] = []

    for uid in target_uids:
        avail = await db[AVAIL_COL].find_one({"owner_user_id": uid}, {"_id": 0})
        display_tz_name = (avail or {}).get("tz") or DEFAULT_TZ
        display_tz = _resolve_tz(display_tz_name)
        recruiter_name = (users_cache.get(uid, {}).get("name") or uid)

        grid = [[0] * 24 for _ in range(7)]
        applicant_tz_counter: Dict[str, int] = {}
        total = 0

        async for iv in db[INTERVIEWS_COL].find(
            {
                "interviewer_user_id": uid,
                "status": {"$in": ["booked", "rescheduled"]},
                "slot_utc_iso": {"$gte": since.isoformat()},
            },
            {"_id": 0, "slot_utc_iso": 1, "applicant_tz": 1},
        ).limit(5000):
            try:
                s = datetime.fromisoformat(
                    str(iv["slot_utc_iso"]).replace("Z", "+00:00")
                )
                local = s.astimezone(display_tz)
                grid[local.weekday()][local.hour] += 1
                total += 1
                tz = str(iv.get("applicant_tz") or "").strip() or "(unknown)"
                applicant_tz_counter[tz] = applicant_tz_counter.get(tz, 0) + 1
            except Exception:
                continue

        # Emit the 7×24 cells — skip zero-count rows to keep the file
        # focused on actual activity (but include a summary row when
        # the recruiter has zero bookings so recruiters aren't missing
        # from the output entirely).
        any_written = False
        for wd in range(7):
            for h in range(24):
                count = grid[wd][h]
                if count == 0:
                    continue
                w.writerow(
                    [
                        uid,
                        recruiter_name,
                        display_tz_name,
                        wd,
                        weekday_labels[wd],
                        h,
                        count,
                    ]
                )
                any_written = True
        if not any_written:
            w.writerow(
                [uid, recruiter_name, display_tz_name, "", "", "", 0]
            )

        # Stash applicant-TZ summary rows for section 2.
        for tz, n in sorted(
            applicant_tz_counter.items(), key=lambda kv: kv[1], reverse=True
        )[:20]:
            tz_rows.append(
                [
                    uid,
                    recruiter_name,
                    tz,
                    n,
                    round(100 * n / max(total, 1)),
                ]
            )

    # Section 2.
    w.writerow([])
    w.writerow(
        [
            "recruiter_user_id",
            "recruiter_name",
            "applicant_tz",
            "bookings",
            "percent_of_recruiter_bookings",
        ]
    )
    for r in tz_rows:
        w.writerow(r)

    csv_bytes = buf.getvalue().encode("utf-8")
    fname = (
        f"careers-tz-heatmap-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    )
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Export-Rows": str(len(tz_rows)),
            "X-Export-Recruiters": str(len(target_uids)),
        },
    )


__all__ = ["router", "_generate_free_slots_utc"]
