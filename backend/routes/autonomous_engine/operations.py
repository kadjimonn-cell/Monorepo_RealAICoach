"""Drift detection, tiers, controlled scaling, continuous cycle, architecture, content marketing."""
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from routes.autonomous_engine._shared import (
    router, _db, _require_admin, _get_engine_config, _save_engine_config,
    GATE_NAMES, MANDATORY_GATES,
    DEFAULT_DRIFT_POLICY,
)

from services.autonomous.controlled_scaling import (
    CONTROLLED_SCALING_SUBSYSTEMS,
    check_subsystem_statuses as _check_subsystem_statuses,
    enforce_controlled_scaling as _enforce_controlled_scaling_rules,
)
from services.autonomous.continuous_cycle import (
    DEFAULT_CONTINUOUS_POLICY,
    run_continuous_cycle_core,
)
from services.autonomous.tiering import (
    DEFAULT_MODULE_REGISTRY,
    TIER_NAMES,
    TIER_POLICIES,
    build_tier_validation_checks,
    group_registry_by_tier,
    tier_policy_summary,
)
from services.architecture_mode import load_modules_manifest, validate_architecture_mode_assets
from routes.autonomous_engine.core_pipeline import (
    _build_drift_status_summary, _calculate_architecture_compliance_score,
    _get_baseline_state, _save_baseline_state, _run_tests_gate,
    _trim_architecture_compliance_history, run_drift_detection, run_full_pipeline,
)
from routes.autonomous_engine.memory_predictive import (
    _auto_log_failure, _lookup_similar_failures,
)
from routes.autonomous_engine.monitoring import run_feedback_loop_analysis

class DriftPolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    baseline_mode: Optional[str] = None
    rolling_pass_window: Optional[int] = None
    performance_drift_pct: Optional[float] = None
    tests_passed_drop_pct: Optional[float] = None
    recent_pass_rate_floor_pct: Optional[float] = None
    auto_optimize: Optional[bool] = None
    revalidate_after_optimize: Optional[bool] = None
    max_history: Optional[int] = None


class DuplicationDriftAcknowledgePayload(BaseModel):
    note: Optional[str] = ""


_DUPLICATION_DRIFT_THRESHOLDS = {
    "low_pct": 2.0,
    "medium_pct": 5.0,
    "high_pct": 10.0,
}

_DUPLICATION_DRIFT_DATASETS = [
    {
        "id": "careers_applications",
        "label": "Careers Applications",
        "collection": "careers_applications",
        "id_field": "application_id",
        "timestamp_field": "created_at",
        "scan_limit": 600,
        "exact_fields": ["email", "role_slug", "name", "cover_letter"],
        "near_fields": ["email", "role_slug", "name"],
    },
    {
        "id": "id_checker_messages",
        "label": "ID Checker Messages",
        "collection": "id_checker_messages",
        "id_field": "message_id",
        "timestamp_field": "created_at",
        "scan_limit": 800,
        "exact_fields": ["thread_user_id", "sender_user_id", "message"],
        "near_fields": ["thread_user_id", "sender_user_id", "message"],
    },
    {
        "id": "security_incidents",
        "label": "Security Incidents",
        "collection": "security_incidents",
        "id_field": "ts",
        "timestamp_field": "ts",
        "scan_limit": 1000,
        "exact_fields": ["status", "code", "path", "ip"],
        "near_fields": ["status", "code", "path"],
    },
    {
        "id": "notifications",
        "label": "User Notifications",
        "collection": "notifications",
        "id_field": "notification_id",
        "timestamp_field": "created_at",
        "scan_limit": 1200,
        "exact_fields": ["user_id", "type", "title", "body"],
        "near_fields": ["user_id", "type", "title"],
    },
]


def _duplication_severity_from_rate(rate_pct: float) -> str:
    if rate_pct > 20:
        return "critical"
    if rate_pct > _DUPLICATION_DRIFT_THRESHOLDS["high_pct"]:
        return "high"
    if rate_pct > _DUPLICATION_DRIFT_THRESHOLDS["medium_pct"]:
        return "medium"
    if rate_pct > _DUPLICATION_DRIFT_THRESHOLDS["low_pct"]:
        return "low"
    return "none"


def _normalize_duplication_value(value: Any, *, loose: bool) -> str:
    if value is None:
        normalized = ""
    elif isinstance(value, (dict, list)):
        normalized = json.dumps(value, sort_keys=True, ensure_ascii=False)
    else:
        normalized = str(value)

    normalized = " ".join(normalized.strip().lower().split())
    if loose:
        normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
        normalized = " ".join(normalized.split())
        return normalized[:120]
    return normalized[:400]


