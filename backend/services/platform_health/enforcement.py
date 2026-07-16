"""Enforcement/runbook orchestration helpers for platform health routes."""

from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Optional


async def collect_enforcement_rule_health(
    *,
    db,
    normalize_policy: Callable[[Optional[Dict[str, Any]]], Dict[str, Any]],
    policy_flag_key: str,
) -> Dict[str, Any]:
    """Build health snapshot for permanent enforcement rules and cadence gates."""
    enforcement = await db.enterprise_enforcement_rules.find_one(
        {"rule_id": "enterprise_permanent_enforcement"},
        {"_id": 0},
    ) or {}
    perf = await db.performance_optimization_rules.find_one(
        {"rule_id": "global_enterprise_perf"},
        {"_id": 0},
    ) or {}
    tabs = await db.admin_tabs_audit_history.find_one({}, {"_id": 0}, sort=[("run_at", -1)]) or {}
    reg_gate = await db.platform_regression_gate_history.find_one({}, {"_id": 0}, sort=[("run_at", -1)]) or {}
    growth = await db.growth_integrity_monitor_history.find_one({}, {"_id": 0}, sort=[("run_at", -1)]) or {}
    slo_policy_flag = await db.system_runtime_flags.find_one({"key": policy_flag_key}, {"_id": 0}) or {}
    slo_policy = normalize_policy((slo_policy_flag.get("value") or {}) if isinstance(slo_policy_flag.get("value"), dict) else {})

    enforcement_ok = bool(enforcement.get("enabled") and enforcement.get("safe_auto_fix_required"))
    perf_ok = bool(perf.get("lazy_loading") and perf.get("response_caching") and perf.get("asset_compression"))
    tabs_ok = bool(tabs.get("is_unique", True))
    gate_ok = bool(reg_gate.get("gate_passed", True))
    growth_ok = str(growth.get("status", "healthy")) == "healthy"
    slo_ok = bool(enforcement.get("slo_auto_mitigation_required", True) and bool(slo_policy.get("enabled")))

    checks = [enforcement_ok, perf_ok, tabs_ok, gate_ok, growth_ok, slo_ok]
    health_score = int(round((sum(1 for c in checks if c) / max(len(checks), 1)) * 100))

    return {
        "health_score": health_score,
        "status": "healthy" if all(checks) else "warning",
        "enforcement_rules": {
            "enabled": bool(enforcement.get("enabled")),
            "safe_auto_fix_required": bool(enforcement.get("safe_auto_fix_required")),
            "regression_gate_required": bool(enforcement.get("regression_gate_required")),
            "growth_monitor_required": bool(enforcement.get("growth_monitor_required")),
            "admin_tabs_uniqueness_required": bool(enforcement.get("admin_tabs_uniqueness_required")),
            "performance_policy_required": bool(enforcement.get("performance_policy_required")),
            "slo_auto_mitigation_required": bool(enforcement.get("slo_auto_mitigation_required", True)),
            "updated_at": enforcement.get("updated_at"),
        },
        "performance_policy": {
            "lazy_loading": bool(perf.get("lazy_loading")),
            "response_caching": bool(perf.get("response_caching")),
            "asset_compression": bool(perf.get("asset_compression")),
            "db_query_guardrails": bool(perf.get("db_query_guardrails")),
            "api_retry_policy": bool(perf.get("api_retry_policy")),
            "updated_at": perf.get("updated_at"),
        },
        "latest_admin_tabs_audit": {
            "run_at": tabs.get("run_at"),
            "is_unique": bool(tabs.get("is_unique", True)),
            "duplicate_count": len(tabs.get("duplicate_keys", {}) or {}),
        },
        "latest_regression_gate": {
            "run_at": reg_gate.get("run_at"),
            "gate_passed": bool(reg_gate.get("gate_passed", True)),
            "score": reg_gate.get("score", 100),
            "total_issues": reg_gate.get("total_issues", 0),
        },
        "latest_growth_monitor": {
            "run_at": growth.get("run_at"),
            "status": growth.get("status", "healthy"),
            "high_risk_alerts": growth.get("high_risk_alerts", 0),
            "payment_severity": growth.get("payment_severity", "unknown"),
            "payment_pass_rate": growth.get("payment_pass_rate", 0),
        },
        "slo_auto_mitigation": {
            "enabled": bool(slo_policy.get("enabled")),
            "p95_latency_threshold_ms": int(slo_policy.get("p95_latency_threshold_ms") or 0),
            "cooldown_minutes": int(slo_policy.get("cooldown_minutes") or 0),
            "check_interval_seconds": int(slo_policy.get("check_interval_seconds") or 0),
            "status": "healthy" if slo_ok else "warning",
        },
    }


