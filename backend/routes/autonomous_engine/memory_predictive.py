"""System memory, failure memory, predictive failure prevention, feature builds, perf audit."""
import asyncio
import hashlib
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from routes.autonomous_engine._shared import (
    router, _db, _require_admin, _get_engine_config, _save_engine_config,
    GATE_NAMES, DEFAULT_PREDICTIVE_POLICY,
    DEFAULT_SYSTEM_MEMORY_POLICY,
)

from services.autonomous.common import (
    parse_iso_datetime as _parse_iso_datetime,
)
from services.autonomous.predictive import build_prediction_candidates
from services.autonomous.audit_reports import build_perf_trends_payload
from routes.autonomous_engine.core_pipeline import (
    _build_gate_lock_state, _get_baseline_state, _lookup_system_memory,
    _run_deployment_gate, _run_tests_gate, _run_validation_gate,
    _store_system_memory, run_drift_detection, run_full_pipeline,
)

class PredictivePolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    analyze_window_hours: Optional[int] = None
    min_pattern_occurrences: Optional[int] = None
    confidence_threshold: Optional[int] = None
    auto_preemptive_fix: Optional[bool] = None
    run_validation_after_fix: Optional[bool] = None
    scheduler_enabled: Optional[bool] = None
    scheduled_interval_minutes: Optional[int] = None
    max_history: Optional[int] = None
    signal_sources: Optional[Dict[str, bool]] = None


class MemoryStorePayload(BaseModel):
    memory_type: str
    signature: str
    problem_summary: str
    solution_summary: str
    source: Optional[str] = "manual"
    tags: Optional[List[str]] = []
    confidence_score: Optional[float] = 0.7
    evidence: Optional[Dict[str, Any]] = {}


class MemoryQueryPayload(BaseModel):
    task_type: str
    signature: str
    categories: Optional[List[str]] = None
    top_k: Optional[int] = None
    context: Optional[Dict[str, Any]] = {}


class SystemMemoryPolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    require_lookup_before_task: Optional[bool] = None
    lookup_top_k: Optional[int] = None
    min_confidence_score: Optional[float] = None
    auto_capture_failures: Optional[bool] = None
    auto_capture_fixes: Optional[bool] = None
    auto_capture_optimizations: Optional[bool] = None
    auto_capture_test_patterns: Optional[bool] = None
    max_memory_entries: Optional[int] = None


@router.get("/memory/policy")
async def get_system_memory_policy(request: Request):
    await _require_admin(request)
    config = await _get_engine_config()
    return {"system_memory_policy": config.get("system_memory_policy", {**DEFAULT_SYSTEM_MEMORY_POLICY})}


@router.post("/memory/policy")
async def update_system_memory_policy(request: Request, body: SystemMemoryPolicyUpdate):
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("system_memory_policy", {**DEFAULT_SYSTEM_MEMORY_POLICY})
    payload = body.model_dump(exclude_none=True)
    for key, value in payload.items():
        if key in {"lookup_top_k", "max_memory_entries"}:
            policy[key] = max(1, int(value))
        elif key == "min_confidence_score":
            policy[key] = max(0.0, min(1.0, float(value)))
        else:
            policy[key] = bool(value)
    config["system_memory_policy"] = policy
    await _save_engine_config(config)
    return {"updated": True, "system_memory_policy": (await _get_engine_config()).get("system_memory_policy")}


@router.post("/memory/store")
async def store_system_memory(request: Request, body: MemoryStorePayload):
    await _require_admin(request)
    memory_type = str(body.memory_type or "").strip().lower()
    if memory_type not in {"failure", "fix", "optimization", "test_pattern"}:
        raise HTTPException(status_code=400, detail="memory_type must be one of: failure, fix, optimization, test_pattern")
    result = await _store_system_memory(
        memory_type=memory_type,
        signature=body.signature,
        problem_summary=body.problem_summary,
        solution_summary=body.solution_summary,
        source=body.source or "manual",
        tags=body.tags or [],
        confidence_score=float(body.confidence_score or 0.7),
        evidence=body.evidence or {},
    )
    return result


@router.post("/memory/query")
async def query_system_memory(request: Request, body: MemoryQueryPayload):
    await _require_admin(request)
    return await _lookup_system_memory(
        task_type=body.task_type,
        signature=body.signature,
        context=body.context or {},
        categories=body.categories,
        top_k=body.top_k,
    )


@router.get("/memory/library")
async def get_system_memory_library(request: Request, memory_type: Optional[str] = None, limit: int = Query(default=50, ge=1, le=200)):
    await _require_admin(request)
    db = await _db()
    query: Dict[str, Any] = {}
    if memory_type:
        query["memory_type"] = str(memory_type).strip().lower()
    rows = await db.system_knowledge_memory.find(query, {"_id": 0}).sort(
        [("updated_at", -1), ("confidence_score", -1), ("reuse_count", -1)]
    ).limit(limit).to_list(limit)
    return {"items": rows, "returned": len(rows)}


@router.get("/memory/dashboard")
async def get_system_memory_dashboard(request: Request):
    await _require_admin(request)
    db = await _db()
    policy = (await _get_engine_config()).get("system_memory_policy", {**DEFAULT_SYSTEM_MEMORY_POLICY})
    total = await db.system_knowledge_memory.count_documents({})
    by_type = {
        "failure": await db.system_knowledge_memory.count_documents({"memory_type": "failure"}),
        "fix": await db.system_knowledge_memory.count_documents({"memory_type": "fix"}),
        "optimization": await db.system_knowledge_memory.count_documents({"memory_type": "optimization"}),
        "test_pattern": await db.system_knowledge_memory.count_documents({"memory_type": "test_pattern"}),
    }
    top_reused = await db.system_knowledge_memory.find({}, {"_id": 0}).sort(
        [("reuse_count", -1), ("confidence_score", -1), ("updated_at", -1)]
    ).limit(10).to_list(10)
    latest_lookups = await db.system_memory_lookups.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    return {
        "policy": policy,
        "stats": {
            "total": total,
            "by_type": by_type,
        },
        "top_reused": top_reused,
        "latest_lookups": latest_lookups,
    }


# ═══════════════════════════════════════════════════════════
# PREDICTIVE FAILURE PREVENTION MODE
# ═══════════════════════════════════════════════════════════

async def _build_predictive_status_summary(config: Optional[dict] = None) -> dict:
    db = await _db()
    cfg = config or await _get_engine_config()
    policy = cfg.get("predictive_policy", {**DEFAULT_PREDICTIVE_POLICY})
    latest_run = await db.predictive_failure_runs.find_one({}, {"_id": 0}, sort=[("predicted_at", -1)])
    total_runs = await db.predictive_failure_runs.count_documents({})
    high_risk = await db.predictive_failure_runs.count_documents({"high_risk_count": {"$gt": 0}})
    preemptive_executed = await db.predictive_failure_runs.count_documents({"preemptive.executed": True})
    validated_pass = await db.predictive_failure_runs.count_documents({"validation.status": "PASS"})
    return {
        "enabled": bool(policy.get("enabled", True)),
        "policy": policy,
        "latest_run": latest_run,
        "stats": {
            "total_runs": total_runs,
            "high_risk_runs": high_risk,
            "preemptive_executed_runs": preemptive_executed,
            "validated_pass_runs": validated_pass,
        },
    }


async def _build_darkmode_regression_scan_summary() -> dict:
    db = await _db()
    latest_scan = await db.email_darkmode_regression_scans.find_one({}, {"_id": 0}, sort=[("scanned_at", -1)])
    open_tickets = await db.email_darkmode_regression_tickets.count_documents({"status": {"$in": ["open", "in_progress"]}})
    latest_ticket = await db.email_darkmode_regression_tickets.find_one(
        {"status": {"$in": ["open", "in_progress"]}},
        {"_id": 0, "ticket_id": 1, "template_key": 1, "updated_at": 1, "latest_issues": 1, "occurrence_count": 1},
        sort=[("updated_at", -1)],
    )
    status = "NOT_RUN"
    if latest_scan:
        status = "PASS" if str(latest_scan.get("status") or "").upper() == "PASS" else "FAIL"

    return {
        "status": status,
        "latest_scan": latest_scan,
        "latest_failures": (latest_scan or {}).get("failures", [])[:5],
        "open_tickets": open_tickets,
        "latest_open_ticket": latest_ticket,
    }


