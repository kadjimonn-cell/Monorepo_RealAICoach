"""Feature Access Control & Subscription Enforcement System.

Server-side tier enforcement for Free/Basic/Premium subscriptions.
Includes Developer Workspace usage tracking and limits.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import logging

from routes.db import db, get_current_user
from routes.payments_catalog import get_subscription_plan_from_gps, get_subscription_plans_from_gps
from utils.access_control_engine import FEATURE_ACCESS, compute_effective_plan

logger = logging.getLogger(__name__)
router = APIRouter()

def _resolve_tier(user) -> str:
    """Get effective subscription tier from user object."""
    if not user:
        return "free"
    return compute_effective_plan(
        {
            "subscription_plan": getattr(user, "subscription_plan", "free"),
            "subscription_status": getattr(user, "subscription_status", "active"),
            "subscription_end_date": getattr(user, "subscription_end_date", None),
            "subscription_permanent": getattr(user, "subscription_permanent", False),
            "is_admin": getattr(user, "is_admin", False),
            "full_access": getattr(user, "full_access", False),
            "pending_subscription_transition": getattr(user, "pending_subscription_transition", None),
        }
    )


def get_feature_value(tier: str, feature: str):
    """Get the feature value for a given tier."""
    feature_def = FEATURE_ACCESS.get(feature)
    if not feature_def:
        return None
    return feature_def.get(tier, feature_def.get("free"))


@router.get("/feature-access/check")
async def check_feature_access(feature: str, request: Request):
    """Check if current user has access to a specific feature."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tier = _resolve_tier(user)
    value = get_feature_value(tier, feature)

    result = {
        "feature": feature,
        "tier": tier,
        "value": value,
        "has_access": value is not None and value is not False and value != 0,
    }

    # For numeric limits, check usage
    if feature.startswith("dev_") and isinstance(value, int) and value > 0:
        usage = await _get_daily_usage(user.user_id, feature)
        result["usage"] = usage
        result["limit"] = value
        result["remaining"] = max(0, value - usage)
        result["has_access"] = usage < value

    return result


@router.get("/feature-access/tier-info")
async def get_tier_info(request: Request):
    """Get complete feature access info for the current user's tier."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tier = _resolve_tier(user)
    features = {}
    for feature_name, tiers in FEATURE_ACCESS.items():
        features[feature_name] = tiers.get(tier, tiers.get("free"))

    # Get dev workspace usage
    dev_usage = {}
    if tier == "free":
        dev_usage["ai_requests"] = await _get_daily_usage(user.user_id, "dev_ai_requests_daily")
        dev_usage["projects"] = await _get_project_count(user.user_id)
        dev_usage["builds_today"] = await _get_daily_usage(user.user_id, "dev_max_builds")

    return {
        "tier": tier,
        "tier_name": tier.capitalize(),
        "features": features,
        "dev_usage": dev_usage,
    }


@router.get("/feature-access/all-tiers")
async def get_all_tiers():
    """Get feature matrix for all tiers (public endpoint for upgrade comparison)."""
    return {"features": FEATURE_ACCESS}


# ── Developer Workspace Endpoints ──


@router.get("/developer/workspace/status")
async def developer_workspace_status(request: Request):
    """Get developer workspace status with usage limits."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tier = _resolve_tier(user)
    access_level = get_feature_value(tier, "dev_workspace_access")
    ai_limit = get_feature_value(tier, "dev_ai_requests_daily")
    project_limit = get_feature_value(tier, "dev_max_projects")
    build_limit = get_feature_value(tier, "dev_max_builds")

    ai_used = await _get_daily_usage(user.user_id, "dev_ai_requests_daily")
    projects_count = await _get_project_count(user.user_id)
    builds_today = await _get_daily_usage(user.user_id, "dev_max_builds")

    return {
        "tier": tier,
        "access_level": access_level,
        "ai_requests": {
            "used": ai_used,
            "limit": ai_limit,
            "remaining": max(0, ai_limit - ai_used) if isinstance(ai_limit, int) and ai_limit > 0 else -1,
            "unlimited": ai_limit == -1,
        },
        "projects": {
            "count": projects_count,
            "limit": project_limit,
            "remaining": max(0, project_limit - projects_count)
            if isinstance(project_limit, int) and project_limit > 0
            else -1,
            "unlimited": project_limit == -1,
        },
        "builds": {
            "today": builds_today,
            "limit": build_limit,
            "remaining": max(0, build_limit - builds_today) if isinstance(build_limit, int) and build_limit > 0 else -1,
            "unlimited": build_limit == -1,
        },
        "features": {
            "api_keys": get_feature_value(tier, "dev_api_keys"),
            "advanced_debug": get_feature_value(tier, "dev_advanced_debug"),
            "multi_env": get_feature_value(tier, "dev_multi_env"),
            "team_collab": get_feature_value(tier, "dev_team_collab"),
            "perf_analytics": get_feature_value(tier, "dev_perf_analytics"),
            "advanced_export": get_feature_value(tier, "dev_advanced_export"),
        },
    }


