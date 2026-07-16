"""AI User Insights Engine (Admin) — Engagement scoring, churn prediction, retention analytics.

Uses behavioral signals to compute engagement scores and predict churn risk.

API:
- GET  /api/admin/insights/dashboard     — Executive insights dashboard
- GET  /api/admin/insights/users         — User engagement leaderboard
- GET  /api/admin/insights/churn-risk    — High churn-risk users
- POST /api/admin/insights/retention-tips — AI retention recommendations
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import logging

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate_json
from utils.access_control_engine import compute_effective_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/insights")


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


def _engagement_score(metrics: dict) -> float:
    """Compute engagement score (0-100) from behavioral metrics."""
    weights = {
        "sessions_7d": 25,
        "messages_7d": 20,
        "goals_active": 15,
        "login_days_7d": 20,
        "features_used": 10,
        "streak": 10,
    }
    score = 0
    score += min(metrics.get("sessions_7d", 0) / 5, 1) * weights["sessions_7d"]
    score += min(metrics.get("messages_7d", 0) / 10, 1) * weights["messages_7d"]
    score += min(metrics.get("goals_active", 0) / 3, 1) * weights["goals_active"]
    score += min(metrics.get("login_days_7d", 0) / 7, 1) * weights["login_days_7d"]
    score += min(metrics.get("features_used", 0) / 5, 1) * weights["features_used"]
    score += min(metrics.get("streak", 0) / 7, 1) * weights["streak"]
    return round(score, 1)


def _churn_risk(engagement: float, days_since_login: int, plan: str) -> dict:
    """Predict churn risk based on engagement and activity."""
    risk = 0
    factors = []

    if engagement < 20:
        risk += 40
        factors.append("Very low engagement")
    elif engagement < 40:
        risk += 25
        factors.append("Low engagement")

    if days_since_login > 14:
        risk += 35
        factors.append(f"Inactive {days_since_login} days")
    elif days_since_login > 7:
        risk += 20
        factors.append(f"Inactive {days_since_login} days")

    if plan == "free":
        risk += 15
        factors.append("Free tier user")

    risk = min(risk, 100)
    level = "critical" if risk >= 70 else "high" if risk >= 50 else "medium" if risk >= 30 else "low"
    return {"risk_score": risk, "risk_level": level, "factors": factors}


@router.get("/dashboard")
async def insights_dashboard(request: Request):
    user = await get_current_user(request)
    if not user or not (user.is_admin or user.role == "admin"):
        raise HTTPException(403, "Admin access required")

    now = datetime.now(timezone.utc)
    seven_days = (now - timedelta(days=7)).isoformat()
    thirty_days = (now - timedelta(days=30)).isoformat()

    total_users = await db.users.count_documents({})
    active_7d = await db.security_events.distinct("user_id", {"event_type": "login", "timestamp": {"$gte": seven_days}})
    active_30d = await db.security_events.distinct(
        "user_id", {"event_type": "login", "timestamp": {"$gte": thirty_days}}
    )

    new_users_7d = await db.users.count_documents({"created_at": {"$gte": seven_days}})
    paid_users_cursor = await db.users.find(
        {},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
    ).to_list(5000)
    paid_users = sum(1 for row in paid_users_cursor if _effective_plan_from_user_doc(row) != "free")

    # Feature adoption
    coach_users = await db.coach_conversations.distinct("user_id")
    goal_users = await db.ai_goals.distinct("user_id")
    doc_users = await db.doc_analyses.distinct("user_id")
    briefing_users = await db.ai_briefings.distinct("user_id")

    # Engagement distribution
    all_users = await db.users.find({}, {"_id": 0, "user_id": 1}).to_list(500)
    engagement_buckets = {"high": 0, "medium": 0, "low": 0, "dormant": 0}

    for u in all_users[:200]:
        uid = u["user_id"]
        sessions = await db.conversations.count_documents({"user_id": uid, "created_at": {"$gte": seven_days}})
        msgs = await db.coach_messages.count_documents({"conversation_id": {"$regex": uid[:8]}})
        goals = await db.ai_goals.count_documents({"user_id": uid, "status": "active"})

        es = _engagement_score(
            {
                "sessions_7d": sessions,
                "messages_7d": min(msgs, 20),
                "goals_active": goals,
                "login_days_7d": min(sessions, 7),
                "features_used": 3,
                "streak": 0,
            }
        )
        if es >= 60:
            engagement_buckets["high"] += 1
        elif es >= 30:
            engagement_buckets["medium"] += 1
        elif es >= 10:
            engagement_buckets["low"] += 1
        else:
            engagement_buckets["dormant"] += 1

    return {
        "overview": {
            "total_users": total_users,
            "active_7d": len(active_7d),
            "active_30d": len(active_30d),
            "new_users_7d": new_users_7d,
            "paid_users": paid_users,
            "conversion_rate": round(paid_users / max(total_users, 1) * 100, 1),
        },
        "engagement_distribution": engagement_buckets,
        "feature_adoption": {
            "ai_coach": len(coach_users),
            "goal_tracker": len(goal_users),
            "doc_analyzer": len(doc_users),
            "daily_briefing": len(briefing_users),
        },
        "timestamp": now.isoformat(),
    }


@router.get("/users")
async def user_engagement_leaderboard(request: Request):
    user = await get_current_user(request)
    if not user or not (user.is_admin or user.role == "admin"):
        raise HTTPException(403, "Admin access required")

    seven_days = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    users = await db.users.find(
        {}, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1, "last_login": 1}
    ).to_list(100)

    results = []
    for u in users:
        uid = u["user_id"]
        sessions = await db.conversations.count_documents({"user_id": uid, "created_at": {"$gte": seven_days}})
        goals = await db.ai_goals.count_documents({"user_id": uid, "status": "active"})
        es = _engagement_score(
            {
                "sessions_7d": sessions,
                "goals_active": goals,
                "login_days_7d": min(sessions, 7),
                "messages_7d": 0,
                "features_used": 3,
                "streak": 0,
            }
        )

        days_since = 999
        if u.get("last_login"):
            try:
                ll = datetime.fromisoformat(str(u["last_login"]).replace("Z", "+00:00"))
                if ll.tzinfo is None:
                    ll = ll.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - ll).days
            except Exception:
                pass

        effective_plan = _effective_plan_from_user_doc(u)
        churn = _churn_risk(es, days_since, effective_plan)
        results.append(
            {
                "user_id": uid,
                "name": u.get("name", ""),
                "email": u.get("email", ""),
                "plan": effective_plan,
                "engagement_score": es,
                "churn_risk": churn,
                "sessions_7d": sessions,
                "active_goals": goals,
            }
        )

    results.sort(key=lambda x: x["engagement_score"], reverse=True)
    return {"users": results[:50]}


@router.get("/churn-risk")
async def churn_risk_users(request: Request):
    user = await get_current_user(request)
    if not user or not (user.is_admin or user.role == "admin"):
        raise HTTPException(403, "Admin access required")

    users = await db.users.find(
        {}, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1, "last_login": 1}
    ).to_list(200)
    at_risk = []

    for u in users:
        uid = u["user_id"]
        seven_days = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        sessions = await db.conversations.count_documents({"user_id": uid, "created_at": {"$gte": seven_days}})
        es = _engagement_score(
            {
                "sessions_7d": sessions,
                "goals_active": 0,
                "login_days_7d": min(sessions, 7),
                "messages_7d": 0,
                "features_used": 2,
                "streak": 0,
            }
        )

        days_since = 999
        if u.get("last_login"):
            try:
                ll = datetime.fromisoformat(str(u["last_login"]).replace("Z", "+00:00"))
                if ll.tzinfo is None:
                    ll = ll.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - ll).days
            except Exception:
                pass

        effective_plan = _effective_plan_from_user_doc(u)
        churn = _churn_risk(es, days_since, effective_plan)
        if churn["risk_score"] >= 30:
            at_risk.append(
                {
                    "user_id": uid,
                    "name": u.get("name", ""),
                    "email": u.get("email", ""),
                    "plan": effective_plan,
                    "engagement_score": es,
                    **churn,
                    "days_since_login": days_since,
                }
            )

    at_risk.sort(key=lambda x: x["risk_score"], reverse=True)
    return {"at_risk_users": at_risk[:30], "total_at_risk": len(at_risk)}


@router.post("/retention-tips")
async def get_retention_tips(request: Request):
    user = await get_current_user(request)
    if not user or not (user.is_admin or user.role == "admin"):
        raise HTTPException(403, "Admin access required")

    # Get summary stats
    total = await db.users.count_documents({})
    active = await db.security_events.distinct(
        "user_id",
        {"event_type": "login", "timestamp": {"$gte": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}},
    )
    paid_cursor = await db.users.find(
        {},
        {"_id": 0, "subscription_plan": 1, "subscription_status": 1, "subscription_end_date": 1, "subscription_permanent": 1, "payment_verified": 1, "pending_subscription_transition": 1, "is_admin": 1, "full_access": 1},
    ).to_list(5000)
    paid = sum(1 for row in paid_cursor if _effective_plan_from_user_doc(row) != "free")

    system_msg = """You are a SaaS Retention Strategist. Based on the platform metrics, provide actionable retention recommendations.
Return ONLY valid JSON:
{
  "recommendations": [
    {"title": "Strategy title", "description": "Detailed description", "impact": "high|medium", "effort": "low|medium|high", "category": "engagement|onboarding|communication|value"},
    ...
  ],
  "quick_wins": ["Quick win 1", "Quick win 2"],
  "key_metric_to_watch": "Which metric to focus on"
}"""
    prompt = f"Platform stats: {total} total users, {len(active)} active (7d), {paid} paid. Conversion: {round(paid / max(total, 1) * 100, 1)}%. Provide 5-6 retention strategies:"

    try:
        tips = await ai_generate_json(system_msg, prompt, "retention-tips")
    except Exception as e:
        logger.error(f"Retention tips error: {e}")
        tips = {
            "recommendations": [
                {
                    "title": "Re-engagement Campaign",
                    "description": "Send personalized emails to inactive users",
                    "impact": "high",
                    "effort": "medium",
                    "category": "communication",
                }
            ],
            "quick_wins": ["Send a welcome email series"],
            "key_metric_to_watch": "7-day active users",
        }
    return tips
