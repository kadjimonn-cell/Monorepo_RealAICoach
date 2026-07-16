"""AI Smart Scheduling Assistant.

Features:
- Proactively suggest optimal meeting times based on user behavior
- Auto-fill empty calendar slots with recommendations
- Smart conflict detection and resolution
- Analyze user patterns for scheduling preferences
"""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
import uuid
import logging

from .db import db, require_auth

router = APIRouter(prefix="/smart-schedule")
logger = logging.getLogger("routes.smart_schedule_ai")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


async def _get_busy_slots(user_id: str, date_str: str) -> list:
    """Get all busy time slots for a user on a specific date."""
    next_day = (datetime.fromisoformat(date_str) + timedelta(days=1)).isoformat()[:10]
    busy = []

    # Calendar events
    events = await db.calendar_events.find(
        {"user_id": user_id, "start": {"$gte": date_str, "$lt": next_day}}, {"_id": 0, "start": 1, "end": 1, "title": 1}
    ).to_list(50)
    for e in events:
        busy.append({"start": e["start"], "end": e["end"], "type": "calendar", "title": e.get("title", "Event")})

    # Bookings
    bookings = await db.calendar_bookings.find(
        {"user_id": user_id, "status": "confirmed", "start": {"$gte": date_str, "$lt": next_day}},
        {"_id": 0, "start": 1, "end": 1, "guest_name": 1},
    ).to_list(50)
    for b in bookings:
        busy.append(
            {
                "start": b["start"],
                "end": b["end"],
                "type": "booking",
                "title": f"Meeting: {b.get('guest_name', 'Guest')}",
            }
        )

    # Interviews
    interviews = await db.interview_bookings.find(
        {
            "$or": [{"employer_id": user_id}, {"candidate_id": user_id}],
            "status": {"$in": ["scheduled", "confirmed"]},
            "scheduled_time": {"$gte": date_str, "$lt": next_day},
        },
        {"_id": 0, "scheduled_time": 1, "duration_minutes": 1},
    ).to_list(50)
    for iv in interviews:
        start = iv["scheduled_time"]
        dur = iv.get("duration_minutes", 30)
        end = (datetime.fromisoformat(start) + timedelta(minutes=dur)).isoformat()
        busy.append({"start": start, "end": end, "type": "interview", "title": "Interview"})

    return sorted(busy, key=lambda s: s["start"])


async def _analyze_user_patterns(user_id: str) -> dict:
    """Analyze user's scheduling patterns for smart suggestions."""
    # Get recent bookings to find preferred times
    recent = (
        await db.calendar_bookings.find(
            {"user_id": user_id, "status": "confirmed"}, {"_id": 0, "start": 1, "duration": 1}
        )
        .sort("start", -1)
        .limit(20)
        .to_list(20)
    )

    hour_counts = {}
    day_counts = {}
    durations = []

    for b in recent:
        try:
            dt = datetime.fromisoformat(b["start"])
            hour = dt.hour
            day = dt.weekday()
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
            day_counts[day] = day_counts.get(day, 0) + 1
            if b.get("duration"):
                durations.append(b["duration"])
        except (ValueError, KeyError):
            continue

    preferred_hours = sorted(hour_counts.items(), key=lambda x: -x[1])[:3]
    preferred_days = sorted(day_counts.items(), key=lambda x: -x[1])[:3]

    return {
        "preferred_hours": [h for h, _ in preferred_hours] if preferred_hours else [9, 10, 14],
        "preferred_days": [d for d, _ in preferred_days] if preferred_days else [0, 1, 2, 3, 4],
        "avg_duration": int(sum(durations) / len(durations)) if durations else 30,
        "total_meetings": len(recent),
    }


