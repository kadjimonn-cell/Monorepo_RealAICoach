"""Automated newsletter campaign system — fully automated monthly digest."""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from routes.db import db
from routes.auth import get_current_user
from utils.email_service import is_email_configured, render_email_logo
from utils.email_templates import _premium_mini_footer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/newsletter/campaigns", tags=["newsletter-campaigns"])

CAMPAIGN_INTERVAL_DAYS = 30

BG_IMAGES = [
    "https://images.unsplash.com/photo-1758551051834-61f10a361b73?w=1200&q=80",
    "https://images.unsplash.com/photo-1770339030394-d170e336470d?w=1200&q=80",
    "https://images.unsplash.com/photo-1770409747297-aadfdd473f32?w=1200&q=80",
    "https://images.unsplash.com/photo-1737505598998-693328b57ae3?w=1200&q=80",
    "https://images.unsplash.com/photo-1770954001166-2945c5433f85?w=1200&q=80",
    "https://images.pexels.com/photos/28428592/pexels-photo-28428592.jpeg?auto=compress&w=1200",
]


def _build_monthly_digest_html(month_label: str, stats: dict) -> str:
    logo = render_email_logo("default")
    datetime.now().year
    total_users = stats.get("total_users", 0)
    new_subs = stats.get("new_subscribers_30d", 0)
    ai_requests = stats.get("ai_requests_30d", 0)
    top_features = stats.get("top_features", ["AI Coaching", "Problem Solver", "Learning Hub"])

    features_html = ""
    feature_icons = ["&#128640;", "&#9889;", "&#127891;", "&#128161;", "&#127775;"]
    for i, feat in enumerate(top_features[:5]):
        icon = feature_icons[i % len(feature_icons)]
        features_html += f"""
        <tr><td style="padding:8px 0;">
          <table cellpadding="0" cellspacing="0"><tr>
            <td style="width:36px;height:36px;background:#F0FDF4;border-radius:10px;text-align:center;vertical-align:middle;font-size:16px;">{icon}</td>
            <td style="padding-left:14px;">
              <strong style="color:#1E293B;font-size:14px;">{feat}</strong>
            </td>
          </tr></table>
        </td></tr>"""

    tips = [
        "Use the AI Problem Solver for complex scenarios — it learns from your coaching style.",
        "Check your Learning Hub weekly for personalized course recommendations.",
        "Review your My Analytics dashboard to track your coaching progression.",
    ]
    tips_html = ""
    for tip in tips:
        tips_html += f'<li style="color:#475569;font-size:13px;line-height:1.8;margin-bottom:6px;">{tip}</li>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:40px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 50%,#0F172A 100%);padding:44px 32px 36px;text-align:center;">
          {logo}
          <h1 style="color:#F8FAFC;font-size:22px;font-weight:800;margin:16px 0 6px;letter-spacing:-0.3px;">Monthly AI Coaching Digest</h1>
          <p style="color:#00D4AA;font-size:14px;font-weight:600;margin:0;">{month_label}</p>
        </td></tr>

        <!-- Platform Stats Banner -->
        <tr><td style="background:#F8FAFC;padding:24px 32px;">
          <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td style="text-align:center;padding:12px;background:#ffffff;border-radius:12px;border:1px solid #E2E8F0;width:33%;">
              <div style="color:#00D4AA;font-size:24px;font-weight:800;">{total_users:,}</div>
              <div style="color:#64748B;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Active Users</div>
            </td>
            <td style="width:12px;"></td>
            <td style="text-align:center;padding:12px;background:#ffffff;border-radius:12px;border:1px solid #E2E8F0;width:33%;">
              <div style="color:#3B82F6;font-size:24px;font-weight:800;">+{new_subs}</div>
              <div style="color:#64748B;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">New Members</div>
            </td>
            <td style="width:12px;"></td>
            <td style="text-align:center;padding:12px;background:#ffffff;border-radius:12px;border:1px solid #E2E8F0;width:33%;">
              <div style="color:#8B5CF6;font-size:24px;font-weight:800;">{ai_requests:,}</div>
              <div style="color:#64748B;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">AI Requests</div>
            </td>
          </tr></table>
        </td></tr>

        <!-- Trending Features -->
        <tr><td style="padding:28px 32px 8px;">
          <h2 style="color:#0F172A;font-size:17px;font-weight:700;margin:0 0 4px;">Trending This Month</h2>
          <p style="color:#64748B;font-size:13px;margin:0 0 16px;">Most popular AI coaching features</p>
          <table width="100%" cellpadding="0" cellspacing="0">
            {features_html}
          </table>
        </td></tr>

        <!-- Tips Section -->
        <tr><td style="padding:20px 32px 28px;">
          <div style="background:linear-gradient(135deg,#EFF6FF,#F0FDF4);border-radius:12px;padding:20px 24px;border:1px solid #E2E8F0;">
            <h3 style="color:#0F172A;font-size:15px;font-weight:700;margin:0 0 12px;">Pro Tips for This Month</h3>
            <ul style="margin:0;padding-left:18px;">
              {tips_html}
            </ul>
          </div>
        </td></tr>

        <!-- CTA -->
        <tr><td style="padding:0 32px 32px;text-align:center;">
          <a href="#" style="display:inline-block;background:#00D4AA;color:#0F172A;font-size:14px;font-weight:700;padding:14px 40px;border-radius:10px;text-decoration:none;letter-spacing:0.3px;">Open Your Dashboard</a>
        </td></tr>

        <!-- Footer -->
        {_premium_mini_footer(reason="you subscribed to RealAICoach updates")}
      </table>
    </body>
    </html>
    """


async def _gather_platform_stats() -> dict:
    """Gather real platform statistics for the digest."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    total_users = await db.users.count_documents({})
    new_subs = await db.newsletter_subscribers.count_documents({"subscribed_at": {"$gte": thirty_days_ago}})
    ai_requests = (
        await db.ai_requests.count_documents({"created_at": {"$gte": thirty_days_ago}})
        if "ai_requests" in await db.list_collection_names()
        else 0
    )

    return {
        "total_users": total_users,
        "new_subscribers_30d": new_subs,
        "ai_requests_30d": ai_requests,
        "top_features": ["AI Coaching Tools", "Problem Solver", "Learning Hub", "Daily Briefing", "My Analytics"],
    }


