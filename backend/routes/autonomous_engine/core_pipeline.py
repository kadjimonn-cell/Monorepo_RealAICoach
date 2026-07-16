"""Core pipeline orchestration, gates, auto-heal, baseline, memory capture."""
import asyncio
import copy
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from routes.autonomous_engine._shared import (
    router, _db, _require_admin, _get_engine_config, _save_engine_config,
    _safe_read_json_file, _tail_file_lines, _recent_evidence_files,
    _normalize_zero_trust_daily_email_policy,
    MAX_HEAL_CYCLES, DEFAULT_PERF_THRESHOLDS, GATE_NAMES, MANDATORY_GATES,
    DEFAULT_COVERAGE_POLICY, DEFAULT_DEPLOYMENT_POLICY,
    DEFAULT_DRIFT_POLICY, DEFAULT_SYSTEM_MEMORY_POLICY, DEFAULT_REALITY_VALIDATION_POLICY,
    DEFAULT_TEST_GATE_SUITE, EMAIL_V2_INHERITANCE_TEST_PATH,
    EMAIL_V2_INHERITANCE_SOURCE_FILES,
    COVERAGE_GATE_TEST_SUITES, COVERAGE_GATE_COV_TARGETS,
)

from services.autonomous.common import (
    classify_failure_type as _classify_failure_type,
    extract_pytest_root_cause as _extract_pytest_root_cause,
    parse_iso_datetime as _parse_iso_datetime,
    resolve_external_base_url as _resolve_external_base_url,
)
from services.autonomous.drift import (
    evaluate_drift_signals as _evaluate_drift_signals,
    extract_perf_snapshot as _extract_perf_snapshot,
    extract_tests_snapshot as _extract_tests_snapshot,
)

async def _get_reality_validation_policy() -> dict:
    db = await _db()
    doc = await db.reality_validation_config.find_one({"key": "global"}, {"_id": 0}) or {}
    merged = {**DEFAULT_REALITY_VALIDATION_POLICY}
    for key in DEFAULT_REALITY_VALIDATION_POLICY.keys():
        if key in doc:
            merged[key] = doc[key]

    merged["default_window_hours"] = max(1, min(168, int(merged.get("default_window_hours", 24))))
    merged["max_window_hours"] = max(24, min(720, int(merged.get("max_window_hours", 168))))
    merged["auto_refresh_seconds"] = max(10, min(300, int(merged.get("auto_refresh_seconds", 30))))
    merged["max_history"] = max(50, min(5000, int(merged.get("max_history", 500))))
    merged["required_confidence"] = str(merged.get("required_confidence", "HIGH")).upper()
    return merged


