"""Notifications routes: in-app notifications, push token management, notification settings, daily briefings."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import os
import json
import uuid
import httpx
from bson import ObjectId
from .db import db, logger, get_current_user

router = APIRouter()


def _sanitize_notification_payload(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_notification_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_notification_payload(v) for v in value]
    return value


def _normalize_notification_identifiers(notification_ids: List[str]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for raw in notification_ids:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _notification_identifier_filter(notification_ids: List[str]) -> dict:
    normalized = _normalize_notification_identifiers(notification_ids)
    return {
        "$or": [
            {"notification_id": {"$in": normalized}},
            {"id": {"$in": normalized}},
        ]
    }


def _notification_base_query(user_id: str, *, include_archived: bool = False) -> dict:
    from utils.notification_helper import SYSTEM_SUPPRESSED_TYPES
    query: dict = {
        "user_id": user_id,
        "type": {"$nin": list(SYSTEM_SUPPRESSED_TYPES), "$not": {"$regex": "^gps_", "$options": "i"}},
    }
    if not include_archived:
        query["archived"] = {"$ne": True}
    return query

# VAPID config for web push (reuse from env)
_raw_vapid_private = os.environ.get("VAPID_PRIVATE_KEY", "")
_VAPID_PRIVATE_KEY = _raw_vapid_private.replace("\\n", "\n") if "\\n" in _raw_vapid_private else _raw_vapid_private
_VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@realaicoach.app")


# ── Push Token Management ──


class PushTokenRequest(BaseModel):
    push_token: str
    platform: Optional[str] = "expo"


class WebPushSubscription(BaseModel):
    endpoint: str
    keys: dict


@router.post("/notifications/push-token")
async def register_push_token(request: PushTokenRequest, req: Request):
    """Register or update a user's Expo push token."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.push_tokens.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "user_id": user.user_id,
                "token": request.push_token,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"success": True, "message": "Push token registered"}


@router.post("/notifications/web-push/subscribe")
async def register_web_push(subscription: WebPushSubscription, req: Request):
    """Register a Web Push API subscription for browser notifications."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.web_push_subscriptions.update_one(
        {"user_id": user.user_id, "endpoint": subscription.endpoint},
        {
            "$set": {
                "user_id": user.user_id,
                "endpoint": subscription.endpoint,
                "keys": subscription.keys,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"success": True, "message": "Web push subscription registered"}


@router.delete("/notifications/web-push/unsubscribe")
async def unregister_web_push(req: Request):
    """Remove Web Push subscription."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.web_push_subscriptions.delete_many({"user_id": user.user_id})
    return {"success": True}


@router.delete("/notifications/push-token")
async def remove_push_token(req: Request):
    """Remove push token on logout."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.push_tokens.delete_many({"user_id": user.user_id})
    return {"success": True}


# ── Notification Settings ──


class NotificationSettingsUpdate(BaseModel):
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    daily_briefing: Optional[bool] = None
    practice_reminders: Optional[bool] = None
    achievement_alerts: Optional[bool] = None
    weekly_digest: Optional[bool] = None
    team_updates: Optional[bool] = None
    goal_reminders: Optional[bool] = None
    coaching_nudges: Optional[bool] = None
    coaching_digest_push: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class NotificationBulkActionRequest(BaseModel):
    notification_ids: List[str] = []


DEFAULT_SETTINGS = {
    "push_enabled": True,
    "email_enabled": True,
    "daily_briefing": True,
    "practice_reminders": True,
    "achievement_alerts": True,
    "weekly_digest": True,
    "team_updates": True,
    "goal_reminders": True,
    "coaching_nudges": True,
    "coaching_digest_push": True,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
}


@router.get("/notifications/settings")
async def get_notification_settings(req: Request):
    """Get user's notification preferences."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    doc = await db.notification_settings.find_one({"user_id": user.user_id}, {"_id": 0})
    # Always merge with defaults so every field is present
    merged = {**DEFAULT_SETTINGS, "user_id": user.user_id}
    if doc:
        merged.update({k: v for k, v in doc.items() if v is not None})
    return merged