def _build_duplication_key(doc: Dict[str, Any], fields: list[str], *, loose: bool) -> str:
    return " | ".join(
        f"{field}:{_normalize_duplication_value(doc.get(field), loose=loose)}"
        for field in fields
    )


def _safe_id(doc: Dict[str, Any], id_field: str) -> str:
    value = doc.get(id_field)
    if value:
        return str(value)
    for fallback in ("application_id", "message_id", "notification_id", "user_id", "ts"):
        if doc.get(fallback):
            return str(doc.get(fallback))
    return "record_unknown"


async def _scan_dataset_duplication(db, dataset: Dict[str, Any]) -> Dict[str, Any]:
    projection = {"_id": 0}
    for field in set(
        [dataset["id_field"], dataset.get("timestamp_field", "")]
        + dataset.get("exact_fields", [])
        + dataset.get("near_fields", [])
    ):
        if field:
            projection[field] = 1

    cursor = db[dataset["collection"]].find({}, projection)
    timestamp_field = dataset.get("timestamp_field")
    if timestamp_field:
        cursor = cursor.sort(timestamp_field, -1)

    scan_limit = int(dataset.get("scan_limit", 500))
    docs = await cursor.limit(scan_limit).to_list(scan_limit)
    total = len(docs)
    if total == 0:
        return {
            "dataset": dataset["id"],
            "label": dataset["label"],
            "collection": dataset["collection"],
            "scanned": 0,
            "exact_duplicates": 0,
            "near_duplicates": 0,
            "duplicate_rate_pct": 0.0,
            "severity": "none",
            "sample_impacted": [],
        }

    exact_groups: Dict[str, list[str]] = {}
    near_groups: Dict[str, list[str]] = {}
    for doc in docs:
        rec_id = _safe_id(doc, dataset["id_field"])
        exact_key = _build_duplication_key(doc, dataset.get("exact_fields", []), loose=False)
        near_key = _build_duplication_key(doc, dataset.get("near_fields", []), loose=True)
        exact_groups.setdefault(exact_key, []).append(rec_id)
        near_groups.setdefault(near_key, []).append(rec_id)

    exact_duplicates = sum(len(v) - 1 for v in exact_groups.values() if len(v) > 1)
    near_duplicates_raw = sum(len(v) - 1 for v in near_groups.values() if len(v) > 1)
    near_duplicates = max(near_duplicates_raw - exact_duplicates, 0)
    combined = exact_duplicates + near_duplicates
    duplicate_rate_pct = round((combined / total) * 100, 2) if total else 0.0

    impacted = []
    for mode, groups in (("exact", exact_groups), ("near", near_groups)):
        sorted_groups = sorted(
            ((fingerprint, ids) for fingerprint, ids in groups.items() if len(ids) > 1),
            key=lambda item: len(item[1]),
            reverse=True,
        )
        for fingerprint, ids in sorted_groups[:3]:
            impacted.append(
                {
                    "mode": mode,
                    "dataset": dataset["id"],
                    "label": dataset["label"],
                    "occurrences": len(ids),
                    "sample_ids": ids[:3],
                    "fingerprint": fingerprint[:200],
                }
            )

    return {
        "dataset": dataset["id"],
        "label": dataset["label"],
        "collection": dataset["collection"],
        "scanned": total,
        "exact_duplicates": exact_duplicates,
        "near_duplicates": near_duplicates,
        "duplicate_rate_pct": duplicate_rate_pct,
        "severity": _duplication_severity_from_rate(duplicate_rate_pct),
        "sample_impacted": impacted[:6],
    }


@router.get("/drift/status")
async def get_drift_detection_status(request: Request):
    """Get current drift detection status, policy, baseline, and latest result."""
    await _require_admin(request)
    config = await _get_engine_config()
    summary = await _build_drift_status_summary(config)
    return {
        "mode": "DRIFT_DETECTION",
        **summary,
    }


@router.post("/drift/run")
async def trigger_drift_detection(request: Request):
    """Run drift detection now: detect degradation, auto-optimize, and re-validate."""
    await _require_admin(request)
    return await run_drift_detection(triggered_by="admin_manual", auto_optimize=True)


