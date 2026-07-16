"""Newsletter analytics endpoints for admin dashboard."""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from routes.db import db
from routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/newsletter", tags=["newsletter-analytics"])


@router.get("/analytics")
async def get_newsletter_analytics(user=Depends(get_current_user)):
    # Require authentication for analytics access
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total = await db.newsletter_subscribers.count_documents({"status": "active"})
    today_count = await db.newsletter_subscribers.count_documents({"subscribed_at": {"$gte": today_start.isoformat()}})

    # Weekly trend (last 7 days)
    weekly_data = []
    for i in range(6, -1, -1):
        day_start = (today_start - timedelta(days=i)).isoformat()
        day_end = (today_start - timedelta(days=i - 1)).isoformat() if i > 0 else now.isoformat()
        count = await db.newsletter_subscribers.count_documents({"subscribed_at": {"$gte": day_start, "$lt": day_end}})
        day_label = (today_start - timedelta(days=i)).strftime("%a")
        weekly_data.append({"day": day_label, "count": count})

    # Monthly trend (last 30 days grouped by week)
    monthly_data = []
    for w in range(3, -1, -1):
        wk_start = (today_start - timedelta(days=(w + 1) * 7)).isoformat()
        wk_end = (today_start - timedelta(days=w * 7)).isoformat()
        count = await db.newsletter_subscribers.count_documents({"subscribed_at": {"$gte": wk_start, "$lt": wk_end}})
        label = f"Week {4 - w}"
        monthly_data.append({"week": label, "count": count})

    # Source breakdown
    sources = await db.newsletter_subscribers.aggregate(
        [
            {"$match": {"status": "active"}},
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
    ).to_list(length=20)
    source_breakdown = [{"source": s["_id"] or "unknown", "count": s["count"]} for s in sources]

    # Recent subscribers (last 10)
    recent_cursor = (
        db.newsletter_subscribers.find({"status": "active"}, {"_id": 0, "email": 1, "subscribed_at": 1, "source": 1})
        .sort("subscribed_at", -1)
        .limit(10)
    )
    recent = await recent_cursor.to_list(length=10)

    # Growth rate (this week vs last week)
    this_week_start = (today_start - timedelta(days=7)).isoformat()
    last_week_start = (today_start - timedelta(days=14)).isoformat()
    this_week = await db.newsletter_subscribers.count_documents({"subscribed_at": {"$gte": this_week_start}})
    last_week = await db.newsletter_subscribers.count_documents(
        {"subscribed_at": {"$gte": last_week_start, "$lt": this_week_start}}
    )
    growth_pct = round(((this_week - last_week) / max(last_week, 1)) * 100, 1)

    return {
        "total_subscribers": total,
        "today_signups": today_count,
        "this_week_signups": this_week,
        "growth_rate_pct": growth_pct,
        "weekly_trend": weekly_data,
        "monthly_trend": monthly_data,
        "source_breakdown": source_breakdown,
        "recent_subscribers": recent,
    }
