"""
scheduler_jobs.digests — Newsletter / briefing / weekly-quality digest jobs.

**Phase 2 incremental domain split — fifth batch.**

Owns weekly summary emails to admins/users. Currently scoped to the
weekly quality digest pipeline; future expansion target for the
`*_briefings_due` cluster in `_legacy.py` (newsletter localized
briefings) once it stops sharing helpers with newsletter routes.

Jobs in this module
===================
- ``scheduled_weekly_quality_digest`` — Sunday-only top-level scheduler
  entry that triggers `_send_weekly_quality_digest`.
- ``_send_weekly_quality_digest`` — pure aggregator + email-sender used
  by the scheduler entry and by the admin "preview digest" endpoint.

External callers continue to import via the facade:
    from scheduler_jobs import scheduled_weekly_quality_digest
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from utils.pagination import iter_find_paginated


logger = logging.getLogger("scheduler_jobs.digests")


async def _send_weekly_quality_digest(db, send_email_fn) -> Dict[str, Any]:
    """Aggregate the last 7 days of AI feedback and email a summary digest.

    Pure of scheduler concerns: takes the DB handle + the send-email
    callable, returns the summary dict (so it's reusable from the admin
    "preview digest" endpoint without triggering the cron-gating logic).
    """
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=7)).isoformat()
    prev_week_start = (now - timedelta(days=14)).isoformat()
    settings = await db.quality_alert_settings.find_one({}, {"_id": 0}) or {}
    alert_email = settings.get("alert_email", os.environ.get("ADMIN_EMAILS", ""))

    this_week = []
    async for row in iter_find_paginated(
        db.ai_feedback,
        {"created_at": {"$gte": week_start}},
        {"_id": 0, "feature": 1, "feature_key": 1, "rating": 1, "comment": 1},
        max_docs=5000,
    ):
        this_week.append(row)

    last_week = []
    async for row in iter_find_paginated(
        db.ai_feedback,
        {"created_at": {"$gte": prev_week_start, "$lt": week_start}},
        {"_id": 0, "feature": 1, "feature_key": 1, "rating": 1},
        max_docs=5000,
    ):
        last_week.append(row)

    def calc_pct(items):
        stats: Dict[str, Dict[str, int]] = {}
        for fb in items:
            feat = fb.get("feature") or fb.get("feature_key") or "unknown"
            rating = fb.get("rating")
            positive = rating == "up" if isinstance(rating, str) else (rating or 0) > 0
            if feat not in stats:
                stats[feat] = {"total": 0, "positive": 0}
            stats[feat]["total"] += 1
            if positive:
                stats[feat]["positive"] += 1
        return {
            k: round(v["positive"] / v["total"] * 100, 1) if v["total"] > 0 else 0
            for k, v in stats.items()
        }

    calc_pct(this_week)
    calc_pct(last_week)
    total_ratings_week = len(this_week)
    positive_week = sum(
        1
        for fb in this_week
        if (isinstance(fb.get("rating"), str) and fb["rating"] == "up")
        or (isinstance(fb.get("rating"), (int, float)) and (fb.get("rating") or 0) > 0)
    )
    overall_pct_week = (
        round(positive_week / total_ratings_week * 100, 1) if total_ratings_week > 0 else 0
    )
    subject = f"[RealAICoach] Weekly Quality Digest - {now.strftime('%b %d, %Y')}"
    html = (
        f"<h2>Weekly Quality Digest</h2>"
        f"<p>Overall: {overall_pct_week}% positive from {total_ratings_week} ratings</p>"
    )
    result = await send_email_fn(recipient_email=alert_email, subject=subject, content=html)
    await db.quality_digest_history.insert_one(
        {
            "sent_at": now.isoformat(),
            "total_ratings": total_ratings_week,
            "overall_pct": overall_pct_week,
            "alert_email": alert_email,
            "email_result": result.get("success", False),
        }
    )
    return {
        "success": result.get("success", False),
        "total_ratings": total_ratings_week,
        "overall_pct": overall_pct_week,
    }


async def scheduled_weekly_quality_digest() -> None:
    """Send weekly quality digest email every Sunday (no-op on other days)."""
    now = datetime.now(timezone.utc)
    if now.weekday() != 6:
        return
    logger.info("Running weekly quality digest generation...")
    try:
        from routes.db import db
        from utils.email_service import send_email

        await _send_weekly_quality_digest(db, send_email)
    except Exception as e:
        logger.error(f"Weekly quality digest failed: {e}")


async def _send_job_search_weekly_digest(db, trigger: str = "cron", force: bool = False) -> Dict[str, Any]:
    """Compile and send the weekly Job Search digest to opted-in workspace users.

    Idempotent per ISO week via `job_search_digest_runs` unless `force=True`.
    """
    from utils.email_service import is_email_configured, send_catalog_template

    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    week_key = f"{iso[0]}-W{iso[1]:02d}"
    week_start = (now - timedelta(days=7)).isoformat()
    week_label = f"Week of {(now - timedelta(days=7)).strftime('%b %d')}"

    if not force:
        existing = await db.job_search_digest_runs.find_one({"week_key": week_key, "status": "complete"})
        if existing:
            logger.info(f"Job Search digest already sent for {week_key}; skipping")
            return {"success": True, "skipped": "already_sent", "week_key": week_key}

    if not is_email_configured():
        logger.warning("Email service not configured - skipping Job Search weekly digest")
        return {"success": False, "skipped": "email_not_configured", "week_key": week_key}

    profile_user_ids = []
    async for row in iter_find_paginated(
        db.job_search_profiles, {}, {"_id": 0, "user_id": 1, "skills": 1, "target_roles": 1}, max_docs=10000
    ):
        profile_user_ids.append(row)
    profiles_by_uid = {p["user_id"]: p for p in profile_user_ids if p.get("user_id")}
    if not profiles_by_uid:
        return {"success": True, "skipped": "no_profiles", "week_key": week_key}

    users = await db.users.find(
        {"user_id": {"$in": list(profiles_by_uid.keys())}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1},
    ).to_list(10000)
    # Personalized digest: default opt-in; exclude only explicit opt-outs.
    opted_out_ids = set()
    async for row in iter_find_paginated(
        db.job_alert_preferences,
        {"user_id": {"$in": [u.get("user_id") for u in users]}, "subscribed": False},
        {"_id": 0, "user_id": 1},
        max_docs=10000,
    ):
        if row.get("user_id"):
            opted_out_ids.add(str(row["user_id"]))
    recipients = [
        u for u in users
        if str(u.get("email") or "").strip() and str(u.get("user_id") or "") not in opted_out_ids
    ]

    new_jobs = await db.careers_jobs.find(
        {"status": "open", "posted_at": {"$gte": week_start}},
        {"_id": 0, "job_id": 1, "title": 1, "department": 1, "location": 1, "description": 1, "requirements": 1, "level": 1},
    ).to_list(500)

    def _job_terms(job: dict) -> str:
        reqs = job.get("requirements") or []
        if isinstance(reqs, list):
            reqs = " ".join(str(r) for r in reqs)
        return f"{job.get('title', '')} {job.get('department', '')} {job.get('description', '')} {reqs} {job.get('level', '')}".lower()

    sent = 0
    skipped_no_content = 0
    for user in recipients:
        uid = str(user.get("user_id") or "")
        profile = profiles_by_uid.get(uid) or {}
        keywords = [str(k).lower() for k in (profile.get("skills") or []) + (profile.get("target_roles") or []) if str(k).strip()]

        scored = []
        for job in new_jobs:
            terms = _job_terms(job)
            hits = sum(1 for kw in keywords if kw and kw in terms)
            if hits > 0:
                scored.append((hits, job))
        scored.sort(key=lambda item: item[0], reverse=True)
        matching = [job for _, job in scored]

        best = await db.job_search_matches.find(
            {"user_id": uid, "created_at": {"$gte": week_start}},
            {"_id": 0, "overall_score": 1, "job_title": 1},
        ).sort("overall_score", -1).limit(1).to_list(1)
        best_fit_score = int(best[0].get("overall_score") or 0) if best else 0
        best_fit_job_title = str(best[0].get("job_title") or "") if best else ""

        kits_generated = await db.job_search_documents.count_documents({"user_id": uid, "generated_at": {"$gte": week_start}})
        apps_tracked = await db.job_search_applications.count_documents({"user_id": uid, "created_at": {"$gte": week_start}})

        if not matching and not best_fit_score and not kits_generated and not apps_tracked:
            skipped_no_content += 1
            continue

        result = await send_catalog_template(
            recipient_email=user["email"],
            template_key="job_search_weekly_digest",
            recipient_name=user.get("name") or "there",
            user_name=user.get("name") or "there",
            week_label=week_label,
            new_roles_count=len(matching),
            top_roles=[{"title": j.get("title"), "department": j.get("department"), "location": j.get("location")} for j in matching[:3]],
            best_fit_score=best_fit_score,
            best_fit_job_title=best_fit_job_title,
            kits_generated=kits_generated,
            apps_tracked=apps_tracked,
            show_upgrade_hint=str(user.get("subscription_plan") or "free").lower() == "free",
        )
        if result.get("success"):
            sent += 1

    summary = {
        "week_key": week_key,
        "trigger": trigger,
        "audience": len(recipients),
        "profiles": len(profiles_by_uid),
        "new_jobs_pool": len(new_jobs),
        "sent": sent,
        "skipped_no_content": skipped_no_content,
        "status": "complete",
        "generated_at": now.isoformat(),
    }
    await db.job_search_digest_runs.insert_one(dict(summary))
    logger.info(f"Job Search weekly digest {week_key}: sent {sent}/{len(recipients)} (trigger={trigger})")
    summary["success"] = True
    return summary


async def scheduled_job_search_weekly_digest() -> None:
    """Send the Job Search weekly digest (cron: Monday 09:30 UTC)."""
    logger.info("Running Job Search weekly digest...")
    try:
        from routes.db import db

        await _send_job_search_weekly_digest(db, trigger="cron")
    except Exception as e:
        logger.error(f"Job Search weekly digest failed: {e}")


__all__ = [
    "_send_weekly_quality_digest",
    "scheduled_weekly_quality_digest",
    "_send_job_search_weekly_digest",
    "scheduled_job_search_weekly_digest",
]