async def run_monthly_campaign(segment: str = None):
    """Automated monthly digest — called by scheduler every day, sends every 30 days.
    If segment is provided, sends to that segment only (no interval check)."""
    logger.info(f"Campaign check: segment={segment}")

    if not segment:
        last_campaign = await db.newsletter_campaigns.find_one(
            {"status": "sent", "segment": {"$exists": False}}, {"_id": 0}, sort=[("sent_at", -1)]
        )

        now = datetime.now(timezone.utc)
        if last_campaign and last_campaign.get("sent_at"):
            last_sent = datetime.fromisoformat(last_campaign["sent_at"])
            days_since = (now - last_sent).days
            if days_since < CAMPAIGN_INTERVAL_DAYS:
                logger.info(f"Last campaign sent {days_since} days ago. Skipping.")
                return {"action": "skipped", "reason": "interval_not_reached"}
    else:
        now = datetime.now(timezone.utc)

    if not is_email_configured():
        logger.warning("Email not configured — skipping campaign.")
        return {"action": "skipped", "reason": "email_not_configured"}

    sub_query = {"status": "active"}
    if segment:
        sub_query["segments"] = segment

    subscribers = await db.newsletter_subscribers.find(sub_query, {"_id": 0, "email": 1}).to_list(length=100000)

    if not subscribers:
        logger.info("No active subscribers — skipping campaign.")
        return {"action": "skipped", "reason": "no_subscribers"}

    month_label = now.strftime("%B %Y")
    stats = await _gather_platform_stats()
    _build_monthly_digest_html(month_label, stats)
    subject = f"Your Monthly AI Coaching Digest — {month_label}"

    sent_count = 0
    failed_count = 0
    for sub in subscribers:
        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=sub["email"],
                template_key="newsletter_monthly_campaign",
                month_label=month_label,
                total_users=stats.get("total_users", 0),
                new_subscribers=stats.get("new_subscribers_30d", 0),
                ai_requests=stats.get("ai_requests_30d", 0),
                top_features=stats.get("top_features", ["AI Coaching", "Problem Solver", "Learning Hub"]),
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.warning(f"Campaign email failed for {sub['email']}: {e}")

    campaign_record = {
        "campaign_id": f"campaign_{now.strftime('%Y%m%d_%H%M%S')}",
        "type": "monthly_digest" if not segment else f"segment_{segment}",
        "subject": subject,
        "month_label": month_label,
        "status": "sent",
        "sent_at": now.isoformat(),
        "subscriber_count": len(subscribers),
        "sent_count": sent_count,
        "failed_count": failed_count,
        "stats_snapshot": stats,
    }
    if segment:
        campaign_record["segment"] = segment
    await db.newsletter_campaigns.insert_one(campaign_record)

    logger.info(f"Monthly campaign sent: {sent_count}/{len(subscribers)} delivered, {failed_count} failed.")
    return {"action": "sent", "sent": sent_count, "failed": failed_count, "total": len(subscribers)}


