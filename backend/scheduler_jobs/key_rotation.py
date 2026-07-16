# ruff: noqa
"""scheduler_jobs.key_rotation — Cryptographic key rotation governance jobs.

**Phase 2 batch #14.**

Jobs: policy attestation, game-day staleness guard, compliance bundle
autogen, status drift monitor. All function bodies are byte-identical
to the originals in `_legacy.py`.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from scheduler_jobs.observability import _record_scheduler_heartbeat

logger = logging.getLogger("scheduler_jobs.key_rotation")


async def scheduled_key_rotation_policy_attestation() -> Dict[str, Any]:
    """Periodic key-rotation policy attestation with webhook validation snapshot."""
    job_id = "key_rotation_policy_attestation"
    try:
        from routes.db import db
        from routes.security_key_rotation import _rotation_policy_snapshot, _validate_siem_incident_webhook_delivery
        from utils.production_security_policy_gate import collect_policy_gate_signals

        policy = _rotation_policy_snapshot()
        signals = await collect_policy_gate_signals(db_ref=db, allow_rotation_window_override=False)
        webhook_validation = await _validate_siem_incident_webhook_delivery(
            actor_user_id="scheduler",
            context="scheduled_policy_attestation",
            related_run_id=None,
        )
        game_day_snapshot = await db.system_runtime_flags.find_one(
            {"key": "key_rotation_last_game_day"},
            {"_id": 0},
        ) or {}

        attestation_doc = {
            "attestation_id": f"keyrot_att_{uuid.uuid4().hex[:12]}",
            "attested_at": datetime.now(timezone.utc).isoformat(),
            "attested_by": "scheduler",
            "source": "scheduled_policy_attestation",
            "note": "Automated periodic attestation",
            "policy": policy,
            "policy_gate_snapshot": signals,
            "prerequisite_refresh": {"actions": [{"action": "scheduled_snapshot", "ok": True}]},
            "webhook_validation": webhook_validation,
            "game_day_snapshot": game_day_snapshot,
        }
        await db.security_key_rotation_policy_attestations.insert_one(attestation_doc)

        await _record_scheduler_heartbeat(
            job_id,
            "healthy",
            (
                f"gate_passed={bool(signals.get('passed'))} "
                f"webhook_validated={bool((webhook_validation or {}).get('validated'))}"
            ),
        )
        return {
            "status": "ok",
            "attestation_id": attestation_doc["attestation_id"],
            "policy_gate_passed": bool(signals.get("passed")),
            "webhook_validated": bool((webhook_validation or {}).get("validated")),
        }
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "degraded", f"error={str(exc)[:220]}")
        return {"status": "error", "error": str(exc)[:220]}


async def scheduled_key_rotation_game_day_staleness_guard() -> Dict[str, Any]:
    """Raise alert if game-day attestation is stale beyond policy interval."""
    job_id = "key_rotation_game_day_staleness_guard"
    try:
        from routes.db import db

        now = datetime.now(timezone.utc)
        interval_days = max(1, int(str(os.environ.get("KEY_ROTATION_GAME_DAY_INTERVAL_DAYS") or "90")))
        game_day_snapshot = await db.system_runtime_flags.find_one(
            {"key": "key_rotation_last_game_day"},
            {"_id": 0},
        ) or {}

        recorded_at_raw = str(game_day_snapshot.get("recorded_at") or "").strip()
        stale_days = None
        is_stale = False
        if recorded_at_raw:
            try:
                recorded_at = datetime.fromisoformat(recorded_at_raw.replace("Z", "+00:00"))
                if recorded_at.tzinfo is None:
                    recorded_at = recorded_at.replace(tzinfo=timezone.utc)
                stale_days = (now - recorded_at.astimezone(timezone.utc)).days
                is_stale = stale_days > interval_days
            except Exception:
                is_stale = True
        else:
            is_stale = True

        alert_emitted = False
        if is_stale:
            dedupe_key = f"key_rotation_game_day_stale_{now.date().isoformat()}"
            existing = await db.siem_triggered_alerts.find_one({"dedupe_key": dedupe_key}, {"_id": 0, "alert_id": 1})
            if not existing:
                await db.siem_triggered_alerts.insert_one(
                    {
                        "alert_id": f"alert_keyrot_{uuid.uuid4().hex[:12]}",
                        "dedupe_key": dedupe_key,
                        "rule_id": "key_rotation_game_day_staleness",
                        "rule_name": "Key Rotation Game-Day Staleness",
                        "event_type": "key_rotation_game_day_staleness",
                        "severity": "high",
                        "status": "active",
                        "triggered_at": now.isoformat(),
                        "message": (
                            "Key-rotation game-day evidence is stale beyond policy interval"
                            if stale_days is not None
                            else "Key-rotation game-day evidence is missing"
                        ),
                        "stale_days": stale_days,
                        "interval_days": interval_days,
                    }
                )
                alert_emitted = True

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if not is_stale else "degraded",
            f"is_stale={is_stale} stale_days={stale_days} interval_days={interval_days} alert_emitted={alert_emitted}",
        )
        return {
            "status": "ok",
            "is_stale": is_stale,
            "stale_days": stale_days,
            "interval_days": interval_days,
            "alert_emitted": alert_emitted,
        }
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "degraded", f"error={str(exc)[:220]}")
        return {"status": "error", "error": str(exc)[:220]}


async def scheduled_key_rotation_compliance_bundle_autogen() -> Dict[str, Any]:
    """Auto-generate compact compliance bundles for recent runs."""
    job_id = "key_rotation_compliance_bundle_autogen"
    try:
        from routes.db import db

        now = datetime.now(timezone.utc)
        runs = await db.security_key_rotation_runs.find({}, {"_id": 0}).sort("started_at", -1).limit(10).to_list(10)
        created = 0
        skipped = 0

        for run in runs:
            run_id = str(run.get("run_id") or "")
            if not run_id:
                continue
            exists = await db.security_key_rotation_compliance_bundles.find_one(
                {"run.run_id": run_id},
                {"_id": 0, "bundle_id": 1},
            )
            if exists:
                skipped += 1
                continue

            plan_id = str(run.get("plan_id") or "")
            plan = await db.security_key_rotation_plans.find_one({"plan_id": plan_id}, {"_id": 0}) or {}
            steps_count = await db.security_key_rotation_steps.count_documents({"run_id": run_id})
            evidence_count = await db.security_key_rotation_evidence.count_documents({"run_id": run_id})
            incidents_count = await db.security_incidents.count_documents({"run_id": run_id})
            rollbacks_count = await db.security_key_rotation_rollbacks.count_documents({"run_id": run_id})
            siem_count = await db.siem_triggered_alerts.count_documents({"rotation_run_id": run_id})

            summary = run.get("summary") or {}
            markdown_lines = [
                "# Key Rotation Compliance Bundle (Scheduled)",
                "",
                f"- Generated At: {now.isoformat()}",
                f"- Run ID: {run_id}",
                f"- Plan ID: {plan_id}",
                f"- Status: {run.get('status')}",
                "",
                "## Summary",
                f"- Providers Total: {summary.get('providers_total')}",
                f"- Credential Validated: {summary.get('credential_validated')}",
                f"- Cutover Applied: {summary.get('cutover_applied')}",
                f"- Provider Revoked: {summary.get('provider_revoked', 0)}",
                f"- Manual Pending: {summary.get('manual_pending_evidence')}",
                f"- Manual Verified: {summary.get('manual_applied_verified')}",
                "",
                "## Counts",
                f"- Steps: {steps_count}",
                f"- Evidence Docs: {evidence_count}",
                f"- Incidents: {incidents_count}",
                f"- Rollbacks: {rollbacks_count}",
                f"- SIEM Alerts: {siem_count}",
            ]

            await db.security_key_rotation_compliance_bundles.insert_one(
                {
                    "bundle_id": f"keyrot_bundle_{uuid.uuid4().hex[:12]}",
                    "generated_at": now.isoformat(),
                    "source": "scheduled_autogen",
                    "run": run,
                    "plan": {
                        "plan_id": plan.get("plan_id"),
                        "status": plan.get("status"),
                        "approved_at": plan.get("approved_at"),
                        "approved_by": plan.get("approved_by"),
                    },
                    "summary": {
                        "steps": steps_count,
                        "evidence": evidence_count,
                        "incidents": incidents_count,
                        "rollbacks": rollbacks_count,
                        "siem_alerts": siem_count,
                    },
                    "markdown": "\n".join(markdown_lines),
                }
            )
            created += 1

        await _record_scheduler_heartbeat(job_id, "healthy", f"created={created} skipped={skipped}")
        return {"status": "ok", "created": created, "skipped": skipped}
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "degraded", f"error={str(exc)[:220]}")
        return {"status": "error", "error": str(exc)[:220]}


async def scheduled_key_rotation_status_drift_monitor() -> Dict[str, Any]:
    """Monitor contract/readiness drift and emit alerts for unresolved rotate blockers."""
    job_id = "key_rotation_status_drift_monitor"
    try:
        from routes.db import db
        from routes.security_key_rotation import (
            _build_readiness_map,
            PROVIDER_DEFINITIONS,
            APPLY_CONTRACT_API_ROTATE,
            READINESS_STATUS_API_ROTATE_READY,
            READINESS_STATUS_ADAPTER_MISSING,
        )

        readiness_map = _build_readiness_map()
        providers = [readiness_map[item["provider_id"]] for item in PROVIDER_DEFINITIONS]
        rotate_contract_rows = [
            p for p in providers if str(p.get("apply_contract_mode") or "") == APPLY_CONTRACT_API_ROTATE
        ]
        rotate_ready_count = len([
            p for p in rotate_contract_rows if str((p.get("apply_capability") or {}).get("status") or "") == READINESS_STATUS_API_ROTATE_READY
        ])
        rotate_adapter_missing = [
            p for p in rotate_contract_rows if str((p.get("apply_capability") or {}).get("status") or "") == READINESS_STATUS_ADAPTER_MISSING
        ]

        issues: List[Dict[str, Any]] = []
        if rotate_contract_rows and rotate_ready_count == 0:
            issues.append(
                {
                    "code": "rotate_contracts_not_ready",
                    "message": "Rotate contracts are configured but none are live-ready.",
                    "rotate_contract_count": len(rotate_contract_rows),
                }
            )
        if rotate_adapter_missing:
            issues.append(
                {
                    "code": "rotate_adapter_missing",
                    "message": "One or more rotate-contract providers are missing adapter requirements.",
                    "provider_ids": [p.get("provider_id") for p in rotate_adapter_missing],
                }
            )

        report_doc = {
            "report_id": f"keyrot_drift_{uuid.uuid4().hex[:12]}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rotate_contract_count": len(rotate_contract_rows),
            "rotate_ready_count": rotate_ready_count,
            "issues": issues,
        }
        await db.security_key_rotation_status_drift_reports.insert_one(report_doc)

        alert_emitted = False
        if issues:
            dedupe_key = f"key_rotation_status_drift_{datetime.now(timezone.utc).date().isoformat()}"
            existing = await db.siem_triggered_alerts.find_one({"dedupe_key": dedupe_key}, {"_id": 0, "alert_id": 1})
            if not existing:
                await db.siem_triggered_alerts.insert_one(
                    {
                        "alert_id": f"alert_keyrot_{uuid.uuid4().hex[:12]}",
                        "dedupe_key": dedupe_key,
                        "rule_id": "key_rotation_status_drift",
                        "rule_name": "Key Rotation Status Drift",
                        "event_type": "key_rotation_status_drift",
                        "severity": "medium",
                        "status": "active",
                        "triggered_at": datetime.now(timezone.utc).isoformat(),
                        "message": "Key-rotation contract/readiness drift detected",
                        "issues": issues,
                    }
                )
                alert_emitted = True

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if not issues else "degraded",
            f"issues={len(issues)} rotate_contract_count={len(rotate_contract_rows)} rotate_ready_count={rotate_ready_count} alert_emitted={alert_emitted}",
        )
        return {
            "status": "ok",
            "issues": issues,
            "rotate_contract_count": len(rotate_contract_rows),
            "rotate_ready_count": rotate_ready_count,
            "alert_emitted": alert_emitted,
        }
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "degraded", f"error={str(exc)[:220]}")
        return {"status": "error", "error": str(exc)[:220]}


__all__ = [
    "scheduled_key_rotation_policy_attestation",
    "scheduled_key_rotation_game_day_staleness_guard",
    "scheduled_key_rotation_compliance_bundle_autogen",
    "scheduled_key_rotation_status_drift_monitor",
]
