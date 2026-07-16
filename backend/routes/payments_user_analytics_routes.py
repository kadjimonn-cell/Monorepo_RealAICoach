"""User-facing payment analytics routes extracted from payments.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException, Request

from .db import db
from .payments_catalog import get_plan_name, get_subscription_plan_from_gps
from utils.access_control_engine import compute_effective_plan


router = APIRouter()


async def _missing_user_resolver(_request: Request):
    raise HTTPException(status_code=503, detail="Payment analytics routes are not configured")


_get_user_from_request: Callable[[Request], Awaitable[object | None]] = _missing_user_resolver


def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
    row = user_doc or {}
    return compute_effective_plan(
        {
            "subscription_plan": row.get("subscription_plan", "free"),
            "subscription_status": row.get("subscription_status", "active"),
            "subscription_end_date": row.get("subscription_expires_at") or row.get("subscription_end_date"),
            "subscription_permanent": row.get("subscription_permanent", False),
            "payment_verified": row.get("payment_verified", False),
            "pending_subscription_transition": row.get("pending_subscription_transition"),
            "is_admin": row.get("is_admin", False),
            "full_access": row.get("full_access", False),
        }
    )


def configure_payment_user_analytics_routes(
    *,
    get_user_from_request: Callable[[Request], Awaitable[object | None]],
) -> None:
    global _get_user_from_request
    _get_user_from_request = get_user_from_request


async def require_auth_payment(request: Request):
    user = await _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/payments/analytics/my-dashboard")
async def my_payment_analytics(request: Request):
    """User-facing payment analytics: spending history, subscription value, and renewal info."""
    user = await require_auth_payment(request)

    now = datetime.now(timezone.utc)
    payments = (
        await db.payments.find({"user_id": user.user_id, "status": "completed"}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(50)
    )

    total_spent = sum(payment.get("amount", 0) for payment in payments)
    total_payments = len(payments)

    six_months_ago = now - timedelta(days=180)
    monthly_pipeline = [
        {"$match": {"user_id": user.user_id, "status": "completed"}},
        {
            "$addFields": {
                "parsed_date": {
                    "$cond": {
                        "if": {"$eq": [{"$type": "$created_at"}, "date"]},
                        "then": "$created_at",
                        "else": {
                            "$dateFromString": {"dateString": {"$toString": "$created_at"}, "onError": six_months_ago}
                        },
                    }
                }
            }
        },
        {"$match": {"parsed_date": {"$gte": six_months_ago}}},
        {"$addFields": {"month": {"$dateToString": {"format": "%Y-%m", "date": "$parsed_date"}}}},
        {"$group": {"_id": "$month", "amount": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    monthly_spending = await db.payments.aggregate(monthly_pipeline).to_list(12)

    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1, "subscription_expires_at": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1, "billing_period": 1},
    )
    plan_id = _effective_plan_from_user_doc(user_doc)
    plan = await get_subscription_plan_from_gps(plan_id, default_plan_id="free") or {}

    expires_at = user_doc.get("subscription_expires_at") if user_doc else None
    days_remaining: Optional[int] = None
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(str(expires_at))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            days_remaining = max(0, (exp_dt - now).days)
        except Exception:
            days_remaining = None

    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    collection_names = await db.list_collection_names()
    conversations_30d = (
        await db.conversations.count_documents({"user_id": user.user_id, "created_at": {"$gte": thirty_days_ago}})
        if "conversations" in collection_names
        else 0
    )

    daily_limit = plan.get("daily_conversation_limit", 3)
    features_unlocked = len([feature for feature in plan.get("features", []) if not feature.startswith("no_")])
    export_formats = plan.get("export_formats", [])

    return {
        "spending": {
            "total_spent": round(total_spent, 2),
            "total_payments": total_payments,
            "monthly_trend": monthly_spending,
            "recent_payments": [
                {
                    "amount": payment.get("amount", 0),
                    "description": payment.get("description")
                    or f"{await get_plan_name(payment.get('plan_id', 'free'))} Plan - {payment.get('payment_method', 'card').title()}",
                    "method": payment.get("payment_method", ""),
                    "date": payment.get("created_at", ""),
                    "status": payment.get("status", ""),
                    "plan_id": payment.get("plan_id", ""),
                }
                for payment in payments[:10]
            ],
        },
        "subscription": {
            "plan_id": plan_id,
            "plan_name": plan.get("name", "Free"),
            "status": user_doc.get("subscription_status", "active") if user_doc else "active",
            "billing_period": user_doc.get("billing_period") if user_doc else None,
            "days_remaining": days_remaining,
            "expires_at": str(expires_at) if expires_at else None,
        },
        "value": {
            "daily_conversation_limit": daily_limit,
            "conversations_used_30d": conversations_30d,
            "features_unlocked": features_unlocked,
            "export_formats": export_formats,
            "badge": plan.get("badge", {}),
        },
    }