"""i18n language guidance routes."""

from fastapi import HTTPException, Request
from datetime import datetime, timezone, timedelta

from ..db import db, require_auth

from .constants import COUNTRY_LANGUAGE_HINTS
from .helpers import router, _get_user_language_code, _safe_parse_iso, _guidance_copy

@router.get("/language-guidance")
async def get_language_guidance(request: Request):
    user = await require_auth(request)
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "country": 1, "currency_preference": 1})
    country = str((user_doc or {}).get("country") or "US").upper()
    expected_language = COUNTRY_LANGUAGE_HINTS.get(country, "en")

    preferred_language = await _get_user_language_code(user.user_id)
    mismatch = preferred_language != expected_language

    now = datetime.now(timezone.utc)
    pref_doc = await db.user_guidance_preferences.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "dismissed_until": 1, "snoozed_until": 1, "last_action": 1},
    )
    dismiss_until = _safe_parse_iso(str((pref_doc or {}).get("dismissed_until") or ""))
    snooze_until = _safe_parse_iso(str((pref_doc or {}).get("snoozed_until") or ""))
    suppress_until_candidates = [dt for dt in [dismiss_until, snooze_until] if dt]
    suppress_until = max(suppress_until_candidates) if suppress_until_candidates else None
    suppressed = bool(suppress_until and suppress_until > now)
    suppress_reason = "dismissed" if dismiss_until and dismiss_until == suppress_until else "snoozed" if suppressed else None

    settings_url = "/language-selector"
    guidance = _guidance_copy(preferred_language, expected_language, settings_url)

    notification_id = None
    if mismatch and not suppressed:
        dedupe_key = f"language-guidance-{user.user_id}-{now.date().isoformat()}"
        existing = await db.system_events.find_one({"event_key": dedupe_key}, {"_id": 0, "event_key": 1})
        if not existing:
            created_at = now.isoformat()
            notif_payload = {
                "id": f"guidance_{user.user_id}_{int(now.timestamp())}",
                "user_id": user.user_id,
                "type": "language_guidance",
                "title": guidance["title"],
                "message": guidance["message"],
                "read": False,
                "created_at": created_at,
                "metadata": {
                    "suggested_language": expected_language,
                    "settings_url": settings_url,
                },
            }
            await db.notifications.insert_one(notif_payload)
            await db.system_events.insert_one({
                "event_key": dedupe_key,
                "event_type": "language_guidance_dedupe",
                "user_id": user.user_id,
                "created_at": created_at,
            })
            notification_id = notif_payload["id"]

    return {
        "show": mismatch and not suppressed,
        "suppressed": suppressed,
        "suppress_reason": suppress_reason,
        "suppress_until": suppress_until.isoformat() if suppress_until else None,
        "country": country,
        "preferred_language": preferred_language,
        "expected_language": expected_language,
        "guidance": guidance,
        "notification_id": notification_id,
    }


@router.post("/language-guidance/preference")
async def set_language_guidance_preference(request: Request):
    """Persist cross-device snooze/dismiss preference for language/currency mismatch hints."""
    user = await require_auth(request)
    body = await request.json()
    action = str(body.get("action") or "").strip().lower()
    if action not in {"dismiss", "snooze", "clear"}:
        raise HTTPException(status_code=400, detail="action must be one of: dismiss, snooze, clear")

    now = datetime.now(timezone.utc)
    snooze_hours = int(body.get("snooze_hours") or 24)
    snooze_hours = max(1, min(168, snooze_hours))

    update = {
        "updated_at": now.isoformat(),
        "last_action": action,
    }
    if action == "clear":
        update.update({"dismissed_until": None, "snoozed_until": None})
    elif action == "dismiss":
        update.update({"dismissed_until": (now + timedelta(hours=snooze_hours)).isoformat()})
    elif action == "snooze":
        update.update({"snoozed_until": (now + timedelta(hours=snooze_hours)).isoformat()})

    await db.user_guidance_preferences.update_one(
        {"user_id": user.user_id},
        {"$set": update},
        upsert=True,
    )

    return {
        "success": True,
        "action": action,
        "snooze_hours": snooze_hours,
        "updated_at": update["updated_at"],
    }


@router.post("/language-guidance/event")
async def track_language_guidance_event(request: Request):
    user = await require_auth(request)
    body = await request.json()
    event_type = str(body.get("event_type") or "").strip().lower()
    if event_type not in {"open", "dismiss", "switch", "remediation_success"}:
        raise HTTPException(status_code=400, detail="Unsupported event_type")

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "country": 1})
    country = str(body.get("country") or (user_doc or {}).get("country") or "US").upper()
    now = datetime.now(timezone.utc).isoformat()
    event = {
        "id": f"lge_{user.user_id}_{int(datetime.now(timezone.utc).timestamp()*1000)}",
        "user_id": user.user_id,
        "event_type": event_type,
        "country": country,
        "source": str(body.get("source") or "unknown"),
        "metadata": body.get("metadata") or {},
        "created_at": now,
    }
    await db.language_guidance_events.insert_one(event)
    return {"success": True, "event_id": event["id"]}