# ── API Endpoints ──


@router.get("/dashboard")
async def get_campaign_dashboard(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    now = datetime.now(timezone.utc)

    # Campaign history (last 12)
    campaigns_cursor = db.newsletter_campaigns.find({}, {"_id": 0}).sort("sent_at", -1).limit(12)
    campaigns = await campaigns_cursor.to_list(length=12)

    # Total stats
    total_campaigns = await db.newsletter_campaigns.count_documents({"status": "sent"})
    total_emails_sent = 0
    total_failed = 0
    for c in campaigns:
        total_emails_sent += c.get("sent_count", 0)
        total_failed += c.get("failed_count", 0)

    # All-time stats from all campaigns
    all_campaigns = (
        await db.newsletter_campaigns.find(
            {"status": "sent"},
            {"_id": 0, "sent_count": 1, "failed_count": 1, "subscriber_count": 1, "sent_at": 1, "month_label": 1},
        )
        .sort("sent_at", -1)
        .to_list(length=100)
    )

    all_time_sent = sum(c.get("sent_count", 0) for c in all_campaigns)
    all_time_failed = sum(c.get("failed_count", 0) for c in all_campaigns)

    # Delivery trend (last 6 campaigns)
    delivery_trend = []
    for c in all_campaigns[:6]:
        delivery_trend.append(
            {
                "month": c.get("month_label", ""),
                "sent": c.get("sent_count", 0),
                "failed": c.get("failed_count", 0),
                "subscribers": c.get("subscriber_count", 0),
            }
        )
    delivery_trend.reverse()

    # Next send date
    last_campaign = all_campaigns[0] if all_campaigns else None
    next_send = None
    days_until_next = CAMPAIGN_INTERVAL_DAYS
    if last_campaign and last_campaign.get("sent_at"):
        last_sent = datetime.fromisoformat(last_campaign["sent_at"])
        next_dt = last_sent + timedelta(days=CAMPAIGN_INTERVAL_DAYS)
        next_send = next_dt.isoformat()
        days_until_next = max(0, (next_dt - now).days)

    # Active subscriber count
    active_subs = await db.newsletter_subscribers.count_documents({"status": "active"})

    # Delivery rate
    delivery_rate = round((all_time_sent / max(all_time_sent + all_time_failed, 1)) * 100, 1)

    return {
        "total_campaigns": total_campaigns,
        "total_emails_sent": all_time_sent,
        "total_failed": all_time_failed,
        "delivery_rate": delivery_rate,
        "active_subscribers": active_subs,
        "next_send_date": next_send,
        "days_until_next": days_until_next,
        "campaign_interval_days": CAMPAIGN_INTERVAL_DAYS,
        "campaigns": campaigns,
        "delivery_trend": delivery_trend,
        "bg_images": BG_IMAGES,
    }


@router.post("/trigger")
async def trigger_campaign_manually(user=Depends(get_current_user), segment: str = None):
    """Admin manual trigger — sends campaign immediately. Optional segment filter."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    result = await run_monthly_campaign(segment=segment)
    return result



@router.get("/preview-email")
async def preview_campaign_email(user=Depends(get_current_user)):
    """Preview the monthly digest email template with app download badges."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    from fastapi.responses import HTMLResponse
    html = _build_monthly_digest_html(
        month_label="March 2026",
        stats={
            "total_users": 1250,
            "new_subscribers_30d": 87,
            "ai_requests_30d": 4200,
            "top_features": ["AI Interview Analysis", "Smart Scheduling", "Career Insights"],
        },
    )
    return HTMLResponse(content=html)
