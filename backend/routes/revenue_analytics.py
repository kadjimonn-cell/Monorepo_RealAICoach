"""Revenue Analytics & Subscription Management.

Advanced metrics: MRR, ARR, churn rate, LTV, ARPU, cohort analysis.
Subscription tiers: Free, Pro, Enterprise with upgrade/downgrade flows.
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import uuid
import logging
from shared.pricing_policy import get_plan_amount

from .db import db, require_auth

router = APIRouter(prefix="/revenue")
logger = logging.getLogger("routes.revenue")

PLANS = {
    "free": {
        "name": "Free",
        "price": 0,
        "features": ["basic_coaching", "3_scenarios", "community"],
        "daily_limit": 3,
        "color": "#6B7280",
    },
    "basic": {
        "name": "Basic",
        "price": 5.99,
        "features": ["unlimited_coaching", "all_scenarios", "ai_analytics", "priority_support"],
        "daily_limit": 50,
        "color": "#3B82F6",
    },
    "premium": {
        "name": "Premium",
        "price": 15.99,
        "features": ["everything_basic", "mini_apps", "api_access", "sso", "dedicated_support"],
        "daily_limit": -1,
        "color": "#8B5CF6",
    },
}


async def _require_admin(request: Request):
    user = await require_auth(request)
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/metrics")
async def get_revenue_metrics(request: Request, period: str = "30d"):
    """Get comprehensive revenue metrics: MRR, ARR, churn, LTV, ARPU."""
    await _require_admin(request)
    now = datetime.now(timezone.utc)

    days = int(period.replace("d", "")) if period.endswith("d") else 30
    since = (now - timedelta(days=days)).isoformat()
    prev_since = (now - timedelta(days=days * 2)).isoformat()

    # Active subscriptions from users collection
    active = await db.users.count_documents({"subscription_status": "active", "subscription_plan": {"$ne": "free"}})
    total = await db.users.count_documents({"subscription_plan": {"$ne": "free"}})
    canceled = await db.users.count_documents({"subscription_status": "cancelled"})

    # New subs in period
    new_subs = await db.users.count_documents({
        "subscription_status": "active", "subscription_plan": {"$ne": "free"},
        "created_at": {"$gte": since}
    })
    prev_new = await db.users.count_documents({
        "subscription_status": "active", "subscription_plan": {"$ne": "free"},
        "created_at": {"$gte": prev_since, "$lt": since}
    })

    # Cancellations in period
    churned = await db.users.count_documents({"subscription_status": "cancelled", "updated_at": {"$gte": since}})

    # Revenue from plan counts
    plan_counts = {}
    for plan in PLANS:
        if plan == "free":
            continue
        count = await db.users.count_documents({
            "subscription_plan": plan, "subscription_status": "active"
        })
        if count > 0:
            plan_counts[plan] = count

    mrr = sum(PLANS.get(plan, {}).get("price", 0) * count for plan, count in plan_counts.items())
    arr = mrr * 12

    # Churn rate
    start_active = active + churned - new_subs
    churn_rate = round((churned / max(1, start_active)) * 100, 1) if start_active > 0 else 0

    # ARPU
    arpu = round(mrr / max(1, active), 2)

    # LTV
    monthly_churn = churn_rate / 100 if churn_rate > 0 else 0.05
    ltv = round(arpu / max(0.01, monthly_churn), 2)

    # Growth rate
    growth = round(((new_subs - prev_new) / max(1, prev_new)) * 100, 1) if prev_new > 0 else 0

    return {
        "mrr": mrr,
        "arr": arr,
        "active_subscribers": active,
        "total_subscribers": total,
        "canceled_subscribers": canceled,
        "new_subscribers": new_subs,
        "churned": churned,
        "churn_rate": churn_rate,
        "arpu": arpu,
        "ltv": ltv,
        "growth_rate": growth,
        "plan_breakdown": {
            plan: {"count": plan_counts.get(plan, 0), "revenue": PLANS[plan]["price"] * plan_counts.get(plan, 0)}
            for plan in PLANS
        },
        "period": period,
        "generated_at": now.isoformat(),
    }


@router.get("/trends")
async def get_revenue_trends(request: Request, months: int = 6):
    """Get monthly revenue trends for charting."""
    await _require_admin(request)
    now = datetime.now(timezone.utc)
    trends = []

    for i in range(months - 1, -1, -1):
        # Proper month arithmetic (avoid timedelta imprecision)
        target_month = now.month - i
        target_year = now.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        month_start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
        next_m = target_month + 1
        next_y = target_year
        if next_m > 12:
            next_m = 1
            next_y += 1
        month_end = datetime(next_y, next_m, 1, tzinfo=timezone.utc)

        # Use both ISO string and datetime for mixed-type created_at fields
        ms_str = month_start.isoformat()
        me_str = month_end.isoformat()

        new = await db.users.count_documents({
            "subscription_status": "active", "subscription_plan": {"$ne": "free"},
            "$or": [
                {"created_at": {"$gte": month_start, "$lt": month_end}},
                {"created_at": {"$gte": ms_str, "$lt": me_str}},
            ]
        })
        lost = await db.users.count_documents({
            "subscription_status": "cancelled",
            "$or": [
                {"updated_at": {"$gte": month_start, "$lt": month_end}},
                {"updated_at": {"$gte": ms_str, "$lt": me_str}},
            ]
        })

        basic_count = await db.users.count_documents({
            "subscription_plan": "basic", "subscription_status": "active",
            "$or": [{"created_at": {"$lt": month_end}}, {"created_at": {"$lt": me_str}}]
        })
        premium_count = await db.users.count_documents({
            "subscription_plan": "premium", "subscription_status": "active",
            "$or": [{"created_at": {"$lt": month_end}}, {"created_at": {"$lt": me_str}}]
        })
        active_at_end = basic_count + premium_count
        month_mrr = round(basic_count * PLANS["basic"]["price"] + premium_count * PLANS["premium"]["price"], 2)

        trends.append(
            {
                "month": month_start.strftime("%Y-%m"),
                "label": month_start.strftime("%b %Y"),
                "mrr": month_mrr,
                "new_subscribers": new,
                "churned": lost,
                "active": active_at_end,
                "net_growth": new - lost,
            }
        )

    return {"trends": trends, "months": months}


@router.get("/plans")
async def get_plans(request: Request):
    """Get available subscription plans."""
    await require_auth(request)
    plans = []
    for pid, plan in PLANS.items():
        plans.append(
            {
                "id": pid,
                **plan,
                "popular": pid == "pro",
            }
        )
    return {"plans": plans}


@router.get("/my-subscription")
async def get_my_subscription(request: Request):
    """Get current user's subscription details."""
    user = await require_auth(request)
    sub = await db.subscriptions.find_one({"user_id": user.user_id, "status": "active"}, {"_id": 0})
    current_plan = "free"
    if sub:
        current_plan = sub.get("plan", "free")

    plan_info = PLANS.get(current_plan, PLANS["free"])
    return {
        "plan": current_plan,
        "plan_info": {**plan_info, "id": current_plan},
        "subscription": sub,
        "usage": {
            "daily_limit": plan_info["daily_limit"],
            "features": plan_info["features"],
        },
    }


