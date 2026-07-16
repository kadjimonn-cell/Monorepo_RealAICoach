from fastapi import APIRouter, HTTPException, Request, Response
import re
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Literal
import uuid
import logging

from .db import db, require_admin
from utils.access_control_engine import compute_effective_plan

router = APIRouter()
logger = logging.getLogger(__name__)


def _effective_plan_from_user_doc(user_doc: dict | None) -> str:
    row = user_doc or {}
    return compute_effective_plan(
        {
            "subscription_plan": row.get("subscription_plan", "free"),
            "subscription_status": row.get("subscription_status", "active"),
            "subscription_end_date": row.get("subscription_end") or row.get("subscription_end_date") or row.get("subscription_expires_at"),
            "subscription_permanent": row.get("subscription_permanent", False),
            "payment_verified": row.get("payment_verified", False),
            "pending_subscription_transition": row.get("pending_subscription_transition"),
            "is_admin": row.get("is_admin", False),
            "full_access": row.get("full_access", False),
        }
    )

TEST_ALIAS_KEYWORDS = {
    "test",
    "qa",
    "e2e",
    "sandbox",
    "staging",
    "newhire",
    "humantest",
    "smoke",
    "demo",
    "dryrun",
    "automation",
    "seed",
}


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    subscription_plan: Optional[str] = None
    subscription_status: Optional[str] = None
    suspended: Optional[bool] = None


class PlanUpdateRequest(BaseModel):
    plan_id: str
    name: Optional[str] = None
    monthly_price: Optional[float] = None
    yearly_price: Optional[float] = None
    features: Optional[List[str]] = None
    active: Optional[bool] = None


class AnnouncementRequest(BaseModel):
    title: str
    message: str
    priority: str = "normal"
    audience: str = "all"


class FeatureFlagRequest(BaseModel):
    key: str
    enabled: bool
    description: Optional[str] = None


class ContentPageRequest(BaseModel):
    title: str
    slug: str
    status: str = "draft"
    body: str = ""


class GlobalAliasHygieneRunRequest(BaseModel):
    apply: bool = True
    limit: int = 5000
    disable_login: bool = True
    enforce_email_blocklist: bool = True


class AliasTelemetryHitRequest(BaseModel):
    console: Literal["executive", "operations"]
    source_tab_id: str
    canonical_tab_id: str
    context: str = ""


async def log_admin_event(user_id: str, action: str, metadata: dict | None = None, request: Request | None = None):
    payload = metadata.copy() if metadata else {}
    if request:
        payload.update(
            {
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
                "path": request.url.path,
                "method": request.method,
            }
        )
    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"log_{uuid.uuid4().hex[:10]}",
            "user_id": user_id,
            "action": action,
            "metadata": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _split_alias_email(email: str) -> tuple[str, str, str]:
    value = str(email or "").strip().lower()
    if "@" not in value:
        return value, "", ""
    local, domain = value.split("@", 1)
    if "+" not in local:
        return local, "", domain
    base_local, alias_tag = local.split("+", 1)
    return base_local, alias_tag, domain


def _is_obsolete_test_alias(alias_tag: str) -> bool:
    tag = str(alias_tag or "").strip().lower()
    if not tag:
        return False
    for keyword in TEST_ALIAS_KEYWORDS:
        if keyword in tag:
            return True
    return False


async def _collect_global_test_alias_candidates(limit: int = 5000) -> list[dict]:
    docs = await db.users.find(
        {
            "email": {"$regex": r"\+", "$options": "i"},
            "is_admin": {"$ne": True},
        },
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "name": 1,
            "created_at": 1,
            "is_active": 1,
            "email_verified": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
        },
    ).limit(max(1, min(int(limit or 5000), 20000))).to_list(max(1, min(int(limit or 5000), 20000)))

    candidates: list[dict] = []
    for doc in docs:
        email = str(doc.get("email") or "").strip().lower()
        base_local, alias_tag, domain = _split_alias_email(email)
        if not alias_tag:
            continue
        if not _is_obsolete_test_alias(alias_tag):
            continue

        base_email = f"{base_local}@{domain}" if base_local and domain else ""
        if not base_email:
            continue

        primary = await db.users.find_one(
            {"email": base_email},
            {
                "_id": 0,
                "user_id": 1,
                "email": 1,
                "name": 1,
                "is_active": 1,
                "email_verified": 1,
            },
        )
        if not primary:
            continue
        if str(primary.get("user_id") or "") == str(doc.get("user_id") or ""):
            continue

        candidates.append(
            {
                "alias_user_id": doc.get("user_id"),
                "alias_email": email,
                "alias_tag": alias_tag,
                "alias_active": doc.get("is_active", True),
                "alias_email_verified": doc.get("email_verified", False),
                "alias_created_at": doc.get("created_at"),
                "primary_user_id": primary.get("user_id"),
                "primary_email": primary.get("email"),
                "primary_active": primary.get("is_active", True),
                "primary_email_verified": primary.get("email_verified", False),
            }
        )

    return candidates


