"""
Enterprise Autonomous Engine — Unified Closed-Loop Build + QA + DevOps Pipeline.

Orchestrates ALL existing platform systems into a single pipeline with hard PASS/FAIL gates:
  1. Tests Gate        — Playwright E2E + backend pytest
  2. Validation Gate   — Platform Health + Code Health + Auth/Role + Schema
  3. Performance Gate  — Performance Guardian budgets (hard enforced)
  4. E2E Gate          — Critical Journey Monitor probe
  5. Visual Gate       — Lighthouse audit + Responsiveness audit
  6. Self-Heal Loop    — If ANY gate fails: diagnose → fix → re-test (max 3 cycles)

Standardized output:  STATUS / TESTS / PERFORMANCE / VALIDATION / E2E / VISUAL = PASS | FAIL
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from utils.email_service import ops_alert_template_enforcer

router = APIRouter(prefix="/admin/autonomous-engine", tags=["Enterprise Autonomous Engine"])

# ─── Constants ───
MAX_HEAL_CYCLES = 3
DEFAULT_PERF_THRESHOLDS = {
    "initial_load_s": 2.5,
    "api_response_ms": 300,
    "bundle_size_kb": 250,
    "lighthouse_score": 90,
}
GATE_NAMES = ["tests", "coverage", "validation", "performance", "e2e", "visual", "deployment"]
MANDATORY_GATES = {"tests", "coverage"}


@ops_alert_template_enforcer("monitoring", "monitoring_anomaly_alert")
async def _send_monitoring_alert_email(**kwargs):
    from utils.email_service import send_email

    return await send_email(**kwargs)


DEFAULT_COVERAGE_POLICY = {
    "global_minimum_pct": 15,
    "critical_minimum_pct": 95,
    "critical_modules": [
        "agent_framework/catalog.py",
        "agent_framework/catalog_expansion.py",
    ],
    "fail_on_drop": True,
    "fail_on_missing_tests": True,
}
DEFAULT_DEPLOYMENT_POLICY = {
    "load_concurrent_users": 20,
    "load_duration_seconds": 10,
    "stress_burst_size": 50,
    "max_avg_response_ms": 5000,
    "max_error_rate_pct": 5,
    "max_degradation_factor": 3.0,
    "degradation_min_avg_ms": 250,
    "target_endpoints": [
        "/api/health",
        "/api/auth/sso-config",
        "/api/features/registry",
        "/api/system/vanity-metrics",
    ],
    "require_full_pipeline_pass": True,
    "require_email_v2_inheritance_pass": True,
}
EMAIL_V2_INHERITANCE_TEST_PATH = "/app/backend/tests/test_email_v2_inheritance.py"
EMAIL_V2_INHERITANCE_SOURCE_FILES = [
    EMAIL_V2_INHERITANCE_TEST_PATH,
    "/app/backend/utils/email_service.py",
]
DEFAULT_DRIFT_POLICY = {
    "enabled": True,
    "baseline_mode": "dual",
    "rolling_pass_window": 5,
    "performance_drift_pct": 20.0,
    "tests_passed_drop_pct": 5.0,
    "recent_pass_rate_floor_pct": 80.0,
    "auto_optimize": True,
    "revalidate_after_optimize": True,
    "max_history": 250,
}
DEFAULT_FEEDBACK_LOOP_POLICY = {
    "enabled": True,
    "analyze_window_hours": 24,
    "min_route_views_for_detection": 8,
    "min_route_exits_for_dropoff": 5,
    "dropoff_threshold_pct": 55.0,
    "slow_interaction_threshold_ms": 1200,
    "slow_interaction_count_threshold": 5,
    "error_count_threshold": 4,
    "interaction_bounce_ms": 20000,
    "auto_create_tasks": True,
    "auto_run_pipeline_on_high_severity": True,
    "high_severity_score_threshold": 80,
    "max_event_history": 10000,
    "max_task_history": 250,
}
DEFAULT_PREDICTIVE_POLICY = {
    "enabled": True,
    "analyze_window_hours": 72,
    "min_pattern_occurrences": 3,
    "confidence_threshold": 75,
    "auto_preemptive_fix": True,
    "run_validation_after_fix": True,
    "scheduler_enabled": True,
    "scheduled_interval_minutes": 30,
    "max_history": 250,
    "signal_sources": {
        "failure_memory": True,
        "drift_history": True,
        "monitor_anomalies": True,
        "pipeline_runs": True,
        "feedback_loop": True,
    },
}
DEFAULT_ZERO_TRUST_AUTOMATION_POLICY = {
    "enabled": True,
    "trigger_mode": "both",  # continuous | threshold | both
    "interval_minutes": 10,
    "threshold_levels": ["high", "critical"],
    "safety_level": "auto_low_medium_queue_high",  # auto_all | auto_low_medium_queue_high | dry_run
    "enable_active_mitigation": True,
    "enable_autofix_runs": True,
    "enable_pipeline_rerun": True,
    "anomaly_window_minutes": 30,
    "max_actions_per_run": 20,
    "max_history": 500,
}
DEFAULT_ZERO_TRUST_DAILY_EMAIL_POLICY = {
    "enabled": True,
    "send_hour_utc": 9,
    "send_minute_utc": 0,
    "recipient_mode": "all_admins",  # all_admins | specific
    "recipient_emails": [],
    "detail_level": "executive",  # executive | detailed
    "max_history": 365,
}
DEFAULT_ACTIVE_DEFENSE_NIGHTLY_POLICY = {
    "enabled": True,
    "scan_hour_utc": 3,
    "scan_minute_utc": 0,
    "auto_block_on_fail": True,
    "send_email_report": True,
    "recipient_mode": "all_admins",
    "recipient_emails": [],
    "max_history": 365,
}
DEFAULT_DRIFT_ALERT_CONFIG = {
    "enabled": False,
    "slack_webhook_url": "",
    "teams_webhook_url": "",
    "alert_min_severity": "high",
}
DEFAULT_SYSTEM_MEMORY_POLICY = {
    "enabled": True,
    "require_lookup_before_task": True,
    "lookup_top_k": 3,
    "min_confidence_score": 0.55,
    "auto_capture_failures": True,
    "auto_capture_fixes": True,
    "auto_capture_optimizations": True,
    "auto_capture_test_patterns": True,
    "max_memory_entries": 5000,
}


def _normalize_zero_trust_daily_email_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = {**DEFAULT_ZERO_TRUST_DAILY_EMAIL_POLICY, **(policy or {})}
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["send_hour_utc"] = max(0, min(23, int(merged.get("send_hour_utc", 9))))
    merged["send_minute_utc"] = max(0, min(59, int(merged.get("send_minute_utc", 0))))

    recipient_mode = str(merged.get("recipient_mode") or "all_admins").strip().lower()
    if recipient_mode not in {"all_admins", "specific"}:
        recipient_mode = "all_admins"
    merged["recipient_mode"] = recipient_mode

    raw_emails = merged.get("recipient_emails") or []
    if not isinstance(raw_emails, list):
        raw_emails = []
    normalized_emails: List[str] = []
    for email in raw_emails:
        value = str(email or "").strip().lower()
        if value and "@" in value and value not in normalized_emails:
            normalized_emails.append(value)
    merged["recipient_emails"] = normalized_emails[:100]

    detail_level = str(merged.get("detail_level") or "executive").strip().lower()
    if detail_level not in {"executive", "detailed"}:
        detail_level = "executive"
    merged["detail_level"] = detail_level

    merged["max_history"] = max(30, min(1000, int(merged.get("max_history", 365))))
    return merged
DEFAULT_REALITY_VALIDATION_POLICY = {
    "enabled": True,
    "default_window_hours": 24,
    "max_window_hours": 168,
    "auto_refresh_seconds": 30,
    "required_categories": [
        "real_world_scenarios",
        "negative_testing",
        "ux_quality",
        "regression",
        "independent_validation",
    ],
    "required_evidence": [
        "api_logs",
        "latency_metrics",
        "screenshots",
        "error_logs",
    ],
    "required_confidence": "HIGH",
    "mandatory_scenarios": [
        "authentication_tests",
        "network_failure_simulation",
        "core_user_flow",
        "negative_testing",
        "data_consistency_checks",
        "responsiveness_checks",
        "performance_under_load",
        "regression_scenarios",
    ],
    "required_for_every_task": True,
    "required_for_every_release": True,
    "max_history": 500,
}
DEFAULT_TEST_GATE_SUITE = "/app/backend/tests/test_autonomous_tests_gate_mandatory.py"
COVERAGE_GATE_TEST_SUITES = [
    DEFAULT_TEST_GATE_SUITE,
    EMAIL_V2_INHERITANCE_TEST_PATH,
]
COVERAGE_GATE_COV_TARGETS = [
    "--cov=agent_framework",
    "--cov=utils/email_templates.py",
    "--cov=utils/email_service.py",
    "--cov=routes/careers_offers.py",
]


# ─── DB helper ───


async def _db():
    from server import db
    return db


async def _require_admin(request: Request):
    from routes.db import require_auth
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ─── Configuration ───


async def _get_engine_config() -> dict:
    db = await _db()
    doc = await db.autonomous_engine_config.find_one({"config_id": "global"}, {"_id": 0})
    if not doc:
        doc = {
            "config_id": "global",
            "enabled": True,
            "max_heal_cycles": MAX_HEAL_CYCLES,
            "gates_enabled": {g: True for g in GATE_NAMES},
            "performance_thresholds": DEFAULT_PERF_THRESHOLDS,
            "auto_heal_enabled": True,
            "strict_hard_gate": True,
            "require_recent_pass_minutes": 240,
            "mandatory_gates": sorted(list(MANDATORY_GATES)),
            "notify_on_fail": True,
            "notify_on_pass": False,
            "drift_detection_policy": {**DEFAULT_DRIFT_POLICY},
            "feedback_loop_policy": {**DEFAULT_FEEDBACK_LOOP_POLICY},
            "predictive_policy": {**DEFAULT_PREDICTIVE_POLICY},
            "zero_trust_policy": {**DEFAULT_ZERO_TRUST_AUTOMATION_POLICY},
            "zero_trust_daily_email_policy": {**DEFAULT_ZERO_TRUST_DAILY_EMAIL_POLICY},
            "active_defense_nightly_policy": {**DEFAULT_ACTIVE_DEFENSE_NIGHTLY_POLICY},
            "system_memory_policy": {**DEFAULT_SYSTEM_MEMORY_POLICY},
        }
        await db.autonomous_engine_config.insert_one(doc)
    else:
        if "strict_hard_gate" not in doc:
            doc["strict_hard_gate"] = True
        if "require_recent_pass_minutes" not in doc:
            doc["require_recent_pass_minutes"] = 240
        if "drift_detection_policy" not in doc:
            doc["drift_detection_policy"] = {**DEFAULT_DRIFT_POLICY}
        if "feedback_loop_policy" not in doc:
            doc["feedback_loop_policy"] = {**DEFAULT_FEEDBACK_LOOP_POLICY}
        if "predictive_policy" not in doc:
            doc["predictive_policy"] = {**DEFAULT_PREDICTIVE_POLICY}
        if "zero_trust_policy" not in doc:
            doc["zero_trust_policy"] = {**DEFAULT_ZERO_TRUST_AUTOMATION_POLICY}
        if "zero_trust_daily_email_policy" not in doc:
            doc["zero_trust_daily_email_policy"] = {**DEFAULT_ZERO_TRUST_DAILY_EMAIL_POLICY}
        if "system_memory_policy" not in doc:
            doc["system_memory_policy"] = {**DEFAULT_SYSTEM_MEMORY_POLICY}
    gates_enabled = doc.get("gates_enabled") or {g: True for g in GATE_NAMES}
    for gate_name in MANDATORY_GATES:
        gates_enabled[gate_name] = True
    doc["gates_enabled"] = gates_enabled
    doc["mandatory_gates"] = sorted(list(MANDATORY_GATES))
    drift_policy = {**DEFAULT_DRIFT_POLICY, **(doc.get("drift_detection_policy") or {})}
    drift_policy["baseline_mode"] = str(drift_policy.get("baseline_mode") or "dual").lower()
    if drift_policy["baseline_mode"] not in {"locked", "rolling", "dual"}:
        drift_policy["baseline_mode"] = "dual"
    try:
        drift_policy["rolling_pass_window"] = max(3, min(20, int(drift_policy.get("rolling_pass_window", 5))))
    except Exception:
        drift_policy["rolling_pass_window"] = 5
    drift_policy["performance_drift_pct"] = max(1.0, float(drift_policy.get("performance_drift_pct", 20.0)))
    drift_policy["tests_passed_drop_pct"] = max(1.0, float(drift_policy.get("tests_passed_drop_pct", 5.0)))
    drift_policy["recent_pass_rate_floor_pct"] = max(1.0, min(100.0, float(drift_policy.get("recent_pass_rate_floor_pct", 80.0))))
    drift_policy["max_history"] = max(50, min(1000, int(drift_policy.get("max_history", 250))))
    drift_policy["enabled"] = bool(drift_policy.get("enabled", True))
    drift_policy["auto_optimize"] = bool(drift_policy.get("auto_optimize", True))
    drift_policy["revalidate_after_optimize"] = bool(drift_policy.get("revalidate_after_optimize", True))
    doc["drift_detection_policy"] = drift_policy
    feedback_policy = {**DEFAULT_FEEDBACK_LOOP_POLICY, **(doc.get("feedback_loop_policy") or {})}
    feedback_policy["enabled"] = bool(feedback_policy.get("enabled", True))
    feedback_policy["analyze_window_hours"] = max(1, min(168, int(feedback_policy.get("analyze_window_hours", 24))))
    feedback_policy["min_route_views_for_detection"] = max(1, min(1000, int(feedback_policy.get("min_route_views_for_detection", 8))))
    feedback_policy["min_route_exits_for_dropoff"] = max(1, min(1000, int(feedback_policy.get("min_route_exits_for_dropoff", 5))))
    feedback_policy["dropoff_threshold_pct"] = max(1.0, min(100.0, float(feedback_policy.get("dropoff_threshold_pct", 55.0))))
    feedback_policy["slow_interaction_threshold_ms"] = max(50, int(feedback_policy.get("slow_interaction_threshold_ms", 1200)))
    feedback_policy["slow_interaction_count_threshold"] = max(1, min(1000, int(feedback_policy.get("slow_interaction_count_threshold", 5))))
    feedback_policy["error_count_threshold"] = max(1, min(1000, int(feedback_policy.get("error_count_threshold", 4))))
    feedback_policy["interaction_bounce_ms"] = max(1000, int(feedback_policy.get("interaction_bounce_ms", 20000)))
    feedback_policy["auto_create_tasks"] = bool(feedback_policy.get("auto_create_tasks", True))
    feedback_policy["auto_run_pipeline_on_high_severity"] = bool(feedback_policy.get("auto_run_pipeline_on_high_severity", True))
    feedback_policy["high_severity_score_threshold"] = max(1, min(100, int(feedback_policy.get("high_severity_score_threshold", 80))))
    feedback_policy["max_event_history"] = max(100, min(50000, int(feedback_policy.get("max_event_history", 10000))))
    feedback_policy["max_task_history"] = max(10, min(2000, int(feedback_policy.get("max_task_history", 250))))
    doc["feedback_loop_policy"] = feedback_policy
    predictive_policy = {**DEFAULT_PREDICTIVE_POLICY, **(doc.get("predictive_policy") or {})}
    predictive_policy["enabled"] = bool(predictive_policy.get("enabled", True))
    predictive_policy["analyze_window_hours"] = max(1, min(24 * 30, int(predictive_policy.get("analyze_window_hours", 72))))
    predictive_policy["min_pattern_occurrences"] = max(1, min(50, int(predictive_policy.get("min_pattern_occurrences", 3))))
    predictive_policy["confidence_threshold"] = max(1, min(99, int(predictive_policy.get("confidence_threshold", 75))))
    predictive_policy["auto_preemptive_fix"] = bool(predictive_policy.get("auto_preemptive_fix", True))
    predictive_policy["run_validation_after_fix"] = bool(predictive_policy.get("run_validation_after_fix", True))
    predictive_policy["scheduler_enabled"] = bool(predictive_policy.get("scheduler_enabled", True))
    predictive_policy["scheduled_interval_minutes"] = max(
        5,
        min(1440, int(predictive_policy.get("scheduled_interval_minutes", 30))),
    )
    predictive_policy["max_history"] = max(50, min(5000, int(predictive_policy.get("max_history", 250))))
    sources = {**DEFAULT_PREDICTIVE_POLICY.get("signal_sources", {}), **(predictive_policy.get("signal_sources") or {})}
    predictive_policy["signal_sources"] = {
        "failure_memory": bool(sources.get("failure_memory", True)),
        "drift_history": bool(sources.get("drift_history", True)),
        "monitor_anomalies": bool(sources.get("monitor_anomalies", True)),
        "pipeline_runs": bool(sources.get("pipeline_runs", True)),
        "feedback_loop": bool(sources.get("feedback_loop", True)),
    }
    doc["predictive_policy"] = predictive_policy
    zero_trust_policy = {**DEFAULT_ZERO_TRUST_AUTOMATION_POLICY, **(doc.get("zero_trust_policy") or {})}
    zero_trust_policy["enabled"] = bool(zero_trust_policy.get("enabled", True))
    trigger_mode = str(zero_trust_policy.get("trigger_mode") or "both").strip().lower()
    if trigger_mode not in {"continuous", "threshold", "both"}:
        trigger_mode = "both"
    zero_trust_policy["trigger_mode"] = trigger_mode
    zero_trust_policy["interval_minutes"] = max(5, min(60, int(zero_trust_policy.get("interval_minutes", 10))))
    levels = zero_trust_policy.get("threshold_levels") or ["high", "critical"]
    allowed_levels = ["low", "medium", "high", "critical"]
    normalized_levels = [str(level).lower() for level in levels if str(level).lower() in allowed_levels]
    if not normalized_levels:
        normalized_levels = ["high", "critical"]
    zero_trust_policy["threshold_levels"] = list(dict.fromkeys(normalized_levels))
    safety_level = str(zero_trust_policy.get("safety_level") or "auto_low_medium_queue_high").strip().lower()
    if safety_level not in {"auto_all", "auto_low_medium_queue_high", "dry_run"}:
        safety_level = "auto_low_medium_queue_high"
    zero_trust_policy["safety_level"] = safety_level
    zero_trust_policy["enable_active_mitigation"] = bool(zero_trust_policy.get("enable_active_mitigation", True))
    zero_trust_policy["enable_autofix_runs"] = bool(zero_trust_policy.get("enable_autofix_runs", True))
    zero_trust_policy["enable_pipeline_rerun"] = bool(zero_trust_policy.get("enable_pipeline_rerun", True))
    zero_trust_policy["anomaly_window_minutes"] = max(5, min(120, int(zero_trust_policy.get("anomaly_window_minutes", 30))))
    zero_trust_policy["max_actions_per_run"] = max(1, min(200, int(zero_trust_policy.get("max_actions_per_run", 20))))
    zero_trust_policy["max_history"] = max(50, min(5000, int(zero_trust_policy.get("max_history", 500))))
    doc["zero_trust_policy"] = zero_trust_policy
    doc["zero_trust_daily_email_policy"] = _normalize_zero_trust_daily_email_policy(
        doc.get("zero_trust_daily_email_policy")
    )
    system_memory_policy = {**DEFAULT_SYSTEM_MEMORY_POLICY, **(doc.get("system_memory_policy") or {})}
    system_memory_policy["enabled"] = bool(system_memory_policy.get("enabled", True))
    system_memory_policy["require_lookup_before_task"] = bool(system_memory_policy.get("require_lookup_before_task", True))
    system_memory_policy["lookup_top_k"] = max(1, min(10, int(system_memory_policy.get("lookup_top_k", 3))))
    system_memory_policy["min_confidence_score"] = max(0.0, min(1.0, float(system_memory_policy.get("min_confidence_score", 0.55))))
    system_memory_policy["auto_capture_failures"] = bool(system_memory_policy.get("auto_capture_failures", True))
    system_memory_policy["auto_capture_fixes"] = bool(system_memory_policy.get("auto_capture_fixes", True))
    system_memory_policy["auto_capture_optimizations"] = bool(system_memory_policy.get("auto_capture_optimizations", True))
    system_memory_policy["auto_capture_test_patterns"] = bool(system_memory_policy.get("auto_capture_test_patterns", True))
    system_memory_policy["max_memory_entries"] = max(200, min(20000, int(system_memory_policy.get("max_memory_entries", 5000))))
    doc["system_memory_policy"] = system_memory_policy
    return doc


async def _save_engine_config(config: dict):
    db = await _db()
    config.pop("_id", None)
    await db.autonomous_engine_config.update_one(
        {"config_id": "global"}, {"$set": config}, upsert=True
    )


def _safe_read_json_file(path: str) -> dict:
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _tail_file_lines(path: str, max_lines: int = 300) -> List[str]:
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-max_lines:]]
    except Exception:
        return []


def _recent_evidence_files(hours: int, limit: int = 20) -> List[Dict[str, Any]]:
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff_ts = now_ts - (max(1, int(hours)) * 3600)
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    roots = [
        "/root/.emergent/automation_output",
        "/app/.screenshots",
        "/tmp",
    ]

    files: List[Dict[str, Any]] = []
    seen_files = 0
    max_scan_files = 1200

    for root in roots:
        if not os.path.exists(root):
            continue
        try:
            for base, _, names in os.walk(root):
                if len(files) >= limit * 2 or seen_files >= max_scan_files:
                    break
                for name in names:
                    seen_files += 1
                    if seen_files >= max_scan_files:
                        break
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in exts:
                        continue
                    fp = os.path.join(base, name)
                    try:
                        mtime = os.path.getmtime(fp)
                    except Exception:
                        continue
                    if mtime < cutoff_ts:
                        continue
                    files.append(
                        {
                            "path": fp,
                            "modified_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                        }
                    )
                if len(files) >= limit * 2 or seen_files >= max_scan_files:
                    break
        except Exception:
            continue

    files.sort(key=lambda x: x.get("modified_at", ""), reverse=True)
    return files[:limit]


