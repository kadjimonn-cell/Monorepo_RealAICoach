"""
Admin Push Notifications — Real-time critical event detection and WebSocket push.
Runs periodically to detect anomalies and pushes alerts to all connected admin users.
"""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("admin_push")

# Track last push times to avoid duplicate alerts
_last_pushed: dict = {}
COOLDOWN_SECONDS = 120  # Don't re-push the same alert type within 2 minutes


async def detect_and_push_admin_alerts():
    """Main detection loop — called by scheduler every 30-60 seconds."""
    try:
        from routes.db import db
        from utils.ws_manager import ws_manager

        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        five_min_ago = now - timedelta(minutes=5)
        alerts_to_push = []

        # 1. Error spike detection
        try:
            recent_errors = await db.live_activity_events.count_documents({
                "event_type": "error",
                "timestamp": {"$gte": five_min_ago.isoformat()}
            })
            if recent_errors >= 5 and _should_push("error_spike"):
                alerts_to_push.append({
                    "type": "admin_alert",
                    "severity": "critical",
                    "alert_type": "error_spike",
                    "title": "Error Spike Detected",
                    "message": f"{recent_errors} errors in the last 5 minutes — investigate immediately",
                    "timestamp": now.isoformat(),
                    "count": recent_errors,
                })
        except Exception:
            pass

        # 2. New user signups
        try:
            recent_signups = await db.users.count_documents({
                "created_at": {"$gte": five_min_ago.isoformat()}
            })
            if recent_signups > 0 and _should_push("new_signup"):
                alerts_to_push.append({
                    "type": "admin_alert",
                    "severity": "info",
                    "alert_type": "new_signup",
                    "title": "New User Signup",
                    "message": f"{recent_signups} new user{'s' if recent_signups > 1 else ''} signed up in the last 5 minutes",
                    "timestamp": now.isoformat(),
                    "count": recent_signups,
                })
        except Exception:
            pass

        # 3. Payment events
        try:
            recent_payments = await db.payments.count_documents({
                "created_at": {"$gte": five_min_ago.isoformat()},
                "status": {"$in": ["completed", "succeeded", "active"]}
            })
            if recent_payments > 0 and _should_push("payment_success"):
                alerts_to_push.append({
                    "type": "admin_alert",
                    "severity": "info",
                    "alert_type": "payment_success",
                    "title": "Payment Received",
                    "message": f"{recent_payments} successful payment{'s' if recent_payments > 1 else ''} processed",
                    "timestamp": now.isoformat(),
                    "count": recent_payments,
                })
            # Payment failures
            recent_failures = await db.payments.count_documents({
                "created_at": {"$gte": five_min_ago.isoformat()},
                "status": {"$in": ["failed", "declined", "cancelled"]}
            })
            if recent_failures > 0 and _should_push("payment_failure"):
                alerts_to_push.append({
                    "type": "admin_alert",
                    "severity": "warning",
                    "alert_type": "payment_failure",
                    "title": "Payment Failure",
                    "message": f"{recent_failures} payment{'s' if recent_failures > 1 else ''} failed — check billing system",
                    "timestamp": now.isoformat(),
                    "count": recent_failures,
                })
        except Exception:
            pass

        # 4. Support ticket surge
        try:
            recent_tickets = await db.support_tickets.count_documents({
                "created_at": {"$gte": one_hour_ago.isoformat()},
                "status": {"$in": ["open", "pending"]}
            })
            if recent_tickets >= 5 and _should_push("ticket_surge"):
                alerts_to_push.append({
                    "type": "admin_alert",
                    "severity": "warning",
                    "alert_type": "ticket_surge",
                    "title": "Support Ticket Surge",
                    "message": f"{recent_tickets} open/pending tickets in the last hour",
                    "timestamp": now.isoformat(),
                    "count": recent_tickets,
                })
        except Exception:
            pass

        # 5. High API response times (from web vitals)
        try:
            slow_vitals = await db.web_vitals.find(
                {"metric": "TTFB", "value": {"$gt": 2000}, "timestamp": {"$gte": five_min_ago.isoformat()}},
                {"_id": 0}
            ).to_list(5)
            if len(slow_vitals) >= 3 and _should_push("slow_api"):
                avg_ttfb = sum(v.get("value", 0) for v in slow_vitals) / len(slow_vitals)
                alerts_to_push.append({
                    "type": "admin_alert",
                    "severity": "warning",
                    "alert_type": "slow_api",
                    "title": "Slow API Response",
                    "message": f"Average TTFB: {avg_ttfb:.0f}ms — {len(slow_vitals)} slow requests detected",
                    "timestamp": now.isoformat(),
                })
        except Exception:
            pass

        # 6. Active sessions spike
        try:
            active_sessions = await db.user_sessions.count_documents({
                "expires_at": {"$gt": now.isoformat()}
            })
            if active_sessions >= 50 and _should_push("session_spike"):
                alerts_to_push.append({
                    "type": "admin_alert",
                    "severity": "info",
                    "alert_type": "session_spike",
                    "title": "High Active Sessions",
                    "message": f"{active_sessions} concurrent active sessions — platform under load",
                    "timestamp": now.isoformat(),
                    "count": active_sessions,
                })
        except Exception:
            pass

        # 7. Security events (failed logins, suspicious activity)
        try:
            failed_logins = await db.security_events.count_documents({
                "event_type": {"$in": ["failed_login", "suspicious_login", "brute_force"]},
                "created_at": {"$gte": five_min_ago.isoformat()}
            })
            if failed_logins >= 3 and _should_push("security_alert"):
                alerts_to_push.append({
                    "type": "admin_alert",
                    "severity": "critical",
                    "alert_type": "security_alert",
                    "title": "Security Alert",
                    "message": f"{failed_logins} suspicious login attempts in the last 5 minutes",
                    "timestamp": now.isoformat(),
                    "count": failed_logins,
                })
        except Exception:
            pass

        # Push all alerts via WebSocket to admin users
        if alerts_to_push:
            admin_users = await db.users.find(
                {"is_admin": True}, {"_id": 0, "user_id": 1}
            ).to_list(50)
            admin_ids = [u["user_id"] for u in admin_users]

            for alert in alerts_to_push:
                _last_pushed[alert["alert_type"]] = now
                try:
                    await ws_manager.send_to_admins(alert, admin_ids)
                    logger.info(f"Pushed admin alert: {alert['alert_type']} ({alert['severity']})")
                except Exception as e:
                    logger.warning(f"Failed to push alert {alert['alert_type']}: {e}")

            # Also store in notifications collection for bell persistence
            for alert in alerts_to_push:
                try:
                    await db.admin_push_notifications.insert_one({
                        "type": alert["alert_type"],
                        "severity": alert["severity"],
                        "title": alert["title"],
                        "message": alert["message"],
                        "timestamp": now.isoformat(),
                        "read": False,
                    })
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Admin push notification error: {e}")


