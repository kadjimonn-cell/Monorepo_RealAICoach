"""
ICS (RFC 5545) VCALENDAR builder for interview invites.

Small, dependency-free. Produces a VCALENDAR:VEVENT string that Gmail /
Outlook / Apple Mail render as a native "Add to calendar" prompt.
"""
from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

_BRAND = "RealAICoach"


def _escape(text: str) -> str:
    """Escape commas, semicolons, backslashes and newlines per RFC 5545."""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _fold(line: str) -> str:
    """RFC 5545 line-folding at 75 octets — CRLF + single space continuation."""
    if len(line) <= 75:
        return line
    out = []
    while len(line) > 75:
        out.append(line[:75])
        line = " " + line[75:]
    out.append(line)
    return "\r\n".join(out)


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_slot(date_iso: str, time_hhmm: str) -> Optional[datetime]:
    """Parse YYYY-MM-DD + HH:MM into an aware UTC datetime. Returns None on failure."""
    if not date_iso or not time_hhmm:
        return None
    m = re.match(r"^(\d{2}):(\d{2})$", time_hhmm.strip())
    if not m:
        return None
    try:
        y, mo, d = [int(x) for x in date_iso.split("-")]
        h = int(m.group(1))
        mi = int(m.group(2))
        return datetime(y, mo, d, h, mi, 0, tzinfo=timezone.utc)
    except Exception:
        return None


def build_interview_ics(
    *,
    application_id: str,
    candidate_name: str,
    candidate_email: str,
    role_title: str,
    interview_date: str,
    interview_time: str,
    duration_minutes: int = 45,
    interview_type: str = "video",
    video_url: str = "",
    organizer_email: str = "hiring@realaicoach.app",
    organizer_name: str = f"{_BRAND} Hiring",
    notes: str = "",
    method: str = "REQUEST",
) -> Optional[str]:
    """Return a single-event VCALENDAR string, or None if the slot cannot be parsed."""
    start = _parse_slot(interview_date, interview_time)
    if not start:
        return None
    duration = max(15, min(int(duration_minutes or 45), 240))
    end = start + timedelta(minutes=duration)
    now = datetime.now(timezone.utc)

    # Deterministic UID so re-sends update the same event in the candidate's calendar.
    uid_source = f"{application_id}|{interview_date}|{interview_time}"
    uid_hash = hashlib.sha256(uid_source.encode("utf-8")).hexdigest()[:24]
    uid = f"iv-{uid_hash}@realaicoach.app"

    type_label = (interview_type or "video").lower()
    summary = f"Interview: {role_title} · {_BRAND}"
    location = video_url if type_label in ("video", "video-call") and video_url else (
        "Phone interview" if type_label == "phone" else
        "On-site — details to follow" if type_label == "onsite" else
        video_url or ""
    )
    desc_lines = [
        f"Interview for {role_title} at {_BRAND}.",
        f"Candidate: {candidate_name}",
        f"Format: {type_label.title()}",
    ]
    if video_url:
        desc_lines.append(f"Join link: {video_url}")
    if notes:
        desc_lines.append("")
        desc_lines.append(notes.strip())
    description = "\n".join(desc_lines)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{_BRAND}//Interview Invite//EN",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_fmt_utc(now)}",
        f"DTSTART:{_fmt_utc(start)}",
        f"DTEND:{_fmt_utc(end)}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        f"LOCATION:{_escape(location)}",
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "TRANSP:OPAQUE",
        f"ORGANIZER;CN={_escape(organizer_name)}:mailto:{organizer_email}",
        f"ATTENDEE;CN={_escape(candidate_name)};ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{candidate_email}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Interview reminder",
        "TRIGGER:-PT30M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def ics_attachment(ics: str, filename: str = "interview.ics") -> dict:
    """Wrap an ICS string into Resend's attachment shape."""
    return {
        "filename": filename if filename.endswith(".ics") else f"{filename}.ics",
        "content": base64.b64encode(ics.encode("utf-8")).decode("ascii"),
        "content_type": "text/calendar; charset=utf-8; method=REQUEST",
    }


# ─────────────────────────────────────────────────────────────────────────────
# TZ-aware ICS (Phase 1 scheduling)
# ─────────────────────────────────────────────────────────────────────────────

def _vtimezone_block(tz_name: str, anchor_utc: datetime) -> list[str]:
    """Emit a minimal, correct VTIMEZONE block for the named IANA zone at the
    moment ``anchor_utc`` falls on. We compute the current UTC offset + DST
    offset (if any) and emit a single STANDARD (or DAYLIGHT) component so
    Gmail / Apple Mail / Outlook render the local time correctly WITHOUT
    silently re-converting to the reader's TZ.

    We deliberately do NOT emit a full year's rolling RRULE — for single-
    event invites, the instant-anchored block is unambiguous, lightweight,
    and DST-safe. Returns a list of ICS content lines (no CRLFs)."""
    try:
        from zoneinfo import ZoneInfo
    except Exception:
        return []
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        return []

    local = anchor_utc.astimezone(tz)
    offset_now = local.utcoffset() or timedelta(0)
    dst_now = local.dst() or timedelta(0)
    is_dst = dst_now != timedelta(0)

    # "Standard" offset = current offset minus any DST component
    std_offset = offset_now - dst_now

    def _fmt_offset(td: timedelta) -> str:
        total = int(td.total_seconds())
        sign = "+" if total >= 0 else "-"
        total = abs(total)
        h = total // 3600
        m = (total % 3600) // 60
        return f"{sign}{h:02d}{m:02d}"

    # DTSTART for the sub-component is a local-time marker (no Z)
    dtstart_local = local.strftime("%Y%m%dT%H%M%S")
    tzname_abbr = local.tzname() or tz_name
    sub_name = "DAYLIGHT" if is_dst else "STANDARD"
    # In the STANDARD branch DST is zero, so tzoffsetfrom == tzoffsetto.
    # In the DAYLIGHT branch we came FROM standard TO standard+dst.
    tzoffsetfrom = _fmt_offset(std_offset)
    tzoffsetto = _fmt_offset(offset_now)

    return [
        "BEGIN:VTIMEZONE",
        f"TZID:{tz_name}",
        f"BEGIN:{sub_name}",
        f"DTSTART:{dtstart_local}",
        f"TZOFFSETFROM:{tzoffsetfrom}",
        f"TZOFFSETTO:{tzoffsetto}",
        f"TZNAME:{tzname_abbr}",
        f"END:{sub_name}",
        "END:VTIMEZONE",
    ]