async def _collect_predictive_signal_profile(policy: dict) -> dict:
    db = await _db()
    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(hours=int(policy.get("analyze_window_hours", 72)))
    since_iso = since_dt.isoformat()
    signal_sources = policy.get("signal_sources", {}) or {}

    profile = {
        "lookback_start": since_iso,
        "lookback_end": now.isoformat(),
        "failure_type_counts": {},
        "component_counts": {},
        "drift_signal_counts": {},
        "monitor_anomaly_counts": {},
        "feedback_issue_counts": {},
        "pipeline_fail_rate_pct": 0.0,
        "monitor_alert_rate_pct": 0.0,
        "feedback_friction_rate_pct": 0.0,
        "unresolved_failures": 0,
        "sample_sizes": {},
    }

    if signal_sources.get("failure_memory", True):
        failures = await db.failure_memory.find(
            {"logged_at": {"$gte": since_iso}},
            {"_id": 0, "failure_type": 1, "component": 1, "fix_confirmed": 1},
        ).limit(4000).to_list(4000)
        profile["sample_sizes"]["failure_memory"] = len(failures)
        unresolved = 0
        for item in failures:
            f_type = str(item.get("failure_type") or "unknown").strip().lower()
            component = str(item.get("component") or "unknown").strip()
            profile["failure_type_counts"][f_type] = int(profile["failure_type_counts"].get(f_type, 0) or 0) + 1
            profile["component_counts"][component] = int(profile["component_counts"].get(component, 0) or 0) + 1
            if not bool(item.get("fix_confirmed")):
                unresolved += 1
        profile["unresolved_failures"] = unresolved

    if signal_sources.get("drift_history", True):
        drift_events = await db.autonomous_engine_drift_history.find(
            {"checked_at": {"$gte": since_iso}},
            {"_id": 0, "signals": 1, "status": 1},
        ).limit(2000).to_list(2000)
        profile["sample_sizes"]["drift_history"] = len(drift_events)
        for event in drift_events:
            for signal in event.get("signals", []) or []:
                signal_type = str((signal or {}).get("type") or "unknown").strip().lower()
                profile["drift_signal_counts"][signal_type] = int(profile["drift_signal_counts"].get(signal_type, 0) or 0) + 1

    if signal_sources.get("monitor_anomalies", True):
        anomalies = await db.monitor_anomalies.find(
            {"detected_at": {"$gte": since_iso}},
            {"_id": 0, "type": 1},
        ).limit(3000).to_list(3000)
        profile["sample_sizes"]["monitor_anomalies"] = len(anomalies)
        for item in anomalies:
            a_type = str(item.get("type") or "unknown").strip().lower()
            profile["monitor_anomaly_counts"][a_type] = int(profile["monitor_anomaly_counts"].get(a_type, 0) or 0) + 1
        if anomalies:
            alert_items = sum(1 for a in anomalies if str(a.get("type") or "").strip())
            profile["monitor_alert_rate_pct"] = round((alert_items / max(len(anomalies), 1)) * 100, 1)

    if signal_sources.get("pipeline_runs", True):
        runs = await db.autonomous_engine_runs.find(
            {"timestamp": {"$gte": since_dt}},
            {"_id": 0, "status": 1},
        ).limit(2000).to_list(2000)
        profile["sample_sizes"]["pipeline_runs"] = len(runs)
        fail_count = sum(1 for run in runs if str(run.get("status") or "").upper() != "PASS")
        profile["pipeline_fail_rate_pct"] = round((fail_count / max(len(runs), 1)) * 100, 1) if runs else 0.0

    if signal_sources.get("feedback_loop", True):
        feedback_runs = await db.feedback_loop_runs.find(
            {"analyzed_at": {"$gte": since_iso}},
            {"_id": 0, "friction_detected": 1, "event_count": 1},
        ).limit(2000).to_list(2000)
        profile["sample_sizes"]["feedback_loop_runs"] = len(feedback_runs)
        total_friction = 0
        total_events = 0
        for run in feedback_runs:
            issues = run.get("friction_detected") or []
            total_friction += len(issues)
            total_events += int(run.get("event_count") or 0)
            for issue in issues:
                issue_type = str((issue or {}).get("issue_type") or "unknown").strip().lower()
                profile["feedback_issue_counts"][issue_type] = int(profile["feedback_issue_counts"].get(issue_type, 0) or 0) + 1
        profile["feedback_friction_rate_pct"] = round((total_friction / max(total_events, 1)) * 100, 1) if total_events > 0 else 0.0

    return profile


async def _execute_predictive_preemptive_action(action_key: str, triggered_by: str) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    if action_key == "optimize_drift":
        drift = await run_drift_detection(triggered_by=f"predictive:{triggered_by}", auto_optimize=True)
        return {
            "action_key": action_key,
            "executed": True,
            "success": bool(drift.get("restored") or not drift.get("detected")),
            "result": {
                "status": drift.get("status"),
                "detected": drift.get("detected"),
                "restored": drift.get("restored"),
                "signal_count": len(drift.get("signals", [])),
                "event_id": drift.get("event_id"),
            },
            "executed_at": now_iso,
        }
    if action_key == "feedback_hardening":
        from routes.autonomous_engine.monitoring import run_feedback_loop_analysis

        feedback = await run_feedback_loop_analysis(triggered_by=f"predictive:{triggered_by}")
        return {
            "action_key": action_key,
            "executed": True,
            "success": feedback.get("status") in {"CLEAR", "FRICTION_DETECTED"},
            "result": {
                "status": feedback.get("status"),
                "friction_count": len(feedback.get("friction_detected", [])),
                "generated_tasks": len(feedback.get("generated_tasks", [])),
                "run_id": feedback.get("run_id"),
            },
            "executed_at": now_iso,
        }
    if action_key == "stabilize_pipeline":
        config = await _get_engine_config()
        pipeline = await run_full_pipeline(config, triggered_by=f"predictive:{triggered_by}")
        return {
            "action_key": action_key,
            "executed": True,
            "success": str(pipeline.get("status") or "").upper() == "PASS",
            "result": {
                "status": pipeline.get("status"),
                "run_id": pipeline.get("run_id"),
                "final_output": pipeline.get("final_output", {}),
            },
            "executed_at": now_iso,
        }

    validation = await _run_validation_gate()
    return {
        "action_key": "validation_probe",
        "executed": True,
        "success": validation.get("status") == "PASS",
        "result": {
            "status": validation.get("status"),
            "issues": validation.get("issues", [])[:5],
        },
        "executed_at": now_iso,
    }


