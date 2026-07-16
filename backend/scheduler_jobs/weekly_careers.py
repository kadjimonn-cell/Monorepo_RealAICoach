"""
scheduler_jobs.weekly_careers — Weekly careers job creation + announcement pipeline.

**Phase 2 incremental domain split — third batch.**

Owns the end-to-end weekly-careers automation:
- Constants & fallback template list
- Template merging and slug generation
- Recipient selection (with opt-in / opt-out gating)
- In-app notification fanout
- Email broadcast via the email service catalog
- The top-level scheduler entry point (`scheduled_weekly_careers_job_creation_and_announcement`)

External callers continue to import via the facade:
    from scheduler_jobs import scheduled_weekly_careers_job_creation_and_announcement

The facade auto-mirrors every public name from this module, and
`scheduler_jobs/_legacy.py` re-imports the same names to keep its
own body unchanged for the remaining 80+ scheduled jobs.

Imports are deferred where they depend back on `_legacy` (e.g.
`_get_scheduler_admin_context`) to avoid circular import at module
load.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from utils.pagination import iter_find_paginated

from scheduler_jobs.observability import _record_scheduler_heartbeat
from scheduler_jobs.utils import (
    _is_active_user_record,
    _resolve_frontend_base_url,
    _slugify_weekly_careers,
)


# ── Constants ────────────────────────────────────────────────────────────
WEEKLY_CAREERS_TEMPLATE_FLAG_KEY = "weekly_careers_job_template_config"
WEEKLY_CAREERS_AUTOMATION_STATE_KEY = "weekly_careers_job_automation_state"
WEEKLY_CAREERS_AUTOMATION_RUNS_COLLECTION = "weekly_careers_job_automation_runs"
WEEKLY_CAREERS_JOB_HEARTBEAT_ID = "weekly_careers_job_automation"


WEEKLY_CAREERS_FALLBACK_TEMPLATES: List[Dict[str, Any]] = [
    {
        "slug_base": "ai-career-growth-engineer",
        "title": "AI Career Growth Engineer",
        "department": "AI Platform",
        "location": "Remote",
        "type": "Full-time",
        "level": "Mid-Senior",
        "description": (
            "Help build the next generation of AI career tools. You will partner across product, data, and "
            "operations to design user-facing experiences that improve hiring outcomes."
        ),
        "requirements": [
            "3+ years in product engineering or applied AI",
            "Strong Python/TypeScript fundamentals",
            "Experience shipping user-facing workflows",
        ],
        "salary_usd_min": 90000,
        "salary_usd_max": 130000,
        "hourly_rate_usd": 0,
        "status": "open",
    },
    {
        "slug_base": "careers-operations-analyst",
        "title": "Careers Operations Analyst",
        "department": "Operations",
        "location": "Hybrid",
        "type": "Full-time",
        "level": "Mid",
        "description": (
            "Own the candidate funnel reporting layer and improve conversion from discovery to application. "
            "Work with cross-functional teams to remove friction and improve applicant quality."
        ),
        "requirements": [
            "2+ years in operations, growth, or analytics",
            "Comfort with SQL and dashboard tooling",
            "Strong written communication",
        ],
        "salary_usd_min": 70000,
        "salary_usd_max": 105000,
        "hourly_rate_usd": 0,
        "status": "open",
    },
    {
        "slug_base": "global-talent-partner",
        "title": "Global Talent Partner",
        "department": "People",
        "location": "Remote",
        "type": "Contract",
        "level": "Senior",
        "description": (
            "Lead high-quality outbound and inbound recruiting for strategic roles, and partner with leadership "
            "on weekly hiring planning and candidate experience improvements."
        ),
        "requirements": [
            "4+ years in recruiting or talent acquisition",
            "Strong sourcing and stakeholder management",
            "Experience with modern ATS workflows",
        ],
        "salary_usd_min": 80000,
        "salary_usd_max": 120000,
        "hourly_rate_usd": 0,
        "status": "open",
    },
]


# ── Template merging ─────────────────────────────────────────────────────


def _merge_weekly_careers_template(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge an admin-supplied override on top of the fallback template.

    Normalizes every field, caps strings/lists to sane lengths, and forces
    `status='open'`.
    """
    merged = {**(base or {}), **(override or {})}
    merged["slug_base"] = _slugify_weekly_careers(
        merged.get("slug_base") or merged.get("title") or "weekly-careers-opening"
    )
    merged["title"] = str(merged.get("title") or "Weekly Careers Opportunity").strip()[:200]
    merged["department"] = str(merged.get("department") or "General").strip()[:120]
    merged["location"] = str(merged.get("location") or "Remote").strip()[:120]
    merged["type"] = str(merged.get("type") or "Full-time").strip()[:80]
    merged["level"] = str(merged.get("level") or "").strip()[:80] or None
    merged["description"] = str(merged.get("description") or "Join our careers platform team.").strip()
    requirements = merged.get("requirements") if isinstance(merged.get("requirements"), list) else []
    merged["requirements"] = [str(item).strip() for item in requirements if str(item).strip()][:12]
    merged["salary_usd_min"] = max(0, int(merged.get("salary_usd_min") or 0))
    merged["salary_usd_max"] = max(0, int(merged.get("salary_usd_max") or 0))
    merged["hourly_rate_usd"] = max(0, int(merged.get("hourly_rate_usd") or 0))
    merged["status"] = "open"
    return merged