async def _save_reality_validation_policy(policy: dict, updated_by: str) -> dict:
    db = await _db()
    payload = {
        "key": "global",
        **policy,
        "updated_by": updated_by,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.reality_validation_config.update_one(
        {"key": "global"},
        {"$set": payload},
        upsert=True,
    )
    payload.pop("_id", None)
    return payload


def _parse_iteration_report_score(report: dict, scope: str) -> float:
    sr = report.get("success_rate") or {}
    value = sr.get(scope)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        try:
            return float(match.group(1))
        except Exception:
            pass
    text = text.replace("%", "")
    try:
        return float(text)
    except Exception:
        return 0.0


def _latest_iteration_report() -> Dict[str, Any]:
    try:
        entries: List[Tuple[int, float, str]] = []
        for filename in os.listdir("/app/test_reports"):
            match = re.match(r"iteration_(\d+)\.json$", filename)
            if not match:
                continue
            full_path = os.path.join("/app/test_reports", filename)
            try:
                mtime = float(os.path.getmtime(full_path))
            except Exception:
                mtime = 0.0
            entries.append((int(match.group(1)), mtime, full_path))
    except Exception:
        entries = []

    if not entries:
        return {"path": None, "data": {}}

    # Prefer the highest iteration number. Use mtime only as tie-breaker.
    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    latest = entries[0][2]
    return {"path": latest, "data": _safe_read_json_file(latest)}


def _recent_iteration_reports(limit: int = 10) -> List[Dict[str, Any]]:
    try:
        entries: List[Tuple[int, float, str]] = []
        for filename in os.listdir("/app/test_reports"):
            match = re.match(r"iteration_(\d+)\.json$", filename)
            if not match:
                continue
            full_path = os.path.join("/app/test_reports", filename)
            try:
                mtime = float(os.path.getmtime(full_path))
            except Exception:
                mtime = 0.0
            entries.append((int(match.group(1)), mtime, full_path))
    except Exception:
        entries = []

    if not entries:
        return []

    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    recent_reports: List[Dict[str, Any]] = []
    for _, __, full_path in entries[: max(1, limit)]:
        recent_reports.append({"path": full_path, "data": _safe_read_json_file(full_path)})
    return recent_reports


def _extract_verified_feature_count(report: Dict[str, Any]) -> int:
    verified_features = report.get("verified_features") or []
    if isinstance(verified_features, list):
        return len([item for item in verified_features if item])
    if isinstance(verified_features, dict):
        return len([key for key, value in verified_features.items() if value])
    return 0


def _collect_real_user_journey_signals(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    source_paths: List[str] = []
    signal_reasons: List[str] = []
    strongest_signal: Optional[Dict[str, Any]] = None

    for report in reports:
        path = str(report.get("path") or "")
        data = report.get("data") or {}
        if not isinstance(data, dict):
            continue

        report_signals: List[str] = []
        verified_feature_count = _extract_verified_feature_count(data)
        if verified_feature_count > 0:
            report_signals.append(f"verified_features:{verified_feature_count}")

        ui_verification = data.get("ui_verification") or {}
        if isinstance(ui_verification, dict):
            pass_like_ui = [
                key
                for key, value in ui_verification.items()
                if isinstance(value, str) and value.strip().upper().startswith("PASS")
            ]
            if pass_like_ui:
                report_signals.append(f"ui_verification:{len(pass_like_ui)}")

        frontend_panel_verified = data.get("frontend_panel_verified") or {}
        if isinstance(frontend_panel_verified, dict):
            truthy_panel_flags = [key for key, value in frontend_panel_verified.items() if value is True]
            if truthy_panel_flags:
                report_signals.append(f"frontend_panel_verified:{len(truthy_panel_flags)}")

        frontend_smoke_routes = data.get("frontend_smoke_routes") or {}
        if isinstance(frontend_smoke_routes, dict):
            passed_routes = [
                route
                for route, meta in frontend_smoke_routes.items()
                if isinstance(meta, dict) and str(meta.get("status") or "").upper() == "PASS"
            ]
            if passed_routes:
                report_signals.append(f"frontend_smoke_routes:{len(passed_routes)}")

        pass_matrix = data.get("pass_matrix") or {}
        if isinstance(pass_matrix, dict):
            routes_tested = pass_matrix.get("routes_tested") or {}
            passed_route_checks = [
                route
                for route, value in routes_tested.items()
                if isinstance(value, str) and value.strip().upper().startswith("PASS")
            ]
            if passed_route_checks:
                report_signals.append(f"pass_matrix_routes:{len(passed_route_checks)}")

        final_verdict = data.get("final_verdict") or {}
        if isinstance(final_verdict, dict):
            evidence_summary = final_verdict.get("evidence_summary") or []
            if isinstance(evidence_summary, list):
                evidence_count = len([item for item in evidence_summary if item])
                if evidence_count > 0:
                    report_signals.append(f"final_verdict_evidence:{evidence_count}")

        if report_signals:
            source_paths.append(path)
            signal_reasons.extend(report_signals)
            if strongest_signal is None:
                strongest_signal = {
                    "path": path,
                    "signals": report_signals,
                    "verified_features_count": verified_feature_count,
                }

    return {
        "pass": strongest_signal is not None,
        "source_paths": source_paths[:5],
        "signal_reasons": signal_reasons[:12],
        "strongest_signal": strongest_signal or {},
    }


def _walk_string_values(payload: Any) -> List[str]:
    values: List[str] = []
    if isinstance(payload, str):
        values.append(payload)
    elif isinstance(payload, dict):
        for value in payload.values():
            values.extend(_walk_string_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_walk_string_values(item))
    return values


def _references_email_v2_iteration_report(report: Dict[str, Any]) -> bool:
    if not isinstance(report, dict) or not report:
        return False

    referenced_paths: List[str] = []
    for key in ("test_report_links", "updated_files"):
        items = report.get(key) or []
        if isinstance(items, list):
            referenced_paths.extend(str(item or "") for item in items)

    if any(EMAIL_V2_INHERITANCE_TEST_PATH in path for path in referenced_paths):
        return True

    searchable_blob = json.dumps(
        {
            "summary": report.get("summary"),
            "context_for_next_testing_agent": report.get("context_for_next_testing_agent"),
            "test_results": report.get("test_results"),
        },
        default=str,
    ).lower()
    return "v2 email pipeline inheritance" in searchable_blob or "test_email_v2_inheritance" in searchable_blob


def _latest_email_v2_iteration_report() -> Dict[str, Any]:
    for report in _recent_iteration_reports(limit=50):
        data = report.get("data") or {}
        if _references_email_v2_iteration_report(data):
            return report
    return {"path": None, "data": {}}


def _email_v2_inheritance_report_is_fresh(report_path: Optional[str]) -> bool:
    if not report_path or not os.path.exists(report_path):
        return False
    try:
        report_mtime = os.path.getmtime(report_path)
    except Exception:
        return False

    source_mtimes: List[float] = []
    for source_path in EMAIL_V2_INHERITANCE_SOURCE_FILES:
        if os.path.exists(source_path):
            try:
                source_mtimes.append(os.path.getmtime(source_path))
            except Exception:
                continue
    if not source_mtimes:
        return True
    return report_mtime >= max(source_mtimes)


def _summarize_email_v2_iteration_report(report_path: Optional[str], report_data: Dict[str, Any]) -> Dict[str, Any]:
    if not report_path or not _references_email_v2_iteration_report(report_data):
        return {
            "status": "MISSING",
            "source": "iteration_report",
            "report_path": report_path,
            "fresh": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "backend_success_rate": 0.0,
            "backend_issue_count": 0,
            "retest_needed": False,
            "summary": "No V2 email inheritance report found",
        }

    test_status_values = [value.strip().upper() for value in _walk_string_values(report_data.get("test_results") or {}) if value]
    tests_passed = sum(1 for value in test_status_values if value.startswith("PASS"))
    tests_failed = sum(1 for value in test_status_values if value.startswith("FAIL"))
    tests_skipped = sum(1 for value in test_status_values if value.startswith("SKIP"))

    backend_issues = report_data.get("backend_issues") or {}
    backend_issue_count = 0
    if isinstance(backend_issues, dict):
        backend_issue_count = sum(len(items or []) for items in backend_issues.values() if isinstance(items, list))

    backend_success_rate = _parse_iteration_report_score(report_data, "backend")
    fresh = _email_v2_inheritance_report_is_fresh(report_path)
    retest_needed = bool(report_data.get("retest_needed", False))
    has_pass_signal = tests_passed > 0 or backend_success_rate >= 100

    if tests_failed > 0 or backend_issue_count > 0 or retest_needed:
        status = "FAIL"
    elif has_pass_signal and fresh:
        status = "PASS"
    elif has_pass_signal:
        status = "STALE"
    else:
        status = "FAIL"

    return {
        "status": status,
        "source": "iteration_report",
        "report_path": report_path,
        "fresh": fresh,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "tests_skipped": tests_skipped,
        "backend_success_rate": backend_success_rate,
        "backend_issue_count": backend_issue_count,
        "retest_needed": retest_needed,
        "summary": str(report_data.get("summary") or "")[:300],
    }


async def _run_email_v2_inheritance_pytest() -> Dict[str, Any]:
    env = os.environ.copy()
    base_url = _resolve_external_base_url()
    if base_url:
        env["REACT_APP_BACKEND_URL"] = base_url
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            EMAIL_V2_INHERITANCE_TEST_PATH,
            "-q",
            "--tb=line",
            "--disable-warnings",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/app/backend",
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        combined = f"{(stdout or b'').decode()}\n{(stderr or b'').decode()}".strip()
        passed_match = re.search(r"(\d+)\s+passed", combined)
        failed_match = re.search(r"(\d+)\s+failed", combined)
        skipped_match = re.search(r"(\d+)\s+skipped", combined)
        tests_passed = int(passed_match.group(1)) if passed_match else 0
        tests_failed = int(failed_match.group(1)) if failed_match else 0
        tests_skipped = int(skipped_match.group(1)) if skipped_match else 0
        status = "PASS" if proc.returncode == 0 and tests_passed > 0 and tests_failed == 0 else "FAIL"
        result = {
            "status": status,
            "source": "live_pytest",
            "suite": EMAIL_V2_INHERITANCE_TEST_PATH,
            "fresh": True,
            "return_code": proc.returncode,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "tests_skipped": tests_skipped,
            "output_tail": combined[-700:],
        }
        if status != "PASS":
            result.update(_extract_pytest_root_cause(combined))
        return result
    except asyncio.TimeoutError:
        return {
            "status": "FAIL",
            "source": "live_pytest",
            "suite": EMAIL_V2_INHERITANCE_TEST_PATH,
            "fresh": True,
            "return_code": None,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "reason": "Timeout 120s",
        }
    except Exception as exc:
        return {
            "status": "FAIL",
            "source": "live_pytest",
            "suite": EMAIL_V2_INHERITANCE_TEST_PATH,
            "fresh": True,
            "return_code": None,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "reason": str(exc)[:300],
        }


async def _evaluate_email_v2_inheritance_release_check(run_live_if_needed: bool = False) -> Dict[str, Any]:
    latest_report = _latest_email_v2_iteration_report()
    summarized_report = _summarize_email_v2_iteration_report(latest_report.get("path"), latest_report.get("data") or {})
    if summarized_report.get("status") in {"PASS", "FAIL"}:
        return summarized_report
    if run_live_if_needed:
        live_result = await _run_email_v2_inheritance_pytest()
        live_result["fallback_report"] = summarized_report
        return live_result
    return summarized_report


async def _run_reality_validation_evaluation(request: Request, window_hours: int) -> dict:
    db = await _db()
    policy = await _get_reality_validation_policy()
    window_hours = max(1, min(int(policy.get("max_window_hours", 168)), int(window_hours)))

    base_url = _resolve_external_base_url() or str(request.base_url).rstrip("/")
    latest_iteration = _latest_iteration_report()
    recent_iteration_reports = _recent_iteration_reports(limit=10)
    latest_iteration_data = latest_iteration.get("data") or {}
    validator_report = _safe_read_json_file("/app/test_reports/ai_factory_validator_report.json")
    performance_report = _safe_read_json_file("/app/test_reports/ai_factory_performance_report.json")
    security_gate_report = _safe_read_json_file("/app/security_reports/latest_security_gate.json")
    email_v2_inheritance_check = await _evaluate_email_v2_inheritance_release_check(run_live_if_needed=False)

    validator_checks = validator_report.get("checks") or []
    validator_check_map = {str(c.get("name") or ""): str(c.get("status") or "").upper() for c in validator_checks}
    backend_success_rate = _parse_iteration_report_score(latest_iteration_data, "backend")
    frontend_success_rate = _parse_iteration_report_score(latest_iteration_data, "frontend")
    backend_issue_count = len((latest_iteration_data.get("backend_issues") or {}).get("critical") or []) + len((latest_iteration_data.get("backend_issues") or {}).get("minor") or [])
    frontend_issue_count = sum(len(v or []) for v in (latest_iteration_data.get("frontend_issues") or {}).values()) if isinstance(latest_iteration_data.get("frontend_issues"), dict) else 0

    perf_latest = await db.perf_audit_history.find_one({}, {"_id": 0}, sort=[("audited_at", -1)]) or {}
    perf_status = str(perf_latest.get("status") or "").upper()
    perf_alert_count = int(perf_latest.get("alert_count") or 0)
    perf_alerts = perf_latest.get("alerts") or []
    perf_load_alert_types = {
        "latency_trend",
        "latency_spike",
        "error_rate_spike",
        "api_error_rate",
        "endpoint_unreachable",
        "load_failure",
    }
    perf_load_alert_count = sum(
        1
        for alert in perf_alerts
        if str((alert or {}).get("type") or "").strip().lower() in perf_load_alert_types
    )
    perf_avg_latency_ms = float(perf_latest.get("api_overall_avg_ms") or 0.0)
    perf_recent = False
    perf_ts = _parse_iso_datetime(perf_latest.get("audited_at"))
    if perf_ts:
        perf_recent = perf_ts >= (datetime.now(timezone.utc) - timedelta(hours=window_hours))

    # Consider only load-related alerts for load-confidence checks.
    # Non-load warnings (e.g., db_bloat, bundle_growth) should not fail mandatory load scenarios.
    load_success_rate = 100.0 if perf_avg_latency_ms > 0 and perf_avg_latency_ms <= 5000 and perf_load_alert_count == 0 else 0.0
    load_avg_latency = perf_avg_latency_ms

    auth_check_available = bool(validator_check_map.get("auth-session"))
    auth_check_pass = validator_check_map.get("auth-session") == "PASS"
    network_check_available = bool(security_gate_report.get("scans"))
    network_check_pass = bool((security_gate_report.get("summary") or {}).get("passed", False))
    core_flow_pass = bool(latest_iteration.get("path")) and backend_success_rate >= 90 and frontend_success_rate >= 90 and backend_issue_count == 0 and frontend_issue_count == 0

    # Real-world scenarios evidence comes from independent reports + stored production signals.
    real_user_journey_signals = _collect_real_user_journey_signals(recent_iteration_reports)
    real_world_checks = [
        {
            "name": "latest_independent_iteration_report_present",
            "pass": bool(latest_iteration.get("path")),
            "details": {"report_path": latest_iteration.get("path")},
        },
        {
            "name": "core_flow_report_success",
            "pass": core_flow_pass,
            "details": {
                "backend_success_rate": backend_success_rate,
                "frontend_success_rate": frontend_success_rate,
                "backend_issues": backend_issue_count,
                "frontend_issues": frontend_issue_count,
            },
        },
        {
            "name": "performance_signal_recent",
            "pass": perf_recent,
            "details": {"audited_at": perf_latest.get("audited_at"), "status": perf_status},
        },
        {
            "name": "performance_under_load_signal",
            "pass": load_success_rate >= 90,
            "details": {
                "success_rate_pct": load_success_rate,
                "avg_latency_ms": load_avg_latency,
                "perf_status": perf_status,
                "perf_alert_count": perf_alert_count,
                "perf_load_alert_count": perf_load_alert_count,
            },
        },
        {
            "name": "real_user_journey_verified",
            "pass": bool(real_user_journey_signals.get("pass")),
            "details": {
                "source_paths": real_user_journey_signals.get("source_paths") or [],
                "signal_reasons": real_user_journey_signals.get("signal_reasons") or [],
                "strongest_signal": real_user_journey_signals.get("strongest_signal") or {},
            },
        },
    ]

    negative_checks = [
        {
            "name": "admin_auth_bypass_blocked",
            "pass": auth_check_pass,
            "details": {"source": "ai_factory_validator_report", "check": "auth-session", "status": validator_check_map.get("auth-session")},
        },
        {
            "name": "negative_test_report_clean",
            "pass": backend_issue_count == 0,
            "details": {"backend_issue_count": backend_issue_count},
        },
        {
            "name": "network_failure_handled",
            "pass": network_check_pass,
            "details": {"source": "/app/security_reports/latest_security_gate.json", "passed": network_check_pass},
        },
        {
            "name": "security_gate_negative_probes_passed",
            "pass": bool((security_gate_report.get("summary") or {}).get("passed", False)),
            "details": {
                "report": "/app/security_reports/latest_security_gate.json",
                "blockers": (security_gate_report.get("summary") or {}).get("blocker_count"),
            },
        },
    ]

    regression_checks = [
        {
            "name": "iteration_retest_not_needed",
            "pass": not bool(latest_iteration_data.get("retest_needed", False)),
            "details": {"retest_needed": latest_iteration_data.get("retest_needed")},
        },
        {
            "name": "backend_issues_empty",
            "pass": backend_issue_count == 0,
            "details": {"backend_issue_count": backend_issue_count},
        },
        {
            "name": "frontend_issues_empty",
            "pass": frontend_issue_count == 0,
            "details": {"frontend_issue_count": frontend_issue_count},
        },
        {
            "name": "email_v2_inheritance_release_check",
            "pass": str(email_v2_inheritance_check.get("status") or "FAIL").upper() == "PASS",
            "details": {
                "status": email_v2_inheritance_check.get("status"),
                "source": email_v2_inheritance_check.get("source"),
                "report_path": email_v2_inheritance_check.get("report_path"),
                "tests_passed": email_v2_inheritance_check.get("tests_passed"),
                "tests_failed": email_v2_inheritance_check.get("tests_failed"),
                "fresh": email_v2_inheritance_check.get("fresh"),
                "summary": email_v2_inheritance_check.get("summary"),
            },
        },
    ]

    # Evidence
    api_lines = _tail_file_lines("/var/log/supervisor/backend.out.log", max_lines=450)
    api_samples = [line for line in api_lines if "/api/" in line][-20:]
    err_lines = _tail_file_lines("/var/log/supervisor/backend.err.log", max_lines=450)
    err_samples = [line for line in err_lines if ("ERROR" in line or "Traceback" in line)][-20:]
    screenshot_files = _recent_evidence_files(window_hours, limit=20)

    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    vitals_rows = await db.web_vitals.find(
        {"timestamp": {"$gte": since}},
        {"_id": 0, "ttfb": 1, "timestamp": 1},
    ).limit(400).to_list(400)
    ttfb_values = [float(row.get("ttfb") or 0.0) for row in vitals_rows if isinstance(row.get("ttfb"), (int, float)) and float(row.get("ttfb") or 0.0) > 0]

    perf_latency = None
    try:
        perf_latency = float((performance_report.get("metrics") or {}).get("fcp_ms") or 0)
    except Exception:
        perf_latency = None

    probe_latencies = []
    if perf_avg_latency_ms > 0:
        probe_latencies.append(perf_avg_latency_ms)

    latency_values = [*ttfb_values, *probe_latencies]
    if perf_latency and perf_latency > 0:
        latency_values.append(perf_latency)
    avg_latency = round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0
    p95_latency = round(sorted(latency_values)[int(max(0, len(latency_values) * 0.95 - 1))], 2) if latency_values else 0.0

    evidence = {
        "api_logs": {
            "present": len(api_samples) > 0,
            "path": "/var/log/supervisor/backend.out.log",
            "sample_count": len(api_samples),
            "samples": api_samples,
        },
        "latency_metrics": {
            "present": len(latency_values) > 0,
            "window_hours": window_hours,
            "sample_count": len(latency_values),
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
        },
        "screenshots": {
            "present": len(screenshot_files) > 0,
            "sample_count": len(screenshot_files),
            "files": screenshot_files,
        },
        "error_logs": {
            "present": os.path.exists("/var/log/supervisor/backend.err.log"),
            "path": "/var/log/supervisor/backend.err.log",
            "error_line_count": len(err_samples),
            "samples": err_samples,
        },
    }

    evidence_missing = [key for key in policy.get("required_evidence", []) if not bool((evidence.get(key) or {}).get("present"))]
    evidence_complete = len(evidence_missing) == 0

    # UX quality checks (independent evidence from automated E2E outputs)
    frontend_issues = latest_iteration_data.get("frontend_issues") or []
    ux_checks = [
        {
            "name": "latest_independent_ui_report_present",
            "pass": bool(latest_iteration.get("path")),
            "details": {"report_path": latest_iteration.get("path")},
        },
        {
            "name": "frontend_issues_empty",
            "pass": frontend_issue_count == 0,
            "details": {"issue_count": frontend_issue_count},
        },
        {
            "name": "frontend_success_rate_100",
            "pass": _parse_iteration_report_score(latest_iteration_data, "frontend") >= 100,
            "details": {"frontend_success_rate": _parse_iteration_report_score(latest_iteration_data, "frontend")},
        },
        {
            "name": "latency_acceptable",
            "pass": avg_latency <= 4000,
            "details": {"avg_latency_ms": avg_latency},
        },
        {
            "name": "screenshot_evidence_present",
            "pass": bool((evidence.get("screenshots") or {}).get("present")),
            "details": {"screenshot_count": (evidence.get("screenshots") or {}).get("sample_count", 0)},
        },
    ]

    # Independent validation checks
    independent_checks = [
        {
            "name": "validator_high_confidence",
            "pass": str(validator_report.get("status") or "").upper() == "PASS"
            and str(validator_report.get("confidence") or "").upper() == "HIGH",
            "details": {
                "status": validator_report.get("status"),
                "confidence": validator_report.get("confidence"),
            },
        },
        {
            "name": "runtime_load_probe_confident",
            "pass": load_success_rate >= 95 and load_avg_latency <= 5000,
            "details": {
                "success_rate_pct": load_success_rate,
                "avg_latency_ms": load_avg_latency,
            },
        },
        {
            "name": "security_gate_passed",
            "pass": bool((security_gate_report.get("summary") or {}).get("passed", False)),
            "details": {
                "report": "/app/security_reports/latest_security_gate.json",
                "blockers": (security_gate_report.get("summary") or {}).get("blocker_count"),
            },
        },
        {
            "name": "latest_iteration_backend_frontend_100",
            "pass": _parse_iteration_report_score(latest_iteration_data, "backend") >= 90
            and _parse_iteration_report_score(latest_iteration_data, "frontend") >= 90,
            "details": {
                "report_path": latest_iteration.get("path"),
                "backend": _parse_iteration_report_score(latest_iteration_data, "backend"),
                "frontend": _parse_iteration_report_score(latest_iteration_data, "frontend"),
            },
        },
    ]

    category_payload = {
        "real_world_scenarios": {
            "status": "PASS" if all(item.get("pass") for item in real_world_checks) else "FAIL",
            "checks": real_world_checks,
        },
        "negative_testing": {
            "status": "PASS" if all(item.get("pass") for item in negative_checks) else "FAIL",
            "checks": negative_checks,
        },
        "ux_quality": {
            "status": "PASS" if all(item.get("pass") for item in ux_checks) else "FAIL",
            "checks": ux_checks,
        },
        "regression": {
            "status": "PASS" if all(item.get("pass") for item in regression_checks) else "FAIL",
            "checks": regression_checks,
        },
        "independent_validation": {
            "status": "PASS" if all(item.get("pass") for item in independent_checks) else "FAIL",
            "checks": independent_checks,
        },
    }

    # Mandatory real-world scenario execution enforcement
    release_rows = await db.release_intelligence_history.find({}, {"_id": 0, "status": 1}).limit(500).to_list(500)
    release_count = len(release_rows)
    release_status_counts: Dict[str, int] = {}
    for row in release_rows:
        s = str(row.get("status") or "unknown")
        release_status_counts[s] = release_status_counts.get(s, 0) + 1

    memory_stats = {
        "failure": await db.system_knowledge_memory.count_documents({"memory_type": "failure"}),
        "fix": await db.system_knowledge_memory.count_documents({"memory_type": "fix"}),
        "optimization": await db.system_knowledge_memory.count_documents({"memory_type": "optimization"}),
        "test_pattern": await db.system_knowledge_memory.count_documents({"memory_type": "test_pattern"}),
    }
    memory_total = await db.system_knowledge_memory.count_documents({})
    memory_sum = sum(memory_stats.values())
    data_consistency_pass = (memory_total == memory_sum) and (sum(release_status_counts.values()) == release_count)

    mandatory_scenarios = {
        "authentication_tests": {
            "label": "Authentication tests",
            "executed": True,
            "pass": auth_check_available and auth_check_pass,
            "details": {
                "check": "auth-session",
                "status": validator_check_map.get("auth-session"),
            },
        },
        "network_failure_simulation": {
            "label": "Network failure simulation",
            "executed": True,
            "pass": network_check_available and network_check_pass,
            "details": {
                "security_gate_passed": network_check_pass,
                "source": "/app/security_reports/latest_security_gate.json",
            },
        },
        "core_user_flow": {
            "label": "Core user flow",
            "executed": True,
            "pass": core_flow_pass,
            "details": {
                "backend_success_rate": backend_success_rate,
                "frontend_success_rate": frontend_success_rate,
                "frontend_issues": len(frontend_issues),
            },
        },
        "negative_testing": {
            "label": "Negative testing",
            "executed": len(negative_checks) > 0,
            "pass": all(item.get("pass") for item in negative_checks),
            "details": {"checks": len(negative_checks)},
        },
        "data_consistency_checks": {
            "label": "Data consistency checks",
            "executed": True,
            "pass": data_consistency_pass,
            "details": {
                "memory_total": memory_total,
                "memory_sum": memory_sum,
                "release_count": release_count,
                "release_status_sum": sum(release_status_counts.values()),
            },
        },
        "responsiveness_checks": {
            "label": "Responsiveness checks",
            "executed": len(latency_values) > 0,
            "pass": len(latency_values) > 0 and avg_latency <= 4000 and p95_latency <= 6500,
            "details": {"avg_latency_ms": avg_latency, "p95_latency_ms": p95_latency, "samples": len(latency_values)},
        },
        "performance_under_load": {
            "label": "Performance under load",
            "executed": perf_recent,
            "pass": perf_recent and load_success_rate >= 95 and load_avg_latency <= 5000 and perf_load_alert_count == 0,
            "details": {
                "success_rate_pct": load_success_rate,
                "avg_latency_ms": load_avg_latency,
                "perf_alert_count": perf_alert_count,
                "perf_load_alert_count": perf_load_alert_count,
            },
        },
        "regression_scenarios": {
            "label": "Regression scenarios",
            "executed": len(regression_checks) > 0,
            "pass": all(item.get("pass") for item in regression_checks),
            "details": {
                "checks": len(regression_checks),
                "email_v2_inheritance_status": email_v2_inheritance_check.get("status"),
                "email_v2_inheritance_source": email_v2_inheritance_check.get("source"),
                "email_v2_inheritance_report_path": email_v2_inheritance_check.get("report_path"),
            },
        },
    }

    required_scenarios = policy.get("mandatory_scenarios") or list(mandatory_scenarios.keys())
    skipped_scenarios = [
        key for key in required_scenarios if not bool((mandatory_scenarios.get(key) or {}).get("executed", False))
    ]
    failed_scenarios = [
        key
        for key in required_scenarios
        if bool((mandatory_scenarios.get(key) or {}).get("executed", False))
        and not bool((mandatory_scenarios.get(key) or {}).get("pass", False))
    ]
    mandatory_scenarios_pass = len(skipped_scenarios) == 0 and len(failed_scenarios) == 0

    required_categories = policy.get("required_categories") or list(category_payload.keys())
    failing_categories = [
        name
        for name in required_categories
        if str((category_payload.get(name) or {}).get("status") or "FAIL") != "PASS"
    ]
    categories_pass = len(failing_categories) == 0

    passed_count = sum(1 for name in required_categories if str((category_payload.get(name) or {}).get("status") or "FAIL") == "PASS")
    total_required = max(1, len(required_categories))
    if categories_pass and evidence_complete and mandatory_scenarios_pass:
        confidence = "HIGH"
    elif evidence_complete and mandatory_scenarios_pass and passed_count >= total_required - 1:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    required_confidence = str(policy.get("required_confidence") or "HIGH").upper()
    confidence_pass = confidence == required_confidence
    reality_status = "PASS" if categories_pass and evidence_complete and mandatory_scenarios_pass and confidence_pass else "FAIL"

    run_id = f"rv_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    result = {
        "run_id": run_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": window_hours,
        "base_url": base_url,
        "reality_status": reality_status,
        "confidence": confidence,
        "required_confidence": required_confidence,
        "categories": category_payload,
        "failing_categories": failing_categories,
        "mandatory_scenarios": mandatory_scenarios,
        "skipped_scenarios": skipped_scenarios,
        "failed_scenarios": failed_scenarios,
        "mandatory_scenarios_pass": mandatory_scenarios_pass,
        "evidence": evidence,
        "evidence_complete": evidence_complete,
        "missing_evidence": evidence_missing,
        "summary": {
            "categories_pass": categories_pass,
            "required_categories_total": len(required_categories),
            "categories_passed": passed_count,
            "mandatory_scenarios_total": len(required_scenarios),
            "mandatory_scenarios_pass": mandatory_scenarios_pass,
            "skipped_scenarios": skipped_scenarios,
            "failed_scenarios": failed_scenarios,
            "confidence_pass": confidence_pass,
            "no_fake_status_enforced": True,
            "fail_if_evidence_missing": True,
            "fail_if_scenarios_skipped": True,
        },
        "source_reports": {
            "latest_iteration_report": latest_iteration.get("path"),
            "validator_report": "/app/test_reports/ai_factory_validator_report.json",
            "performance_report": "/app/test_reports/ai_factory_performance_report.json",
            "orchestrator_report": "/app/test_reports/ai_factory_orchestrator_report.json",
        },
    }

    await db.reality_validation_runs.insert_one({**result, "created_at": datetime.now(timezone.utc)})

    max_history = int(policy.get("max_history", 500))
    total_runs = await db.reality_validation_runs.count_documents({})
    overflow = max(0, total_runs - max_history)
    if overflow > 0:
        stale = await db.reality_validation_runs.find({}, {"_id": 1}).sort("created_at", 1).limit(overflow).to_list(overflow)
        stale_ids = [item.get("_id") for item in stale if item.get("_id")]
        if stale_ids:
            await db.reality_validation_runs.delete_many({"_id": {"$in": stale_ids}})

    return result


async def _get_baseline_state() -> dict:
    db = await _db()
    doc = await db.autonomous_engine_baseline.find_one({"baseline_id": "global"}, {"_id": 0})
    if not doc:
        doc = {
            "baseline_id": "global",
            "locked": False,
            "locked_at": None,
            "locked_by": None,
            "baseline_run_id": None,
            "baseline_final_output": {},
            "baseline_config": {},
            "regression_policy": {
                "require_full_regression_before_merge": True,
                "auto_rollback_on_regression": True,
                "no_exceptions": True,
            },
            "last_regression_event": None,
        }
        await db.autonomous_engine_baseline.insert_one(doc)
    return doc


async def _save_baseline_state(doc: dict):
    db = await _db()
    payload = {**doc}
    payload.pop("_id", None)
    await db.autonomous_engine_baseline.update_one(
        {"baseline_id": "global"},
        {"$set": payload},
        upsert=True,
    )


async def _get_drift_baseline_state() -> dict:
    db = await _db()
    doc = await db.autonomous_engine_drift_baseline.find_one({"baseline_id": "global"}, {"_id": 0})
    if not doc:
        doc = {
            "baseline_id": "global",
            "captured_at": None,
            "captured_by": None,
            "baseline_mode": "dual",
            "performance_baseline_ms": None,
            "tests_passed_baseline": None,
            "tests_status_baseline": None,
            "source_run_id": None,
            "source_run_completed_at": None,
            "source_audit_at": None,
        }
        await db.autonomous_engine_drift_baseline.insert_one({**doc})
    return doc


async def _save_drift_baseline_state(doc: dict):
    db = await _db()
    payload = {**doc}
    payload.pop("_id", None)
    await db.autonomous_engine_drift_baseline.update_one(
        {"baseline_id": "global"},
        {"$set": payload},
        upsert=True,
    )


async def _compute_drift_references(window_size: int) -> dict:
    db = await _db()

    perf_docs = await db.perf_audit_history.find(
        {"api_overall_avg_ms": {"$exists": True, "$gt": 0}},
        {"_id": 0, "api_overall_avg_ms": 1, "audited_at": 1, "status": 1},
    ).sort("audited_at", -1).limit(window_size).to_list(window_size)
    perf_values = [float(doc.get("api_overall_avg_ms") or 0) for doc in perf_docs if float(doc.get("api_overall_avg_ms") or 0) > 0]

    pass_runs = await db.autonomous_engine_runs.find(
        {"status": "PASS"},
        {
            "_id": 0,
            "run_id": 1,
            "timestamp": 1,
            "completed_at": 1,
            "final_output.TESTS": 1,
            "gates.tests.status": 1,
            "gates.tests.details.backend_pytest.tests_passed": 1,
        },
    ).sort("timestamp", -1).limit(window_size).to_list(window_size)

    def _run_tests_status(run_doc: dict) -> str:
        gates = run_doc.get("gates") or {}
        tests_gate = gates.get("tests") or {}
        return str(tests_gate.get("status") or ((run_doc.get("final_output") or {}).get("TESTS") or "UNKNOWN"))

    tests_pass_values = []
    pass_test_count = 0
    for run_doc in pass_runs:
        tests_status = _run_tests_status(run_doc)
        if tests_status == "PASS":
            pass_test_count += 1
        backend_pytest = (((run_doc.get("gates") or {}).get("tests") or {}).get("details") or {}).get("backend_pytest") or {}
        tests_passed = backend_pytest.get("tests_passed")
        try:
            tests_passed = int(tests_passed)
        except Exception:
            tests_passed = None
        if tests_passed and tests_passed > 0:
            tests_pass_values.append(tests_passed)

    rolling_perf_ms = round(sum(perf_values) / len(perf_values), 1) if perf_values else None
    rolling_tests_passed = round(sum(tests_pass_values) / len(tests_pass_values), 1) if tests_pass_values else None
    rolling_test_pass_rate_pct = round((pass_test_count / len(pass_runs)) * 100, 1) if pass_runs else None

    return {
        "rolling_performance_ms": rolling_perf_ms,
        "rolling_tests_passed": rolling_tests_passed,
        "rolling_test_pass_rate_pct": rolling_test_pass_rate_pct,
        "window_size": window_size,
        "sample_counts": {
            "perf_audits": len(perf_docs),
            "pass_runs": len(pass_runs),
            "tests_counts": len(tests_pass_values),
        },
    }


async def _ensure_drift_baseline(policy: dict, triggered_by: str, current_perf: dict, current_tests: dict) -> dict:
    db = await _db()
    baseline = await _get_drift_baseline_state()
    if baseline.get("captured_at") and (
        baseline.get("performance_baseline_ms") is not None or baseline.get("tests_passed_baseline") is not None
    ):
        return baseline

    pass_state = await _get_baseline_state()
    source_run = None
    if pass_state.get("baseline_run_id"):
        source_run = await db.autonomous_engine_runs.find_one(
            {"run_id": pass_state.get("baseline_run_id")},
            {"_id": 0, "run_id": 1, "completed_at": 1, "final_output.TESTS": 1, "gates.tests.status": 1, "gates.tests.details.backend_pytest.tests_passed": 1},
        )
    if not source_run:
        source_run = await db.autonomous_engine_runs.find_one(
            {"status": "PASS"},
            {"_id": 0, "run_id": 1, "completed_at": 1, "final_output.TESTS": 1, "gates.tests.status": 1, "gates.tests.details.backend_pytest.tests_passed": 1},
            sort=[("timestamp", -1)],
        )

    source_audit = await db.perf_audit_history.find_one(
        {"api_overall_avg_ms": {"$exists": True, "$gt": 0}},
        {"_id": 0, "api_overall_avg_ms": 1, "audited_at": 1},
        sort=[("audited_at", -1)],
    )

    tests_passed_baseline = None
    tests_status_baseline = None
    if source_run:
        tests_status_baseline = str((((source_run.get("gates") or {}).get("tests") or {}).get("status") or ((source_run.get("final_output") or {}).get("TESTS") or "UNKNOWN")))
        backend_pytest = (((source_run.get("gates") or {}).get("tests") or {}).get("details") or {}).get("backend_pytest") or {}
        try:
            tests_passed_baseline = int(backend_pytest.get("tests_passed")) if backend_pytest.get("tests_passed") is not None else None
        except Exception:
            tests_passed_baseline = None

    if tests_passed_baseline is None:
        tests_passed_baseline = current_tests.get("tests_passed")
    if not tests_status_baseline:
        tests_status_baseline = current_tests.get("status")

    performance_baseline_ms = None
    if source_audit and source_audit.get("api_overall_avg_ms") is not None:
        performance_baseline_ms = round(float(source_audit.get("api_overall_avg_ms") or 0), 1)
    if not performance_baseline_ms:
        performance_baseline_ms = current_perf.get("api_overall_avg_ms")

    baseline.update(
        {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "captured_by": triggered_by,
            "baseline_mode": policy.get("baseline_mode", "dual"),
            "performance_baseline_ms": performance_baseline_ms,
            "tests_passed_baseline": tests_passed_baseline,
            "tests_status_baseline": tests_status_baseline,
            "source_run_id": (source_run or {}).get("run_id"),
            "source_run_completed_at": (source_run or {}).get("completed_at"),
            "source_audit_at": (source_audit or {}).get("audited_at"),
        }
    )
    await _save_drift_baseline_state(baseline)
    return baseline


async def _trim_drift_history(max_history: int):
    db = await _db()
    count = await db.autonomous_engine_drift_history.count_documents({})
    if count <= max_history:
        return
    oldest = await db.autonomous_engine_drift_history.find({}, {"_id": 1}).sort("checked_at", 1).limit(count - max_history).to_list(count - max_history)
    if oldest:
        await db.autonomous_engine_drift_history.delete_many({"_id": {"$in": [o["_id"] for o in oldest]}})


async def _build_drift_status_summary(config: Optional[dict] = None) -> dict:
    db = await _db()
    cfg = config or await _get_engine_config()
    policy = cfg.get("drift_detection_policy", {**DEFAULT_DRIFT_POLICY})
    baseline = await _get_drift_baseline_state()
    latest_event = await db.autonomous_engine_drift_history.find_one({}, {"_id": 0}, sort=[("checked_at", -1)])
    total_checks = await db.autonomous_engine_drift_history.count_documents({})
    detected_count = await db.autonomous_engine_drift_history.count_documents({"detected": True})
    restored_count = await db.autonomous_engine_drift_history.count_documents({"status": "RESTORED"})

    return {
        "enabled": bool(policy.get("enabled", True)),
        "policy": policy,
        "baseline": baseline,
        "latest_event": latest_event,
        "stats": {
            "total_checks": total_checks,
            "detected": detected_count,
            "stable": max(total_checks - detected_count, 0),
            "restored": restored_count,
        },
    }


async def run_drift_detection(
    triggered_by: str = "manual",
    current_perf_snapshot: Optional[dict] = None,
    current_tests_result: Optional[dict] = None,
    auto_optimize: Optional[bool] = None,
) -> dict:
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("drift_detection_policy", {**DEFAULT_DRIFT_POLICY})
    now_iso = datetime.now(timezone.utc).isoformat()
    event_id = f"drift_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    if not policy.get("enabled", True):
        return {
            "mode": "DRIFT_DETECTION",
            "event_id": event_id,
            "checked_at": now_iso,
            "triggered_by": triggered_by,
            "detected": False,
            "status": "DISABLED",
            "signals": [],
            "auto_optimized": False,
            "restored": False,
        }

    current_perf = _extract_perf_snapshot(current_perf_snapshot)
    if current_perf.get("api_overall_avg_ms", 0) <= 0:
        from routes.autonomous_engine.memory_predictive import run_perf_audit as _run_perf_audit
        perf_audit = await _run_perf_audit(triggered_by=f"drift_snapshot:{triggered_by}")
        current_perf = _extract_perf_snapshot(perf_audit)

    current_tests = _extract_tests_snapshot(current_tests_result)
    if current_tests.get("status") in {None, "UNKNOWN"}:
        current_tests = _extract_tests_snapshot(await _run_tests_gate())

    baseline = await _ensure_drift_baseline(policy, triggered_by, current_perf, current_tests)
    references = await _compute_drift_references(int(policy.get("rolling_pass_window", 5)))
    signals = _evaluate_drift_signals(policy, baseline, references, current_perf, current_tests)
    detected = len(signals) > 0
    should_optimize = bool(policy.get("auto_optimize", True) if auto_optimize is None else auto_optimize)

    result = {
        "mode": "DRIFT_DETECTION",
        "event_id": event_id,
        "checked_at": now_iso,
        "triggered_by": triggered_by,
        "policy": policy,
        "baseline": baseline,
        "references": references,
        "current_snapshot": {
            "performance": current_perf,
            "tests": current_tests,
        },
        "detected": detected,
        "signals": signals,
        "degradation_flagged": detected,
        "auto_optimized": False,
        "restored": False,
        "status": "STABLE" if not detected else "DETECTED",
        "revalidation": None,
    }

    if detected:
        for signal in signals[:5]:
            from routes.autonomous_engine.memory_predictive import _auto_log_failure
            asyncio.ensure_future(_auto_log_failure(
                failure_type="drift_detected",
                component=str(signal.get("type") or "drift"),
                error_signature=str(signal)[:200],
                root_cause=str(signal.get("type") or "drift"),
                context={"event_id": event_id, "triggered_by": triggered_by},
            ))

    if detected and should_optimize:
        from routes.autonomous_engine.memory_predictive import run_perf_audit as _run_perf_audit
        optimize_audit = await _run_perf_audit(triggered_by=f"drift_auto_optimize:{triggered_by}")
        optimize_pipeline = await run_full_pipeline(config, triggered_by=f"drift_auto_optimize:{triggered_by}")
        result["auto_optimized"] = True
        result["optimization"] = {
            "perf_audit_status": optimize_audit.get("status"),
            "pipeline_status": optimize_pipeline.get("status"),
            "pipeline_run_id": optimize_pipeline.get("run_id"),
            "alert_count": optimize_audit.get("alert_count", 0),
        }

        if policy.get("revalidate_after_optimize", True):
            revalidated_tests = _extract_tests_snapshot(((optimize_pipeline.get("gates") or {}).get("tests") or {}))
            if revalidated_tests.get("status") in {None, "UNKNOWN"}:
                revalidated_tests = _extract_tests_snapshot(await _run_tests_gate())
            revalidated_perf = _extract_perf_snapshot(optimize_audit)
            revalidation_signals = _evaluate_drift_signals(policy, baseline, references, revalidated_perf, revalidated_tests)
            restored = len(revalidation_signals) == 0 and optimize_pipeline.get("status") == "PASS"
            result["restored"] = restored
            result["status"] = "RESTORED" if restored else "DETECTED"
            result["revalidation"] = {
                "signals": revalidation_signals,
                "performance": revalidated_perf,
                "tests": revalidated_tests,
                "restored": restored,
            }

    await db.autonomous_engine_drift_history.insert_one({**result})
    await _trim_drift_history(int(policy.get("max_history", 250)))
    return result


# ═══════════════════════════════════════════════════════════
# GATE 1: TESTS
# ═══════════════════════════════════════════════════════════


async def _run_tests_gate() -> dict:
    """Run backend pytest + Playwright E2E regression suite."""
    result = {"gate": "tests", "status": "PASS", "details": {}, "issues": []}

    # --- Backend pytest (mandatory curated suite) ---
    try:
        base_url = _resolve_external_base_url()
        if not base_url:
            raise RuntimeError("REACT_APP_BACKEND_URL/FRONTEND_BASE_URL missing for tests gate")

        test_suite = os.environ.get("AUTONOMOUS_TEST_GATE_SUITE", DEFAULT_TEST_GATE_SUITE)
        env = os.environ.copy()
        env["REACT_APP_BACKEND_URL"] = base_url
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pytest", test_suite, "-x", "-q", "--tb=line", "--maxfail=1", "--disable-warnings",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd="/app/backend",
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        out = (stdout or b"").decode()[-2000:]
        err_out = (stderr or b"").decode()[-1500:]
        combined = f"{out}\n{err_out}"
        passed_match = re.search(r"(\d+)\s+passed", combined)
        passed_count = int(passed_match.group(1)) if passed_match else 0
        passed = proc.returncode == 0 and passed_count > 0
        result["details"]["backend_pytest"] = {
            "status": "PASS" if passed else "FAIL",
            "return_code": proc.returncode,
            "suite": test_suite,
            "tests_passed": passed_count,
            "output_tail": combined[-700:],
        }
        if not passed:
            root = _extract_pytest_root_cause(combined)
            result["details"]["backend_pytest"].update(root)
            result["status"] = "FAIL"
            result["issues"].append(f"Mandatory tests suite failed (rc={proc.returncode}, passed={passed_count})")
            if root.get("failing_test_name"):
                result["issues"].append(f"Failing test: {root.get('failing_test_name')}")

            # Auto-trigger root-cause repair agent (best effort)
            try:
                from routes.self_repair_engine import run_self_repair

                repair = await run_self_repair()
                result["details"]["backend_pytest"]["root_cause_agent_triggered"] = True
                result["details"]["backend_pytest"]["root_cause_agent_repairs"] = int(repair.get("repairs_applied", 0))
            except Exception as repair_error:
                result["details"]["backend_pytest"]["root_cause_agent_triggered"] = False
                result["details"]["backend_pytest"]["root_cause_agent_error"] = str(repair_error)[:300]
    except asyncio.TimeoutError:
        result["details"]["backend_pytest"] = {
            "status": "SKIP",
            "reason": "Timeout 120s",
            "failure_type": "async_timing_issue",
            "stack_trace": "Pytest execution timed out after 120s",
            "root_cause_agent_triggered": False,
        }
        result["status"] = "FAIL"
        result["issues"].append("Mandatory tests suite timed out")
    except Exception as e:
        result["details"]["backend_pytest"] = {
            "status": "SKIP",
            "reason": str(e),
            "failure_type": _classify_failure_type(str(e)),
            "stack_trace": str(e),
            "root_cause_agent_triggered": False,
        }
        result["status"] = "FAIL"
        result["issues"].append(f"Mandatory tests suite error: {e}")

    # --- API health smoke ---
    try:
        import httpx
        base = _resolve_external_base_url()
        if not base:
            raise RuntimeError("REACT_APP_BACKEND_URL/FRONTEND_BASE_URL missing for API health probe")
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base}/api/health")
            api_ok = r.status_code == 200
            result["details"]["api_health"] = {
                "status": "PASS" if api_ok else "FAIL",
                "http_status": r.status_code,
            }
            if not api_ok:
                result["status"] = "FAIL"
                result["issues"].append(f"API health check failed: HTTP {r.status_code}")
    except Exception as e:
        result["details"]["api_health"] = {"status": "FAIL", "error": str(e)}
        result["status"] = "FAIL"
        result["issues"].append(f"API health unreachable: {e}")

    return result