@router.get("/drift/history")
async def get_drift_detection_history(request: Request, limit: int = Query(default=30, ge=1, le=200)):
    """Get recent drift detection events."""
    await _require_admin(request)
    db = await _db()
    events = await db.autonomous_engine_drift_history.find(
        {}, {"_id": 0}
    ).sort("checked_at", -1).limit(limit).to_list(limit)
    statuses = [str(event.get("status") or "UNKNOWN") for event in events]
    return {
        "events": events,
        "returned": len(events),
        "status_breakdown": {
            "STABLE": statuses.count("STABLE"),
            "DETECTED": statuses.count("DETECTED"),
            "RESTORED": statuses.count("RESTORED"),
            "DISABLED": statuses.count("DISABLED"),
        },
    }


@router.post("/drift/policy")
async def update_drift_detection_policy(request: Request, body: DriftPolicyUpdate):
    """Update drift detection thresholds and automation behavior."""
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("drift_detection_policy", {**DEFAULT_DRIFT_POLICY})

    if body.enabled is not None:
        policy["enabled"] = body.enabled
    if body.baseline_mode is not None:
        baseline_mode = str(body.baseline_mode).lower().strip()
        if baseline_mode not in {"locked", "rolling", "dual"}:
            raise HTTPException(status_code=400, detail="baseline_mode must be one of: locked, rolling, dual")
        policy["baseline_mode"] = baseline_mode
    if body.rolling_pass_window is not None:
        policy["rolling_pass_window"] = max(3, min(20, int(body.rolling_pass_window)))
    if body.performance_drift_pct is not None:
        policy["performance_drift_pct"] = max(1.0, float(body.performance_drift_pct))
    if body.tests_passed_drop_pct is not None:
        policy["tests_passed_drop_pct"] = max(1.0, float(body.tests_passed_drop_pct))
    if body.recent_pass_rate_floor_pct is not None:
        policy["recent_pass_rate_floor_pct"] = max(1.0, min(100.0, float(body.recent_pass_rate_floor_pct)))
    if body.auto_optimize is not None:
        policy["auto_optimize"] = body.auto_optimize
    if body.revalidate_after_optimize is not None:
        policy["revalidate_after_optimize"] = body.revalidate_after_optimize
    if body.max_history is not None:
        policy["max_history"] = max(50, min(1000, int(body.max_history)))

    config["drift_detection_policy"] = policy
    await _save_engine_config(config)
    return {"updated": True, "drift_detection_policy": config.get("drift_detection_policy")}


@router.get("/duplication-drift/status")
async def get_duplication_drift_status(request: Request):
    """Compute duplicate/near-duplicate drift across core Operations Console datasets."""
    await _require_admin(request)
    db = await _db()

    dataset_results: list[Dict[str, Any]] = []
    impacted_records: list[Dict[str, Any]] = []
    scanned_total = 0
    exact_total = 0
    near_total = 0

    for dataset in _DUPLICATION_DRIFT_DATASETS:
        result = await _scan_dataset_duplication(db, dataset)
        dataset_results.append(result)
        scanned_total += int(result.get("scanned", 0) or 0)
        exact_total += int(result.get("exact_duplicates", 0) or 0)
        near_total += int(result.get("near_duplicates", 0) or 0)
        impacted_records.extend(result.get("sample_impacted", []))

    combined_total = exact_total + near_total
    combined_rate = round((combined_total / scanned_total) * 100, 2) if scanned_total else 0.0
    impacted_records = sorted(impacted_records, key=lambda row: int(row.get("occurrences", 0)), reverse=True)[:24]

    latest_ack = await db.duplication_drift_ack.find({}, {"_id": 0}).sort("acknowledged_at", -1).limit(1).to_list(1)

    return {
        "scope": "full_operations_console",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": dict(_DUPLICATION_DRIFT_THRESHOLDS),
        "overall": {
            "datasets_covered": len(_DUPLICATION_DRIFT_DATASETS),
            "total_records_scanned": scanned_total,
            "exact_duplicate_records": exact_total,
            "near_duplicate_records": near_total,
            "combined_duplicate_records": combined_total,
            "combined_drift_rate_pct": combined_rate,
            "severity": _duplication_severity_from_rate(combined_rate),
            "requires_attention": combined_rate > _DUPLICATION_DRIFT_THRESHOLDS["low_pct"],
        },
        "datasets": dataset_results,
        "impacted_records": impacted_records,
        "last_acknowledged": latest_ack[0] if latest_ack else None,
    }


