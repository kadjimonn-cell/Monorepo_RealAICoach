"""Flappy Bird Streak Saver — daily reminder when an arcade streak is about to expire.

A streak is "at risk" when the user completed yesterday's daily challenge but
has not completed today's. The scheduler triggers this once per day at 17:00
UTC (7 hours before the streak breaks at midnight UTC).
"""

import logging
from datetime import datetime, timedelta, timezone

from routes.db import db

logger = logging.getLogger(__name__)

BATCH_CAP = 500


def _day_key(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=offset_days)).isoformat()


async def find_at_risk_users() -> list[dict]:
    """Users who completed yesterday's challenge but not today's."""
    today, yesterday = _day_key(0), _day_key(1)
    yesterday_docs = await db.flappy_bird_daily.find(
        {"day_key": yesterday}, {"_id": 0, "user_id": 1}
    ).to_list(BATCH_CAP * 4)
    candidate_ids = list({str(d["user_id"]) for d in yesterday_docs})
    if not candidate_ids:
        return []
    done_today = await db.flappy_bird_daily.find(
        {"day_key": today, "user_id": {"$in": candidate_ids}}, {"_id": 0, "user_id": 1}
    ).to_list(len(candidate_ids))
    done_ids = {str(d["user_id"]) for d in done_today}
    return [{"user_id": uid} for uid in candidate_ids if uid not in done_ids][:BATCH_CAP]


async def _streak_for(user_id: str) -> int:
    docs = await (
        db.flappy_bird_daily
        .find({"user_id": user_id}, {"_id": 0, "day_key": 1})
        .sort("day_key", -1)
        .to_list(400)
    )
    completed = {str(d["day_key"]) for d in docs}
    streak = 0
    cursor = datetime.now(timezone.utc).date() - timedelta(days=1)
    while cursor.isoformat() in completed:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def send_streak_saver_reminders() -> int:
    """Send at-risk streak reminders. Returns number of emails sent."""
    from routes.flappy_bird import daily_challenge_target, _personal_stats
    from utils.email_service import send_catalog_template

    today = _day_key(0)
    target = daily_challenge_target()
    sent = 0

    for candidate in await find_at_risk_users():
        user_id = candidate["user_id"]
        already = await db.flappy_streak_saver_log.find_one(
            {"user_id": user_id, "day_key": today}, {"_id": 0}
        )
        if already:
            continue

        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
        if not user or not user.get("email"):
            continue

        streak = await _streak_for(user_id)
        if streak < 1:
            continue

        stats = await _personal_stats(user_id)
        user_name = str(user.get("name") or user["email"].split("@")[0])
        result = await send_catalog_template(
            recipient_email=user["email"],
            template_key="flappy_streak_saver_v7",
            recipient_name=user_name,
            user_name=user_name,
            streak=streak,
            target=target,
            personal_best=int(stats.get("personal_best") or 0),
            dedupe_key=f"flappy-streak-saver:{user_id}:{today}",
            expected_user_id=user_id,
        )
        await db.flappy_streak_saver_log.insert_one({
            "user_id": user_id,
            "day_key": today,
            "streak": streak,
            "target": target,
            "email": user["email"],
            "success": bool(result.get("success")),
            "error": str(result.get("error") or ""),
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        if result.get("success"):
            sent += 1
        else:
            logger.warning(f"Streak saver send failed for {user_id}: {result.get('error')}")

    return sent