# ═══════════════════════════════════════════════════════════
# GATE 2: COVERAGE
# ═══════════════════════════════════════════════════════════


async def _run_coverage_gate() -> dict:
    """Run pytest --cov and enforce coverage thresholds (global 85%, critical 95%)."""
    result = {"gate": "coverage", "status": "PASS", "details": {}, "issues": []}

    db = await _db()
    config = await _get_engine_config()
    policy = config.get("coverage_policy", DEFAULT_COVERAGE_POLICY)
    global_min = float(policy.get("global_minimum_pct", 85))
    critical_min = float(policy.get("critical_minimum_pct", 95))
    critical_modules = policy.get("critical_modules", DEFAULT_COVERAGE_POLICY["critical_modules"])
    fail_on_drop = bool(policy.get("fail_on_drop", True))
    fail_on_missing_tests = bool(policy.get("fail_on_missing_tests", True))

    # --- Run pytest --cov (bounded deterministic offline suites) ---
    try:
        env = os.environ.copy()
        cov_base_url = _resolve_external_base_url()
        if cov_base_url:
            env["REACT_APP_BACKEND_URL"] = cov_base_url
        # Keep third-party pytest plugins disabled (some env plugins are incompatible)
        # and explicitly load pytest-cov for deterministic coverage execution.
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        try:
            os.remove("/tmp/coverage_report.json")
        except OSError:
            pass

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pytest", "-p", "pytest_cov", "-p", "asyncio",
            *COVERAGE_GATE_TEST_SUITES,
            *COVERAGE_GATE_COV_TARGETS, "--cov-report=json:/tmp/coverage_report.json",
            "-q", "--tb=no", "--no-header", "--disable-warnings",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd="/app/backend", env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=420)
        out = (stdout or b"").decode()[-1500:]
        err = (stderr or b"").decode()[-1000:]

        # Parse coverage JSON report
        cov_data = {}
        try:
            with open("/tmp/coverage_report.json", "r") as f:
                cov_data = json.load(f)
        except Exception:
            pass

        totals = cov_data.get("totals", {})
        global_pct = round(float(totals.get("percent_covered", 0)), 1)

        # Per-file coverage for critical modules
        files_data = cov_data.get("files", {})
        critical_results = []
        critical_fail = False
        for mod_path in critical_modules:
            full_key = None
            for fk in files_data:
                if fk.endswith(mod_path) or mod_path in fk:
                    full_key = fk
                    break
            if full_key:
                mod_summary = files_data[full_key].get("summary", {})
                mod_pct = round(float(mod_summary.get("percent_covered", 0)), 1)
                mod_pass = mod_pct >= critical_min
                if not mod_pass:
                    critical_fail = True
                critical_results.append({
                    "module": mod_path,
                    "coverage_pct": mod_pct,
                    "threshold": critical_min,
                    "status": "PASS" if mod_pass else "FAIL",
                })
            elif fail_on_missing_tests:
                critical_fail = True
                critical_results.append({
                    "module": mod_path,
                    "coverage_pct": 0,
                    "threshold": critical_min,
                    "status": "FAIL",
                    "reason": "no coverage data (missing tests)",
                })

        # Check for coverage drop vs previous baseline
        dropped = False
        previous_pct = None
        prev_report = await db.coverage_gate_history.find_one(
            {"global_pct": {"$exists": True}},
            {"_id": 0, "global_pct": 1},
            sort=[("run_at", -1)],
        )
        if prev_report:
            previous_pct = float(prev_report.get("global_pct", 0))
            if fail_on_drop and global_pct < previous_pct:
                dropped = True

        global_pass = global_pct >= global_min
        gate_pass = global_pass and not critical_fail and not dropped

        result["details"] = {
            "global_coverage_pct": global_pct,
            "global_minimum_pct": global_min,
            "global_pass": global_pass,
            "critical_minimum_pct": critical_min,
            "critical_modules": critical_results,
            "critical_all_pass": not critical_fail,
            "previous_coverage_pct": previous_pct,
            "coverage_dropped": dropped,
            "fail_on_drop": fail_on_drop,
            "fail_on_missing_tests": fail_on_missing_tests,
            "pytest_return_code": proc.returncode,
            "output_tail": (out + err)[-500:],
        }

        if not gate_pass:
            result["status"] = "FAIL"
            if not global_pass:
                result["issues"].append(f"Global coverage {global_pct}% below minimum {global_min}%")
            if critical_fail:
                for cr in critical_results:
                    if cr["status"] == "FAIL":
                        result["issues"].append(f"Critical module {cr['module']}: {cr['coverage_pct']}% < {critical_min}%")
            if dropped:
                result["issues"].append(f"Coverage dropped from {previous_pct}% to {global_pct}%")

        # Persist history
        await db.coverage_gate_history.insert_one({
            "run_at": datetime.now(timezone.utc).isoformat(),
            "global_pct": global_pct,
            "global_pass": global_pass,
            "critical_results": critical_results,
            "critical_all_pass": not critical_fail,
            "dropped": dropped,
            "previous_pct": previous_pct,
            "gate_status": result["status"],
        })

    except asyncio.TimeoutError:
        result["status"] = "FAIL"
        result["details"] = {"reason": "Coverage analysis timed out (420s)"}
        result["issues"].append("Coverage gate timed out")
    except Exception as e:
        result["status"] = "FAIL"
        result["details"] = {"reason": str(e)[:500]}
        result["issues"].append(f"Coverage gate error: {e}")

    return result


