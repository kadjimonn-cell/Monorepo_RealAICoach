"""Daily AI Coaching Team push digest — mobile (Expo) + web push re-engagement."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

MAX_PUSH_PER_RUN = 500

DAILY_TIPS = [
    "Practice one STAR story out loud today — spoken rehearsal doubles recall.",
    "Rewrite one resume bullet as action + scope + result. Quantified wins compound.",
    "Write down your walk-away point before any negotiation. Clarity beats confidence.",
    "Note one skill you sharpened today. Visible momentum is momentum you keep.",
    "Ask your Interview Coach for one curveball question — surprise builds resilience.",
    "Spend 10 minutes mapping your next career move with your Career Coach.",
    "Have your Resume Specialist scan one section for filler words today.",
]


async def _gather_push_recipients(db) -> list:
    since_14d = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    engaged_ids = await db.coaching_team_sessions.distinct("user_id")
    new_users = await db.users.find(
        {"created_at": {"$gte": since_14d}}, {"_id": 0, "user_id": 1}
    ).to_list(length=2000)
    return list({*engaged_ids, *[u["user_id"] for u in new_users]})[: MAX_PUSH_PER_RUN * 2]


async def _push_pref_enabled(db, user_id: str) -> bool:
    settings = await db.notification_settings.find_one(
        {"user_id": user_id}, {"_id": 0, "coaching_digest_push": 1}
    )
    return bool((settings or {}).get("coaching_digest_push", True))


async def _yesterday_stats(db, user_id: str) -> Dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    sessions = await db.coaching_team_sessions.find(
        {"user_id": user_id, "updated_at": {"$gte": since}},
        {"_id": 0, "message_count": 1},
    ).to_list(length=100)
    return {
        "sessions_yesterday": len(sessions),
        "messages_yesterday": sum(int(s.get("message_count", 0)) for s in sessions),
    }


def _build_push_body(stats: Dict[str, Any], tip: str) -> str:
    if stats["sessions_yesterday"] > 0:
        return (
            f"Yesterday: {stats['sessions_yesterday']} coaching session"
            f"{'s' if stats['sessions_yesterday'] > 1 else ''} · "
            f"{stats['messages_yesterday']} messages. Today's tip: {tip}"
        )
    return f"Today's tip: {tip} Your coaching team is ready when you are."


async def send_coaching_daily_digest_push(trigger: str = "manual", dry_run: bool = False) -> Dict[str, Any]:
    from routes.db import db
    from routes.notifications import send_push_notification

    day_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tip = DAILY_TIPS[datetime.now(timezone.utc).timetuple().tm_yday % len(DAILY_TIPS)]

    user_ids = await _gather_push_recipients(db)
    summary = {"trigger": trigger, "dry_run": dry_run, "day": day_tag,
               "candidates": len(user_ids), "sent": 0, "skipped_pref": 0,
               "skipped_no_channel": 0, "send_failed": 0, "deduped": 0, "errors": 0}

    for user_id in user_ids[:MAX_PUSH_PER_RUN]:
        if not await _push_pref_enabled(db, user_id):
            summary["skipped_pref"] += 1
            continue

        already = await db.coaching_digest_push_log.find_one(
            {"user_id": user_id, "day": day_tag}, {"_id": 1}
        )
        if already:
            summary["deduped"] += 1
            continue

        has_expo = await db.push_tokens.find_one({"user_id": user_id}, {"_id": 1})
        has_web = await db.push_subscriptions.find_one(
            {"user_id": user_id, "active": True}, {"_id": 1}
        ) or await db.web_push_subscriptions.find_one({"user_id": user_id}, {"_id": 1})
        if not has_expo and not has_web:
            summary["skipped_no_channel"] += 1
            continue

        if dry_run:
            summary["sent"] += 1
            continue

        try:
            stats = await _yesterday_stats(db, user_id)
            delivered = await send_push_notification(
                user_id=user_id,
                title="Your daily coaching digest",
                body=_build_push_body(stats, tip),
                data={"type": "coaching_digest", "action_url": "/ai-coaching-team"},
            )
            if delivered:
                summary["sent"] += 1
                await db.coaching_digest_push_log.insert_one({
                    "user_id": user_id, "day": day_tag, "trigger": trigger,
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                })
            else:
                summary["send_failed"] += 1
        except Exception as exc:
            summary["errors"] += 1
            logger.warning("[coaching-digest-push] send failed for %s: %s", user_id, exc)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    await db.coaching_digest_push_runs.insert_one(dict(summary))
    summary.pop("_id", None)
    logger.info("[coaching-digest-push] %s", summary)
    return summary
