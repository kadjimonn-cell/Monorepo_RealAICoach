"""Admin AI Usage Analytics — Executive-level insights on AI usage, limits, and tier conversions.

Endpoints:
- GET /api/admin/ai-usage-analytics — Full analytics dashboard data
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import logging

from routes.db import db, get_current_user
from routes.payments_catalog import get_subscription_plan_from_gps, get_subscription_plans_from_gps
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

@router.get("/admin/ai-usage-analytics")
async def admin_ai_usage_analytics(request: Request):
    """Executive dashboard: AI usage, limit hits, tier conversions, feature popularity."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    now.strftime("%Y-%m-%d")
    today_start = now.replace(hour=0, minute=0, second=0).isoformat()
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    gps_plans = await get_subscription_plans_from_gps()

    # === 1. Overview KPIs ===
    total_ai_requests_today = await db.usage_analytics.count_documents({"timestamp": {"$gte": today_start}})
    total_ai_requests_7d = await db.usage_analytics.count_documents({"timestamp": {"$gte": seven_days_ago}})
    total_ai_requests_30d = await db.usage_analytics.count_documents({"timestamp": {"$gte": thirty_days_ago}})
    total_unique_users_today = len(await db.usage_analytics.distinct("user_id", {"timestamp": {"$gte": today_start}}))
    total_unique_users_7d = len(await db.usage_analytics.distinct("user_id", {"timestamp": {"$gte": seven_days_ago}}))

    # === 2. Users hitting limits (top limit-hitters) ===
    # Find users whose daily usage >= their tier limit
    limit_hit_users = []
    pipeline_heavy = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}}},
        {"$addFields": {"day": {"$substr": ["$timestamp", 0, 10]}}},
        {"$group": {"_id": {"user_id": "$user_id", "day": "$day"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 100},
    ]
    daily_counts = []
    async for doc in db.usage_analytics.aggregate(pipeline_heavy):
        daily_counts.append(doc)

    # For each user, check if they hit their limit
    user_limit_hits = {}
    checked_users = {}
    for dc in daily_counts:
        uid = dc["_id"]["user_id"]
        count = dc["count"]
        if uid not in checked_users:
            user_doc = await db.users.find_one(
                {"user_id": uid}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1}
            )
            checked_users[uid] = user_doc or {}
        u = checked_users[uid]
        plan = _effective_plan_from_user_doc(u)
        plan_doc = await get_subscription_plan_from_gps(plan, default_plan_id="free") or {}
        limit = 9999 if plan in ("admin", "enterprise") else plan_doc.get("daily_conversation_limit", 3)
        if count >= limit and limit < 9999:
            if uid not in user_limit_hits:
                user_limit_hits[uid] = {
                    "user_id": uid,
                    "email": u.get("email", ""),
                    "name": u.get("name", ""),
                    "plan": plan,
                    "hits": 0,
                    "days": [],
                }
            user_limit_hits[uid]["hits"] += 1
            user_limit_hits[uid]["days"].append({"date": dc["_id"]["day"], "usage": count, "limit": limit})

    limit_hit_users = sorted(user_limit_hits.values(), key=lambda x: x["hits"], reverse=True)[:20]
    total_limit_hits_7d = sum(u["hits"] for u in limit_hit_users)

    # === 3. Tier distribution ===
    tier_dist = {plan: 0 for plan in gps_plans.keys()}
    tier_dist.setdefault("free", 0)
    effective_user_ids_by_plan: dict[str, list[str]] = {plan: [] for plan in gps_plans.keys()}
    effective_user_ids_by_plan.setdefault("free", [])
    users_for_tiers = await db.users.find(
        {},
        {"_id": 0, "user_id": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
    ).to_list(5000)
    for row in users_for_tiers:
        effective_plan = _effective_plan_from_user_doc(row)
        tier_dist.setdefault(effective_plan, 0)
        tier_dist[effective_plan] += 1
        user_id = row.get("user_id")
        if user_id:
            effective_user_ids_by_plan.setdefault(effective_plan, []).append(user_id)

    # === 4. Tier conversions (from subscription_audit_log) ===
    conversions = []
    conv_cursor = (
        db.subscription_audit_log.find(
            {"action": {"$in": ["upgrade", "downgrade", "auto_downgrade", "plan_change"]}}, {"_id": 0}
        )
        .sort("timestamp", -1)
        .limit(50)
    )
    async for entry in conv_cursor:
        if "timestamp" in entry and hasattr(entry["timestamp"], "isoformat"):
            entry["timestamp"] = entry["timestamp"].isoformat()
        conversions.append(entry)

    # Also check payments for recent upgrades
    upgrade_pipeline = [
        {"$match": {"status": "completed", "created_at": {"$gte": thirty_days_ago}}},
        {"$group": {"_id": "$plan_id", "count": {"$sum": 1}, "revenue": {"$sum": "$amount"}}},
        {"$sort": {"count": -1}},
    ]
    upgrade_stats = []
    try:
        async for doc in db.payments.aggregate(upgrade_pipeline):
            upgrade_stats.append({"plan": doc["_id"], "conversions": doc["count"], "revenue": doc.get("revenue", 0)})
    except Exception:
        pass

    # === 5. Daily usage trend (last 14 days) ===
    daily_trend = []
    for i in range(13, -1, -1):
        d = now - timedelta(days=i)
        day_start = d.replace(hour=0, minute=0, second=0).isoformat()
        day_end = (d + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()
        count = await db.usage_analytics.count_documents({"timestamp": {"$gte": day_start, "$lt": day_end}})
        unique = len(await db.usage_analytics.distinct("user_id", {"timestamp": {"$gte": day_start, "$lt": day_end}}))
        daily_trend.append({"date": d.strftime("%Y-%m-%d"), "requests": count, "unique_users": unique})

    # === 6. Feature popularity (top features by usage) ===
    feature_pipeline = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}}},
        {"$group": {"_id": "$feature_id", "count": {"$sum": 1}, "users": {"$addToSet": "$user_id"}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
    ]
    top_features = []
    async for doc in db.usage_analytics.aggregate(feature_pipeline):
        top_features.append(
            {
                "feature": doc["_id"] or "unknown",
                "requests": doc["count"],
                "unique_users": len(doc.get("users", [])),
            }
        )

    # === 7. Usage by tier (7 day aggregate) ===
    tier_usage = {}
    for plan in gps_plans.keys():
        user_ids = effective_user_ids_by_plan.get(plan, [])
        if user_ids:
            count = await db.usage_analytics.count_documents(
                {"user_id": {"$in": user_ids}, "timestamp": {"$gte": seven_days_ago}}
            )
            tier_usage[plan] = {
                "total_requests": count,
                "user_count": len(user_ids),
                "avg_per_user": round(count / max(len(user_ids), 1), 1),
            }
        else:
            tier_usage[plan] = {"total_requests": 0, "user_count": 0, "avg_per_user": 0}

    # === 8. Conversion funnel ===
    users_hit_limit = len(user_limit_hits)
    users_upgraded_after_limit = 0
    for uid, info in user_limit_hits.items():
        upgrade_found = await db.subscription_audit_log.find_one(
            {"user_id": uid, "action": {"$in": ["upgrade", "plan_change"]}}
        )
        if upgrade_found:
            users_upgraded_after_limit += 1

    conversion_rate = round((users_upgraded_after_limit / max(users_hit_limit, 1)) * 100, 1)

    return {
        "overview": {
            "total_requests_today": total_ai_requests_today,
            "total_requests_7d": total_ai_requests_7d,
            "total_requests_30d": total_ai_requests_30d,
            "unique_users_today": total_unique_users_today,
            "unique_users_7d": total_unique_users_7d,
            "limit_hits_7d": total_limit_hits_7d,
        },
        "tier_distribution": tier_dist,
        "tier_usage": tier_usage,
        "daily_trend": daily_trend,
        "top_features": top_features,
        "limit_hit_users": limit_hit_users,
        "conversions": conversions[:20],
        "upgrade_stats": upgrade_stats,
        "conversion_funnel": {
            "users_hit_limit": users_hit_limit,
            "users_upgraded": users_upgraded_after_limit,
            "conversion_rate": conversion_rate,
        },
    }
