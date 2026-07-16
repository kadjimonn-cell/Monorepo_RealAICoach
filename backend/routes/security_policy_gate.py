from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from routes.db import db, require_admin
from utils.production_security_policy_gate import collect_policy_gate_signals


router = APIRouter(prefix="/admin/security/policy-gate", tags=["Enterprise Security"])


@router.get("/status")
async def policy_gate_status(request: Request):
    await require_admin(request)

    signal_snapshot = await collect_policy_gate_signals(db_ref=db)
    runtime_state = await db.system_runtime_flags.find_one(
        {"key": "production_security_policy_gate_state"},
        {"_id": 0},
    ) or {}
    latest_run = await db.production_security_policy_gate_runs.find_one(
        {},
        {"_id": 0},
        sort=[("ran_at", -1)],
    ) or {}

    day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    blocked_24h = await db.production_security_policy_audit_logs.count_documents(
        {
            "allowed": False,
            "evaluated_at": {"$gte": day_ago},
        }
    )
    allowed_24h = await db.production_security_policy_audit_logs.count_documents(
        {
            "allowed": True,
            "evaluated_at": {"$gte": day_ago},
        }
    )

    return {
        "status": "pass" if signal_snapshot.get("passed") else "fail",
        "signal_snapshot": signal_snapshot,
        "runtime_state": runtime_state,
        "latest_run": latest_run,
        "audit_window_24h": {
            "allowed": allowed_24h,
            "blocked": blocked_24h,
        },
    }


@router.get("/runs")
async def policy_gate_runs(request: Request, limit: int = 20):
    await require_admin(request)
    safe_limit = max(1, min(limit, 100))
    runs = await db.production_security_policy_gate_runs.find(
        {},
        {"_id": 0},
    ).sort("ran_at", -1).limit(safe_limit).to_list(safe_limit)
    return {
        "runs": runs,
        "count": len(runs),
    }


@router.get("/audit")
async def policy_gate_audit(request: Request, limit: int = 50):
    await require_admin(request)
    safe_limit = max(1, min(limit, 200))
    records = await db.production_security_policy_audit_logs.find(
        {},
        {"_id": 0},
    ).sort("evaluated_at", -1).limit(safe_limit).to_list(safe_limit)
    return {
        "records": records,
        "count": len(records),
    }


@router.post("/recover-prerequisites")
async def policy_gate_recover_prerequisites(request: Request):
    """One-click recovery action to re-run prerequisite checks and attempt safe unblocking."""
    await require_admin(request)

    before = await collect_policy_gate_signals(db_ref=db)
    actions: list[dict] = []

    try:
        from routes.auth import _resolve_sso_redirect_base, run_sso_e2e_validation_internal

        active_base = await _resolve_sso_redirect_base(request, force_sync=True)
        validation = await run_sso_e2e_validation_internal(request)
        validation_state = "pass" if validation.get("passed") else "fail"
        await db.system_runtime_flags.update_one(
            {"key": "sso_e2e_validation_state"},
            {
                "$set": {
                    "key": "sso_e2e_validation_state",
                    "state": validation_state,
                    "last_run_at": validation.get("validated_at"),
                    "failed_checks": [
                        item.get("name") for item in (validation.get("checks") or []) if not item.get("passed")
                    ],
                    "active_base": active_base,
                }
            },
            upsert=True,
        )
        actions.append(
            {
                "action": "sso_redirect_sync_and_validation",
                "ok": True,
                "state": validation_state,
                "active_base": active_base,
            }
        )
    except Exception as exc:
        actions.append(
            {
                "action": "sso_redirect_sync_and_validation",
                "ok": False,
                "error": str(exc),
            }
        )

    try:
        from scheduler_jobs import scheduled_admin_e2e_health_gate

        await scheduled_admin_e2e_health_gate()
        actions.append({"action": "admin_e2e_health_gate_rerun", "ok": True})
    except Exception as exc:
        actions.append({"action": "admin_e2e_health_gate_rerun", "ok": False, "error": str(exc)})

    try:
        from scheduler_jobs import scheduled_subscription_plan_guardrail

        await scheduled_subscription_plan_guardrail()
        actions.append({"action": "subscription_plan_guardrail_rerun", "ok": True})
    except Exception as exc:
        actions.append({"action": "subscription_plan_guardrail_rerun", "ok": False, "error": str(exc)})

    try:
        from routes.cia_trust import cia_self_heal_heartbeat

        cia_result = await cia_self_heal_heartbeat(request)
        actions.append(
            {
                "action": "cia_self_heal_heartbeat",
                "ok": True,
                "trust_score": (cia_result.get("overview") or {}).get("trust_score"),
            }
        )
    except Exception as exc:
        actions.append({"action": "cia_self_heal_heartbeat", "ok": False, "error": str(exc)})

    try:
        from scheduler_jobs import scheduled_production_security_policy_gate

        await scheduled_production_security_policy_gate()
        actions.append({"action": "policy_gate_state_refresh", "ok": True})
    except Exception as exc:
        actions.append({"action": "policy_gate_state_refresh", "ok": False, "error": str(exc)})

    after = await collect_policy_gate_signals(db_ref=db)
    recovery_success = bool(after.get("passed"))

    await db.production_security_policy_recovery_runs.insert_one(
        {
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "before": before,
            "after": after,
            "actions": actions,
            "recovery_success": recovery_success,
        }
    )

    return {
        "ok": True,
        "recovery_success": recovery_success,
        "before": before,
        "after": after,
        "actions": actions,
    }