async def run_predictive_failure_prevention(triggered_by: str = "manual") -> dict:
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("predictive_policy", {**DEFAULT_PREDICTIVE_POLICY})
    now_iso = datetime.now(timezone.utc).isoformat()
    run_id = f"predictive_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    if not bool(policy.get("enabled", True)):
        return {
            "mode": "PREDICTIVE_FAILURE_PREVENTION",
            "run_id": run_id,
            "status": "DISABLED",
            "predicted_at": now_iso,
            "predictions": [],
            "high_risk_predictions": [],
            "preemptive": {"executed": False, "actions": []},
            "validation": {"ran": False},
        }

    signal_profile = await _collect_predictive_signal_profile(policy)
    min_patterns = int(policy.get("min_pattern_occurrences", 3))
    confidence_threshold = int(policy.get("confidence_threshold", 75))
    candidates = build_prediction_candidates(signal_profile, min_patterns)

    predictions = []
    for idx, candidate in enumerate(candidates):
        predictions.append(
            {
                "prediction_id": f"pred_{idx + 1}",
                **candidate,
                "rank": idx + 1,
                "threshold": confidence_threshold,
                "is_high_risk": int(candidate.get("confidence", 0)) >= confidence_threshold,
            }
        )

    high_risk = [p for p in predictions if p.get("is_high_risk")]

    actions = []
    if high_risk and bool(policy.get("auto_preemptive_fix", True)):
        for item in high_risk[:2]:
            action_key = str(item.get("recommended_action_key") or "validation_probe")
            try:
                action_result = await _execute_predictive_preemptive_action(action_key, triggered_by)
                actions.append({"prediction_id": item.get("prediction_id"), **action_result})
            except Exception as exc:
                actions.append(
                    {
                        "prediction_id": item.get("prediction_id"),
                        "action_key": action_key,
                        "executed": False,
                        "success": False,
                        "error": str(exc)[:220],
                        "executed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

    validation_result = {"ran": False}
    if actions and bool(policy.get("run_validation_after_fix", True)):
        tests = await _run_tests_gate()
        validation = await _run_validation_gate()
        is_pass = tests.get("status") == "PASS" and validation.get("status") == "PASS"
        validation_result = {
            "ran": True,
            "status": "PASS" if is_pass else "FAIL",
            "tests_status": tests.get("status"),
            "validation_status": validation.get("status"),
            "tests_issues": tests.get("issues", [])[:3],
            "validation_issues": validation.get("issues", [])[:3],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    if not predictions:
        status = "NO_PATTERN_DETECTED"
    elif high_risk and actions and validation_result.get("status") == "PASS":
        status = "PREEMPTED_AND_VALIDATED"
    elif high_risk and actions:
        status = "PREEMPTIVE_ACTION_EXECUTED"
    elif high_risk:
        status = "HIGH_RISK_PREDICTED"
    else:
        status = "LOW_RISK_MONITORING"

    run_doc = {
        "mode": "PREDICTIVE_FAILURE_PREVENTION",
        "run_id": run_id,
        "triggered_by": triggered_by,
        "predicted_at": now_iso,
        "status": status,
        "policy_snapshot": {
            "analyze_window_hours": policy.get("analyze_window_hours"),
            "min_pattern_occurrences": policy.get("min_pattern_occurrences"),
            "confidence_threshold": confidence_threshold,
            "auto_preemptive_fix": policy.get("auto_preemptive_fix"),
            "run_validation_after_fix": policy.get("run_validation_after_fix"),
            "signal_sources": policy.get("signal_sources", {}),
        },
        "signal_profile": signal_profile,
        "predictions": predictions,
        "high_risk_predictions": high_risk,
        "prediction_count": len(predictions),
        "high_risk_count": len(high_risk),
        "preemptive": {
            "executed": bool(actions),
            "actions": actions,
            "successful_actions": sum(1 for action in actions if action.get("success")),
        },
        "validation": validation_result,
    }

    await db.predictive_failure_runs.insert_one({**run_doc})

    max_history = int(policy.get("max_history", 250))
    count = await db.predictive_failure_runs.count_documents({})
    if count > max_history:
        over = count - max_history
        oldest = await db.predictive_failure_runs.find({}, {"_id": 1}).sort("predicted_at", 1).limit(over).to_list(over)
        if oldest:
            await db.predictive_failure_runs.delete_many({"_id": {"$in": [doc["_id"] for doc in oldest]}})

    return run_doc


@router.get("/predictive/status")
async def get_predictive_status(request: Request):
    await _require_admin(request)
    config = await _get_engine_config()
    return {"mode": "PREDICTIVE_FAILURE_PREVENTION", **(await _build_predictive_status_summary(config))}


@router.post("/predictive/run")
async def run_predictive_now(request: Request):
    await _require_admin(request)
    return await run_predictive_failure_prevention(triggered_by="admin_manual")


@router.get("/predictive/history")
async def get_predictive_history(request: Request, limit: int = Query(default=30, ge=1, le=200)):
    await _require_admin(request)
    db = await _db()
    runs = await db.predictive_failure_runs.find({}, {"_id": 0}).sort("predicted_at", -1).limit(limit).to_list(limit)
    statuses = [str(run.get("status") or "UNKNOWN") for run in runs]
    return {
        "runs": runs,
        "returned": len(runs),
        "status_breakdown": {
            "PREEMPTED_AND_VALIDATED": statuses.count("PREEMPTED_AND_VALIDATED"),
            "PREEMPTIVE_ACTION_EXECUTED": statuses.count("PREEMPTIVE_ACTION_EXECUTED"),
            "HIGH_RISK_PREDICTED": statuses.count("HIGH_RISK_PREDICTED"),
            "LOW_RISK_MONITORING": statuses.count("LOW_RISK_MONITORING"),
            "NO_PATTERN_DETECTED": statuses.count("NO_PATTERN_DETECTED"),
            "DISABLED": statuses.count("DISABLED"),
        },
    }


@router.post("/predictive/policy")
async def update_predictive_policy(request: Request, body: PredictivePolicyUpdate):
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("predictive_policy", {**DEFAULT_PREDICTIVE_POLICY})

    if body.enabled is not None:
        policy["enabled"] = bool(body.enabled)
    if body.analyze_window_hours is not None:
        policy["analyze_window_hours"] = max(1, min(24 * 30, int(body.analyze_window_hours)))
    if body.min_pattern_occurrences is not None:
        policy["min_pattern_occurrences"] = max(1, min(50, int(body.min_pattern_occurrences)))
    if body.confidence_threshold is not None:
        policy["confidence_threshold"] = max(1, min(99, int(body.confidence_threshold)))
    if body.auto_preemptive_fix is not None:
        policy["auto_preemptive_fix"] = bool(body.auto_preemptive_fix)
    if body.run_validation_after_fix is not None:
        policy["run_validation_after_fix"] = bool(body.run_validation_after_fix)
    if body.scheduler_enabled is not None:
        policy["scheduler_enabled"] = bool(body.scheduler_enabled)
    if body.scheduled_interval_minutes is not None:
        policy["scheduled_interval_minutes"] = max(5, min(1440, int(body.scheduled_interval_minutes)))
    if body.max_history is not None:
        policy["max_history"] = max(50, min(5000, int(body.max_history)))

    if body.signal_sources is not None:
        merged_sources = {
            **DEFAULT_PREDICTIVE_POLICY.get("signal_sources", {}),
            **(policy.get("signal_sources") or {}),
            **(body.signal_sources or {}),
        }
        policy["signal_sources"] = {
            "failure_memory": bool(merged_sources.get("failure_memory", True)),
            "drift_history": bool(merged_sources.get("drift_history", True)),
            "monitor_anomalies": bool(merged_sources.get("monitor_anomalies", True)),
            "pipeline_runs": bool(merged_sources.get("pipeline_runs", True)),
            "feedback_loop": bool(merged_sources.get("feedback_loop", True)),
        }

    config["predictive_policy"] = policy
    await _save_engine_config(config)
    return {"updated": True, "predictive_policy": (await _get_engine_config()).get("predictive_policy")}


@router.get("/darkmode-regression/status")
async def get_darkmode_regression_status(request: Request):
    await _require_admin(request)
    return await _build_darkmode_regression_scan_summary()


@router.get("/darkmode-regression/tickets")
async def list_darkmode_regression_tickets(request: Request, limit: int = Query(default=20, ge=1, le=200)):
    await _require_admin(request)
    db = await _db()
    tickets = await db.email_darkmode_regression_tickets.find({}, {"_id": 0}).sort("updated_at", -1).limit(limit).to_list(limit)
    status_values = [str(t.get("status") or "").lower() for t in tickets]
    return {
        "tickets": tickets,
        "returned": len(tickets),
        "summary": {
            "open": status_values.count("open"),
            "in_progress": status_values.count("in_progress"),
            "resolved": status_values.count("resolved"),
        },
    }


# ═══════════════════════════════════════════════════════════
# FEATURE BUILD MODE (TDD PIPELINE ENFORCEMENT)
# ═══════════════════════════════════════════════════════════

FEATURE_STEPS = [
    "tests_first",
    "implement",
    "full_pipeline",
    "performance_impact",
    "regression",
    "deploy",
]

FEATURE_STEP_LABELS = {
    "tests_first": "Write Tests First",
    "implement": "Implement Feature",
    "full_pipeline": "Run Full Pipeline",
    "performance_impact": "Validate Performance Impact",
    "regression": "Run Regression Check",
    "deploy": "Deploy (All PASS Required)",
}


class FeatureStartPayload(BaseModel):
    name: str
    description: Optional[str] = ""
    test_files: Optional[List[str]] = []
    owner: Optional[str] = ""


async def _create_feature_build_record(
    name: str,
    description: str = "",
    test_files: Optional[List[str]] = None,
    owner: str = "",
    extra_fields: Optional[dict] = None,
) -> dict:
    db = await _db()
    feature_id = f"feat_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{name[:20].replace(' ', '_').lower()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    feature = {
        "feature_id": feature_id,
        "name": name,
        "description": description or "",
        "owner": owner or "",
        "test_files": test_files or [],
        "status": "in_progress",
        "current_step": FEATURE_STEPS[0],
        "current_step_index": 0,
        "steps": {s: {"status": "pending", "result": None, "completed_at": None} for s in FEATURE_STEPS},
        "started_at": now_iso,
        "completed_at": None,
        "final_verdict": None,
        "blocked_reason": None,
    }
    if extra_fields:
        feature.update(extra_fields)
    await db.feature_builds.insert_one({**feature})
    return feature


async def _advance_feature_build_record(feature_id: str) -> dict:
    db = await _db()
    feat = await db.feature_builds.find_one({"feature_id": feature_id})
    if not feat:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")
    if feat.get("status") in ("completed", "blocked"):
        raise HTTPException(status_code=400, detail=f"Feature is already {feat['status']}")

    current_step = feat.get("current_step")
    step_idx = feat.get("current_step_index", 0)
    steps = feat.get("steps", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    memory_lookup = await _lookup_system_memory(
        task_type="feature_step_validation",
        signature=f"{feature_id}::{current_step}",
        context={"feature_id": feature_id, "current_step": current_step, "feature_name": feat.get("name")},
        categories=["test_pattern", "fix", "failure", "optimization"],
    )

    step_result = await _validate_feature_step(current_step, feat)
    steps[current_step] = {
        "status": step_result["status"],
        "result": step_result,
        "completed_at": now_iso,
    }

    if step_result["status"] == "FAIL":
        blocked_reason = f"Step '{current_step}' FAILED: {'; '.join(step_result.get('issues', []))}"
        await _store_system_memory(
            memory_type="failure",
            signature=f"feature_step:{current_step}|{'; '.join(step_result.get('issues', [])[:2])}",
            problem_summary=f"Feature step '{current_step}' failed",
            solution_summary="Reuse prior step-specific fix and rerun the same feature step before advancing.",
            source="feature_build_step",
            tags=["feature_build", current_step, "failure"],
            confidence_score=0.68,
            evidence={"feature_id": feature_id, "step_result": step_result},
        )
        asyncio.ensure_future(_auto_log_failure(
            failure_type="feature_build_blocked",
            component=current_step,
            error_signature=blocked_reason[:200],
            root_cause=blocked_reason[:300],
            context={"feature_id": feature_id, "step": current_step},
        ))
        await db.feature_builds.update_one(
            {"feature_id": feature_id},
            {"$set": {
                "steps": steps,
                "status": "blocked",
                "blocked_reason": blocked_reason,
            }},
        )
        return {
            "feature_id": feature_id,
            "action": "advance",
            "step": current_step,
            "step_label": FEATURE_STEP_LABELS.get(current_step, current_step),
            "result": "BLOCKED",
            "step_result": step_result,
            "blocked_reason": f"Step '{current_step}' FAILED",
            "memory_lookup": memory_lookup,
        }

    next_idx = step_idx + 1
    if next_idx >= len(FEATURE_STEPS):
        await db.feature_builds.update_one(
            {"feature_id": feature_id},
            {"$set": {
                "steps": steps,
                "current_step": "done",
                "current_step_index": next_idx,
                "status": "completed",
                "completed_at": now_iso,
                "final_verdict": "DEPLOYABLE",
            }},
        )
        return {
            "feature_id": feature_id,
            "action": "advance",
            "step": current_step,
            "step_label": FEATURE_STEP_LABELS.get(current_step, current_step),
            "result": "DEPLOYABLE",
            "step_result": step_result,
            "message": "All steps PASSED — feature is approved for deployment",
            "memory_lookup": memory_lookup,
        }

    next_step = FEATURE_STEPS[next_idx]
    await db.feature_builds.update_one(
        {"feature_id": feature_id},
        {"$set": {
            "steps": steps,
            "current_step": next_step,
            "current_step_index": next_idx,
        }},
    )
    return {
        "feature_id": feature_id,
        "action": "advance",
        "step_completed": current_step,
        "step_label": FEATURE_STEP_LABELS.get(current_step, current_step),
        "result": "PASS",
        "next_step": next_step,
        "next_step_label": FEATURE_STEP_LABELS.get(next_step, next_step),
        "step_result": step_result,
        "memory_lookup": memory_lookup,
        "progress": f"{next_idx}/{len(FEATURE_STEPS)}",
    }


async def _run_feature_build_automation(feature_id: str, max_steps: int = 6) -> dict:
    memory_lookup = await _lookup_system_memory(
        task_type="feature_build",
        signature=f"feature::{feature_id}",
        context={"feature_id": feature_id, "mode": "automation"},
        categories=["fix", "test_pattern", "optimization", "failure"],
    )
    latest = None
    for _ in range(max_steps):
        latest = await _advance_feature_build_record(feature_id)
        if latest.get("result") in {"BLOCKED", "DEPLOYABLE"}:
            break
    db = await _db()
    final_feature = await db.feature_builds.find_one({"feature_id": feature_id}, {"_id": 0})
    return {
        "feature_id": feature_id,
        "memory_lookup": memory_lookup,
        "latest_result": latest,
        "final_feature": final_feature,
    }


@router.post("/feature/start")
async def start_feature_build(request: Request, body: FeatureStartPayload):
    """Register a new feature build — enforces TDD pipeline from step 1."""
    await _require_admin(request)
    memory_lookup = await _lookup_system_memory(
        task_type="feature_start",
        signature=f"feature_start::{body.name}",
        context={"name": body.name, "description": body.description or "", "test_files": body.test_files or []},
        categories=["test_pattern", "fix", "optimization", "failure"],
    )
    feature = await _create_feature_build_record(
        name=body.name,
        description=(body.description or ""),
        test_files=body.test_files or [],
        owner=body.owner or "",
        extra_fields={"memory_lookup": memory_lookup},
    )
    payload = {k: v for k, v in feature.items() if k != "_id"}
    payload["memory_lookup"] = memory_lookup
    return payload


@router.get("/feature/status/{feature_id}")
async def get_feature_status(request: Request, feature_id: str):
    """Get current feature build workflow state and step results."""
    await _require_admin(request)
    db = await _db()

    feat = await db.feature_builds.find_one({"feature_id": feature_id}, {"_id": 0})
    if not feat:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    return {
        **feat,
        "step_labels": FEATURE_STEP_LABELS,
        "total_steps": len(FEATURE_STEPS),
    }


@router.get("/feature/list")
async def list_feature_builds(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    """List recent feature builds."""
    await _require_admin(request)
    db = await _db()

    features = await db.feature_builds.find(
        {}, {"_id": 0}
    ).sort("started_at", -1).limit(limit).to_list(limit)

    return {"features": features, "total": len(features)}


@router.post("/feature/advance/{feature_id}")
async def advance_feature_step(request: Request, feature_id: str):
    """Advance feature to next step — runs validation for the current step. Each step must PASS."""
    await _require_admin(request)
    return await _advance_feature_build_record(feature_id)


async def _validate_feature_step(step: str, feature: dict) -> dict:
    """Run validation logic for a specific feature build step."""

    if step == "tests_first":
        return await _step_tests_first(feature)
    elif step == "implement":
        return await _step_implement(feature)
    elif step == "full_pipeline":
        return await _step_full_pipeline()
    elif step == "performance_impact":
        return await _step_performance_impact()
    elif step == "regression":
        return await _step_regression()
    elif step == "deploy":
        return await _step_deploy(feature)
    else:
        return {"status": "FAIL", "issues": [f"Unknown step: {step}"]}


async def _step_tests_first(feature: dict) -> dict:
    """Step 1: Validate test files exist for the feature."""
    test_files = feature.get("test_files", [])
    issues = []
    found = []
    missing = []

    if not test_files:
        # Check if /app/backend/tests has any test files at all
        test_dir = "/app/backend/tests"
        try:
            entries = os.listdir(test_dir)
            test_count = sum(1 for e in entries if e.startswith("test_") and e.endswith(".py"))
            if test_count == 0:
                issues.append("No test files found in /app/backend/tests/")
            found.append(f"{test_count} test files found in test directory")
        except Exception as e:
            issues.append(f"Cannot access test directory: {e}")
    else:
        for tf in test_files:
            if os.path.isfile(tf):
                found.append(tf)
            else:
                missing.append(tf)
                issues.append(f"Test file missing: {tf}")

    status = "PASS" if not issues else "FAIL"
    if status == "PASS":
        await _store_system_memory(
            memory_type="test_pattern",
            signature=f"feature_tests::{feature.get('feature_id') or feature.get('name')}",
            problem_summary="Feature build test-first validation passed",
            solution_summary="Start feature workflow with explicit test files and keep tests green before implementation.",
            source="feature_build_step_tests_first",
            tags=["feature_build", "tests_first", "tdd"],
            confidence_score=0.7,
            evidence={"feature_id": feature.get("feature_id"), "test_files": test_files, "found": found},
        )
    return {
        "status": status,
        "step": "tests_first",
        "found": found,
        "missing": missing,
        "issues": issues,
    }


async def _step_implement(feature: dict) -> dict:
    """Step 2: Mark implementation as in progress. Always passes (acknowledgment step)."""
    return {
        "status": "PASS",
        "step": "implement",
        "message": f"Feature '{feature.get('name')}' implementation acknowledged",
        "issues": [],
    }


async def _step_full_pipeline() -> dict:
    """Step 3: Run the full autonomous engine pipeline."""
    try:
        config = await _get_engine_config()
        pipeline_result = await run_full_pipeline(config, triggered_by="feature_build_mode")

        final = pipeline_result.get("final_output", {})
        overall = final.get("STATUS", pipeline_result.get("status", "UNKNOWN"))
        issues = []
        gate_summary = {}
        for gate in GATE_NAMES:
            key = gate.upper()
            gate_status = final.get(key, "SKIP")
            gate_summary[gate] = gate_status
            if gate_status == "FAIL":
                gate_data = pipeline_result.get("gates", {}).get(gate, {})
                gate_issues = gate_data.get("issues", [])
                issues.append(f"Gate '{gate}' FAILED: {'; '.join(gate_issues[:2])}")

        status = "PASS" if overall == "PASS" else "FAIL"
        return {
            "status": status,
            "step": "full_pipeline",
            "overall": overall,
            "gates": gate_summary,
            "issues": issues,
        }
    except Exception as e:
        return {"status": "FAIL", "step": "full_pipeline", "issues": [str(e)[:300]]}


async def _step_performance_impact() -> dict:
    """Step 4: Run deployment gate to validate no performance degradation."""
    try:
        result = await _run_deployment_gate()
        issues = result.get("issues", [])
        details = result.get("details", {})
        load = details.get("load_simulation", {})
        stress = details.get("stress_test", {})

        return {
            "status": result["status"],
            "step": "performance_impact",
            "load_avg_ms": load.get("avg_response_ms", 0),
            "load_error_rate_pct": load.get("error_rate_pct", 0),
            "stress_avg_ms": stress.get("avg_response_ms", 0),
            "stress_error_rate_pct": stress.get("error_rate_pct", 0),
            "degradation_detected": details.get("degradation", {}).get("detected", False),
            "issues": issues,
        }
    except Exception as e:
        return {"status": "FAIL", "step": "performance_impact", "issues": [str(e)[:300]]}


async def _step_regression() -> dict:
    """Step 5: Compare against locked baseline to ensure no regression."""
    try:
        baseline = await _get_baseline_state()
        locked = baseline.get("locked", False)
        baseline_status = baseline.get("status", "UNKNOWN")

        # Run tests gate to check for regression
        tests_result = await _run_tests_gate()
        tests_passed = tests_result.get("status") == "PASS"

        issues = []
        if not tests_passed:
            issues.append(f"Tests gate regressed: {'; '.join(tests_result.get('issues', [])[:2])}")
        if locked and baseline_status == "PASS" and not tests_passed:
            issues.append("Regression detected against locked PASS baseline")

        return {
            "status": "PASS" if tests_passed else "FAIL",
            "step": "regression",
            "baseline_locked": locked,
            "baseline_status": baseline_status,
            "tests_passed": tests_passed,
            "issues": issues,
        }
    except Exception as e:
        return {"status": "FAIL", "step": "regression", "issues": [str(e)[:300]]}


async def _step_deploy(feature: dict) -> dict:
    """Step 6: Final deploy approval — verifies all prior steps passed."""
    db = await _db()
    feat = await db.feature_builds.find_one({"feature_id": feature.get("feature_id")})
    if not feat:
        return {"status": "FAIL", "step": "deploy", "issues": ["Feature not found"]}

    steps = feat.get("steps", {})
    all_prior_pass = True
    failed_steps = []
    for s in FEATURE_STEPS[:-1]:  # all except deploy itself
        s_data = steps.get(s, {})
        if s_data.get("status") != "PASS":
            all_prior_pass = False
            failed_steps.append(s)

    if not all_prior_pass:
        return {
            "status": "FAIL",
            "step": "deploy",
            "issues": [f"Cannot deploy: steps not passed: {', '.join(failed_steps)}"],
            "failed_steps": failed_steps,
        }

    return {
        "status": "PASS",
        "step": "deploy",
        "message": f"Feature '{feat.get('name')}' approved for deployment — all 6 steps PASSED",
        "issues": [],
    }


# ═══════════════════════════════════════════════════════════
# FAILURE MEMORY SYSTEM
# ═══════════════════════════════════════════════════════════

FAILURE_SEVERITY_SLA_HOURS = {
    "critical": 24,
    "high": 72,
    "medium": 168,
}

FAILURE_SEVERITY_RANK = {
    "critical": 3,
    "high": 2,
    "medium": 1,
}


def _normalize_failure_severity(
    severity: Optional[str],
    failure_type: str = "",
    component: str = "",
    root_cause: str = "",
) -> str:
    value = str(severity or "").strip().lower()
    if value in FAILURE_SEVERITY_SLA_HOURS:
        return value

    context = " ".join([str(failure_type or ""), str(component or ""), str(root_cause or "")]).lower()
    if any(token in context for token in ["security", "auth", "injection", "xss", "csrf", "vulnerability"]):
        return "critical"
    if any(token in context for token in ["deployment", "gate_failure", "coverage", "tests", "drift"]):
        return "high"
    return "medium"


def _infer_failure_owner(component: str, failure_type: str = "") -> str:
    comp = str(component or "").strip().lower()
    f_type = str(failure_type or "").strip().lower()
    if any(token in comp for token in ["security", "auth"]):
        return "security-oncall"
    if any(token in comp for token in ["deployment", "canary", "performance", "drift"]):
        return "devops-oncall"
    if any(token in comp for token in ["tests", "coverage", "validation"]) or f_type in {"gate_failure", "build_block"}:
        return "qa-oncall"
    if any(token in comp for token in ["feature", "frontend", "ui"]):
        return "feature-oncall"
    return "unassigned"


def _build_failure_incident_key(failure_type: str, component: str, error_signature: str) -> str:
    seed = "|".join(
        [
            str(failure_type or "").strip().lower(),
            str(component or "").strip().lower(),
            _normalize_signature(error_signature or ""),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"fm_{digest}"


def _compute_failure_sla_fields(logged_at: str, severity: str, sla_hours_override: Optional[int] = None) -> dict:
    now = datetime.now(timezone.utc)
    logged_dt = _parse_iso_datetime(logged_at) or now
    if logged_dt.tzinfo is None:
        logged_dt = logged_dt.replace(tzinfo=timezone.utc)

    default_hours = FAILURE_SEVERITY_SLA_HOURS.get(severity, FAILURE_SEVERITY_SLA_HOURS["high"])
    if sla_hours_override is not None:
        try:
            sla_hours = max(1, int(sla_hours_override))
        except Exception:
            sla_hours = default_hours
    else:
        sla_hours = default_hours

    due_at = logged_dt + timedelta(hours=sla_hours)
    remaining_minutes = int((due_at - now).total_seconds() // 60)
    status = "BREACHED" if remaining_minutes < 0 else "ON_TRACK"

    return {
        "sla_hours": sla_hours,
        "sla_due_at": due_at.isoformat(),
        "sla_status": status,
        "sla_remaining_minutes": remaining_minutes,
    }


async def _upsert_failure_memory_entry(
    *,
    failure_type: str,
    component: str,
    error_signature: str,
    root_cause: str,
    fix_applied: str = "",
    context: Optional[dict] = None,
    source: str = "auto",
    owner: Optional[str] = None,
    severity: Optional[str] = None,
    sla_hours: Optional[int] = None,
    confirm_fix: bool = False,
    resolved_by: str = "system",
) -> dict:
    db = await _db()
    now_iso = datetime.now(timezone.utc).isoformat()

    failure_type_clean = str(failure_type or "unknown").strip().lower()
    component_clean = str(component or "unknown").strip().lower()
    signature_clean = str(error_signature or "").strip()[:500]
    root_cause_clean = str(root_cause or signature_clean or "unknown").strip()[:1000]
    fix_clean = str(fix_applied or "").strip()[:1000]
    context_clean = context or {}
    severity_clean = _normalize_failure_severity(severity, failure_type_clean, component_clean, root_cause_clean)
    owner_clean = str(owner or "").strip() or _infer_failure_owner(component_clean, failure_type_clean)
    incident_key = _build_failure_incident_key(failure_type_clean, component_clean, signature_clean or root_cause_clean)

    existing = await db.failure_memory.find_one(
        {"incident_key": incident_key, "fix_confirmed": {"$ne": True}},
        {"_id": 1, "logged_at": 1, "owner": 1, "severity": 1, "occurrence_count": 1, "fix_success_count": 1, "fix_fail_count": 1},
    )

    if existing:
        existing_logged_at = str(existing.get("logged_at") or now_iso)
        existing_owner = str(existing.get("owner") or "").strip()
        existing_severity = _normalize_failure_severity(existing.get("severity"), failure_type_clean, component_clean, root_cause_clean)
        final_severity = (
            severity_clean
            if FAILURE_SEVERITY_RANK.get(severity_clean, 1) >= FAILURE_SEVERITY_RANK.get(existing_severity, 1)
            else existing_severity
        )
        final_owner = existing_owner or owner_clean
        sla = _compute_failure_sla_fields(existing_logged_at, final_severity, sla_hours)

        update_set: Dict[str, Any] = {
            "last_seen_at": now_iso,
            "error_signature": signature_clean,
            "root_cause": root_cause_clean,
            "context": context_clean,
            "source": source,
            "severity": final_severity,
            "owner": final_owner,
            "incident_key": incident_key,
            "sla_hours": sla["sla_hours"],
            "sla_due_at": sla["sla_due_at"],
            "sla_status": sla["sla_status"],
            "sla_remaining_minutes": sla["sla_remaining_minutes"],
            "resolution_state": "open",
        }
        inc_payload: Dict[str, int] = {"occurrence_count": 1}

        if fix_clean:
            update_set["fix_applied"] = fix_clean

        if confirm_fix:
            update_set.update(
                {
                    "fix_confirmed": True,
                    "resolved_at": now_iso,
                    "resolved_by": resolved_by,
                    "resolution_state": "resolved",
                    "sla_status": "RESOLVED",
                    "sla_remaining_minutes": 0,
                    "fix_applied": fix_clean or "resolved_from_failure_memory_system",
                }
            )
            inc_payload["fix_success_count"] = 1

        await db.failure_memory.update_one(
            {"_id": existing["_id"]},
            {
                "$set": update_set,
                "$inc": inc_payload,
            },
        )
        return {
            "action": "updated",
            "incident_key": incident_key,
            "logged_at": existing_logged_at,
            "owner": final_owner,
            "severity": final_severity,
            "occurrence_count": int(existing.get("occurrence_count") or 0) + 1,
        }

    sla = _compute_failure_sla_fields(now_iso, severity_clean, sla_hours)
    entry = {
        "failure_type": failure_type_clean,
        "component": component_clean,
        "error_signature": signature_clean,
        "root_cause": root_cause_clean,
        "fix_applied": fix_clean,
        "context": context_clean,
        "logged_at": now_iso,
        "first_seen_at": now_iso,
        "last_seen_at": now_iso,
        "source": source,
        "fix_confirmed": bool(confirm_fix),
        "fix_success_count": 1 if confirm_fix else 0,
        "fix_fail_count": 0,
        "occurrence_count": 1,
        "incident_key": incident_key,
        "owner": owner_clean,
        "severity": severity_clean,
        "sla_hours": sla["sla_hours"],
        "sla_due_at": sla["sla_due_at"],
        "sla_status": "RESOLVED" if confirm_fix else sla["sla_status"],
        "sla_remaining_minutes": 0 if confirm_fix else sla["sla_remaining_minutes"],
        "resolution_state": "resolved" if confirm_fix else "open",
    }
    if confirm_fix:
        entry.update(
            {
                "resolved_at": now_iso,
                "resolved_by": resolved_by,
            }
        )

    await db.failure_memory.insert_one(entry)
    return {
        "action": "inserted",
        "incident_key": incident_key,
        "logged_at": now_iso,
        "owner": owner_clean,
        "severity": severity_clean,
        "occurrence_count": 1,
    }

async def _auto_log_failure(failure_type: str, component: str, error_signature: str,
                            root_cause: str, fix_applied: str = "", context: dict = None):
    """Auto-log a failure to the failure memory (called internally by gates/features)."""
    try:
        await _upsert_failure_memory_entry(
            failure_type=failure_type,
            component=component,
            error_signature=error_signature,
            root_cause=root_cause,
            fix_applied=fix_applied,
            context=context,
            source="auto",
        )
    except Exception:
        pass


def _normalize_signature(sig: str) -> str:
    """Normalize an error signature for fuzzy matching."""
    import re
    sig = sig.lower().strip()
    sig = re.sub(r'[0-9a-f]{8,}', '<hash>', sig)
    sig = re.sub(r'\d+\.\d+\.\d+', '<version>', sig)
    sig = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<timestamp>', sig)
    sig = re.sub(r'\d+', '<num>', sig)
    sig = re.sub(r'\s+', ' ', sig)
    return sig


async def _lookup_similar_failures(failure_type: str = "", component: str = "",
                                    error_signature: str = "", limit: int = 10) -> list:
    """Find similar past failures by type, component, or error pattern."""
    db = await _db()
    query: Dict[str, Any] = {}

    if failure_type:
        query["failure_type"] = failure_type
    if component:
        query["component"] = {"$regex": re.escape(str(component)), "$options": "i"}

    candidates = await db.failure_memory.find(
        query if query else {}, {"_id": 0}
    ).sort("logged_at", -1).limit(100).to_list(100)

    if not error_signature:
        return candidates[:limit]

    # Fuzzy match on normalized error signature
    norm_input = _normalize_signature(error_signature)
    input_words = set(norm_input.split())

    scored = []
    for c in candidates:
        norm_stored = _normalize_signature(c.get("error_signature", ""))
        stored_words = set(norm_stored.split())
        if not stored_words:
            continue
        overlap = len(input_words & stored_words)
        union = len(input_words | stored_words)
        similarity = overlap / union if union > 0 else 0

        # Boost confirmed fixes
        boost = 0
        if c.get("fix_confirmed"):
            boost += 0.2
        boost += min(c.get("fix_success_count", 0) * 0.05, 0.3)

        scored.append({**c, "_similarity": round(similarity + boost, 3)})

    scored.sort(key=lambda x: x["_similarity"], reverse=True)
    return [s for s in scored if s["_similarity"] > 0.1][:limit]


class FailureLogPayload(BaseModel):
    failure_type: str
    component: str
    error_signature: str
    root_cause: str
    fix_applied: Optional[str] = ""
    context: Optional[Dict[str, Any]] = {}
    owner: Optional[str] = ""
    severity: Optional[str] = ""
    sla_hours: Optional[int] = None


@router.post("/failure-memory/log")
async def log_failure(request: Request, body: FailureLogPayload):
    """Manually log a failure with root cause and fix to the failure memory."""
    await _require_admin(request)
    now_iso = datetime.now(timezone.utc).isoformat()

    upsert_result = await _upsert_failure_memory_entry(
        failure_type=body.failure_type,
        component=body.component,
        error_signature=body.error_signature,
        root_cause=body.root_cause,
        fix_applied=body.fix_applied or "",
        context=body.context or {},
        source="manual",
        owner=body.owner,
        severity=body.severity,
        sla_hours=body.sla_hours,
        confirm_fix=bool(body.fix_applied),
        resolved_by="admin_manual_log",
    )

    return {
        "logged": True,
        "failure_type": str(body.failure_type).strip().lower(),
        "component": str(body.component).strip().lower(),
        "has_fix": bool(body.fix_applied),
        "logged_at": upsert_result.get("logged_at") or now_iso,
        "incident_key": upsert_result.get("incident_key"),
        "deduplicated": upsert_result.get("action") == "updated",
        "owner": upsert_result.get("owner"),
        "severity": upsert_result.get("severity"),
        "occurrence_count": upsert_result.get("occurrence_count", 1),
    }


class FailureLookupParams(BaseModel):
    failure_type: Optional[str] = ""
    component: Optional[str] = ""
    error_signature: Optional[str] = ""
    limit: Optional[int] = 10


class FailureResolvePayload(BaseModel):
    logged_at: str
    failure_type: str
    component: str
    fix_applied: Optional[str] = ""


class FailureAssignOwnerPayload(BaseModel):
    logged_at: str
    failure_type: str
    component: str
    owner: str
    severity: Optional[str] = None
    sla_hours: Optional[int] = None


class FailureReconcilePayload(BaseModel):
    quiet_minutes: Optional[int] = 60
    limit: Optional[int] = 500
    resolution_note: Optional[str] = "auto_reconciled_after_global_pass"


@router.post("/failure-memory/lookup")
async def lookup_failure(request: Request, body: FailureLookupParams):
    """Find similar past failures. Returns matches ranked by similarity + fix success rate."""
    await _require_admin(request)

    matches = await _lookup_similar_failures(
        failure_type=body.failure_type or "",
        component=body.component or "",
        error_signature=body.error_signature or "",
        limit=body.limit or 10,
    )

    proven_fixes = [m for m in matches if m.get("fix_applied") and m.get("fix_confirmed")]

    return {
        "query": {
            "failure_type": body.failure_type,
            "component": body.component,
            "error_signature": body.error_signature[:100] if body.error_signature else "",
        },
        "total_matches": len(matches),
        "proven_fixes": len(proven_fixes),
        "matches": matches,
        "recommendation": proven_fixes[0]["fix_applied"] if proven_fixes else None,
    }


@router.get("/failure-memory/history")
async def get_failure_history(request: Request, limit: int = Query(default=50, ge=1, le=500),
                               failure_type: str = Query(default=""),
                               component: str = Query(default="")):
    """Browse full failure memory with optional filters."""
    await _require_admin(request)
    db = await _db()
    query: Dict[str, Any] = {}
    if failure_type:
        query["failure_type"] = failure_type
    if component:
        query["component"] = {"$regex": re.escape(str(component)), "$options": "i"}

    entries = await db.failure_memory.find(
        query, {"_id": 0}
    ).sort("logged_at", -1).limit(limit).to_list(limit)

    # Stats
    total = await db.failure_memory.count_documents({})
    confirmed = await db.failure_memory.count_documents({"fix_confirmed": True})
    types_pipeline = [{"$group": {"_id": "$failure_type", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    type_counts = await db.failure_memory.aggregate(types_pipeline).to_list(50)

    return {
        "entries": entries,
        "total_in_memory": total,
        "total_with_confirmed_fix": confirmed,
        "failure_types": {t["_id"]: t["count"] for t in type_counts if t["_id"]},
        "returned": len(entries),
    }


@router.get("/failure-memory/dashboard")
async def get_failure_memory_dashboard(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Executive Failure Memory dashboard: trends, root causes, fix success rates."""
    await _require_admin(request)
    db = await _db()

    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=days)).isoformat()

    entries = await db.failure_memory.find(
        {"logged_at": {"$gte": since_iso}},
        {
            "_id": 0,
            "failure_type": 1,
            "component": 1,
            "root_cause": 1,
            "fix_confirmed": 1,
            "logged_at": 1,
            "fix_success_count": 1,
            "fix_fail_count": 1,
            "error_signature": 1,
            "incident_key": 1,
            "owner": 1,
            "severity": 1,
            "sla_hours": 1,
            "sla_due_at": 1,
            "sla_status": 1,
            "first_seen_at": 1,
            "last_seen_at": 1,
            "occurrence_count": 1,
        },
    ).sort("logged_at", -1).to_list(5000)

    total_entries = len(entries)
    confirmed_fix = sum(1 for item in entries if bool(item.get("fix_confirmed")))
    unresolved_count = total_entries - confirmed_fix
    fix_success_rate_pct = round((confirmed_fix / max(total_entries, 1)) * 100, 1) if total_entries else 0.0

    type_counts: Dict[str, int] = {}
    component_counts: Dict[str, int] = {}
    root_cause_counts: Dict[str, int] = {}
    daily_rollup: Dict[str, Dict[str, int]] = {}

    for item in entries:
        f_type = str(item.get("failure_type") or "unknown").strip().lower()
        component = str(item.get("component") or "unknown").strip()
        root = str(item.get("root_cause") or "unknown").strip()
        root_norm = root.split("\n")[0][:120] if root else "unknown"
        logged_at = str(item.get("logged_at") or "")
        day_key = logged_at[:10] if len(logged_at) >= 10 else "unknown"

        type_counts[f_type] = int(type_counts.get(f_type, 0) or 0) + 1
        component_counts[component] = int(component_counts.get(component, 0) or 0) + 1
        root_cause_counts[root_norm] = int(root_cause_counts.get(root_norm, 0) or 0) + 1

        if day_key not in daily_rollup:
            daily_rollup[day_key] = {"failures": 0, "confirmed": 0}
        daily_rollup[day_key]["failures"] += 1
        if bool(item.get("fix_confirmed")):
            daily_rollup[day_key]["confirmed"] += 1

    top_failure_types = sorted(type_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    top_components = sorted(component_counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    top_root_causes = sorted(root_cause_counts.items(), key=lambda item: item[1], reverse=True)[:limit]

    trend = []
    for day in sorted(daily_rollup.keys()):
        bucket = daily_rollup[day]
        failures = int(bucket.get("failures", 0) or 0)
        confirmed = int(bucket.get("confirmed", 0) or 0)
        trend.append(
            {
                "date": day,
                "failures": failures,
                "confirmed": confirmed,
                "fix_rate_pct": round((confirmed / max(failures, 1)) * 100, 1) if failures else 0.0,
            }
        )

    unresolved_entries_all = [item for item in entries if not bool(item.get("fix_confirmed"))]
    unresolved_entries: List[Dict[str, Any]] = []
    assigned_count = 0
    unassigned_count = 0
    sla_breached_count = 0
    owner_counts: Dict[str, int] = {}

    for item in unresolved_entries_all:
        severity = _normalize_failure_severity(item.get("severity"), item.get("failure_type"), item.get("component"), item.get("root_cause"))
        owner = str(item.get("owner") or "").strip() or "unassigned"
        sla = _compute_failure_sla_fields(str(item.get("logged_at") or now.isoformat()), severity, item.get("sla_hours"))
        owner_counts[owner] = int(owner_counts.get(owner, 0) or 0) + 1

        if owner == "unassigned":
            unassigned_count += 1
        else:
            assigned_count += 1
        if sla["sla_status"] == "BREACHED":
            sla_breached_count += 1

        unresolved_entries.append(
            {
                **item,
                "owner": owner,
                "severity": severity,
                "sla_hours": int(sla["sla_hours"]),
                "sla_due_at": sla["sla_due_at"],
                "sla_status": sla["sla_status"],
                "sla_remaining_minutes": sla["sla_remaining_minutes"],
                "occurrence_count": int(item.get("occurrence_count") or 1),
            }
        )

    unresolved_entries = unresolved_entries[:limit]
    top_owners = sorted(owner_counts.items(), key=lambda item: item[1], reverse=True)[:limit]

    return {
        "window_days": days,
        "generated_at": now.isoformat(),
        "summary": {
            "total_entries": total_entries,
            "confirmed_fix": confirmed_fix,
            "unresolved_count": unresolved_count,
            "fix_success_rate_pct": fix_success_rate_pct,
            "assigned_count": assigned_count,
            "unassigned_count": unassigned_count,
            "sla_breached_count": sla_breached_count,
        },
        "top_failure_types": [{"failure_type": key, "count": count} for key, count in top_failure_types],
        "top_components": [{"component": key, "count": count} for key, count in top_components],
        "top_root_causes": [{"root_cause": key, "count": count} for key, count in top_root_causes],
        "top_owners": [{"owner": key, "count": count} for key, count in top_owners],
        "trend": trend,
        "unresolved_entries": unresolved_entries,
    }


@router.post("/failure-memory/resolve")
async def resolve_failure_memory_entry(request: Request, body: FailureResolvePayload):
    """Resolve an unresolved failure entry from the dashboard for closed-loop remediation."""
    await _require_admin(request)
    db = await _db()
    now_iso = datetime.now(timezone.utc).isoformat()

    query = {
        "logged_at": body.logged_at,
        "failure_type": body.failure_type,
        "component": body.component,
        "fix_confirmed": {"$ne": True},
    }
    target = await db.failure_memory.find_one(query, {"_id": 1, "fix_success_count": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Unresolved failure entry not found or already resolved")

    await db.failure_memory.update_one(
        {"_id": target["_id"]},
        {
            "$set": {
                "fix_confirmed": True,
                "fix_applied": (body.fix_applied or "resolved_from_failure_memory_dashboard").strip(),
                "resolved_at": now_iso,
                "resolved_by": "admin_dashboard",
                "resolution_state": "resolved",
                "sla_status": "RESOLVED",
                "sla_remaining_minutes": 0,
            },
            "$inc": {"fix_success_count": 1},
        },
    )

    unresolved_count = await db.failure_memory.count_documents({"fix_confirmed": {"$ne": True}})
    return {
        "resolved": True,
        "resolved_at": now_iso,
        "failure_type": body.failure_type,
        "component": body.component,
        "logged_at": body.logged_at,
        "remaining_unresolved": unresolved_count,
    }


@router.post("/failure-memory/assign-owner")
async def assign_failure_memory_owner(request: Request, body: FailureAssignOwnerPayload):
    """Assign owner + SLA metadata directly on unresolved failure entries."""
    await _require_admin(request)
    db = await _db()
    now_iso = datetime.now(timezone.utc).isoformat()

    owner = str(body.owner or "").strip()
    if not owner:
        raise HTTPException(status_code=400, detail="Owner is required")

    query = {
        "logged_at": body.logged_at,
        "failure_type": {"$regex": f"^{re.escape(str(body.failure_type or '').strip())}$", "$options": "i"},
        "component": {"$regex": f"^{re.escape(str(body.component or '').strip())}$", "$options": "i"},
        "fix_confirmed": {"$ne": True},
    }
    target = await db.failure_memory.find_one(query, {"_id": 1, "logged_at": 1, "root_cause": 1, "failure_type": 1, "component": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Unresolved failure entry not found for owner assignment")

    normalized_failure_type = str(target.get("failure_type") or body.failure_type or "").strip().lower()
    normalized_component = str(target.get("component") or body.component or "").strip().lower()
    severity = _normalize_failure_severity(body.severity, normalized_failure_type, normalized_component, target.get("root_cause") or "")
    sla = _compute_failure_sla_fields(str(target.get("logged_at") or now_iso), severity, body.sla_hours)

    await db.failure_memory.update_one(
        {"_id": target["_id"]},
        {
            "$set": {
                "owner": owner,
                "severity": severity,
                "sla_hours": sla["sla_hours"],
                "sla_due_at": sla["sla_due_at"],
                "sla_status": sla["sla_status"],
                "sla_remaining_minutes": sla["sla_remaining_minutes"],
                "assignment_updated_at": now_iso,
            }
        },
    )

    unresolved_unassigned = await db.failure_memory.count_documents(
        {
            "fix_confirmed": {"$ne": True},
            "$or": [{"owner": {"$exists": False}}, {"owner": ""}, {"owner": "unassigned"}],
        }
    )

    return {
        "assigned": True,
        "logged_at": body.logged_at,
        "failure_type": normalized_failure_type,
        "component": normalized_component,
        "owner": owner,
        "severity": severity,
        "sla_hours": sla["sla_hours"],
        "sla_due_at": sla["sla_due_at"],
        "sla_status": sla["sla_status"],
        "remaining_unassigned": unresolved_unassigned,
    }


@router.post("/failure-memory/reconcile")
async def reconcile_failure_memory(request: Request, body: FailureReconcilePayload):
    """Auto-reconcile unresolved failures after global PASS evidence and quiet period."""
    await _require_admin(request)
    db = await _db()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    quiet_minutes = max(5, min(int(body.quiet_minutes or 60), 10080))
    max_entries = max(1, min(int(body.limit or 500), 5000))
    resolution_note = str(body.resolution_note or "auto_reconciled_after_global_pass").strip()[:300]

    config = await _get_engine_config()
    gate_lock = await _build_gate_lock_state(config)
    pipeline_pass = str((gate_lock.get("latest_run_output") or {}).get("STATUS") or "").upper() == "PASS"

    latest_reality = await db.reality_validation_runs.find_one(
        {}, {"_id": 0, "run_id": 1, "reality_status": 1, "confidence": 1}, sort=[("created_at", -1)]
    ) or {}
    reality_pass = str(latest_reality.get("reality_status") or "").upper() == "PASS" and str(latest_reality.get("confidence") or "").upper() == "HIGH"

    if not (pipeline_pass and reality_pass):
        unresolved_count = await db.failure_memory.count_documents({"fix_confirmed": {"$ne": True}})
        return {
            "reconciled": False,
            "reason": "Global PASS evidence not satisfied",
            "resolved_entries": 0,
            "remaining_unresolved": unresolved_count,
            "pipeline_pass": pipeline_pass,
            "reality_pass": reality_pass,
            "latest_pipeline_run_id": gate_lock.get("latest_run_id"),
            "latest_reality_run_id": latest_reality.get("run_id"),
        }

    cutoff_dt = now - timedelta(minutes=quiet_minutes)
    candidates = await db.failure_memory.find(
        {"fix_confirmed": {"$ne": True}},
        {
            "_id": 1,
            "logged_at": 1,
            "last_seen_at": 1,
            "incident_key": 1,
            "failure_type": 1,
            "component": 1,
            "occurrence_count": 1,
        },
    ).sort("last_seen_at", -1).limit(max_entries).to_list(max_entries)

    resolved_count = 0
    resolved_preview = []
    for item in candidates:
        last_seen = _parse_iso_datetime(str(item.get("last_seen_at") or item.get("logged_at") or ""))
        if not last_seen:
            continue
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        if last_seen > cutoff_dt:
            continue

        await db.failure_memory.update_one(
            {"_id": item["_id"], "fix_confirmed": {"$ne": True}},
            {
                "$set": {
                    "fix_confirmed": True,
                    "resolved_at": now_iso,
                    "resolved_by": "auto_reconciliation",
                    "fix_applied": resolution_note,
                    "resolution_state": "auto_resolved",
                    "sla_status": "RESOLVED",
                    "sla_remaining_minutes": 0,
                    "reconciled_from_pipeline_run_id": gate_lock.get("latest_run_id"),
                    "reconciled_from_reality_run_id": latest_reality.get("run_id"),
                },
                "$inc": {"fix_success_count": 1},
            },
        )
        resolved_count += 1
        if len(resolved_preview) < 10:
            resolved_preview.append(
                {
                    "incident_key": item.get("incident_key"),
                    "failure_type": item.get("failure_type"),
                    "component": item.get("component"),
                    "last_seen_at": item.get("last_seen_at") or item.get("logged_at"),
                    "occurrence_count": int(item.get("occurrence_count") or 1),
                }
            )

    unresolved_count = await db.failure_memory.count_documents({"fix_confirmed": {"$ne": True}})
    return {
        "reconciled": True,
        "resolved_entries": resolved_count,
        "remaining_unresolved": unresolved_count,
        "quiet_minutes": quiet_minutes,
        "limit": max_entries,
        "latest_pipeline_run_id": gate_lock.get("latest_run_id"),
        "latest_reality_run_id": latest_reality.get("run_id"),
        "resolved_preview": resolved_preview,
    }


class ConfirmFixPayload(BaseModel):
    failure_type: str
    component: str
    error_signature: str
    success: bool = True


@router.post("/failure-memory/confirm-fix")
async def confirm_fix(request: Request, body: ConfirmFixPayload):
    """Mark a fix as successful or failed. Successful fixes get boosted in future lookups."""
    await _require_admin(request)
    db = await _db()

    # Find the most recent matching entry
    query = {"failure_type": body.failure_type, "component": body.component}
    entry = await db.failure_memory.find_one(query, sort=[("logged_at", -1)])
    if not entry:
        raise HTTPException(status_code=404, detail="No matching failure found in memory")

    if body.success:
        update = {"$set": {"fix_confirmed": True}, "$inc": {"fix_success_count": 1}}
    else:
        update = {"$inc": {"fix_fail_count": 1}}

    await db.failure_memory.update_one({"_id": entry["_id"]}, update)

    return {
        "confirmed": True,
        "failure_type": body.failure_type,
        "component": body.component,
        "success": body.success,
        "new_success_count": entry.get("fix_success_count", 0) + (1 if body.success else 0),
        "new_fail_count": entry.get("fix_fail_count", 0) + (0 if body.success else 1),
    }


# ═══════════════════════════════════════════════════════════
# CONTINUOUS PERFORMANCE OPTIMIZATION
# ═══════════════════════════════════════════════════════════

DEFAULT_PERF_AUDIT_POLICY = {
    "bundle_growth_alert_pct": 10.0,
    "latency_trend_alert_factor": 2.0,
    "memory_alert_mb": 512,
    "db_bloat_alert_mb": 4096,
    "api_sample_endpoints": [
        "/api/health",
        "/api/auth/sso-config",
        "/api/features/registry",
        "/api/system/vanity-metrics",
    ],
    "api_samples_per_endpoint": 3,
}


async def run_perf_audit(triggered_by: str = "manual") -> dict:
    """Run a full performance audit: API latency, bundle size, resource utilization."""
    import aiohttp
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("perf_audit_policy", DEFAULT_PERF_AUDIT_POLICY)
    now_iso = datetime.now(timezone.utc).isoformat()
    alerts = []

    base_url = "http://localhost:8001"
    endpoints = policy.get("api_sample_endpoints", DEFAULT_PERF_AUDIT_POLICY["api_sample_endpoints"])
    samples_per = int(policy.get("api_samples_per_endpoint", 3))

    # ── 1. API Latency Sampling ──
    api_metrics = {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
            for ep in endpoints:
                lats = []
                for _ in range(samples_per):
                    t0 = asyncio.get_event_loop().time()
                    try:
                        async with sess.get(f"{base_url}{ep}") as resp:
                            await resp.read()
                            lats.append(round((asyncio.get_event_loop().time() - t0) * 1000, 1))
                    except Exception:
                        pass
                if lats:
                    api_metrics[ep] = {
                        "avg_ms": round(sum(lats) / len(lats), 1),
                        "min_ms": min(lats),
                        "max_ms": max(lats),
                        "samples": len(lats),
                    }
    except Exception:
        pass

    overall_avg = round(sum(m["avg_ms"] for m in api_metrics.values()) / max(len(api_metrics), 1), 1) if api_metrics else 0

    # ── 2. Bundle Size Tracking ──
    bundle_size_bytes = 0
    bundle_files = {}
    dist_dir = "/app/frontend/dist"
    try:
        for root, dirs, files in os.walk(dist_dir):
            for f in files:
                fp = os.path.join(root, f)
                sz = os.path.getsize(fp)
                bundle_size_bytes += sz
                ext = os.path.splitext(f)[1] or "other"
                bundle_files[ext] = bundle_files.get(ext, 0) + sz
    except Exception:
        pass
    bundle_size_mb = round(bundle_size_bytes / (1024 * 1024), 2)

    # Check bundle growth vs previous audit
    prev_audit = await db.perf_audit_history.find_one(
        {"bundle_size_mb": {"$exists": True}}, {"_id": 0, "bundle_size_mb": 1},
        sort=[("audited_at", -1)],
    )
    bundle_growth_pct = 0
    if prev_audit and prev_audit.get("bundle_size_mb", 0) > 0:
        prev_mb = prev_audit["bundle_size_mb"]
        bundle_growth_pct = round(((bundle_size_mb - prev_mb) / prev_mb) * 100, 1)
        if bundle_growth_pct > policy.get("bundle_growth_alert_pct", 10):
            alerts.append({
                "type": "bundle_growth",
                "severity": "warning",
                "detail": f"Bundle grew {bundle_growth_pct}% ({prev_mb}MB -> {bundle_size_mb}MB), threshold: {policy['bundle_growth_alert_pct']}%",
            })

    # ── 3. Resource Utilization ──
    import resource as res_mod
    memory_usage_mb = round(res_mod.getrusage(res_mod.RUSAGE_SELF).ru_maxrss / 1024, 1)

    # DB collection sizes
    db_stats = {}
    try:
        stats = await db.command("dbStats")
        db_stats["total_size_mb"] = round(stats.get("dataSize", 0) / (1024 * 1024), 2)
        db_stats["collections"] = stats.get("collections", 0)
        db_stats["indexes"] = stats.get("indexes", 0)
        db_stats["storage_mb"] = round(stats.get("storageSize", 0) / (1024 * 1024), 2)
    except Exception:
        pass

    if memory_usage_mb > policy.get("memory_alert_mb", 512):
        alerts.append({
            "type": "memory_high",
            "severity": "warning",
            "detail": f"Memory usage {memory_usage_mb}MB exceeds {policy['memory_alert_mb']}MB threshold",
        })
    if db_stats.get("total_size_mb", 0) > policy.get("db_bloat_alert_mb", 4096):
        alerts.append({
            "type": "db_bloat",
            "severity": "warning",
            "detail": f"DB size {db_stats['total_size_mb']}MB exceeds {policy['db_bloat_alert_mb']}MB threshold",
        })

    # Latency trend alert
    prev_latency_audits = await db.perf_audit_history.find(
        {"api_overall_avg_ms": {"$exists": True, "$gt": 0}}, {"_id": 0, "api_overall_avg_ms": 1},
    ).sort("audited_at", -1).limit(5).to_list(5)
    if prev_latency_audits and overall_avg > 0:
        historical_avg = sum(a["api_overall_avg_ms"] for a in prev_latency_audits) / len(prev_latency_audits)
        if historical_avg > 0:
            trend_factor = round(overall_avg / historical_avg, 2)
            if trend_factor > policy.get("latency_trend_alert_factor", 2.0):
                alerts.append({
                    "type": "latency_trend",
                    "severity": "warning",
                    "detail": f"Latency trending up: {overall_avg}ms vs historical avg {round(historical_avg, 1)}ms ({trend_factor}x)",
                })

    # ── Persist audit ──
    audit = {
        "audited_at": now_iso,
        "triggered_by": triggered_by,
        "api_metrics": api_metrics,
        "api_overall_avg_ms": overall_avg,
        "bundle_size_mb": bundle_size_mb,
        "bundle_size_bytes": bundle_size_bytes,
        "bundle_growth_pct": bundle_growth_pct,
        "bundle_breakdown": {k: round(v / 1024, 1) for k, v in bundle_files.items()},
        "memory_usage_mb": memory_usage_mb,
        "db_stats": db_stats,
        "alerts": alerts,
        "alert_count": len(alerts),
        "status": "ALERT" if alerts else "HEALTHY",
    }
    await db.perf_audit_history.insert_one({**audit})

    # Send admin alert if any (6h email cooldown — audits are persisted regardless)
    if alerts:
        try:
            _state = await db.perf_audit_alert_state.find_one({"_id": "state"}) or {}
            _last_raw = _state.get("last_email_at")
            try:
                _last_dt = datetime.fromisoformat(_last_raw) if _last_raw else None
            except Exception:
                _last_dt = None
            _now_dt = datetime.now(timezone.utc)
            if _last_dt and (_now_dt - _last_dt).total_seconds() < 6 * 3600:
                raise StopAsyncIteration
            alert_lines = "".join(
                f"<p style='margin:4px 0;color:#334155;font-size:12px'>- <strong>{a['type']}</strong>: {a['detail']}</p>"
                for a in alerts
            )
            (
                "<div class='em-force-light-card' style='font-family:Inter,sans-serif;padding:16px;background:#FFFFFF;border:1px solid #FCD34D;border-radius:10px'>"
                f"<h3 class='em-force-dark-text' style='margin:0 0 8px;color:#B45309'>Performance Audit Alert</h3>"
                f"<p class='em-force-muted-text' style='margin:0 0 8px;color:#475569;font-size:13px'>{len(alerts)} alert(s) detected</p>"
                f"{alert_lines}</div>"
            )
            from utils.email_service import send_catalog_template
            await send_catalog_template(recipient_email="admin@realaicoach.app",
                             template_key="system_alert_admin",
                             alert_type="Performance Audit Alert",
                             severity="WARNING",
                             description=f"{len(alerts)} performance alert(s) detected at {now_iso[:10]}",
                             component="Performance Audit")
            await db.perf_audit_alert_state.update_one(
                {"_id": "state"}, {"$set": {"last_email_at": _now_dt.isoformat()}}, upsert=True
            )
        except Exception:
            pass

    return audit


@router.post("/perf-audit/run")
async def trigger_perf_audit(request: Request):
    """Trigger a manual performance audit."""
    await _require_admin(request)
    result = await run_perf_audit(triggered_by="manual")
    return result


@router.get("/perf-audit/latest")
async def get_latest_perf_audit(request: Request):
    """Get the most recent performance audit snapshot."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("perf_audit_policy", DEFAULT_PERF_AUDIT_POLICY)

    latest = await db.perf_audit_history.find_one({}, {"_id": 0}, sort=[("audited_at", -1)])

    return {
        "latest": latest,
        "policy": policy,
    }


@router.get("/perf-audit/trends")
async def get_perf_trends(request: Request, limit: int = Query(default=20, ge=1, le=200)):
    """Get performance audit time-series trends."""
    await _require_admin(request)
    db = await _db()

    audits = await db.perf_audit_history.find(
        {}, {"_id": 0}
    ).sort("audited_at", -1).limit(limit).to_list(limit)
    return build_perf_trends_payload(audits)


class PerfAuditPolicyUpdate(BaseModel):
    bundle_growth_alert_pct: Optional[float] = None
    latency_trend_alert_factor: Optional[float] = None
    memory_alert_mb: Optional[float] = None
    db_bloat_alert_mb: Optional[float] = None
    api_sample_endpoints: Optional[List[str]] = None
    api_samples_per_endpoint: Optional[int] = None


@router.post("/perf-audit/policy")
async def update_perf_audit_policy(request: Request, body: PerfAuditPolicyUpdate):
    """Update performance audit policy thresholds."""
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("perf_audit_policy", {**DEFAULT_PERF_AUDIT_POLICY})

    if body.bundle_growth_alert_pct is not None:
        policy["bundle_growth_alert_pct"] = max(1, body.bundle_growth_alert_pct)
    if body.latency_trend_alert_factor is not None:
        policy["latency_trend_alert_factor"] = max(1.1, body.latency_trend_alert_factor)
    if body.memory_alert_mb is not None:
        policy["memory_alert_mb"] = max(64, body.memory_alert_mb)
    if body.db_bloat_alert_mb is not None:
        policy["db_bloat_alert_mb"] = max(10, body.db_bloat_alert_mb)
    if body.api_sample_endpoints is not None:
        policy["api_sample_endpoints"] = body.api_sample_endpoints
    if body.api_samples_per_endpoint is not None:
        policy["api_samples_per_endpoint"] = max(1, min(20, body.api_samples_per_endpoint))

    config["perf_audit_policy"] = policy
    await _save_engine_config(config)

    return {"updated": True, "perf_audit_policy": policy}


# ═══════════════════════════════════════════════════════════
# DRIFT DETECTION MODE
# ═══════════════════════════════════════════════════════════

