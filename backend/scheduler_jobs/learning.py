"""
scheduler_jobs.learning — AI Learning Hub scheduled jobs.

**Phase 2 incremental domain split — eighth batch.**

Owns the recurring learning-hub automation: certificate anchoring,
integrity/assurance guards, weekly course autopublish, video
maintenance, email queue dispatcher, and synthetic canary.

Jobs in this module
===================
- ``scheduled_learning_certificate_anchor_batch`` — hourly OpenTimestamps
  certificate hash anchoring.
- ``scheduled_learning_hub_integrity_guard`` — recurring continuity/freshness
  sweep.
- ``scheduled_learning_hub_weekly_autopublish`` — weekly publish of 5
  enterprise courses with user/admin fanout.
- ``scheduled_learning_hub_video_maintenance`` — continuous course-video
  link validation + self-healing.
- ``scheduled_learning_hub_assurance_guard`` — 15-min enterprise assurance
  cycle (health / API / link / freshness).
- ``scheduled_learning_hub_email_dispatcher`` — batched delivery of
  queued learning-hub emails.
- ``scheduled_learning_hub_synthetic_canary`` — hourly full learner
  funnel synthetic continuity probe.

External callers continue to import via the facade.
"""

import logging

from scheduler_jobs.observability import _record_scheduler_heartbeat


logger = logging.getLogger("scheduler_jobs.learning")


async def scheduled_learning_certificate_anchor_batch() -> None:
    """Hourly certificate hash anchoring batch (OpenTimestamps free API flow)."""
    job_id = "learning_certificate_anchor_batch"
    try:
        from routes.ai_learning_hub import process_certificate_anchor_batch

        result = await process_certificate_anchor_batch(limit=300, triggered_by="scheduler:hourly")
        anchored = int(result.get("anchored", 0) or 0)
        pending_after = 0
        try:
            from routes.db import db

            pending_after = await db.learn_hub_certificate_anchor_queue.count_documents({"status": "pending"})
        except Exception:
            pending_after = 0

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if anchored >= 0 else "warning",
            f"anchored={anchored} batch_id={result.get('batch_id')} pending_after={pending_after}",
        )
    except Exception as e:
        logger.error(f"Certificate anchoring scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_learning_hub_integrity_guard() -> None:
    """Recurring integrity sweep for AI Learning Hub continuity and freshness."""
    job_id = "learning_hub_integrity_guard"
    try:
        from routes.ai_learning_hub import run_learning_hub_integrity_cycle

        result = await run_learning_hub_integrity_cycle(triggered_by="scheduler:hourly")
        status = str(result.get("status") or "unknown")
        checks = result.get("checks") or {}
        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if status == "healthy" else "warning" if status == "warning" else "error",
            (
                f"status={status} repaired_verify_urls={checks.get('repaired_verify_urls', 0)} "
                f"orphan_enrollments={checks.get('orphan_enrollments', 0)}"
            ),
        )
    except Exception as e:
        logger.error(f"Learning hub integrity guard scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_learning_hub_weekly_autopublish() -> None:
    """Weekly generation/publishing of 5 enterprise courses with user/admin notifications."""
    job_id = "learning_hub_weekly_autopublish"
    try:
        from routes.ai_learning_hub import ensure_weekly_course_publication

        result = await ensure_weekly_course_publication(triggered_by="scheduler:weekly")
        created_count = int(result.get("created_count", 0) or 0)
        total_count = int(result.get("total_count", 0) or 0)
        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if total_count >= 5 else "warning",
            f"week={result.get('week_key')} total={total_count} created={created_count}",
        )
    except Exception as e:
        logger.error(f"Weekly learning hub autopublish scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_learning_hub_video_maintenance() -> None:
    """Continuous validation and self-healing for course video links and accessibility."""
    job_id = "learning_hub_video_maintenance"
    try:
        from routes.ai_learning_hub import validate_and_repair_learning_hub_videos

        report = await validate_and_repair_learning_hub_videos(limit=1000)
        broken = int(report.get("broken_links", 0) or 0)
        repaired = int(report.get("repaired_lessons", 0) or 0)
        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if broken == 0 else "warning",
            f"checked_lessons={report.get('checked_lessons')} broken={broken} repaired={repaired}",
        )
    except Exception as e:
        logger.error(f"Learning hub video maintenance scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_learning_hub_assurance_guard() -> None:
    """Enterprise assurance cycle: health/API/link/freshness checks with runtime enforcement."""
    job_id = "learning_hub_assurance_guard"
    try:
        from routes.ai_learning_hub import run_learning_hub_assurance_cycle

        result = await run_learning_hub_assurance_cycle(triggered_by="scheduler:15min")
        status = str(result.get("status") or "unknown")
        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if status == "healthy" else "warning",
            (
                f"status={status} score={(result.get('platform_health') or {}).get('score')} "
                f"video_broken={(result.get('videos') or {}).get('broken_links')}"
            ),
        )
    except Exception as e:
        logger.error(f"Learning hub assurance guard scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_learning_hub_email_dispatcher() -> None:
    """Dispatch queued learning hub emails in batches for reliable delivery."""
    job_id = "learning_hub_email_dispatcher"
    try:
        from routes.ai_learning_hub import process_learning_hub_email_queue
        from routes.db import db

        result = await process_learning_hub_email_queue(batch_size=150)
        pending = await db.learn_hub_email_queue.count_documents({"status": "pending"})
        await _record_scheduler_heartbeat(
            job_id,
            "healthy",
            (
                f"processed={result.get('processed')} sent={result.get('sent')} "
                f"failed={result.get('failed')} pending={pending}"
            ),
        )
    except Exception as e:
        logger.error(f"Learning hub email dispatcher scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_learning_hub_synthetic_canary() -> None:
    """Hourly synthetic canary for full learner funnel continuity."""
    job_id = "learning_hub_synthetic_canary"
    try:
        from routes.ai_learning_hub import run_learning_hub_synthetic_canary

        result = await run_learning_hub_synthetic_canary(triggered_by="scheduler:hourly")
        status = str(result.get("status") or "unknown")
        warnings = len(result.get("issues") or [])
        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if status == "healthy" else "warning",
            f"status={status} warnings={warnings} run_id={result.get('run_id')}",
        )
    except Exception as e:
        logger.error(f"Learning hub synthetic canary scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


__all__ = [
    "scheduled_learning_certificate_anchor_batch",
    "scheduled_learning_hub_integrity_guard",
    "scheduled_learning_hub_weekly_autopublish",
    "scheduled_learning_hub_video_maintenance",
    "scheduled_learning_hub_assurance_guard",
    "scheduled_learning_hub_email_dispatcher",
    "scheduled_learning_hub_synthetic_canary",
]
