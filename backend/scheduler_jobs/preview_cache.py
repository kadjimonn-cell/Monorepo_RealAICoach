"""
scheduler_jobs.preview_cache — Preview cache hygiene scheduled jobs.

**Phase 2 incremental domain split — batch #11.**

Owns the hourly and nightly preview-cache hygiene sweeps that keep the
preview-shell consistent with the canonical source tree.

Jobs in this module
===================
- ``scheduled_preview_cache_hygiene_hourly``
- ``scheduled_preview_cache_hygiene_nightly``
"""

import asyncio
import logging
import requests
from typing import Any, Dict

from scheduler_jobs.observability import _record_scheduler_heartbeat
from scheduler_jobs.admin_context import _mint_scheduler_admin_token


logger = logging.getLogger("scheduler_jobs.preview_cache")


async def scheduled_preview_cache_hygiene_hourly():
    """Hourly preview cache hygiene monitor with scheduler heartbeat reporting."""
    job_id = "preview_cache_hygiene_hourly"
    try:
        result = await asyncio.wait_for(
            _run_scheduled_preview_cache_hygiene(triggered_by="scheduler:hourly"),
            timeout=180,
        )
        status = str(result.get("status") or "unknown")
        heartbeat = "healthy" if result.get("ok") else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat,
            f"status={status} severity={result.get('severity')} fail_count={result.get('fail_count')} alert_sent={result.get('alert_sent')} fail_streak={result.get('alert_fail_streak')} incident_opened={result.get('incident_opened')} incident_id={result.get('incident_id') or 'none'}",
        )
    except Exception as exc:
        logger.error(f"Hourly preview cache hygiene monitor failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_preview_cache_hygiene_nightly():
    """Nightly preview cache hygiene monitor with scheduler heartbeat reporting."""
    job_id = "preview_cache_hygiene_nightly"
    try:
        result = await asyncio.wait_for(
            _run_scheduled_preview_cache_hygiene(triggered_by="scheduler:nightly"),
            timeout=180,
        )
        status = str(result.get("status") or "unknown")
        heartbeat = "healthy" if result.get("ok") else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat,
            f"status={status} severity={result.get('severity')} fail_count={result.get('fail_count')} alert_sent={result.get('alert_sent')} fail_streak={result.get('alert_fail_streak')} incident_opened={result.get('incident_opened')} incident_id={result.get('incident_id') or 'none'}",
        )
    except Exception as exc:
        logger.error(f"Nightly preview cache hygiene monitor failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


__all__ = [
    "scheduled_preview_cache_hygiene_hourly",
    "scheduled_preview_cache_hygiene_nightly",
]


# ─────────────────────────────────────────────────────────────
# Phase 2 batch #24 — Helpers relocated from `scheduler_jobs/_legacy.py`.
# These were previously called as unbound names which silently raised
# NameError at runtime (swallowed by try/except heartbeat wrappers).
# Moving them here makes them resolvable via the module's own globals.
# ─────────────────────────────────────────────────────────────

async def _run_scheduled_preview_cache_hygiene(*, triggered_by: str) -> Dict[str, Any]:
    token = await _mint_scheduler_admin_token(minutes=45)
    if not token:
        return {
            "ok": False,
            "status_code": 0,
            "error": "scheduler_admin_token_unavailable",
        }

    url = (
        "http://127.0.0.1:8001/api/admin/platform-health/preview-cache-hygiene/run"
        f"?triggered_by={triggered_by}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    def _post():
        return requests.post(url, headers=headers, timeout=180)

    response = await asyncio.to_thread(_post)
    payload: Dict[str, Any]
    try:
        payload = response.json()
    except Exception:
        payload = {"_raw": (response.text or "")[:240]}

    scan = payload.get("scan") if isinstance(payload, dict) else {}
    alert = payload.get("alert") if isinstance(payload, dict) else {}
    incident = payload.get("incident") if isinstance(payload, dict) else {}
    incident_doc = incident.get("incident") if isinstance(incident, dict) else {}
    return {
        "ok": response.status_code == 200 and str((scan or {}).get("status") or "") == "pass",
        "status_code": response.status_code,
        "payload": payload,
        "status": str((scan or {}).get("status") or "unknown"),
        "severity": str((scan or {}).get("severity") or "unknown"),
        "fail_count": int((scan or {}).get("fail_count") or 0),
        "alert_sent": int((alert or {}).get("sent") or 0),
        "alert_fail_streak": int((alert or {}).get("fail_streak") or 0),
        "incident_opened": bool((incident or {}).get("opened")),
        "incident_id": str((incident_doc or {}).get("incident_id") or ""),
    }