@router.post("/upgrade")
async def upgrade_subscription(request: Request):
    """Upgrade user's subscription plan."""
    user = await require_auth(request)
    from utils.preprod_entitlement_lock import is_preprod_lock_active

    if is_preprod_lock_active() and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Subscriptions are disabled until production launch.")
    body = await request.json()
    target_plan = body.get("plan", "pro")

    if target_plan not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")
    if target_plan == "free":
        raise HTTPException(status_code=400, detail="Use downgrade endpoint for free plan")

    # Check existing subscription
    existing = await db.subscriptions.find_one({"user_id": user.user_id, "status": "active"}, {"_id": 0})
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        # Upgrade existing
        await db.subscriptions.update_one(
            {"user_id": user.user_id, "status": "active"},
            {"$set": {"plan": target_plan, "upgraded_at": now, "previous_plan": existing.get("plan", "free")}},
        )
    else:
        # Create new subscription
        sub = {
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user.user_id,
            "plan": target_plan,
            "status": "active",
            "created_at": now,
            "billing_cycle": "monthly",
        }
        await db.subscriptions.insert_one(sub)

    # Notify
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=user.user_id,
            notif_type="subscription_upgrade",
            title=f"Upgraded to {PLANS[target_plan]['name']}",
            body=f"Welcome to {PLANS[target_plan]['name']}! You now have access to {len(PLANS[target_plan]['features'])} features.",
            action_url="/settings",
        )
    except Exception:
        pass

    return {"success": True, "plan": target_plan, "price": PLANS[target_plan]["price"]}


