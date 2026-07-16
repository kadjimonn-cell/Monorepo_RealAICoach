"""
scheduler_jobs.security — Security audit & enforcement scheduled jobs.

**Phase 2 incremental domain split — fourth batch.**

Owns the recurring security-posture jobs that operate the platform's
zero-trust mitigation, production policy gate, release intelligence
rollback, GTEC/Safe-Auto runbook monitoring, and the executive daily
digest emails.

Jobs in this module
===================
- ``scheduled_release_intelligence_monitor`` — auto-rollback on negative
  release impact (Issue 13 / release-safety).
- ``scheduled_production_security_policy_gate`` — recurring SLA / CIA-gate
  evaluator with signed audit snapshots and admin notification fanout.
- ``scheduled_zero_trust_auto_mitigation`` — continuous + threshold-based
  zero-trust mitigation cycles.
- ``scheduled_zero_trust_daily_email_digest`` — daily executive summary
  email for admins.
- ``scheduled_security_incident_runbook_monitor`` — GTEC C5 / Go-Live
  runbook Safe-Auto monitor (every 3 hours).

External callers (`scheduler.py`) continue to import via the facade:
    from scheduler_jobs import scheduled_zero_trust_auto_mitigation, ...

Imports are deferred where they depend on `routes.*` to keep this
module load-order-safe.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from scheduler_jobs.observability import _record_scheduler_heartbeat


logger = logging.getLogger("scheduler_jobs.security")


# ── Release intelligence (auto-rollback) ─────────────────────────────────


async def scheduled_release_intelligence_monitor() -> None:
    """Evaluate recent releases and auto-rollback on negative impact."""
    job_id = "release_intelligence_monitor"
    try:
        from routes.security_engine import run_release_intelligence_monitor

        result = await run_release_intelligence_monitor(trigger="scheduler")
        detail = (
            f"evaluated={result.get('evaluated', 0)} "
            f"stable={result.get('stable', 0)} "
            f"rolled_back={result.get('rolled_back', 0)}"
        )
        await _record_scheduler_heartbeat(job_id, "healthy", detail)
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:200])


# ── Production security policy gate ──────────────────────────────────────


async def scheduled_production_security_policy_gate() -> None:
    """Recurring production policy gate evaluator with signed audit snapshots.

    Persists a snapshot to ``production_security_policy_gate_runs`` and
    updates the ``production_security_policy_gate_state`` runtime flag.
    On state transitions (PASS↔FAIL), emits a realtime admin alert and
    fans out individual notifications to every admin user.
    """
    job_id = "production_security_policy_gate"
    try:
        from routes.db import db
        from routes.admin_push_notifications import emit_realtime_alert
        from utils.production_security_policy_gate import (
            collect_policy_gate_signals,
            sign_policy_payload,
        )

        snapshot = await collect_policy_gate_signals(db_ref=db)
        status = "pass" if snapshot.get("passed") else "fail"
        failed_checks = list(snapshot.get("failed_checks", []))
        now_iso = datetime.now(timezone.utc).isoformat()

        signature = sign_policy_payload(
            {
                "ran_at": now_iso,
                "status": status,
                "failed_checks": failed_checks,
                "cia_score": snapshot.get("cia_score"),
            }
        )

        await db.production_security_policy_gate_runs.insert_one(
            {
                "ran_at": now_iso,
                "status": status,
                "failed_checks": failed_checks,
                "snapshot": snapshot,
                "signature": signature,
            }
        )

        key = "production_security_policy_gate_state"
        prev = await db.system_runtime_flags.find_one({"key": key}, {"_id": 0}) or {}
        prev_state = str(prev.get("state") or "")
        changed = bool(prev_state) and prev_state != status

        await db.system_runtime_flags.update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "state": status,
                    "previous_state": prev_state or None,
                    "changed": changed,
                    "last_run_at": now_iso,
                    "failed_checks": failed_checks,
                    "cia_score": snapshot.get("cia_score"),
                    "signature": signature,
                }
            },
            upsert=True,
        )

        if changed:
            severity = "critical" if status == "fail" else "info"
            title = "Production Security Policy Gate State Changed"
            message = (
                f"Production security policy gate changed PASS → FAIL. "
                f"Failed checks: {', '.join(failed_checks) if failed_checks else 'unknown'}."
                if status == "fail"
                else "Production security policy gate recovered FAIL → PASS."
            )

            await emit_realtime_alert(
                alert_type="production_security_policy_gate_state_change",
                severity=severity,
                title=title,
                message=message,
            )

            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(100)
            for adm in admins:
                uid = str(adm.get("user_id") or "")
                if not uid:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"production_policy_gate_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": uid,
                        "type": "production_security_policy_gate_state_change",
                        "title": title,
                        "message": message,
                        "read": False,
                        "created_at": now_iso,
                        "metadata": {
                            "state": status,
                            "previous_state": prev_state,
                            "failed_checks": failed_checks,
                            "cia_score": snapshot.get("cia_score"),
                        },
                    }
                )

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if status == "pass" else "warning",
            f"state={status} changed={changed} failed={','.join(failed_checks) if failed_checks else 'none'}",
        )
    except Exception as e:
        logger.error(f"Production security policy gate scheduler failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


# ── Zero-trust mitigation ────────────────────────────────────────────────


async def scheduled_zero_trust_auto_mitigation() -> None:
    """Continuous + threshold-based zero-trust mitigation with integrated auto-fix runs."""
    job_id = "zero_trust_auto_mitigation"
    try:
        from routes.autonomous_engine import run_zero_trust_auto_mitigation_cycle, _get_engine_config

        config = await _get_engine_config()
        policy = config.get("zero_trust_policy", {})
        if not bool(policy.get("enabled", True)):
            await _record_scheduler_heartbeat(job_id, "skipped", "zero_trust_automation disabled")
            return

        result = await run_zero_trust_auto_mitigation_cycle(triggered_by="scheduler")
        status = str(result.get("status") or "UNKNOWN")
        signals = result.get("signals") or {}
        threat = str(signals.get("threat_level") or "unknown").upper()
        score = signals.get("threat_score", 0)
        action_counts = (result.get("actions") or {})
        applied = int(action_counts.get("applied", 0))
        queued = int(action_counts.get("queued", 0))
        heartbeat_status = "healthy" if status in {"MITIGATED", "MONITORING", "EXECUTED_NO_ACTION"} else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat_status,
            f"status={status} threat={threat} score={score} applied={applied} queued={queued} trigger_hit={result.get('trigger_hit')}",
        )
        logger.info(
            "Zero-trust mitigation: status=%s threat=%s score=%s applied=%s queued=%s",
            status,
            threat,
            score,
            applied,
            queued,
        )
    except Exception as exc:
        logger.error(f"scheduled_zero_trust_auto_mitigation failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_zero_trust_daily_email_digest() -> None:
    """Daily Zero-Trust status digest email for admins (executive summary)."""
    job_id = "zero_trust_daily_email_digest"
    try:
        from routes.autonomous_engine import run_zero_trust_daily_status_email

        result = await run_zero_trust_daily_status_email(triggered_by="scheduler", force=False)
        status = str(result.get("status") or "unknown")
        sent = int(result.get("sent_count") or 0)
        failed = int(result.get("failed_count") or 0)
        pending = int(((result.get("snapshot") or {}).get("pending_approvals") or 0)) if isinstance(result, dict) else 0

        if status in {"sent", "partial"}:
            heartbeat_status = "healthy" if failed == 0 else "warning"
        elif status in {"skipped_window", "skipped_already_sent", "skipped_disabled"}:
            heartbeat_status = "skipped"
        elif status in {"skipped_no_recipients", "skipped_email_not_configured"}:
            heartbeat_status = "warning"
        else:
            heartbeat_status = "warning"

        await _record_scheduler_heartbeat(
            job_id,
            heartbeat_status,
            f"status={status} sent={sent} failed={failed} pending={pending}",
        )
        logger.info(
            "Zero-trust daily email digest: status=%s sent=%s failed=%s pending=%s",
            status,
            sent,
            failed,
            pending,
        )
    except Exception as exc:
        logger.error(f"scheduled_zero_trust_daily_email_digest failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


# ── GTEC C5 / Safe-Auto runbook monitor ──────────────────────────────────


async def scheduled_security_incident_runbook_monitor() -> Dict[str, Any]:
    """Continuous Safe Auto monitoring cycle every 3 hours for Go-Live runbook (GTEC C5)."""
    job_id = "security_incident_runbook_monitor"
    try:
        from routes.security_key_rotation import run_security_runbook_monitor_cycle

        result = await run_security_runbook_monitor_cycle(
            trigger_source="scheduler",
            force=False,
            include_attestation_override=None,
        )
        status = str(result.get("status") or "ok")
        if status == "ok":
            rag = str(result.get("rag") or "AMBER")
            await _record_scheduler_heartbeat(job_id, "healthy", f"status=ok rag={rag}")
        elif status == "skipped":
            await _record_scheduler_heartbeat(
                job_id,
                "healthy",
                f"status=skipped reason={result.get('reason')}",
            )
        else:
            await _record_scheduler_heartbeat(job_id, "degraded", f"status={status}")
        return result
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "degraded", f"error={str(exc)[:220]}")
        return {"status": "error", "error": str(exc)[:220]}


__all__ = [
    "scheduled_release_intelligence_monitor",
    "scheduled_production_security_policy_gate",
    "scheduled_zero_trust_auto_mitigation",
    "scheduled_zero_trust_daily_email_digest",
    "scheduled_security_incident_runbook_monitor",
]