async def _get_weekly_careers_template_config(db, now: datetime) -> Dict[str, Any]:
    """Resolve this week's template by rotating the fallback list and
    merging any admin override from `system_runtime_flags`."""
    week = int(now.isocalendar().week)
    fallback = WEEKLY_CAREERS_FALLBACK_TEMPLATES[week % len(WEEKLY_CAREERS_FALLBACK_TEMPLATES)]
    settings_doc = await db.system_runtime_flags.find_one(
        {"key": WEEKLY_CAREERS_TEMPLATE_FLAG_KEY},
        {"_id": 0, "value": 1},
    ) or {}
    override = settings_doc.get("value") if isinstance(settings_doc.get("value"), dict) else {}
    return _merge_weekly_careers_template(fallback, override)


def _build_weekly_careers_job_doc(template: Dict[str, Any], now: datetime, created_by: str, week_key: str) -> Dict[str, Any]:
    """Produce the persisted `careers_jobs` document for this week."""
    now_iso = now.isoformat()
    slug = f"{_slugify_weekly_careers(template.get('slug_base'))}-{week_key.lower()}"
    return {
        "job_id": f"job_{slug}",
        "slug": slug,
        "title": template.get("title"),
        "department": template.get("department"),
        "location": template.get("location"),
        "type": template.get("type"),
        "level": template.get("level"),
        "description": template.get("description"),
        "requirements": template.get("requirements") or [],
        "salary_usd_min": template.get("salary_usd_min") or 0,
        "salary_usd_max": template.get("salary_usd_max") or 0,
        "hourly_rate_usd": template.get("hourly_rate_usd") or 0,
        "status": "open",
        "posted_at": now_iso,
        "updated_at": now_iso,
        "created_by": created_by,
        "automation": {
            "source": "weekly_careers_scheduler",
            "week_key": week_key,
            "created_at": now_iso,
        },
    }


# ── Recipient selection & broadcast ──────────────────────────────────────


