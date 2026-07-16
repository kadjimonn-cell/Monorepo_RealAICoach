"""Coaching Streak & Gamification routes: streak tracking, badges, analytics, email notifications."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import uuid
from .db import db, get_current_user

router = APIRouter()

# ── Badge Definitions ──
STREAK_BADGES = [
    {
        "id": "streak_3",
        "name": "First Spark",
        "description": "Complete 3 consecutive days of coaching",
        "days_required": 3,
        "tier": "bronze",
        "color": "#CD7F32",
        "image": "https://static.prod-images.emergentagent.com/jobs/7c9bd262-5bc3-4dae-a553-eec82dfc8198/images/915572ebf2dd40dace38ef1d876b4be10f56b9efc4a4f2629366263a08b95652.png",
    },
    {
        "id": "streak_7",
        "name": "Week Warrior",
        "description": "7-day coaching streak",
        "days_required": 7,
        "tier": "silver",
        "color": "#C0C0C0",
        "image": "https://static.prod-images.emergentagent.com/jobs/7c9bd262-5bc3-4dae-a553-eec82dfc8198/images/21ffab48563112da219cda54bb01cfb94f5e210e6bf4494fdd81290eb1a6dc37.png",
    },
    {
        "id": "streak_14",
        "name": "Fortnight Focus",
        "description": "14-day coaching streak",
        "days_required": 14,
        "tier": "gold",
        "color": "#FFD700",
        "image": "https://static.prod-images.emergentagent.com/jobs/7c9bd262-5bc3-4dae-a553-eec82dfc8198/images/4e4f636a190f6dfdc2688a3111b7d1db3884300e380f7439d195ebc5e194739a.png",
    },
    {
        "id": "streak_30",
        "name": "Monthly Master",
        "description": "30-day coaching streak",
        "days_required": 30,
        "tier": "platinum",
        "color": "#A855F7",
        "image": "https://static.prod-images.emergentagent.com/jobs/7c9bd262-5bc3-4dae-a553-eec82dfc8198/images/83c30cbbd8fbcb776a8263d59212520cbba4a4afe1f7db3cc8401e5a81f46d6e.png",
    },
    {
        "id": "streak_60",
        "name": "Elite Coach",
        "description": "60-day coaching streak",
        "days_required": 60,
        "tier": "diamond",
        "color": "#EF4444",
        "image": "https://static.prod-images.emergentagent.com/jobs/7c9bd262-5bc3-4dae-a553-eec82dfc8198/images/804384190dfff44107f1720fa093f9727723eb853c625cbd924113cce2f9e6ec.png",
    },
    {
        "id": "streak_100",
        "name": "Legendary",
        "description": "100-day coaching streak",
        "days_required": 100,
        "tier": "legendary",
        "color": "#EC4899",
        "image": "https://static.prod-images.emergentagent.com/jobs/7c9bd262-5bc3-4dae-a553-eec82dfc8198/images/8d80ad92fe7033d3ac008232777e78fc30dd2278886f259e2aaa8b456915c227.png",
    },
]


# ── Streak Tracking ──


def _compute_shields(current_streak: int, shields_used: int) -> int:
    """Earn 1 shield per 7-day streak completed. Max 3 shields banked."""
    earned = current_streak // 7
    available = max(0, min(3, earned - shields_used))
    return available


@router.get("/coaching/streak/{user_id}")
async def get_coaching_streak(user_id: str):
    """Get user's coaching streak data including shields."""
    doc = await db.coaching_streaks.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        doc = {
            "user_id": user_id,
            "current_streak": 0,
            "longest_streak": 0,
            "last_session_date": None,
            "total_coaching_days": 0,
            "streak_frozen": False,
            "shields_available": 0,
            "shields_used": 0,
            "shields_earned_total": 0,
        }
    # Compute if streak is still active (allow 1-day grace or shield)
    if doc.get("last_session_date"):
        last = doc["last_session_date"]
        if isinstance(last, str):
            last_date = datetime.fromisoformat(last).date()
        else:
            last_date = last.date() if hasattr(last, "date") else last
        today = datetime.now(timezone.utc).date()
        gap = (today - last_date).days
        shields = _compute_shields(doc.get("current_streak", 0), doc.get("shields_used", 0))
        if gap > 1 and not doc.get("streak_frozen"):
            if gap == 2 and shields > 0:
                # Auto-use a shield to save the streak
                doc["streak_active"] = True
                doc["shield_protecting"] = True
            else:
                doc["current_streak"] = 0
                doc["streak_active"] = False
                doc["shield_protecting"] = False
        else:
            doc["streak_active"] = gap <= 1 or doc.get("streak_frozen", False)
            doc["shield_protecting"] = False
        doc["practiced_today"] = gap == 0
        doc["shields_available"] = shields
    else:
        doc["streak_active"] = False
        doc["practiced_today"] = False
        doc["shields_available"] = 0
        doc["shield_protecting"] = False

    return doc