@router.get("/notifications/preferences")
async def get_notification_preferences(req: Request):
    """Compatibility alias for notification preferences."""
    return await get_notification_settings(req)


@router.put("/notifications/settings")
async def update_notification_settings(body: NotificationSettingsUpdate, req: Request):
    """Update user's notification preferences."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No settings to update")

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.notification_settings.update_one(
        {"user_id": user.user_id},
        {"$set": {**update_data, "user_id": user.user_id}},
        upsert=True,
    )

    doc = await db.notification_settings.find_one({"user_id": user.user_id}, {"_id": 0})
    return doc


@router.post("/notifications/preferences")
async def update_notification_preferences(body: NotificationSettingsUpdate, req: Request):
    """Compatibility alias for notification preferences updates."""
    return await update_notification_settings(body, req)


# ── Send Push Notification ──


async def send_push_notification(user_id: str, title: str, body: str, data: dict = None):
    """Send a push notification to a user via Expo Push API + Web Push. Respects quiet hours."""
    settings = await db.notification_settings.find_one({"user_id": user_id}, {"_id": 0})
    if settings and not settings.get("push_enabled", True):
        return False

    # Check quiet hours
    if settings and settings.get("quiet_hours_enabled"):
        now_hour = datetime.now(timezone.utc).hour
        now_min = datetime.now(timezone.utc).minute
        now_time = now_hour * 60 + now_min
        try:
            sh, sm = map(int, settings.get("quiet_hours_start", "22:00").split(":"))
            eh, em = map(int, settings.get("quiet_hours_end", "07:00").split(":"))
            start = sh * 60 + sm
            end = eh * 60 + em
            if start > end:  # overnight (e.g. 22:00 - 07:00)
                if now_time >= start or now_time < end:
                    logger.info(f"Quiet hours active for {user_id}, skipping push")
                    return False
            else:
                if start <= now_time < end:
                    logger.info(f"Quiet hours active for {user_id}, skipping push")
                    return False
        except Exception:
            pass

    expo_sent = False
    web_sent = False

    # 1) Expo Push (mobile)
    token_doc = await db.push_tokens.find_one({"user_id": user_id}, {"_id": 0})
    if token_doc:
        push_token = token_doc["token"]
        if push_token.startswith("ExponentPushToken") or push_token.startswith("ExpoPushToken"):
            message = {"to": push_token, "sound": "default", "title": title, "body": body}
            if data:
                message["data"] = data
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "https://exp.host/--/api/v2/push/send",
                        json=message,
                        headers={"Content-Type": "application/json"},
                    )
                    logger.info(f"Expo push sent to {user_id}: {resp.json()}")
                    expo_sent = True
            except Exception as e:
                logger.error(f"Expo push failed for {user_id}: {e}")

    # 2) Web Push (browser)
    web_sent = await _send_web_push_to_user(user_id, title, body, data)

    return expo_sent or web_sent


async def _send_web_push_to_user(user_id: str, title: str, body: str, data: dict = None) -> bool:
    """Send Web Push notifications to all active browser subscriptions for a user."""
    if not _VAPID_PRIVATE_KEY:
        return False

    # Check both collections (push_subscriptions from push_notifications.py, web_push_subscriptions from old endpoints)
    subs = []
    async for sub in db.push_subscriptions.find({"user_id": user_id, "active": True}, {"_id": 0}):
        subs.append(sub)
    async for sub in db.web_push_subscriptions.find({"user_id": user_id}, {"_id": 0}):
        subs.append(sub)

    if not subs:
        return False

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": data.get("action_url", "/") if data else "/",
        "icon": "/api/static/images/favicon-64.png",
        "tag": data.get("type", "general") if data else "general",
    })

    sent = False
    try:
        from pywebpush import webpush, WebPushException
        vapid_claims = {"sub": _VAPID_SUBJECT}

        for sub in subs:
            try:
                subscription_info = {"endpoint": sub["endpoint"], "keys": sub["keys"]}
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=_VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,
                    timeout=10,
                )
                sent = True
            except WebPushException as e:
                resp_code = getattr(e, 'response', None)
                status_code = resp_code.status_code if resp_code else 0
                if status_code in (404, 410):
                    await db.push_subscriptions.update_one(
                        {"endpoint": sub["endpoint"]}, {"$set": {"active": False}}
                    )
                    await db.web_push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
                logger.warning(f"Web push failed for {user_id}: {e}")
            except Exception as e:
                logger.warning(f"Web push error for {user_id}: {e}")
    except ImportError:
        logger.warning("pywebpush not installed, skipping web push")
    return sent


class SendNotificationRequest(BaseModel):
    user_id: str
    title: str
    body: str
    notification_type: str = "general"


@router.post("/notifications/send-push")
async def send_push_endpoint(body: SendNotificationRequest, req: Request):
    """Send a push notification to a specific user (admin/internal use)."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    sent = await send_push_notification(body.user_id, body.title, body.body, {"type": body.notification_type})

    # Also create in-app notification
    notif = {
        "id": f"notif_{uuid.uuid4().hex[:12]}",
        "user_id": body.user_id,
        "type": body.notification_type,
        "title": body.title,
        "message": body.body,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notifications.insert_one({**notif})

    return {"success": True, "push_sent": sent}


# ── In-App Notifications ──


# Smart alerts must be defined before {user_id} route to avoid path conflict
@router.get("/notifications/smart-alerts")
async def get_smart_alerts_endpoint(req: Request):
    """Generate personalized smart notifications based on user data."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await _generate_smart_alerts(user)


@router.get("/notifications")
async def get_my_notifications(req: Request, limit: int = 20):
    """Convenience endpoint for current user's notifications."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    query = _notification_base_query(user.user_id)
    notifs = (
        await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    )
    notifs = [_sanitize_notification_payload(n) for n in notifs]
    unread = await db.notifications.count_documents({**query, "read": False})
    return {"notifications": notifs, "unread_count": unread}


@router.get("/notifications/unread-count")
async def get_notifications_unread_count(req: Request):
    """Compatibility endpoint for unread count checks."""
    user = await get_current_user(req)
    if not user:
        return {"unread_count": 0, "requires_auth": True}
    unread = await db.notifications.count_documents({**_notification_base_query(user.user_id), "read": False})
    return {"unread_count": unread}


@router.post("/notifications/bulk/read")
async def bulk_mark_notifications_read(body: NotificationBulkActionRequest, req: Request):
    """Mark selected notifications as read for the current user."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    notification_ids = _normalize_notification_identifiers(body.notification_ids)
    if not notification_ids:
        raise HTTPException(status_code=400, detail="No notifications selected")

    query = {
        **_notification_base_query(user.user_id),
        **_notification_identifier_filter(notification_ids),
    }
    docs = await db.notifications.find(query, {"_id": 0, "read": 1}).to_list(len(notification_ids) * 2)
    unread_affected = sum(1 for doc in docs if not doc.get("read"))
    result = await db.notifications.update_many(
        query,
        {"$set": {"read": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {
        "success": True,
        "matched": result.matched_count,
        "updated": result.modified_count,
        "unread_affected": unread_affected,
    }


@router.post("/notifications/bulk/archive")
async def bulk_archive_notifications(body: NotificationBulkActionRequest, req: Request):
    """Archive selected notifications for the current user."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    notification_ids = _normalize_notification_identifiers(body.notification_ids)
    if not notification_ids:
        raise HTTPException(status_code=400, detail="No notifications selected")

    query = {
        **_notification_base_query(user.user_id),
        **_notification_identifier_filter(notification_ids),
    }
    docs = await db.notifications.find(query, {"_id": 0, "read": 1}).to_list(len(notification_ids) * 2)
    unread_affected = sum(1 for doc in docs if not doc.get("read"))
    now = datetime.now(timezone.utc).isoformat()
    result = await db.notifications.update_many(
        query,
        {"$set": {"archived": True, "archived_at": now, "updated_at": now}},
    )
    return {
        "success": True,
        "matched": result.matched_count,
        "updated": result.modified_count,
        "unread_affected": unread_affected,
    }


@router.post("/notifications/clear-read")
async def clear_all_read_notifications(req: Request):
    """Archive all read notifications for the current user in one action."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    query = {**_notification_base_query(user.user_id), "read": True}
    now = datetime.now(timezone.utc).isoformat()
    result = await db.notifications.update_many(
        query,
        {"$set": {"archived": True, "archived_at": now, "updated_at": now}},
    )
    return {"success": True, "cleared": result.modified_count}


# ── Notification Retention Settings (Admin) ──

class RetentionSettingsUpdate(BaseModel):
    retention_days: int
    auto_archive_enabled: bool = True

_DEFAULT_RETENTION = {"retention_days": 30, "auto_archive_enabled": True}

@router.get("/admin/notification-settings/retention")
async def get_retention_settings(req: Request):
    """Get notification auto-archive retention settings (admin only)."""
    user = await get_current_user(req)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    doc = await db.platform_settings.find_one({"key": "notification_retention"}, {"_id": 0})
    return doc.get("value", _DEFAULT_RETENTION) if doc else _DEFAULT_RETENTION

@router.put("/admin/notification-settings/retention")
async def update_retention_settings(body: RetentionSettingsUpdate, req: Request):
    """Update notification auto-archive retention settings (admin only)."""
    user = await get_current_user(req)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    if body.retention_days < 1 or body.retention_days > 365:
        raise HTTPException(status_code=400, detail="retention_days must be between 1 and 365")
    value = {"retention_days": body.retention_days, "auto_archive_enabled": body.auto_archive_enabled}
    await db.platform_settings.update_one(
        {"key": "notification_retention"},
        {"$set": {"key": "notification_retention", "value": value, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user.user_id}},
        upsert=True,
    )
    return {"success": True, **value}


@router.get("/live-activity/feed")
async def get_live_activity_feed_alias(req: Request, limit: int = 20):
    """Compatibility alias for /api/live-activity/feed checks."""
    user = await get_current_user(req)
    if not user:
        return {"events": [], "count": 0, "requires_auth": True}

    safe_limit = min(max(limit, 1), 100)
    docs = await db.live_activity_events.find({}, {"_id": 0}).sort("timestamp", -1).limit(safe_limit).to_list(safe_limit)
    return {"events": docs, "count": len(docs)}


@router.get("/notifications/{user_id}")
async def get_notifications(user_id: str, req: Request, limit: int = 20):
    """Get notifications for the current user."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    resolved_user_id = user.user_id if user_id == "me" else user_id
    if user.user_id != resolved_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    query = _notification_base_query(resolved_user_id)
    notifs = (
        await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    )
    notifs = [_sanitize_notification_payload(n) for n in notifs]
    unread = await db.notifications.count_documents({**query, "read": False})
    return {"notifications": notifs, "unread_count": unread}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, req: Request):
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.notifications.update_one(
        {
            **_notification_base_query(user.user_id),
            "$or": [{"notification_id": notification_id}, {"id": notification_id}],
        },
        {"$set": {"read": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@router.post("/notifications/{user_id}/read-all")
async def mark_all_read(user_id: str, req: Request):
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    resolved_user_id = user.user_id if user_id == "me" else user_id
    if user.user_id != resolved_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    await db.notifications.update_many(
        {**_notification_base_query(resolved_user_id), "read": False},
        {"$set": {"read": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True}


@router.delete("/notifications/{notification_id}")
async def delete_notification(notification_id: str, req: Request):
    """Delete a specific notification"""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.notifications.delete_one(
        {
            **_notification_base_query(user.user_id, include_archived=True),
            "$or": [{"notification_id": notification_id}, {"id": notification_id}],
        }
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True, "message": "Notification deleted"}


# ── Daily Briefing ──


@router.get("/notifications/daily-briefing/{user_id}")
async def get_daily_briefing(user_id: str, req: Request):
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    """Generate a personalized daily briefing notification combining calendar, quests, weather."""
    now = datetime.now(timezone.utc)
    today_key = now.strftime("%Y-%m-%d")

    existing = await db.daily_briefings.find_one({"user_id": user_id, "date": today_key}, {"_id": 0})
    if existing:
        return existing

    calendar_events = []
    lifegame_char = None

    try:
        upcoming = await db.calendar_events.find({"user_id": user_id}, {"_id": 0}).sort("start", 1).limit(5).to_list(5)
        calendar_events = upcoming
    except Exception:
        pass

    try:
        lifegame_char = await db.lifegame_characters.find_one({"user_id": user_id}, {"_id": 0})
    except Exception:
        pass

    event_count = len(calendar_events)
    event_titles = [e.get("title", "") for e in calendar_events[:3]]

    level = lifegame_char.get("level", 1) if lifegame_char else None
    xp = lifegame_char.get("total_xp", 0) if lifegame_char else None
    char_name = lifegame_char.get("name", "") if lifegame_char else None

    parts = []
    greeting = _get_greeting()
    parts.append(greeting)

    if event_count > 0:
        parts.append(
            f"You have {event_count} event{'s' if event_count > 1 else ''} today{': ' + event_titles[0] if event_count == 1 else '.'}{'.' if event_count == 1 else ''}"
        )
    else:
        parts.append("Your calendar is clear today.")

    if lifegame_char:
        parts.append(f"Your character {char_name} is Level {level} with {xp} XP. Ready for new quests?")

    parts.append("Let's make it a great day!")

    summary = " ".join(parts)

    briefing = {
        "user_id": user_id,
        "date": today_key,
        "summary": summary,
        "greeting": greeting,
        "events": {"count": event_count, "titles": event_titles},
        "lifegame": {
            "active": lifegame_char is not None,
            "level": level,
            "xp": xp,
            "name": char_name,
        },
        "tips": [_get_daily_tip()],
        "created_at": now.isoformat(),
    }

    await db.daily_briefings.insert_one({**briefing})

    notif = {
        "id": f"notif_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "type": "daily_briefing",
        "title": f"{greeting} Here's your daily briefing",
        "message": summary,
        "read": False,
        "created_at": now.isoformat(),
    }
    await db.notifications.insert_one({**notif})

    # Send push notification for daily briefing
    settings = await db.notification_settings.find_one({"user_id": user_id}, {"_id": 0})
    if not settings or settings.get("daily_briefing", True):
        await send_push_notification(user_id, f"{greeting} Daily Briefing", summary, {"type": "daily_briefing"})

    return briefing


def _get_greeting():
    hour = datetime.now(timezone.utc).hour
    if hour < 12:
        return "Good morning!"
    elif hour < 17:
        return "Good afternoon!"
    else:
        return "Good evening!"


def _get_daily_tip():
    import random

    tips = [
        "Start your day with 5 minutes of deep breathing to boost focus.",
        "Take a 10-minute walk between tasks to refresh your mind.",
        "Write down 3 things you're grateful for today.",
        "Drink a glass of water first thing to kickstart your metabolism.",
        "Set your top 3 priorities before checking email.",
        "Use the 2-minute rule: if it takes less than 2 minutes, do it now.",
        "Schedule breaks between meetings to prevent decision fatigue.",
        "Practice active listening in your next conversation.",
        "Try the Pomodoro technique: 25 min work, 5 min break.",
        "End your day by planning tomorrow's top 3 tasks.",
        "Move your body for at least 20 minutes today.",
        "Limit social media to scheduled blocks, not reactive scrolling.",
        "Batch similar tasks together for better focus and efficiency.",
        "Say no to one low-priority request today to protect your time.",
        "Celebrate one small win before the day ends.",
    ]
    return random.choice(tips)


# ── Smart Notifications ──

SMART_MINI_APP_SUGGESTIONS = [
    {
        "app": "Marketplace",
        "route": "/mini-apps/marketplace",
        "icon": "storefront",
        "color": "#10B981",
        "desc": "Browse and sell products in the marketplace",
    },
    {
        "app": "AI Accounting",
        "route": "/mini-apps/ai-accounting",
        "icon": "calculator",
        "color": "#F97316",
        "desc": "Track income, expenses, and get AI profit forecasts",
    },
    {
        "app": "Mobile Money",
        "route": "/subscription/mobile-money",
        "icon": "phone-portrait",
        "color": "#2563EB",
        "desc": "Pay subscriptions via FedaPay & mobile wallets",
    },
    {
        "app": "Job Platform",
        "route": "/mini-apps/job-platform",
        "icon": "briefcase",
        "color": "#2563EB",
        "desc": "Find jobs with AI matching and applicant analytics",
    },
    {
        "app": "Film Production",
        "route": "/mini-apps/film-production",
        "icon": "film",
        "color": "#DB2777",
        "desc": "Manage projects, talent, and milestone payments",
    },
    {
        "app": "Digital Bank",
        "route": "/mini-apps/digital-bank",
        "icon": "business",
        "color": "#3B82F6",
        "desc": "Savings accounts and AI financial advisor",
    },
]


async def _generate_smart_alerts(user):
    """Generate personalized smart notifications based on user data."""

    alerts = []
    now = datetime.now(timezone.utc)

    # 1. Subscription renewal reminder
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if user_doc:
        sub_end = user_doc.get("subscription_end")
        if sub_end:
            if isinstance(sub_end, str):
                try:
                    from datetime import datetime as dt

                    sub_end = dt.fromisoformat(sub_end.replace("Z", "+00:00"))
                except Exception:
                    sub_end = None
            if sub_end and hasattr(sub_end, "tzinfo"):
                if sub_end.tzinfo is None:
                    sub_end = sub_end.replace(tzinfo=timezone.utc)
                days_left = (sub_end - now).days
                if 0 < days_left <= 7:
                    alerts.append(
                        {
                            "id": f"smart_sub_renewal_{user.user_id}",
                            "type": "subscription_renewal",
                            "priority": "high",
                            "icon": "card",
                            "color": "#F59E0B",
                            "title": "Subscription Renewing Soon",
                            "message": f"Your {user_doc.get('subscription_plan', 'plan')} plan expires in {days_left} day{'s' if days_left != 1 else ''}. Renew now to keep your features.",
                            "action": {"label": "Renew Now", "route": "/subscription/plans"},
                            "created_at": now.isoformat(),
                        }
                    )
                elif days_left <= 0:
                    alerts.append(
                        {
                            "id": f"smart_sub_expired_{user.user_id}",
                            "type": "subscription_expired",
                            "priority": "critical",
                            "icon": "alert-circle",
                            "color": "#EF4444",
                            "title": "Subscription Expired",
                            "message": "Your subscription has expired. Upgrade to regain access to premium features.",
                            "action": {"label": "Upgrade Now", "route": "/subscription/plans"},
                            "created_at": now.isoformat(),
                        }
                    )

        # Free plan upgrade suggestion
        if user_doc.get("subscription_plan") == "free":
            alerts.append(
                {
                    "id": f"smart_upgrade_{user.user_id}",
                    "type": "upgrade_suggestion",
                    "priority": "medium",
                    "icon": "star",
                    "color": "#8B5CF6",
                    "title": "Unlock Premium Features",
                    "message": "Get unlimited conversations, advanced scenarios, AI analytics, and more with Premium.",
                    "action": {"label": "See Plans", "route": "/subscription/plans"},
                    "created_at": now.isoformat(),
                }
            )

    # 2. Security score alert
    security = await db.user_security.find_one({"user_id": user.user_id}, {"_id": 0})
    has_2fa = bool(security and security.get("two_fa_enabled"))
    has_pin = await db.biometric_pins.find_one({"user_id": user.user_id}) is not None
    has_passkey = await db.webauthn_credentials.find_one({"user_id": user.user_id}) is not None

    score = 0
    if user_doc and user_doc.get("email_verified"):
        score += 15
    if user_doc and user_doc.get("password_hash"):
        score += 15
    if has_2fa:
        score += 25
    if security and security.get("backup_codes"):
        unused = sum(1 for c in security["backup_codes"] if not c.get("used"))
        if unused > 0:
            score += 10
    if has_pin or has_passkey:
        score += 20

    one_week_ago = now - __import__("datetime").timedelta(days=7)
    recent_failures = await db.security_events.count_documents(
        {
            "user_id": user.user_id,
            "event_type": "login_failed",
            "timestamp": {"$gte": one_week_ago.isoformat()},
        }
    )
    if recent_failures == 0:
        score += 15

    if score < 50:
        tips = []
        if not has_2fa:
            tips.append("Enable 2FA")
        if not (has_pin or has_passkey):
            tips.append("Set up biometric login")
        if not (user_doc and user_doc.get("email_verified")):
            tips.append("Verify your email")
        tip_text = " | ".join(tips[:2]) if tips else "Review your security settings"
        alerts.append(
            {
                "id": f"smart_security_{user.user_id}",
                "type": "security_alert",
                "priority": "high",
                "icon": "shield-checkmark",
                "color": "#EF4444",
                "title": f"Security Score: {score}/100",
                "message": f"Your account security is low. Quick fixes: {tip_text}",
                "action": {"label": "Improve Now", "route": "/privacy-security"},
                "created_at": now.isoformat(),
            }
        )
    elif score < 75:
        alerts.append(
            {
                "id": f"smart_security_med_{user.user_id}",
                "type": "security_tip",
                "priority": "low",
                "icon": "shield-half",
                "color": "#F59E0B",
                "title": f"Security Score: {score}/100",
                "message": "Good start! Enable more security features to reach a strong score.",
                "action": {"label": "Improve Score", "route": "/privacy-security"},
                "created_at": now.isoformat(),
            }
        )

    # 3. Streak & inactivity reminder
    progress = await db.progress.find_one({"user_id": user.user_id}, {"_id": 0})
    if progress:
        streak = progress.get("current_streak", 0)
        last_date = progress.get("last_conversation_date")
        if last_date:
            try:
                from datetime import datetime as dt

                last_dt = dt.fromisoformat(last_date) if isinstance(last_date, str) else last_date
                if hasattr(last_dt, "tzinfo") and last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                days_inactive = (now - last_dt).days if hasattr(last_dt, "tzinfo") else 999
            except Exception:
                days_inactive = 999
        else:
            days_inactive = 999

        if streak > 0 and days_inactive >= 1:
            alerts.append(
                {
                    "id": f"smart_streak_{user.user_id}",
                    "type": "streak_reminder",
                    "priority": "medium",
                    "icon": "flame",
                    "color": "#F97316",
                    "title": f"Keep Your {streak}-Day Streak!",
                    "message": "Practice today to maintain your streak. Just one session keeps it alive!",
                    "action": {"label": "Practice Now", "route": "/(tabs)/practice"},
                    "created_at": now.isoformat(),
                }
            )
        elif days_inactive >= 3:
            alerts.append(
                {
                    "id": f"smart_inactive_{user.user_id}",
                    "type": "inactivity_reminder",
                    "priority": "low",
                    "icon": "time",
                    "color": "#6366F1",
                    "title": "We Miss You!",
                    "message": f"It's been {min(days_inactive, 30)}+ days since your last session. Jump back in!",
                    "action": {"label": "Start Session", "route": "/(tabs)/practice"},
                    "created_at": now.isoformat(),
                }
            )

    # 4. Payment card reminder
    card_count = await db.payment_cards.count_documents({"user_id": user.user_id, "status": "active"})
    if card_count == 0:
        alerts.append(
            {
                "id": f"smart_card_{user.user_id}",
                "type": "payment_setup",
                "priority": "low",
                "icon": "card",
                "color": "#3B82F6",
                "title": "Add a Payment Method",
                "message": "Save a card for quick one-tap payments and seamless subscription renewals.",
                "action": {"label": "Add Card", "route": "/settings/payment-cards"},
                "created_at": now.isoformat(),
            }
        )

    # 5. Mini-app discovery
    import random

    suggestion = random.choice(SMART_MINI_APP_SUGGESTIONS)
    alerts.append(
        {
            "id": f"smart_discover_{suggestion['app'].lower().replace(' ', '_')}",
            "type": "app_discovery",
            "priority": "low",
            "icon": suggestion["icon"],
            "color": suggestion["color"],
            "title": f"Discover: {suggestion['app']}",
            "message": suggestion["desc"],
            "action": {"label": "Try It", "route": suggestion["route"]},
            "created_at": now.isoformat(),
        }
    )

    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: priority_order.get(a["priority"], 4))

    return {"alerts": alerts, "count": len(alerts)}
