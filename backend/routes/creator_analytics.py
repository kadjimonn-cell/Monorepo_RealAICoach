"""Creator Analytics AI — Optimal times, content recs, audience growth, revenue optimization."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
import logging
import json

from .db import db, require_auth
from utils.llm_helper import generate_verified_json

router = APIRouter(prefix="/live/creator-ai")
logger = logging.getLogger(__name__)


@router.get("/insights")
async def creator_insights(request: Request):
    """AI-powered comprehensive creator analytics."""
    user = await require_auth(request)

    # Gather data
    streams = (
        await db.live_streams.find(
            {"streamer_id": user.user_id},
            {
                "_id": 0,
                "stream_id": 1,
                "title": 1,
                "category": 1,
                "viewer_count": 1,
                "peak_viewers": 1,
                "total_tips": 1,
                "total_messages": 1,
                "duration_minutes": 1,
                "status": 1,
                "started_at": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .to_list(50)
    )

    tips = await db.live_tips.aggregate(
        [
            {"$match": {"streamer_id": user.user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        ]
    ).to_list(1)

    subs = await db.live_subscriptions.find(
        {"streamer_id": user.user_id, "status": "active"}, {"_id": 0, "tier_id": 1}
    ).to_list(100)

    purchases = await db.live_purchases.aggregate(
        [
            {"$match": {"streamer_id": user.user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$net_to_streamer"}, "count": {"$sum": 1}}},
        ]
    ).to_list(1)

    # Analyze streaming times
    stream_hours = {}
    stream_days = {}
    for s in streams:
        if s.get("started_at"):
            try:
                dt = datetime.fromisoformat(s["started_at"].replace("Z", "+00:00"))
                h = dt.hour
                d = dt.strftime("%A")
                stream_hours[h] = stream_hours.get(h, 0) + s.get("peak_viewers", 0)
                stream_days[d] = stream_days.get(d, 0) + s.get("peak_viewers", 0)
            except (ValueError, TypeError):
                pass

    # Category performance
    cat_perf = {}
    for s in streams:
        cat = s.get("category", "other")
        if cat not in cat_perf:
            cat_perf[cat] = {"streams": 0, "total_viewers": 0, "total_tips": 0}
        cat_perf[cat]["streams"] += 1
        cat_perf[cat]["total_viewers"] += s.get("peak_viewers", 0)
        cat_perf[cat]["total_tips"] += s.get("total_tips", 0)

    context = {
        "total_streams": len(streams),
        "total_tips": round(tips[0]["total"], 2) if tips else 0,
        "total_subscribers": len(subs),
        "tier_breakdown": {},
        "total_purchase_revenue": round(purchases[0]["total"], 2) if purchases else 0,
        "avg_viewers": round(sum(s.get("peak_viewers", 0) for s in streams) / max(len(streams), 1), 1),
        "avg_duration": round(sum(s.get("duration_minutes", 0) for s in streams) / max(len(streams), 1), 1),
        "top_hours_by_viewers": dict(sorted(stream_hours.items(), key=lambda x: x[1], reverse=True)[:5]),
        "top_days_by_viewers": dict(sorted(stream_days.items(), key=lambda x: x[1], reverse=True)[:3]),
        "category_performance": cat_perf,
    }

    for s in subs:
        t = s.get("tier_id", "bronze")
        context["tier_breakdown"][t] = context["tier_breakdown"].get(t, 0) + 1

    try:
        ai_insights = await generate_verified_json(
            prompt=f"Analyze this creator's streaming data and provide actionable insights. Return ONLY JSON:\n"
            f'{{"optimal_times": [<top 3 best hours to stream, e.g. "7 PM", "9 PM">], '
            f'"optimal_days": [<top 2 best days>], '
            f'"content_recommendations": [<3-4 content/category suggestions>], '
            f'"audience_growth_prediction": {{"next_month": "<growing|stable|declining>", "predicted_subscriber_change": <number>, "confidence": "<high|medium|low>"}}, '
            f'"revenue_optimization": [<3-4 specific revenue tips>], '
            f'"engagement_score": <0-100>, '
            f'"key_metrics_summary": "<2-3 sentence performance summary>"}}\n\n'
            f"Creator data: {json.dumps(context)}",
            system_message="You are a streaming analytics AI. Give specific, actionable advice. Be encouraging but data-driven.",
            session_id=f"creator-ai-{user.user_id[:6]}",
        )
    except Exception as e:
        logger.error(f"Creator AI error: {e}")
        best_hour = max(stream_hours, key=stream_hours.get) if stream_hours else 19
        ai_insights = {
            "optimal_times": [f"{best_hour}:00"],
            "optimal_days": list(stream_days.keys())[:2] if stream_days else ["Saturday"],
            "content_recommendations": ["Try Q&A sessions", "Cover trending topics"],
            "audience_growth_prediction": {
                "next_month": "stable",
                "predicted_subscriber_change": 0,
                "confidence": "low",
            },
            "revenue_optimization": ["Enable paid streams", "Engage chat more"],
            "engagement_score": 50,
            "key_metrics_summary": f"You've streamed {len(streams)} times with an average of {context['avg_viewers']} peak viewers.",
        }

    return {
        "raw_data": context,
        "ai_insights": ai_insights,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/audience")
async def audience_analytics(request: Request):
    """Detailed audience analytics for a creator."""
    user = await require_auth(request)

    # Viewer history across all streams
    # Get all stream IDs
    stream_ids = [
        s["stream_id"]
        for s in await db.live_streams.find({"streamer_id": user.user_id}, {"_id": 0, "stream_id": 1}).to_list(100)
    ]

    unique_viewers = set()
    if stream_ids:
        viewers = await db.live_viewers.find({"stream_id": {"$in": stream_ids}}, {"_id": 0, "user_id": 1}).to_list(1000)
        unique_viewers = {v["user_id"] for v in viewers}

    # Top tippers
    top_tippers = await db.live_tips.aggregate(
        [
            {"$match": {"streamer_id": user.user_id}},
            {
                "$group": {
                    "_id": "$tipper_id",
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1},
                    "handle": {"$first": "$tipper_handle"},
                }
            },
            {"$sort": {"total": -1}},
            {"$limit": 10},
        ]
    ).to_list(10)

    return {
        "unique_viewers": len(unique_viewers),
        "total_streams": len(stream_ids),
        "top_tippers": [
            {"user_id": t["_id"], "handle": t["handle"], "total": round(t["total"], 2), "count": t["count"]}
            for t in top_tippers
        ],
    }


@router.get("/revenue-report")
async def revenue_report(request: Request, days: int = 30):
    """Detailed revenue report for a creator."""
    user = await require_auth(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Daily revenue
    daily_tips = {}
    tips = await db.live_tips.find(
        {"streamer_id": user.user_id, "created_at": {"$gte": cutoff}}, {"_id": 0, "amount": 1, "created_at": 1}
    ).to_list(500)
    for t in tips:
        day = t["created_at"][:10]
        daily_tips[day] = daily_tips.get(day, 0) + t["amount"]

    daily_purchases = {}
    purch = await db.live_purchases.find(
        {"streamer_id": user.user_id, "created_at": {"$gte": cutoff}}, {"_id": 0, "net_to_streamer": 1, "created_at": 1}
    ).to_list(500)
    for p in purch:
        day = p["created_at"][:10]
        daily_purchases[day] = daily_purchases.get(day, 0) + p["net_to_streamer"]

    # Combine daily
    all_days = sorted(set(list(daily_tips.keys()) + list(daily_purchases.keys())))
    daily_revenue = [
        {
            "date": d,
            "tips": round(daily_tips.get(d, 0), 2),
            "purchases": round(daily_purchases.get(d, 0), 2),
            "total": round(daily_tips.get(d, 0) + daily_purchases.get(d, 0), 2),
        }
        for d in all_days
    ]

    total = sum(d["total"] for d in daily_revenue)
    avg_daily = round(total / max(days, 1), 2)

    return {
        "period_days": days,
        "daily_revenue": daily_revenue,
        "total_revenue": round(total, 2),
        "avg_daily_revenue": avg_daily,
        "projected_monthly": round(avg_daily * 30, 2),
    }