def _should_push(alert_type: str) -> bool:
    """Check cooldown to avoid spamming the same alert."""
    now = datetime.now(timezone.utc)
    last = _last_pushed.get(alert_type)
    if last and (now - last).total_seconds() < COOLDOWN_SECONDS:
        return False
    return True


async def emit_realtime_alert(alert_type: str, severity: str, title: str, message: str):
    """
    Directly push a real-time alert to all connected admins.
    Called from route handlers when critical events happen.
    """
    try:
        from routes.db import db
        from utils.ws_manager import ws_manager

        if not _should_push(alert_type):
            return

        now = datetime.now(timezone.utc)
        _last_pushed[alert_type] = now

        alert = {
            "type": "admin_alert",
            "severity": severity,
            "alert_type": alert_type,
            "title": title,
            "message": message,
            "timestamp": now.isoformat(),
        }

        admin_users = await db.users.find(
            {"is_admin": True}, {"_id": 0, "user_id": 1}
        ).to_list(50)
        admin_ids = [u["user_id"] for u in admin_users]

        await ws_manager.send_to_admins(alert, admin_ids)

        await db.admin_push_notifications.insert_one({
            "type": alert_type,
            "severity": severity,
            "title": title,
            "message": message,
            "timestamp": now.isoformat(),
            "read": False,
        })

        logger.info(f"Emitted realtime alert: {alert_type}")
    except Exception as e:
        logger.warning(f"Failed to emit realtime alert: {e}")