@router.post("/downgrade")
async def downgrade_subscription(request: Request):
    """Downgrade or cancel subscription."""
    user = await require_auth(request)
    body = await request.json()
    target_plan = body.get("plan", "free")
    now = datetime.now(timezone.utc).isoformat()

    if target_plan == "free":
        # Cancel active subscription
        await db.subscriptions.update_one(
            {"user_id": user.user_id, "status": "active"},
            {"$set": {"status": "canceled", "canceled_at": now}},
        )
        # Trigger churn recovery email
        try:
            from services.churn_recovery import handle_subscription_cancellation

            await handle_subscription_cancellation(user.user_id, user.email, getattr(user, "name", user.email))
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Churn recovery trigger failed: {e}")
    else:
        await db.subscriptions.update_one(
            {"user_id": user.user_id, "status": "active"},
            {"$set": {"plan": target_plan, "downgraded_at": now}},
        )

    return {"success": True, "plan": target_plan}


@router.get("/cohort-analysis")
async def cohort_analysis(request: Request, months: int = 6):
    """Get cohort retention analysis."""
    await _require_admin(request)
    now = datetime.now(timezone.utc)
    cohorts = []

    for i in range(months - 1, -1, -1):
        cohort_month = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        cohort_end = (cohort_month + timedelta(days=32)).replace(day=1)
        cohort_label = cohort_month.strftime("%b %Y")

        # Users who signed up in this cohort
        cohort_users = await db.users.count_documents(
            {"created_at": {"$gte": cohort_month.isoformat(), "$lt": cohort_end.isoformat()}}
        )

        # How many are still active (have activity in last 30 days)
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        active_now = await db.sessions.count_documents(
            {
                "created_at": {"$gte": thirty_days_ago},
                "user_id": {
                    "$in": [
                        u["user_id"]
                        async for u in db.users.find(
                            {"created_at": {"$gte": cohort_month.isoformat(), "$lt": cohort_end.isoformat()}},
                            {"_id": 0, "user_id": 1},
                        ).limit(500)
                    ]
                },
            }
        )

        retention = round((active_now / max(1, cohort_users)) * 100, 1)

        cohorts.append(
            {
                "month": cohort_month.strftime("%Y-%m"),
                "label": cohort_label,
                "users_joined": cohort_users,
                "still_active": min(active_now, cohort_users),
                "retention_pct": min(100, retention),
            }
        )

    return {"cohorts": cohorts, "months": months}


