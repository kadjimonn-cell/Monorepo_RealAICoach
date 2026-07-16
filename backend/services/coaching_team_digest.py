"""Weekly AI Coaching Team email digest — engagement + preview-driven conversion."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

MAX_RECIPIENTS_PER_RUN = 500

COACH_DISPLAY = {
    "career_coach": ("Career Coach", "Career growth & direction"),
    "interview_coach": ("Interview Coach", "Mock interviews & STAR feedback"),
    "resume_specialist": ("Resume Specialist", "Resume & profile optimization"),
    "negotiation_coach": ("Negotiation Coach", "Salary & offer negotiation"),
}

WEEKLY_TIPS = [
    "Book 15 minutes this week to practice one STAR story out loud — spoken rehearsal doubles recall in real interviews.",
    "Rewrite one resume bullet as action + scope + measurable result. Small quantified wins compound fast.",
    "Before any negotiation, write down your walk-away point. Clarity beats confidence in the moment.",
    "End each week by noting one skill you sharpened. Momentum you can see is momentum you keep.",
]


async def _gather_recipients(db) -> list:
    since_14d = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    engaged_ids = await db.coaching_team_sessions.distinct("user_id")
    new_users = await db.users.find(
        {"created_at": {"$gte": since_14d}}, {"_id": 0, "user_id": 1}
    ).to_list(length=2000)
    user_ids = list({*engaged_ids, *[u["user_id"] for u in new_users]})[: MAX_RECIPIENTS_PER_RUN * 2]
    users = await db.users.find(
        {"user_id": {"$in": user_ids}, "email": {"$exists": True, "$ne": ""}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    ).to_list(length=len(user_ids))
    return users


async def _digest_pref_enabled(db, user_id: str) -> bool:
    prefs = await db.email_preferences.find_one({"user_id": user_id}, {"_id": 0, "coaching_digest": 1})
    return bool((prefs or {}).get("coaching_digest", True))


async def _week_stats(db, user_id: str) -> Dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    sessions = await db.coaching_team_sessions.find(
        {"user_id": user_id},
        {"_id": 0, "coach_key": 1, "message_count": 1, "updated_at": 1},
    ).to_list(length=200)
    week_sessions = [s for s in sessions if s.get("updated_at", "") >= since]
    used_keys = {s["coach_key"] for s in sessions}
    spotlight_key = next((k for k in COACH_DISPLAY if k not in used_keys), "interview_coach")
    preview_used = await db.coaching_team_previews.find_one(
        {"user_id": user_id, "coach_key": spotlight_key}, {"_id": 0}
    )
    return {
        "sessions_this_week": len(week_sessions),
        "messages_this_week": sum(int(s.get("message_count", 0)) for s in week_sessions),
        "coaches_used": [COACH_DISPLAY[k][0] for k in used_keys if k in COACH_DISPLAY],
        "spotlight_key": spotlight_key,
        "spotlight_preview_available": preview_used is None,
    }


async def send_coaching_team_weekly_digest(trigger: str = "manual", dry_run: bool = False) -> Dict[str, Any]:
    from routes.db import db
    from utils.email_service import send_email
    from utils.email_templates import build_coaching_team_weekly_digest_email

    week_tag = datetime.now(timezone.utc).strftime("%G-W%V")
    tip = WEEKLY_TIPS[int(datetime.now(timezone.utc).strftime("%V")) % len(WEEKLY_TIPS)]
    users = await _gather_recipients(db)

    summary = {"trigger": trigger, "dry_run": dry_run, "week": week_tag,
               "candidates": len(users), "sent": 0, "skipped_pref": 0, "errors": 0}
    for user in users[:MAX_RECIPIENTS_PER_RUN]:
        if not await _digest_pref_enabled(db, user["user_id"]):
            summary["skipped_pref"] += 1
            continue
        stats = await _week_stats(db, user["user_id"])
        spotlight_name, spotlight_tagline = COACH_DISPLAY[stats["spotlight_key"]]
        if dry_run:
            summary["sent"] += 1
            continue
        try:
            template = build_coaching_team_weekly_digest_email(
                user_name=user.get("name") or "there",
                sessions_this_week=stats["sessions_this_week"],
                messages_this_week=stats["messages_this_week"],
                coaches_used=stats["coaches_used"],
                spotlight_coach_name=spotlight_name,
                spotlight_coach_tagline=spotlight_tagline,
                spotlight_preview_available=stats["spotlight_preview_available"],
                coaching_tip=tip,
            )
            result = await send_email(
                recipient_email=user["email"],
                subject=template.subject,
                content=template.html,
                content_text=template.text,
                recipient_name=user.get("name"),
                template_key="coaching_team_weekly_digest",
                dedupe_key=f"coaching-digest-{user['user_id']}-{week_tag}",
                expected_user_id=user["user_id"],
            )
            if result.get("success") or result.get("deduped"):
                summary["sent"] += 1
            else:
                summary["errors"] += 1
        except Exception as exc:
            summary["errors"] += 1
            logger.warning("[coaching-digest] send failed for %s: %s", user["user_id"], exc)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    await db.coaching_digest_runs.insert_one(dict(summary))
    summary.pop("_id", None)
    logger.info("[coaching-digest] %s", summary)
    return summary
