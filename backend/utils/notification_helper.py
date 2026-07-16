"""Shared notification helper — creates in-app notifications + pushes via WebSocket."""

from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger("notification_helper")

# ══════════════════════════════════════════════════════════════
# GLOBAL NOTIFICATION SUPPRESSION — System-level permanent fix
# These types are internal ops/scheduler noise and MUST NOT
# appear in user notification feeds.
# ══════════════════════════════════════════════════════════════
SYSTEM_SUPPRESSED_TYPES = frozenset({
    # GPS state machine churn (scheduler runs every 30s)
    "gps_contentupdated", "gps_planchanged", "gps_gpsselfheal",
    "gps_featureremoved", "gps_featureadded", "gps_featureupdated",
    "gps_gls_config_updated", "gps_configchanged", "gps_routeadded",
    "gps_routeremoved",
    # Self-repair engine (runs every ~3 min)
    "self_repair",
    # Integrity monitors (scheduler cron)
    "platform_integrity_alert", "growth_integrity_monitor",
    "critical_journey_monitor_incident", "critical_journey_monitor_recovered",
    "platform_regression_gate", "global_parity_incident",
    # Host/cache/probe monitors (ops-only)
    "assigned_host_guard_alert", "platform_cache_freshness_warning",
    "preview_cache_hygiene_alert", "logo_render_probe",
    "fee_visibility_visual_incident", "fee_visibility_visual_drift",
    # Email guardrails (internal cap/block logs)
    "email_guardrail_block", "email_notification_cap_blocked",
    # Automated content drops (scheduler bulk-creates)
    "watch_videos_new_release", "watch-videos-sports_weekly_drop",
    "watch-videos-audio-studio_daily_drop", "watch-videos-my-podcasts_daily_drop",
    "learning_hub_weekly_release",
    # Nightly ops reports
    "acceptance_report_nightly", "nightly_categorization",
})

# Rate-limited types: max 1 notification per user per window (minutes)
RATE_LIMITED_TYPES = {
    "security_alert": 60,
    "subscription_reminder": 1440,
}


def is_notification_suppressed(notif_type: str) -> bool:
    """Check if a notification type is globally suppressed from user feeds."""
    if not notif_type:
        return False
    normalized = notif_type.strip().lower()
    if normalized in SYSTEM_SUPPRESSED_TYPES:
        return True
    # Suppress any gps_ prefixed type not explicitly allowlisted
    if normalized.startswith("gps_"):
        return True
    return False


async def create_notification(
    user_id: str,
    title: str,
    message: str,
    notif_type: str = "general",
    data: dict = None,
):
    """Create an in-app notification, push to WebSocket, and attempt push notification."""
    # Global suppression gate — block system noise from user feeds
    if is_notification_suppressed(notif_type):
        logger.debug(f"[notif-suppressed] type={notif_type} user={user_id} title={title[:40]}")
        return None

    from routes.db import db
    from utils.ws_manager import ws_manager

    notif_id = f"notif_{uuid.uuid4().hex[:12]}"
    notif = {
        "id": notif_id,
        "notification_id": notif_id,
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "message": message,
        "read": False,
        "data": data or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notifications.insert_one({**notif})
    notif.pop("_id", None)

    # Count unread
    unread = await db.notifications.count_documents({"user_id": user_id, "read": False})

    # Push via WebSocket
    try:
        await ws_manager.send_to_user(
            user_id,
            {
                "type": "notification",
                "notification": notif,
                "unread_count": unread,
            },
        )
    except Exception as e:
        logger.debug(f"WS push failed for {user_id}: {e}")

    # Attempt push notification (non-blocking)
    try:
        from routes.notifications import send_push_notification

        await send_push_notification(user_id, title, message, {"type": notif_type, **(data or {})})
    except Exception:
        pass

    return notif


async def create_notification_for_email(
    user_id: str, email: str, title: str, message: str, notif_type: str = "general"
):
    """Create notification and attempt to send email as well."""
    from utils.email_service import is_email_configured, render_email_logo

    notif = await create_notification(user_id, title, message, notif_type)

    if is_email_configured() and email:
        try:
            render_email_logo(variant="compact")
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=email,
                template_key="user_notification_alert",
                alert_title=title,
                message=message[:500] if message else title,
                context_type=notif_type or "notification",
                action_url="/notifications",
            )
        except Exception as e:
            logger.warning(f"Email send failed for {email}: {e}")

    return notif