async def _select_weekly_careers_email_recipients(db, active_users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter `active_users` against `job_alert_preferences` opt-in / opt-out
    rules. When ANY explicit opt-in exists, the broadcast becomes opt-in-only
    for that audience subset; otherwise default-opt-in applies."""
    users_with_email = [
        user for user in active_users
        if str(user.get("email") or "").strip()
    ]
    if not users_with_email:
        return []

    user_ids = [str(user.get("user_id") or "") for user in users_with_email if str(user.get("user_id") or "")]
    emails = [str(user.get("email") or "").strip().lower() for user in users_with_email]
    preference_query = {
        "$or": [
            {"user_id": {"$in": user_ids}} if user_ids else {"user_id": ""},
            {"email": {"$in": emails}} if emails else {"email": ""},
        ]
    }
    explicit_opt_in_user_ids: set[str] = set()
    explicit_opt_in_emails: set[str] = set()
    opt_out_user_ids: set[str] = set()
    opt_out_emails: set[str] = set()

    async for row in iter_find_paginated(
        db.job_alert_preferences,
        preference_query,
        {"_id": 0, "user_id": 1, "email": 1, "subscribed": 1},
    ):
        row_user_id = str(row.get("user_id") or "")
        row_email = str(row.get("email") or "").strip().lower()
        if row.get("subscribed") is True:
            if row_user_id:
                explicit_opt_in_user_ids.add(row_user_id)
            if row_email:
                explicit_opt_in_emails.add(row_email)
        elif row.get("subscribed") is False:
            if row_user_id:
                opt_out_user_ids.add(row_user_id)
            if row_email:
                opt_out_emails.add(row_email)

    has_explicit_opt_in = bool(explicit_opt_in_user_ids or explicit_opt_in_emails)
    recipients: List[Dict[str, Any]] = []
    for user in users_with_email:
        uid = str(user.get("user_id") or "")
        email = str(user.get("email") or "").strip().lower()
        if not email:
            continue
        if uid in opt_out_user_ids or email in opt_out_emails:
            continue
        if has_explicit_opt_in and uid not in explicit_opt_in_user_ids and email not in explicit_opt_in_emails:
            continue
        recipients.append(user)

    return recipients


async def _emit_weekly_careers_in_app_notifications(db, users: List[Dict[str, Any]], job_doc: Dict[str, Any], now_iso: str) -> int:
    """Insert one `weekly_careers_job_announcement` notification per user.
    Returns the number of documents inserted."""
    if not users:
        return 0
    action_url = f"/careers/jobs/{job_doc.get('slug')}?source=weekly-careers-notification"
    docs = []
    for user in users:
        user_id = str(user.get("user_id") or "")
        if not user_id:
            continue
        notification_id = f"notif_{uuid.uuid4().hex[:12]}"
        docs.append(
            {
                "notification_id": notification_id,
                "id": notification_id,
                "user_id": user_id,
                "type": "weekly_careers_job_announcement",
                "title": "New job added this week",
                "body": f"New opening: {job_doc.get('title')}. Go to Careers to view and apply.",
                "action_url": action_url,
                "read": False,
                "created_at": now_iso,
                "meta": {
                    "job_slug": job_doc.get("slug"),
                    "job_id": job_doc.get("job_id"),
                    "source": "weekly_careers_scheduler",
                },
            }
        )

    if docs:
        await db.notifications.insert_many(docs)
    return len(docs)


async def _send_weekly_careers_emails(db, recipients: List[Dict[str, Any]], job_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Send the `weekly_careers_job_announcement` template via the email
    service. Returns a summary including counts and the canonical apply URL."""
    if not recipients:
        return {"attempted": 0, "sent": 0, "failed": 0, "configured": False}

    from utils.email_service import is_email_configured, send_catalog_template

    if not is_email_configured():
        return {"attempted": len(recipients), "sent": 0, "failed": 0, "configured": False}

    frontend_base = _resolve_frontend_base_url()
    apply_path = f"/careers/jobs/{job_doc.get('slug')}?source=weekly-careers-email"
    careers_path = "/careers?source=weekly-careers-email"
    apply_url = f"{frontend_base}{apply_path}" if frontend_base else apply_path
    careers_url = f"{frontend_base}{careers_path}" if frontend_base else careers_path

    sent = 0
    failed = 0
    for user in recipients:
        recipient_email = str(user.get("email") or "").strip()
        if not recipient_email:
            continue
        recipient_name = str(user.get("full_name") or user.get("name") or "there").strip() or "there"
        try:
            result = await send_catalog_template(
                recipient_email=recipient_email,
                template_key="weekly_careers_job_announcement",
                recipient_name=recipient_name,
                user_name=recipient_name,
                job_title=str(job_doc.get("title") or "New Role"),
                department=str(job_doc.get("department") or "General"),
                location=str(job_doc.get("location") or "Remote"),
                role_type=str(job_doc.get("type") or "Full-time"),
                apply_url=apply_url,
                careers_url=careers_url,
            )
            if result.get("success"):
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return {
        "attempted": len(recipients),
        "sent": sent,
        "failed": failed,
        "configured": True,
        "apply_url": apply_url,
        "careers_url": careers_url,
    }


# ── Top-level scheduler entry point ──────────────────────────────────────


async def scheduled_weekly_careers_job_creation_and_announcement(
    triggered_by: str = "scheduler:weekly",
    force: bool = False,
) -> Dict[str, Any]:
    """Create one careers job every Monday and broadcast in-app + email announcements.

    Idempotent per ISO week: a second invocation in the same week skips
    creation unless `force=True`. Persists a run summary into
    `WEEKLY_CAREERS_AUTOMATION_RUNS_COLLECTION` and updates the
    `WEEKLY_CAREERS_AUTOMATION_STATE_KEY` system runtime flag.
    """
    import logging

    # Deferred imports to avoid circular load order at module init.
    from routes.db import db
    from scheduler_jobs.admin_context import _get_scheduler_admin_context

    logger = logging.getLogger("scheduler_jobs.weekly_careers")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    week_key = f"{now.isocalendar().year}W{now.isocalendar().week:02d}"
    run_id = f"weekly_careers_{uuid.uuid4().hex[:10]}"

    try:
        state_doc = await db.system_runtime_flags.find_one(
            {"key": WEEKLY_CAREERS_AUTOMATION_STATE_KEY},
            {"_id": 0, "value": 1},
        ) or {}
        state_value = state_doc.get("value") if isinstance(state_doc.get("value"), dict) else {}
        if not force and state_value.get("last_success_week") == week_key:
            detail = f"skipped already_completed week={week_key}"
            await _record_scheduler_heartbeat(WEEKLY_CAREERS_JOB_HEARTBEAT_ID, "healthy", detail)
            return {
                "status": "skipped",
                "reason": "already_ran_this_week",
                "week_key": week_key,
                "run_id": run_id,
            }

        template = await _get_weekly_careers_template_config(db, now)
        scheduler_admin = await _get_scheduler_admin_context()
        created_by = str(getattr(scheduler_admin, "email", "scheduler@system") or "scheduler@system")
        job_doc = _build_weekly_careers_job_doc(template, now, created_by, week_key)

        existing = await db.careers_jobs.find_one(
            {"automation.week_key": week_key},
            {"_id": 0},
        )
        created = False
        if existing and not force:
            job_doc = existing
        else:
            await db.careers_jobs.update_one(
                {"slug": job_doc.get("slug")},
                {"$set": {**job_doc}},
                upsert=True,
            )
            created = True

        active_users: List[Dict[str, Any]] = []
        async for user in iter_find_paginated(
            db.users,
            {"access_locked": {"$ne": True}, "subscription_status": {"$in": ["active", "trial"]}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "full_name": 1, "subscription_status": 1, "access_locked": 1},
        ):
            if _is_active_user_record(user):
                active_users.append(user)

        notifications_sent = await _emit_weekly_careers_in_app_notifications(db, active_users, job_doc, now_iso)
        email_recipients = await _select_weekly_careers_email_recipients(db, active_users)
        email_result = await _send_weekly_careers_emails(db, email_recipients, job_doc)

        result_doc = {
            "run_id": run_id,
            "triggered_by": str(triggered_by or "scheduler:weekly"),
            "status": "success",
            "week_key": week_key,
            "job": {
                "job_id": job_doc.get("job_id"),
                "slug": job_doc.get("slug"),
                "title": job_doc.get("title"),
                "department": job_doc.get("department"),
                "location": job_doc.get("location"),
                "type": job_doc.get("type"),
            },
            "job_created": created,
            "in_app_notifications": {
                "attempted": len(active_users),
                "sent": notifications_sent,
            },
            "email": email_result,
            "ran_at": now_iso,
            "updated_at": now_iso,
        }

        await db[WEEKLY_CAREERS_AUTOMATION_RUNS_COLLECTION].insert_one({**result_doc})
        await db.system_runtime_flags.update_one(
            {"key": WEEKLY_CAREERS_AUTOMATION_STATE_KEY},
            {
                "$set": {
                    "key": WEEKLY_CAREERS_AUTOMATION_STATE_KEY,
                    "value": {
                        "last_success_week": week_key,
                        "last_run_id": run_id,
                        "last_job_slug": job_doc.get("slug"),
                        "last_status": "success",
                    },
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )

        detail = (
            f"week={week_key} created={created} inapp={notifications_sent} "
            f"emails={email_result.get('sent', 0)}/{email_result.get('attempted', 0)}"
        )
        await _record_scheduler_heartbeat(WEEKLY_CAREERS_JOB_HEARTBEAT_ID, "healthy", detail)
        return result_doc
    except Exception as exc:
        error_detail = str(exc)[:240]
        await _record_scheduler_heartbeat(WEEKLY_CAREERS_JOB_HEARTBEAT_ID, "error", error_detail)
        await db.system_runtime_flags.update_one(
            {"key": WEEKLY_CAREERS_AUTOMATION_STATE_KEY},
            {
                "$set": {
                    "key": WEEKLY_CAREERS_AUTOMATION_STATE_KEY,
                    "value": {
                        "last_status": "error",
                        "last_error": error_detail,
                        "last_error_at": now_iso,
                    },
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )
        logger.error(f"scheduled_weekly_careers_job_creation_and_announcement failed: {exc}")
        return {
            "status": "error",
            "run_id": run_id,
            "week_key": week_key,
            "error": error_detail,
        }


__all__ = [
    # Constants
    "WEEKLY_CAREERS_TEMPLATE_FLAG_KEY",
    "WEEKLY_CAREERS_AUTOMATION_STATE_KEY",
    "WEEKLY_CAREERS_AUTOMATION_RUNS_COLLECTION",
    "WEEKLY_CAREERS_JOB_HEARTBEAT_ID",
    "WEEKLY_CAREERS_FALLBACK_TEMPLATES",
    # Helpers
    "_merge_weekly_careers_template",
    "_get_weekly_careers_template_config",
    "_build_weekly_careers_job_doc",
    "_select_weekly_careers_email_recipients",
    "_emit_weekly_careers_in_app_notifications",
    "_send_weekly_careers_emails",
    # Entry point
    "scheduled_weekly_careers_job_creation_and_announcement",
]
