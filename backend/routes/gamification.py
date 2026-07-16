"""Gamification & Leaderboard System.

Features:
- Global leaderboard ranking by engagement score, streaks, achievements
- Weekly/monthly leaderboard cycles
- Badge collection with milestone unlocks
- XP system with level progression
- Achievement tracking and rewards
"""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
import uuid
import logging

from .db import db, require_auth, require_admin

router = APIRouter(prefix="/gamification")
logger = logging.getLogger("routes.gamification")

# Badge definitions
BADGES = {
    "first_login": {
        "name": "Welcome Aboard",
        "description": "Logged in for the first time",
        "icon": "flag",
        "color": "#3B82F6",
        "xp": 10,
    },
    "first_practice": {
        "name": "Practice Makes Perfect",
        "description": "Completed first practice session",
        "icon": "chatbubbles",
        "color": "#10B981",
        "xp": 25,
    },
    "streak_3": {
        "name": "On Fire",
        "description": "3-day activity streak",
        "icon": "flame",
        "color": "#EF4444",
        "xp": 50,
    },
    "streak_7": {
        "name": "Unstoppable",
        "description": "7-day activity streak",
        "icon": "flash",
        "color": "#F59E0B",
        "xp": 100,
    },
    "streak_30": {
        "name": "Legendary Streak",
        "description": "30-day activity streak",
        "icon": "trophy",
        "color": "#8B5CF6",
        "xp": 500,
    },
    "apps_3": {
        "name": "Explorer",
        "description": "Used 3 different mini-apps",
        "icon": "compass",
        "color": "#6366F1",
        "xp": 30,
    },
    "apps_5": {
        "name": "Power User",
        "description": "Used 5 different mini-apps",
        "icon": "rocket",
        "color": "#EC4899",
        "xp": 75,
    },
    "apps_9": {
        "name": "App Master",
        "description": "Used all 9 mini-apps",
        "icon": "star",
        "color": "#F59E0B",
        "xp": 200,
    },
    "first_booking": {
        "name": "Meeting Pro",
        "description": "Booked your first meeting",
        "icon": "calendar",
        "color": "#14B8A6",
        "xp": 25,
    },
    "bookings_10": {
        "name": "Networking Expert",
        "description": "Booked 10 meetings",
        "icon": "people",
        "color": "#3B82F6",
        "xp": 100,
    },
    "first_application": {
        "name": "Career Seeker",
        "description": "Submitted first job application",
        "icon": "briefcase",
        "color": "#6366F1",
        "xp": 25,
    },
    "applications_5": {
        "name": "Go-Getter",
        "description": "Applied to 5 positions",
        "icon": "documents",
        "color": "#10B981",
        "xp": 75,
    },
    "engagement_50": {
        "name": "Active Member",
        "description": "Reached 50 engagement score",
        "icon": "trending-up",
        "color": "#F59E0B",
        "xp": 50,
    },
    "engagement_100": {
        "name": "Top Performer",
        "description": "Maxed out engagement score",
        "icon": "medal",
        "color": "#EF4444",
        "xp": 200,
    },
    "level_5": {
        "name": "Rising Star",
        "description": "Reached Level 5",
        "icon": "sparkles",
        "color": "#8B5CF6",
        "xp": 100,
    },
    "level_10": {
        "name": "Veteran",
        "description": "Reached Level 10",
        "icon": "shield-checkmark",
        "color": "#3B82F6",
        "xp": 250,
    },
    "fps_first_blood": {
        "name": "First Blood",
        "description": "Scored your first FPS arena kill",
        "icon": "locate",
        "color": "#EF4444",
        "xp": 25,
    },
    "fps_double_kill": {
        "name": "Double Kill",
        "description": "Hit a 2-kill streak in the FPS arena",
        "icon": "flash",
        "color": "#F59E0B",
        "xp": 50,
    },
    "fps_killing_spree": {
        "name": "Killing Spree",
        "description": "Hit a 3-kill streak in the FPS arena",
        "icon": "flame",
        "color": "#F97316",
        "xp": 75,
    },
    "fps_rampage": {
        "name": "Rampage",
        "description": "Hit a 5-kill streak in the FPS arena",
        "icon": "skull",
        "color": "#DC2626",
        "xp": 125,
    },
    "fps_unstoppable": {
        "name": "Unstoppable Gunner",
        "description": "Hit a 7-kill streak in the FPS arena",
        "icon": "trophy",
        "color": "#8B5CF6",
        "xp": 200,
    },
    "fps_veteran": {
        "name": "Arena Veteran",
        "description": "Played 10 FPS arena matches",
        "icon": "medal",
        "color": "#14B8A6",
        "xp": 100,
    },
}