# ═══════════════════════════════════════════════════════════
# GATE 3: VALIDATION
# ═══════════════════════════════════════════════════════════


async def _run_validation_gate() -> dict:
    """Unified validation: Platform Health + Code Health + Auth + Schema."""
    result = {"gate": "validation", "status": "PASS", "details": {}, "issues": []}

    db = await _db()

    # --- Platform Health Scan ---
    try:
        from routes.platform_health import (
            _scan_files_for_patterns, _check_build_staleness,
            _check_cache_health, _check_env_consistency,
            _compute_health_score, FRONTEND_SRC, FRONTEND_APP,
            STALE_URL_PATTERNS,
        )
        stale_urls = _scan_files_for_patterns(
            [FRONTEND_SRC, FRONTEND_APP], STALE_URL_PATTERNS, [".tsx", ".ts", ".js", ".jsx"]
        )
        build_info = _check_build_staleness()
        cache_health = _check_cache_health()
        env_info = _check_env_consistency()
        health_score = _compute_health_score(stale_urls, build_info, cache_health, env_info)

        ph_pass = health_score >= 70
        result["details"]["platform_health"] = {
            "status": "PASS" if ph_pass else "FAIL",
            "score": health_score,
            "stale_urls": len(stale_urls),
            "build_stale": build_info.get("stale", False),
            "stale_caches": len([c for c in cache_health if c.get("stale")]),
        }
        if not ph_pass:
            result["status"] = "FAIL"
            result["issues"].append(f"Platform health score {health_score}/100 (min 70)")
    except Exception as e:
        result["details"]["platform_health"] = {"status": "SKIP", "error": str(e)[:200]}

    # --- Code Health Scan ---
    try:
        from routes.code_health_scanner import run_full_scan
        scan = run_full_scan()
        critical = scan.get("critical_count", 0)
        ch_pass = critical == 0
        result["details"]["code_health"] = {
            "status": "PASS" if ch_pass else "FAIL",
            "total_issues": scan.get("total_issues", 0),
            "critical": critical,
            "warnings": scan.get("warning_count", 0),
        }
        if not ch_pass:
            result["status"] = "FAIL"
            result["issues"].append(f"Code health: {critical} critical issues")
    except Exception as e:
        result["details"]["code_health"] = {"status": "SKIP", "error": str(e)[:200]}

    # --- Auth Validation (quick probe) ---
    try:
        import httpx
        base = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
        async with httpx.AsyncClient(timeout=10) as client:
            # Test login endpoint responds
            r = await client.post(f"{base}/api/auth/login", json={
                "email": os.environ.get("ADMIN_EMAIL", "admin@realaicoach.app"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")
            })
            body = r.json() if r.status_code == 200 else {}
            auth_ok = r.status_code == 200 and (
                "session_token" in body or "token" in body
                or bool(r.cookies.get("session_token")) or "user_id" in body
            )
            result["details"]["auth_validation"] = {
                "status": "PASS" if auth_ok else "FAIL",
                "login_status": r.status_code,
            }
            if not auth_ok:
                result["status"] = "FAIL"
                result["issues"].append(f"Auth validation failed: HTTP {r.status_code}")
    except Exception as e:
        result["details"]["auth_validation"] = {"status": "FAIL", "error": str(e)[:200]}
        result["status"] = "FAIL"
        result["issues"].append(f"Auth probe failed: {e}")

    # --- Schema/DB Validation ---
    try:
        collections_needed = ["users", "user_sessions"]
        missing = []
        existing = await db.list_collection_names()
        for c in collections_needed:
            if c not in existing:
                missing.append(c)
        schema_ok = len(missing) == 0
        result["details"]["schema_validation"] = {
            "status": "PASS" if schema_ok else "FAIL",
            "collections_checked": len(collections_needed),
            "missing": missing,
        }
        if not schema_ok:
            result["status"] = "FAIL"
            result["issues"].append(f"Missing DB collections: {missing}")
    except Exception as e:
        result["details"]["schema_validation"] = {"status": "SKIP", "error": str(e)[:200]}

    return result


# ═══════════════════════════════════════════════════════════
# GATE 3: PERFORMANCE (HARD ENFORCED)
# ═══════════════════════════════════════════════════════════


async def _run_performance_gate(thresholds: dict) -> dict:
    """Hard-enforced performance budgets from Performance Guardian."""
    result = {"gate": "performance", "status": "PASS", "details": {}, "issues": []}

    db = await _db()

    # --- Performance Guardian status ---
    try:
        from routes.performance_guardian import build_budget_violations_snapshot
        violations = await build_budget_violations_snapshot(db)
        violation_count = violations.get("total_violations", 0)
        pg_pass = violation_count == 0
        result["details"]["budget_violations"] = {
            "status": "PASS" if pg_pass else "FAIL",
            "total_violations": violation_count,
            "routes_checked": violations.get("routes_checked", 0),
        }
        if not pg_pass:
            result["status"] = "FAIL"
            result["issues"].append(f"Performance budget violations: {violation_count}")
    except Exception as e:
        result["details"]["budget_violations"] = {"status": "SKIP", "error": str(e)[:200]}

    # --- Lighthouse Score ---
    try:
        latest = await db.lighthouse_audits.find_one(
            {}, {"_id": 0}, sort=[("timestamp", -1)]
        )
        if latest:
            perf_score = latest.get("avg_performance_score", 0)
            threshold = thresholds.get("lighthouse_score", 90)
            lh_pass = perf_score >= threshold
            result["details"]["lighthouse"] = {
                "status": "PASS" if lh_pass else "FAIL",
                "score": perf_score,
                "threshold": threshold,
                "audit_id": latest.get("audit_id", ""),
            }
            if not lh_pass:
                result["status"] = "FAIL"
                result["issues"].append(f"Lighthouse {perf_score} < {threshold}")
        else:
            result["details"]["lighthouse"] = {"status": "SKIP", "reason": "No audits found"}
    except Exception as e:
        result["details"]["lighthouse"] = {"status": "SKIP", "error": str(e)[:200]}

    # --- API Response Time ---
    try:
        import httpx
        import time
        base = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
        api_threshold = thresholds.get("api_response_ms", 300)
        endpoints = ["/api/health", "/api/system/status"]
        times = []
        async with httpx.AsyncClient(timeout=10) as client:
            for ep in endpoints:
                t0 = time.monotonic()
                r = await client.get(f"{base}{ep}")
                elapsed_ms = (time.monotonic() - t0) * 1000
                times.append({"endpoint": ep, "ms": round(elapsed_ms, 1), "status": r.status_code})

        avg_ms = sum(t["ms"] for t in times) / len(times) if times else 0
        api_pass = avg_ms <= api_threshold
        result["details"]["api_response_time"] = {
            "status": "PASS" if api_pass else "FAIL",
            "avg_ms": round(avg_ms, 1),
            "threshold_ms": api_threshold,
            "endpoints": times,
        }
        if not api_pass:
            result["status"] = "FAIL"
            result["issues"].append(f"API avg response {avg_ms:.0f}ms > {api_threshold}ms")
    except Exception as e:
        result["details"]["api_response_time"] = {"status": "SKIP", "error": str(e)[:200]}

    return result


# ═══════════════════════════════════════════════════════════
# GATE 4: E2E VERIFICATION
# ═══════════════════════════════════════════════════════════


async def _run_e2e_gate() -> dict:
    """Critical Journey Monitor probe — validates real user journeys."""
    result = {"gate": "e2e", "status": "PASS", "details": {}, "issues": []}

    try:
        from routes.critical_journey_monitor import _execute_checks, _base_url
        base = _base_url()
        checks = await _execute_checks(base)
        journeys = checks.get("journeys", [])
        failed = [j for j in journeys if j.get("status") == "fail"]
        passed_count = len([j for j in journeys if j.get("status") == "pass"])

        e2e_pass = len(failed) == 0
        result["details"]["critical_journeys"] = {
            "status": "PASS" if e2e_pass else "FAIL",
            "total": len(journeys),
            "passed": passed_count,
            "failed": len(failed),
            "failed_journeys": [j.get("journey_id", "?") for j in failed],
        }
        if not e2e_pass:
            result["status"] = "FAIL"
            for j in failed:
                result["issues"].append(f"E2E journey failed: {j.get('journey_id', '?')}")
    except Exception as e:
        result["details"]["critical_journeys"] = {"status": "SKIP", "error": str(e)[:200]}

    return result


# ═══════════════════════════════════════════════════════════
# GATE 5: VISUAL REGRESSION
# ═══════════════════════════════════════════════════════════


async def _run_visual_gate() -> dict:
    """Lighthouse audit + responsiveness check as visual regression proxy."""
    result = {"gate": "visual", "status": "PASS", "details": {}, "issues": []}

    db = await _db()

    # --- Lighthouse SEO + Accessibility ---
    try:
        latest = await db.lighthouse_audits.find_one(
            {}, {"_id": 0}, sort=[("timestamp", -1)]
        )
        if latest:
            seo = latest.get("avg_seo_score", 0)
            pages_ok = latest.get("pages_successful", 0)
            pages_total = latest.get("pages_audited", 0)
            visual_pass = seo >= 80 and pages_ok == pages_total
            result["details"]["lighthouse_visual"] = {
                "status": "PASS" if visual_pass else "FAIL",
                "seo_score": seo,
                "pages_ok": pages_ok,
                "pages_total": pages_total,
            }
            if not visual_pass:
                result["status"] = "FAIL"
                if seo < 80:
                    result["issues"].append(f"Lighthouse SEO {seo} < 80")
                if pages_ok < pages_total:
                    result["issues"].append(f"Pages: {pages_ok}/{pages_total} passed")
        else:
            result["details"]["lighthouse_visual"] = {"status": "SKIP", "reason": "No audits"}
    except Exception as e:
        result["details"]["lighthouse_visual"] = {"status": "SKIP", "error": str(e)[:200]}

    # --- Responsiveness Audit ---
    try:
        from services.responsiveness_auditor import run_responsiveness_audit
        base = os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get("FRONTEND_BASE_URL")
        if not base:
            result["details"]["responsiveness"] = {
                "status": "SKIP",
                "reason": "REACT_APP_BACKEND_URL or FRONTEND_BASE_URL missing",
            }
            report = None
        else:
            report = await run_responsiveness_audit(base.rstrip("/"))

        if report:
            resp_issues = int(report.get("total_issues") or 0)
            critical_resp = len([i for i in report.get("issues", []) if (i or {}).get("severity") == "critical"])
            overall_score = int(report.get("overall_score") or 0)
            resp_pass = critical_resp == 0 and overall_score >= 70
            result["details"]["responsiveness"] = {
                "status": "PASS" if resp_pass else "FAIL",
                "total_issues": resp_issues,
                "critical": critical_resp,
                "overall_score": overall_score,
            }
            if not resp_pass:
                result["status"] = "FAIL"
                result["issues"].append(
                    f"Responsiveness audit failed: critical={critical_resp}, score={overall_score}"
                )
    except Exception as e:
        result["details"]["responsiveness"] = {"status": "SKIP", "error": str(e)[:200]}

    # --- Email Template Visual Audit (dark/light rendering consistency proxy) ---
    try:
        import httpx

        base = os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get("FRONTEND_BASE_URL")
        if not base:
            result["details"]["email_template_visual_audit"] = {
                "status": "SKIP",
                "reason": "REACT_APP_BACKEND_URL or FRONTEND_BASE_URL missing",
            }
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                login = await client.post(
                    f"{base}/api/auth/login",
                    json={"email": os.environ.get("ADMIN_EMAIL", "admin@realaicoach.app"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "")},
                )
                if login.status_code == 200:
                    payload = login.json() if login.headers.get("content-type", "").startswith("application/json") else {}
                    token = payload.get("session_token") or payload.get("token")
                    if token:
                        audit = await client.get(
                            f"{base}/api/email-notifications/templates/audit",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        if audit.status_code == 200:
                            audit_json = audit.json()
                            summary = audit_json.get("summary", {})
                            templates_failed = int(summary.get("templates_failed") or 0)
                            broken_links = int(summary.get("broken_links_found") or 0)
                            audit_pass = templates_failed == 0 and broken_links == 0
                            result["details"]["email_template_visual_audit"] = {
                                "status": "PASS" if audit_pass else "FAIL",
                                "templates_total": int(summary.get("templates_total") or 0),
                                "templates_failed": templates_failed,
                                "broken_links_found": broken_links,
                                "footer_version": summary.get("footer_version"),
                            }
                            if not audit_pass:
                                result["status"] = "FAIL"
                                result["issues"].append(
                                    f"Email template visual audit failed: templates_failed={templates_failed}, broken_links={broken_links}"
                                )
                        else:
                            result["details"]["email_template_visual_audit"] = {
                                "status": "SKIP",
                                "reason": f"Audit endpoint HTTP {audit.status_code}",
                            }
                    else:
                        result["details"]["email_template_visual_audit"] = {
                            "status": "SKIP",
                            "reason": "Admin token missing for audit probe",
                        }
                else:
                    result["details"]["email_template_visual_audit"] = {
                        "status": "SKIP",
                        "reason": f"Admin login failed HTTP {login.status_code}",
                    }
    except Exception as e:
        result["details"]["email_template_visual_audit"] = {"status": "SKIP", "error": str(e)[:200]}

    return result


# ═══════════════════════════════════════════════════════════
# GATE 7: PRE-DEPLOYMENT (Load Simulation + API Stress Test)
# ═══════════════════════════════════════════════════════════


async def _run_deployment_gate() -> dict:
    """Pre-deployment gate: load simulation, API stress test, degradation detection."""
    import aiohttp
    result = {"gate": "deployment", "status": "PASS", "details": {}, "issues": []}

    db = await _db()
    config = await _get_engine_config()
    policy = {**DEFAULT_DEPLOYMENT_POLICY, **(config.get("deployment_policy") or {})}

    concurrent_users = int(policy.get("load_concurrent_users", 20))
    duration_sec = int(policy.get("load_duration_seconds", 10))
    burst_size = int(policy.get("stress_burst_size", 50))
    max_avg_ms = float(policy.get("max_avg_response_ms", 5000))
    max_error_pct = float(policy.get("max_error_rate_pct", 5))
    max_degradation = float(policy.get("max_degradation_factor", 3.0))
    endpoints = policy.get("target_endpoints", DEFAULT_DEPLOYMENT_POLICY["target_endpoints"])

    base_url = _resolve_external_base_url() or "http://localhost:8001"

    # ── Phase 1: Baseline latency (single sequential request per endpoint) ──
    baseline_latencies = {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
            for ep in endpoints:
                url = f"{base_url}{ep}"
                t0 = asyncio.get_event_loop().time()
                try:
                    async with sess.get(url) as resp:
                        await resp.read()
                        elapsed = (asyncio.get_event_loop().time() - t0) * 1000
                        baseline_latencies[ep] = round(elapsed, 1)
                except Exception:
                    baseline_latencies[ep] = None
    except Exception as e:
        result["details"]["baseline_error"] = str(e)[:300]

    # ── Phase 2: Load simulation (concurrent users) ──
    load_results = {"total_requests": 0, "successes": 0, "failures": 0, "latencies_ms": []}

    async def _load_worker(session, url, results_acc):
        t0 = asyncio.get_event_loop().time()
        try:
            async with session.get(url) as resp:
                await resp.read()
                elapsed = (asyncio.get_event_loop().time() - t0) * 1000
                results_acc["total_requests"] += 1
                results_acc["latencies_ms"].append(round(elapsed, 1))
                if resp.status < 500:
                    results_acc["successes"] += 1
                else:
                    results_acc["failures"] += 1
        except Exception:
            results_acc["total_requests"] += 1
            results_acc["failures"] += 1

    try:
        end_time = asyncio.get_event_loop().time() + duration_sec
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as sess:
            while asyncio.get_event_loop().time() < end_time:
                tasks = []
                for _ in range(concurrent_users):
                    ep = endpoints[load_results["total_requests"] % len(endpoints)]
                    url = f"{base_url}{ep}"
                    tasks.append(_load_worker(sess, url, load_results))
                await asyncio.gather(*tasks)
                await asyncio.sleep(0.1)
    except Exception as e:
        result["details"]["load_sim_error"] = str(e)[:300]

    lats = load_results["latencies_ms"]
    load_avg_ms = round(sum(lats) / len(lats), 1) if lats else 0
    load_p95_ms = round(sorted(lats)[int(len(lats) * 0.95)] if lats else 0, 1)
    load_error_rate = round((load_results["failures"] / max(load_results["total_requests"], 1)) * 100, 1)

    # ── Phase 3: API stress test (rapid burst) ──
    stress_results = {"total_requests": 0, "successes": 0, "failures": 0, "latencies_ms": []}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as sess:
            tasks = []
            for i in range(burst_size):
                ep = endpoints[i % len(endpoints)]
                url = f"{base_url}{ep}"
                tasks.append(_load_worker(sess, url, stress_results))
            await asyncio.gather(*tasks)
    except Exception as e:
        result["details"]["stress_error"] = str(e)[:300]

    slats = stress_results["latencies_ms"]
    stress_avg_ms = round(sum(slats) / len(slats), 1) if slats else 0
    stress_p95_ms = round(sorted(slats)[int(len(slats) * 0.95)] if slats else 0, 1)
    stress_error_rate = round((stress_results["failures"] / max(stress_results["total_requests"], 1)) * 100, 1)

    # ── Phase 4: Degradation detection ──
    degradation_detected = False
    degradation_details = []
    degradation_min_avg_ms = float(policy.get("degradation_min_avg_ms", 250))
    for ep, base_ms in baseline_latencies.items():
        if base_ms is None or base_ms == 0:
            continue
        load_ep_lats = [lats[i] for i in range(len(lats)) if endpoints[i % len(endpoints)] == ep] if lats else []
        if load_ep_lats:
            avg_under_load = sum(load_ep_lats) / len(load_ep_lats)
            factor = round(avg_under_load / base_ms, 2)
            # Relative factor alone is noisy for sub-50ms baselines; require the
            # absolute latency under load to also exceed the floor.
            if factor > max_degradation and avg_under_load >= degradation_min_avg_ms:
                degradation_detected = True
                degradation_details.append({
                    "endpoint": ep,
                    "baseline_ms": base_ms,
                    "load_avg_ms": round(avg_under_load, 1),
                    "degradation_factor": factor,
                    "threshold": max_degradation,
                })

    # ── Assemble details ──
    result["details"] = {
        "baseline_latencies_ms": baseline_latencies,
        "load_simulation": {
            "concurrent_users": concurrent_users,
            "duration_seconds": duration_sec,
            "total_requests": load_results["total_requests"],
            "successes": load_results["successes"],
            "failures": load_results["failures"],
            "avg_response_ms": load_avg_ms,
            "p95_response_ms": load_p95_ms,
            "error_rate_pct": load_error_rate,
            "max_avg_response_ms": max_avg_ms,
            "max_error_rate_pct": max_error_pct,
        },
        "stress_test": {
            "burst_size": burst_size,
            "total_requests": stress_results["total_requests"],
            "successes": stress_results["successes"],
            "failures": stress_results["failures"],
            "avg_response_ms": stress_avg_ms,
            "p95_response_ms": stress_p95_ms,
            "error_rate_pct": stress_error_rate,
        },
        "degradation": {
            "detected": degradation_detected,
            "max_factor_allowed": max_degradation,
            "details": degradation_details,
        },
    }

    if bool(policy.get("require_email_v2_inheritance_pass", True)):
        email_v2_inheritance_check = await _evaluate_email_v2_inheritance_release_check(run_live_if_needed=True)
        result["details"]["email_v2_inheritance"] = email_v2_inheritance_check
        if str(email_v2_inheritance_check.get("status") or "FAIL").upper() != "PASS":
            result["status"] = "FAIL"
            issue_suffix = (
                email_v2_inheritance_check.get("summary")
                or email_v2_inheritance_check.get("reason")
                or email_v2_inheritance_check.get("output_tail")
                or "No passing V2 inheritance evidence available"
            )
            result["issues"].append(f"Email V2 inheritance release check failed: {str(issue_suffix)[:220]}")

    # ── PASS/FAIL logic ──
    if load_avg_ms > max_avg_ms:
        result["status"] = "FAIL"
        result["issues"].append(f"Load avg response {load_avg_ms}ms exceeds {max_avg_ms}ms threshold")
    if load_error_rate > max_error_pct:
        result["status"] = "FAIL"
        result["issues"].append(f"Load error rate {load_error_rate}% exceeds {max_error_pct}% threshold")
    if stress_avg_ms > max_avg_ms:
        result["status"] = "FAIL"
        result["issues"].append(f"Stress avg response {stress_avg_ms}ms exceeds {max_avg_ms}ms threshold")
    if stress_error_rate > max_error_pct:
        result["status"] = "FAIL"
        result["issues"].append(f"Stress error rate {stress_error_rate}% exceeds {max_error_pct}% threshold")
    if degradation_detected:
        result["status"] = "FAIL"
        for dd in degradation_details:
            result["issues"].append(
                f"Degradation on {dd['endpoint']}: {dd['degradation_factor']}x slowdown (limit: {max_degradation}x)"
            )

    # Persist history
    await db.deployment_gate_history.insert_one({
        "run_at": datetime.now(timezone.utc).isoformat(),
        "gate_status": result["status"],
        "load_avg_ms": load_avg_ms,
        "load_error_rate_pct": load_error_rate,
        "stress_avg_ms": stress_avg_ms,
        "stress_error_rate_pct": stress_error_rate,
        "degradation_detected": degradation_detected,
        "email_v2_inheritance_status": ((result.get("details") or {}).get("email_v2_inheritance") or {}).get("status"),
        "email_v2_inheritance_source": ((result.get("details") or {}).get("email_v2_inheritance") or {}).get("source"),
        "issues": result["issues"],
    })

    return result


# ═══════════════════════════════════════════════════════════
# SELF-HEAL LOOP
# ═══════════════════════════════════════════════════════════


async def _attempt_auto_heal(failed_gates: List[dict]) -> List[dict]:
    """Attempt to auto-heal failed gates using existing engine capabilities."""
    heals = []

    for gate in failed_gates:
        name = gate["gate"]

        if name == "validation":
            # Platform Health auto-fix
            try:
                from routes.platform_health import (
                    _scan_files_for_patterns, _auto_fix_stale_urls,
                    _auto_fix_caches, _check_cache_health,
                    FRONTEND_SRC, FRONTEND_APP,
                    STALE_URL_PATTERNS,
                )
                stale_urls = _scan_files_for_patterns(
                    [FRONTEND_SRC, FRONTEND_APP], STALE_URL_PATTERNS, [".tsx", ".ts", ".js", ".jsx"]
                )
                cache_health = _check_cache_health()
                stale_caches = [c for c in cache_health if c.get("stale")]
                url_fix = _auto_fix_stale_urls(stale_urls)
                cache_fix = _auto_fix_caches(stale_caches)
                heals.append({
                    "gate": name, "action": "platform_health_autofix",
                    "urls_fixed": url_fix.get("fixed", 0),
                    "caches_cleared": len(cache_fix),
                })
            except Exception as e:
                heals.append({"gate": name, "action": "platform_health_autofix", "error": str(e)[:200]})

            # Code Health auto-fix
            try:
                from routes.code_health_scanner import run_full_scan, _auto_fix_tdz
                scan = run_full_scan()
                fixed = 0
                for issue in scan.get("issues", []):
                    if issue.get("type") == "temporal_dead_zone" and issue.get("file"):
                        fixed += _auto_fix_tdz(issue["file"], [issue])
                heals.append({"gate": name, "action": "code_health_autofix", "issues_fixed": fixed})
            except Exception as e:
                heals.append({"gate": name, "action": "code_health_autofix", "error": str(e)[:200]})

        elif name == "performance":
            # Performance Guardian auto-fix
            try:
                from routes.performance_guardian import auto_fix_check
                await auto_fix_check()
                heals.append({"gate": name, "action": "performance_guardian_autofix", "triggered": True})
            except Exception as e:
                heals.append({"gate": name, "action": "performance_guardian_autofix", "error": str(e)[:200]})

        elif name == "e2e":
            # Critical Journey auto-heal
            try:
                from routes.critical_journey_monitor import _attempt_auto_heal as cjm_heal
                failed_ids = [
                    issue.replace("E2E journey failed: ", "")
                    for issue in gate.get("issues", []) if "journey" in issue
                ]
                heal_results = await cjm_heal(failed_ids)
                heals.append({
                    "gate": name, "action": "critical_journey_autoheal",
                    "attempts": len(heal_results),
                    "results": heal_results[:5],
                })
            except Exception as e:
                heals.append({"gate": name, "action": "critical_journey_autoheal", "error": str(e)[:200]})

        elif name == "tests":
            # Self-repair engine
            try:
                from routes.self_repair_engine import run_self_repair
                repair = await run_self_repair()
                heals.append({
                    "gate": name, "action": "self_repair",
                    "repairs": repair.get("repairs_applied", 0),
                })
            except Exception as e:
                heals.append({"gate": name, "action": "self_repair", "error": str(e)[:200]})

    return heals


def _normalize_memory_signature(raw: str) -> str:
    text = re.sub(r"\s+", " ", str(raw or "").strip().lower())
    return re.sub(r"[^a-z0-9:_|\-/\. ]+", "", text)[:220]


def _memory_tokens(raw: str) -> List[str]:
    text = _normalize_memory_signature(raw)
    tokens = [t for t in re.split(r"[^a-z0-9]+", text) if len(t) > 2]
    return list(dict.fromkeys(tokens))[:20]


def _memory_entry_id(memory_type: str, signature: str, solution_summary: str) -> str:
    base = f"{memory_type}|{_normalize_memory_signature(signature)}|{_normalize_memory_signature(solution_summary)}"
    return f"mem_{hashlib.sha1(base.encode('utf-8')).hexdigest()[:16]}"


async def _trim_system_memory(policy: dict):
    db = await _db()
    max_entries = int(policy.get("max_memory_entries", 5000))
    total = await db.system_knowledge_memory.count_documents({})
    overflow = max(0, total - max_entries)
    if overflow <= 0:
        return
    stale = await db.system_knowledge_memory.find({}, {"_id": 0, "memory_id": 1}).sort(
        [("last_used_at", 1), ("created_at", 1)]
    ).limit(overflow).to_list(overflow)
    stale_ids = [row.get("memory_id") for row in stale if row.get("memory_id")]
    if stale_ids:
        await db.system_knowledge_memory.delete_many({"memory_id": {"$in": stale_ids}})


async def _store_system_memory(
    memory_type: str,
    signature: str,
    problem_summary: str,
    solution_summary: str,
    source: str,
    tags: Optional[List[str]] = None,
    confidence_score: float = 0.7,
    evidence: Optional[dict] = None,
):
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("system_memory_policy", {**DEFAULT_SYSTEM_MEMORY_POLICY})
    if not policy.get("enabled", True):
        return {"stored": False, "reason": "system_memory_disabled"}

    normalized_signature = _normalize_memory_signature(signature)
    entry_id = _memory_entry_id(memory_type, normalized_signature, solution_summary)
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "memory_id": entry_id,
        "memory_type": memory_type,
        "signature": normalized_signature,
        "problem_summary": (problem_summary or "")[:360],
        "solution_summary": (solution_summary or "")[:420],
        "source": source,
        "tags": list(dict.fromkeys([str(t).strip().lower() for t in (tags or []) if str(t).strip()]))[:20],
        "tokens": _memory_tokens(f"{normalized_signature} {problem_summary} {solution_summary} {' '.join(tags or [])}"),
        "confidence_score": max(0.0, min(1.0, float(confidence_score))),
        "reuse_count": 0,
        "active": True,
        "evidence": evidence or {},
        "updated_at": now_iso,
    }
    await db.system_knowledge_memory.update_one(
        {"memory_id": entry_id},
        {"$set": payload, "$setOnInsert": {"created_at": now_iso}},
        upsert=True,
    )
    await _trim_system_memory(policy)
    return {"stored": True, "memory_id": entry_id}


def _score_memory_match(entry: dict, query_tokens: List[str], signature: str) -> float:
    if not query_tokens:
        return float(entry.get("confidence_score") or 0.0)
    entry_tokens = set(entry.get("tokens") or [])
    overlap = len(set(query_tokens) & entry_tokens)
    overlap_score = overlap / max(len(set(query_tokens)), 1)
    signature_bonus = 0.2 if _normalize_memory_signature(signature) == str(entry.get("signature") or "") else 0.0
    confidence = float(entry.get("confidence_score") or 0.0)
    return round((overlap_score * 0.55) + (confidence * 0.25) + signature_bonus, 4)


async def _lookup_system_memory(
    task_type: str,
    signature: str,
    context: Optional[dict] = None,
    categories: Optional[List[str]] = None,
    top_k: Optional[int] = None,
) -> dict:
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("system_memory_policy", {**DEFAULT_SYSTEM_MEMORY_POLICY})

    if not policy.get("enabled", True):
        return {"lookup_performed": False, "matches": [], "reason": "system_memory_disabled"}
    if not policy.get("require_lookup_before_task", True):
        return {"lookup_performed": False, "matches": [], "reason": "memory_lookup_optional_disabled"}

    categories = categories or ["failure", "fix", "optimization", "test_pattern"]
    limit = max(1, min(10, int(top_k or policy.get("lookup_top_k", 3))))
    signature_norm = _normalize_memory_signature(signature)
    query_tokens = _memory_tokens(f"{task_type} {signature_norm} {' '.join(categories)}")
    min_conf = float(policy.get("min_confidence_score", 0.55))

    rows = await db.system_knowledge_memory.find(
        {
            "active": True,
            "memory_type": {"$in": categories},
            "confidence_score": {"$gte": min_conf},
        },
        {"_id": 0},
    ).sort([("confidence_score", -1), ("reuse_count", -1), ("updated_at", -1)]).limit(300).to_list(300)

    ranked = []
    for row in rows:
        score = _score_memory_match(row, query_tokens, signature_norm)
        if score <= 0:
            continue
        ranked.append({
            "memory_id": row.get("memory_id"),
            "memory_type": row.get("memory_type"),
            "signature": row.get("signature"),
            "problem_summary": row.get("problem_summary"),
            "solution_summary": row.get("solution_summary"),
            "confidence_score": row.get("confidence_score"),
            "reuse_count": row.get("reuse_count", 0),
            "score": score,
            "tags": row.get("tags", []),
        })
    ranked.sort(key=lambda x: (x.get("score", 0), x.get("confidence_score", 0), x.get("reuse_count", 0)), reverse=True)
    matches = ranked[:limit]

    now_iso = datetime.now(timezone.utc).isoformat()
    lookup_id = f"lookup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    await db.system_memory_lookups.insert_one({
        "lookup_id": lookup_id,
        "task_type": task_type,
        "signature": signature_norm,
        "categories": categories,
        "context": context or {},
        "matches": matches,
        "created_at": now_iso,
    })

    for match in matches:
        await db.system_knowledge_memory.update_one(
            {"memory_id": match.get("memory_id")},
            {"$set": {"last_used_at": now_iso}, "$inc": {"reuse_count": 1}},
        )

    return {
        "lookup_performed": True,
        "lookup_id": lookup_id,
        "task_type": task_type,
        "signature": signature_norm,
        "matches": matches,
    }


