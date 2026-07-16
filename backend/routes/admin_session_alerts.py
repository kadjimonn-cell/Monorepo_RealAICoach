"""Admin Session Alert Service — email alerts for critical-risk sessions."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging
from routes.db import db, require_admin

logger = logging.getLogger(__name__)


async def _send_alert_email(subject: str, body_text: str, recipients: list[str] = None):
    """Send an alert email to admin(s)."""
    try:
        from utils.email_service import is_email_configured

        if not is_email_configured():
            logger.warning("Email not configured, skipping alert email")
            return
        for addr in recipients or ["admin@realaicoach.app"]:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=addr,
                template_key="system_alert_admin",
                alert_type=subject,
                severity="HIGH",
                description=body_text[:500] if body_text else subject,
                component="Session Alerts",
            )
    except Exception as e:
        logger.error(f"Alert email send failed: {e}")


router = APIRouter(prefix="/admin/session-alerts", tags=["Session Alerts"])

_DEFAULT_SETTINGS = {
    "enabled": False,
    "min_risk_level": "critical",
    "notify_emails": [],
    "cooldown_minutes": 60,
}


@router.get("/settings")
async def get_alert_settings(request: Request):
    """Get current session alert settings."""
    await require_admin(request)
    settings = await db.session_alert_settings.find_one({"_id": "global"})
    if not settings:
        return _DEFAULT_SETTINGS
    settings.pop("_id", None)
    return settings


@router.put("/settings")
async def update_alert_settings(request: Request):
    """Update session alert settings."""
    await require_admin(request)
    body = await request.json()
    updates = {}
    if "enabled" in body:
        updates["enabled"] = bool(body["enabled"])
    if "min_risk_level" in body:
        level = body["min_risk_level"]
        if level not in ("critical", "high", "medium", "low"):
            return JSONResponse({"detail": "min_risk_level must be critical, high, medium, or low"}, status_code=400)
        updates["min_risk_level"] = level
    if "notify_emails" in body:
        emails = body["notify_emails"]
        if not isinstance(emails, list):
            return JSONResponse({"detail": "notify_emails must be a list"}, status_code=400)
        updates["notify_emails"] = [e.strip() for e in emails if isinstance(e, str) and "@" in e]
    if "cooldown_minutes" in body:
        try:
            updates["cooldown_minutes"] = max(5, int(body["cooldown_minutes"]))
        except (ValueError, TypeError):
            return JSONResponse({"detail": "cooldown_minutes must be a positive integer"}, status_code=400)

    if not updates:
        return JSONResponse({"detail": "No valid fields to update"}, status_code=400)

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.session_alert_settings.update_one({"_id": "global"}, {"$set": updates}, upsert=True)
    result = await db.session_alert_settings.find_one({"_id": "global"})
    result.pop("_id", None)
    return result


@router.get("/history")
async def alert_history(request: Request, limit: int = 30):
    """Get session alert history."""
    await require_admin(request)
    alerts = await db.session_alert_history.find({}, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(limit)
    return {"alerts": alerts}


async def check_and_send_alerts(suspicious_data: dict):
    """Check suspicious data against alert settings and send emails if thresholds met.
    Called after suspicious activity detection runs.
    """
    from utils.email_service import render_email_logo

    settings = await db.session_alert_settings.find_one({"_id": "global"})
    if not settings or not settings.get("enabled"):
        return

    notify_emails = settings.get("notify_emails", [])
    if not notify_emails:
        return

    min_level = settings.get("min_risk_level", "critical")
    cooldown = settings.get("cooldown_minutes", 60)
    level_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    min_level_num = level_order.get(min_level, 0)

    flagged = suspicious_data.get("flagged_users", [])
    alertable = [u for u in flagged if level_order.get(u.get("risk_level"), 3) <= min_level_num]

    if not alertable:
        return

    # Check cooldown
    now = datetime.now(timezone.utc)
    last_alert = await db.session_alert_history.find_one({}, sort=[("sent_at", -1)])
    if last_alert:
        last_sent = last_alert.get("sent_at", "")
        try:
            if isinstance(last_sent, str):
                last_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
            else:
                last_dt = last_sent
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if (now - last_dt).total_seconds() < cooldown * 60:
                return
        except Exception:
            pass

    # Build email content
    risk_summary = suspicious_data.get("risk_summary", {})
    f"[RealAICoach Security] {len(alertable)} suspicious session(s) detected"
    rows = ""
    for u in alertable[:10]:
        flags_text = ", ".join(f.get("detail", f.get("type", "")) for f in u.get("flags", [])[:3])
        rows += f"""
        <tr style="border-bottom:1px solid #2d3748">
          <td style="padding:8px;color:#e53e3e;font-weight:700">{u.get("risk_score", 0)}</td>
          <td style="padding:8px">{u.get("email", "Unknown")}</td>
          <td style="padding:8px;text-transform:uppercase;color:{"#e53e3e" if u.get("risk_level") == "critical" else "#ed8936"}">{u.get("risk_level", "unknown")}</td>
          <td style="padding:8px">{u.get("session_count", 0)} sessions, {len(u.get("distinct_ips", []))} IPs</td>
          <td style="padding:8px;font-size:12px;color:#a0aec0">{flags_text}</td>
        </tr>"""

    logo_html = render_email_logo(variant="security")
    f"""
    <div style="font-family:system-ui,-apple-system,sans-serif;max-width:700px;margin:0 auto;background:#1a202c;color:#e2e8f0;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#e53e3e,#c53030);padding:24px 32px">
        {logo_html}
        <h1 style="margin:0;font-size:20px;color:#fff">Security Alert: Suspicious Sessions Detected</h1>
        <p style="margin:8px 0 0;color:rgba(255,255,255,0.8);font-size:14px">{len(alertable)} user(s) flagged at {min_level}+ risk level</p>
      </div>
      <div style="padding:24px 32px">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px">
          <tr>
            <td width="32%" style="background:#2d3748;border-radius:8px;padding:12px;text-align:center">
              <div style="color:#e53e3e;font-size:24px;font-weight:800">{risk_summary.get("critical", 0)}</div>
              <div style="color:#a0aec0;font-size:11px">Critical</div>
            </td>
            <td width="2%"></td>
            <td width="32%" style="background:#2d3748;border-radius:8px;padding:12px;text-align:center">
              <div style="color:#ed8936;font-size:24px;font-weight:800">{risk_summary.get("high", 0)}</div>
              <div style="color:#a0aec0;font-size:11px">High</div>
            </td>
            <td width="2%"></td>
            <td width="32%" style="background:#2d3748;border-radius:8px;padding:12px;text-align:center">
              <div style="color:#ecc94b;font-size:24px;font-weight:800">{risk_summary.get("medium", 0)}</div>
              <div style="color:#a0aec0;font-size:11px">Medium</div>
            </td>
          </tr>
        </table>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="border-bottom:2px solid #4a5568">
              <th style="text-align:left;padding:8px;color:#a0aec0">Score</th>
              <th style="text-align:left;padding:8px;color:#a0aec0">User</th>
              <th style="text-align:left;padding:8px;color:#a0aec0">Risk</th>
              <th style="text-align:left;padding:8px;color:#a0aec0">Activity</th>
              <th style="text-align:left;padding:8px;color:#a0aec0">Flags</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        <p style="margin-top:24px;color:#a0aec0;font-size:12px">Scanned {suspicious_data.get("scanned_sessions", 0)} sessions across {suspicious_data.get("scanned_users", 0)} users at {now.strftime("%Y-%m-%d %H:%M UTC")}</p>
        <p style="margin-top:8px;color:#718096;font-size:11px">This is an automated alert from the RealAICoach Executive Control Center. Review sessions in the admin dashboard.</p>
      </div>
    </div>
    """

    try:
        from utils.email_service import is_email_configured

        if not is_email_configured():
            logger.warning("Session alert: email not configured, skipping")
            return

        for email in notify_emails:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=email,
                template_key="session_security_alert",
                sessions=alertable,
                scanned_sessions=suspicious_data.get("scanned_sessions", 0),
                scanned_users=suspicious_data.get("scanned_users", 0),
            )
        logger.info(f"Session security alert sent to {len(notify_emails)} recipient(s)")

        await db.session_alert_history.insert_one(
            {
                "sent_at": now.isoformat(),
                "recipients": notify_emails,
                "flagged_count": len(alertable),
                "min_risk_level": min_level,
                "risk_summary": risk_summary,
                "top_users": [
                    {"email": u.get("email"), "risk_score": u.get("risk_score"), "risk_level": u.get("risk_level")}
                    for u in alertable[:5]
                ],
            }
        )
    except Exception as e:
        logger.error(f"Session alert send error: {e}")