@router.post("/coaching/streak/record")
async def record_coaching_session(req: Request):
    """Record a coaching session and update streak."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user.user_id
    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()

    doc = await db.coaching_streaks.find_one({"user_id": user_id}, {"_id": 0})

    if not doc:
        doc = {
            "user_id": user_id,
            "current_streak": 0,
            "longest_streak": 0,
            "last_session_date": None,
            "total_coaching_days": 0,
            "streak_frozen": False,
        }

    last_date = None
    if doc.get("last_session_date"):
        last = doc["last_session_date"]
        if isinstance(last, str):
            last_date = datetime.fromisoformat(last).date()
        else:
            last_date = last.date() if hasattr(last, "date") else last

    # Already practiced today
    if last_date == today:
        return {
            "message": "Already recorded today",
            "current_streak": doc["current_streak"],
            "longest_streak": doc["longest_streak"],
            "new_badges": [],
        }

    if last_date and (today - last_date).days == 1:
        new_streak = doc["current_streak"] + 1
    elif last_date and (today - last_date).days == 2:
        # Missed 1 day — use a shield if available
        shields = _compute_shields(doc["current_streak"], doc.get("shields_used", 0))
        if shields > 0:
            new_streak = doc["current_streak"] + 1
            await db.coaching_streaks.update_one(
                {"user_id": user_id},
                {"$inc": {"shields_used": 1}},
            )
        else:
            new_streak = 1
    else:
        new_streak = 1

    longest = max(doc.get("longest_streak", 0), new_streak)
    total_days = doc.get("total_coaching_days", 0) + 1
    shields_earned = new_streak // 7

    await db.coaching_streaks.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "current_streak": new_streak,
                "longest_streak": longest,
                "last_session_date": today_str,
                "total_coaching_days": total_days,
                "streak_frozen": False,
                "shields_earned_total": shields_earned,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    # Check for new badges
    earned = await db.coaching_badges.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    earned_ids = {b["badge_id"] for b in earned}
    new_badges = []

    for badge in STREAK_BADGES:
        if badge["id"] not in earned_ids and new_streak >= badge["days_required"]:
            badge_record = {
                "id": f"ub_{uuid.uuid4().hex[:8]}",
                "user_id": user_id,
                "badge_id": badge["id"],
                "earned_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.coaching_badges.insert_one({**badge_record})
            new_badges.append(badge)

            # Create in-app notification for badge
            await db.notifications.insert_one(
                {
                    "id": f"notif_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "type": "badge_earned",
                    "title": f"Badge Earned: {badge['name']}!",
                    "message": f"You've earned the '{badge['name']}' badge for a {badge['days_required']}-day coaching streak!",
                    "read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    return {
        "current_streak": new_streak,
        "longest_streak": longest,
        "total_coaching_days": total_days,
        "new_badges": new_badges,
        "practiced_today": True,
    }


@router.get("/coaching/badges/{user_id}")
async def get_badges(user_id: str):
    """Get all badges — earned and locked."""
    earned = await db.coaching_badges.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    earned_ids = {b["badge_id"] for b in earned}
    earned_map = {b["badge_id"]: b for b in earned}

    badges = []
    for b in STREAK_BADGES:
        badges.append(
            {
                **b,
                "earned": b["id"] in earned_ids,
                "earned_at": earned_map[b["id"]]["earned_at"] if b["id"] in earned_map else None,
            }
        )
    return {"badges": badges, "total_earned": len(earned_ids), "total_available": len(STREAK_BADGES)}


# ── Voice AI Session Analytics ──


@router.get("/coaching/analytics/{user_id}")
async def get_coaching_analytics(user_id: str):
    """Get comprehensive voice coaching analytics."""
    sessions = await db.voice_sessions.find({"user_id": user_id}, {"_id": 0}).to_list(500)

    total_sessions = len(sessions)
    total_messages = sum(len(s.get("messages", [])) for s in sessions)
    user_messages = sum(1 for s in sessions for m in s.get("messages", []) if m.get("role") == "user")

    # Words spoken (user messages only)
    total_words = sum(
        len(m.get("text", "").split()) for s in sessions for m in s.get("messages", []) if m.get("role") == "user"
    )

    # Scenario breakdown
    scenario_counts = {}
    for s in sessions:
        sid = s.get("scenario_id") or "free_chat"
        scenario_counts[sid] = scenario_counts.get(sid, 0) + 1

    # Sessions per day (last 7 days)
    daily_activity = {}
    for s in sessions:
        created = s.get("created_at", "")
        if created:
            try:
                day = created[:10]
                daily_activity[day] = daily_activity.get(day, 0) + 1
            except Exception:
                pass

    # Last 7 days activity
    today = datetime.now(timezone.utc).date()
    week_activity = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        week_activity.append({"date": d, "sessions": daily_activity.get(d, 0)})

    # Streak data
    streak = await db.coaching_streaks.find_one({"user_id": user_id}, {"_id": 0})

    return {
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "user_messages": user_messages,
        "total_words_spoken": total_words,
        "scenario_breakdown": scenario_counts,
        "weekly_activity": week_activity,
        "current_streak": streak.get("current_streak", 0) if streak else 0,
        "longest_streak": streak.get("longest_streak", 0) if streak else 0,
        "total_coaching_days": streak.get("total_coaching_days", 0) if streak else 0,
        "avg_messages_per_session": round(total_messages / max(total_sessions, 1), 1),
        "avg_words_per_message": round(total_words / max(user_messages, 1), 1),
    }


# ── Email Notification Queue (stored in DB, sends when SMTP configured) ──


class EmailNotification(BaseModel):
    user_id: str
    email_type: str
    subject: str
    body_html: str
    recipient_email: Optional[str] = None


@router.post("/notifications/email/queue")
async def queue_email(body: EmailNotification, req: Request):
    """Queue an email notification. Stored in DB for in-app viewing. Sends via SMTP when configured."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    email_record = {
        "id": f"email_{uuid.uuid4().hex[:12]}",
        "user_id": body.user_id,
        "email_type": body.email_type,
        "subject": body.subject,
        "body_html": body.body_html,
        "recipient_email": body.recipient_email or user.email,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_queue.insert_one({**email_record})

    # Also create in-app notification
    await db.notifications.insert_one(
        {
            "id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": body.user_id,
            "type": f"email_{body.email_type}",
            "title": body.subject,
            "message": f"Email queued: {body.subject}",
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    return {"success": True, "email_id": email_record["id"], "status": "pending"}


@router.get("/notifications/emails/{user_id}")
async def get_email_history(user_id: str):
    """Get user's email notification history."""
    emails = await db.email_queue.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    return {"emails": emails, "total": len(emails)}