@router.get("/admin/overview")
async def admin_overview(req: Request):
    user = await require_admin(req)
    user_counts = await db.users.aggregate(
        [
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "premium": {"$sum": {"$cond": [{"$eq": ["$subscription_plan", "premium"]}, 1, 0]}},
                    "basic": {"$sum": {"$cond": [{"$eq": ["$subscription_plan", "basic"]}, 1, 0]}},
                    "free": {"$sum": {"$cond": [{"$eq": ["$subscription_plan", "free"]}, 1, 0]}},
                    "suspended": {"$sum": {"$cond": [{"$eq": ["$suspended", True]}, 1, 0]}},
                }
            }
        ]
    ).to_list(1)
    user_count_doc = user_counts[0] if user_counts else {}
    total_users = int(user_count_doc.get("total", 0) or 0)
    premium_users = int(user_count_doc.get("premium", 0) or 0)
    basic_users = int(user_count_doc.get("basic", 0) or 0)
    free_users = int(user_count_doc.get("free", 0) or 0)
    suspended_users = int(user_count_doc.get("suspended", 0) or 0)

    payments = await db.payments.aggregate(
        [{"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}]
    ).to_list(1)
    revenue = payments[0]["total"] if payments else 0
    payment_count = payments[0]["count"] if payments else 0

    await log_admin_event(user.user_id, "view_admin_overview")

    return {
        "users": {
            "total": total_users,
            "premium": premium_users,
            "basic": basic_users,
            "free": free_users,
            "suspended": suspended_users,
        },
        "billing": {
            "total_revenue": round(revenue, 2),
            "transactions": payment_count,
        },
    }


@router.get("/admin/console/overview")
async def admin_console_overview_alias(req: Request):
    """Compatibility alias for legacy /api/admin/console/overview checks."""
    return await admin_overview(req)


@router.get("/admin/users")
async def admin_users(req: Request, q: Optional[str] = None, plan: Optional[str] = None):
    user = await require_admin(req)
    query = {}
    if plan:
        query["subscription_plan"] = plan
    if q:
        query["$or"] = [
            {"email": {"$regex": re.escape(str(q)), "$options": "i"}},
            {"name": {"$regex": re.escape(str(q)), "$options": "i"}},
        ]
    users = await db.users.find(query, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    await log_admin_event(user.user_id, "list_users", {"query": q, "plan": plan})
    return {"users": users, "total": len(users)}


@router.put("/admin/users/{user_id}")
async def update_user(user_id: str, request: UserUpdateRequest, req: Request):
    admin = await require_admin(req)
    payload = {k: v for k, v in request.dict().items() if v is not None}
    payload["updated_at"] = datetime.now(timezone.utc)
    result = await db.users.update_one({"user_id": user_id}, {"$set": payload})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await log_admin_event(admin.user_id, "update_user", {"user_id": user_id, **payload})
    return {"success": True}


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, req: Request):
    admin = await require_admin(req)
    await db.users.delete_one({"user_id": user_id})
    await log_admin_event(admin.user_id, "delete_user", {"user_id": user_id})
    return {"success": True}


@router.get("/admin/subscriptions/plans")
async def get_subscription_plans(req: Request, response: Response):
    await require_admin(req)
    from routes.payments_catalog import get_subscription_plan_catalog

    plans = await get_subscription_plan_catalog()
    response.headers["X-Endpoint-Scope"] = "admin-only"
    response.headers["X-Replacement-Endpoint"] = "/api/subscriptions/plans"
    response.headers["X-User-Path-Policy"] = "forbidden"
    return {"plans": plans}


@router.post("/admin/subscriptions/plans")
async def update_subscription_plan(request: PlanUpdateRequest, req: Request):
    admin = await require_admin(req)
    payload = {k: v for k, v in request.dict().items() if v is not None}
    payload["plan_id"] = request.plan_id
    await db.subscription_plans.update_one({"plan_id": request.plan_id}, {"$set": payload}, upsert=True)
    await log_admin_event(admin.user_id, "update_plan", {"plan_id": request.plan_id})
    try:
        from routes.global_platform_state import sync_global_plans
        await sync_global_plans(reason="Plan changed in admin console", actor_user_id=admin.user_id)
    except Exception:
        pass
    return {"success": True}


@router.get("/admin/billing/overview")
async def billing_overview(req: Request):
    await require_admin(req)
    payments = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    total_revenue = sum([p.get("amount", 0) for p in payments])
    active_subs = await db.users.count_documents(
        {"subscription_status": "active", "subscription_plan": {"$in": ["basic", "premium"]}}
    )
    return {
        "total_revenue": round(total_revenue, 2),
        "transactions": len(payments),
        "active_subscriptions": active_subs,
    }


@router.get("/admin/billing/transactions")
async def billing_transactions(req: Request):
    await require_admin(req)
    payments = await db.payments.find({}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    transactions = await db.payment_transactions.find({}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"payments": payments, "transactions": transactions}


@router.get("/admin/ai/monitor")
async def ai_monitor(req: Request):
    await require_admin(req)
    monitor_rows = await db.llm_search_logs.aggregate(
        [
            {"$count": "count"},
            {"$addFields": {"metric": "search_logs"}},
            {"$project": {"_id": 0, "metric": 1, "count": 1}},
            {
                "$unionWith": {
                    "coll": "media_playback_events",
                    "pipeline": [
                        {"$count": "count"},
                        {"$addFields": {"metric": "playback_events"}},
                        {"$project": {"_id": 0, "metric": 1, "count": 1}},
                    ],
                }
            },
            {
                "$unionWith": {
                    "coll": "conversations",
                    "pipeline": [
                        {"$count": "count"},
                        {"$addFields": {"metric": "conversations"}},
                        {"$project": {"_id": 0, "metric": 1, "count": 1}},
                    ],
                }
            },
        ]
    ).to_list(10)
    metric_counts = {str(row.get("metric") or ""): int(row.get("count") or 0) for row in monitor_rows}
    search_logs = metric_counts.get("search_logs", 0)
    playback_events = metric_counts.get("playback_events", 0)
    conversations = metric_counts.get("conversations", 0)
    return {
        "search_logs": search_logs,
        "playback_events": playback_events,
        "conversations": conversations,
    }


@router.get("/admin/analytics")
async def admin_analytics(req: Request):
    await require_admin(req)
    pipeline = [
        {
            "$group": {
                "_id": None,
                "total_watch_seconds": {"$sum": "$position_seconds"},
                "unique_viewers": {"$addToSet": "$user_id"},
            }
        },
        {"$addFields": {"viewer_count": {"$size": "$unique_viewers"}}},
    ]
    stats = await db.media_resume.aggregate(pipeline).to_list(1)
    result = stats[0] if stats else {"total_watch_seconds": 0, "viewer_count": 0}
    return {
        "total_watch_seconds": result.get("total_watch_seconds", 0),
        "unique_viewers": result.get("viewer_count", 0),
    }


@router.get("/admin/announcements")
async def get_announcements(req: Request):
    await require_admin(req)
    items = await db.admin_announcements.find({}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    return {"announcements": items}


@router.post("/admin/announcements")
async def create_announcement(request: AnnouncementRequest, req: Request):
    admin = await require_admin(req)
    doc = {
        "id": f"ann_{uuid.uuid4().hex[:8]}",
        **request.dict(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin.email,
    }
    await db.admin_announcements.insert_one(doc)
    await log_admin_event(admin.user_id, "create_announcement", {"id": doc["id"]})
    announcement = {k: v for k, v in doc.items() if k != "_id"}
    return {"success": True, "announcement": announcement}


@router.delete("/admin/announcements/{announcement_id}")
async def delete_announcement(announcement_id: str, req: Request):
    admin = await require_admin(req)
    await db.admin_announcements.delete_one({"id": announcement_id})
    await log_admin_event(admin.user_id, "delete_announcement", {"id": announcement_id})
    return {"success": True}


@router.get("/admin/feature-flags")
async def get_feature_flags(req: Request):
    await require_admin(req)
    flags = await db.feature_flags.find({}, {"_id": 0}).to_list(200)
    return {"flags": flags}


@router.post("/admin/feature-flags")
async def upsert_feature_flag(request: FeatureFlagRequest, req: Request):
    admin = await require_admin(req)
    payload = request.dict()
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.feature_flags.update_one({"key": request.key}, {"$set": payload}, upsert=True)
    await log_admin_event(admin.user_id, "update_feature_flag", {"key": request.key, "enabled": request.enabled})
    return {"success": True}


@router.get("/admin/access-logs")
async def get_access_logs(req: Request):
    await require_admin(req)
    logs = await db.admin_audit_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"logs": logs}


@router.get("/admin/content/pages")
async def get_content_pages(req: Request):
    await require_admin(req)
    pages = await db.admin_content_pages.find({}, {"_id": 0}).sort("updated_at", -1).limit(200).to_list(200)
    return {"pages": pages}


@router.post("/admin/content/pages")
async def upsert_content_page(request: ContentPageRequest, req: Request):
    admin = await require_admin(req)
    payload = request.dict()
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.admin_content_pages.update_one({"slug": request.slug}, {"$set": payload}, upsert=True)
    await log_admin_event(admin.user_id, "update_content_page", {"slug": request.slug})
    return {"success": True}


@router.delete("/admin/content/pages/{slug}")
async def delete_content_page(slug: str, req: Request):
    admin = await require_admin(req)
    await db.admin_content_pages.delete_one({"slug": slug})
    await log_admin_event(admin.user_id, "delete_content_page", {"slug": slug})
    return {"success": True}


@router.get("/admin/content/media")
async def get_media_catalog(req: Request):
    await require_admin(req)
    videos = (
        await db.video_catalog.find({"source_type": "internal"}, {"_id": 0})
        .sort("added_date", -1)
        .limit(200)
        .to_list(200)
    )
    return {"media": videos, "total": len(videos)}


@router.get("/admin/analytics/retention")
async def admin_retention_heatmap(req: Request, days: int = 30):
    """Return daily active users (DAU) for the last N days, from user_sessions."""
    await require_admin(req)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Build a day-keyed dict with zero values for all days
    day_map: dict[str, set] = {}
    for i in range(days):
        day = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        day_map[day] = set()

    # Aggregate unique user logins per day from user_sessions
    sessions = await db.user_sessions.find(
        {"created_at": {"$gte": start_date}}, {"_id": 0, "user_id": 1, "created_at": 1}
    ).to_list(10000)

    for sess in sessions:
        created = sess.get("created_at")
        if not created:
            continue
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                continue
        day_key = created.strftime("%Y-%m-%d")
        if day_key in day_map:
            day_map[day_key].add(sess.get("user_id", ""))

    # Also aggregate from usage_analytics for richer activity signal
    activities = await db.usage_analytics.find(
        {"timestamp": {"$gte": start_date.isoformat()}}, {"_id": 0, "user_id": 1, "timestamp": 1}
    ).to_list(10000)

    for act in activities:
        ts = act.get("timestamp")
        if not ts:
            continue
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
        else:
            dt = ts
        day_key = dt.strftime("%Y-%m-%d")
        if day_key in day_map:
            day_map[day_key].add(act.get("user_id", ""))

    retention = [{"date": d, "dau": len(users)} for d, users in sorted(day_map.items())]
    max_dau = max((r["dau"] for r in retention), default=1)

    # Also compute weekly averages
    weeks = []
    for w in range(0, days, 7):
        week_data = retention[w : w + 7]
        avg = sum(r["dau"] for r in week_data) / max(len(week_data), 1)
        weeks.append({"week": w // 7 + 1, "avg_dau": round(avg, 1)})

    return {"retention": retention, "max_dau": max(max_dau, 1), "weekly_averages": weeks, "period_days": days}


@router.get("/admin/analytics/churn")
async def admin_churn_analysis(req: Request):
    """Return churn risk for all users based on last login date."""
    await require_admin(req)
    now = datetime.now(timezone.utc)

    # Get last login per user from user_sessions
    pipeline = [
        {"$group": {"_id": "$user_id", "last_login": {"$max": "$created_at"}}},
    ]
    sessions = await db.user_sessions.aggregate(pipeline).to_list(10000)
    last_login_map: dict[str, int] = {}
    for s in sessions:
        uid = s["_id"]
        last_dt = s["last_login"]
        if isinstance(last_dt, str):
            try:
                last_dt = datetime.fromisoformat(last_dt.replace("Z", "+00:00"))
            except Exception:
                continue
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        days_ago = (now - last_dt).days
        last_login_map[uid] = days_ago

    def risk_level(uid: str) -> str:
        days = last_login_map.get(uid)
        if days is None:
            return "never"
        if days < 7:
            return "low"
        if days < 15:
            return "medium"
        return "high"

    users = await db.users.find({}, {"_id": 0, "user_id": 1}).to_list(10000)
    churn = []
    for u in users:
        uid = u.get("user_id", "")
        days = last_login_map.get(uid)
        churn.append(
            {
                "user_id": uid,
                "risk": risk_level(uid),
                "days_since_login": days,
            }
        )

    high_risk = [c for c in churn if c["risk"] == "high"]
    medium_risk = [c for c in churn if c["risk"] == "medium"]
    return {"churn": churn, "high_risk_count": len(high_risk), "medium_risk_count": len(medium_risk)}


@router.get("/admin/analytics/feature-quality")
async def feature_quality_monitor(req: Request):
    """Aggregate AI feedback ratings per feature. Flag features with <70% thumbs-up."""
    await require_admin(req)

    all_feedback = (
        await db.ai_feedback.find(
            {}, {"_id": 0, "feature_key": 1, "feature": 1, "rating": 1, "comment": 1, "created_at": 1, "user_id": 1}
        )
        .sort("created_at", -1)
        .to_list(5000)
    )

    feature_stats: dict[str, dict] = {}

    for fb in all_feedback:
        # Support both old (feature_key, rating 1/-1/0) and new (feature, rating 'up'/'down') formats
        feature = fb.get("feature") or fb.get("feature_key") or "unknown"
        raw_rating = fb.get("rating")

        # Normalize to bool: positive = thumbs up
        if isinstance(raw_rating, str):
            positive = raw_rating == "up"
        elif isinstance(raw_rating, (int, float)):
            positive = raw_rating > 0
        else:
            continue

        if feature not in feature_stats:
            feature_stats[feature] = {"total": 0, "positive": 0, "negative": 0, "comments": [], "feature": feature}

        feature_stats[feature]["total"] += 1
        if positive:
            feature_stats[feature]["positive"] += 1
        else:
            feature_stats[feature]["negative"] += 1
            if fb.get("comment"):
                feature_stats[feature]["comments"].append(
                    {
                        "comment": fb["comment"],
                        "created_at": fb.get("created_at", ""),
                    }
                )

    results = []
    for feat, stats in feature_stats.items():
        pct = round(stats["positive"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
        results.append(
            {
                "feature": feat,
                "total": stats["total"],
                "positive": stats["positive"],
                "negative": stats["negative"],
                "thumbs_up_pct": pct,
                "flagged": pct < 70 and stats["total"] >= 3,
                "recent_complaints": stats["comments"][:5],
            }
        )

    # Sort: flagged first, then by total descending
    results.sort(key=lambda x: (-int(x["flagged"]), -x["total"]))

    # Recent reports (most recent 10 negative feedback with comments)
    recent_reports = []
    for fb in all_feedback:
        raw_rating = fb.get("rating")
        if isinstance(raw_rating, str):
            positive = raw_rating == "up"
        elif isinstance(raw_rating, (int, float)):
            positive = raw_rating > 0
        else:
            continue
        if not positive and fb.get("comment"):
            feature = fb.get("feature") or fb.get("feature_key") or "unknown"
            recent_reports.append(
                {
                    "feature": feature,
                    "comment": fb["comment"],
                    "user_id": fb.get("user_id", ""),
                    "created_at": fb.get("created_at", ""),
                }
            )
        if len(recent_reports) >= 10:
            break

    flagged_count = sum(1 for r in results if r["flagged"])
    total_ratings = sum(r["total"] for r in results)
    overall_positive = sum(r["positive"] for r in results)
    overall_pct = round(overall_positive / total_ratings * 100, 1) if total_ratings > 0 else 0

    return {
        "features": results,
        "recent_reports": recent_reports,
        "summary": {
            "total_ratings": total_ratings,
            "overall_thumbs_up_pct": overall_pct,
            "flagged_features": flagged_count,
            "total_features_rated": len(results),
        },
    }


@router.get("/admin/analytics/alert-settings")
async def get_alert_settings(req: Request):
    """Get quality alert settings."""
    await require_admin(req)
    settings = await db.quality_alert_settings.find_one({}, {"_id": 0}) or {
        "enabled": True,
        "threshold": 70,
        "alert_email": "admin@realaicoach.app",
    }
    # Get last 5 sent alerts
    alerts = await db.quality_alerts.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    return {"settings": settings, "recent_alerts": alerts}


@router.post("/admin/analytics/alert-settings")
async def update_alert_settings(req: Request):
    """Update quality alert settings."""
    admin = await require_admin(req)
    body = await req.json()
    payload = {
        "enabled": bool(body.get("enabled", True)),
        "threshold": max(1, min(100, int(body.get("threshold", 70)))),
        "alert_email": body.get("alert_email", "admin@realaicoach.app"),
        "updated_by": admin.email,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.quality_alert_settings.update_one({}, {"$set": payload}, upsert=True)
    await log_admin_event(admin.user_id, "update_alert_settings", payload)
    return {"success": True, "settings": payload}


async def _gather_admin_notification_history(days: int = 7) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    notifications = []

    sec_events = (
        await db.security_events.find(
            {"timestamp": {"$gte": since.isoformat()}, "risk_level": {"$in": ["high", "medium"]}}, {"_id": 0}
        )
        .sort("timestamp", -1)
        .limit(50)
        .to_list(50)
    )
    for ev in sec_events:
        notifications.append({
            "id": ev.get("event_id", ""),
            "type": "security",
            "severity": "critical" if ev.get("risk_level") == "high" else "warning",
            "title": f"Security: {ev.get('event_type', 'unknown').replace('_', ' ').title()}",
            "message": f"IP: {ev.get('ip_address', 'N/A')} | Risk: {ev.get('risk_level', 'unknown')}",
            "timestamp": ev.get("timestamp", ""),
            "read": False,
            "source": "security_events",
            "delivery_status": "delivered",
        })

    new_users = (
        await db.users.find(
            {"created_at": {"$gte": since.isoformat()}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .limit(40)
        .to_list(40)
    )
    for u in new_users:
        notifications.append({
            "id": f"signup_{u.get('user_id', '')}",
            "type": "signup",
            "severity": "info",
            "title": "New User Signup",
            "message": f"{u.get('name', 'User')} ({u.get('email', '')})",
            "timestamp": u.get("created_at", ""),
            "read": False,
            "source": "users",
            "delivery_status": "delivered",
        })

    failed_payments = (
        await db.payments.find(
            {"created_at": {"$gte": since.isoformat()}, "status": {"$in": ["failed", "error", "declined"]}}, {"_id": 0}
        )
        .sort("created_at", -1)
        .limit(40)
        .to_list(40)
    )
    for p in failed_payments:
        notifications.append({
            "id": p.get("payment_id", p.get("id", "")),
            "type": "payment_failure",
            "severity": "critical",
            "title": "Payment Failed",
            "message": f"Plan: {p.get('plan_id', 'unknown')} | ${p.get('amount', 0)}",
            "timestamp": p.get("created_at", ""),
            "read": False,
            "source": "payments",
            "delivery_status": "delivered",
        })

    expiry_window = datetime.now(timezone.utc) + timedelta(days=3)
    expiring = (
        await db.users.find(
            {
                "subscription_end": {"$lte": expiry_window.isoformat(), "$gte": datetime.now(timezone.utc).isoformat()},
                "subscription_plan": {"$ne": "free"},
            },
            {"_id": 0, "user_id": 1, "email": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end": 1, "subscription_end_date": 1, "subscription_expires_at": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
        )
        .limit(20)
        .to_list(20)
    )
    for u in expiring:
        notifications.append({
            "id": f"expiry_{u.get('user_id', '')}",
            "type": "subscription_expiry",
            "severity": "warning",
            "title": "Subscription Expiring",
            "message": f"{u.get('email', '')} — {_effective_plan_from_user_doc(u)} expires soon",
            "timestamp": u.get("subscription_end", ""),
            "read": False,
            "source": "users",
            "delivery_status": "delivered",
        })

    push_notifs = await db.admin_push_notifications.find(
        {"timestamp": {"$gte": since.isoformat()}},
        {"_id": 0}
    ).sort("timestamp", -1).limit(80).to_list(80)
    for pn in push_notifs:
        notifications.append({
            "id": f"push_{pn.get('type', '')}_{pn.get('timestamp', '')}",
            "type": pn.get("type", "system"),
            "severity": pn.get("severity", "info"),
            "title": pn.get("title", "Alert"),
            "message": pn.get("message", ""),
            "timestamp": pn.get("timestamp", ""),
            "read": pn.get("read", False),
            "source": "admin_push_notifications",
            "delivery_status": pn.get("status", "delivered"),
        })

    notifications.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return notifications


@router.get("/admin/notifications/live")
async def admin_live_notifications(req: Request, limit: int = 20):
    """Get recent admin notifications aggregated from security events, new signups, and payment failures."""
    await require_admin(req)
    notifications = (await _gather_admin_notification_history(days=1))[:limit]

    # Count by type
    counts = {
        "total": len(notifications),
        "security": sum(1 for n in notifications if n["type"] in ("security", "security_alert")),
        "signups": sum(1 for n in notifications if n["type"] in ("signup", "new_signup")),
        "payment_failures": sum(1 for n in notifications if n["type"] in ("payment_failure", "payment_success")),
        "expiring": sum(1 for n in notifications if n["type"] == "subscription_expiry"),
        "system": sum(1 for n in notifications if n["type"] in ("error_spike", "slow_api", "ticket_surge", "session_spike")),
    }

    return {"notifications": notifications[:limit], "counts": counts}


@router.get("/admin/notifications/history")
async def admin_notification_history(req: Request, limit: int = 80, days: int = 7, type_filter: str = "all", severity_filter: str = "all"):
    """Dedicated admin notification history feed with filterable analytics."""
    await require_admin(req)
    rows = await _gather_admin_notification_history(days=max(1, min(days, 30)))

    filtered = rows
    if type_filter != "all":
        filtered = [row for row in filtered if str(row.get("type") or "") == type_filter]
    if severity_filter != "all":
        filtered = [row for row in filtered if str(row.get("severity") or "") == severity_filter]

    severity_counts = {
        "critical": sum(1 for row in rows if row.get("severity") == "critical"),
        "warning": sum(1 for row in rows if row.get("severity") == "warning"),
        "info": sum(1 for row in rows if row.get("severity") == "info"),
    }
    type_counts = {}
    for row in rows:
        key = str(row.get("type") or "unknown")
        type_counts[key] = type_counts.get(key, 0) + 1

    return {
        "summary": {
            "total": len(rows),
            "critical": severity_counts["critical"],
            "warning": severity_counts["warning"],
            "info": severity_counts["info"],
            "types": type_counts,
        },
        "filters": {
            "type_filter": type_filter,
            "severity_filter": severity_filter,
            "days": days,
        },
        "notifications": filtered[:limit],
    }


@router.post("/admin/notifications/broadcast")
async def admin_broadcast_notification(req: Request):
    """Admin: Send a notification to all active users."""
    await require_admin(req)
    body = await req.json()
    title = body.get("title", "")
    msg_body = body.get("body", "")
    if not title or not msg_body:
        raise HTTPException(status_code=400, detail="Title and body are required")

    # Get all active users
    users = await db.users.find({"access_locked": {"$ne": True}}, {"_id": 0, "user_id": 1}).to_list(1000)

    sent = 0
    try:
        from routes.notification_engine import emit_notification

        for u in users:
            await emit_notification(
                user_id=u["user_id"],
                notif_type="admin_broadcast",
                title=title,
                body=msg_body,
                action_url="/notifications",
            )
            sent += 1

        # Also send email broadcast using platform_announcement template
        from utils.email_service import send_catalog_template, is_email_configured
        if is_email_configured():
            email_users = await db.users.find(
                {"access_locked": {"$ne": True}, "email": {"$exists": True, "$ne": ""}},
                {"_id": 0, "email": 1, "name": 1},
            ).to_list(1000)
            for eu in email_users:
                try:
                    await send_catalog_template(
                        recipient_email=eu["email"],
                        template_key="platform_announcement",
                        recipient_name=eu.get("name", ""),
                        user_name=eu.get("name", "there"),
                        title=title,
                        message=msg_body,
                        category_label=body.get("category", "announcement"),
                        cta_label=body.get("cta_label", ""),
                        cta_url=body.get("cta_url", ""),
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Broadcast failed after {sent} notifications: {e}")

    return {"success": True, "sent_to": sent, "total_users": len(users)}


@router.post("/admin/notifications/test-push")
async def test_push_notification(req: Request):
    """Test push notification — sends a test toast alert to the current admin."""
    await require_admin(req)
    body = await req.json() if req.headers.get("content-type", "").startswith("application/json") else {}
    severity = body.get("severity", "info")
    title = body.get("title", "Test Notification")
    message = body.get("message", "This is a test push notification from the admin console.")

    try:
        from routes.admin_push_notifications import emit_realtime_alert
        await emit_realtime_alert(f"test_{severity}", severity, title, message)
        return {"success": True, "severity": severity, "message": "Push notification sent"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/admin/legal-notice/broadcast-legacy-v1-disabled")
async def admin_legal_notice_broadcast_legacy(req: Request):
    """DEPRECATED: this v1 endpoint is retained only as a 410 Gone marker.
    The active endpoint lives in routes/admin_broadcast.py with the
    dry-run + type-SEND + rate-limit safety rails required for
    irreversible broadcasts. Kept here so existing clients (if any)
    fail loud instead of silently hitting the old path."""
    await require_admin(req)
    raise HTTPException(
        status_code=410,
        detail=(
            "This endpoint has been replaced. Use POST /api/admin/legal-notice/broadcast "
            "(v2) which requires dry_run=true first, then confirm_phrase=SEND for a "
            "real send. See LegalNoticeBroadcastPanel in the Admin Console."
        ),
    )


@router.get("/admin/legal-notice/history")
async def admin_legal_notice_history(req: Request):
    """Admin: View history of all legal notice broadcasts."""
    await require_admin(req)
    history = await db.legal_notice_broadcasts.find({}, {"_id": 0}).sort("sent_at", -1).limit(50).to_list(50)
    return {"broadcasts": history}


@router.get("/admin/data-hygiene/test-alias-accounts/preview")
async def admin_test_alias_hygiene_preview(req: Request, limit: int = 5000):
    admin = await require_admin(req)
    candidates = await _collect_global_test_alias_candidates(limit=limit)
    await log_admin_event(
        admin.user_id,
        "preview_test_alias_hygiene",
        {
            "candidate_count": len(candidates),
            "limit": int(limit),
        },
        req,
    )
    return {
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


@router.post("/admin/data-hygiene/test-alias-accounts/run")
async def admin_test_alias_hygiene_run(req: Request, body: GlobalAliasHygieneRunRequest):
    admin = await require_admin(req)
    candidates = await _collect_global_test_alias_candidates(limit=body.limit)

    if not body.apply:
        await log_admin_event(
            admin.user_id,
            "run_test_alias_hygiene_dry",
            {
                "candidate_count": len(candidates),
                "limit": body.limit,
            },
            req,
        )
        return {
            "mode": "dry_run",
            "candidate_count": len(candidates),
            "candidates": candidates,
        }

    from utils.email_service import canonicalize_recipient_email

    now_iso = datetime.now(timezone.utc).isoformat()
    updated_users = 0
    blocklisted = 0
    sessions_revoked = 0

    for c in candidates:
        alias_user_id = str(c.get("alias_user_id") or "").strip()
        alias_email = str(c.get("alias_email") or "").strip().lower()
        primary_user_id = str(c.get("primary_user_id") or "").strip()
        if not alias_user_id or not alias_email or not primary_user_id:
            continue

        user_updates = {
            "is_active": False,
            "allow_login": False,
            "hygiene_obsolete_alias": True,
            "hygiene_obsolete_alias_tag": c.get("alias_tag"),
            "hygiene_obsolete_alias_disabled_at": now_iso,
            "hygiene_obsolete_alias_disabled_by": admin.user_id,
            "merged_into_user_id": primary_user_id,
            "email_notifications_opt_out": True,
            "updated_at": now_iso,
        }
        res = await db.users.update_one({"user_id": alias_user_id}, {"$set": user_updates})
        if res.modified_count:
            updated_users += 1

        await db.notification_settings.update_one(
            {"user_id": alias_user_id},
            {
                "$set": {
                    "user_id": alias_user_id,
                    "email_enabled": False,
                    "daily_briefing": False,
                    "updated_at": now_iso,
                    "updated_by": admin.user_id,
                    "hygiene_obsolete_alias": True,
                }
            },
            upsert=True,
        )

        if body.disable_login:
            session_res = await db.user_sessions.update_many(
                {"user_id": alias_user_id, "is_active": True},
                {"$set": {"is_active": False, "revoked_at": now_iso, "revoked_reason": "obsolete_test_alias_hygiene"}},
            )
            sessions_revoked += int(session_res.modified_count or 0)

        if body.enforce_email_blocklist:
            canon = canonicalize_recipient_email(alias_email)
            await db.email_recipient_blocklist.update_one(
                {"recipient_email": alias_email},
                {
                    "$set": {
                        "recipient_email": alias_email,
                        "canonical_recipient": canon,
                        "active": True,
                        "apply_to_canonical": False,
                        "reason": "obsolete_test_alias_hygiene",
                        "source": "admin_data_hygiene",
                        "updated_at": now_iso,
                        "updated_by": admin.user_id,
                    },
                    "$setOnInsert": {
                        "created_at": now_iso,
                        "created_by": admin.user_id,
                    },
                },
                upsert=True,
            )
            blocklisted += 1

    await log_admin_event(
        admin.user_id,
        "run_test_alias_hygiene_apply",
        {
            "candidate_count": len(candidates),
            "updated_users": updated_users,
            "blocklisted": blocklisted,
            "sessions_revoked": sessions_revoked,
            "limit": body.limit,
            "disable_login": body.disable_login,
            "enforce_email_blocklist": body.enforce_email_blocklist,
        },
        req,
    )

    return {
        "mode": "applied",
        "candidate_count": len(candidates),
        "updated_users": updated_users,
        "blocklisted": blocklisted,
        "sessions_revoked": sessions_revoked,
        "timestamp": now_iso,
    }


@router.post("/admin/tab-alias-telemetry/hit")
async def admin_tab_alias_telemetry_hit(req: Request, body: AliasTelemetryHitRequest):
    admin = await require_admin(req)
    source_tab = str(body.source_tab_id or "").strip()
    canonical_tab = str(body.canonical_tab_id or "").strip()
    if not source_tab or not canonical_tab:
        raise HTTPException(status_code=400, detail="source_tab_id and canonical_tab_id are required")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    bucket_date = now.strftime("%Y-%m-%d")
    bucket_key = f"{bucket_date}:{body.console}:{source_tab}:{canonical_tab}:{admin.user_id}"

    await db.tab_alias_telemetry_daily.update_one(
        {"bucket_key": bucket_key},
        {
            "$set": {
                "bucket_key": bucket_key,
                "bucket_date": bucket_date,
                "console": body.console,
                "source_tab_id": source_tab,
                "canonical_tab_id": canonical_tab,
                "user_id": admin.user_id,
                "updated_at": now_iso,
                "context": body.context,
            },
            "$setOnInsert": {
                "created_at": now_iso,
                "first_hit_at": now_iso,
            },
            "$inc": {"hit_count": 1},
        },
        upsert=True,
    )

    return {"success": True, "bucket_key": bucket_key}


@router.get("/admin/tab-alias-telemetry/summary")
async def admin_tab_alias_telemetry_summary(req: Request, days: int = 30):
    await require_admin(req)
    days = max(1, min(int(days or 30), 365))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = await db.tab_alias_telemetry_daily.find(
        {"bucket_date": {"$gte": since}},
        {"_id": 0},
    ).to_list(10000)

    by_pair: dict[str, dict] = {}
    by_console: dict[str, int] = {"executive": 0, "operations": 0}
    by_day: dict[str, int] = {}
    total = 0

    for row in rows:
        hits = int(row.get("hit_count") or 0)
        total += hits
        console = str(row.get("console") or "unknown")
        by_console[console] = by_console.get(console, 0) + hits
        day = str(row.get("bucket_date") or "")
        by_day[day] = by_day.get(day, 0) + hits

        pair_key = f"{row.get('source_tab_id')}->{row.get('canonical_tab_id')}"
        if pair_key not in by_pair:
            by_pair[pair_key] = {
                "source_tab_id": row.get("source_tab_id"),
                "canonical_tab_id": row.get("canonical_tab_id"),
                "hit_count": 0,
                "console_breakdown": {},
            }
        by_pair[pair_key]["hit_count"] += hits
        by_pair[pair_key]["console_breakdown"][console] = by_pair[pair_key]["console_breakdown"].get(console, 0) + hits

    top_pairs = sorted(by_pair.values(), key=lambda x: x["hit_count"], reverse=True)[:50]
    timeline = [{"date": k, "hits": by_day[k]} for k in sorted(by_day.keys())][-90:]

    return {
        "window_days": days,
        "total_hits": total,
        "by_console": by_console,
        "top_pairs": top_pairs,
        "timeline": timeline,
    }




@router.get("/admin/smoke-test")
async def smoke_test(request: Request):
    """Run system diagnostics — admin only."""
    await require_admin(request)
    import os

    checks = []

    # 1. Database connectivity
    try:
        await db.command("ping")
        checks.append({"name": "MongoDB Connection", "status": "pass", "detail": "Connected"})
    except Exception as e:
        checks.append({"name": "MongoDB Connection", "status": "fail", "detail": str(e)})

    # 2. Collections check
    try:
        collections = await db.list_collection_names()
        critical = ["users", "user_sessions", "payments", "security_events"]
        missing = [c for c in critical if c not in collections]
        if missing:
            checks.append(
                {"name": "Critical Collections", "status": "warn", "detail": f"Missing: {', '.join(missing)}"}
            )
        else:
            checks.append(
                {"name": "Critical Collections", "status": "pass", "detail": f"{len(collections)} collections found"}
            )
    except Exception as e:
        checks.append({"name": "Critical Collections", "status": "fail", "detail": str(e)})

    # 3. User count
    try:
        count = await db.users.count_documents({})
        checks.append({"name": "User Records", "status": "pass", "detail": f"{count} users"})
    except Exception as e:
        checks.append({"name": "User Records", "status": "fail", "detail": str(e)})

    # 4. Email service
    try:
        from utils.email_service import is_email_configured

        configured = is_email_configured()
        checks.append(
            {
                "name": "Email Service (Resend)",
                "status": "pass" if configured else "warn",
                "detail": "Configured" if configured else "Not configured",
            }
        )
    except Exception as e:
        checks.append({"name": "Email Service (Resend)", "status": "fail", "detail": str(e)})

    # 5. Stripe
    stripe_key = os.environ.get("STRIPE_API_KEY") or os.environ.get("STRIPE_SECRET_KEY")
    checks.append(
        {
            "name": "Stripe API",
            "status": "pass" if stripe_key else "warn",
            "detail": "Key configured" if stripe_key else "No key",
        }
    )

    # 6. LLM Key
    llm_key = os.environ.get("EMERGENT_LLM_KEY")
    checks.append(
        {
            "name": "Emergent LLM Key",
            "status": "pass" if llm_key else "warn",
            "detail": "Configured" if llm_key else "Not configured",
        }
    )

    # 7. Route modules loaded
    route_dir = os.path.join(os.path.dirname(__file__))
    route_files = [f[:-3] for f in os.listdir(route_dir) if f.endswith(".py") and f != "__init__.py" and f != "db.py"]
    checks.append({"name": "Backend Route Modules", "status": "pass", "detail": f"{len(route_files)} modules loaded"})

    # 8. Active sessions
    try:
        active = await db.user_sessions.count_documents({"expires_at": {"$gte": datetime.now(timezone.utc)}})
        checks.append({"name": "Active Sessions", "status": "pass", "detail": f"{active} active sessions"})
    except Exception as e:
        checks.append({"name": "Active Sessions", "status": "fail", "detail": str(e)})

    # 9. Security events (24h)
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        sec_count = await db.security_events.count_documents({"timestamp": {"$gte": since.isoformat()}})
        high_risk = await db.security_events.count_documents(
            {"timestamp": {"$gte": since.isoformat()}, "risk_level": "high"}
        )
        status = "warn" if high_risk > 5 else "pass"
        checks.append(
            {"name": "Security Events (24h)", "status": status, "detail": f"{sec_count} events, {high_risk} high-risk"}
        )
    except Exception as e:
        checks.append({"name": "Security Events (24h)", "status": "fail", "detail": str(e)})

    # 10. Disk space (media)
    try:
        media_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")
        if os.path.exists(media_path):
            total_size = sum(
                os.path.getsize(os.path.join(dp, f)) for dp, dn, filenames in os.walk(media_path) for f in filenames
            )
            size_mb = round(total_size / (1024 * 1024), 1)
            checks.append(
                {"name": "Media Storage", "status": "pass" if size_mb < 500 else "warn", "detail": f"{size_mb} MB used"}
            )
        else:
            checks.append({"name": "Media Storage", "status": "pass", "detail": "No media directory"})
    except Exception as e:
        checks.append({"name": "Media Storage", "status": "fail", "detail": str(e)})

    passed = sum(1 for c in checks if c["status"] == "pass")
    total = len(checks)
    overall = "healthy" if passed == total else "degraded" if passed > total // 2 else "critical"

    return {
        "overall": overall,
        "passed": passed,
        "total": total,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/admin/security-leaderboard")
async def security_leaderboard(request: Request):
    """Get security scores for all users — admin only."""
    await require_admin(request)

    users = await db.users.find({}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(500)
    user_ids = [str(u.get("user_id") or "") for u in users if str(u.get("user_id") or "")]

    two_fa_user_ids: set[str] = set()
    passkey_user_ids: set[str] = set()

    if user_ids:
        security_rows = await db.user_security.find(
            {
                "user_id": {"$in": user_ids},
                "two_fa_enabled": True,
            },
            {"_id": 0, "user_id": 1},
        ).to_list(500)
        two_fa_user_ids = {str(row.get("user_id") or "") for row in security_rows if str(row.get("user_id") or "")}

        passkey_rows = await db.webauthn_credentials.find(
            {"user_id": {"$in": user_ids}},
            {"_id": 0, "user_id": 1},
        ).to_list(500)
        passkey_user_ids = {str(row.get("user_id") or "") for row in passkey_rows if str(row.get("user_id") or "")}

    results = []

    for u in users:
        uid = str(u.get("user_id") or "")
        has_2fa = uid in two_fa_user_ids
        has_pk = uid in passkey_user_ids

        results.append(
            {
                "user_id": uid,
                "email": u.get("email", ""),
                "name": u.get("name", ""),
                "has_2fa": has_2fa,
                "has_passkey": bool(has_pk),
            }
        )

    results.sort(key=lambda x: (x["has_2fa"], x["has_passkey"], x["user_id"]), reverse=True)
    has_2fa_count = sum(1 for r in results if r["has_2fa"])
    has_passkey_count = sum(1 for r in results if r["has_passkey"])

    return {
        "users": results[:50],
        "total_users": len(results),
        "has_2fa_count": has_2fa_count,
        "has_passkey_count": has_passkey_count,
    }