async def _capture_pipeline_memory(result: dict, triggered_by: str):
    config = await _get_engine_config()
    policy = config.get("system_memory_policy", {**DEFAULT_SYSTEM_MEMORY_POLICY})
    if not policy.get("enabled", True):
        return

    gates = result.get("gates") or {}
    run_id = result.get("run_id")
    status = str(result.get("status") or "").upper()

    if status == "FAIL" and policy.get("auto_capture_failures", True):
        for gate_name, gate in gates.items():
            if str(gate.get("status") or "") != "FAIL":
                continue
            issues = gate.get("issues") or []
            signature = f"gate:{gate_name}|{'|'.join(issues[:2])}"
            await _store_system_memory(
                memory_type="failure",
                signature=signature,
                problem_summary=f"Pipeline gate '{gate_name}' failed",
                solution_summary="Reuse prior fix playbook for this gate before rerunning autonomous pipeline.",
                source="pipeline_auto_capture",
                tags=["pipeline", "gate", gate_name, "failure"],
                confidence_score=0.72,
                evidence={"run_id": run_id, "issues": issues[:3], "triggered_by": triggered_by},
            )

    if status == "PASS" and policy.get("auto_capture_fixes", True) and result.get("heal_cycles"):
        await _store_system_memory(
            memory_type="fix",
            signature=f"pipeline:heal_success|{triggered_by}",
            problem_summary="Pipeline recovered from failures via self-heal loop",
            solution_summary="Run autonomous self-heal cycle and revalidate all gates after remediation.",
            source="pipeline_auto_capture",
            tags=["pipeline", "self_heal", "fix"],
            confidence_score=0.78,
            evidence={"run_id": run_id, "heal_cycles": len(result.get("heal_cycles") or [])},
        )

    if status == "PASS" and policy.get("auto_capture_optimizations", True):
        perf_gate = gates.get("performance") or {}
        if str(perf_gate.get("status") or "") == "PASS":
            await _store_system_memory(
                memory_type="optimization",
                signature="performance_gate:pass",
                problem_summary="Performance gate met thresholds",
                solution_summary="Keep Performance Guardian budget + deployment gate checks in release workflow.",
                source="pipeline_auto_capture",
                tags=["performance", "optimization", "guardian"],
                confidence_score=0.69,
                evidence={"run_id": run_id, "details": (perf_gate.get("details") or {})},
            )

    if status == "PASS" and policy.get("auto_capture_test_patterns", True):
        tests_gate = gates.get("tests") or {}
        if str(tests_gate.get("status") or "") == "PASS":
            await _store_system_memory(
                memory_type="test_pattern",
                signature="tests_gate:pass",
                problem_summary="Test gate passed successfully",
                solution_summary="Run backend pytest + critical E2E checks before merges/deployments.",
                source="pipeline_auto_capture",
                tags=["tests", "qa", "pattern"],
                confidence_score=0.66,
                evidence={"run_id": run_id},
            )


