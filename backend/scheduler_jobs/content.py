"""
scheduler_jobs.content — Content automation scheduled jobs.

**Phase 2 incremental domain split — seventh batch.**

Owns the recurring content-drop pipeline. Currently scoped to the
daily watch-videos drop; intended expansion target for the
content-studio rotation, blog-post automation, and word-forge
content pipelines once their underlying domain routes stabilize.

Jobs in this module
===================
- ``scheduled_watch_videos_daily_drop`` — daily insertion of 2 curated
  videos plus in-app and email notification fanout.

External callers (`scheduler.py`) continue to import via the facade:
    from scheduler_jobs import scheduled_watch_videos_daily_drop
"""

from typing import Any, Dict

from scheduler_jobs.observability import _record_scheduler_heartbeat


async def scheduled_watch_videos_daily_drop() -> Dict[str, Any]:
    """Daily insertion of 2 curated videos + in-app and email notification fanout."""
    job_id = "watch_videos_daily_drop"
    try:
        from routes.watch_videos import run_watch_videos_daily_drop

        summary = await run_watch_videos_daily_drop(triggered_by="scheduler:daily")
        status = "healthy" if summary.get("status") in {"ok", "skipped"} else "degraded"
        detail = (
            f"status={summary.get('status')} inserted={summary.get('inserted_count', 0)} "
            f"notified={summary.get('in_app_notified', 0)}"
        )
        await _record_scheduler_heartbeat(job_id, status, detail)
        return summary
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "degraded", f"error={str(exc)[:220]}")
        return {"status": "error", "error": str(exc)[:220]}


__all__ = ["scheduled_watch_videos_daily_drop"]
