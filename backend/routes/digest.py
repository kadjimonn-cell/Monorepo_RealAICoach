"""Weekly Digest routes: Smart per-user weekly coaching progress + streak digests."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from .db import db, EMERGENT_LLM_KEY, logger, require_auth, require_admin
from emergentintegrations.llm.chat import LlmChat, UserMessage
import uuid

router = APIRouter()

FALLBACK_SMART_TIP = (
    "Consistency beats intensity: one focused 15-minute practice session tomorrow "
    "keeps your streak alive and compounds your coaching progress."
)


def _resp_text(response):
    return response.text if hasattr(response, "text") else str(response)


class DigestPreferencesRequest(BaseModel):
    user_id: str
    email_enabled: bool = True
    frequency: str = "weekly"
    preferred_day: str = "monday"
    preferred_time: str = "08:00"
    include_sections: list = ["progress", "tips", "challenges", "motivation"]


@router.get("/weekly-digest/{user_id}")
async def get_weekly_digest(user_id: str):
    """Generate a personalized weekly digest for the user."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Gather user activity data
    usage_count = await db.usage_analytics.count_documents(
        {"user_id": user_id, "timestamp": {"$gte": week_ago.isoformat()}}
    )

    conversations = await db.conversations.count_documents(
        {"user_id": user_id, "created_at": {"$gte": week_ago.isoformat()}}
    )

    lifegame_char = await db.lifegame_characters.find_one({"user_id": user_id}, {"_id": 0})
    quests_completed = lifegame_char.get("quests_completed", 0) if lifegame_char else 0
    level = lifegame_char.get("level", 1) if lifegame_char else 1

    # Recent feature usage breakdown
    pipeline = [
        {"$match": {"user_id": user_id, "timestamp": {"$gte": week_ago.isoformat()}}},
        {"$group": {"_id": "$feature_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top_features = await db.usage_analytics.aggregate(pipeline).to_list(5)
    feature_breakdown = [{"feature": f["_id"], "count": f["count"]} for f in top_features]

    # Search alerts: new matching internal + external roles since last digest run
    try:
        from .job_search import collect_search_alert_matches

        search_alerts = await collect_search_alert_matches(user_id, update_last_run=True)
    except Exception as e:
        logger.error(f"Digest search alerts error: {e}")
        search_alerts = []

    # Generate AI insights
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"digest-{user_id}-{uuid.uuid4().hex[:8]}",
            system_message="You are a helpful AI life coach generating a weekly progress digest.",
        )

        prompt = f"""Generate a motivating weekly digest for a user with this activity:
- AI Feature Interactions: {usage_count}
- Practice Sessions: {conversations}
- LifeGame Level: {level}, Quests Completed: {quests_completed}
- Top Features Used: {feature_breakdown}

Create a brief, encouraging digest with:
1. Progress Summary (2-3 sentences)
2. Key Achievement of the Week
3. Personalized Tip for Next Week
4. Motivational Quote

Keep it concise and warm. Max 200 words total."""

        response = await chat.send_message(UserMessage(text=prompt))
        ai_content = _resp_text(response)
    except Exception as e:
        logger.error(f"Digest AI error: {e}")
        ai_content = None

    digest = {
        "digest_id": f"digest_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "period": {"start": week_ago.isoformat(), "end": now.isoformat()},
        "stats": {
            "total_interactions": usage_count,
            "practice_sessions": conversations,
            "lifegame_level": level,
            "quests_completed": quests_completed,
            "top_features": feature_breakdown,
        },
        "ai_insights": ai_content or "Keep up the great work! Every interaction brings you closer to your goals.",
        "search_alerts": search_alerts,
        "generated_at": now.isoformat(),
    }

    # Save digest
    await db.weekly_digests.insert_one({**digest})

    return digest


@router.get("/weekly-digest/history/{user_id}")
async def get_digest_history(user_id: str, limit: int = 10):
    digests = (
        await db.weekly_digests.find({"user_id": user_id}, {"_id": 0})
        .sort("generated_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    return {"digests": digests}


@router.get("/weekly-digest/preferences/{user_id}")
async def get_digest_preferences(user_id: str):
    prefs = await db.digest_preferences.find_one({"user_id": user_id}, {"_id": 0})
    if not prefs:
        prefs = {
            "user_id": user_id,
            "email_enabled": True,
            "frequency": "weekly",
            "preferred_day": "monday",
            "preferred_time": "08:00",
            "include_sections": ["progress", "tips", "challenges", "motivation"],
        }
    return prefs


@router.put("/weekly-digest/preferences")
async def update_digest_preferences(request: DigestPreferencesRequest):
    data = request.dict()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.digest_preferences.update_one({"user_id": request.user_id}, {"$set": data}, upsert=True)
    return {"success": True, "preferences": data}


# ── Smart Weekly Digest (premium chrome, streaks + coaching progress) ──


def _iso_week_key(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


async def _build_smart_digest_data(user_id: str) -> dict:
    """Aggregate coaching progress + streak data for the smart weekly digest."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    sessions = await db.conversations.count_documents(
        {"user_id": user_id, "created_at": {"$gte": week_ago.isoformat()}}
    )

    profile = await db.gamification_profiles.find_one({"user_id": user_id}, {"_id": 0}) or {}
    streak_days = int(profile.get("current_streak", 0) or 0)
    longest_streak = int(profile.get("longest_streak", 0) or 0)
    xp_earned = int(profile.get("weekly_xp", 0) or 0)
    total_xp = int(profile.get("xp", 0) or 0)

    # Per-day activity map for the trailing 7 days (oldest → today)
    day_docs = await db.usage_analytics.aggregate([
        {"$match": {"user_id": user_id, "timestamp": {"$gte": week_ago.isoformat()}}},
        {"$group": {"_id": {"$substr": ["$timestamp", 0, 10]}}},
    ]).to_list(10)
    active_dates = {d["_id"] for d in day_docs}
    convo_docs = await db.conversations.aggregate([
        {"$match": {"user_id": user_id, "created_at": {"$gte": week_ago.isoformat()}}},
        {"$group": {"_id": {"$substr": ["$created_at", 0, 10]}}},
    ]).to_list(10)
    active_dates |= {d["_id"] for d in convo_docs}

    days = [(now - timedelta(days=offset)).date() for offset in range(6, -1, -1)]
    active_day_map = [d.isoformat() in active_dates for d in days]
    day_labels = [d.strftime("%a")[0] for d in days]
    active_days = sum(active_day_map)

    top_features = await db.usage_analytics.aggregate([
        {"$match": {"user_id": user_id, "timestamp": {"$gte": week_ago.isoformat()}}},
        {"$group": {"_id": "$feature_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 3},
    ]).to_list(3)

    highlights = []
    if sessions > 0:
        highlights.append(f"Completed {sessions} coaching session{'s' if sessions != 1 else ''} this week")
    if streak_days > 0:
        highlights.append(f"Kept a {streak_days}-day practice streak going")
    if xp_earned > 0:
        highlights.append(f"Earned {xp_earned} XP toward your next level")
    if top_features:
        names = [str(f.get("_id") or "AI Tool").replace("_", " ").title() for f in top_features]
        highlights.append(f"Most used tools: {', '.join(names)}")
    if not highlights:
        highlights.append("A fresh week ahead — one short session today starts a brand-new streak")

    week_label = f"Week of {days[0].strftime('%b %d')} – {days[-1].strftime('%b %d, %Y')}"

    return {
        "streak_days": streak_days,
        "longest_streak": max(longest_streak, streak_days),
        "active_day_map": active_day_map,
        "day_labels": day_labels,
        "sessions": sessions,
        "active_days": active_days,
        "xp_earned": xp_earned,
        "total_xp": total_xp,
        "highlights": highlights,
        "week_label": week_label,
    }


async def _generate_smart_tip(user_name: str, data: dict) -> str:
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"smart-digest-{uuid.uuid4().hex[:8]}",
            system_message="You are an elite career coach. Reply with ONE actionable, specific, motivating coaching tip in max 45 words. No greetings, no emojis, no quotes.",
        )
        prompt = (
            f"User {user_name}: streak {data['streak_days']} days (best {data['longest_streak']}), "
            f"{data['sessions']} coaching sessions, {data['active_days']}/7 active days, "
            f"+{data['xp_earned']} XP this week. Give next week's single smartest tip."
        )
        response = await chat.send_message(UserMessage(text=prompt))
        tip = _resp_text(response).strip().strip('"')
        return tip[:400] if tip else FALLBACK_SMART_TIP
    except Exception as e:
        logger.warning(f"Smart digest tip AI fallback: {e}")
        return FALLBACK_SMART_TIP


async def _send_smart_digest_for_user(user_id: str, force: bool = False, with_ai_tip: bool = True) -> dict:
    """Build and send the smart weekly digest. Idempotent per user per ISO week."""
    from utils.email_service import is_email_configured, send_catalog_template

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    user_email = (user_doc.get("email") or "").strip()
    if not user_email:
        raise HTTPException(status_code=400, detail="User has no email address")

    prefs = await db.digest_preferences.find_one({"user_id": user_id}, {"_id": 0})
    if prefs and not prefs.get("email_enabled", True):
        return {"success": True, "skipped": True, "reason": "digest_email_disabled"}

    now = datetime.now(timezone.utc)
    week_key = _iso_week_key(now)
    existing = await db.weekly_digest_sends.find_one({"user_id": user_id, "week_key": week_key}, {"_id": 0})
    if existing and not force:
        return {"success": True, "skipped": True, "reason": "already_sent_this_week", "week_key": week_key}

    user_name = user_doc.get("name") or user_email.split("@")[0]
    data = await _build_smart_digest_data(user_id)
    smart_tip = await _generate_smart_tip(user_name, data) if with_ai_tip else FALLBACK_SMART_TIP

    payload = {"user_name": user_name, "smart_tip": smart_tip, **data}

    if not is_email_configured():
        return {"success": True, "preview": True, "digest": payload, "note": "Email service not configured — preview only"}

    result = await send_catalog_template(
        recipient_email=user_email,
        template_key="smart_weekly_digest",
        recipient_name=user_name,
        **payload,
    )

    if result.get("success"):
        await db.weekly_digest_sends.update_one(
            {"user_id": user_id, "week_key": week_key},
            {"$set": {
                "user_id": user_id,
                "week_key": week_key,
                "send_id": f"swd_{uuid.uuid4().hex[:12]}",
                "sent_at": now.isoformat(),
                "streak_days": data["streak_days"],
                "sessions": data["sessions"],
                "forced": bool(force),
            }},
            upsert=True,
        )

    return {"success": bool(result.get("success")), "skipped": False, "week_key": week_key, "digest": payload, "email_result": result}


@router.post("/weekly-digest/send-email/{user_id}")
async def send_weekly_digest_email(user_id: str, request: Request, force: bool = False):
    """Send the smart weekly digest to a user (self or admin only). Idempotent per ISO week."""
    actor = await require_auth(request)
    if actor.user_id != user_id and not getattr(actor, "is_admin", False):
        raise HTTPException(status_code=403, detail="You can only send your own digest")
    return await _send_smart_digest_for_user(user_id, force=force)


@router.post("/weekly-digest/send-all")
async def send_weekly_digest_to_all(request: Request):
    """Send smart weekly digest emails to all opted-in active users (admin only)."""
    await require_admin(request)
    return await dispatch_smart_weekly_digests()


async def dispatch_smart_weekly_digests() -> dict:
    """Bulk dispatch used by the Monday scheduler job and the admin send-all endpoint."""
    users = await db.users.find(
        {"email": {"$exists": True, "$ne": ""}, "subscription_status": {"$in": ["active", None]}},
        {"_id": 0, "user_id": 1},
    ).to_list(5000)
    sent = skipped = errors = 0

    for user_doc in users:
        uid = user_doc.get("user_id")
        if not uid:
            continue
        try:
            result = await _send_smart_digest_for_user(uid, force=False)
            if result.get("skipped"):
                skipped += 1
            elif result.get("success"):
                sent += 1
            else:
                errors += 1
        except HTTPException:
            skipped += 1
        except Exception as e:
            logger.error(f"Smart weekly digest error for {uid}: {e}")
            errors += 1

    summary = {"sent": sent, "skipped": skipped, "errors": errors, "total_users": len(users)}
    logger.info(f"Smart weekly digest dispatch: {summary}")
    return summary