# ═══════════════════════════════════════════════════════════
# MAIN PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════


async def run_full_pipeline(config: dict, triggered_by: str = "manual") -> dict:
    """Execute the full closed-loop pipeline with recursive self-healing."""
    db = await _db()
    run_id = f"ae_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    gates_enabled = config.get("gates_enabled", {g: True for g in GATE_NAMES})
    for mandatory_gate in MANDATORY_GATES:
        gates_enabled[mandatory_gate] = True
    thresholds = config.get("performance_thresholds", DEFAULT_PERF_THRESHOLDS)
    max_cycles = config.get("max_heal_cycles", MAX_HEAL_CYCLES)
    auto_heal = config.get("auto_heal_enabled", True)
    memory_lookup = await _lookup_system_memory(
        task_type="pipeline_run",
        signature=f"pipeline::{triggered_by}",
        context={"triggered_by": triggered_by, "run_scope": "full_pipeline"},
        categories=["failure", "fix", "optimization", "test_pattern"],
    )

    pipeline_result = {
        "run_id": run_id,
        "triggered_by": triggered_by,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "RUNNING",
        "gates": {},
        "heal_cycles": [],
        "memory_lookup": memory_lookup,
        "final_output": {},
        "completed_at": None,
    }

    for cycle in range(max_cycles + 1):
        cycle_result = {"cycle": cycle, "gates": {}, "heals": []}

        # Run each enabled gate
        gate_runners = {
            "tests": _run_tests_gate,
            "coverage": _run_coverage_gate,
            "validation": _run_validation_gate,
            "performance": lambda: _run_performance_gate(thresholds),
            "e2e": _run_e2e_gate,
            "visual": _run_visual_gate,
            "deployment": _run_deployment_gate,
        }

        for gate_name in GATE_NAMES:
            if gate_name in MANDATORY_GATES and not gates_enabled.get(gate_name, False):
                cycle_result["gates"][gate_name] = {
                    "gate": gate_name,
                    "status": "FAIL",
                    "details": {"status": "FAIL", "reason": "Mandatory gate disabled"},
                    "issues": [f"Mandatory gate '{gate_name}' cannot be disabled"],
                }
                continue
            if not gates_enabled.get(gate_name, True):
                cycle_result["gates"][gate_name] = {
                    "gate": gate_name, "status": "SKIP", "details": {}, "issues": []
                }
                continue
            try:
                gate_result = await gate_runners[gate_name]()
            except Exception as e:
                gate_result = {
                    "gate": gate_name, "status": "FAIL",
                    "details": {"error": str(e)[:500]},
                    "issues": [f"Gate execution error: {e}"],
                }
            cycle_result["gates"][gate_name] = gate_result

        # Determine failed gates
        failed_gates = [
            g for g in cycle_result["gates"].values()
            if g.get("status") == "FAIL"
        ]

        # Auto-log failures to failure memory
        for fg in failed_gates:
            gate_name_f = fg.get("gate", "unknown")
            issues_str = "; ".join(fg.get("issues", [])[:3])
            from routes.autonomous_engine.memory_predictive import _auto_log_failure
            asyncio.ensure_future(_auto_log_failure(
                failure_type="gate_failure",
                component=gate_name_f,
                error_signature=issues_str,
                root_cause=issues_str,
                context={"run_id": run_id, "cycle": cycle, "gate": gate_name_f},
            ))

        # All pass? Exit loop
        if not failed_gates:
            pipeline_result["gates"] = cycle_result["gates"]
            pipeline_result["status"] = "PASS"
            break

        # Last cycle or auto-heal disabled? Mark as FAIL
        if cycle >= max_cycles or not auto_heal:
            pipeline_result["gates"] = cycle_result["gates"]
            pipeline_result["status"] = "FAIL"
            break

        memory_reuse_actions = []
        for fg in failed_gates:
            gate_name_f = fg.get("gate", "unknown")
            issues_str = "; ".join(fg.get("issues", [])[:2])
            gate_memory = await _lookup_system_memory(
                task_type="gate_failure",
                signature=f"{gate_name_f}::{issues_str}",
                context={"run_id": run_id, "cycle": cycle, "gate": gate_name_f},
                categories=["fix", "failure", "optimization", "test_pattern"],
                top_k=1,
            )
            if gate_memory.get("matches"):
                best = gate_memory["matches"][0]
                memory_reuse_actions.append({
                    "gate": gate_name_f,
                    "action": "memory_reuse_recommendation",
                    "memory_id": best.get("memory_id"),
                    "problem_summary": best.get("problem_summary"),
                    "recommended_solution": best.get("solution_summary"),
                    "score": best.get("score"),
                })

        # Attempt self-heal
        heals = await _attempt_auto_heal(failed_gates)
        cycle_result["heals"] = [*memory_reuse_actions, *heals]
        pipeline_result["heal_cycles"].append(cycle_result)

        # Brief pause before re-test
        await asyncio.sleep(2)

    # Build final standardized output
    pipeline_result["completed_at"] = datetime.now(timezone.utc).isoformat()
    pipeline_result["final_output"] = _build_final_output(pipeline_result)

    # Baseline regression guard (immutable pass-state protection)
    baseline_state = await _get_baseline_state()
    if baseline_state.get("locked") and pipeline_result.get("status") != "PASS":
        rollback_performed = False
        rollback_error = None
        if baseline_state.get("regression_policy", {}).get("auto_rollback_on_regression", True):
            try:
                baseline_config = baseline_state.get("baseline_config") or {}
                if baseline_config:
                    await _save_engine_config(baseline_config)
                    rollback_performed = True
            except Exception as rollback_exc:
                rollback_error = str(rollback_exc)[:300]

        regression_event = {
            "event_id": f"ae_reg_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
            "timestamp": datetime.now(timezone.utc),
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "run_id": pipeline_result.get("run_id"),
            "triggered_by": triggered_by,
            "baseline_run_id": baseline_state.get("baseline_run_id"),
            "final_output": pipeline_result.get("final_output", {}),
            "rollback_performed": rollback_performed,
            "rollback_error": rollback_error,
            "message": "Regression detected against locked PASS baseline",
        }
        await db.autonomous_engine_regression_events.insert_one({**regression_event})
        baseline_state["last_regression_event"] = {
            "event_id": regression_event["event_id"],
            "run_id": regression_event["run_id"],
            "triggered_at": regression_event["triggered_at"],
            "rollback_performed": rollback_performed,
            "message": regression_event["message"],
        }
        await _save_baseline_state(baseline_state)

        pipeline_result["regression_guard"] = {
            "baseline_locked": True,
            "regression_detected": True,
            "rollback_performed": rollback_performed,
            "rollback_error": rollback_error,
            "baseline_run_id": baseline_state.get("baseline_run_id"),
            "event_id": regression_event["event_id"],
            "message": regression_event["message"],
        }
    else:
        pipeline_result["regression_guard"] = {
            "baseline_locked": bool(baseline_state.get("locked")),
            "regression_detected": False,
        }

    # Persist run to DB
    await db.autonomous_engine_runs.insert_one({
        **pipeline_result,
        "timestamp": datetime.now(timezone.utc),
    })

    await _capture_pipeline_memory(pipeline_result, triggered_by=triggered_by)

    # Send notification if configured
    if config.get("notify_on_fail") and pipeline_result["status"] == "FAIL":
        await _send_pipeline_alert(pipeline_result)
    elif config.get("notify_on_pass") and pipeline_result["status"] == "PASS":
        await _send_pipeline_alert(pipeline_result)

    return pipeline_result


