"""AI Feature Analytics — Deep analytics across all AI features with AI-generated insights.

Aggregates data from each AI feature's collection + usage_analytics to provide
executive-level intelligence about feature adoption, engagement, and value.

GET /api/admin/ai-feature-analytics — Full analytics with AI insights
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import logging

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate
from utils.access_control_engine import compute_effective_plan

logger = logging.getLogger(__name__)
router = APIRouter()


def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
    row = user_doc or {}
    return compute_effective_plan(
        {
            "subscription_plan": row.get("subscription_plan", "free"),
            "subscription_status": row.get("subscription_status", "active"),
            "subscription_end_date": row.get("subscription_end_date"),
            "subscription_permanent": row.get("subscription_permanent", False),
            "payment_verified": row.get("payment_verified", False),
            "pending_subscription_transition": row.get("pending_subscription_transition"),
            "is_admin": row.get("is_admin", False),
            "full_access": row.get("full_access", False),
        }
    )

AI_FEATURES = {
    "ai-life-coach": {
        "name": "AI Life Coach",
        "icon": "chatbubble-ellipses",
        "color": "#10B981",
        "collection": "ai_coach_conversations",
    },
    "ai-coaching-team": {
        "name": "AI Coaching Team",
        "icon": "people",
        "color": "#8B5CF6",
        "collection": "coaching_team_sessions",
    },
    "ai-learning-hub": {"name": "AI Learning Hub", "icon": "school", "color": "#3B82F6", "collection": "learn_lessons"},
    "ai-marketplace": {"name": "AI Marketplace", "icon": "storefront", "color": "#F59E0B", "collection": None},
    "ai-goal-tracker": {"name": "AI Goal Tracker", "icon": "flag", "color": "#EC4899", "collection": "ai_goals"},
    "ai-doc-analyzer": {
        "name": "AI Doc Analyzer",
        "icon": "document-text",
        "color": "#06B6D4",
        "collection": "doc_analyses",
    },
    "daily-briefing": {"name": "Daily Briefing", "icon": "sunny", "color": "#F97316", "collection": "ai_briefings"},
}


@router.get("/admin/ai-feature-analytics")
async def ai_feature_analytics(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin access required")

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    today_start = now.replace(hour=0, minute=0, second=0).isoformat()

    # === 1. Per-Feature Usage Stats ===
    feature_stats = []
    for fid, finfo in AI_FEATURES.items():
        # Usage from usage_analytics collection
        usage_7d = await db.usage_analytics.count_documents({"feature_id": fid, "timestamp": {"$gte": seven_days_ago}})
        usage_30d = await db.usage_analytics.count_documents(
            {"feature_id": fid, "timestamp": {"$gte": thirty_days_ago}}
        )
        usage_today = await db.usage_analytics.count_documents({"feature_id": fid, "timestamp": {"$gte": today_start}})
        unique_users_7d = len(
            await db.usage_analytics.distinct("user_id", {"feature_id": fid, "timestamp": {"$gte": seven_days_ago}})
        )
        unique_users_30d = len(
            await db.usage_analytics.distinct("user_id", {"feature_id": fid, "timestamp": {"$gte": thirty_days_ago}})
        )

        # Feature-specific data from its own collection
        items_total = 0
        items_7d = 0
        completion_rate = 0
        if finfo["collection"]:
            col = db[finfo["collection"]]
            items_total = await col.count_documents({})
            items_7d = await col.count_documents({"created_at": {"$gte": seven_days_ago}})

            # Feature-specific completion metrics
            if fid == "ai-learning-hub":
                completed = await col.count_documents({"completed": True})
                completion_rate = round((completed / max(items_total, 1)) * 100, 1)
            elif fid == "ai-goal-tracker":
                completed = await col.count_documents({"status": "completed"})
                completion_rate = round((completed / max(items_total, 1)) * 100, 1)

        # Daily trend for this feature (last 7 days)
        daily = []
        for i in range(6, -1, -1):
            d = now - timedelta(days=i)
            ds = d.replace(hour=0, minute=0, second=0).isoformat()
            de = (d + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()
            count = await db.usage_analytics.count_documents({"feature_id": fid, "timestamp": {"$gte": ds, "$lt": de}})
            daily.append({"date": d.strftime("%m/%d"), "count": count})

        # Engagement score (weighted formula)
        engagement = min(100, round((usage_7d * 2) + (unique_users_7d * 10) + (items_7d * 3) + (completion_rate * 0.5)))

        feature_stats.append(
            {
                "feature_id": fid,
                "name": finfo["name"],
                "icon": finfo["icon"],
                "color": finfo["color"],
                "usage_today": usage_today,
                "usage_7d": usage_7d,
                "usage_30d": usage_30d,
                "unique_users_7d": unique_users_7d,
                "unique_users_30d": unique_users_30d,
                "items_total": items_total,
                "items_7d": items_7d,
                "completion_rate": completion_rate,
                "engagement_score": engagement,
                "daily_trend": daily,
            }
        )

    # Sort by engagement score descending
    feature_stats.sort(key=lambda f: f["engagement_score"], reverse=True)

    # === 2. Aggregate KPIs ===
    total_usage_7d = sum(f["usage_7d"] for f in feature_stats)
    total_usage_30d = sum(f["usage_30d"] for f in feature_stats)
    total_items = sum(f["items_total"] for f in feature_stats)
    all_unique_users_7d = len(await db.usage_analytics.distinct("user_id", {"timestamp": {"$gte": seven_days_ago}}))
    total_users = await db.users.count_documents({})
    adoption_rate = round((all_unique_users_7d / max(total_users, 1)) * 100, 1)

    # === 3. Top Users (power users across all AI features) ===
    power_user_pipeline = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}}},
        {"$group": {"_id": "$user_id", "total_usage": {"$sum": 1}, "features_used": {"$addToSet": "$feature_id"}}},
        {"$sort": {"total_usage": -1}},
        {"$limit": 10},
    ]
    power_users = []
    async for doc in db.usage_analytics.aggregate(power_user_pipeline):
        uid = doc["_id"]
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1, "name": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1})
        power_users.append(
            {
                "user_id": uid,
                "email": (u or {}).get("email", ""),
                "name": (u or {}).get("name", "User"),
                "plan": _effective_plan_from_user_doc(u),
                "total_usage": doc["total_usage"],
                "features_count": len(doc.get("features_used", [])),
            }
        )

    # === 4. Feature Correlation (which features are used together) ===
    cross_usage_pipeline = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}}},
        {"$group": {"_id": "$user_id", "features": {"$addToSet": "$feature_id"}}},
        {"$match": {"features.1": {"$exists": True}}},  # users with 2+ features
    ]
    multi_feature_users = 0
    feature_pairs = {}
    async for doc in db.usage_analytics.aggregate(cross_usage_pipeline):
        multi_feature_users += 1
        feats = sorted(doc["features"])
        for i in range(len(feats)):
            for j in range(i + 1, len(feats)):
                pair = f"{feats[i]} + {feats[j]}"
                feature_pairs[pair] = feature_pairs.get(pair, 0) + 1

    top_pairs = sorted(feature_pairs.items(), key=lambda x: x[1], reverse=True)[:5]
    feature_correlations = [{"pair": p[0], "users": p[1]} for p in top_pairs]

    # === 5. AI-Generated Insights ===
    stats_summary = "\n".join(
        [
            f"- {f['name']}: {f['usage_7d']} uses (7d), {f['unique_users_7d']} users, {f['items_total']} items, engagement={f['engagement_score']}/100"
            for f in feature_stats
        ]
    )
    try:
        ai_insights = await ai_generate(
            "You are a product analytics AI expert. Analyze feature usage data and provide 4-5 actionable insights. "
            "Focus on: which features drive engagement, what's underutilized, growth opportunities, and retention strategies. "
            "Be specific with numbers. Use bullet points. Keep each insight to 1-2 sentences.",
            f"Platform has {total_users} total users, {all_unique_users_7d} active in 7 days ({adoption_rate}% adoption).\n"
            f"Feature stats (last 7 days):\n{stats_summary}\n"
            f"Multi-feature users: {multi_feature_users}\n"
            f"Top feature combos: {feature_correlations[:3]}\n"
            f"Power users: {len(power_users)} identified\n"
            f"Provide actionable insights:",
            "feature-analytics",
        )
    except Exception as e:
        logger.error(f"AI insights generation error: {e}")
        ai_insights = (
            f"- Platform adoption rate is {adoption_rate}% with {all_unique_users_7d} active users.\n"
            f"- Top feature by engagement: {feature_stats[0]['name'] if feature_stats else 'N/A'}.\n"
            f"- {multi_feature_users} users use multiple AI features, indicating strong cross-feature engagement.\n"
            f"- Consider promoting underutilized features through in-app recommendations."
        )

    return {
        "overview": {
            "total_usage_7d": total_usage_7d,
            "total_usage_30d": total_usage_30d,
            "total_items_created": total_items,
            "active_ai_users_7d": all_unique_users_7d,
            "total_users": total_users,
            "adoption_rate": adoption_rate,
            "multi_feature_users": multi_feature_users,
            "features_count": len(AI_FEATURES),
        },
        "feature_stats": feature_stats,
        "power_users": power_users,
        "feature_correlations": feature_correlations,
        "ai_insights": ai_insights,
    }