@router.get("/suggestions")
async def get_scheduling_suggestions(request: Request, days_ahead: int = 7):
    """Get AI-powered scheduling suggestions for optimal meeting times."""
    user = await require_auth(request)
    uid = user.user_id
    now = datetime.now(timezone.utc)
    patterns = await _analyze_user_patterns(uid)

    suggestions = []
    for day_offset in range(1, min(days_ahead + 1, 15)):
        target = now + timedelta(days=day_offset)
        date_str = target.strftime("%Y-%m-%d")
        day_name = DAYS[target.weekday()]

        # Skip weekends unless user prefers them
        if target.weekday() >= 5 and target.weekday() not in patterns["preferred_days"]:
            continue

        busy = await _get_busy_slots(uid, date_str)
        busy_hours = set()
        for slot in busy:
            try:
                start_h = datetime.fromisoformat(slot["start"]).hour
                end_h = datetime.fromisoformat(slot["end"]).hour
                for h in range(start_h, end_h + 1):
                    busy_hours.add(h)
            except (ValueError, KeyError):
                continue

        # Find open slots during preferred hours (fallback to 9-17)
        check_hours = patterns["preferred_hours"] + [h for h in range(9, 17) if h not in patterns["preferred_hours"]]
        for hour in check_hours:
            if hour not in busy_hours and 8 <= hour <= 18:
                # Calculate confidence based on preference match
                is_preferred_hour = hour in patterns["preferred_hours"]
                is_preferred_day = target.weekday() in patterns["preferred_days"]
                confidence = 0.5
                if is_preferred_hour:
                    confidence += 0.25
                if is_preferred_day:
                    confidence += 0.2
                if len(busy) == 0:
                    confidence += 0.05

                slot_start = f"{date_str}T{hour:02d}:00:00"
                slot_end = f"{date_str}T{hour:02d}:{patterns['avg_duration']:02d}:00"

                suggestions.append(
                    {
                        "id": f"sug_{uuid.uuid4().hex[:8]}",
                        "date": date_str,
                        "day": day_name,
                        "start_time": f"{hour:02d}:00",
                        "end_time": f"{hour:02d}:{patterns['avg_duration']:02d}",
                        "start_iso": slot_start,
                        "end_iso": slot_end,
                        "duration": patterns["avg_duration"],
                        "confidence": round(confidence, 2),
                        "reason": f"{'Preferred time' if is_preferred_hour else 'Available slot'} on {'preferred' if is_preferred_day else ''} {day_name}",
                        "busy_slots_that_day": len(busy),
                    }
                )
                break  # One suggestion per day

    suggestions.sort(key=lambda s: -s["confidence"])

    return {
        "suggestions": suggestions[:7],
        "patterns": patterns,
        "generated_at": now.isoformat(),
    }


@router.get("/conflicts")
async def detect_conflicts(request: Request, days_ahead: int = 7):
    """Detect scheduling conflicts in the user's calendar."""
    user = await require_auth(request)
    now = datetime.now(timezone.utc)
    conflicts = []

    for day_offset in range(0, days_ahead):
        target = now + timedelta(days=day_offset)
        date_str = target.strftime("%Y-%m-%d")
        busy = await _get_busy_slots(user.user_id, date_str)

        for i in range(len(busy)):
            for j in range(i + 1, len(busy)):
                try:
                    end_i = datetime.fromisoformat(busy[i]["end"])
                    start_j = datetime.fromisoformat(busy[j]["start"])
                    if end_i > start_j:
                        conflicts.append(
                            {
                                "date": date_str,
                                "slot_a": busy[i],
                                "slot_b": busy[j],
                                "overlap_minutes": int((end_i - start_j).total_seconds() / 60),
                            }
                        )
                except (ValueError, KeyError):
                    continue

    return {"conflicts": conflicts, "has_conflicts": len(conflicts) > 0, "checked_days": days_ahead}


@router.get("/availability/{date}")
async def get_availability(date: str, request: Request):
    """Get hourly availability for a specific date."""
    user = await require_auth(request)
    busy = await _get_busy_slots(user.user_id, date)

    busy_hours = {}
    for slot in busy:
        try:
            start_h = datetime.fromisoformat(slot["start"]).hour
            end_h = datetime.fromisoformat(slot["end"]).hour
            for h in range(start_h, end_h + 1):
                busy_hours[h] = slot.get("title", "Busy")
        except (ValueError, KeyError):
            continue

    hours = []
    for h in range(7, 21):
        hours.append(
            {
                "hour": h,
                "time": f"{h:02d}:00",
                "available": h not in busy_hours,
                "event": busy_hours.get(h, None),
            }
        )

    return {
        "date": date,
        "hours": hours,
        "available_count": sum(1 for h in hours if h["available"]),
        "busy_count": sum(1 for h in hours if not h["available"]),
    }


@router.get("/weekly-overview")
async def weekly_overview(request: Request):
    """Get a weekly scheduling overview with availability summary."""
    user = await require_auth(request)
    now = datetime.now(timezone.utc)
    days = []

    for offset in range(7):
        target = now + timedelta(days=offset)
        date_str = target.strftime("%Y-%m-%d")
        busy = await _get_busy_slots(user.user_id, date_str)

        busy_count = len(busy)
        available_hours = 0
        busy_hours_set = set()
        for slot in busy:
            try:
                start_h = datetime.fromisoformat(slot["start"]).hour
                end_h = datetime.fromisoformat(slot["end"]).hour
                for h in range(start_h, end_h + 1):
                    busy_hours_set.add(h)
            except (ValueError, KeyError):
                continue

        for h in range(9, 17):
            if h not in busy_hours_set:
                available_hours += 1

        days.append(
            {
                "date": date_str,
                "day": DAYS[target.weekday()],
                "is_today": offset == 0,
                "meetings": busy_count,
                "available_hours": available_hours,
                "utilization": round((8 - available_hours) / 8 * 100) if available_hours < 8 else 0,
            }
        )

    return {"days": days, "total_meetings": sum(d["meetings"] for d in days)}
