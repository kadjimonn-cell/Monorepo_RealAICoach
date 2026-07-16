"""Admin subscription maintenance and analytics routes extracted from payments.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from .db import db, require_admin


router = APIRouter()


@router.post("/admin/subscriptions/run-maintenance")
async def admin_run_subscription_maintenance(request: Request):
    """Admin-only: Manually trigger subscription maintenance (expire + reminders + retry)."""
    await require_admin(request)

    from .subscription_enforcement import scheduled_subscription_maintenance

    await scheduled_subscription_maintenance()

    return {"success": True, "message": "Subscription maintenance completed"}


@router.get("/admin/subscriptions/expiry-overview")
async def admin_subscription_expiry_overview(request: Request):
    """Admin: View upcoming subscription expirations and reminder status."""
    await require_admin(request)

    now = datetime.now(timezone.utc)

    expiring_7d = await db.users.find(
        {
            "subscription_plan": {"$in": ["basic", "premium"]},
            "subscription_status": "active",
            "subscription_end_date": {"$gte": now, "$lte": now + timedelta(days=7)},
        },
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "name": 1,
            "subscription_plan": 1,
            "subscription_end_date": 1,
            "reminder_7d_sent": 1,
            "reminder_3d_sent": 1,
            "reminder_1d_sent": 1,
        },
    ).to_list(100)

    expired = await db.users.find(
        {
            "subscription_plan": {"$in": ["basic", "premium"]},
            "subscription_end_date": {"$lt": now},
            "subscription_status": {"$ne": "expired"},
        },
        {"_id": 0, "user_id": 1, "email": 1, "subscription_plan": 1, "subscription_end_date": 1},
    ).to_list(100)

    active_count = await db.users.count_documents(
        {
            "subscription_plan": {"$in": ["basic", "premium"]},
            "subscription_status": "active",
        }
    )

    recent_reminders = (
        await db.subscription_audit_log.find({"action": {"$regex": "expiry_reminder"}}, {"_id": 0})
        .sort("timestamp", -1)
        .to_list(20)
    )

    for user in expiring_7d:
        if hasattr(user.get("subscription_end_date"), "isoformat"):
            user["subscription_end_date"] = user["subscription_end_date"].isoformat()
    for user in expired:
        if hasattr(user.get("subscription_end_date"), "isoformat"):
            user["subscription_end_date"] = user["subscription_end_date"].isoformat()

    return {
        "active_subscriptions": active_count,
        "expiring_within_7_days": expiring_7d,
        "expired_not_downgraded": expired,
        "recent_reminders": recent_reminders,
    }


@router.get("/admin/subscriptions/analytics")
async def admin_subscription_analytics(request: Request):
    """Subscription analytics dashboard for admin."""
    await require_admin(request)

    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    plan_pipeline = [
        {"$match": {"subscription_plan": {"$in": ["basic", "premium"]}}},
        {"$group": {"_id": "$subscription_plan", "count": {"$sum": 1}}},
    ]
    plan_breakdown = await db.users.aggregate(plan_pipeline).to_list(10)

    total_basic = next((plan["count"] for plan in plan_breakdown if plan["_id"] == "basic"), 0)
    total_premium = next((plan["count"] for plan in plan_breakdown if plan["_id"] == "premium"), 0)
    total_free = await db.users.count_documents({"subscription_plan": "free"})
    total_users = await db.users.count_documents({})

    method_pipeline = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}, "payment_status": "completed"}},
        {"$group": {"_id": "$payment_method", "count": {"$sum": 1}, "volume": {"$sum": "$amount_usd"}}},
        {"$sort": {"count": -1}},
    ]
    method_stats = await db.payment_transactions.aggregate(method_pipeline).to_list(20)

    if not any(method.get("volume") for method in method_stats):
        method_pipeline = [
            {"$match": {"created_at": {"$gte": thirty_days_ago}, "payment_status": "completed"}},
            {
                "$group": {
                    "_id": "$payment_method",
                    "count": {"$sum": 1},
                    "volume": {"$sum": {"$ifNull": ["$amount_usd", "$amount"]}},
                }
            },
            {"$sort": {"count": -1}},
        ]
        method_stats = await db.payment_transactions.aggregate(method_pipeline).to_list(20)

    monthly_pipeline = [
        {"$match": {"status": "completed", "created_at": {"$exists": True}}},
        {"$addFields": {"month": {"$substr": [{"$toString": "$created_at"}, 0, 7]}}},
        {"$group": {"_id": "$month", "revenue": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    monthly_revenue = await db.payments.aggregate(monthly_pipeline).to_list(12)

    recent_payments = (
        await db.payment_transactions.find(
            {"payment_status": "completed"},
            {
                "_id": 0,
                "user_id": 1,
                "plan_id": 1,
                "amount_usd": 1,
                "amount": 1,
                "payment_method": 1,
                "gateway": 1,
                "currency": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .to_list(20)
    )

    churn_count = await db.subscription_audit_log.count_documents(
        {
            "action": {"$in": ["auto_downgrade", "payment_confirmed"]},
            "timestamp": {"$gte": now - timedelta(days=30)},
        }
    )
    cancelled_count = await db.users.count_documents({"subscription_status": "cancelled"})
    expired_count = await db.users.count_documents({"subscription_status": "expired"})

    total_rev_pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    total_rev = await db.payments.aggregate(total_rev_pipeline).to_list(1)

    return {
        "subscribers": {
            "total_users": total_users,
            "free": total_free,
            "basic": total_basic,
            "premium": total_premium,
            "total_paid": total_basic + total_premium,
            "conversion_rate": round((total_basic + total_premium) / max(total_users, 1) * 100, 1),
        },
        "revenue": {
            "total": round(total_rev[0]["total"], 2) if total_rev else 0,
            "total_payments": total_rev[0]["count"] if total_rev else 0,
            "monthly_trend": monthly_revenue,
        },
        "payment_methods": method_stats,
        "churn": {
            "cancelled": cancelled_count,
            "expired": expired_count,
            "recent_downgrades": churn_count,
        },
        "recent_payments": recent_payments,
    }