# XP thresholds for levels
LEVEL_THRESHOLDS = [0, 50, 125, 225, 375, 575, 825, 1125, 1500, 1950, 2500, 3150, 3900, 4800, 5900, 7200]


def get_level(xp: int) -> dict:
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
    next_threshold = LEVEL_THRESHOLDS[min(level, len(LEVEL_THRESHOLDS) - 1)]
    prev_threshold = LEVEL_THRESHOLDS[max(0, level - 2)] if level > 1 else 0
    progress = (
        ((xp - prev_threshold) / max(1, next_threshold - prev_threshold)) * 100
        if level <= len(LEVEL_THRESHOLDS)
        else 100
    )
    return {"level": level, "xp": xp, "next_level_xp": next_threshold, "progress": min(100, round(progress, 1))}


async def _get_or_create_profile(user_id: str) -> dict:
    profile = await db.gamification_profiles.find_one({"user_id": user_id}, {"_id": 0})
    if not profile:
        profile = {
            "user_id": user_id,
            "xp": 0,
            "badges": [],
            "current_streak": 0,
            "longest_streak": 0,
            "last_activity_date": None,
            "weekly_xp": 0,
            "monthly_xp": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.gamification_profiles.insert_one(profile)
        profile.pop("_id", None)
    return profile


async def award_badge(user_id: str, badge_id: str) -> bool:
    """Award a badge to a user if not already earned."""
    if badge_id not in BADGES:
        return False
    profile = await _get_or_create_profile(user_id)
    if badge_id in profile.get("badges", []):
        return False

    badge = BADGES[badge_id]
    xp_gain = badge["xp"]

    await db.gamification_profiles.update_one(
        {"user_id": user_id},
        {
            "$push": {"badges": badge_id},
            "$inc": {"xp": xp_gain, "weekly_xp": xp_gain, "monthly_xp": xp_gain},
        },
    )

    # Store badge award event
    await db.gamification_events.insert_one(
        {
            "event_id": f"gev_{uuid.uuid4().hex[:10]}",
            "user_id": user_id,
            "type": "badge_earned",
            "badge_id": badge_id,
            "xp_gained": xp_gain,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Notify user
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=user_id,
            notif_type="badge_earned",
            title=f"Badge Earned: {badge['name']}",
            body=f"{badge['description']} (+{xp_gain} XP)",
            action_url="/leaderboard",
        )
    except Exception as e:
        logger.error(f"Badge notification failed: {e}")

    # Check for level-up badges
    updated = await db.gamification_profiles.find_one({"user_id": user_id}, {"_id": 0, "xp": 1})
    new_xp = updated.get("xp", 0)
    level_info = get_level(new_xp)
    if level_info["level"] >= 5 and "level_5" not in profile.get("badges", []) and badge_id != "level_5":
        await award_badge(user_id, "level_5")
    if level_info["level"] >= 10 and "level_10" not in profile.get("badges", []) and badge_id != "level_10":
        await award_badge(user_id, "level_10")

    return True


async def add_xp(user_id: str, amount: int, reason: str = "activity"):
    """Add XP to a user's profile."""
    await _get_or_create_profile(user_id)
    await db.gamification_profiles.update_one(
        {"user_id": user_id},
        {"$inc": {"xp": amount, "weekly_xp": amount, "monthly_xp": amount}},
    )
    await db.gamification_events.insert_one(
        {
            "event_id": f"gev_{uuid.uuid4().hex[:10]}",
            "user_id": user_id,
            "type": "xp_gained",
            "xp_gained": amount,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


async def update_streak(user_id: str):
    """Update the user's daily activity streak."""
    profile = await _get_or_create_profile(user_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last = profile.get("last_activity_date")

    if last == today:
        return profile.get("current_streak", 0)

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    if last == yesterday:
        new_streak = profile.get("current_streak", 0) + 1
    else:
        new_streak = 1

    longest = max(profile.get("longest_streak", 0), new_streak)
    await db.gamification_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"current_streak": new_streak, "longest_streak": longest, "last_activity_date": today}},
    )

    # Award streak badges
    if new_streak >= 3:
        await award_badge(user_id, "streak_3")
    if new_streak >= 7:
        await award_badge(user_id, "streak_7")
    if new_streak >= 30:
        await award_badge(user_id, "streak_30")

    # XP for daily login
    await add_xp(user_id, 5, "daily_login")
    return new_streak


# ── API Endpoints ──


@router.get("/profile")
async def get_gamification_profile(request: Request):
    """Get current user's gamification profile."""
    user = await require_auth(request)
    profile = await _get_or_create_profile(user.user_id)

    # Update streak on visit
    streak = await update_streak(user.user_id)
    profile["current_streak"] = streak

    # Re-fetch for updated XP
    profile = await db.gamification_profiles.find_one({"user_id": user.user_id}, {"_id": 0})
    level_info = get_level(profile.get("xp", 0))

    # Enrich badges with metadata
    earned_badges = []
    for bid in profile.get("badges", []):
        if bid in BADGES:
            earned_badges.append({**BADGES[bid], "id": bid, "earned": True})

    unearned_badges = []
    for bid, badge in BADGES.items():
        if bid not in profile.get("badges", []):
            unearned_badges.append({**badge, "id": bid, "earned": False})

    return {
        **profile,
        "level": level_info,
        "earned_badges": earned_badges,
        "unearned_badges": unearned_badges,
        "total_badges": len(BADGES),
        "earned_count": len(earned_badges),
    }


@router.get("/leaderboard")
async def get_leaderboard(request: Request, period: str = "all_time"):
    """Get the current user's private leaderboard stats only. No other users' data exposed."""
    user = await require_auth(request)

    sort_field = "xp"
    if period == "weekly":
        sort_field = "weekly_xp"
    elif period == "monthly":
        sort_field = "monthly_xp"

    profile = await _get_or_create_profile(user.user_id)
    my_xp = profile.get(sort_field, 0)
    my_rank = await db.gamification_profiles.count_documents({sort_field: {"$gt": my_xp}}) + 1
    total_participants = await db.gamification_profiles.count_documents({})
    level_info = get_level(profile.get("xp", 0))

    # Build user's earned badges detail
    earned_ids = profile.get("badges", [])
    badges_detail = []
    for bid in earned_ids:
        if bid in BADGES:
            b = BADGES[bid]
            badges_detail.append({"id": bid, "name": b["name"], "icon": b["icon"], "color": b["color"], "xp": b["xp"]})

    # Percentile calculation
    percentile = (
        round(((total_participants - my_rank) / max(1, total_participants)) * 100, 1) if total_participants > 0 else 0
    )

    # Milestones
    milestones = []
    for tid, t in BADGES.items():
        milestones.append(
            {
                "id": tid,
                "name": t["name"],
                "description": t["description"],
                "icon": t["icon"],
                "color": t["color"],
                "xp": t["xp"],
                "earned": tid in earned_ids,
            }
        )

    return {
        "period": period,
        "my_rank": my_rank,
        "total_participants": total_participants,
        "percentile": percentile,
        "xp": my_xp,
        "total_xp": profile.get("xp", 0),
        "weekly_xp": profile.get("weekly_xp", 0),
        "monthly_xp": profile.get("monthly_xp", 0),
        "level": level_info,
        "current_streak": profile.get("current_streak", 0),
        "longest_streak": profile.get("longest_streak", 0),
        "badges_earned": badges_detail,
        "badges_count": len(earned_ids),
        "total_badges": len(BADGES),
        "milestones": milestones,
    }


@router.get("/badges")
async def get_all_badges(request: Request):
    """Get all available badges with their status for the current user."""
    user = await require_auth(request)
    profile = await _get_or_create_profile(user.user_id)
    earned = set(profile.get("badges", []))

    badges = []
    for bid, badge in BADGES.items():
        badges.append({**badge, "id": bid, "earned": bid in earned})

    return {"badges": badges, "earned_count": len(earned), "total": len(BADGES)}


@router.post("/check-achievements")
async def check_achievements(request: Request):
    """Check and award any pending achievements based on user activity."""
    user = await require_auth(request)
    uid = user.user_id
    awarded = []

    # Check practice sessions
    practice_count = await db.practice_sessions.count_documents({"user_id": uid})
    if practice_count >= 1:
        if await award_badge(uid, "first_practice"):
            awarded.append("first_practice")

    # Check mini-app usage
    apps_used = await db.ai_engagement_events.distinct("page", {"user_id": uid, "event_type": "mini_app_open"})
    if len(apps_used) >= 3:
        if await award_badge(uid, "apps_3"):
            awarded.append("apps_3")
    if len(apps_used) >= 5:
        if await award_badge(uid, "apps_5"):
            awarded.append("apps_5")
    if len(apps_used) >= 9:
        if await award_badge(uid, "apps_9"):
            awarded.append("apps_9")

    # Check bookings
    booking_count = await db.calendar_bookings.count_documents({"user_id": uid})
    if booking_count >= 1:
        if await award_badge(uid, "first_booking"):
            awarded.append("first_booking")
    if booking_count >= 10:
        if await award_badge(uid, "bookings_10"):
            awarded.append("bookings_10")

    # Check applications
    app_count = await db.applications.count_documents({"user_id": uid})
    if app_count >= 1:
        if await award_badge(uid, "first_application"):
            awarded.append("first_application")
    if app_count >= 5:
        if await award_badge(uid, "applications_5"):
            awarded.append("applications_5")

    # Check engagement
    eng = await db.ai_engagement.find_one({"user_id": uid}, {"_id": 0, "score": 1})
    if eng and eng.get("score", 0) >= 50:
        if await award_badge(uid, "engagement_50"):
            awarded.append("engagement_50")
    if eng and eng.get("score", 0) >= 100:
        if await award_badge(uid, "engagement_100"):
            awarded.append("engagement_100")

    # First login badge
    if await award_badge(uid, "first_login"):
        awarded.append("first_login")

    return {"awarded": awarded, "count": len(awarded)}


@router.get("/activity-feed")
async def get_activity_feed(request: Request, limit: int = 20):
    """Get recent gamification events across the platform."""
    await require_auth(request)
    events = (
        await db.gamification_events.find({"type": "badge_earned"}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )

    # Enrich with names
    feed = []
    for ev in events:
        user_doc = await db.users.find_one({"user_id": ev["user_id"]}, {"_id": 0, "name": 1})
        badge = BADGES.get(ev.get("badge_id", ""), {})
        feed.append(
            {
                "event_id": ev["event_id"],
                "user_name": user_doc.get("name", "A user") if user_doc else "A user",
                "badge_name": badge.get("name", "Unknown Badge"),
                "badge_icon": badge.get("icon", "star"),
                "badge_color": badge.get("color", "#3B82F6"),
                "xp_gained": ev.get("xp_gained", 0),
                "created_at": ev.get("created_at", ""),
            }
        )

    return {"feed": feed}


# ── Streak-protection nudge ──


async def run_streak_protection_nudge() -> dict:
    """Warn users whose activity streak (>=3 days) dies at UTC midnight without activity today.

    Idempotent per user per day via `streak_nudge_log`.
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    hours_left = max(1, 24 - now.hour)
    notified = 0
    skipped = 0
    cursor = db.gamification_profiles.find(
        {"current_streak": {"$gte": 3}, "last_activity_date": yesterday},
        {"_id": 0, "user_id": 1, "current_streak": 1},
    )
    async for profile in cursor:
        uid = str(profile.get("user_id") or "")
        if not uid:
            skipped += 1
            continue
        already = await db.streak_nudge_log.find_one({"user_id": uid, "date_key": today}, {"_id": 0})
        if already:
            skipped += 1
            continue
        streak = int(profile.get("current_streak") or 0)
        try:
            from utils.notification_helper import create_notification

            await create_notification(
                uid,
                f"Your {streak}-day streak expires in {hours_left}h",
                f"You're on a {streak}-day activity streak — do any activity before midnight UTC to keep it alive.",
                notif_type="streak_protection_nudge",
                data={"streak": streak, "hours_left": hours_left, "route": "/dashboard"},
            )
            await db.streak_nudge_log.insert_one(
                {"user_id": uid, "date_key": today, "streak": streak, "created_at": now.isoformat()}
            )
            notified += 1
        except Exception as exc:
            logger.warning(f"streak nudge failed for {uid}: {exc}")
            skipped += 1
    return {"notified": notified, "skipped": skipped, "date_key": today, "hours_left": hours_left}


@router.post("/streak-nudge/run")
async def trigger_streak_nudge(request: Request):
    """Admin-only manual trigger for the streak-protection nudge job."""
    await require_admin(request)
    return await run_streak_protection_nudge()

