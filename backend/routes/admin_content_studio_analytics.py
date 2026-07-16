"""Content Studio Analytics — Admin-only real-time analytics for AI content generation.

Aggregates generation data across all users:
  - Total generations, words produced, avg word count
  - Template popularity distribution
  - Tone usage breakdown
  - Category distribution
  - Daily generation volume (30-day trend)
  - Top users by generation count
  - Hourly heatmap (when content is generated)
"""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from routes.db import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/content-studio", tags=["Admin Content Studio Analytics"])


@router.get("/analytics")
async def content_studio_analytics(request: Request):
    """Full analytics payload for the executive content studio dashboard."""
    await require_admin(request)

    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    collection = db.content_studio_history

    # Total counts
    total_generations = await collection.count_documents({})
    last_7d_generations = await collection.count_documents({"created_at": {"$gte": seven_days_ago}})
    last_30d_generations = await collection.count_documents({"created_at": {"$gte": thirty_days_ago}})

    # Aggregation: template popularity
    template_pipeline = [
        {"$group": {"_id": "$template_id", "count": {"$sum": 1}, "template_name": {"$first": "$template_name"}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
    ]
    template_stats = await collection.aggregate(template_pipeline).to_list(15)
    template_distribution = [
        {"template": doc.get("template_name", doc["_id"]), "count": doc["count"]}
        for doc in template_stats
    ]

    # Aggregation: tone distribution
    tone_pipeline = [
        {"$group": {"_id": "$tone", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    tone_stats = await collection.aggregate(tone_pipeline).to_list(20)
    tone_distribution = [
        {"tone": doc["_id"] or "default", "count": doc["count"]}
        for doc in tone_stats if doc["_id"]
    ]

    # Aggregation: category distribution
    category_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    category_stats = await collection.aggregate(category_pipeline).to_list(10)
    category_distribution = [
        {"category": doc["_id"] or "unknown", "count": doc["count"]}
        for doc in category_stats if doc["_id"]
    ]

    # Aggregation: word count stats
    word_pipeline = [
        {"$group": {
            "_id": None,
            "total_words": {"$sum": "$word_count"},
            "avg_words": {"$avg": "$word_count"},
            "max_words": {"$max": "$word_count"},
            "min_words": {"$min": "$word_count"},
        }},
    ]
    word_stats_result = await collection.aggregate(word_pipeline).to_list(1)
    word_stats = word_stats_result[0] if word_stats_result else {"total_words": 0, "avg_words": 0, "max_words": 0, "min_words": 0}
    word_stats.pop("_id", None)
    word_stats["avg_words"] = round(word_stats.get("avg_words", 0) or 0)

    # Daily volume (last 30 days)
    daily_pipeline = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}}},
        {"$addFields": {"date_str": {"$substr": ["$created_at", 0, 10]}}},
        {"$group": {"_id": "$date_str", "count": {"$sum": 1}, "words": {"$sum": "$word_count"}}},
        {"$sort": {"_id": 1}},
    ]
    daily_raw = await collection.aggregate(daily_pipeline).to_list(31)
    daily_map = {d["_id"]: {"count": d["count"], "words": d.get("words", 0)} for d in daily_raw}

    daily_volume = []
    for i in range(30):
        day = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        entry = daily_map.get(day, {"count": 0, "words": 0})
        daily_volume.append({"date": day, "generations": entry["count"], "words": entry["words"]})

    # Hourly heatmap (all time)
    hourly_pipeline = [
        {"$addFields": {"hour_str": {"$substr": ["$created_at", 11, 2]}}},
        {"$group": {"_id": "$hour_str", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    hourly_raw = await collection.aggregate(hourly_pipeline).to_list(24)
    hourly_map = {d["_id"]: d["count"] for d in hourly_raw}
    hourly_heatmap = [{"hour": f"{h:02d}", "count": hourly_map.get(f"{h:02d}", 0)} for h in range(24)]

    # Top users
    user_pipeline = [
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}, "words": {"$sum": "$word_count"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    user_stats = await collection.aggregate(user_pipeline).to_list(10)

    top_users = []
    for u in user_stats:
        user_doc = await db.users.find_one({"user_id": u["_id"]}, {"_id": 0, "name": 1, "email": 1})
        top_users.append({
            "user_id": u["_id"],
            "name": user_doc.get("name", "Unknown") if user_doc else "Unknown",
            "email": user_doc.get("email", "") if user_doc else "",
            "generations": u["count"],
            "total_words": u.get("words", 0),
        })

    # 7-day trend (compare this week vs last week)
    fourteen_days_ago = (now - timedelta(days=14)).isoformat()
    prev_7d = await collection.count_documents({
        "created_at": {"$gte": fourteen_days_ago, "$lt": seven_days_ago}
    })
    trend_pct = round(((last_7d_generations - prev_7d) / max(prev_7d, 1)) * 100, 1)

    return {
        "summary": {
            "total_generations": total_generations,
            "last_7d_generations": last_7d_generations,
            "last_30d_generations": last_30d_generations,
            "trend_7d_pct": trend_pct,
            "word_stats": word_stats,
        },
        "template_distribution": template_distribution,
        "tone_distribution": tone_distribution,
        "category_distribution": category_distribution,
        "daily_volume": daily_volume,
        "hourly_heatmap": hourly_heatmap,
        "top_users": top_users,
        "generated_at": now.isoformat(),
    }
