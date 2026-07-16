"""
scheduler_jobs.observability — Heartbeat & status persistence for scheduled jobs.

**Phase 2 incremental domain split — second batch.**

Centralizes the observability primitives that every scheduled job uses
to report its last-run status. Used by 100+ jobs in `_legacy.py` plus
external callers in `services/gtec_scan_v2.py` and `scheduler.py`.

Why split this out
==================
- It's pure observability (writes only) — never raises, never blocks.
- It's a leaf dependency: takes only stdlib types, defers `routes.db`
  to runtime to avoid import cycles during module load.
- It's the most cross-referenced helper in `_legacy.py`, so extracting
  it gives every future migration cleaner observability hooks.

The canonical implementation lives here; `scheduler_jobs/_legacy.py`
re-imports it so existing call sites resolve to the SAME function
object (verified in the regression suite).
"""

from datetime import datetime, timezone
from typing import Any, Dict, Final


_HEARTBEAT_DETAIL_MAX_CHARS: Final[int] = 400


async def _record_scheduler_heartbeat(job_id: str, status: str, detail: str = "") -> None:
    """Persist last-run heartbeat for scheduler observability and enterprise control plane.

    Non-blocking by design: heartbeat writes MUST NOT break the critical
    job they instrument. Any exception is swallowed and the function
    returns silently.

    Parameters
    ----------
    job_id:
        Stable identifier for the scheduled job (e.g. ``bill_generator_hourly_daemon``).
    status:
        Free-form status token used by the admin dashboard — typically
        one of ``healthy``, ``degraded``, ``error``, ``skipped``.
    detail:
        Optional human-readable summary line. Capped at 400 chars so the
        heartbeat document stays small in MongoDB.
    """
    try:
        # Deferred import keeps this module a leaf dependency and avoids
        # import-cycle headaches when scheduler_jobs is loaded early.
        from routes.db import db

        now_iso = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {
            "job_id": job_id,
            "status": status,
            "detail": (detail or "")[:_HEARTBEAT_DETAIL_MAX_CHARS],
            "last_run": now_iso,
            "updated_at": now_iso,
        }
        await db.scheduler_heartbeats.update_one(
            {"job_id": job_id},
            {"$set": {**payload}},
            upsert=True,
        )
    except Exception:
        # Non-blocking by design; heartbeat must never break critical jobs.
        return


__all__ = ["_record_scheduler_heartbeat"]