@router.get("/unified")
async def get_unified_revenue(request: Request, period: str = "30d"):
    """Unified revenue dashboard combining Stripe (web) + IAP (mobile) data."""
    await _require_admin(request)
    now = datetime.now(timezone.utc)
    days = int(period.replace("d", "")) if period.endswith("d") else 30
    since = (now - timedelta(days=days)).isoformat()
    (now - timedelta(days=days * 2)).isoformat()

    # ── Stripe (web) revenue ──
    stripe_active = await db.users.count_documents({
        "subscription_status": "active", "subscription_plan": {"$ne": "free"},
        "iap_platform": {"$exists": False}
    })
    stripe_plan_counts = {}
    for plan in ["basic", "premium"]:
        c = await db.users.count_documents({
            "subscription_plan": plan, "subscription_status": "active",
            "iap_platform": {"$exists": False}
        })
        if c > 0:
            stripe_plan_counts[plan] = c
    stripe_mrr = sum(PLANS.get(p, {}).get("price", 0) * c for p, c in stripe_plan_counts.items())
    stripe_new = await db.users.count_documents({
        "subscription_status": "active", "subscription_plan": {"$ne": "free"},
        "iap_platform": {"$exists": False}, "created_at": {"$gte": since}
    })
    stripe_churned = await db.users.count_documents({
        "subscription_status": "cancelled", "iap_platform": {"$exists": False},
        "updated_at": {"$gte": since}
    })

    # ── IAP (mobile) revenue ──
    iap_apple_active = await db.users.count_documents({"iap_platform": "apple", "subscription_status": "active", "subscription_plan": {"$ne": "free"}})
    iap_google_active = await db.users.count_documents({"iap_platform": "google", "subscription_status": "active", "subscription_plan": {"$ne": "free"}})
    iap_total_active = iap_apple_active + iap_google_active
    iap_total_txs = await db.iap_transactions.count_documents({})

    iap_rev_pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": {"plan": "$plan", "period": "$period"}, "count": {"$sum": 1}}},
    ]
    iap_rev_groups = await db.iap_transactions.aggregate(iap_rev_pipeline).to_list(100)

    iap_plan_prices = {
        "basic": {"monthly": get_plan_amount("basic", "monthly"), "yearly": get_plan_amount("basic", "yearly")},
        "premium": {"monthly": get_plan_amount("premium", "monthly"), "yearly": get_plan_amount("premium", "yearly")},
    }
    iap_mrr = 0
    for g in iap_rev_groups:
        plan = g["_id"].get("plan", "free")
        period_type = g["_id"].get("period", "monthly")
        price = iap_plan_prices.get(plan, {}).get(period_type, 0)
        monthly_price = price if period_type == "monthly" else price / 12
        iap_mrr += monthly_price * g["count"]

    iap_new = await db.iap_transactions.count_documents({"created_at": {"$gte": since}})

    # ── Combined metrics ──
    total_mrr = stripe_mrr + iap_mrr
    total_arr = total_mrr * 12
    total_active = stripe_active + iap_total_active
    total_new = stripe_new + iap_new

    # Churn
    total_churned = stripe_churned
    start_active = total_active + total_churned - total_new
    churn_rate = round((total_churned / max(1, start_active)) * 100, 1) if start_active > 0 else 0
    arpu = round(total_mrr / max(1, total_active), 2)
    monthly_churn = churn_rate / 100 if churn_rate > 0 else 0.05
    ltv = round(arpu / max(0.01, monthly_churn), 2)

    # ── Monthly trends (last 6 months, both channels) ──
    trends = []
    for i in range(5, -1, -1):
        target_month = now.month - i
        target_year = now.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        m_start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
        next_m = target_month + 1
        next_y = target_year
        if next_m > 12:
            next_m = 1
            next_y += 1
        m_end = datetime(next_y, next_m, 1, tzinfo=timezone.utc)
        ms, me = m_start.isoformat(), m_end.isoformat()

        s_new = await db.users.count_documents({
            "subscription_status": "active", "subscription_plan": {"$ne": "free"},
            "iap_platform": {"$exists": False},
            "$or": [
                {"created_at": {"$gte": m_start, "$lt": m_end}},
                {"created_at": {"$gte": ms, "$lt": me}},
            ]
        })
        s_basic = await db.users.count_documents({
            "subscription_plan": "basic", "subscription_status": "active",
            "iap_platform": {"$exists": False},
            "$or": [{"created_at": {"$lt": m_end}}, {"created_at": {"$lt": me}}]
        })
        s_premium = await db.users.count_documents({
            "subscription_plan": "premium", "subscription_status": "active",
            "iap_platform": {"$exists": False},
            "$or": [{"created_at": {"$lt": m_end}}, {"created_at": {"$lt": me}}]
        })
        s_mrr = s_basic * PLANS["basic"]["price"] + s_premium * PLANS["premium"]["price"]

        i_new = await db.iap_transactions.count_documents({"created_at": {"$gte": ms, "$lt": me}})
        i_plan_pipe = [
            {"$match": {"created_at": {"$lt": me}, "status": "active"}},
            {"$group": {"_id": {"plan": "$plan", "period": "$period"}, "count": {"$sum": 1}}},
        ]
        i_plan_data = await db.iap_transactions.aggregate(i_plan_pipe).to_list(100)
        i_mrr = 0
        for g in i_plan_data:
            plan = g["_id"].get("plan", "free")
            pt = g["_id"].get("period", "monthly")
            price = iap_plan_prices.get(plan, {}).get(pt, 0)
            i_mrr += (price if pt == "monthly" else price / 12) * g["count"]

        trends.append({
            "month": m_start.strftime("%Y-%m"),
            "label": m_start.strftime("%b %Y"),
            "stripe_mrr": round(s_mrr, 2),
            "iap_mrr": round(i_mrr, 2),
            "total_mrr": round(s_mrr + i_mrr, 2),
            "stripe_new": s_new,
            "iap_new": i_new,
        })

    return {
        "combined": {
            "total_mrr": round(total_mrr, 2),
            "total_arr": round(total_arr, 2),
            "total_active_subscribers": total_active,
            "total_new_subscribers": total_new,
            "churn_rate": churn_rate,
            "arpu": arpu,
            "ltv": ltv,
        },
        "stripe": {
            "mrr": round(stripe_mrr, 2),
            "active_subscribers": stripe_active,
            "new_subscribers": stripe_new,
            "churned": stripe_churned,
            "plan_breakdown": {p: stripe_plan_counts.get(p, 0) for p in PLANS},
        },
        "iap": {
            "mrr": round(iap_mrr, 2),
            "active_subscribers": iap_total_active,
            "apple_active": iap_apple_active,
            "google_active": iap_google_active,
            "total_transactions": iap_total_txs,
            "new_transactions": iap_new,
        },
        "trends": trends,
        "period": period,
        "generated_at": now.isoformat(),
    }
