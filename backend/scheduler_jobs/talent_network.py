"""scheduler_jobs.talent_network — Daily Talent Network role-alert dispatcher.

Enterprise role-alert automation that:
- Reads Talent Network preferences from `careers_talent_network`
- Matches against currently open careers roles
- Dispatches one role-alert email per candidate per 24h window
- Persists run/event telemetry for admin analytics
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from scheduler_jobs.observability import _record_scheduler_heartbeat
from scheduler_jobs.utils import _resolve_frontend_base_url
from utils.pagination import iter_find_paginated


logger = logging.getLogger("scheduler_jobs.talent_network")


TALENT_NETWORK_COL = "careers_talent_network"
CAREERS_JOBS_COL = "careers_jobs"
TALENT_NETWORK_DISPATCH_RUNS_COL = "careers_talent_network_dispatch_runs"
TALENT_NETWORK_DISPATCH_EVENTS_COL = "careers_talent_network_dispatch_events"
TALENT_NETWORK_ALERT_STATE_KEY = "careers_talent_network_role_alert_state"
TALENT_NETWORK_JOB_HEARTBEAT_ID = "careers_talent_network_role_alert_dispatch"
TALENT_NETWORK_SEGMENTS_COL = "careers_talent_network_campaign_segments"
TALENT_NETWORK_CAMPAIGNS_COL = "careers_talent_network_campaigns"
TALENT_NETWORK_CAMPAIGN_RUNS_COL = "careers_talent_network_campaign_runs"
TALENT_NETWORK_REMINDER_EVENTS_COL = "careers_talent_network_reminder_events"
TALENT_NETWORK_CAMPAIGN_HEARTBEAT_ID = "careers_talent_network_campaign_scheduler"


def _normalize_keywords(values: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        text = str(raw or "").strip().lower()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _job_matches_preferences(
    job: dict[str, Any],
    role_interests: list[str],
    locations: list[str],
    work_types: list[str],
) -> bool:
    title = str(job.get("title") or "").lower()
    department = str(job.get("department") or "").lower()
    location = str(job.get("location") or "").lower()
    role_type = str(job.get("type") or "").lower()

    role_ok = True
    if role_interests:
        role_ok = any((keyword in title) or (keyword in department) for keyword in role_interests)

    location_ok = True
    if locations:
        location_ok = any(keyword in location for keyword in locations)

    work_type_ok = True
    if work_types:
        work_type_ok = any(keyword in role_type for keyword in work_types)

    return role_ok and location_ok and work_type_ok


def _coerce_posted_at_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _compute_match_confidence(
    *,
    job: dict[str, Any],
    role_interests: list[str],
    locations: list[str],
    work_types: list[str],
    now: datetime,
) -> tuple[float, str, dict[str, float]]:
    title = str(job.get("title") or "").lower()
    department = str(job.get("department") or "").lower()
    location = str(job.get("location") or "").lower()
    role_type = str(job.get("type") or "").lower()

    role_weight = 0.45
    location_weight = 0.20
    work_type_weight = 0.20
    recency_weight = 0.15

    if role_interests:
        role_hit = 1.0 if any((keyword in title) or (keyword in department) for keyword in role_interests) else 0.0
    else:
        role_hit = 0.72

    if locations:
        location_hit = 1.0 if any(keyword in location for keyword in locations) else 0.0
    else:
        location_hit = 0.70

    if work_types:
        work_type_hit = 1.0 if any(keyword in role_type for keyword in work_types) else 0.0
    else:
        work_type_hit = 0.70

    posted_at_dt = _coerce_posted_at_datetime(job.get("posted_at"))
    recency_score = 0.45
    if posted_at_dt is not None:
        age_days = max(0.0, (now - posted_at_dt).total_seconds() / 86400.0)
        if age_days <= 7:
            recency_score = 1.0
        elif age_days <= 30:
            recency_score = 0.8
        elif age_days <= 60:
            recency_score = 0.6
        else:
            recency_score = 0.35

    weighted_score = (
        (role_hit * role_weight)
        + (location_hit * location_weight)
        + (work_type_hit * work_type_weight)
        + (recency_score * recency_weight)
    )
    confidence_score = round(min(100.0, max(0.0, weighted_score * 100.0)), 2)

    if confidence_score >= 75:
        label = "high"
    elif confidence_score >= 45:
        label = "medium"
    else:
        label = "low"

    return confidence_score, label, {
        "role": round(role_hit, 2),
        "location": round(location_hit, 2),
        "work_type": round(work_type_hit, 2),
        "recency": round(recency_score, 2),
    }


def _eligible_cutoff_for_frequency(now: datetime, alert_frequency: str) -> str:
    if str(alert_frequency or "weekly").strip().lower() == "daily":
        return (now - timedelta(hours=24)).isoformat()
    return (now - timedelta(days=7)).isoformat()


async def _select_open_jobs(db) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    async for row in iter_find_paginated(
        db[CAREERS_JOBS_COL],
        {"status": "open"},
        {
            "_id": 0,
            "job_id": 1,
            "slug": 1,
            "title": 1,
            "department": 1,
            "location": 1,
            "type": 1,
            "posted_at": 1,
        },
        sort=[("posted_at", -1)],
        max_docs=400,
    ):
        jobs.append(row)
    return jobs


async def _already_dispatched_within_frequency(
    db,
    email: str,
    now: datetime,
    force: bool,
    alert_frequency: str,
) -> bool:
    if force:
        return False
    cutoff_iso = _eligible_cutoff_for_frequency(now, alert_frequency)
    existing = await db[TALENT_NETWORK_DISPATCH_EVENTS_COL].find_one(
        {
            "email": email,
            "status": "sent",
            "created_at": {"$gte": cutoff_iso},
        },
        {"_id": 0, "event_id": 1},
    )
    return bool(existing)


async def _send_talent_network_alert_email(
    *,
    recipient_email: str,
    recipient_name: str,
    job: dict[str, Any],
) -> dict[str, Any]:
    from utils.email_service import is_email_configured, send_catalog_template

    if not is_email_configured():
        return {"success": False, "error": "email_not_configured"}

    frontend_base = _resolve_frontend_base_url()
    slug = str(job.get("slug") or "")
    apply_path = f"/careers/jobs/{slug}?source=talent-network-alert"
    careers_path = "/talent-network?source=talent-network-alert"
    apply_url = f"{frontend_base}{apply_path}" if frontend_base else apply_path
    careers_url = f"{frontend_base}{careers_path}" if frontend_base else careers_path

    return await send_catalog_template(
        recipient_email=recipient_email,
        template_key="weekly_careers_job_announcement",
        recipient_name=recipient_name or "there",
        user_name=recipient_name or "there",
        job_title=str(job.get("title") or "New Role"),
        department=str(job.get("department") or "General"),
        location=str(job.get("location") or "Remote"),
        role_type=str(job.get("type") or "Full-time"),
        apply_url=apply_url,
        careers_url=careers_url,
        subject_override=f"Role alert: {str(job.get('title') or 'New opportunity')} · RealAICoach Careers",
    )


async def scheduled_talent_network_role_alert_dispatch(
    triggered_by: str = "scheduler:daily-24h",
    force: bool = False,
) -> Dict[str, Any]:
    """Dispatch role-alert emails to Talent Network members using saved preferences."""
    from routes.db import db

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    run_id = f"tn_dispatch_{uuid.uuid4().hex[:12]}"

    summary: dict[str, Any] = {
        "run_id": run_id,
        "triggered_by": str(triggered_by or "scheduler:daily-24h"),
        "mode": "live",
        "cadence": "24h",
        "started_at": now_iso,
        "updated_at": now_iso,
        "force": bool(force),
        "candidates_scanned": 0,
        "eligible_candidates": 0,
        "attempted": 0,
        "sent": 0,
        "failed": 0,
        "skipped_recently_sent": 0,
        "skipped_no_match": 0,
        "skipped_invalid_email": 0,
        "open_jobs": 0,
        "confidence_distribution": {
            "high": 0,
            "medium": 0,
            "low": 0,
        },
        "confidence_total_score": 0.0,
        "confidence_samples": 0,
        "status": "success",
        "errors": [],
    }

    try:
        open_jobs = await _select_open_jobs(db)
        summary["open_jobs"] = len(open_jobs)

        if not open_jobs:
            summary["status"] = "skipped"
            summary["reason"] = "no_open_jobs"
            summary["completed_at"] = datetime.now(timezone.utc).isoformat()
            await db[TALENT_NETWORK_DISPATCH_RUNS_COL].insert_one({**summary})
            await db.system_runtime_flags.update_one(
                {"key": TALENT_NETWORK_ALERT_STATE_KEY},
                {
                    "$set": {
                        "key": TALENT_NETWORK_ALERT_STATE_KEY,
                        "value": {
                            "last_status": "skipped",
                            "last_reason": "no_open_jobs",
                            "last_run_id": run_id,
                            "last_run_at": summary["completed_at"],
                        },
                        "updated_at": summary["completed_at"],
                    }
                },
                upsert=True,
            )
            await _record_scheduler_heartbeat(
                TALENT_NETWORK_JOB_HEARTBEAT_ID,
                "healthy",
                "skipped no_open_jobs",
            )
            return summary

        async for member in iter_find_paginated(
            db[TALENT_NETWORK_COL],
            {"$or": [{"status": "active"}, {"status": {"$exists": False}}]},
            {
                "_id": 0,
                "network_id": 1,
                "email": 1,
                "full_name": 1,
                "role_interests": 1,
                "locations": 1,
                "work_types": 1,
                "alert_frequency": 1,
                "source": 1,
            },
            sort=[("updated_at", -1)],
            max_docs=12000,
        ):
            summary["candidates_scanned"] += 1

            email = str(member.get("email") or "").strip().lower()
            if not email:
                summary["skipped_invalid_email"] += 1
                continue

            alert_frequency = str(member.get("alert_frequency") or "weekly").strip().lower()
            if alert_frequency not in {"daily", "weekly"}:
                alert_frequency = "weekly"

            if await _already_dispatched_within_frequency(db, email, now, bool(force), alert_frequency):
                summary["skipped_recently_sent"] += 1
                continue

            role_interests = _normalize_keywords(member.get("role_interests"))
            locations = _normalize_keywords(member.get("locations"))
            work_types = _normalize_keywords(member.get("work_types"))

            matched_jobs = [
                job
                for job in open_jobs
                if _job_matches_preferences(job, role_interests, locations, work_types)
            ]

            if not matched_jobs:
                summary["skipped_no_match"] += 1
                continue

            summary["eligible_candidates"] += 1
            summary["attempted"] += 1
            scored_jobs: list[tuple[float, str, dict[str, float], dict[str, Any]]] = []
            for candidate_job in matched_jobs:
                confidence_score, confidence_label, confidence_breakdown = _compute_match_confidence(
                    job=candidate_job,
                    role_interests=role_interests,
                    locations=locations,
                    work_types=work_types,
                    now=now,
                )
                scored_jobs.append((confidence_score, confidence_label, confidence_breakdown, candidate_job))
            scored_jobs.sort(key=lambda item: item[0], reverse=True)
            top_confidence_score, top_confidence_label, top_confidence_breakdown, top_job = scored_jobs[0]

            summary["confidence_distribution"][top_confidence_label] += 1
            summary["confidence_total_score"] = round(float(summary["confidence_total_score"]) + top_confidence_score, 2)
            summary["confidence_samples"] += 1

            recipient_name = str(member.get("full_name") or "there").strip() or "there"

            send_result = await _send_talent_network_alert_email(
                recipient_email=email,
                recipient_name=recipient_name,
                job=top_job,
            )
            success = bool(send_result.get("success"))
            if success:
                summary["sent"] += 1
            else:
                summary["failed"] += 1
                if len(summary["errors"]) < 12:
                    summary["errors"].append(
                        f"{email}: {str(send_result.get('error') or 'send_failed')[:160]}"
                    )

            event_doc = {
                "event_id": f"tn_evt_{uuid.uuid4().hex[:12]}",
                "run_id": run_id,
                "network_id": str(member.get("network_id") or ""),
                "email": email,
                "status": "sent" if success else "failed",
                "source": str(member.get("source") or "unknown")[:80],
                "alert_frequency": alert_frequency,
                "matched_count": len(matched_jobs),
                "confidence_score": top_confidence_score,
                "confidence_label": top_confidence_label,
                "confidence_breakdown": top_confidence_breakdown,
                "matched_jobs": [
                    {
                        "slug": str(job.get("slug") or ""),
                        "title": str(job.get("title") or ""),
                        "department": str(job.get("department") or ""),
                        "location": str(job.get("location") or ""),
                        "type": str(job.get("type") or ""),
                    }
                    for job in matched_jobs[:3]
                ],
                "top_job_slug": str(top_job.get("slug") or ""),
                "top_job_title": str(top_job.get("title") or ""),
                "triggered_by": summary["triggered_by"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db[TALENT_NETWORK_DISPATCH_EVENTS_COL].insert_one(event_doc)

        summary["completed_at"] = datetime.now(timezone.utc).isoformat()
        await db[TALENT_NETWORK_DISPATCH_RUNS_COL].insert_one({**summary})
        await db.system_runtime_flags.update_one(
            {"key": TALENT_NETWORK_ALERT_STATE_KEY},
            {
                "$set": {
                    "key": TALENT_NETWORK_ALERT_STATE_KEY,
                    "value": {
                        "last_status": summary["status"],
                        "last_run_id": run_id,
                        "last_run_at": summary["completed_at"],
                        "last_sent": int(summary["sent"]),
                        "last_attempted": int(summary["attempted"]),
                        "last_failed": int(summary["failed"]),
                    },
                    "updated_at": summary["completed_at"],
                }
            },
            upsert=True,
        )

        detail = (
            f"open_jobs={summary['open_jobs']} sent={summary['sent']} "
            f"attempted={summary['attempted']} skipped_no_match={summary['skipped_no_match']} "
            f"avg_confidence={round((summary['confidence_total_score'] / summary['confidence_samples']), 2) if summary['confidence_samples'] > 0 else 0}"
        )
        await _record_scheduler_heartbeat(TALENT_NETWORK_JOB_HEARTBEAT_ID, "healthy", detail)
        return summary
    except Exception as exc:
        err = str(exc)[:220]
        summary["status"] = "error"
        summary["error"] = err
        summary["completed_at"] = datetime.now(timezone.utc).isoformat()
        try:
            await db[TALENT_NETWORK_DISPATCH_RUNS_COL].insert_one({**summary})
            await db.system_runtime_flags.update_one(
                {"key": TALENT_NETWORK_ALERT_STATE_KEY},
                {
                    "$set": {
                        "key": TALENT_NETWORK_ALERT_STATE_KEY,
                        "value": {
                            "last_status": "error",
                            "last_error": err,
                            "last_run_id": run_id,
                            "last_run_at": summary["completed_at"],
                        },
                        "updated_at": summary["completed_at"],
                    }
                },
                upsert=True,
            )
        except Exception:
            pass
        await _record_scheduler_heartbeat(TALENT_NETWORK_JOB_HEARTBEAT_ID, "error", err)
        logger.error("scheduled_talent_network_role_alert_dispatch failed: %s", exc)
        return summary


__all__ = [
    "TALENT_NETWORK_ALERT_STATE_KEY",
    "TALENT_NETWORK_COL",
    "TALENT_NETWORK_DISPATCH_EVENTS_COL",
    "TALENT_NETWORK_DISPATCH_RUNS_COL",
    "TALENT_NETWORK_JOB_HEARTBEAT_ID",
    "scheduled_talent_network_role_alert_dispatch",
    "scheduled_talent_network_campaign_scheduler",
]


def _campaign_member_matches_segment(member: dict[str, Any], state_map: dict[str, dict[str, Any]], segment: dict[str, Any]) -> bool:
    email = str(member.get("email") or "").strip().lower()
    if not email:
        return False
    state = state_map.get(email) or {}

    profile = int(state.get("profile_completeness") or 0)
    profile_min = max(0, min(100, int(segment.get("profile_min") or 0)))
    profile_max = max(profile_min, min(100, int(segment.get("profile_max") or 100)))
    if profile < profile_min or profile > profile_max:
        return False

    premium_state = str(segment.get("premium_state") or "any").strip().lower()
    premium_unlocked = bool(state.get("premium_unlocked") or False)
    if premium_state == "unlocked" and not premium_unlocked:
        return False
    if premium_state == "locked" and premium_unlocked:
        return False

    alert_frequency = str(segment.get("alert_frequency") or "any").strip().lower()
    member_frequency = str(member.get("alert_frequency") or "weekly").strip().lower()
    if alert_frequency in {"daily", "weekly"} and member_frequency != alert_frequency:
        return False

    reminder_channel = str(segment.get("reminder_channel") or "any").strip().lower()
    channels = [str(v or "").strip().lower() for v in (member.get("reminder_channels") or [])]
    if reminder_channel in {"in_app", "email"} and reminder_channel not in channels:
        return False

    if bool(segment.get("marketing_consent_required") or False) and not bool(member.get("consent_marketing") or False):
        return False

    return True


async def _load_campaign_state_map(db) -> dict[str, dict[str, Any]]:
    state_map: dict[str, dict[str, Any]] = {}
    async for row in db["careers_talent_network_user_state"].find(
        {},
        {"_id": 0, "email": 1, "profile_completeness": 1, "premium_unlocked": 1},
    ).limit(18000):
        email = str(row.get("email") or "").strip().lower()
        if not email:
            continue
        state_map[email] = row
    return state_map


async def scheduled_talent_network_campaign_scheduler(triggered_by: str = "scheduler:5min") -> Dict[str, Any]:
    """Execute due Talent Network campaigns created from admin campaign scheduler."""
    from routes.db import db

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    summary: dict[str, Any] = {
        "triggered_by": str(triggered_by or "scheduler:5min"),
        "started_at": now_iso,
        "campaigns_scanned": 0,
        "campaigns_executed": 0,
        "attempted": 0,
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "run_count": 0,
        "status": "success",
        "errors": [],
    }

    try:
        state_map = await _load_campaign_state_map(db)

        async for campaign in db[TALENT_NETWORK_CAMPAIGNS_COL].find(
            {
                "status": {"$in": ["scheduled", "queued"]},
                "scheduled_at": {"$lte": now_iso},
            },
            {"_id": 0},
        ).sort("scheduled_at", 1).limit(40):
            summary["campaigns_scanned"] += 1

            campaign_id = str(campaign.get("campaign_id") or "").strip().lower()
            if not campaign_id:
                continue
            segment_id = str(campaign.get("segment_id") or "").strip().lower()
            segment = await db[TALENT_NETWORK_SEGMENTS_COL].find_one({"segment_id": segment_id}, {"_id": 0})
            if not segment:
                await db[TALENT_NETWORK_CAMPAIGNS_COL].update_one(
                    {"campaign_id": campaign_id},
                    {
                        "$set": {
                            "status": "failed",
                            "failure_reason": "segment_not_found",
                            "updated_at": now_iso,
                        }
                    },
                )
                summary["failed"] += 1
                continue

            run_id = f"tn_cmp_run_{uuid.uuid4().hex[:12]}"
            attempted = 0
            sent = 0
            skipped = 0
            failed = 0
            channel = str(campaign.get("channel") or "in_app").strip().lower()

            async for member in db[TALENT_NETWORK_COL].find(
                {"$or": [{"status": "active"}, {"status": {"$exists": False}}]},
                {
                    "_id": 0,
                    "email": 1,
                    "full_name": 1,
                    "alert_frequency": 1,
                    "reminder_channels": 1,
                    "consent_marketing": 1,
                },
            ).limit(12000):
                if not _campaign_member_matches_segment(member, state_map, segment):
                    continue

                attempted += 1
                email = str(member.get("email") or "").strip().lower()
                if not email:
                    skipped += 1
                    continue

                channels = [str(v or "").strip().lower() for v in (member.get("reminder_channels") or [])]
                if channel not in channels:
                    skipped += 1
                    continue

                if channel == "in_app":
                    await db[TALENT_NETWORK_REMINDER_EVENTS_COL].insert_one(
                        {
                            "event_id": f"tn_rem_{uuid.uuid4().hex[:12]}",
                            "email": email,
                            "event_type": "campaign_delivery",
                            "action": "in_app_sent",
                            "channel": "in_app",
                            "campaign_id": campaign_id,
                            "campaign_name": str(campaign.get("campaign_name") or ""),
                            "segment_id": str(campaign.get("segment_id") or ""),
                            "segment_name": str(campaign.get("segment_name") or ""),
                            "meta": {
                                "title": str(campaign.get("message_title") or ""),
                                "body": str(campaign.get("message_body") or "")[:360],
                                "cta_label": str(campaign.get("cta_label") or "Open Talent Network"),
                                "cta_path": str(campaign.get("cta_path") or "/talent-network"),
                            },
                            "created_at": now_iso,
                        }
                    )
                    sent += 1
                else:
                    try:
                        from utils.email_service import send_catalog_template
                        result = await send_catalog_template(
                            recipient_email=email,
                            template_key="weekly_careers_job_announcement",
                            recipient_name=str(member.get("full_name") or "there").strip() or "there",
                            user_name=str(member.get("full_name") or "there").strip() or "there",
                            job_title=str(campaign.get("message_title") or "Career Reminder"),
                            department="Talent Network",
                            location="Remote",
                            role_type="Reminder",
                            apply_url=str(campaign.get("cta_path") or "/talent-network"),
                            careers_url="/talent-network",
                            subject_override=str(campaign.get("message_title") or "Talent Network Reminder")[:160],
                        )
                        if result.get("success"):
                            await db[TALENT_NETWORK_REMINDER_EVENTS_COL].insert_one(
                                {
                                    "event_id": f"tn_rem_{uuid.uuid4().hex[:12]}",
                                    "email": email,
                                    "event_type": "campaign_delivery",
                                    "action": "email_sent",
                                    "channel": "email",
                                    "campaign_id": campaign_id,
                                    "campaign_name": str(campaign.get("campaign_name") or ""),
                                    "segment_id": str(campaign.get("segment_id") or ""),
                                    "segment_name": str(campaign.get("segment_name") or ""),
                                    "meta": {
                                        "title": str(campaign.get("message_title") or ""),
                                    },
                                    "created_at": now_iso,
                                }
                            )
                            sent += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1

            run_doc = {
                "run_id": run_id,
                "campaign_id": campaign_id,
                "campaign_name": str(campaign.get("campaign_name") or ""),
                "segment_id": str(campaign.get("segment_id") or ""),
                "segment_name": str(campaign.get("segment_name") or ""),
                "channel": channel,
                "attempted": attempted,
                "sent": sent,
                "skipped": skipped,
                "failed": failed,
                "triggered_by": summary["triggered_by"],
                "created_at": now_iso,
            }
            await db[TALENT_NETWORK_CAMPAIGN_RUNS_COL].insert_one(run_doc)
            await db[TALENT_NETWORK_CAMPAIGNS_COL].update_one(
                {"campaign_id": campaign_id},
                {
                    "$set": {
                        "status": "completed",
                        "last_run_id": run_id,
                        "last_run_at": now_iso,
                        "last_run_summary": {
                            "attempted": attempted,
                            "sent": sent,
                            "skipped": skipped,
                            "failed": failed,
                        },
                        "updated_at": now_iso,
                    }
                },
            )

            summary["campaigns_executed"] += 1
            summary["run_count"] += 1
            summary["attempted"] += attempted
            summary["sent"] += sent
            summary["skipped"] += skipped
            summary["failed"] += failed

        summary["completed_at"] = datetime.now(timezone.utc).isoformat()
        await _record_scheduler_heartbeat(
            TALENT_NETWORK_CAMPAIGN_HEARTBEAT_ID,
            "healthy",
            f"campaigns={summary['campaigns_executed']} sent={summary['sent']} attempted={summary['attempted']}",
        )
        return summary
    except Exception as exc:
        err = str(exc)[:220]
        summary["status"] = "error"
        summary["error"] = err
        summary["completed_at"] = datetime.now(timezone.utc).isoformat()
        await _record_scheduler_heartbeat(TALENT_NETWORK_CAMPAIGN_HEARTBEAT_ID, "error", err)
        logger.error("scheduled_talent_network_campaign_scheduler failed: %s", exc)
        return summary