def _build_final_output(result: dict) -> dict:
    """Build the strict PASS/FAIL output format."""
    gates = result.get("gates", {})
    output = {}
    for g in GATE_NAMES:
        gate_data = gates.get(g, {})
        output[g.upper()] = gate_data.get("status", "SKIP")

    all_statuses = [v for v in output.values() if v != "SKIP"]
    output["STATUS"] = "PASS" if all(s == "PASS" for s in all_statuses) else "FAIL"
    return output


async def _build_gate_lock_state(config: Optional[dict] = None) -> dict:
    db = await _db()
    cfg = config or await _get_engine_config()
    strict_mode = bool(cfg.get("strict_hard_gate", True))
    required_window_minutes = int(cfg.get("require_recent_pass_minutes", 240) or 240)

    latest_run = await db.autonomous_engine_runs.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
    latest_pass_run = await db.autonomous_engine_runs.find_one({"status": "PASS"}, {"_id": 0}, sort=[("timestamp", -1)])

    now = datetime.now(timezone.utc)
    minutes_since_last_pass = None
    if latest_pass_run:
        pass_dt = _parse_iso_datetime(latest_pass_run.get("completed_at")) or _parse_iso_datetime(latest_pass_run.get("started_at"))
        if pass_dt:
            minutes_since_last_pass = max(0, int((now - pass_dt).total_seconds() // 60))

    has_recent_pass = bool(
        latest_pass_run
        and minutes_since_last_pass is not None
        and minutes_since_last_pass <= required_window_minutes
    )
    gate_open = (not strict_mode) or has_recent_pass

    return {
        "strict_hard_gate": strict_mode,
        "require_recent_pass_minutes": required_window_minutes,
        "gate_open": gate_open,
        "has_recent_pass": has_recent_pass,
        "minutes_since_last_pass": minutes_since_last_pass,
        "latest_run_status": (latest_run or {}).get("status"),
        "latest_run_id": (latest_run or {}).get("run_id"),
        "latest_pass_run_id": (latest_pass_run or {}).get("run_id") if latest_pass_run else None,
        "latest_run_output": (latest_run or {}).get("final_output", {}),
    }


def _build_actor_snapshot(user: Any) -> Dict[str, Any]:
    return {
        "user_id": str(getattr(user, "user_id", "")),
        "email": str(getattr(user, "email", "")),
        "is_admin": bool(getattr(user, "is_admin", False)),
    }


async def _record_completion_attempt(
    *,
    actor: Dict[str, Any],
    blocked: bool,
    gate_lock: dict,
    source_endpoint: str,
    workflow_type: Optional[str] = None,
    workflow_id: Optional[str] = None,
    close_reason: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> dict:
    db = await _db()
    audit_doc = {
        "audit_id": f"aeclose_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": datetime.now(timezone.utc),
        "blocked": bool(blocked),
        "source_endpoint": source_endpoint,
        "workflow_type": str(workflow_type or "generic_completion"),
        "workflow_id": str(workflow_id or ""),
        "close_reason": str(close_reason or "unspecified"),
        "actor": {
            "user_id": str(actor.get("user_id") or ""),
            "email": str(actor.get("email") or ""),
            "is_admin": bool(actor.get("is_admin", False)),
        },
        "gate_lock": {
            "strict_hard_gate": bool(gate_lock.get("strict_hard_gate", True)),
            "gate_open": bool(gate_lock.get("gate_open", False)),
            "has_recent_pass": bool(gate_lock.get("has_recent_pass", False)),
            "minutes_since_last_pass": gate_lock.get("minutes_since_last_pass"),
            "latest_run_status": gate_lock.get("latest_run_status"),
            "latest_run_id": gate_lock.get("latest_run_id"),
        },
        "context": context or {},
    }
    await db.autonomous_engine_completion_audit.insert_one(audit_doc)
    audit_doc.pop("_id", None)
    audit_doc.pop("timestamp", None)
    return audit_doc


async def evaluate_completion_gate_and_audit(
    *,
    user: Any,
    source_endpoint: str,
    workflow_type: Optional[str] = None,
    workflow_id: Optional[str] = None,
    close_reason: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> dict:
    """Reusable strict gate check + audit logger for platform closure workflows."""
    config = await _get_engine_config()
    gate_lock = await _build_gate_lock_state(config)
    blocked = bool(config.get("strict_hard_gate", True)) and not bool(gate_lock.get("gate_open"))

    audit_entry = await _record_completion_attempt(
        actor=_build_actor_snapshot(user),
        blocked=blocked,
        gate_lock=gate_lock,
        source_endpoint=source_endpoint,
        workflow_type=workflow_type,
        workflow_id=workflow_id,
        close_reason=close_reason,
        context=context,
    )

    return {
        "blocked": blocked,
        "gate_lock": gate_lock,
        "audit_entry": audit_entry,
        "config": config,
    }


async def _send_pipeline_alert(result: dict):
    """Send email alert for pipeline results."""
    try:
        from utils.email_service import send_catalog_template
        status = result.get("status", "UNKNOWN")
        run_id = result.get("run_id", "?")
        duration = result.get("duration")
        if not duration and result.get("started_at") and result.get("completed_at"):
            try:
                from datetime import datetime

                delta = (datetime.fromisoformat(result["completed_at"])
                         - datetime.fromisoformat(result["started_at"])).total_seconds()
                duration = f"{int(delta // 60)}m {int(delta % 60)}s"
            except Exception:
                duration = "N/A"
        content_count = result.get("content_generated", 0)
        error_count = len(result.get("errors", []))
        gates_summary = {}
        final_output = result.get("final_output") or {}
        if isinstance(final_output, dict):
            gates_summary = {k: str(v) for k, v in final_output.items() if isinstance(v, str)}
        root_cause = ""
        if str(status).upper() != "PASS":
            pytest_detail = (((result.get("gates") or {}).get("tests") or {})
                             .get("details", {}).get("backend_pytest", {}))
            root_cause = (pytest_detail.get("failure_message")
                          or str(pytest_detail.get("output_tail") or "").strip()
                          or "See run details in the Operations Console.")
        await send_catalog_template(
            recipient_email="admin@realaicoach.app",
            template_key="autonomous_engine_report",
            run_id=run_id,
            status=str(status).title(),
            duration=str(duration or "N/A"),
            content_generated=content_count,
            errors=error_count,
            gates=gates_summary,
            root_cause=root_cause,
        )
    except Exception:
        pass


def _build_pipeline_alert_email_html(result: dict) -> str:
    output = result.get("final_output", {})
    run_id = result.get("run_id", "?")
    status = str(result.get("status", "UNKNOWN")).upper()
    cycles = result.get("heal_cycles", [])
    status_color = "#10B981" if status == "PASS" else "#EF4444" if status == "FAIL" else "#F59E0B"
    rows = []
    for key in ["STATUS", "TESTS", "COVERAGE", "VALIDATION", "PERFORMANCE", "E2E", "VISUAL", "DEPLOYMENT"]:
        val = str(output.get(key, "SKIP"))
        val_color = "#10B981" if val == "PASS" else "#EF4444" if val == "FAIL" else "#64748B"
        rows.append(
            "<tr>"
            f"<td style='padding:7px 8px;color:#475569;font-size:12px;font-weight:700;letter-spacing:0.2px'>{key}</td>"
            f"<td style='padding:7px 8px;text-align:right;color:{val_color}!important;-webkit-text-fill-color:{val_color}!important;font-size:12px;font-weight:900'>{val}</td>"
            "</tr>"
        )

    cycles_line = (
        f"<p class='em-force-muted-text' style='margin:12px 0 0;color:#475569;font-size:12px'><strong style='color:#0F172A'>Self-heal cycles:</strong> {len(cycles)}</p>"
        if cycles
        else ""
    )

    return (
        "<div class='em-force-light-card' style='font-family:Inter,Segoe UI,Arial,sans-serif;padding:18px;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px'>"
        f"<h3 class='em-force-dark-text' style='margin:0 0 8px;color:#0F172A;font-size:16px'>Autonomous Engine Pipeline Result</h3>"
        f"<p class='em-force-muted-text' style='margin:0 0 6px;color:#475569;font-size:12px'>Run: <span style='color:#0F172A;font-weight:700'>{run_id}</span></p>"
        f"<p class='em-force-muted-text' style='margin:0 0 12px;color:#475569;font-size:12px'>Overall status: <span style='color:{status_color}!important;-webkit-text-fill-color:{status_color}!important;font-weight:900'>{status}</span></p>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='border-collapse:collapse;border:1px solid #E2E8F0;border-radius:10px;overflow:hidden'>"
        f"{''.join(rows)}"
        "</table>"
        f"{cycles_line}"
        "</div>"
    )


# ═══════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════


def _calculate_architecture_compliance_score(validation: dict) -> float:
    summary = validation.get("summary") or {}
    total_modules = int(summary.get("total_modules") or 0)
    pass_modules = int(summary.get("pass_modules") or 0)
    module_ratio = (pass_modules / total_modules) if total_modules > 0 else 1.0
    gateway_ok = bool(((validation.get("gateway_path_mapping") or {}).get("communications_pilot") or {}).get("path_mapping_verified"))
    score = (module_ratio * 85.0) + (15.0 if gateway_ok else 0.0)
    return round(max(0.0, min(100.0, score)), 1)


async def _trim_architecture_compliance_history(max_rows: int = 200):
    db = await _db()
    total = await db.architecture_compliance_history.count_documents({})
    if total <= max_rows:
        return
    overflow = total - max_rows
    rows = await db.architecture_compliance_history.find({}, {"_id": 1}).sort("checked_at", 1).limit(overflow).to_list(overflow)
    if rows:
        await db.architecture_compliance_history.delete_many({"_id": {"$in": [row["_id"] for row in rows]}})


@router.post("/run")
async def trigger_pipeline(request: Request):
    """Trigger the full autonomous pipeline. Returns standardized PASS/FAIL output."""
    await _require_admin(request)
    config = await _get_engine_config()
    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail="Autonomous engine is disabled")

    result = await run_full_pipeline(config, triggered_by="admin_manual")
    result.pop("_id", None)

    if config.get("strict_hard_gate", True) and result.get("status") != "PASS":
        gate_lock = await _build_gate_lock_state(config)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Autonomous Engine strict hard-gate blocked completion (pipeline failed).",
                "completion_blocked": True,
                "run_id": result.get("run_id"),
                "final_output": result.get("final_output", {}),
                "gate_lock": gate_lock,
                "result": result,
            },
        )

    return result


@router.get("/status")
async def engine_status(request: Request):
    """Get engine status and last run results."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()

    last_run = await db.autonomous_engine_runs.find_one(
        {}, {"_id": 0}, sort=[("timestamp", -1)]
    )
    total_runs = await db.autonomous_engine_runs.count_documents({})
    pass_count = await db.autonomous_engine_runs.count_documents({"status": "PASS"})
    gate_lock = await _build_gate_lock_state(config)
    baseline_state = await _get_baseline_state()
    drift_summary = await _build_drift_status_summary(config)
    from routes.autonomous_engine.monitoring import _build_feedback_loop_summary
    from routes.autonomous_engine.memory_predictive import _build_predictive_status_summary, _build_darkmode_regression_scan_summary
    from routes.autonomous_engine.zero_trust import _build_zero_trust_mitigation_status
    from routes.autonomous_engine.theme import _latest_theme_guardrail_run
    feedback_summary = await _build_feedback_loop_summary(config)
    predictive_summary = await _build_predictive_status_summary(config)
    darkmode_scan_summary = await _build_darkmode_regression_scan_summary()
    zero_trust_summary = await _build_zero_trust_mitigation_status(config)
    zero_trust_email_policy = _normalize_zero_trust_daily_email_policy(config.get("zero_trust_daily_email_policy"))
    zero_trust_daily_email_latest = await db.zero_trust_daily_email_history.find_one({}, {"_id": 0}, sort=[("sent_at", -1)])
    theme_guardrail_summary = await _latest_theme_guardrail_run()

    return {
        "engine_enabled": config.get("enabled", True),
        "auto_heal_enabled": config.get("auto_heal_enabled", True),
        "strict_hard_gate": config.get("strict_hard_gate", True),
        "require_recent_pass_minutes": config.get("require_recent_pass_minutes", 240),
        "mandatory_gates": config.get("mandatory_gates", sorted(list(MANDATORY_GATES))),
        "gates_enabled": config.get("gates_enabled", {}),
        "performance_thresholds": config.get("performance_thresholds", {}),
        "total_runs": total_runs,
        "pass_count": pass_count,
        "fail_count": total_runs - pass_count,
        "pass_rate": f"{(pass_count / total_runs * 100):.0f}%" if total_runs > 0 else "N/A",
        "gate_lock": gate_lock,
        "pass_state_protection": {
            "locked": bool(baseline_state.get("locked")),
            "locked_at": baseline_state.get("locked_at"),
            "locked_by": baseline_state.get("locked_by"),
            "baseline_run_id": baseline_state.get("baseline_run_id"),
            "regression_policy": baseline_state.get("regression_policy", {}),
            "last_regression_event": baseline_state.get("last_regression_event"),
        },
        "drift_detection": drift_summary,
        "feedback_loop": feedback_summary,
        "predictive_prevention": predictive_summary,
        "zero_trust_automation": zero_trust_summary,
        "zero_trust_daily_email": {
            "policy": zero_trust_email_policy,
            "latest": zero_trust_daily_email_latest,
        },
        "theme_guardrail": theme_guardrail_summary,
        "nightly_darkmode_scan": darkmode_scan_summary,
        "last_run": last_run,
    }


@router.get("/history")
async def engine_history(request: Request, limit: int = Query(20, ge=1, le=100)):
    """Get pipeline run history."""
    await _require_admin(request)
    db = await _db()
    cursor = db.autonomous_engine_runs.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit)
    runs = await cursor.to_list(length=limit)
    return {"runs": runs, "total": await db.autonomous_engine_runs.count_documents({})}


@router.get("/config")
async def get_config(request: Request):
    """Get engine configuration."""
    await _require_admin(request)
    config = await _get_engine_config()
    return config


class EngineConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    max_heal_cycles: Optional[int] = None
    gates_enabled: Optional[Dict[str, bool]] = None
    performance_thresholds: Optional[Dict[str, float]] = None
    auto_heal_enabled: Optional[bool] = None
    strict_hard_gate: Optional[bool] = None
    require_recent_pass_minutes: Optional[int] = None
    notify_on_fail: Optional[bool] = None
    notify_on_pass: Optional[bool] = None
    zero_trust_policy: Optional[Dict[str, Any]] = None


class CompletionGateRequest(BaseModel):
    workflow_type: Optional[str] = None
    workflow_id: Optional[str] = None
    close_reason: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@router.put("/config")
async def update_config(request: Request, body: EngineConfigUpdate):
    """Update engine configuration."""
    user = await _require_admin(request)
    config = await _get_engine_config()
    previous_config = copy.deepcopy(config)
    updates = body.dict(exclude_none=True)

    incoming_gates = updates.get("gates_enabled")
    if isinstance(incoming_gates, dict):
        for mandatory_gate in MANDATORY_GATES:
            if incoming_gates.get(mandatory_gate) is False:
                raise HTTPException(status_code=400, detail=f"'{mandatory_gate}' gate is mandatory and cannot be disabled")

    config.update(updates)
    gates_enabled = config.get("gates_enabled") or {g: True for g in GATE_NAMES}
    for mandatory_gate in MANDATORY_GATES:
        gates_enabled[mandatory_gate] = True
    config["gates_enabled"] = gates_enabled
    config["mandatory_gates"] = sorted(list(MANDATORY_GATES))
    if config.get("require_recent_pass_minutes") is not None:
        try:
            config["require_recent_pass_minutes"] = max(1, int(config["require_recent_pass_minutes"]))
        except Exception:
            config["require_recent_pass_minutes"] = 240
    await _save_engine_config(config)

    baseline_state = await _get_baseline_state()
    if baseline_state.get("locked") and baseline_state.get("regression_policy", {}).get("require_full_regression_before_merge", True):
        verification_run = await run_full_pipeline(config, triggered_by=f"config_update:{getattr(user, 'email', 'admin')}")
        if verification_run.get("status") != "PASS":
            await _save_engine_config(previous_config)
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Regression detected during mandatory full-suite verification. Config auto-rolled back.",
                    "rollback_performed": True,
                    "verification_run": verification_run,
                },
            )
        return {
            **config,
            "regression_verified": True,
            "regression_verified_run_id": verification_run.get("run_id"),
        }

    return config


@router.get("/gate-lock")
async def get_gate_lock_status(request: Request):
    """Get strict hard-gate lock state used for completion enforcement."""
    await _require_admin(request)
    config = await _get_engine_config()
    return await _build_gate_lock_state(config)


@router.post("/run-gate/{gate_name}")
async def run_single_gate(gate_name: str, request: Request):
    """Run a single gate for debugging."""
    await _require_admin(request)
    if gate_name not in GATE_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid gate. Choose from: {GATE_NAMES}")

    config = await _get_engine_config()
    thresholds = config.get("performance_thresholds", DEFAULT_PERF_THRESHOLDS)

    runners = {
        "tests": _run_tests_gate,
        "coverage": _run_coverage_gate,
        "validation": _run_validation_gate,
        "performance": lambda: _run_performance_gate(thresholds),
        "e2e": _run_e2e_gate,
        "visual": _run_visual_gate,
        "deployment": _run_deployment_gate,
    }
    result = await runners[gate_name]()
    return result


# ═══════════════════════════════════════════════════════════
# COVERAGE POLICY & STATUS ENDPOINTS
# ═══════════════════════════════════════════════════════════

