"""Google OAuth Verification Monitor — tracks verification status and sends alerts."""

import os
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")


async def check_google_verification_status(db) -> dict:
    """
    Check if the Google OAuth app is verified by examining the consent screen behavior.
    Stores results in MongoDB for historical tracking.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Get current stored status
    current = await db.google_verification_status.find_one(
        {"type": "current_status"}, {"_id": 0}
    )

    if not GOOGLE_CLIENT_ID:
        return {
            "status": "not_configured",
            "message": "Google OAuth not configured",
            "checked_at": now,
        }

    # Attempt to detect verification status by checking the OAuth consent screen
    # Google returns different responses for verified vs unverified apps
    try:
        test_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={GOOGLE_CLIENT_ID}"
            f"&redirect_uri=https://localhost/callback"
            f"&response_type=code"
            f"&scope=openid%20email%20profile"
            f"&access_type=offline"
        )

        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
            resp = await client.get(test_url)
            # Check response for verification indicators
            body = resp.text if resp.status_code == 200 else ""
            is_verified = (
                "unverified" not in body.lower()
                and "hasn't been verified" not in body.lower()
                and resp.status_code in (200, 302)
            )

        new_status = "verified" if is_verified else "under_review"

    except Exception as e:
        logger.warning(f"Google verification check failed: {e}")
        new_status = current.get("status", "under_review") if current else "under_review"

    prev_status = current.get("status") if current else None
    status_changed = prev_status is not None and prev_status != new_status

    result = {
        "type": "current_status",
        "status": new_status,
        "previous_status": prev_status,
        "checked_at": now,
        "status_changed": status_changed,
        "client_id": GOOGLE_CLIENT_ID[:20] + "..." if GOOGLE_CLIENT_ID else "",
    }

    # Upsert current status
    await db.google_verification_status.update_one(
        {"type": "current_status"},
        {"$set": result},
        upsert=True,
    )

    # Add to history log
    await db.google_verification_history.insert_one({
        "status": new_status,
        "checked_at": now,
        "status_changed": status_changed,
    })

    # Trim history to last 500 entries
    count = await db.google_verification_history.count_documents({})
    if count > 500:
        oldest = await db.google_verification_history.find().sort("checked_at", 1).limit(count - 500).to_list(count - 500)
        if oldest:
            ids = [d["_id"] for d in oldest]
            await db.google_verification_history.delete_many({"_id": {"$in": ids}})

    # Send alerts if status changed (email + push + in-app)
    if status_changed:
        await _send_status_change_alert(db, prev_status, new_status, now)
        await _send_push_notification(db, prev_status, new_status)

    return result


async def _send_status_change_alert(db, old_status: str, new_status: str, timestamp: str):
    """Send email alert when Google verification status changes."""
    try:
        from utils.email_service import is_email_configured

        if not is_email_configured():
            logger.warning("Email not configured — skipping verification alert")
            return

        alert_email = os.environ.get("ADMIN_EMAILS", "")

        status_emoji = {
            "verified": "&#9989;",
            "under_review": "&#9203;",
            "rejected": "&#10060;",
            "not_configured": "&#9888;",
        }

        is_good_news = new_status == "verified"
        accent = "#10B981" if is_good_news else "#F59E0B"
        emoji = status_emoji.get(new_status, "&#128276;")

        f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; background: #0F172A; border-radius: 16px; overflow: hidden; border: 1px solid #1E293B;">
            <div style="background: linear-gradient(135deg, {accent}22, {accent}08); padding: 32px 24px; text-align: center; border-bottom: 1px solid #1E293B;">
                <div style="font-size: 40px; margin-bottom: 8px;">{emoji}</div>
                <h1 style="color: #F8FAFC; font-size: 20px; margin: 0 0 4px;">Google OAuth Verification Update</h1>
                <p style="color: #94A3B8; font-size: 13px; margin: 0;">Status change detected at {timestamp[:19]}</p>
            </div>
            <div style="padding: 24px;">
                <div style="display: flex; gap: 12px; margin-bottom: 20px;">
                    <div style="flex: 1; background: #1E293B; border-radius: 10px; padding: 16px; text-align: center;">
                        <p style="color: #64748B; font-size: 11px; text-transform: uppercase; margin: 0 0 6px;">Previous</p>
                        <p style="color: #F59E0B; font-size: 15px; font-weight: 700; margin: 0; text-transform: capitalize;">{old_status or 'Unknown'}</p>
                    </div>
                    <div style="display: flex; align-items: center; color: #64748B; font-size: 20px;">&#8594;</div>
                    <div style="flex: 1; background: #1E293B; border-radius: 10px; padding: 16px; text-align: center;">
                        <p style="color: #64748B; font-size: 11px; text-transform: uppercase; margin: 0 0 6px;">Current</p>
                        <p style="color: {accent}; font-size: 15px; font-weight: 700; margin: 0; text-transform: capitalize;">{new_status}</p>
                    </div>
                </div>
                {'<p style="color: #10B981; font-size: 14px; text-align: center; background: #10B98115; padding: 12px; border-radius: 8px;">Your Google OAuth app has been verified! The unverified warning will no longer appear for users.</p>' if is_good_news else '<p style="color: #94A3B8; font-size: 13px;">Check your <a href="https://console.cloud.google.com/auth/branding" style="color: ' + accent + ';">Google Cloud Console</a> for more details.</p>'}
            </div>
            <div style="padding: 16px 24px; background: #0B1120; text-align: center;">
                <p style="color: #475569; font-size: 11px; margin: 0;">RealAICoach Admin Alerts</p>
            </div>
        </div>
        """

        from utils.email_service import send_catalog_template
        await send_catalog_template(
            recipient_email=alert_email,
            template_key="system_alert_admin",
            alert_type="Google OAuth Verification Status Change",
            severity="HIGH",
            description=f"Google OAuth verification status changed from {old_status} to {new_status}. Review required.",
            component="Google OAuth",
        )
        logger.info(f"Sent Google verification alert: {old_status} -> {new_status}")

    except Exception as e:
        logger.error(f"Failed to send verification alert: {e}")


