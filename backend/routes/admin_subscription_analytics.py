"""Admin Subscription Analytics — MRR, churn, funnel, plan distribution."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
from dateutil.parser import parse as dt_parse
from typing import List, Optional
from pydantic import BaseModel, Field
from routes.db import db, require_admin
from routes.payments_catalog import get_subscription_plan_catalog
from routes.subscription_enforcement import _get_required_level, EXEMPT_EMAILS
from shared.pricing_policy import get_monthly_price_map, get_yearly_price_map

router = APIRouter(prefix="/admin/subscription-analytics", tags=["Subscription Analytics"])

DEFAULT_MONTHLY_PLANS = get_monthly_price_map()
DEFAULT_YEARLY_PLANS = get_yearly_price_map()
KNOWN_PLANS = set(DEFAULT_MONTHLY_PLANS.keys())

SAMPLE_PROTECTED_PATHS = [
    "/api/admin/payment-analytics/subscriptions/integrity-report/latest",
    "/api/ai-engine/chat",
    "/api/content-studio/generate",
    "/api/developer/workspace/projects",
    "/api/notifications",
    "/api/subscriptions/plans",
    "/api/payments/checkout",
    "/api/admin/employees",
    "/api/admin/platform-health/scan",
    "/api/i18n/language-guidance",
]


# ─────────────────────────────────────────────────────────────────────────
# OpenAPI response models for /enforcement-audit
#
# These types document the exact shape of the audit response, including
# the top-level `health_score` field. Surfaces the contract in /docs and
# generated client SDKs (which would otherwise lose the type information
# in a plain dict return).
# ─────────────────────────────────────────────────────────────────────────


class EnforcementAuditPlanCounts(BaseModel):
    free: int = Field(0, description="Number of users currently on the free plan.")
    basic: int = Field(0, description="Number of users currently on the basic plan.")
    premium: int = Field(0, description="Number of users currently on the premium plan.")


class EnforcementAuditSummary(BaseModel):
    total_users: int = Field(..., description="Total user records in the database.")
    plan_counts: EnforcementAuditPlanCounts
    unknown_plan_count: int = Field(..., description="Users whose subscription_plan is outside the known set (free/basic/premium).")
    premium_without_role_count: int = Field(..., description="Users with premium_access=True but no platform_role assigned.")
    expired_but_paid_count: int = Field(..., description="Users on basic/premium whose subscription_end_date is in the past.")
    non_admin_full_access_count: int = Field(..., description="Non-admin, non-exempt users carrying the legacy full_access flag.")


class EnforcementAuditRouteEntry(BaseModel):
    path: str = Field(..., description="API path being audited for enforcement coverage.")
    required_level: int = Field(..., description="Numeric access level (-1=public, 0=free, 1=basic, 2=premium).")
    required_plan: str = Field(..., description="Plan name corresponding to required_level.")


class EnforcementAuditHighRiskUser(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    plan: Optional[str] = Field(None, description="Current subscription_plan stored on the user record.")
    status: Optional[str] = Field(None, description="Current subscription_status stored on the user record.")
    subscription_end_date: Optional[str] = Field(None, description="ISO8601 end date that has already elapsed.")


class EnforcementRealtimeStatus(BaseModel):
    backend_middleware_enabled: bool = True
    frontend_subscription_interceptor: bool = True
    admin_exempt: bool = True


class SubscriptionEnforcementAuditResponse(BaseModel):
    """Top-level response for `GET /api/admin/subscription-analytics/enforcement-audit`.

    Note: `health_score` is at the TOP LEVEL (not nested under `summary`).
    It is a 0-100 integer computed from the four counts in `summary`.
    """

    timestamp: str = Field(..., description="UTC ISO8601 timestamp at which the audit ran.")
    health_score: int = Field(..., ge=0, le=100, description="Subscription enforcement health score (0-100). 100 means no integrity issues detected; lower scores indicate the number/severity of unknown plans, premium-without-role users, expired-but-paid users, and non-admin full-access carriers.")
    summary: EnforcementAuditSummary
    route_enforcement_matrix: List[EnforcementAuditRouteEntry]
    high_risk_users: List[EnforcementAuditHighRiskUser] = Field(..., description="Capped at 100 entries; full list available via the auto-fix endpoint.")
    realtime_enforcement: EnforcementRealtimeStatus
    recommended_actions: List[str]
    issues_total: int = Field(..., description="Sum of unknown_plan_count + premium_without_role_count + expired_but_paid_count.")


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


async def _count_many_facet(collection, filters: dict[str, dict]) -> dict[str, int]:
    """Count many filters via one aggregation round-trip using $facet."""
    facet_pipeline = {
        key: [
            {"$match": query},
            {"$count": "count"},
        ]
        for key, query in filters.items()
    }
    rows = await collection.aggregate([{"$facet": facet_pipeline}]).to_list(length=1)
    first = rows[0] if rows else {}
    output: dict[str, int] = {}
    for key in filters.keys():
        bucket = first.get(key, []) if isinstance(first, dict) else []
        output[key] = int(bucket[0].get("count", 0)) if bucket else 0
    return output


async def _load_live_plan_pricing():
    monthly_prices = dict(DEFAULT_MONTHLY_PLANS)
    yearly_prices = dict(DEFAULT_YEARLY_PLANS)
    records = await get_subscription_plan_catalog(include_deprecated=False)

    for rec in records:
        plan_id = str(rec.get("plan_id") or rec.get("id") or rec.get("key") or "").strip().lower()
        if not plan_id:
            continue

        monthly_raw = rec.get("monthly_price")
        if monthly_raw is None:
            monthly_raw = rec.get("price_monthly")
        if monthly_raw is None:
            monthly_raw = rec.get("price")

        yearly_raw = rec.get("yearly_price")
        if yearly_raw is None:
            yearly_raw = rec.get("price_yearly")

        monthly_val = _safe_float(monthly_raw, monthly_prices.get(plan_id, 0.0))
        yearly_val = _safe_float(yearly_raw, yearly_prices.get(plan_id, monthly_val * 12))

        monthly_prices[plan_id] = monthly_val
        yearly_prices[plan_id] = yearly_val

    plan_catalog = []
    for plan_id in sorted(monthly_prices.keys()):
        monthly_price = _safe_float(monthly_prices.get(plan_id, 0.0))
        yearly_price = _safe_float(yearly_prices.get(plan_id, monthly_price * 12))
        yearly_discount_pct = 0.0
        if monthly_price > 0:
            yearly_discount_pct = round(max(0.0, min(100.0, 100.0 - ((yearly_price / (monthly_price * 12)) * 100.0))), 1)

        plan_catalog.append(
            {
                "plan_id": plan_id,
                "name": plan_id.replace("_", " ").title(),
                "monthly_price": round(monthly_price, 2),
                "yearly_price": round(yearly_price, 2),
                "monthly_equivalent": round(yearly_price / 12 if yearly_price > 0 else monthly_price, 2),
                "yearly_discount_pct": yearly_discount_pct,
            }
        )

    return monthly_prices, yearly_prices, plan_catalog


@router.get("")
async def subscription_analytics(request: Request, period: str = "30d"):
    """Combined subscription analytics: MRR, churn, funnel, distribution."""
    await require_admin(request)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)
    since = (now - timedelta(days=days)).isoformat()
    prev_since = (now - timedelta(days=days * 2)).isoformat()
    monthly_prices, yearly_prices, plan_catalog = await _load_live_plan_pricing()

    base_counts = await _count_many_facet(
        db.users,
        {
            "total_users": {},
            "active_subs": {"subscription_status": "active", "subscription_plan": {"$ne": "free"}},
            "free_users": {"$or": [{"subscription_plan": "free"}, {"subscription_plan": {"$exists": False}}]},
            "basic_users": {"subscription_plan": "basic", "subscription_status": "active"},
            "premium_users": {"subscription_plan": "premium", "subscription_status": "active"},
            "new_subs": {
                "subscription_status": "active",
                "subscription_plan": {"$ne": "free"},
                "created_at": {"$gte": since},
            },
            "churned": {"subscription_status": "cancelled", "updated_at": {"$gte": since}},
            "prev_churned": {
                "subscription_status": "cancelled",
                "updated_at": {"$gte": prev_since, "$lt": since},
            },
            "basic_yearly": {
                "subscription_plan": "basic",
                "subscription_status": "active",
                "$or": [{"iap_product_id": {"$regex": "yearly"}}, {"billing_period": "yearly"}],
            },
            "premium_yearly": {
                "subscription_plan": "premium",
                "subscription_status": "active",
                "$or": [{"iap_product_id": {"$regex": "yearly"}}, {"billing_period": "yearly"}],
            },
            "signups_period": {"created_at": {"$gte": since}},
            "trial_started": {"subscription_status": {"$in": ["active", "trial"]}, "created_at": {"$gte": since}},
            "apple_subs": {
                "subscription_status": "active",
                "subscription_plan": {"$ne": "free"},
                "iap_platform": "apple",
            },
            "google_subs": {
                "subscription_status": "active",
                "subscription_plan": {"$ne": "free"},
                "iap_platform": "google",
            },
            "apple_basic_m": {
                "subscription_plan": "basic",
                "subscription_status": "active",
                "iap_platform": "apple",
                "iap_product_id": {"$not": {"$regex": "yearly"}},
            },
            "apple_basic_y": {
                "subscription_plan": "basic",
                "subscription_status": "active",
                "iap_platform": "apple",
                "iap_product_id": {"$regex": "yearly"},
            },
            "apple_prem_m": {
                "subscription_plan": "premium",
                "subscription_status": "active",
                "iap_platform": "apple",
                "iap_product_id": {"$not": {"$regex": "yearly"}},
            },
            "apple_prem_y": {
                "subscription_plan": "premium",
                "subscription_status": "active",
                "iap_platform": "apple",
                "iap_product_id": {"$regex": "yearly"},
            },
            "google_basic_m": {
                "subscription_plan": "basic",
                "subscription_status": "active",
                "iap_platform": "google",
                "iap_product_id": {"$not": {"$regex": "yearly"}},
            },
            "google_basic_y": {
                "subscription_plan": "basic",
                "subscription_status": "active",
                "iap_platform": "google",
                "iap_product_id": {"$regex": "yearly"},
            },
            "google_prem_m": {
                "subscription_plan": "premium",
                "subscription_status": "active",
                "iap_platform": "google",
                "iap_product_id": {"$not": {"$regex": "yearly"}},
            },
            "google_prem_y": {
                "subscription_plan": "premium",
                "subscription_status": "active",
                "iap_platform": "google",
                "iap_product_id": {"$regex": "yearly"},
            },
        },
    )

    total_users = base_counts["total_users"]
    active_subs = base_counts["active_subs"]
    free_users = base_counts["free_users"]
    basic_users = base_counts["basic_users"]
    premium_users = base_counts["premium_users"]
    new_subs = base_counts["new_subs"]
    churned = base_counts["churned"]
    prev_churned = base_counts["prev_churned"]
    basic_yearly = base_counts["basic_yearly"]
    premium_yearly = base_counts["premium_yearly"]
    basic_monthly = basic_users - basic_yearly
    premium_monthly = premium_users - premium_yearly

    mrr = (basic_monthly * monthly_prices.get("basic", 0.0)) + (basic_yearly * yearly_prices.get("basic", 0.0) / 12) + \
          (premium_monthly * monthly_prices.get("premium", 0.0)) + (premium_yearly * yearly_prices.get("premium", 0.0) / 12)
    mrr = round(mrr, 2)
    arr = mrr * 12
    start_active = active_subs + churned - new_subs
    churn_rate = round((churned / max(1, start_active)) * 100, 1) if start_active > 0 else 0
    prev_churn_rate = round((prev_churned / max(1, start_active)) * 100, 1) if start_active > 0 else 0
    arpu = round(mrr / max(1, active_subs), 2)
    monthly_churn = churn_rate / 100 if churn_rate > 0 else 0.05
    ltv = round(arpu / max(0.01, monthly_churn), 2)

    conversion_rate = round((active_subs / max(1, total_users)) * 100, 1)

    # Real online users (distinct users with non-revoked, unexpired sessions)
    active_session_filter = {
        "$and": [
            {
                "$or": [
                    {"expires_at": {"$gt": now}},
                    {"expires_at": {"$gt": now_iso}},
                ]
            },
            {
                "$or": [
                    {"revoked": {"$exists": False}},
                    {"revoked": False},
                ]
            },
            {"user_id": {"$exists": True, "$ne": ""}},
        ]
    }
    try:
        online_user_ids = await db.user_sessions.distinct("user_id", active_session_filter)
        online_users_live = len(online_user_ids or [])
    except Exception:
        online_users_live = 0

    # Monthly trend (last 6 months) using single $facet aggregation
    month_windows = []
    for i in range(5, -1, -1):
        month_start = (now - timedelta(days=i * 30)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = (month_start + timedelta(days=32)).replace(day=1)
        month_windows.append(
            {
                "label": month_start.strftime("%b %Y"),
                "start_iso": month_start.isoformat(),
                "end_iso": month_end.isoformat(),
            }
        )

    facet_stage = {}
    for idx, month in enumerate(month_windows):
        start_iso = month["start_iso"]
        end_iso = month["end_iso"]
        facet_stage[f"m{idx}_basic"] = [
            {"$match": {"subscription_plan": "basic", "subscription_status": "active", "created_at": {"$lt": end_iso}}},
            {"$count": "count"},
        ]
        facet_stage[f"m{idx}_premium"] = [
            {"$match": {"subscription_plan": "premium", "subscription_status": "active", "created_at": {"$lt": end_iso}}},
            {"$count": "count"},
        ]
        facet_stage[f"m{idx}_churned"] = [
            {"$match": {"subscription_status": "cancelled", "updated_at": {"$gte": start_iso, "$lt": end_iso}}},
            {"$count": "count"},
        ]
        facet_stage[f"m{idx}_new"] = [
            {
                "$match": {
                    "subscription_plan": {"$ne": "free"},
                    "subscription_status": "active",
                    "created_at": {"$gte": start_iso, "$lt": end_iso},
                }
            },
            {"$count": "count"},
        ]

    facet_result = await db.users.aggregate([{"$facet": facet_stage}]).to_list(length=1)
    facet_doc = facet_result[0] if facet_result else {}

    def _facet_count(key: str) -> int:
        rows = facet_doc.get(key, []) if isinstance(facet_doc, dict) else []
        if not rows:
            return 0
        return int(rows[0].get("count", 0))

    trends = []
    for idx, month in enumerate(month_windows):
        m_basic = _facet_count(f"m{idx}_basic")
        m_premium = _facet_count(f"m{idx}_premium")
        m_churned = _facet_count(f"m{idx}_churned")
        m_new = _facet_count(f"m{idx}_new")
        m_mrr = m_basic * monthly_prices.get("basic", 0.0) + m_premium * monthly_prices.get("premium", 0.0)
        trends.append(
            {
                "month": month["label"],
                "mrr": round(m_mrr, 2),
                "churned": m_churned,
                "new_subs": m_new,
                "basic": m_basic,
                "premium": m_premium,
            }
        )

    # Funnel
    signups_period = base_counts["signups_period"]
    trial_started = base_counts["trial_started"]
    converted = new_subs
    retained = active_subs

    funnel = [
        {"stage": "Signups", "count": signups_period, "pct": 100},
        {"stage": "Activated", "count": trial_started, "pct": round((trial_started / max(1, signups_period)) * 100, 1)},
        {"stage": "Converted", "count": converted, "pct": round((converted / max(1, signups_period)) * 100, 1)},
        {"stage": "Retained", "count": retained, "pct": round((retained / max(1, signups_period)) * 100, 1)},
    ]

    # ── Platform & Billing Breakdown ────────────────────────────────
    # IAP platform split
    apple_subs = base_counts["apple_subs"]
    google_subs = base_counts["google_subs"]
    stripe_subs = active_subs - apple_subs - google_subs

    # Billing period split (for IAP + Stripe)
    yearly_subs = basic_yearly + premium_yearly
    monthly_subs = active_subs - yearly_subs

    # Per-platform revenue (MRR)
    # Apple
    apple_basic_m = base_counts["apple_basic_m"]
    apple_basic_y = base_counts["apple_basic_y"]
    apple_prem_m = base_counts["apple_prem_m"]
    apple_prem_y = base_counts["apple_prem_y"]
    apple_mrr = round(
        apple_basic_m * monthly_prices.get("basic", 0.0)
        + apple_basic_y * yearly_prices.get("basic", 0.0) / 12
        + apple_prem_m * monthly_prices.get("premium", 0.0)
        + apple_prem_y * yearly_prices.get("premium", 0.0) / 12,
        2,
    )

    # Google
    google_basic_m = base_counts["google_basic_m"]
    google_basic_y = base_counts["google_basic_y"]
    google_prem_m = base_counts["google_prem_m"]
    google_prem_y = base_counts["google_prem_y"]
    google_mrr = round(
        google_basic_m * monthly_prices.get("basic", 0.0)
        + google_basic_y * yearly_prices.get("basic", 0.0) / 12
        + google_prem_m * monthly_prices.get("premium", 0.0)
        + google_prem_y * yearly_prices.get("premium", 0.0) / 12,
        2,
    )

    stripe_mrr = round(mrr - apple_mrr - google_mrr, 2)

    # IAP transaction counts (last period)
    transaction_counts = await _count_many_facet(
        db.iap_transactions,
        {
            "iap_txns_period": {"created_at": {"$gte": since}},
            "apple_txns": {"platform": "apple", "created_at": {"$gte": since}},
            "google_txns": {"platform": "google", "created_at": {"$gte": since}},
        },
    )
    iap_txns_period = transaction_counts["iap_txns_period"]
    apple_txns = transaction_counts["apple_txns"]
    google_txns = transaction_counts["google_txns"]

    return {
        "period": period,
        "kpis": {
            "mrr": round(mrr, 2),
            "arr": round(arr, 2),
            "churn_rate": churn_rate,
            "prev_churn_rate": prev_churn_rate,
            "ltv": ltv,
            "arpu": arpu,
            "active_subs": active_subs,
            "new_subs": new_subs,
            "churned": churned,
            "conversion_rate": conversion_rate,
            "total_users": total_users,
            "online_users_live": online_users_live,
        },
        "distribution": {
            "free": free_users,
            "basic": basic_users,
            "premium": premium_users,
        },
        "platform": {
            "apple": {"subs": apple_subs, "mrr": apple_mrr, "txns": apple_txns},
            "google": {"subs": google_subs, "mrr": google_mrr, "txns": google_txns},
            "stripe": {"subs": stripe_subs, "mrr": stripe_mrr},
            "iap_txns_period": iap_txns_period,
        },
        "billing": {
            "monthly": monthly_subs,
            "yearly": yearly_subs,
            "monthly_pct": round((monthly_subs / max(1, active_subs)) * 100, 1),
            "yearly_pct": round((yearly_subs / max(1, active_subs)) * 100, 1),
        },
        "plan_catalog": plan_catalog,
        "trends": trends,
        "funnel": funnel,
    }



@router.get("/overview")
async def subscription_overview(request: Request, period: str = "30d"):
    """Alias for subscription analytics overview."""
    return await subscription_analytics(request, period)


@router.get(
    "/enforcement-audit",
    response_model=SubscriptionEnforcementAuditResponse,
    summary="Subscription enforcement audit",
    description=(
        "Deep audit of subscription enforcement across the user base. Returns a "
        "0-100 `health_score` (top-level, NOT nested under `summary`) computed "
        "from four integrity counts: unknown plans, premium-without-role, "
        "expired-but-paid, and non-admin full-access carriers. Caps "
        "`high_risk_users` at 100 entries; use the `/enforcement-audit/auto-fix` "
        "endpoint for safe normalization of the underlying records."
    ),
)
async def subscription_enforcement_audit(request: Request):
    """Deep subscription enforcement audit with bypass-risk detection and route-level policy checks."""
    await require_admin(request)
    now = datetime.now(timezone.utc)

    audit_counts = await _count_many_facet(
        db.users,
        {
            "total_users": {},
            "free": {"subscription_plan": "free"},
            "basic": {"subscription_plan": "basic"},
            "premium": {"subscription_plan": "premium"},
            "unknown_plans": {"subscription_plan": {"$exists": True, "$nin": list(KNOWN_PLANS)}},
            "non_admin_full_access": {
                "full_access": True,
                "$or": [{"is_admin": {"$ne": True}}, {"is_admin": {"$exists": False}}],
                "email": {"$nin": list(EXEMPT_EMAILS)},
                "premium_access": {"$ne": True},
                "$and": [
                    {"$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}]},
                ],
            },
            "premium_without_role": {
                "premium_access": True,
                "$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}],
            },
        },
    )
    total_users = audit_counts["total_users"]
    plan_counts = {
        "free": audit_counts["free"],
        "basic": audit_counts["basic"],
        "premium": audit_counts["premium"],
    }
    unknown_plans = audit_counts["unknown_plans"]
    non_admin_full_access = audit_counts["non_admin_full_access"]
    premium_without_role = audit_counts["premium_without_role"]

    expired_paid_cursor = await db.users.find(
        {
            "subscription_plan": {"$in": ["basic", "premium"]},
            "subscription_status": {"$in": ["active", "expired", "cancelled"]},
            "subscription_end_date": {"$exists": True, "$ne": None},
        },
        {"_id": 0, "user_id": 1, "email": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1},
    ).to_list(5000)

    expired_but_paid = []
    for u in expired_paid_cursor:
        end_raw = u.get("subscription_end_date")
        if not end_raw:
            continue
        try:
            end_dt = dt_parse(str(end_raw)) if isinstance(end_raw, str) else end_raw
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if end_dt < now and u.get("subscription_plan") in {"basic", "premium"}:
            expired_but_paid.append({
                "user_id": u.get("user_id"),
                "email": u.get("email"),
                "plan": u.get("subscription_plan"),
                "status": u.get("subscription_status"),
                "subscription_end_date": end_dt.isoformat(),
            })

    route_matrix = []
    for path in SAMPLE_PROTECTED_PATHS:
        level = _get_required_level(path)
        level_name = "public" if level == -1 else "free" if level == 0 else "basic" if level == 1 else "premium"
        route_matrix.append({
            "path": path,
            "required_level": level,
            "required_plan": level_name,
        })

    issues_total = unknown_plans + premium_without_role + len(expired_but_paid)
    score = 100
    score -= min(20, unknown_plans * 5)
    score -= min(25, premium_without_role * 5)
    score -= min(30, len(expired_but_paid) * 3)
    score -= min(20, non_admin_full_access * 2)
    score = max(0, score)

    return {
        "timestamp": now.isoformat(),
        "health_score": score,
        "summary": {
            "total_users": total_users,
            "plan_counts": plan_counts,
            "unknown_plan_count": unknown_plans,
            "premium_without_role_count": premium_without_role,
            "expired_but_paid_count": len(expired_but_paid),
            "non_admin_full_access_count": non_admin_full_access,
        },
        "route_enforcement_matrix": route_matrix,
        "high_risk_users": expired_but_paid[:100],
        "realtime_enforcement": {
            "backend_middleware_enabled": True,
            "frontend_subscription_interceptor": True,
            "admin_exempt": True,
        },
        "recommended_actions": [
            "Run POST /api/admin/subscription-analytics/enforcement-audit/auto-fix for safe normalization",
            "Review non-admin full_access accounts and keep only approved exceptions",
            "Review premium_access users without platform_role and convert to managed employee roles",
        ],
        "issues_total": issues_total,
    }


@router.post("/enforcement-audit/auto-fix")
async def subscription_enforcement_auto_fix(request: Request):
    """Safe auto-fix for subscription enforcement data drift and privilege-risk edge cases."""
    await require_admin(request)
    now = datetime.now(timezone.utc).isoformat()

    unknown_plan_result = await db.users.update_many(
        {"subscription_plan": {"$exists": True, "$nin": list(KNOWN_PLANS)}},
        {
            "$set": {
                "subscription_plan": "free",
                "subscription_status": "expired",
                "payment_verified": False,
                "updated_at": now,
            }
        },
    )

    premium_without_role_result = await db.users.update_many(
        {
            "premium_access": True,
            "$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}],
        },
        {
            "$set": {
                "premium_access": False,
                "updated_at": now,
            }
        },
    )

    unauthorized_full_access_result = await db.users.update_many(
        {
            "full_access": True,
            "$or": [{"is_admin": {"$ne": True}}, {"is_admin": {"$exists": False}}],
            "email": {"$nin": list(EXEMPT_EMAILS)},
            "premium_access": {"$ne": True},
            "$and": [
                {"$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}]},
            ],
        },
        {
            "$set": {
                "full_access": False,
                "full_access_revoked_at": now,
                "updated_at": now,
            }
        },
    )

    expired_fixed = 0
    users = await db.users.find(
        {
            "subscription_plan": {"$in": ["basic", "premium"]},
            "subscription_end_date": {"$exists": True, "$ne": None},
        },
        {"_id": 0, "user_id": 1, "subscription_end_date": 1},
    ).to_list(5000)
    now_dt = datetime.now(timezone.utc)
    for u in users:
        try:
            end_dt = dt_parse(str(u.get("subscription_end_date")))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if end_dt < now_dt:
            upd = await db.users.update_one(
                {"user_id": u.get("user_id")},
                {
                    "$set": {
                        "subscription_plan": "free",
                        "subscription_status": "expired",
                        "payment_verified": False,
                        "updated_at": now,
                    }
                },
            )
            if upd.modified_count:
                expired_fixed += 1

    return {
        "success": True,
        "fixed_at": now,
        "fixes": {
            "unknown_plan_normalized": unknown_plan_result.modified_count,
            "premium_without_role_revoked": premium_without_role_result.modified_count,
            "unauthorized_full_access_revoked": unauthorized_full_access_result.modified_count,
            "expired_plan_downgraded": expired_fixed,
        },
    }