@router.post("/duplication-drift/acknowledge")
async def acknowledge_duplication_drift(request: Request, body: DuplicationDriftAcknowledgePayload):
    """Acknowledge current duplication drift findings from Operations Console."""
    user = await _require_admin(request)
    db = await _db()

    payload = {
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "acknowledged_by": getattr(user, "email", None) or getattr(user, "user_id", None) or "admin",
        "note": str(body.note or "").strip()[:240],
    }
    await db.duplication_drift_ack.insert_one({**payload})
    return {"acknowledged": True, "record": payload}


# ═══════════════════════════════════════════════════════════
# PLATFORM SYSTEM TIERS (ENTERPRISE STRUCTURE)
# ═══════════════════════════════════════════════════════════

@router.get("/tiers/registry")
async def get_tier_registry(request: Request):
    """View all modules and their assigned tiers."""
    await _require_admin(request)
    config = await _get_engine_config()
    registry = config.get("module_tier_registry", {**DEFAULT_MODULE_REGISTRY})
    by_tier = group_registry_by_tier(registry)

    return {
        "registry": registry,
        "by_tier": by_tier,
        "tier_counts": {t: len(modules) for t, modules in by_tier.items()},
        "total_modules": len(registry),
        "tier_names": TIER_NAMES,
    }


class TierAssignPayload(BaseModel):
    module: str
    tier: str


