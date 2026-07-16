"""Conversion modal analytics — track and analyze footer modal interactions."""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from routes.db import db
from routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/newsletter/modal", tags=["modal-analytics"])


class ModalEvent(BaseModel):
    event: str  # opened, signup_click, dismiss, backdrop_close
    feature: str  # e.g. "AI Coaching Tools"
    timestamp: str = ""


@router.post("/events")
async def track_modal_event(ev: ModalEvent):
    """Public endpoint — no auth required (used by non-registered visitors)."""
    valid_events = {"opened", "signup_click", "dismiss", "backdrop_close"}
    if ev.event not in valid_events:
        raise HTTPException(status_code=400, detail="Invalid event type")

    await db.modal_events.insert_one(
        {
            "event": ev.event,
            "feature": ev.feature,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"ok": True}


@router.get("/analytics")
async def get_modal_analytics(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    (now - timedelta(days=30)).isoformat()

    # Totals
    total_opens = await db.modal_events.count_documents({"event": "opened"})
    total_signups = await db.modal_events.count_documents({"event": "signup_click"})
    total_dismiss = await db.modal_events.count_documents({"event": "dismiss"})
    total_backdrop = await db.modal_events.count_documents({"event": "backdrop_close"})
    total_closes = total_dismiss + total_backdrop

    conversion_rate = round((total_signups / max(total_opens, 1)) * 100, 1)
    dismiss_rate = round((total_closes / max(total_opens, 1)) * 100, 1)

    # 7-day totals
    opens_7d = await db.modal_events.count_documents({"event": "opened", "created_at": {"$gte": seven_days_ago}})
    signups_7d = await db.modal_events.count_documents(
        {"event": "signup_click", "created_at": {"$gte": seven_days_ago}}
    )

    # Feature popularity (top features by opens)
    feature_pipeline = [
        {"$match": {"event": "opened"}},
        {"$group": {"_id": "$feature", "opens": {"$sum": 1}}},
        {"$sort": {"opens": -1}},
        {"$limit": 12},
    ]
    feature_agg = await db.modal_events.aggregate(feature_pipeline).to_list(length=12)

    # Per-feature conversion (opens vs signup_click)
    feature_stats = []
    for f in feature_agg:
        feat_name = f["_id"]
        feat_signups = await db.modal_events.count_documents({"event": "signup_click", "feature": feat_name})
        feat_conv = round((feat_signups / max(f["opens"], 1)) * 100, 1)
        feature_stats.append(
            {
                "feature": feat_name,
                "opens": f["opens"],
                "signups": feat_signups,
                "conversion_rate": feat_conv,
            }
        )

    # Daily trend (last 7 days)
    daily_trend = []
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(6, -1, -1):
        day_start = (today_start - timedelta(days=i)).isoformat()
        day_end = (today_start - timedelta(days=i - 1)).isoformat() if i > 0 else now.isoformat()
        day_opens = await db.modal_events.count_documents(
            {"event": "opened", "created_at": {"$gte": day_start, "$lt": day_end}}
        )
        day_signups = await db.modal_events.count_documents(
            {"event": "signup_click", "created_at": {"$gte": day_start, "$lt": day_end}}
        )
        day_label = (today_start - timedelta(days=i)).strftime("%a")
        daily_trend.append({"day": day_label, "opens": day_opens, "signups": day_signups})

    # Recent events (last 20)
    recent = await db.modal_events.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(length=20)

    # Funnel
    funnel = [
        {"stage": "Modal Opens", "count": total_opens, "color": "#3B82F6"},
        {"stage": "Sign Up Clicks", "count": total_signups, "color": "#10B981"},
        {"stage": "Dismissals", "count": total_closes, "color": "#6B7280"},
    ]

    return {
        "total_opens": total_opens,
        "total_signups": total_signups,
        "total_dismissals": total_closes,
        "conversion_rate": conversion_rate,
        "dismiss_rate": dismiss_rate,
        "opens_7d": opens_7d,
        "signups_7d": signups_7d,
        "feature_stats": feature_stats,
        "daily_trend": daily_trend,
        "recent_events": recent,
        "funnel": funnel,
    }