class DevAIRequest(BaseModel):
    prompt: str
    project_id: Optional[str] = None


@router.post("/developer/workspace/ai-request")
async def developer_ai_request(payload: DevAIRequest, request: Request):
    """Track and enforce AI request limits for developer workspace."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tier = _resolve_tier(user)
    ai_limit = get_feature_value(tier, "dev_ai_requests_daily")

    if isinstance(ai_limit, int) and ai_limit > 0:
        usage = await _get_daily_usage(user.user_id, "dev_ai_requests_daily")
        if usage >= ai_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily AI request limit reached ({ai_limit}). Upgrade to unlock unlimited AI requests.",
            )

    # Log the usage
    await _log_usage(user.user_id, "dev_ai_requests_daily")

    return {
        "allowed": True,
        "message": "AI request processed",
        "usage": await _get_daily_usage(user.user_id, "dev_ai_requests_daily"),
        "limit": ai_limit,
    }


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = ""


@router.post("/developer/workspace/projects")
async def create_project(payload: CreateProjectRequest, request: Request):
    """Create a new developer project with tier-based limits."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tier = _resolve_tier(user)
    project_limit = get_feature_value(tier, "dev_max_projects")
    projects_count = await _get_project_count(user.user_id)

    if isinstance(project_limit, int) and project_limit > 0 and projects_count >= project_limit:
        raise HTTPException(
            status_code=403, detail=f"Project limit reached ({project_limit}). Upgrade to create unlimited projects."
        )

    project = {
        "project_id": f"proj_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "user_id": user.user_id,
        "name": payload.name,
        "description": payload.description,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.dev_projects.insert_one(project)
    project.pop("_id", None)

    return {"message": "Project created", "project": project}


@router.get("/developer/workspace/projects")
async def list_projects(request: Request):
    """List user's developer projects."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    cursor = db.dev_projects.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    projects = await cursor.to_list(100)
    return {"projects": projects, "count": len(projects)}


@router.post("/developer/workspace/build")
async def trigger_build(request: Request):
    """Trigger a build with tier-based limits."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tier = _resolve_tier(user)
    build_limit = get_feature_value(tier, "dev_max_builds")
    builds_today = await _get_daily_usage(user.user_id, "dev_max_builds")

    if isinstance(build_limit, int) and build_limit > 0 and builds_today >= build_limit:
        raise HTTPException(
            status_code=429, detail=f"Daily build limit reached ({build_limit}). Upgrade for unlimited builds."
        )

    await _log_usage(user.user_id, "dev_max_builds")

    build = {
        "build_id": f"build_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "user_id": user.user_id,
        "status": "success",
        "tier": tier,
        "created_at": datetime.now(timezone.utc),
    }
    await db.dev_builds.insert_one(build)
    build.pop("_id", None)

    return {"message": "Build triggered successfully", "build": build}


@router.get("/developer/workspace/builds")
async def list_builds(request: Request):
    """List user's build history."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    cursor = db.dev_builds.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(20)
    builds = await cursor.to_list(20)
    return {"builds": builds}


# ── Admin: Feature Flags Management ──


@router.get("/admin/feature-access/matrix")
async def admin_feature_matrix(request: Request):
    """Admin view of the complete feature access matrix."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get usage stats
    total_free = await db.users.count_documents({"subscription_plan": "free"})
    total_basic = await db.users.count_documents({"subscription_plan": "basic"})
    total_premium = await db.users.count_documents({"subscription_plan": {"$in": ["premium"]}})

    return {
        "feature_matrix": FEATURE_ACCESS,
        "tier_counts": {
            "free": total_free,
            "basic": total_basic,
            "premium": total_premium,
        },
    }


@router.get("/admin/developer/usage-stats")
async def admin_developer_usage_stats(request: Request):
    """Admin stats for developer workspace usage."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_ai_today = await db.dev_usage_logs.count_documents({"date": today, "feature": "dev_ai_requests_daily"})
    total_builds = await db.dev_builds.count_documents({})
    total_projects = await db.dev_projects.count_documents({})
    active_devs = len(await db.dev_usage_logs.distinct("user_id", {"date": today}))

    return {
        "ai_requests_today": total_ai_today,
        "total_builds": total_builds,
        "total_projects": total_projects,
        "active_developers_today": active_devs,
    }


# ── Admin Subscription Audit ──


@router.get("/admin/subscription/audit")
async def admin_subscription_audit(request: Request):
    """Admin: Audit users with potential subscription anomalies."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from routes.subscription_enforcement import _is_payment_exempt, check_and_expire_subscriptions

    # Run expiry check
    expired_count = await check_and_expire_subscriptions()

    # Find users with paid plans but no payment_verified flag
    unverified = []
    cursor = db.users.find(
        {"subscription_plan": {"$in": ["basic", "premium"]}, "payment_verified": {"$ne": True}},
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
        },
    )
    async for u in cursor:
        if not _is_payment_exempt(u.get("email", "")):
            if "subscription_end_date" in u and hasattr(u["subscription_end_date"], "isoformat"):
                u["subscription_end_date"] = u["subscription_end_date"].isoformat()
            unverified.append(u)

    # Get audit log
    audit_cursor = db.subscription_audit_log.find({}, {"_id": 0}).sort("timestamp", -1).limit(20)
    audit_log = []
    async for entry in audit_cursor:
        if "timestamp" in entry and hasattr(entry["timestamp"], "isoformat"):
            entry["timestamp"] = entry["timestamp"].isoformat()
        audit_log.append(entry)

    # Stats
    total_paid = await db.users.count_documents({"subscription_plan": {"$in": ["basic", "premium"]}})
    total_verified = await db.users.count_documents(
        {"subscription_plan": {"$in": ["basic", "premium"]}, "payment_verified": True}
    )

    return {
        "total_paid_users": total_paid,
        "total_verified": total_verified,
        "unverified_count": len(unverified),
        "unverified_users": unverified,
        "expired_downgraded": expired_count,
        "recent_audit_log": audit_log,
    }