def _fmt_local(dt_utc: datetime, tz_name: str) -> str:
    """Render ``dt_utc`` as a floating local-time string YYYYMMDDTHHMMSS in the
    named zone. Used for DTSTART;TZID=... values. Falls back to UTC ``Z`` if
    the zone is invalid."""
    try:
        from zoneinfo import ZoneInfo
        return dt_utc.astimezone(ZoneInfo(tz_name)).strftime("%Y%m%dT%H%M%S")
    except Exception:
        return _fmt_utc(dt_utc)


def build_interview_ics_tzaware(
    *,
    application_id: str,
    candidate_name: str,
    candidate_email: str,
    role_title: str,
    start_utc: datetime,
    duration_minutes: int = 45,
    display_tz: str = "UTC",
    interview_type: str = "video",
    video_url: str = "",
    organizer_email: str = "hiring@realaicoach.app",
    organizer_name: str = f"{_BRAND} Hiring",
    notes: str = "",
    method: str = "REQUEST",
    uid_suffix: str = "",
) -> Optional[str]:
    """TZ-aware VCALENDAR builder. Emits a VTIMEZONE block and anchors
    DTSTART/DTEND via TZID so each side's calendar (applicant / interviewer)
    gets a native "Add to calendar" prompt rendered in THEIR displayed
    local time — without the mail client silently re-converting.

    Pass the same ``start_utc`` to both the applicant's TZ build and the
    interviewer's TZ build — the UTC instant is identical; only the TZID
    frame differs."""
    if not isinstance(start_utc, datetime) or start_utc.tzinfo is None:
        return None
    start_utc = start_utc.astimezone(timezone.utc)
    duration = max(15, min(int(duration_minutes or 45), 240))
    end_utc = start_utc + timedelta(minutes=duration)
    now = datetime.now(timezone.utc)

    # Deterministic UID so a reschedule updates the same calendar event.
    # Include uid_suffix so applicant + interviewer ICS files don't merge
    # into one event on a shared Google Workspace calendar.
    uid_base = f"{application_id}|{start_utc.isoformat()}|{uid_suffix}"
    uid_hash = hashlib.sha256(uid_base.encode("utf-8")).hexdigest()[:24]
    uid = f"iv-{uid_hash}@realaicoach.app"

    type_label = (interview_type or "video").lower()
    summary = f"Interview: {role_title} · {_BRAND}"
    if type_label in ("video", "video-call") and video_url:
        location = video_url
    elif type_label == "phone":
        location = "Phone interview"
    elif type_label == "onsite":
        location = "On-site — details to follow"
    else:
        location = video_url or ""

    desc_lines = [
        f"Interview for {role_title} at {_BRAND}.",
        f"Candidate: {candidate_name}",
        f"Format: {type_label.title()}",
    ]
    if video_url:
        desc_lines.append(f"Join link: {video_url}")
    if notes:
        desc_lines.append("")
        desc_lines.append(notes.strip())
    description = "\n".join(desc_lines)

    tz_block = _vtimezone_block(display_tz, start_utc)
    if tz_block:
        dtstart_line = f"DTSTART;TZID={display_tz}:{_fmt_local(start_utc, display_tz)}"
        dtend_line = f"DTEND;TZID={display_tz}:{_fmt_local(end_utc, display_tz)}"
    else:
        # Fallback to UTC if zoneinfo can't resolve the zone — still valid ICS.
        dtstart_line = f"DTSTART:{_fmt_utc(start_utc)}"
        dtend_line = f"DTEND:{_fmt_utc(end_utc)}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{_BRAND}//Interview Invite//EN",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
        *tz_block,
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_fmt_utc(now)}",
        dtstart_line,
        dtend_line,
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        f"LOCATION:{_escape(location)}",
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "TRANSP:OPAQUE",
        f"ORGANIZER;CN={_escape(organizer_name)}:mailto:{organizer_email}",
        f"ATTENDEE;CN={_escape(candidate_name)};ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{candidate_email}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Interview reminder",
        "TRIGGER:-PT30M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def google_calendar_link(
    *, title: str, start_utc: datetime, end_utc: datetime, details: str = "",
    location: str = "",
) -> str:
    """Single-click Google Calendar "add event" URL. Date spec is UTC Zulu."""
    from urllib.parse import urlencode
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{_fmt_utc(start_utc)}/{_fmt_utc(end_utc)}",
        "details": details,
        "location": location,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def outlook_calendar_link(
    *, title: str, start_utc: datetime, end_utc: datetime, details: str = "",
    location: str = "",
) -> str:
    """Single-click Outlook.com "add event" URL (ISO-8601 with offset)."""
    from urllib.parse import urlencode
    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": title,
        "startdt": start_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enddt": end_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "body": details,
        "location": location,
    }
    return "https://outlook.live.com/calendar/0/deeplink/compose?" + urlencode(params)
