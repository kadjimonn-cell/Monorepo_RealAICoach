"""
User Analytics Dashboard - Real-time analytics for end users
"""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user-analytics", tags=["User Analytics"])


def get_db():
    from routes.db import db

    return db


async def _auth(request: Request):
    from routes.db import require_auth

    return await require_auth(request)


def _date_range(days: int):
    now = datetime.now(timezone.utc)
    return now - timedelta(days=days), now


@router.get("/dashboard")
async def analytics_dashboard(request: Request):
    user = await _auth(request)
    uid = user.user_id
    db = get_db()
    start_7d, now = _date_range(7)
    start_30d, _ = _date_range(30)

    prog = await db.progress.find_one({"user_id": uid}, {"_id": 0}) or {}

    usage_7d = await db.ai_usage_tracking.find(
        {"user_id": uid, "date": {"$gte": start_7d.strftime("%Y-%m-%d")}}, {"_id": 0}
    ).to_list(1000)
    usage_30d = await db.ai_usage_tracking.find(
        {"user_id": uid, "date": {"$gte": start_30d.strftime("%Y-%m-%d")}}, {"_id": 0}
    ).to_list(1000)

    total_requests_7d = sum(u.get("requests", 0) for u in usage_7d)
    total_requests_30d = sum(u.get("requests", 0) for u in usage_30d)
    total_tokens_7d = sum(u.get("tokens_used", 0) for u in usage_7d)
    total_tokens_30d = sum(u.get("tokens_used", 0) for u in usage_30d)

    convos_total = await db.conversations.count_documents({"user_id": uid})
    convos_7d = await db.conversations.count_documents({"user_id": uid, "created_at": {"$gte": start_7d.isoformat()}})
    actions_total = await db.action_history.count_documents({"user_id": uid})
    actions_7d = await db.action_history.count_documents({"user_id": uid, "timestamp": {"$gte": start_7d.isoformat()}})

    features_result = await db.ai_usage_tracking.aggregate(
        [{"$match": {"user_id": uid}}, {"$group": {"_id": "$mini_app"}}, {"$count": "total"}]
    ).to_list(1)
    features_accessed = features_result[0]["total"] if features_result else 0

    prev_start = start_7d - timedelta(days=7)
    usage_prev = await db.ai_usage_tracking.find(
        {"user_id": uid, "date": {"$gte": prev_start.strftime("%Y-%m-%d"), "$lt": start_7d.strftime("%Y-%m-%d")}},
        {"_id": 0},
    ).to_list(1000)
    prev_requests = sum(u.get("requests", 0) for u in usage_prev)
    wow_change = ((total_requests_7d - prev_requests) / max(prev_requests, 1)) * 100

    return {
        "summary": {
            "ai_requests_7d": total_requests_7d,
            "ai_requests_30d": total_requests_30d,
            "tokens_used_7d": total_tokens_7d,
            "tokens_used_30d": total_tokens_30d,
            "conversations_total": convos_total,
            "conversations_7d": convos_7d,
            "actions_total": actions_total,
            "actions_7d": actions_7d,
            "features_accessed": features_accessed,
            "wow_change_pct": round(wow_change, 1),
        },
        "coaching": {
            "current_streak": prog.get("current_streak", 0),
            "longest_streak": prog.get("longest_streak", 0),
            "xp": prog.get("xp", 0),
            "level": prog.get("level", 1),
            "sessions_completed": prog.get("completed_conversations", 0),
            "skills": prog.get("skills", {}),
        },
        "generated_at": now.isoformat(),
    }


