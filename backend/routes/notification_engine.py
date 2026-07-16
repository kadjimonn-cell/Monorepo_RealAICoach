"""Centralized Notification Engine - auto-triggers for all platform events."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
import uuid
import hashlib
import re
from .db import db, logger, get_current_user

router = APIRouter(prefix="/notification-engine")

# Map notification types to their user preference key
CATEGORY_PREFERENCE_MAP = {
    "team_invite": "team_updates",
    "team_update": "team_updates",
    "member_invited": "team_updates",
    "member_removed": "team_updates",
    "team_role_changed": "team_updates",
    "goal_reminder": "goal_reminders",
    "goal_milestone": "goal_reminders",
    "goal_completed": "goal_reminders",
    "goal_deadline": "goal_reminders",
    "coaching_nudge": "coaching_nudges",
    "coaching_tip": "coaching_nudges",
    "ai_coaching": "coaching_nudges",
}


async def _is_category_enabled(user_id: str, notif_type: str) -> bool:
    """Check if user has this notification category enabled."""
    pref_key = CATEGORY_PREFERENCE_MAP.get(notif_type)
    if not pref_key:
        return True  # No category mapping = always send
    settings = await db.notification_settings.find_one({"user_id": user_id}, {"_id": 0})
    if not settings:
        return True  # Defaults are all enabled
    return settings.get(pref_key, True)


def _sanitize_notification_entity(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9:_\-.]", "", str(value or "").strip())[:180]


def _build_notification_email_dedupe_key(
    *,
    user_id: str,
    notif_type: str,
    title: str,
    body: str,
    action_url: str,
    metadata: dict,
) -> str:
    metadata = metadata or {}
    preferred_entity_keys = (
        "notification_entity_id",
        "gps_event_id",
        "event_id",
        "entity_id",
        "ticket_id",
        "payment_id",
        "invoice_id",
        "application_id",
        "offer_id",
        "job_id",
        "team_id",
        "goal_id",
    )

    entity = ""
    for key in preferred_entity_keys:
        value = metadata.get(key)
        if value is None:
            continue
        cleaned = _sanitize_notification_entity(str(value))
        if cleaned:
            entity = f"{key}:{cleaned}"
            break

    if not entity:
        raw = f"{str(title or '').strip().lower()}|{str(body or '').strip().lower()}|{str(action_url or '').strip().lower()}"
        entity = f"content:{hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()[:20]}"

    return f"notif:{str(user_id or '').strip()}:{str(notif_type or '').strip().lower()}:{entity}"


async def emit_notification(
    user_id: str,
    notif_type: str,
    title: str,
    body: str,
    action_url: str = "",
    metadata: dict = None,
    send_email_notification: bool = True,
):
    """Central function to create in-app notification + push via WebSocket.
    Respects user category preferences (team_updates, goal_reminders, coaching_nudges)."""
    # Global suppression gate — block system noise from user feeds
    from utils.notification_helper import is_notification_suppressed
    if is_notification_suppressed(notif_type):
        logger.debug(f"[notif-suppressed] type={notif_type} user={user_id} title={title[:40] if title else '?'}")
        return None

    # Check category preference
    if not await _is_category_enabled(user_id, notif_type):
        logger.info(f"Notification suppressed for {user_id}: category disabled for type={notif_type}")
        return None

    # Global notification dedupe: prevent duplicate records/spam bursts for the same event payload.
    dedupe_window_minutes = 15
    now_utc = datetime.now(timezone.utc)
    dedupe_cutoff = (now_utc - timedelta(minutes=dedupe_window_minutes)).isoformat()
    existing_recent = await db.notifications.find_one(
        {
            "user_id": user_id,
            "type": notif_type,
            "title": title,
            "body": body,
            "created_at": {"$gte": dedupe_cutoff},
            "archived": {"$ne": True},
        },
        {"_id": 0, "notification_id": 1, "created_at": 1},
    )
    if existing_recent:
        logger.warning(
            "notification dedupe suppressed duplicate (user=%s type=%s notif_id=%s)",
            user_id,
            notif_type,
            existing_recent.get("notification_id", ""),
        )
        return existing_recent

    notif = {
        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "body": body,
        "message": body,
        "action_url": action_url,
        "read": False,
        "archived": False,
        "metadata": metadata or {},
        "created_at": now_utc.isoformat(),
    }
    await db.notifications.insert_one(notif)
    notif.pop("_id", None)

    # Push via WebSocket
    try:
        from utils.ws_manager import ws_manager

        unread = await db.notifications.count_documents({"user_id": user_id, "read": False, "archived": {"$ne": True}})
        await ws_manager.send_to_user(
            user_id,
            {
                "type": "notification",
                "notification": notif,
                "unread_count": unread,
            },
        )
    except Exception as e:
        logger.error(f"WS push failed for {user_id}: {e}")

    # Push notification (Expo)
    try:
        from routes.notifications import send_push_notification

        await send_push_notification(user_id, title, body, {"type": notif_type, "action_url": action_url})
    except Exception as e:
        logger.error(f"Push notification failed for {user_id}: {e}")

    # Email notification (if enabled)
    try:
        if send_email_notification:
            settings = await db.notification_settings.find_one({"user_id": user_id}, {"_id": 0})
            if not settings or settings.get("email_enabled", True):
                user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
                if user_doc and user_doc.get("email"):
                    from utils.email_service import is_email_configured

                    if is_email_configured():
                        from utils.email_service import send_catalog_template

                        email_dedupe_key = _build_notification_email_dedupe_key(
                            user_id=user_id,
                            notif_type=notif_type,
                            title=title,
                            body=body,
                            action_url=action_url,
                            metadata=metadata or {},
                        )

                        await send_catalog_template(
                            recipient_email=user_doc["email"],
                            template_key="user_notification_alert",
                            recipient_name=user_doc.get("name", "User"),
                            alert_title=title,
                            message=body,
                            context_type=notif_type,
                            action_url=action_url or "/notifications",
                            dedupe_key=email_dedupe_key,
                            expected_user_id=user_id,
                            enforce_verified_primary=True,
                        )
    except Exception as e:
        logger.error(f"Email notification failed for {user_id}: {e}")

    return notif


# Event-specific emitters
async def emit_booking_created(host_id: str, guest_name: str, guest_email: str, start: str):
    """Notify host when a new meeting is booked."""
    return await emit_notification(
        user_id=host_id,
        notif_type="booking_created",
        title="New Meeting Booked",
        body=f"{guest_name} ({guest_email}) booked a meeting on {start[:16].replace('T', ' ')}",
        action_url="/book-meeting",
    )


async def emit_booking_cancelled(host_id: str, guest_name: str, start: str, cancelled_by: str = "host"):
    """Notify about booking cancellation."""
    return await emit_notification(
        user_id=host_id,
        notif_type="booking_cancelled",
        title="Meeting Cancelled",
        body=f"Meeting with {guest_name} on {start[:16].replace('T', ' ')} was cancelled by {cancelled_by}",
        action_url="/book-meeting",
    )


async def emit_booking_reminder(host_id: str, guest_name: str, start: str, minutes_until: int):
    """Reminder notification before a meeting."""
    return await emit_notification(
        user_id=host_id,
        notif_type="meeting_reminder",
        title=f"Meeting in {minutes_until} min",
        body=f"Your meeting with {guest_name} starts at {start[11:16]}",
        action_url="/book-meeting",
    )


async def emit_employer_action(user_id: str, action: str, details: str):
    """Notify about employer workflow events."""
    titles = {
        "approved": "Application Approved",
        "denied": "Application Denied",
        "pending": "New Application Submitted",
        "need_info": "Additional Information Required",
    }
    return await emit_notification(
        user_id=user_id,
        notif_type=f"employer_{action}",
        title=titles.get(action, f"Employer Update: {action}"),
        body=details,
        action_url="/employer-apply",
    )


async def emit_interview_scheduled(candidate_id: str, job_title: str, interview_time: str):
    """Notify candidate about scheduled interview."""
    return await emit_notification(
        user_id=candidate_id,
        notif_type="interview_scheduled",
        title="Interview Scheduled",
        body=f"Your interview for {job_title} is scheduled for {interview_time[:16].replace('T', ' ')}",
        action_url="/hiring-hub",
    )


async def emit_ai_recommendation(user_id: str, rec_type: str, message: str):
    """AI-generated proactive recommendation."""
    return await emit_notification(
        user_id=user_id,
        notif_type=f"ai_{rec_type}",
        title="AI Recommendation",
        body=message,
        action_url="/career",
    )


# ── Team, Goal & Coaching Emitters ──


async def emit_team_invite(invitee_user_id: str, inviter_name: str, team_name: str, role: str = "member"):
    """Notify a user when they are invited to a team."""
    return await emit_notification(
        user_id=invitee_user_id,
        notif_type="team_invite",
        title=f"Team Invitation: {team_name}",
        body=f"{inviter_name} invited you to join {team_name} as {role}.",
        action_url="/team-management",
        metadata={"team_name": team_name, "inviter": inviter_name, "role": role},
    )


async def emit_team_member_removed(user_id: str, team_name: str, removed_by: str):
    """Notify a user when they are removed from a team."""
    return await emit_notification(
        user_id=user_id,
        notif_type="member_removed",
        title=f"Removed from {team_name}",
        body=f"You were removed from {team_name} by {removed_by}.",
        action_url="/team-management",
        metadata={"team_name": team_name, "removed_by": removed_by},
    )


async def emit_goal_reminder(user_id: str, goal_title: str, deadline: str = "", message: str = ""):
    """Notify a user about a goal deadline or milestone."""
    body = message or f"Your goal '{goal_title}' needs attention."
    if deadline:
        body += f" Deadline: {deadline}."
    return await emit_notification(
        user_id=user_id,
        notif_type="goal_reminder",
        title=f"Goal Reminder: {goal_title}",
        body=body,
        action_url="/career",
        metadata={"goal_title": goal_title, "deadline": deadline},
    )


async def emit_goal_completed(user_id: str, goal_title: str):
    """Notify a user when a goal is completed."""
    return await emit_notification(
        user_id=user_id,
        notif_type="goal_completed",
        title="Goal Completed!",
        body=f"Congratulations! You've completed your goal: '{goal_title}'.",
        action_url="/career",
        metadata={"goal_title": goal_title},
    )


async def emit_coaching_nudge(user_id: str, tip: str, category: str = "general"):
    """Send an AI coaching nudge/tip to a user."""
    return await emit_notification(
        user_id=user_id,
        notif_type="coaching_nudge",
        title="AI Coaching Tip",
        body=tip,
        action_url="/career",
        metadata={"category": category},
    )


# ── API Endpoints ──


@router.get("/summary")
async def notification_summary(request: Request):
    """Get notification summary with counts by type."""
    user = await get_current_user(request)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    pipeline = [
        {"$match": {"user_id": user.user_id, "archived": {"$ne": True}}},
        {
            "$group": {
                "_id": "$type",
                "count": {"$sum": 1},
                "unread": {"$sum": {"$cond": [{"$eq": ["$read", False]}, 1, 0]}},
            }
        },
    ]
    results = await db.notifications.aggregate(pipeline).to_list(50)
    total_unread = sum(r["unread"] for r in results)
    total = sum(r["count"] for r in results)

    return {
        "total": total,
        "total_unread": total_unread,
        "by_type": {r["_id"]: {"count": r["count"], "unread": r["unread"]} for r in results},
    }


@router.post("/test")
async def test_notification(request: Request):
    """Send a test notification to the current user."""
    user = await get_current_user(request)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    notif = await emit_notification(
        user_id=user.user_id,
        notif_type="test",
        title="Test Notification",
        body="This is a test notification from the notification engine.",
        action_url="/notifications",
    )
    return {"success": True, "notification": notif}


# ── Daily Digest ──


async def _send_daily_digest_for_user(user_id: str) -> dict:
    """Collect unread notifications from past 24h and send digest email for one user."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Check if user has daily_briefing enabled
    settings = await db.notification_settings.find_one({"user_id": user_id}, {"_id": 0})
    if settings and not settings.get("daily_briefing", True):
        return {"user_id": user_id, "skipped": True, "reason": "daily_briefing disabled"}

    # Also check email_enabled
    if settings and not settings.get("email_enabled", True):
        return {"user_id": user_id, "skipped": True, "reason": "email disabled"}

    # Fetch unread notifications from past 24h
    notifs = (
        await db.notifications.find(
            {"user_id": user_id, "read": False, "archived": {"$ne": True}, "created_at": {"$gte": cutoff}},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(100)
    )

    if not notifs:
        return {"user_id": user_id, "skipped": True, "reason": "no unread notifications"}

    # Get user email
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
    if not user_doc or not user_doc.get("email"):
        return {"user_id": user_id, "skipped": True, "reason": "no email"}

    # Build and send
    try:
        from utils.email_service import is_email_configured

        if not is_email_configured():
            return {"user_id": user_id, "skipped": True, "reason": "email not configured"}

        from utils.email_service import send_catalog_template

        notification_ids = sorted(
            str(n.get("notification_id") or "").strip()
            for n in notifs
            if str(n.get("notification_id") or "").strip()
        )
        digest_seed = (
            hashlib.sha256("|".join(notification_ids).encode("utf-8", errors="ignore")).hexdigest()[:24]
            if notification_ids
            else hashlib.sha256(
                "|".join(
                    f"{n.get('type','')}::{n.get('title','')}::{n.get('body','')}"
                    for n in notifs
                ).encode("utf-8", errors="ignore")
            ).hexdigest()[:24]
        )
        digest_dedupe_key = f"daily_digest:{user_id}:{digest_seed}"

        await send_catalog_template(
            recipient_email=user_doc["email"],
            template_key="daily_digest",
            recipient_name=user_doc.get("name", "User"),
            user_name=user_doc.get("name", "there"),
            unread_count=len(notifs),
            notifications=notifs,
            dedupe_key=digest_dedupe_key,
            expected_user_id=user_id,
            enforce_verified_primary=True,
        )
        return {"user_id": user_id, "sent": True, "count": len(notifs)}
    except Exception as e:
        logger.error(f"Daily digest failed for {user_id}: {e}")
        return {"user_id": user_id, "skipped": True, "reason": str(e)}


@router.post("/daily-digest")
async def trigger_daily_digest(request: Request):
    """Trigger daily digest emails for all eligible users. Admin-only or cron trigger."""
    user = await get_current_user(request)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get all users with unread notifications in the past 24h
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    user_ids = await db.notifications.distinct(
        "user_id",
        {"read": False, "archived": {"$ne": True}, "created_at": {"$gte": cutoff}},
    )

    results = []
    for uid in user_ids:
        result = await _send_daily_digest_for_user(uid)
        results.append(result)

    sent = sum(1 for r in results if r.get("sent"))
    skipped = sum(1 for r in results if r.get("skipped"))
    return {
        "success": True,
        "total_users": len(user_ids),
        "sent": sent,
        "skipped": skipped,
        "details": results,
    }


@router.post("/daily-digest/preview")
async def preview_daily_digest(request: Request):
    """Preview the daily digest email for the current user (does not send)."""
    user = await get_current_user(request)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    notifs = (
        await db.notifications.find(
            {"user_id": user.user_id, "read": False, "archived": {"$ne": True}, "created_at": {"$gte": cutoff}},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(100)
    )

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "name": 1, "email": 1})
    from utils.email_templates import build_daily_digest_email

    tpl = build_daily_digest_email(
        user_name=user_doc.get("name", "there") if user_doc else "there",
        unread_count=len(notifs),
        notifications=notifs,
    )
    return {
        "unread_count": len(notifs),
        "html": tpl.html,
        "would_send_to": user_doc.get("email", "") if user_doc else "",
    }