async def create_remediation_rollback_checkpoint(
    *,
    db,
    rollback_policies: Dict[str, Dict[str, Any]],
    user: Any,
    trigger: str,
    severity_band: str,
    score: int,
    issues: int,
    source_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist rollback checkpoint snapshots tied to severity bands."""
    policy = rollback_policies.get(severity_band, rollback_policies["medium"])
    checkpoint_id = f"rollback_{int(datetime.now(timezone.utc).timestamp())}_{severity_band}"

    enforcement_snapshot = await db.enterprise_enforcement_rules.find_one(
        {"rule_id": "enterprise_permanent_enforcement"},
        {"_id": 0},
    ) or {}
    perf_snapshot = await db.performance_optimization_rules.find_one(
        {"rule_id": "global_enterprise_perf"},
        {"_id": 0},
    ) or {}
    latest_scan = await db.platform_health_scans.find_one({}, {"_id": 0}, sort=[("_stored_at", -1)]) or {}

    checkpoint = {
        "checkpoint_id": checkpoint_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": getattr(user, "email", None) or "system",
        "trigger": trigger,
        "severity_band": severity_band,
        "severity_policy": policy,
        "score": score,
        "issues": issues,
        "source_run_id": source_run_id,
        "restore_ready": bool(enforcement_snapshot or perf_snapshot),
        "snapshots": {
            "enterprise_enforcement_rules": enforcement_snapshot,
            "performance_optimization_rules": perf_snapshot,
            "platform_health_scan_summary": {
                "score": latest_scan.get("score"),
                "grade": latest_scan.get("grade"),
                "total_issues": latest_scan.get("total_issues"),
                "scanned_at": latest_scan.get("scanned_at"),
            },
        },
    }

    await db.enterprise_rollback_checkpoints.insert_one({**checkpoint})

    cutoff = datetime.now(timezone.utc) - timedelta(hours=policy["retention_hours"])
    await db.enterprise_rollback_checkpoints.delete_many({"created_at": {"$lt": cutoff.isoformat()}})

    keep = int(policy["max_checkpoints"])
    checkpoints = await db.enterprise_rollback_checkpoints.find({}, {"_id": 1}).sort("created_at", -1).to_list(keep + 200)
    if len(checkpoints) > keep:
        old_ids = [doc["_id"] for doc in checkpoints[keep:]]
        if old_ids:
            await db.enterprise_rollback_checkpoints.delete_many({"_id": {"$in": old_ids}})

    return {
        "checkpoint_id": checkpoint_id,
        "created_at": checkpoint["created_at"],
        "severity_band": severity_band,
        "policy": policy,
        "restore_ready": checkpoint["restore_ready"],
    }


def build_pipeline_stage_status(
    *,
    latest_scan: Dict[str, Any],
    final_score: int,
    final_issues: int,
    enforcement_health: Dict[str, Any],
    checkpoint_id: str,
) -> list[Dict[str, Any]]:
    now_iso = datetime.now(timezone.utc).isoformat()
    detect_ok = bool(latest_scan)
    diagnose_ok = bool((latest_scan.get("total_issues", 0) or 0) >= 0)
    repair_ok = final_score >= 90
    optimize_ok = bool(enforcement_health.get("performance_policy", {}).get("lazy_loading"))
    validate_ok = final_score >= 95 and final_issues == 0
    lock_ok = bool(enforcement_health.get("enforcement_rules", {}).get("enabled"))

    stages = [
        {"id": "detect", "label": "Detect", "status": "healthy" if detect_ok else "warning", "detail": "Platform scan complete"},
        {"id": "diagnose", "label": "Diagnose", "status": "healthy" if diagnose_ok else "warning", "detail": f"Issues observed: {latest_scan.get('total_issues', 0)}"},
        {"id": "repair", "label": "Repair", "status": "healthy" if repair_ok else "warning", "detail": f"Post-fix score: {final_score}"},
        {"id": "optimize", "label": "Optimize", "status": "healthy" if optimize_ok else "warning", "detail": "Performance policy guardrails active"},
        {"id": "validate", "label": "Validate", "status": "healthy" if validate_ok else "warning", "detail": f"Final issues: {final_issues}"},
        {"id": "lock", "label": "Lock", "status": "healthy" if lock_ok else "warning", "detail": f"Rollback checkpoint: {checkpoint_id}"},
    ]

    return [{**stage, "updated_at": now_iso} for stage in stages]