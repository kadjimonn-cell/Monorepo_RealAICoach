"""ASO Keyword Ranking Alerts — Settings, history, and email notification logic.

Split from aso_unified.py for modularity. All endpoints under /admin/aso-unified/keywords/alerts.
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request

from routes.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/aso-unified/keywords/alerts", tags=["ASO Alerts"])


@router.get("/settings")
async def get_alert_settings(request: Request):
    """Get ASO keyword alert settings."""
    settings = await db.aso_alert_settings.find_one({"type": "keyword_alerts"}, {"_id": 0})
    if not settings:
        settings = {
            "type": "keyword_alerts",
            "enabled": False,
            "threshold": 10,
            "alert_email": "",
            "notify_on_improvement": True,
            "notify_on_decline": True,
            "last_alert_sent": None,
        }
    return settings


@router.put("/settings")
async def update_alert_settings(request: Request):
    """Update ASO keyword alert settings."""
    body = await request.json()
    settings = {
        "type": "keyword_alerts",
        "enabled": body.get("enabled", False),
        "threshold": max(1, min(100, body.get("threshold", 10))),
        "alert_email": body.get("alert_email", "").strip(),
        "notify_on_improvement": body.get("notify_on_improvement", True),
        "notify_on_decline": body.get("notify_on_decline", True),
    }
    await db.aso_alert_settings.update_one(
        {"type": "keyword_alerts"}, {"$set": settings}, upsert=True
    )
    return {"status": "updated", **settings}


@router.get("/history")
async def get_alert_history(request: Request):
    """Get history of sent keyword ranking alerts."""
    alerts = await db.aso_keyword_alerts.find(
        {}, {"_id": 0}
    ).sort("sent_at", -1).to_list(50)
    return {"alerts": alerts, "total": len(alerts)}


async def check_and_send_ranking_alerts(keyword: str, prev_apple: int, new_apple: int, prev_google: int, new_google: int):
    """Check if ranking changes exceed threshold and send email alerts."""
    settings = await db.aso_alert_settings.find_one({"type": "keyword_alerts"})
    if not settings or not settings.get("enabled") or not settings.get("alert_email"):
        return

    threshold = settings.get("threshold", 10)
    alert_email = settings["alert_email"]
    changes = []

    apple_delta = new_apple - prev_apple if prev_apple and new_apple else 0
    google_delta = new_google - prev_google if prev_google and new_google else 0

    if abs(apple_delta) >= threshold:
        is_improvement = apple_delta < 0
        if (is_improvement and settings.get("notify_on_improvement")) or (not is_improvement and settings.get("notify_on_decline")):
            changes.append({
                "store": "App Store", "keyword": keyword,
                "prev_rank": prev_apple, "new_rank": new_apple,
                "delta": apple_delta, "direction": "improved" if is_improvement else "declined",
            })

    if abs(google_delta) >= threshold:
        is_improvement = google_delta < 0
        if (is_improvement and settings.get("notify_on_improvement")) or (not is_improvement and settings.get("notify_on_decline")):
            changes.append({
                "store": "Google Play", "keyword": keyword,
                "prev_rank": prev_google, "new_rank": new_google,
                "delta": google_delta, "direction": "improved" if is_improvement else "declined",
            })

    if not changes:
        return

    try:
        from utils.email_service import render_email_logo
        now = datetime.now(timezone.utc)
        logo_html = render_email_logo(variant="admin")

        rows_html = ""
        for c in changes:
            color = "#10B981" if c["direction"] == "improved" else "#EF4444"
            arrow = "&#8593;" if c["direction"] == "improved" else "&#8595;"
            rows_html += f"""<tr>
              <td style="padding:10px 14px;border-bottom:1px solid #f1f5f9;font-size:13px;font-weight:600;color:#334155;">{c["keyword"]}</td>
              <td style="padding:10px 14px;border-bottom:1px solid #f1f5f9;font-size:12px;color:#64748b;">{c["store"]}</td>
              <td style="padding:10px 14px;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b;">#{c["prev_rank"]}</td>
              <td style="padding:10px 14px;border-bottom:1px solid #f1f5f9;font-size:13px;font-weight:700;color:{color};">#{c["new_rank"]} <span style="font-size:11px;">{arrow} {abs(c["delta"])}</span></td>
            </tr>"""

        f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:560px;margin:20px auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#7c3aed,#2563eb);padding:28px 24px;text-align:center;">
    {logo_html}
    <h1 style="color:#fff;font-size:20px;margin:12px 0 4px;font-weight:800;">Keyword Ranking Alert</h1>
    <p style="color:rgba(255,255,255,0.8);font-size:12px;margin:0;">Significant position changes detected</p>
  </div>
  <div style="padding:24px;">
    <p style="color:#475569;font-size:13px;line-height:1.6;margin:0 0 16px;">Your ASO keyword rankings changed by <strong>{threshold}+ positions</strong>. Here's the summary:</p>
    <table style="width:100%;border-collapse:collapse;border-radius:10px;overflow:hidden;border:1px solid #e2e8f0;">
      <thead><tr style="background:#f8fafc;">
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Keyword</th>
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Store</th>
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Previous</th>
        <th style="padding:10px 14px;text-align:left;font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Current</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p style="color:#94a3b8;font-size:11px;margin:20px 0 0;text-align:center;">Data source: iTunes Search API &amp; Google Play Scraper &bull; {now.strftime('%B %d, %Y %H:%M UTC')}</p>
  </div>
</div></body></html>"""

        from utils.email_service import send_catalog_template
        result = await send_catalog_template(
            recipient_email=alert_email,
            template_key="aso_keyword_alert",
            changes=changes,
            threshold=threshold,
        )

        await db.aso_keyword_alerts.insert_one({
            "sent_at": now.isoformat(),
            "email": alert_email,
            "changes": changes,
            "email_sent": result.get("success", False),
            "threshold": threshold,
        })

        await db.aso_alert_settings.update_one(
            {"type": "keyword_alerts"},
            {"$set": {"last_alert_sent": now.isoformat()}}
        )

        logger.info(f"ASO ranking alert sent to {alert_email}: {len(changes)} changes")
    except Exception as e:
        logger.error(f"Failed to send ASO ranking alert: {e}")
