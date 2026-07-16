"""
scheduler_jobs.global_parity — Global parity audit scheduled jobs.

**Phase 2 incremental domain split — batch #12.**

Owns the hourly and nightly global-parity audits that compare admin
dashboard data parity across regions/tenants/locales.

Jobs in this module
===================
- ``scheduled_global_parity_audit_hourly``
- ``scheduled_global_parity_audit_nightly``
"""

import asyncio
import logging
import shutil
import requests
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from scheduler_jobs.observability import _record_scheduler_heartbeat
from scheduler_jobs.admin_context import _mint_scheduler_admin_token
from scheduler_jobs.utils import _parse_iso_datetime


logger = logging.getLogger("scheduler_jobs.global_parity")


async def scheduled_global_parity_audit_hourly():
    """Hourly safe parity check with guardrails, lock, and cooldown."""
    job_id = "global_parity_audit_hourly"
    lock_key = "global_parity_audit_hourly_lock"
    lock_acquired = False
    try:
        safe_config = await _load_global_parity_safe_config()
        precheck = await _global_parity_safe_precheck(
            job_id=job_id,
            requested_full_check=False,
            min_interval_minutes=int(safe_config.get("hourly_min_interval_minutes") or 45),
            safe_config=safe_config,
        )
        if precheck.get("action") == "skip":
            await _record_scheduler_heartbeat(
                job_id,
                "skipped",
                f"reason={precheck.get('reason')} disk={precheck.get('disk_free_mb')} load={precheck.get('load_avg_1m')} relaxed={precheck.get('maintenance_relax_active')} safe_reasons={','.join(precheck.get('safe_reasons') or []) or 'none'}",
            )
            return

        lock_acquired = await _acquire_global_parity_scheduler_lock(
            lock_key,
            ttl_seconds=int(safe_config.get("lock_ttl_seconds") or 900),
        )
        if not lock_acquired:
            await _record_scheduler_heartbeat(job_id, "skipped", "reason=lock_active")
            return

        max_runtime_seconds = int(safe_config.get("max_runtime_seconds") or 120)
        result = await asyncio.wait_for(
            _run_scheduled_global_parity_audit(
                run_admin_checks=False,
                triggered_by="scheduler:hourly",
            ),
            timeout=max_runtime_seconds,
        )
        status = str(result.get("overall_status") or "unknown")
        heartbeat = "healthy" if result.get("ok") and status == "pass" else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat,
            f"http={result.get('status_code')} status={status} severity={result.get('severity')} instance_match={result.get('instance_match')} notifications={result.get('notification_sent')} mode=lightweight fallback=False relaxed={precheck.get('maintenance_relax_active')} max_runtime_s={max_runtime_seconds} safe_reasons={','.join(precheck.get('safe_reasons') or []) or 'none'}",
        )
    except Exception as exc:
        logger.error(f"Hourly global parity audit failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])
    finally:
        if lock_acquired:
            try:
                await _release_global_parity_scheduler_lock(lock_key)
            except Exception:
                pass


async def scheduled_global_parity_audit_nightly():
    """Nightly safe parity check with auto-fallback to lightweight mode when unstable."""
    job_id = "global_parity_audit_nightly"
    lock_key = "global_parity_audit_nightly_lock"
    lock_acquired = False
    try:
        safe_config = await _load_global_parity_safe_config()
        precheck = await _global_parity_safe_precheck(
            job_id=job_id,
            requested_full_check=True,
            min_interval_minutes=int(safe_config.get("nightly_min_interval_minutes") or 720),
            safe_config=safe_config,
        )
        if precheck.get("action") == "skip":
            await _record_scheduler_heartbeat(
                job_id,
                "skipped",
                f"reason={precheck.get('reason')} disk={precheck.get('disk_free_mb')} load={precheck.get('load_avg_1m')} relaxed={precheck.get('maintenance_relax_active')} safe_reasons={','.join(precheck.get('safe_reasons') or []) or 'none'}",
            )
            return

        lock_acquired = await _acquire_global_parity_scheduler_lock(
            lock_key,
            ttl_seconds=int(safe_config.get("lock_ttl_seconds") or 900),
        )
        if not lock_acquired:
            await _record_scheduler_heartbeat(job_id, "skipped", "reason=lock_active")
            return

        run_admin_checks = bool(precheck.get("run_admin_checks"))
        effective_triggered_by = "scheduler:nightly:fallback-light" if not run_admin_checks else "scheduler:nightly"
        max_runtime_seconds = int(safe_config.get("max_runtime_seconds") or 120)
        result = await asyncio.wait_for(
            _run_scheduled_global_parity_audit(
                run_admin_checks=run_admin_checks,
                triggered_by=effective_triggered_by,
            ),
            timeout=max_runtime_seconds,
        )
        status = str(result.get("overall_status") or "unknown")
        heartbeat = "healthy" if result.get("ok") and status == "pass" else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat,
            f"http={result.get('status_code')} status={status} severity={result.get('severity')} instance_match={result.get('instance_match')} notifications={result.get('notification_sent')} mode={'full' if run_admin_checks else 'lightweight'} fallback={precheck.get('fallback_applied')} relaxed={precheck.get('maintenance_relax_active')} max_runtime_s={max_runtime_seconds} safe_reasons={','.join(precheck.get('safe_reasons') or []) or 'none'}",
        )
    except Exception as exc:
        logger.error(f"Nightly global parity audit failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])
    finally:
        if lock_acquired:
            try:
                await _release_global_parity_scheduler_lock(lock_key)
            except Exception:
                pass


__all__ = [
    "scheduled_global_parity_audit_hourly",
    "scheduled_global_parity_audit_nightly",
]


# ─────────────────────────────────────────────────────────────
# Phase 2 batch #24 — Helpers relocated from `scheduler_jobs/_legacy.py`.
# These were previously called as unbound names which silently raised
# NameError at runtime (swallowed by try/except heartbeat wrappers).
# Moving them here makes them resolvable via the module's own globals.
# ─────────────────────────────────────────────────────────────

def _default_global_parity_safe_config() -> Dict[str, Any]:
    return {
        "hourly_min_interval_minutes": int(os.environ.get("GLOBAL_PARITY_SAFE_HOURLY_MIN_INTERVAL_MINUTES", "45") or 45),
        "nightly_min_interval_minutes": int(os.environ.get("GLOBAL_PARITY_SAFE_NIGHTLY_MIN_INTERVAL_MINUTES", "720") or 720),
        "min_disk_mb": float(os.environ.get("GLOBAL_PARITY_SAFE_MIN_DISK_MB", "220") or 220),
        "hard_floor_mb": float(os.environ.get("GLOBAL_PARITY_SAFE_HARD_FLOOR_MB", "140") or 140),
        "max_load_avg": float(os.environ.get("GLOBAL_PARITY_SAFE_MAX_LOAD_AVG", "12") or 12),
        "max_runtime_seconds": int(os.environ.get("GLOBAL_PARITY_SAFE_MAX_RUNTIME_SECONDS", "120") or 120),
        "lock_ttl_seconds": int(os.environ.get("GLOBAL_PARITY_SAFE_LOCK_TTL_SECONDS", "900") or 900),
    }

async def _load_global_parity_safe_config() -> Dict[str, Any]:
    from routes.db import db

    defaults = _default_global_parity_safe_config()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    flag_doc = await db.system_runtime_flags.find_one(
        {"key": "global_parity_safe_config"},
        {"_id": 0, "value": 1},
    ) or {}
    value = dict(flag_doc.get("value") or {})

    maintenance_relax_until = str(value.get("maintenance_relax_until") or "")
    previous_config = dict(value.get("maintenance_previous_config") or {})
    relax_until_dt = _parse_iso_datetime(maintenance_relax_until)

    # Automatic rollback when relax window expires.
    if relax_until_dt and relax_until_dt <= now and previous_config:
        rolled_back = {
            **defaults,
            **previous_config,
            "maintenance_relax_active": False,
            "maintenance_relax_until": "",
            "maintenance_previous_config": {},
            "maintenance_last_roll_back_at": now_iso,
            "updated_at": now_iso,
        }
        await db.system_runtime_flags.update_one(
            {"key": "global_parity_safe_config"},
            {"$set": {"key": "global_parity_safe_config", "value": rolled_back, "updated_at": now_iso}},
            upsert=True,
        )
        value = dict(rolled_back)
        relax_until_dt = None

    merged = {**defaults, **value}
    is_relaxed = bool(relax_until_dt and relax_until_dt > now and merged.get("maintenance_relax_active"))
    merged["maintenance_relax_active"] = is_relaxed
    merged["maintenance_relax_until"] = maintenance_relax_until if is_relaxed else ""

    return merged

async def _acquire_global_parity_scheduler_lock(lock_key: str, ttl_seconds: int = 900) -> bool:
    from routes.db import db

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expires_at = (now + timedelta(seconds=max(60, int(ttl_seconds or 900)))).isoformat()

    result = await db.system_runtime_flags.update_one(
        {
            "key": lock_key,
            "$or": [
                {"locked": {"$ne": True}},
                {"lock_expires_at": {"$lt": now_iso}},
            ],
        },
        {
            "$set": {
                "key": lock_key,
                "locked": True,
                "lock_acquired_at": now_iso,
                "lock_expires_at": expires_at,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )
    return bool(result.modified_count or result.upserted_id)

async def _release_global_parity_scheduler_lock(lock_key: str) -> None:
    from routes.db import db

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.system_runtime_flags.update_one(
        {"key": lock_key},
        {
            "$set": {
                "locked": False,
                "lock_released_at": now_iso,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

async def _global_parity_safe_precheck(
    *,
    job_id: str,
    requested_full_check: bool,
    min_interval_minutes: int,
    safe_config: Dict[str, Any],
) -> Dict[str, Any]:
    from routes.db import db

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    disk_usage = shutil.disk_usage("/app")
    disk_free_mb = round(float(disk_usage.free) / (1024 * 1024), 2)
    min_disk_mb = float(safe_config.get("min_disk_mb") or 220)
    hard_disk_floor_mb = float(safe_config.get("hard_floor_mb") or 140)
    max_load_avg = float(safe_config.get("max_load_avg") or 12)

    load_avg_1m = None
    try:
        load_avg_1m = float(os.getloadavg()[0])
    except Exception:
        load_avg_1m = None

    reasons: list[str] = []
    if disk_free_mb < min_disk_mb:
        reasons.append(f"low_disk:{disk_free_mb}mb")

    platform_cache_state_doc = await db.system_runtime_flags.find_one(
        {"key": "platform_cache_freshness_state"},
        {"_id": 0, "value": 1},
    ) or {}
    platform_cache_state = platform_cache_state_doc.get("value") or {}
    if bool(platform_cache_state.get("disk_pressure")):
        reasons.append("platform_disk_pressure")

    if load_avg_1m is not None and load_avg_1m > max_load_avg:
        reasons.append(f"high_load:{round(load_avg_1m, 2)}")

    latest_scheduler_run = await db.platform_global_parity_audits.find_one(
        {"triggered_by": {"$regex": "^scheduler:"}},
        {"_id": 0, "created_at": 1, "overall_status": 1},
        sort=[("created_at", -1)],
    ) or {}
    latest_dt = _parse_iso_datetime(str(latest_scheduler_run.get("created_at") or ""))
    min_interval_seconds = max(0, int(min_interval_minutes or 0) * 60)
    if latest_dt and min_interval_seconds > 0 and (now - latest_dt).total_seconds() < min_interval_seconds:
        return {
            "action": "skip",
            "reason": "cooldown_window",
            "run_admin_checks": False,
            "fallback_applied": False,
            "safe_reasons": reasons,
            "disk_free_mb": disk_free_mb,
            "load_avg_1m": load_avg_1m,
            "maintenance_relax_active": bool(safe_config.get("maintenance_relax_active")),
            "now_iso": now_iso,
        }

    recent_scheduler_runs = await db.platform_global_parity_audits.find(
        {"triggered_by": {"$regex": "^scheduler:"}},
        {"_id": 0, "overall_status": 1},
    ).sort("created_at", -1).limit(3).to_list(3)
    if len(recent_scheduler_runs) >= 3 and all(str(r.get("overall_status") or "") == "fail" for r in recent_scheduler_runs):
        reasons.append("recent_scheduler_fail_streak")

    if disk_free_mb < hard_disk_floor_mb:
        return {
            "action": "skip",
            "reason": "hard_disk_floor",
            "run_admin_checks": False,
            "fallback_applied": False,
            "safe_reasons": reasons,
            "disk_free_mb": disk_free_mb,
            "load_avg_1m": load_avg_1m,
            "maintenance_relax_active": bool(safe_config.get("maintenance_relax_active")),
            "now_iso": now_iso,
        }

    fallback_applied = False
    run_admin_checks = bool(requested_full_check)
    if requested_full_check and reasons:
        run_admin_checks = False
        fallback_applied = True

    await db.system_runtime_flags.update_one(
        {"key": f"{job_id}_safe_runtime_state"},
        {
            "$set": {
                "key": f"{job_id}_safe_runtime_state",
                "updated_at": now_iso,
                "requested_full_check": bool(requested_full_check),
                "run_admin_checks": run_admin_checks,
                "fallback_applied": fallback_applied,
                "safe_reasons": reasons,
                "disk_free_mb": disk_free_mb,
                "load_avg_1m": load_avg_1m,
                "maintenance_relax_active": bool(safe_config.get("maintenance_relax_active")),
                "config_snapshot": {
                    "hourly_min_interval_minutes": int(safe_config.get("hourly_min_interval_minutes") or 45),
                    "nightly_min_interval_minutes": int(safe_config.get("nightly_min_interval_minutes") or 720),
                    "min_disk_mb": float(safe_config.get("min_disk_mb") or 220),
                    "hard_floor_mb": float(safe_config.get("hard_floor_mb") or 140),
                    "max_load_avg": float(safe_config.get("max_load_avg") or 12),
                    "max_runtime_seconds": int(safe_config.get("max_runtime_seconds") or 120),
                    "lock_ttl_seconds": int(safe_config.get("lock_ttl_seconds") or 900),
                },
            }
        },
        upsert=True,
    )

    return {
        "action": "run",
        "reason": "ok",
        "run_admin_checks": run_admin_checks,
        "fallback_applied": fallback_applied,
        "safe_reasons": reasons,
        "disk_free_mb": disk_free_mb,
        "load_avg_1m": load_avg_1m,
        "maintenance_relax_active": bool(safe_config.get("maintenance_relax_active")),
        "now_iso": now_iso,
    }

async def _run_scheduled_global_parity_audit(*, run_admin_checks: bool, triggered_by: str) -> Dict[str, Any]:
    token = await _mint_scheduler_admin_token(minutes=45)
    if not token:
        return {
            "ok": False,
            "status_code": 0,
            "error": "scheduler_admin_token_unavailable",
        }

    url = (
        "http://127.0.0.1:8001/api/admin/platform-health/global-parity-audit/run"
        f"?run_admin_checks={'true' if run_admin_checks else 'false'}"
        f"&triggered_by={triggered_by}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    def _post():
        return requests.post(url, headers=headers, timeout=120)

    response = await asyncio.to_thread(_post)
    payload: Dict[str, Any]
    try:
        payload = response.json()
    except Exception:
        payload = {"_raw": (response.text or "")[:240]}

    audit = payload.get("audit") if isinstance(payload, dict) else {}
    notification = payload.get("notification") if isinstance(payload, dict) else {}
    return {
        "ok": response.status_code == 200,
        "status_code": response.status_code,
        "payload": payload,
        "overall_status": str((audit or {}).get("overall_status") or "unknown"),
        "severity": str((audit or {}).get("severity") or "unknown"),
        "instance_match": bool((audit or {}).get("instance_match")),
        "notification_sent": int((notification or {}).get("sent") or 0),
    }