async def _send_push_notification(db, old_status: str, new_status: str):
    """Send in-app + WebSocket + browser push notifications to all admin users."""
    try:
        from utils.notification_helper import create_notification

        status_labels = {
            "verified": "Verified",
            "under_review": "Under Review",
            "rejected": "Rejected",
            "action_required": "Action Required",
        }
        new_label = status_labels.get(new_status, new_status)
        old_label = status_labels.get(old_status, old_status)

        is_good = new_status == "verified"
        title = "Google OAuth Verified!" if is_good else f"Google Verification: {new_label}"
        message = (
            "Your Google OAuth app has been verified. The unverified warning will no longer appear for users."
            if is_good
            else f"Google OAuth verification status changed from {old_label} to {new_label}. Check the admin console for details."
        )

        # Find all admin users
        admin_cursor = db.users.find({"is_admin": True}, {"user_id": 1, "_id": 0})
        admins = await admin_cursor.to_list(50)

        for admin in admins:
            uid = admin.get("user_id")
            if uid:
                await create_notification(
                    user_id=uid,
                    title=title,
                    message=message,
                    notif_type="google_verification",
                    data={"old_status": old_status, "new_status": new_status, "action": "/admin-console"},
                )
        logger.info(f"Sent push notification to {len(admins)} admin(s): {old_status} -> {new_status}")

    except Exception as e:
        logger.error(f"Failed to send push notification: {e}")


async def get_verification_dashboard(db) -> dict:
    """Get full verification dashboard data."""
    current = await db.google_verification_status.find_one(
        {"type": "current_status"}, {"_id": 0}
    )

    # Get history (last 50 checks)
    history_cursor = db.google_verification_history.find(
        {}, {"_id": 0}
    ).sort("checked_at", -1).limit(50)
    history = await history_cursor.to_list(50)

    # Get alert settings
    settings = await db.google_verification_settings.find_one(
        {"type": "settings"}, {"_id": 0}
    )

    submission_date = "2026-03-14T23:00:00Z"

    timeline = [
        {"step": "Privacy Policy Updated", "status": "completed", "date": "2026-03-14"},
        {"step": "Google Search Console Verified", "status": "completed", "date": "2026-03-14"},
        {"step": "Branding Submitted for Review", "status": "completed", "date": "2026-03-14"},
        {"step": "Trust & Safety Team Review", "status": "in_progress", "date": None, "estimate": "3-5 business days"},
        {"step": "Full Verification Complete", "status": "pending", "date": None, "estimate": "4-6 weeks"},
    ]

    return {
        "current_status": current or {
            "status": "under_review",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "client_id": (GOOGLE_CLIENT_ID[:20] + "...") if GOOGLE_CLIENT_ID else "",
        },
        "submission_date": submission_date,
        "timeline": timeline,
        "history": history[:20],
        "settings": settings or {
            "email_alerts_enabled": True,
            "alert_email": os.environ.get("ADMIN_EMAILS", ""),
            "check_interval_hours": 6,
        },
        "checklist": {
            "privacy_policy": {"status": "done", "label": "Privacy Policy with Google disclosures"},
            "terms_of_service": {"status": "done", "label": "Terms of Service accessible"},
            "search_console": {"status": "done", "label": "Google Search Console domain verified"},
            "meta_tag": {"status": "done", "label": "Site verification meta tag deployed"},
            "branding_submitted": {"status": "done", "label": "Branding submitted for review"},
            "trust_safety_review": {"status": "in_progress", "label": "Trust & Safety Team review"},
            "full_approval": {"status": "pending", "label": "Full verification approval"},
        },
    }