@router.post("/tiers/assign")
async def assign_module_tier(request: Request, body: TierAssignPayload):
    """Assign or move a module to a tier."""
    await _require_admin(request)

    if body.tier not in TIER_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid tier '{body.tier}'. Must be one of: {TIER_NAMES}")

    db = await _db()
    config = await _get_engine_config()
    registry = config.get("module_tier_registry", {**DEFAULT_MODULE_REGISTRY})

    previous_tier = registry.get(body.module)
    registry[body.module] = body.tier
    config["module_tier_registry"] = registry
    await _save_engine_config(config)

    # Audit trail
    await db.tier_assignment_audit.insert_one({
        "module": body.module,
        "previous_tier": previous_tier,
        "new_tier": body.tier,
        "assigned_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "assigned": True,
        "module": body.module,
        "tier": body.tier,
        "previous_tier": previous_tier,
        "tier_policy": TIER_POLICIES.get(body.tier, {}),
    }


@router.get("/tiers/policy")
async def get_tier_policies(request: Request):
    """View tier enforcement policies for all tiers."""
    await _require_admin(request)

    return {
        "tiers": TIER_POLICIES,
        "tier_names": TIER_NAMES,
        "summary": tier_policy_summary(),
    }


class TierValidatePayload(BaseModel):
    module: str
    proposed_change: Optional[str] = ""


@router.post("/tiers/validate")
async def validate_tier_change(request: Request, body: TierValidatePayload):
    """Check if a change is allowed for a given module based on its tier policy."""
    await _require_admin(request)
    config = await _get_engine_config()
    registry = config.get("module_tier_registry", {**DEFAULT_MODULE_REGISTRY})

    tier = registry.get(body.module, "experimental")
    policy = TIER_POLICIES.get(tier, TIER_POLICIES["experimental"])
    issues = []
    baseline = await _get_baseline_state()

    # Check failure memory for this module
    similar_failures = await _lookup_similar_failures(
        component=body.module, limit=3
    )
    checks = build_tier_validation_checks(policy, baseline, similar_failures)

    if policy["require_admin_approval"]:
        issues.append("Admin approval required for Core tier changes")
    if policy["require_baseline_lock"]:
        if not checks.get("baseline_locked", False):
            issues.append("Core tier requires baseline to be locked before changes")
        if checks.get("baseline_status") != "PASS":
            issues.append(f"Core tier requires baseline status PASS (current: {checks.get('baseline_status')})")

    allowed = len([i for i in issues if "required" in i.lower() and "approval" not in i.lower()]) == 0

    return {
        "module": body.module,
        "tier": tier,
        "tier_label": policy["label"],
        "proposed_change": body.proposed_change or "(not specified)",
        "allowed": allowed,
        "issues": issues,
        "checks": checks,
        "policy": policy,
    }


# ═══════════════════════════════════════════════════════════
# CONTROLLED SCALING MODE (MASTER ENFORCEMENT)
# ═══════════════════════════════════════════════════════════

async def _enforce_controlled_scaling():
    """Enforce all subsystems are active when controlled scaling is ON. Re-enable any disabled subsystem."""
    db = await _db()
    config = await _get_engine_config()
    baseline = await _get_baseline_state()
    enforcement = _enforce_controlled_scaling_rules(config, baseline, set(MANDATORY_GATES))
    corrections = enforcement.get("corrections", [])

    if enforcement.get("baseline_changed"):
        baseline_payload = {**(enforcement.get("baseline") or {}), "locked_at": datetime.now(timezone.utc).isoformat()}
        await _save_baseline_state(baseline_payload)

    if enforcement.get("gates_changed"):
        MANDATORY_GATES.update(enforcement.get("mandatory_gates") or set())

    if enforcement.get("config_changed"):
        await _save_engine_config(enforcement.get("config") or config)

    if corrections:
        await db.controlled_scaling_audit.insert_one(
            {
                "action": "enforce",
                "enforced_at": datetime.now(timezone.utc).isoformat(),
                "corrections": corrections,
            }
        )

    return corrections


@router.get("/controlled-scaling/status")
async def get_controlled_scaling_status(request: Request):
    """Get current Controlled Scaling Mode state and all subsystem statuses."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    cs = config.get("controlled_scaling", {"active": False})

    baseline = await _get_baseline_state()
    subsystems = _check_subsystem_statuses(config, baseline, set(MANDATORY_GATES))
    all_enforced = all(s.get("enforced") for s in subsystems.values())

    # If active, run enforcement check
    corrections = []
    if cs.get("active"):
        corrections = await _enforce_controlled_scaling() or []

    # Recent audit
    recent_audit = await db.controlled_scaling_audit.find(
        {}, {"_id": 0}
    ).sort("enforced_at", -1).limit(10).to_list(10)

    return {
        "mode": "CONTROLLED_SCALING",
        "active": cs.get("active", False),
        "activated_at": cs.get("activated_at"),
        "activated_by": cs.get("activated_by"),
        "all_subsystems_enforced": all_enforced,
        "subsystem_count": len(CONTROLLED_SCALING_SUBSYSTEMS),
        "subsystems": subsystems,
        "corrections_applied": corrections,
        "fail_state_reachable": not all_enforced,
        "recent_audit": recent_audit,
    }


class ControlledScalingPayload(BaseModel):
    activate: bool


@router.post("/controlled-scaling/activate")
async def activate_controlled_scaling(request: Request, body: ControlledScalingPayload):
    """Activate or deactivate Controlled Scaling Mode — the master enforcement switch."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    now_iso = datetime.now(timezone.utc).isoformat()

    if body.activate:
        # ── ACTIVATE: Lock everything down ──

        # 1. Lock baseline
        baseline = await _get_baseline_state()
        if not baseline.get("locked"):
            baseline["locked"] = True
            baseline["locked_at"] = now_iso
            await _save_baseline_state(baseline)

        # 2. Ensure all mandatory gates
        MANDATORY_GATES.add("tests")
        MANDATORY_GATES.add("coverage")

        # 3. Enable monitor auto-heal
        mp = config.get("monitor_policy", {})
        mp["auto_heal_on_anomaly"] = True
        mp["alert_admin_on_anomaly"] = True
        config["monitor_policy"] = mp

        # 4. Enable canary auto-rollback
        cp = config.get("canary_policy", {})
        cp["auto_rollback"] = True
        config["canary_policy"] = cp

        # 5. Enable coverage fail guards
        cvp = config.get("coverage_policy", {})
        cvp["fail_on_drop"] = True
        cvp["fail_on_missing_tests"] = True
        config["coverage_policy"] = cvp

        # 6. Tighten deployment gate
        dp = config.get("deployment_policy", {})
        dp["max_error_rate_pct"] = min(dp.get("max_error_rate_pct", 5), 5)
        config["deployment_policy"] = dp

        # 7. Set controlled scaling state
        config["controlled_scaling"] = {
            "active": True,
            "activated_at": now_iso,
            "activated_by": "admin",
        }
        await _save_engine_config(config)

        # Audit
        await db.controlled_scaling_audit.insert_one({
            "action": "activate",
            "enforced_at": now_iso,
            "corrections": [
                "baseline_lock: locked",
                "mandatory_gates: tests + coverage enforced",
                "monitor: auto_heal + alert enabled",
                "canary: auto_rollback enabled",
                "coverage: fail_on_drop + fail_on_missing_tests enabled",
                "deployment: max_error_rate capped at 5%",
            ],
        })

        baseline_now = await _get_baseline_state()
        subsystems = _check_subsystem_statuses(config, baseline_now, set(MANDATORY_GATES))

        return {
            "mode": "CONTROLLED_SCALING",
            "active": True,
            "activated_at": now_iso,
            "message": "Controlled Scaling Mode ACTIVATED. All protection systems enforced. FAIL state is now unreachable.",
            "subsystems_enforced": {k: v.get("enforced") for k, v in subsystems.items()},
            "all_enforced": all(v.get("enforced") for v in subsystems.values()),
        }

    else:
        # ── DEACTIVATE ──
        config["controlled_scaling"] = {
            "active": False,
            "deactivated_at": now_iso,
        }
        await _save_engine_config(config)

        await db.controlled_scaling_audit.insert_one({
            "action": "deactivate",
            "enforced_at": now_iso,
            "corrections": [],
        })

        return {
            "mode": "CONTROLLED_SCALING",
            "active": False,
            "deactivated_at": now_iso,
            "message": "Controlled Scaling Mode DEACTIVATED. Subsystems remain in current state but are no longer enforced.",
        }


# ═══════════════════════════════════════════════════════════
# CONTINUOUS AUTONOMOUS EXECUTION (24/7 MODE)
# ═══════════════════════════════════════════════════════════


async def run_continuous_cycle(triggered_by: str = "scheduler") -> dict:
    """Execute one full continuous autonomous cycle: health check, latency, tests, perf, auto-heal."""
    db = await _db()
    config = await _get_engine_config()
    release_monitor_fn = None
    try:
        from routes.security_engine import run_release_intelligence_monitor as _run_release_intelligence_monitor
        release_monitor_fn = _run_release_intelligence_monitor
    except Exception:
        release_monitor_fn = None

    return await run_continuous_cycle_core(
        db=db,
        config=config,
        triggered_by=triggered_by,
        run_tests_gate=_run_tests_gate,
        run_drift_detection=run_drift_detection,
        run_feedback_loop_analysis=run_feedback_loop_analysis,
        get_engine_config=_get_engine_config,
        run_full_pipeline=run_full_pipeline,
        run_release_intelligence_monitor=release_monitor_fn,
        auto_log_failure=_auto_log_failure,
    )


@router.get("/continuous/status")
async def get_continuous_status(request: Request):
    """Get current 24/7 continuous autonomous execution state."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("continuous_policy", DEFAULT_CONTINUOUS_POLICY)
    cs = config.get("continuous_mode", {"enabled": False})

    latest = await db.continuous_cycle_history.find_one({}, {"_id": 0}, sort=[("executed_at", -1)])
    total_cycles = await db.continuous_cycle_history.count_documents({})
    pass_cycles = await db.continuous_cycle_history.count_documents({"status": "PASS"})
    healed_cycles = await db.continuous_cycle_history.count_documents({"status": "HEALED"})
    fail_cycles = await db.continuous_cycle_history.count_documents({"status": "FAIL"})

    return {
        "mode": "CONTINUOUS_AUTONOMOUS_24_7",
        "enabled": cs.get("enabled", False),
        "enabled_at": cs.get("enabled_at"),
        "interval_minutes": policy.get("interval_minutes", 30),
        "policy": policy,
        "forever_loop": {
            "enabled": bool(policy.get("forever_loop_enabled", True)),
            "definition": ["Monitor", "Detect", "Fix", "Test", "Validate", "Optimize", "Deploy", "Learn", "Repeat"],
            "latest": (latest or {}).get("forever_loop"),
        },
        "latest_cycle": latest,
        "stats": {
            "total_cycles": total_cycles,
            "pass": pass_cycles,
            "healed": healed_cycles,
            "fail": fail_cycles,
            "uptime_pct": round(((pass_cycles + healed_cycles) / max(total_cycles, 1)) * 100, 1),
        },
    }


class ContinuousTogglePayload(BaseModel):
    enabled: bool
    interval_minutes: Optional[int] = None


@router.post("/continuous/toggle")
async def toggle_continuous_mode(request: Request, body: ContinuousTogglePayload):
    """Enable or disable 24/7 continuous autonomous execution."""
    await _require_admin(request)
    config = await _get_engine_config()
    now_iso = datetime.now(timezone.utc).isoformat()

    if body.interval_minutes is not None:
        policy = config.get("continuous_policy", {**DEFAULT_CONTINUOUS_POLICY})
        policy["interval_minutes"] = max(5, min(1440, body.interval_minutes))
        config["continuous_policy"] = policy

    config["continuous_mode"] = {
        "enabled": body.enabled,
        "enabled_at": now_iso if body.enabled else None,
        "disabled_at": now_iso if not body.enabled else None,
    }
    await _save_engine_config(config)

    return {
        "mode": "CONTINUOUS_AUTONOMOUS_24_7",
        "enabled": body.enabled,
        "timestamp": now_iso,
        "interval_minutes": config.get("continuous_policy", {}).get("interval_minutes", 30),
        "message": f"24/7 Mode {'ENABLED — system will self-monitor and auto-heal continuously' if body.enabled else 'DISABLED'}",
    }


@router.post("/continuous/run-now")
async def run_continuous_now(request: Request):
    """Run one immediate forever-loop cycle."""
    await _require_admin(request)
    cycle = await run_continuous_cycle(triggered_by="manual_forever_loop")
    return {
        "triggered": True,
        "cycle": cycle,
    }


@router.get("/continuous/history")
async def get_continuous_history(request: Request, limit: int = Query(default=30, ge=1, le=200)):
    """Get cycle execution history for continuous autonomous mode."""
    await _require_admin(request)
    db = await _db()

    cycles = await db.continuous_cycle_history.find(
        {}, {"_id": 0}
    ).sort("executed_at", -1).limit(limit).to_list(limit)

    statuses = [c.get("status") for c in cycles]

    return {
        "cycles": cycles,
        "returned": len(cycles),
        "status_breakdown": {
            "PASS": statuses.count("PASS"),
            "HEALED": statuses.count("HEALED"),
            "FAIL": statuses.count("FAIL"),
        },
    }


@router.get("/continuous/forever-loop")
async def get_forever_loop_state(request: Request, limit: int = Query(default=10, ge=1, le=100)):
    """Get explicit forever-loop execution state and latest stage outcomes."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("continuous_policy", DEFAULT_CONTINUOUS_POLICY)

    rows = await db.continuous_cycle_history.find(
        {}, {"_id": 0, "cycle_id": 1, "executed_at": 1, "status": 1, "anomaly_count": 1, "forever_loop": 1}
    ).sort("executed_at", -1).limit(limit).to_list(limit)
    latest = rows[0] if rows else None

    return {
        "enabled": bool(policy.get("forever_loop_enabled", True)),
        "definition": ["Monitor", "Detect", "Fix", "Test", "Validate", "Optimize", "Deploy", "Learn", "Repeat"],
        "latest": latest,
        "history": rows,
        "returned": len(rows),
    }


@router.get("/architecture/compliance-dashboard")
async def get_architecture_compliance_dashboard(request: Request, limit: int = Query(default=12, ge=3, le=50)):
    """Live architecture compliance score + gate history for Executive Command Center."""
    await _require_admin(request)
    db = await _db()

    validation = validate_architecture_mode_assets()
    score = _calculate_architecture_compliance_score(validation)
    checked_at = datetime.now(timezone.utc).isoformat()

    snapshot = {
        "checked_at": checked_at,
        "architecture_status": validation.get("overall_status", "FAIL"),
        "architecture_compliance_score": score,
        "summary": validation.get("summary") or {},
        "gateway_path_mapping": validation.get("gateway_path_mapping") or {},
    }
    await db.architecture_compliance_history.insert_one({**snapshot})
    await _trim_architecture_compliance_history(200)

    run_docs = await db.autonomous_engine_runs.find(
        {},
        {"_id": 0, "run_id": 1, "timestamp": 1, "status": 1, "gates": 1, "final_output": 1},
    ).sort("timestamp", -1).limit(limit).to_list(limit)

    gate_history = []
    for run in run_docs:
        gates = run.get("gates") or {}
        final_output = run.get("final_output") or {}
        gate_map = {}
        pass_count = 0
        for gate_name in GATE_NAMES:
            gate_status = str((gates.get(gate_name) or {}).get("status") or final_output.get(gate_name.upper()) or "UNKNOWN").upper()
            if gate_status == "PASS":
                pass_count += 1
            gate_map[gate_name] = gate_status
        gate_history.append({
            "run_id": run.get("run_id"),
            "timestamp": run.get("timestamp"),
            "overall_status": str(run.get("status") or "UNKNOWN").upper(),
            "pass_count": pass_count,
            "total_gates": len(GATE_NAMES),
            "gates": gate_map,
        })

    architecture_history = await db.architecture_compliance_history.find(
        {},
        {"_id": 0},
    ).sort("checked_at", -1).limit(limit).to_list(limit)

    return {
        "checked_at": checked_at,
        "architecture_status": validation.get("overall_status", "FAIL"),
        "architecture_compliance_score": score,
        "summary": validation.get("summary") or {},
        "gateway_path_mapping": validation.get("gateway_path_mapping") or {},
        "modules": validation.get("modules") or [],
        "gate_history": gate_history,
        "history": architecture_history,
        "limit": limit,
    }


@router.post("/content-marketing/weekly/run")
async def run_autonomous_weekly_content_marketing(
    request: Request,
    subscriber_limit: int = Query(default=25, ge=0, le=5000),
):
    actor = await _require_admin(request)
    from services.autonomous_content_automation import run_weekly_autonomous_content_cycle

    db = await _db()
    resolved_limit: Optional[int] = subscriber_limit
    if subscriber_limit >= 5000:
        resolved_limit = None

    return await run_weekly_autonomous_content_cycle(
        db,
        triggered_by=str(getattr(actor, "email", "admin")),
        subscriber_limit=resolved_limit,
    )


async def _build_autonomous_weekly_content_marketing_payload(db, latest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    recent_runs = await db.autonomous_content_runs.find({}, {"_id": 0}).sort("created_at", -1).limit(8).to_list(8)
    latest_run = latest or (recent_runs[0] if recent_runs else None)

    summary = {
        "total_runs": int(await db.autonomous_content_runs.count_documents({})),
        "completed_runs": int(await db.autonomous_content_runs.count_documents({"status": "completed"})),
        "completed_with_failures_runs": int(await db.autonomous_content_runs.count_documents({"status": "completed_with_failures"})),
        "failed_runs": int(await db.autonomous_content_runs.count_documents({"status": "failed"})),
        "skipped_runs": int(await db.autonomous_content_runs.count_documents({"status": "skipped"})),
    }

    latest_successful_run = await db.autonomous_content_runs.find_one(
        {"status": {"$in": ["completed", "completed_with_failures"]}},
        {"_id": 0},
        sort=[("created_at", -1)],
    )

    def _normalize_run(run: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not run:
            return None
        return {
            "run_id": run.get("run_id"),
            "week_key": run.get("week_key"),
            "status": run.get("status"),
            "triggered_by": run.get("triggered_by"),
            "topic": run.get("topic"),
            "quality_score": run.get("quality_score"),
            "quality_issues": run.get("quality_issues") or [],
            "blog_slug": run.get("blog_slug"),
            "newsletter_digest_id": run.get("newsletter_digest_id"),
            "newsletter_sent": int(run.get("newsletter_sent") or 0),
            "newsletter_failed": int(run.get("newsletter_failed") or 0),
            "newsletter_skipped_existing": int(run.get("newsletter_skipped_existing") or 0),
            "subscribers_total": int(run.get("subscribers_total") or 0),
            "digest_status": run.get("digest_status"),
            "reason": run.get("reason"),
            "existing_run_id": run.get("existing_run_id"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
        }

    latest_payload = _normalize_run(latest_run)
    latest_digest = None
    if latest_payload and latest_payload.get("newsletter_digest_id"):
        latest_digest = await db.newsletter_digests.find_one(
            {"digest_id": latest_payload.get("newsletter_digest_id")},
            {"_id": 0},
        )

    return {
        **(latest_payload or {
            "run_id": None,
            "week_key": None,
            "status": "NOT_RUN",
            "triggered_by": None,
            "topic": None,
            "quality_score": 0,
            "quality_issues": [],
            "blog_slug": None,
            "newsletter_digest_id": None,
            "newsletter_sent": 0,
            "newsletter_failed": 0,
            "newsletter_skipped_existing": 0,
            "subscribers_total": 0,
            "digest_status": None,
            "reason": None,
            "existing_run_id": None,
            "created_at": None,
            "updated_at": None,
        }),
        "digest": latest_digest,
        "summary": summary,
        "latest_successful_run": _normalize_run(latest_successful_run),
        "recent_runs": [_normalize_run(run) for run in recent_runs],
    }


@router.get("/content-marketing/weekly/status")
async def get_autonomous_weekly_content_marketing_status(request: Request):
    await _require_admin(request)
    db = await _db()

    latest = await db.autonomous_content_runs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    return await _build_autonomous_weekly_content_marketing_payload(db, latest=latest)


@router.get("/architecture/modules")
async def get_architecture_modules(request: Request):
    """Architecture mode module boundaries and deployment contracts."""
    await _require_admin(request)
    return load_modules_manifest()


@router.get("/architecture/validate")
async def validate_architecture_mode(request: Request):
    """Validate architecture mode compliance: contracts + deployment specs + independent tests."""
    await _require_admin(request)
    return validate_architecture_mode_assets()



# ─── Theme Drift Tickets Triage ───