@router.get("/ai-usage-patterns")
async def ai_usage_patterns(request: Request, days: int = 30):
    user = await _auth(request)
    uid = user.user_id
    db = get_db()
    start, now = _date_range(min(days, 90))

    usage_data = await db.ai_usage_tracking.find(
        {"user_id": uid, "date": {"$gte": start.strftime("%Y-%m-%d")}}, {"_id": 0}
    ).to_list(5000)

    daily_map, app_map = {}, {}
    for u in usage_data:
        d = u.get("date", "")
        daily_map[d] = daily_map.get(d, 0) + u.get("requests", 0)
        app = u.get("mini_app", "general")
        if app not in app_map:
            app_map[app] = {"requests": 0, "tokens": 0}
        app_map[app]["requests"] += u.get("requests", 0)
        app_map[app]["tokens"] += u.get("tokens_used", 0)

    daily_trend = []
    current = start.date()
    while current <= now.date():
        ds = current.strftime("%Y-%m-%d")
        daily_trend.append({"date": ds, "requests": daily_map.get(ds, 0)})
        current += timedelta(days=1)

    top_features = sorted(app_map.items(), key=lambda x: x[1]["requests"], reverse=True)[:10]

    try:
        hour_data = await db.conversations.aggregate(
            [
                {"$match": {"user_id": uid}},
                {"$addFields": {"hour": {"$hour": {"$toDate": "$created_at"}}}},
                {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
        ).to_list(24)
    except Exception:
        hour_data = []

    return {
        "daily_trend": daily_trend,
        "by_feature": [{"feature": k, **v} for k, v in top_features],
        "peak_hours": [{"hour": h["_id"], "count": h["count"]} for h in hour_data[:5]],
        "total_days_active": len([d for d in daily_trend if d["requests"] > 0]),
        "avg_daily_requests": round(sum(d["requests"] for d in daily_trend) / max(len(daily_trend), 1), 1),
    }


@router.get("/progress-trends")
async def progress_trends(request: Request, days: int = 30):
    user = await _auth(request)
    uid = user.user_id
    db = get_db()
    start, now = _date_range(min(days, 90))

    prog = await db.progress.find_one({"user_id": uid}, {"_id": 0}) or {}
    skills = prog.get(
        "skills", {"empathy": 50, "clarity": 50, "confidence": 50, "active_listening": 50, "emotional_intelligence": 50}
    )

    streak_data = (
        await db.coaching_streaks.find({"user_id": uid}, {"_id": 0, "date": 1, "streak": 1, "xp_earned": 1})
        .sort("date", -1)
        .to_list(days)
    )

    try:
        convo_daily = await db.conversations.aggregate(
            [
                {"$match": {"user_id": uid, "created_at": {"$gte": start.isoformat()}}},
                {"$addFields": {"date": {"$substr": ["$created_at", 0, 10]}}},
                {"$group": {"_id": "$date", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        ).to_list(100)
    except Exception:
        convo_daily = []

    session_trend = []
    current = start.date()
    convo_map = {c["_id"]: c["count"] for c in convo_daily}
    while current <= now.date():
        ds = current.strftime("%Y-%m-%d")
        session_trend.append({"date": ds, "sessions": convo_map.get(ds, 0)})
        current += timedelta(days=1)

    xp = prog.get("xp", 0)
    level = prog.get("level", 1)
    next_level_xp = level * 100

    return {
        "skills": skills,
        "category_progress": prog.get("category_progress", {}),
        "session_trend": session_trend,
        "streak_history": streak_data[:30],
        "xp_progress": {
            "current_xp": xp,
            "level": level,
            "next_level_xp": next_level_xp,
            "xp_to_next_level": max(next_level_xp - xp, 0),
            "progress_pct": round(min(xp / max(next_level_xp, 1), 1) * 100, 1),
        },
        "total_sessions": prog.get("completed_conversations", 0),
        "total_messages": prog.get("total_messages_sent", 0),
    }


@router.get("/skill-radar")
async def skill_radar(request: Request):
    user = await _auth(request)
    db = get_db()
    prog = await db.progress.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    skills = prog.get(
        "skills", {"empathy": 50, "clarity": 50, "confidence": 50, "active_listening": 50, "emotional_intelligence": 50}
    )

    sorted_skills = sorted(skills.items(), key=lambda x: x[1], reverse=True)
    avg = sum(skills.values()) / max(len(skills), 1)

    return {
        "skills": [{"skill": k, "score": v} for k, v in sorted_skills],
        "avg_score": round(avg, 1),
        "strengths": [{"skill": k, "score": v} for k, v in sorted_skills if v >= avg],
        "weaknesses": [{"skill": k, "score": v} for k, v in sorted_skills if v < avg],
    }


@router.get("/recommendations")
async def get_recommendations(request: Request):
    user = await _auth(request)
    uid = user.user_id
    db = get_db()

    prog = await db.progress.find_one({"user_id": uid}, {"_id": 0}) or {}
    skills = prog.get("skills", {})
    streak = prog.get("current_streak", 0)
    sessions = prog.get("completed_conversations", 0)
    category_progress = prog.get("category_progress", {})
    recs = []

    if skills:
        weakest = min(skills.items(), key=lambda x: x[1])
        strongest = max(skills.items(), key=lambda x: x[1])
        if weakest[1] < 60:
            recs.append(
                {
                    "type": "skill_improvement",
                    "priority": "high",
                    "icon": "trending-up",
                    "color": "#F59E0B",
                    "title": f"Boost your {weakest[0].replace('_', ' ').title()}",
                    "description": f"Your {weakest[0].replace('_', ' ')} score is {weakest[1]}. Try 2-3 practice sessions focused on this skill.",
                    "action": "Start Practice",
                    "action_route": "/(tabs)/practice",
                }
            )
        if strongest[1] >= 70:
            recs.append(
                {
                    "type": "skill_mastery",
                    "priority": "medium",
                    "icon": "trophy",
                    "color": "#10B981",
                    "title": f"You're excelling at {strongest[0].replace('_', ' ').title()}!",
                    "description": f"Score: {strongest[1]}/100. Try advanced scenarios to push even higher.",
                    "action": "Advanced Practice",
                    "action_route": "/(tabs)/practice",
                }
            )

    if streak == 0:
        recs.append(
            {
                "type": "streak_start",
                "priority": "high",
                "icon": "flame",
                "color": "#EF4444",
                "title": "Start a practice streak!",
                "description": "Complete one session today to begin building your streak.",
                "action": "Start Now",
                "action_route": "/(tabs)/practice",
            }
        )
    elif streak >= 7:
        recs.append(
            {
                "type": "streak_celebration",
                "priority": "low",
                "icon": "star",
                "color": "#6366F1",
                "title": f"Amazing {streak}-day streak!",
                "description": "You're building great habits. Keep going!",
                "action": "View Achievements",
                "action_route": "/achievements",
            }
        )

    unused_cats = [c for c, v in category_progress.items() if v == 0]
    if unused_cats and len(unused_cats) <= 4:
        recs.append(
            {
                "type": "explore_category",
                "priority": "medium",
                "icon": "compass",
                "color": "#3B82F6",
                "title": f"Explore {unused_cats[0].title()} scenarios",
                "description": f"You haven't tried {unused_cats[0]} practice yet. Diversifying helps build well-rounded skills.",
                "action": "Try It",
                "action_route": "/(tabs)/practice",
            }
        )

    next_ms = (sessions // 10 + 1) * 10
    gap = next_ms - sessions
    if 0 < gap <= 3:
        recs.append(
            {
                "type": "milestone_close",
                "priority": "high",
                "icon": "flag",
                "color": "#8B5CF6",
                "title": f"Only {gap} sessions to milestone!",
                "description": f"You're so close to {next_ms} total sessions!",
                "action": "Keep Going",
                "action_route": "/(tabs)/practice",
            }
        )

    used_feats = {
        f["_id"]
        for f in await db.ai_usage_tracking.aggregate(
            [{"$match": {"user_id": uid}}, {"$group": {"_id": "$mini_app"}}]
        ).to_list(50)
    }
    unexplored = {"ai-chatbot", "ai-writer", "medimate", "pennypilot", "travelpal", "smartbuy"} - used_feats
    if unexplored:
        feat = list(unexplored)[0]
        recs.append(
            {
                "type": "feature_discovery",
                "priority": "low",
                "icon": "sparkles",
                "color": "#0EA5E9",
                "title": f"Try {feat.replace('-', ' ').title()}",
                "description": "Discover a new AI feature you haven't used yet.",
                "action": "Explore",
                "action_route": f"/features/{feat}",
            }
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda x: priority_order.get(x["priority"], 3))

    return {"recommendations": recs[:6], "total_recommendations": len(recs)}


@router.get("/weekly-report")
async def weekly_report(request: Request):
    user = await _auth(request)
    uid = user.user_id
    db = get_db()
    start, now = _date_range(7)

    prog = await db.progress.find_one({"user_id": uid}, {"_id": 0}) or {}
    user_doc = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "subscription_plan": 1}) or {}

    usage_week = await db.ai_usage_tracking.find(
        {"user_id": uid, "date": {"$gte": start.strftime("%Y-%m-%d")}}, {"_id": 0}
    ).to_list(1000)
    convos_week = await db.conversations.count_documents({"user_id": uid, "created_at": {"$gte": start.isoformat()}})
    actions_week = await db.action_history.count_documents({"user_id": uid, "timestamp": {"$gte": start.isoformat()}})

    total_requests = sum(u.get("requests", 0) for u in usage_week)
    total_tokens = sum(u.get("tokens_used", 0) for u in usage_week)

    feat_map = {}
    for u in usage_week:
        app = u.get("mini_app", "general")
        feat_map[app] = feat_map.get(app, 0) + u.get("requests", 0)
    top_feature = max(feat_map.items(), key=lambda x: x[1])[0] if feat_map else "None"

    skills = prog.get("skills", {})
    avg_skill = round(sum(skills.values()) / max(len(skills), 1), 1) if skills else 0

    prev_start = start - timedelta(days=7)
    usage_prev = await db.ai_usage_tracking.find(
        {"user_id": uid, "date": {"$gte": prev_start.strftime("%Y-%m-%d"), "$lt": start.strftime("%Y-%m-%d")}},
        {"_id": 0},
    ).to_list(1000)
    prev_requests = sum(u.get("requests", 0) for u in usage_prev)

    return {
        "user_name": user_doc.get("name", "User"),
        "plan": user_doc.get("subscription_plan", "free"),
        "period": {"start": start.strftime("%Y-%m-%d"), "end": now.strftime("%Y-%m-%d")},
        "highlights": {
            "ai_requests": total_requests,
            "ai_requests_change": total_requests - prev_requests,
            "tokens_used": total_tokens,
            "conversations": convos_week,
            "actions_performed": actions_week,
            "top_feature": top_feature.replace("-", " ").replace("_", " ").title(),
            "avg_skill_score": avg_skill,
            "streak": prog.get("current_streak", 0),
            "xp_earned": prog.get("xp", 0),
            "level": prog.get("level", 1),
        },
        "skills_snapshot": skills,
        "generated_at": now.isoformat(),
    }


@router.get("/home-summary")
async def home_summary(request: Request):
    user = await _auth(request)
    uid = user.user_id
    db = get_db()
    start_7d, now = _date_range(7)

    prog = await db.progress.find_one({"user_id": uid}, {"_id": 0}) or {}

    usage_7d = await db.ai_usage_tracking.find(
        {"user_id": uid, "date": {"$gte": start_7d.strftime("%Y-%m-%d")}}, {"_id": 0}
    ).to_list(1000)
    total_requests = sum(u.get("requests", 0) for u in usage_7d)

    prev_start = start_7d - timedelta(days=7)
    usage_prev = await db.ai_usage_tracking.find(
        {"user_id": uid, "date": {"$gte": prev_start.strftime("%Y-%m-%d"), "$lt": start_7d.strftime("%Y-%m-%d")}},
        {"_id": 0},
    ).to_list(1000)
    prev_requests = sum(u.get("requests", 0) for u in usage_prev)
    trend = "up" if total_requests > prev_requests else "down" if total_requests < prev_requests else "flat"

    skills = prog.get("skills", {})
    avg_skill = round(sum(skills.values()) / max(len(skills), 1), 1) if skills else 0
    top_skill = max(skills.items(), key=lambda x: x[1]) if skills else ("none", 0)

    return {
        "ai_requests_7d": total_requests,
        "trend": trend,
        "trend_pct": round(((total_requests - prev_requests) / max(prev_requests, 1)) * 100, 1),
        "streak": prog.get("current_streak", 0),
        "xp": prog.get("xp", 0),
        "level": prog.get("level", 1),
        "avg_skill": avg_skill,
        "top_skill": {"name": top_skill[0], "score": top_skill[1]},
        "sessions": prog.get("completed_conversations", 0),
    }


# ─── Achievement Definitions ───────────────────────────────────
ACHIEVEMENTS = [
    # Analytics Engagement
    {
        "id": "data_nerd",
        "name": "Data Nerd",
        "description": "Check analytics 7 days in a row",
        "icon": "bar-chart",
        "color": "#6366F1",
        "category": "analytics",
        "tier": "silver",
    },
    {
        "id": "stats_junkie",
        "name": "Stats Junkie",
        "description": "Check analytics 30 days in a row",
        "icon": "stats-chart",
        "color": "#8B5CF6",
        "category": "analytics",
        "tier": "gold",
    },
    # Skill Mastery
    {
        "id": "skill_master",
        "name": "Skill Master",
        "description": "Get any skill to 90+",
        "icon": "ribbon",
        "color": "#10B981",
        "category": "skills",
        "tier": "gold",
    },
    {
        "id": "well_rounded",
        "name": "Well-Rounded",
        "description": "All skills above 70",
        "icon": "globe",
        "color": "#0EA5E9",
        "category": "skills",
        "tier": "platinum",
    },
    # Streak Milestones
    {
        "id": "on_fire",
        "name": "On Fire",
        "description": "Achieve a 7-day streak",
        "icon": "flame",
        "color": "#F59E0B",
        "category": "streak",
        "tier": "bronze",
    },
    {
        "id": "unstoppable",
        "name": "Unstoppable",
        "description": "Achieve a 30-day streak",
        "icon": "flash",
        "color": "#EF4444",
        "category": "streak",
        "tier": "gold",
    },
    {
        "id": "legend",
        "name": "Legend",
        "description": "Achieve a 100-day streak",
        "icon": "diamond",
        "color": "#EC4899",
        "category": "streak",
        "tier": "platinum",
    },
    # AI Usage
    {
        "id": "power_user",
        "name": "Power User",
        "description": "Make 100 AI requests",
        "icon": "rocket",
        "color": "#3B82F6",
        "category": "usage",
        "tier": "silver",
    },
    {
        "id": "ai_enthusiast",
        "name": "AI Enthusiast",
        "description": "Make 500 AI requests",
        "icon": "sparkles",
        "color": "#6366F1",
        "category": "usage",
        "tier": "gold",
    },
    # Session Milestones
    {
        "id": "getting_started",
        "name": "Getting Started",
        "description": "Complete 10 practice sessions",
        "icon": "play-circle",
        "color": "#10B981",
        "category": "sessions",
        "tier": "bronze",
    },
    {
        "id": "committed",
        "name": "Committed",
        "description": "Complete 50 practice sessions",
        "icon": "checkmark-done-circle",
        "color": "#F59E0B",
        "category": "sessions",
        "tier": "silver",
    },
    {
        "id": "expert",
        "name": "Expert",
        "description": "Complete 100 practice sessions",
        "icon": "medal",
        "color": "#EF4444",
        "category": "sessions",
        "tier": "gold",
    },
    # XP/Level
    {
        "id": "level_up",
        "name": "Level Up",
        "description": "Reach Level 5",
        "icon": "arrow-up-circle",
        "color": "#3B82F6",
        "category": "level",
        "tier": "bronze",
    },
    {
        "id": "elite",
        "name": "Elite",
        "description": "Reach Level 10",
        "icon": "star",
        "color": "#F59E0B",
        "category": "level",
        "tier": "silver",
    },
    {
        "id": "grandmaster",
        "name": "Grandmaster",
        "description": "Reach Level 20",
        "icon": "trophy",
        "color": "#EC4899",
        "category": "level",
        "tier": "platinum",
    },
]

ACHIEVEMENT_MAP = {a["id"]: a for a in ACHIEVEMENTS}
TIER_ORDER = {"bronze": 1, "silver": 2, "gold": 3, "platinum": 4}


async def _check_achievements(uid: str, db) -> list:
    """Check and unlock achievements based on current user stats. Returns newly unlocked achievements."""
    prog = await db.progress.find_one({"user_id": uid}, {"_id": 0}) or {}
    skills = prog.get("skills", {})
    streak = prog.get("current_streak", 0)
    longest_streak = prog.get("longest_streak", 0)
    sessions = prog.get("completed_conversations", 0)
    prog.get("xp", 0)
    level = prog.get("level", 1)

    # Total AI requests
    total_ai = 0
    usage_all = await db.ai_usage_tracking.find({"user_id": uid}, {"_id": 0, "requests": 1}).to_list(10000)
    total_ai = sum(u.get("requests", 0) for u in usage_all)

    # Analytics visit streak
    analytics_doc = await db.user_achievements.find_one({"user_id": uid, "type": "analytics_streak"}, {"_id": 0})
    analytics_streak = analytics_doc.get("streak", 0) if analytics_doc else 0

    effective_streak = max(streak, longest_streak)

    # Determine which achievements should be unlocked
    should_unlock = set()

    # Analytics Engagement
    if analytics_streak >= 7:
        should_unlock.add("data_nerd")
    if analytics_streak >= 30:
        should_unlock.add("stats_junkie")

    # Skill Mastery
    if skills and max(skills.values()) >= 90:
        should_unlock.add("skill_master")
    if skills and len(skills) >= 5 and all(v >= 70 for v in skills.values()):
        should_unlock.add("well_rounded")

    # Streak Milestones
    if effective_streak >= 7:
        should_unlock.add("on_fire")
    if effective_streak >= 30:
        should_unlock.add("unstoppable")
    if effective_streak >= 100:
        should_unlock.add("legend")

    # AI Usage
    if total_ai >= 100:
        should_unlock.add("power_user")
    if total_ai >= 500:
        should_unlock.add("ai_enthusiast")

    # Session Milestones
    if sessions >= 10:
        should_unlock.add("getting_started")
    if sessions >= 50:
        should_unlock.add("committed")
    if sessions >= 100:
        should_unlock.add("expert")

    # XP/Level
    if level >= 5:
        should_unlock.add("level_up")
    if level >= 10:
        should_unlock.add("elite")
    if level >= 20:
        should_unlock.add("grandmaster")

    # Get already unlocked
    existing = await db.user_achievements.find(
        {"user_id": uid, "type": "achievement"}, {"_id": 0, "achievement_id": 1}
    ).to_list(50)
    already_unlocked = {e["achievement_id"] for e in existing}

    # Unlock new achievements
    newly_unlocked = []
    now = datetime.now(timezone.utc).isoformat()
    for aid in should_unlock - already_unlocked:
        await db.user_achievements.insert_one(
            {
                "user_id": uid,
                "type": "achievement",
                "achievement_id": aid,
                "unlocked_at": now,
            }
        )
        newly_unlocked.append(aid)

    return newly_unlocked


@router.get("/achievements")
async def get_achievements(request: Request):
    user = await _auth(request)
    uid = user.user_id
    db = get_db()

    # Track analytics visit for streak
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    streak_doc = await db.user_achievements.find_one({"user_id": uid, "type": "analytics_streak"}, {"_id": 0})
    if streak_doc:
        last_visit = streak_doc.get("last_visit", "")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        if last_visit == today:
            pass  # Already visited today
        elif last_visit == yesterday:
            await db.user_achievements.update_one(
                {"user_id": uid, "type": "analytics_streak"}, {"$set": {"last_visit": today}, "$inc": {"streak": 1}}
            )
        else:
            await db.user_achievements.update_one(
                {"user_id": uid, "type": "analytics_streak"}, {"$set": {"last_visit": today, "streak": 1}}
            )
    else:
        await db.user_achievements.insert_one(
            {
                "user_id": uid,
                "type": "analytics_streak",
                "last_visit": today,
                "streak": 1,
            }
        )

    # Check and unlock achievements
    newly_unlocked = await _check_achievements(uid, db)

    # Get all unlocked achievements
    unlocked_docs = await db.user_achievements.find({"user_id": uid, "type": "achievement"}, {"_id": 0}).to_list(50)
    unlocked_map = {d["achievement_id"]: d["unlocked_at"] for d in unlocked_docs}

    # Build response
    achievements = []
    for a in ACHIEVEMENTS:
        unlocked = a["id"] in unlocked_map
        achievements.append(
            {
                **a,
                "unlocked": unlocked,
                "unlocked_at": unlocked_map.get(a["id"]),
            }
        )

    # Get progress stats for display
    prog = await db.progress.find_one({"user_id": uid}, {"_id": 0}) or {}
    skills = prog.get("skills", {})
    streak_info = await db.user_achievements.find_one({"user_id": uid, "type": "analytics_streak"}, {"_id": 0})
    total_ai = sum(
        u.get("requests", 0)
        for u in await db.ai_usage_tracking.find({"user_id": uid}, {"_id": 0, "requests": 1}).to_list(10000)
    )

    progress_stats = {
        "analytics_streak": streak_info.get("streak", 0) if streak_info else 0,
        "max_skill": max(skills.values()) if skills else 0,
        "min_skill": min(skills.values()) if skills else 0,
        "all_skills_above_70": all(v >= 70 for v in skills.values()) if skills and len(skills) >= 5 else False,
        "current_streak": max(prog.get("current_streak", 0), prog.get("longest_streak", 0)),
        "total_ai_requests": total_ai,
        "total_sessions": prog.get("completed_conversations", 0),
        "level": prog.get("level", 1),
    }

    return {
        "achievements": achievements,
        "unlocked_count": len(unlocked_map),
        "total_count": len(ACHIEVEMENTS),
        "newly_unlocked": [ACHIEVEMENT_MAP[a] for a in newly_unlocked if a in ACHIEVEMENT_MAP],
        "progress": progress_stats,
    }


@router.get("/leaderboard")
async def get_leaderboard(request: Request, metric: str = "xp"):
    user = await _auth(request)
    uid = user.user_id
    db = get_db()

    if metric not in ("xp", "achievements", "streak"):
        metric = "xp"

    # Build leaderboard based on metric
    if metric == "xp":
        pipeline = [
            {"$project": {"_id": 0, "user_id": 1, "xp": {"$ifNull": ["$xp", 0]}, "level": {"$ifNull": ["$level", 1]}}},
            {"$sort": {"xp": -1, "level": -1}},
            {"$limit": 100},
        ]
        all_entries = await db.progress.aggregate(pipeline).to_list(100)
        entries = []
        my_rank = None
        for i, e in enumerate(all_entries):
            rank = i + 1
            is_me = e["user_id"] == uid
            if is_me:
                my_rank = rank
            entries.append(
                {
                    "rank": rank,
                    "label": f"User #{rank}",
                    "value": e.get("xp", 0),
                    "secondary": f"Level {e.get('level', 1)}",
                    "is_you": is_me,
                }
            )

        # If user not in top 100, find their rank
        if my_rank is None:
            my_prog = await db.progress.find_one({"user_id": uid}, {"_id": 0, "xp": 1, "level": 1}) or {}
            my_xp = my_prog.get("xp", 0)
            rank_count = await db.progress.count_documents({"xp": {"$gt": my_xp}})
            my_rank = rank_count + 1
            entries.append(
                {
                    "rank": my_rank,
                    "label": f"User #{my_rank}",
                    "value": my_xp,
                    "secondary": f"Level {my_prog.get('level', 1)}",
                    "is_you": True,
                }
            )

    elif metric == "achievements":
        # Count achievements per user
        pipeline = [
            {"$match": {"type": "achievement"}},
            {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 100},
        ]
        all_entries = await db.user_achievements.aggregate(pipeline).to_list(100)
        entries = []
        my_rank = None
        for i, e in enumerate(all_entries):
            rank = i + 1
            is_me = e["_id"] == uid
            if is_me:
                my_rank = rank
            entries.append(
                {
                    "rank": rank,
                    "label": f"User #{rank}",
                    "value": e["count"],
                    "secondary": f"of {len(ACHIEVEMENTS)}",
                    "is_you": is_me,
                }
            )

        if my_rank is None:
            my_count = await db.user_achievements.count_documents({"user_id": uid, "type": "achievement"})
            rank_count = len([e for e in all_entries if e["count"] > my_count])
            my_rank = rank_count + 1
            entries.append(
                {
                    "rank": my_rank,
                    "label": f"User #{my_rank}",
                    "value": my_count,
                    "secondary": f"of {len(ACHIEVEMENTS)}",
                    "is_you": True,
                }
            )

    else:  # streak
        pipeline = [
            {
                "$project": {
                    "_id": 0,
                    "user_id": 1,
                    "streak": {"$max": [{"$ifNull": ["$current_streak", 0]}, {"$ifNull": ["$longest_streak", 0]}]},
                }
            },
            {"$sort": {"streak": -1}},
            {"$limit": 100},
        ]
        all_entries = await db.progress.aggregate(pipeline).to_list(100)
        entries = []
        my_rank = None
        for i, e in enumerate(all_entries):
            rank = i + 1
            is_me = e["user_id"] == uid
            if is_me:
                my_rank = rank
            entries.append(
                {
                    "rank": rank,
                    "label": f"User #{rank}",
                    "value": e.get("streak", 0),
                    "secondary": "days",
                    "is_you": is_me,
                }
            )

        if my_rank is None:
            my_prog = (
                await db.progress.find_one({"user_id": uid}, {"_id": 0, "current_streak": 1, "longest_streak": 1}) or {}
            )
            my_streak = max(my_prog.get("current_streak", 0), my_prog.get("longest_streak", 0))
            rank_count = await db.progress.count_documents(
                {
                    "$expr": {
                        "$gt": [
                            {"$max": [{"$ifNull": ["$current_streak", 0]}, {"$ifNull": ["$longest_streak", 0]}]},
                            my_streak,
                        ]
                    }
                }
            )
            my_rank = rank_count + 1
            entries.append(
                {
                    "rank": my_rank,
                    "label": f"User #{my_rank}",
                    "value": my_streak,
                    "secondary": "days",
                    "is_you": True,
                }
            )

    total_users = await db.progress.count_documents({})
    metric_labels = {"xp": "XP & Level", "achievements": "Achievements", "streak": "Best Streak"}

    # Ensure user's entry is always included
    top_entries = [e for e in entries if not e["is_you"]][:49]
    my_entry = next((e for e in entries if e["is_you"]), None)
    final_entries = top_entries
    if my_entry:
        # Insert at correct position
        inserted = False
        for i, e in enumerate(final_entries):
            if e["rank"] >= my_entry["rank"]:
                final_entries.insert(i, my_entry)
                inserted = True
                break
        if not inserted:
            final_entries.append(my_entry)

    return {
        "metric": metric,
        "metric_label": metric_labels.get(metric, metric),
        "entries": final_entries[:50],
        "my_rank": my_rank,
        "total_users": max(total_users, 1),
    }