@router.post("/admin/subscription/force-downgrade")
async def admin_force_downgrade(request: Request):
    """Admin: Force downgrade all unverified paid users to free."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from routes.subscription_enforcement import _is_payment_exempt, _downgrade_user

    cursor = db.users.find(
        {"subscription_plan": {"$in": ["basic", "premium"]}, "payment_verified": {"$ne": True}},
        {"_id": 0, "user_id": 1, "email": 1},
    )
    count = 0
    async for u in cursor:
        if not _is_payment_exempt(u.get("email", "")):
            await _downgrade_user(u["user_id"])
            count += 1

    return {"downgraded_count": count, "message": f"Downgraded {count} unverified users to free plan"}


# ── AI Access Status & Tier Comparison ──
@router.get("/ai-access/status")
async def ai_access_status(request: Request):
    """Get current user's AI usage status and limits."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    effective_tier = _resolve_tier(user)
    plan = "admin" if user.is_admin or getattr(user, "full_access", False) else effective_tier

    plan_doc = await get_subscription_plan_from_gps(plan, default_plan_id="free") or {}
    if plan in ("admin", "enterprise"):
        daily_limit = 9999
    else:
        entitlement_daily_limit = get_feature_value(effective_tier, "coaching_team_daily_messages")
        if isinstance(entitlement_daily_limit, int):
            daily_limit = entitlement_daily_limit
        else:
            daily_limit = int(plan_doc.get("daily_conversation_limit", 3) or 3)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
    daily_usage = await db.usage_analytics.count_documents(
        {
            "user_id": user.user_id,
            "timestamp": {"$gte": today_start},
        }
    )

    plan_key = plan if plan_doc else "free"
    upgrade_options = []
    if plan not in ("admin", "enterprise"):
        gps_plans = await get_subscription_plans_from_gps()
        plan_order = list(gps_plans.keys())
        current_idx = plan_order.index(plan_key) if plan_key in plan_order else 0
        for up in plan_order[current_idx + 1 :]:
            info = gps_plans.get(up, {})
            if info:
                upgrade_options.append(
                    {
                        "id": up,
                        "name": info.get("name", up.title()),
                        "price": f"${info.get('monthly_price', 0)}/mo",
                        "daily_limit": info.get("daily_conversation_limit", -1),
                    }
                )

    plan_name = "Admin (Unlimited)" if plan in ("admin", "enterprise") else plan_doc.get("name", plan_key.title())

    return {
        "plan": effective_tier if plan not in ("admin", "enterprise") else plan,
        "plan_name": plan_name,
        "usage": {
            "daily": daily_usage,
            "daily_limit": daily_limit,
            "daily_unlimited": daily_limit >= 9999 or daily_limit < 0,
        },
        "upgrade_options": upgrade_options,
    }


@router.get("/ai-access/tier-comparison")
async def ai_access_tier_comparison(request: Request):
    """Get tier comparison data for the upgrade modal."""
    gps_plans = await get_subscription_plans_from_gps()
    return {"tiers": gps_plans}


# ── Usage Tracking Helpers ──


async def _get_daily_usage(user_id: str, feature: str) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = await db.dev_usage_logs.count_documents(
        {
            "user_id": user_id,
            "feature": feature,
            "date": today,
        }
    )
    return count


async def _get_project_count(user_id: str) -> int:
    return await db.dev_projects.count_documents(
        {
            "user_id": user_id,
            "status": {"$ne": "deleted"},
        }
    )


async def _log_usage(user_id: str, feature: str):
    await db.dev_usage_logs.insert_one(
        {
            "user_id": user_id,
            "feature": feature,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "timestamp": datetime.now(timezone.utc),
        }
    )
