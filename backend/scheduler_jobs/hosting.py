"""
scheduler_jobs.hosting — Assigned-host guardian scheduled job.

**Phase 2 incremental domain split — batch #22.**

Owns the every-5-minute assigned-host drift monitor + safe
auto-fallback that keeps the platform pinned to the correct
preview/production host.

Jobs in this module
===================
- ``scheduled_assigned_host_guardian`` — drift monitor with safe auto
  fallback, persistent config gate, and alerting.

Internal helpers
================
- ``_run_scheduled_assigned_host_guard`` — internal POST helper that
  hits the admin platform-health endpoint via a scheduler-minted JWT.
"""

import asyncio
import logging
from typing import Any, Dict

import requests

from scheduler_jobs.admin_context import _mint_scheduler_admin_token
from scheduler_jobs.observability import _record_scheduler_heartbeat


logger = logging.getLogger("scheduler_jobs.hosting")


async def _run_scheduled_assigned_host_guard(*, triggered_by: str) -> Dict[str, Any]:
    token = await _mint_scheduler_admin_token(minutes=45)
    if not token:
        return {
            "ok": False,
            "status_code": 0,
            "error": "scheduler_admin_token_unavailable",
        }

    url = (
        "http://127.0.0.1:8001/api/admin/platform-health/assigned-host/run"
        f"?triggered_by={triggered_by}"
        "&allow_auto_fallback=true"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    def _post():
        return requests.post(url, headers=headers, timeout=140)

    response = await asyncio.to_thread(_post)
    payload: Dict[str, Any]
    try:
        payload = response.json()
    except Exception:
        payload = {"_raw": (response.text or "")[:240]}

    run = payload.get("run") if isinstance(payload, dict) else {}
    alerts = (run or {}).get("alerts") if isinstance(run, dict) else {}
    fallback = (run or {}).get("auto_fallback") if isinstance(run, dict) else {}

    return {
        "ok": response.status_code == 200,
        "status_code": response.status_code,
        "payload": payload,
        "status": str((run or {}).get("status") or "unknown"),
        "severity": str((run or {}).get("severity") or "unknown"),
        "fail_streak": int((run or {}).get("fail_streak") or 0),
        "fallback_applied": bool((fallback or {}).get("applied")),
        "notification_sent": int((alerts or {}).get("sent") or 0),
    }


async def scheduled_assigned_host_guardian():
    """Every 5 minutes: assigned-host drift monitor + safe auto-fallback with alerting."""
    job_id = "assigned_host_guardian"
    try:
        from routes.db import db

        cfg_doc = await db.system_runtime_flags.find_one(
            {"key": "assigned_host_guard_config"},
            {"_id": 0, "value": 1},
        ) or {}
        cfg_value = cfg_doc.get("value") if isinstance(cfg_doc.get("value"), dict) else {}
        enabled = bool(cfg_value.get("enabled", True))
        if not enabled:
            await _record_scheduler_heartbeat(job_id, "skipped", "reason=config_disabled")
            return

        result = await _run_scheduled_assigned_host_guard(triggered_by="scheduler:assigned-host-guard")
        status = str(result.get("status") or "unknown")
        heartbeat = "healthy" if result.get("ok") and status == "pass" else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat,
            (
                f"http={result.get('status_code')} status={status} severity={result.get('severity')} "
                f"fail_streak={result.get('fail_streak')} fallback={result.get('fallback_applied')} "
                f"notifications={result.get('notification_sent')}"
            )[:390],
        )
    except Exception as exc:
        logger.error(f"Assigned-host guardian scheduler failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


__all__ = [
    "_run_scheduled_assigned_host_guard",
    "scheduled_assigned_host_guardian",
]
