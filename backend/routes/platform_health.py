"""
Platform Health Monitor — Detects stale URLs, build staleness, cache age.
Daily auto-scan + 100% automated Safe Auto-Fix.
"""

import os
import asyncio
import re
import glob
import time
import json
import hashlib
import subprocess
import shlex
import shutil
import logging
import uuid
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from routes.auth import get_current_user
from routes.db import db, require_admin
from services.platform_health.common import (
    compute_ledger_entry_hash,
    derive_severity_band,
    normalize_slo_auto_mitigation_policy,
    parse_datetime_value,
    parse_iso_datetime,
    percentile as platform_percentile,
    provider_label,
    safe_float,
)
from services.platform_health.compliance import (
    build_enterprise_compliance_csv,
    build_enterprise_compliance_report,
    dispatch_enterprise_compliance_report_email,
    get_admin_distribution_recipients,
    is_valid_email,
)
from services.platform_health.scanner import (
    auto_fix_caches,
    auto_fix_stale_urls,
    check_build_staleness,
    check_cache_health,
    check_env_consistency,
    compute_health_score,
    scan_files_for_patterns,
    store_scan_result,
)
from services.platform_health.enforcement import (
    build_pipeline_stage_status,
    collect_enforcement_rule_health,
    create_remediation_rollback_checkpoint,
)
from services.platform_health.fee_visibility_visual_audit import build_fee_visibility_visual_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/platform-health", tags=["Platform Health"])

FRONTEND_SRC = "/app/frontend/src"
FRONTEND_APP = "/app/frontend/app"
FRONTEND_DIST = "/app/frontend/dist"
FRONTEND_ROOT = "/app/frontend"
FRONTEND_EXPORT_LOCKFILE = "/tmp/frontend_export_build.lock"
FRONTEND_EXPORT_NODE_OPTIONS = str(
    os.environ.get("FRONTEND_EXPORT_NODE_OPTIONS") or "--max-old-space-size=3072"
).strip()

# Patterns that indicate stale hardcoded URLs
STALE_URL_PATTERNS = [
    r"process\.env\.EXPO_PUBLIC_BACKEND_URL(?!\s*\|\|\s*\(?\s*process)",
]

# The safe pattern we want to see
SAFE_PATTERN = "window.location"

# Directories to skip
SKIP_DIRS = {"node_modules", "dist", ".expo", ".git", "__pycache__", ".next", "build"}

CACHE_DIRS = [
    {"path": "/app/frontend/.expo", "label": "Expo Cache"},
    {"path": "/app/frontend/.metro-cache", "label": "Metro Bundler Cache"},
    {"path": "/app/frontend/node_modules/.cache", "label": "Node Modules Cache"},
    {"path": "/app/frontend/dist", "label": "Production Build"},
]

ROLLBACK_POLICIES = {
    "critical": {"retention_hours": 168, "max_checkpoints": 50, "rollback_window_label": "7 days"},
    "high": {"retention_hours": 120, "max_checkpoints": 40, "rollback_window_label": "5 days"},
    "medium": {"retention_hours": 72, "max_checkpoints": 30, "rollback_window_label": "3 days"},
    "low": {"retention_hours": 48, "max_checkpoints": 20, "rollback_window_label": "2 days"},
}

SLO_POLICY_FLAG_KEY = "slo_auto_mitigation_policy"
SLO_RUNTIME_FLAG_KEY = "slo_auto_mitigation_runtime"
SLO_HISTORY_COLLECTION = "enterprise_slo_auto_mitigation_history"
DEFAULT_SLO_AUTO_MITIGATION_POLICY = {
    "enabled": False,
    "p95_latency_threshold_ms": 300,
    "min_samples": 40,
    "breach_consecutive_checks": 2,
    "cooldown_minutes": 20,
    "check_interval_seconds": 180,
    "auto_fix_recipes": ["warm_hot_caches", "guardian_auto_fix", "platform_auto_fix"],
}

BOOT_POLICY_RELOAD_TELEMETRY_COLLECTION = "boot_policy_reload_telemetry"
BOOT_POLICY_RELOAD_MONITOR_STATE_COLLECTION = "boot_policy_reload_monitor_state"
BOOT_POLICY_RELOAD_MONITOR_EVENTS_COLLECTION = "boot_policy_reload_monitor_events"
BOOT_POLICY_RELOAD_MONITOR_STATE_KEY = "boot_policy_should_reload_spike_monitor"
GLOBAL_PARITY_AUDITS_COLLECTION = "platform_global_parity_audits"
GLOBAL_PARITY_INCIDENTS_COLLECTION = "platform_global_parity_incidents"
GLOBAL_PARITY_SAFE_CONFIG_KEY = "global_parity_safe_config"
FEE_VISIBILITY_VISUAL_AUDITS_COLLECTION = "platform_fee_visibility_visual_audits"
FEE_VISIBILITY_VISUAL_ESCALATION_STATE_KEY = "fee_visibility_visual_escalation_state"
FEE_VISIBILITY_VISUAL_INCIDENT_STATE_KEY = "fee_visibility_visual_incident_state"
FEE_VISIBILITY_VISUAL_INCIDENT_MIN_FAILS = 2
PREVIEW_CACHE_HYGIENE_AUDITS_COLLECTION = "platform_preview_cache_hygiene_audits"
PREVIEW_CACHE_HYGIENE_ALERT_STATE_KEY = "preview_cache_hygiene_alert_state"
PREVIEW_CACHE_HYGIENE_INCIDENT_STATE_KEY = "preview_cache_hygiene_incident_state"
PREVIEW_CACHE_HYGIENE_INCIDENT_MIN_FAIL_STREAK = 2
PREVIEW_BROWSER_E2E_RUNS_COLLECTION = "preview_browser_e2e_runs"
PREVIEW_BROWSER_E2E_STATE_COLLECTION = "preview_browser_e2e_state"
PREVIEW_BROWSER_E2E_ALERT_STATE_KEY = "preview_browser_e2e_alert_state"
PREVIEW_BROWSER_E2E_JOB_ID = "preview_browser_e2e_wake_and_run_nightly"
PREVIEW_BROWSER_E2E_MANUAL_TRIGGER_FLAG_KEY = "preview_browser_e2e_manual_trigger_state"
PREVIEW_BROWSER_E2E_FALSE_POSITIVE_BACKFILL_VERSION = "v2_deterministic_backfill"
PREVIEW_ADAPTER_LIVE_CHECK_STATE_KEY = "preview_adapter_live_check_latest"
PREVIEW_ADAPTER_LIVE_CHECK_CACHE_TTL_SECONDS = 20
_PREVIEW_ADAPTER_LIVE_CHECK_CACHE: Dict[str, Any] = {
    "ts": 0.0,
    "payload": None,
}

BACKFILL_SIMULATOR_PROFILES: Dict[str, Dict[str, Any]] = {
    "strict": {
        "min_confidence": 0.90,
        "max_strict_markers": 0,
        "min_route_pass_count": 3,
    },
    "standard": {
        "min_confidence": 0.86,
        "max_strict_markers": 1,
        "min_route_pass_count": 2,
    },
    "lenient": {
        "min_confidence": 0.72,
        "max_strict_markers": 1,
        "min_route_pass_count": 1,
    },
}

RBAC_ADMIN_POLICY_REGISTRY: Dict[str, str] = {
    r"^/api/admin/access-control/": "delegated_or_admin",
    r"^/api/admin/calendar/": "admin_only",
    r"^/api/admin/platform-health/": "admin_only",
    r"^/api/admin/employees/": "delegated_or_admin",
    r"^/api/admin/subscription": "delegated_or_admin",
    r"^/api/admin/payment": "delegated_or_admin",
    r"^/api/admin/notification": "admin_only",
    r"^/api/admin/live-activity": "admin_only",
    r"^/api/admin/session-replay": "admin_only",
    r"^/api/admin/enterprise": "admin_only",
    r"^/api/admin/automation": "admin_only",
    r"^/api/admin/infra": "admin_only",
    r"^/api/admin/waf": "admin_only",
    r"^/api/admin/self-repair": "admin_only",
}

ASSIGNED_HOST_GUARD_RUNS_COLLECTION = "assigned_host_guard_runs"
ASSIGNED_HOST_GUARD_CONFIG_KEY = "assigned_host_guard_config"
ASSIGNED_HOST_GUARD_STATE_KEY = "assigned_host_guard_state"
ASSIGNED_HOST_GUARD_HEARTBEAT_ID = "assigned_host_guardian"

ENTERPRISE_CONTROL_PLANE_CACHE_TTL_SECONDS = 60
_ENTERPRISE_CONTROL_PLANE_CACHE: Dict[str, Any] = {
    "ts": 0.0,
    "data": None,
    "refreshing": False,
}

_is_valid_email = is_valid_email
_get_admin_distribution_recipients = get_admin_distribution_recipients
_build_enterprise_compliance_report = build_enterprise_compliance_report
_build_enterprise_compliance_csv = build_enterprise_compliance_csv
_dispatch_enterprise_compliance_report_email = dispatch_enterprise_compliance_report_email
_derive_severity_band = derive_severity_band
_parse_iso_datetime = parse_iso_datetime
_provider_label = provider_label
_safe_float = safe_float
_compute_ledger_entry_hash = compute_ledger_entry_hash
_parse_datetime_value = parse_datetime_value
_percentile = platform_percentile
_compute_health_score = compute_health_score
_store_scan_result = store_scan_result


def _scan_files_for_patterns(base_dirs: List[str], patterns: List[str], extensions: List[str]) -> List[Dict[str, Any]]:
    return scan_files_for_patterns(base_dirs, patterns, extensions, safe_pattern=SAFE_PATTERN, skip_dirs=SKIP_DIRS)


def _check_build_staleness() -> Dict[str, Any]:
    return check_build_staleness(FRONTEND_DIST, FRONTEND_SRC, FRONTEND_APP, SKIP_DIRS)


def _check_cache_health() -> List[Dict[str, Any]]:
    return check_cache_health(CACHE_DIRS)


def _check_env_consistency() -> Dict[str, Any]:
    return check_env_consistency(FRONTEND_ROOT)


def _auto_fix_stale_urls(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    return auto_fix_stale_urls(issues)


def _auto_fix_caches(stale_caches: List[Dict[str, Any]]) -> List[str]:
    return auto_fix_caches(stale_caches)


def _normalize_slo_auto_mitigation_policy(raw_policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return normalize_slo_auto_mitigation_policy(raw_policy, DEFAULT_SLO_AUTO_MITIGATION_POLICY)


class _AutoMitigationAdminContext:
    def __init__(self, user_id: str, email: str):
        self.user_id = user_id
        self.email = email
        self.is_admin = True


def _resolve_global_parity_external_base_url() -> str:
    candidates: List[str] = [
        str(os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "").strip(),
        str(os.environ.get("REACT_APP_BACKEND_URL") or "").strip(),
        str(os.environ.get("FRONTEND_BASE_URL") or "").strip(),
    ]

    frontend_env_path = Path("/app/frontend/.env")
    if frontend_env_path.exists():
        try:
            for line in frontend_env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    candidates.insert(0, line.split("=", 1)[1].strip().strip('"').strip("'"))
                if line.startswith("REACT_APP_BACKEND_URL="):
                    candidates.append(line.split("=", 1)[1].strip().strip('"').strip("'"))
        except Exception:
            pass

    for candidate in candidates:
        value = str(candidate or "").strip().rstrip("/")
        if value.startswith("http://") or value.startswith("https://"):
            return value
    return ""


def _extract_request_auth_token(request: Request) -> str:
    auth_header = str(request.headers.get("authorization") or "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    cookie_token = str(request.cookies.get("session_token") or "").strip()
    return cookie_token


async def _fetch_json_probe(
    client: httpx.AsyncClient,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: float = 20.0,
) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        response = await client.get(url, headers=headers or {}, timeout=timeout_seconds)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            parsed = response.json()
        except Exception:
            parsed = {"_raw": response.text[:300]}
        return {
            "url": url,
            "status_code": int(response.status_code),
            "ok": bool(response.status_code == 200),
            "latency_ms": latency_ms,
            "body": parsed,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "url": url,
            "status_code": 0,
            "ok": False,
            "latency_ms": latency_ms,
            "error": str(exc)[:280],
            "body": {},
        }


def _extract_challenge_signal(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    source = snapshot if isinstance(snapshot, dict) else {}
    strict_hits = source.get("strict_hits") if isinstance(source.get("strict_hits"), list) else []
    soft_hits = source.get("soft_hits") if isinstance(source.get("soft_hits"), list) else []
    app_shell_hits = source.get("app_shell_hits") if isinstance(source.get("app_shell_hits"), list) else []

    strict_count = int(source.get("strict_marker_count") or len(strict_hits) or 0)
    soft_count = int(source.get("soft_marker_count") or len(soft_hits) or 0)
    app_shell_count = int(source.get("app_shell_marker_count") or len(app_shell_hits) or 0)

    return {
        "classification": str(source.get("classification") or "").strip().lower(),
        "title_has_challenge": bool(source.get("title_has_challenge")),
        "strict_marker_count": max(0, strict_count),
        "soft_marker_count": max(0, soft_count),
        "app_shell_marker_count": max(0, app_shell_count),
    }


def _classify_preview_browser_e2e_false_positive_candidate(run_doc: Dict[str, Any]) -> Dict[str, Any]:
    status = str(run_doc.get("status") or "").strip().lower()
    status_reason_code = str(run_doc.get("status_reason_code") or "").strip()
    blocking_reason = str(run_doc.get("blocking_reason") or "").strip()
    reason_blob = f"{status_reason_code} {blocking_reason}".lower()

    cloudflare_hint = any(token in reason_blob for token in ["cloudflare", "challenge", "cf_", "cdn-cgi"])
    if status not in {"blocked", "fail"}:
        return {
            "eligible": False,
            "classification": "not_eligible",
            "heuristics": ["non_blocked_status"],
            "status_reason_code_backfill": "NO_BACKFILL_CHANGE",
            "confidence": 0.0,
        }

    guard = run_doc.get("challenge_detection_guard") if isinstance(run_doc.get("challenge_detection_guard"), dict) else {}
    initial_signal = _extract_challenge_signal(guard.get("initial") if isinstance(guard.get("initial"), dict) else {})
    post_wake_signal = _extract_challenge_signal(guard.get("post_wake") if isinstance(guard.get("post_wake"), dict) else {})
    guard_version = str(guard.get("guard_version") or "").strip()

    strict_max = max(initial_signal["strict_marker_count"], post_wake_signal["strict_marker_count"])
    soft_max = max(initial_signal["soft_marker_count"], post_wake_signal["soft_marker_count"])
    app_shell_max = max(initial_signal["app_shell_marker_count"], post_wake_signal["app_shell_marker_count"])
    title_has_challenge = bool(initial_signal["title_has_challenge"] or post_wake_signal["title_has_challenge"])

    checks = run_doc.get("checks") if isinstance(run_doc.get("checks"), list) else []
    route_checks: List[Dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name") or "")
        if name.startswith("route_"):
            route_checks.append(check)
    route_total = len(route_checks)
    route_pass_count = sum(1 for item in route_checks if bool(item.get("ok")))

    localhost_fallback_status = str(run_doc.get("localhost_fallback_status") or "").strip().lower()
    localhost_fallback = run_doc.get("localhost_fallback") if isinstance(run_doc.get("localhost_fallback"), dict) else {}
    fallback_pass = localhost_fallback_status == "pass" or bool(localhost_fallback.get("pass"))

    heuristics: List[str] = []
    strong_challenge_signal = False
    weak_signal = False

    if strict_max >= 2:
        strong_challenge_signal = True
        heuristics.append("strict_marker_count_ge_2")
    if title_has_challenge and strict_max >= 1 and app_shell_max == 0:
        strong_challenge_signal = True
        heuristics.append("challenge_title_with_strict_markers_and_no_app_shell")

    if app_shell_max >= 2 and strict_max <= 1 and not title_has_challenge:
        weak_signal = True
        heuristics.append("app_shell_present_with_weak_challenge_markers")
    if fallback_pass and strict_max <= 1 and not title_has_challenge:
        weak_signal = True
        heuristics.append("localhost_fallback_pass_with_weak_markers")
    if route_total >= 3 and route_pass_count >= 3 and strict_max <= 1:
        weak_signal = True
        heuristics.append("external_routes_rendered_with_weak_markers")
    if guard_version and guard_version != "v2_deterministic" and strict_max <= 1 and soft_max >= 1:
        weak_signal = True
        heuristics.append("legacy_guard_version_with_soft_markers")
    if not guard_version and cloudflare_hint and fallback_pass:
        weak_signal = True
        heuristics.append("legacy_run_without_guard_and_fallback_pass")

    if not cloudflare_hint and strict_max == 0 and soft_max == 0:
        return {
            "eligible": False,
            "classification": "not_eligible",
            "heuristics": ["no_cloudflare_or_challenge_hint"],
            "status_reason_code_backfill": "NO_BACKFILL_CHANGE",
            "confidence": 0.0,
        }

    classification = "likely_false_positive" if weak_signal and not strong_challenge_signal else "likely_true_challenge"
    confidence = 0.86 if classification == "likely_false_positive" else 0.74
    if not heuristics:
        heuristics = ["insufficient_evidence"]

    return {
        "eligible": True,
        "classification": classification,
        "heuristics": heuristics,
        "strict_marker_count": strict_max,
        "soft_marker_count": soft_max,
        "app_shell_marker_count": app_shell_max,
        "title_has_challenge": title_has_challenge,
        "route_total": route_total,
        "route_pass_count": route_pass_count,
        "localhost_fallback_status": localhost_fallback_status,
        "guard_version": guard_version,
        "status_reason_code_backfill": (
            "BLOCKED_EXTERNAL_PREVIEW_WEAK_SIGNAL_FALSE_POSITIVE"
            if classification == "likely_false_positive"
            else "NO_BACKFILL_CHANGE"
        ),
        "confidence": confidence,
    }


def _detect_preview_wake_layer_markers(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "")
    lower = text.lower()
    markers = {
        "ready_to_start_preview": "ready to start your preview" in lower,
        "wake_up_servers": "wake up servers" in lower,
        "no_available_adapters": "no available adapters" in lower,
        "emergent_wrapper": "app.emergent.sh" in lower,
    }
    return {
        "markers": markers,
        "has_wake_layer": any(bool(v) for v in markers.values()),
        "has_react_root_hint": ('id="root"' in lower) or ("data-reactroot" in lower) or ("data-expo-root" in lower),
    }


def _normalize_backfill_profile(raw_profile: Any) -> str:
    profile = str(raw_profile or "standard").strip().lower()
    return profile if profile in BACKFILL_SIMULATOR_PROFILES else "standard"


def _profile_accepts_backfill(classification: Dict[str, Any], profile: str) -> bool:
    normalized = _normalize_backfill_profile(profile)
    if classification.get("classification") != "likely_false_positive":
        return False
    profile_cfg = BACKFILL_SIMULATOR_PROFILES.get(normalized) or BACKFILL_SIMULATOR_PROFILES["standard"]
    confidence = float(classification.get("confidence") or 0.0)
    strict_markers = int(classification.get("strict_marker_count") or 0)
    route_pass_count = int(classification.get("route_pass_count") or 0)
    return bool(
        confidence >= float(profile_cfg.get("min_confidence") or 0.0)
        and strict_markers <= int(profile_cfg.get("max_strict_markers") or 1)
        and route_pass_count >= int(profile_cfg.get("min_route_pass_count") or 0)
    )


def _derive_backfill_signal_badge(*, scanned_count: int, likely_false_positive: int, likely_true_challenge: int) -> Dict[str, Any]:
    scanned = max(1, int(scanned_count or 0))
    false_ratio = float(likely_false_positive) / float(scanned)
    challenge_ratio = float(likely_true_challenge) / float(scanned)
    if likely_false_positive <= 0 and likely_true_challenge > 0:
        status = "TRUE_CHALLENGE_DOMINANT"
        severity = "healthy"
        summary = "Blocked runs are mostly true challenge signals."
    elif false_ratio >= 0.25 and likely_false_positive > likely_true_challenge:
        status = "WEAK_SIGNAL_FALSE_POSITIVE_RISK"
        severity = "warning"
        summary = "Weak-signal false positives are elevated and should be reviewed."
    else:
        status = "MIXED_SIGNAL_REVIEW"
        severity = "info"
        summary = "Mixed signal quality. Review before applying broad backfill."
    return {
        "status": status,
        "severity": severity,
        "summary": summary,
        "false_positive_ratio": round(false_ratio, 4),
        "true_challenge_ratio": round(challenge_ratio, 4),
    }


def _extract_admin_api_routes_for_drift(limit: int = 1000) -> List[str]:
    route_files = sorted(glob.glob('/app/backend/routes/*.py'))
    discovered: List[str] = []
    for file_path in route_files:
        try:
            raw = Path(file_path).read_text(encoding='utf-8')
        except Exception:
            continue
        prefix_match = re.search(r'APIRouter\(\s*prefix\s*=\s*["\']([^"\']+)["\']', raw)
        router_prefix = str(prefix_match.group(1) if prefix_match else '').strip()
        route_matches = re.findall(r'@router\.(?:get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']', raw)
        for route_path in route_matches:
            full_path = f"{router_prefix}{route_path}" if router_prefix else str(route_path)
            if not full_path.startswith('/'):
                full_path = f"/{full_path}"
            api_path = f"/api{full_path}"
            if api_path.startswith('/api/admin/'):
                discovered.append(api_path)
            if len(discovered) >= max(50, int(limit or 1000)):
                return sorted(set(discovered))
    return sorted(set(discovered))


def _is_route_covered_by_rbac_policy(route: str, delegated_patterns: List[str]) -> bool:
    text = str(route or '').strip()
    if not text.startswith('/api/admin/'):
        return True
    for pattern in delegated_patterns:
        try:
            if re.match(pattern, text):
                return True
        except re.error:
            continue
    for registry_pattern in RBAC_ADMIN_POLICY_REGISTRY:
        try:
            if re.match(registry_pattern, text):
                return True
        except re.error:
            continue
    return False


async def _run_preview_adapter_live_check() -> Dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    base_url = _resolve_global_parity_external_base_url().rstrip("/")

    if not base_url:
        return {
            "status": "fail",
            "checked_at": checked_at,
            "base_url": "",
            "checks": {},
            "failure_reasons": ["Preview base URL is not configured"],
            "recommendation": "hold_browser_e2e",
        }

    failure_reasons: List[str] = []
    root_check: Dict[str, Any] = {
        "url": base_url,
        "status_code": 0,
        "ok": False,
        "latency_ms": 0,
        "wrapper_detected": False,
        "react_root_hint": False,
        "markers": {},
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        root_started = time.perf_counter()
        try:
            root_response = await client.get(base_url, timeout=20.0)
            root_latency = round((time.perf_counter() - root_started) * 1000, 2)
            root_probe = _detect_preview_wake_layer_markers(root_response.text)
            root_status_code = int(root_response.status_code)
            root_ok = bool(200 <= root_status_code < 400 and not root_probe["has_wake_layer"])
            root_check = {
                "url": base_url,
                "status_code": root_status_code,
                "ok": root_ok,
                "latency_ms": root_latency,
                "wrapper_detected": bool(root_probe["has_wake_layer"]),
                "react_root_hint": bool(root_probe["has_react_root_hint"]),
                "markers": root_probe["markers"],
            }
            if not root_ok:
                if root_probe["has_wake_layer"]:
                    failure_reasons.append("Preview root is still on wake/adapters wrapper")
                elif root_status_code >= 400:
                    failure_reasons.append(f"Preview root returned HTTP {root_status_code}")
                else:
                    failure_reasons.append("Preview root did not pass live-check criteria")
        except Exception as exc:
            root_latency = round((time.perf_counter() - root_started) * 1000, 2)
            root_check = {
                "url": base_url,
                "status_code": 0,
                "ok": False,
                "latency_ms": root_latency,
                "wrapper_detected": False,
                "react_root_hint": False,
                "markers": {},
                "error": str(exc)[:280],
            }
            failure_reasons.append("Preview root probe failed")

        api_health = await _fetch_json_probe(client, f"{base_url}/api/health")
        api_health["ok"] = bool(api_health.get("status_code") == 200)
        if not api_health["ok"]:
            failure_reasons.append(
                f"/api/health returned {api_health.get('status_code') or 0}"
            )

    status = "pass" if (root_check.get("ok") and api_health.get("ok")) else "fail"
    return {
        "status": status,
        "checked_at": checked_at,
        "base_url": base_url,
        "checks": {
            "preview_root": root_check,
            "api_health": api_health,
        },
        "failure_reasons": failure_reasons,
        "recommendation": "safe_to_run_browser_e2e" if status == "pass" else "hold_browser_e2e",
    }


def _normalize_assigned_host_base(value: str) -> str:
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        return ""
    scheme = parsed.scheme or "https"
    return f"{scheme}://{parsed.netloc}".rstrip("/")


def _read_proc_env_value(key: str) -> str:
    lookup = str(key or "").strip()
    if not lookup:
        return ""

    for proc_path in (Path("/proc/1/environ"), Path("/proc/self/environ")):
        try:
            raw = proc_path.read_bytes().decode("utf-8", errors="ignore")
        except Exception:
            continue
        for token in raw.split("\x00"):
            if token.startswith(f"{lookup}="):
                return token.split("=", 1)[1].strip()
    return ""


def _read_env_key(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        txt = line.strip()
        if not txt or txt.startswith("#") or "=" not in txt:
            continue
        k, v = txt.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def _resolve_assigned_host_expected_base() -> str:
    candidates: List[str] = [
        str(os.environ.get("PREVIEW_ENDPOINT") or "").strip(),
        str(os.environ.get("preview_endpoint") or "").strip(),
        _read_proc_env_value("PREVIEW_ENDPOINT"),
        _read_proc_env_value("preview_endpoint"),
        _read_env_key(Path("/app/frontend/.env"), "REACT_APP_BACKEND_URL"),
        _read_env_key(Path("/app/frontend/.env"), "EXPO_PUBLIC_BACKEND_URL"),
        str(os.environ.get("FRONTEND_BASE_URL") or "").strip(),
    ]

    for candidate in candidates:
        normalized = _normalize_assigned_host_base(candidate)
        if normalized and ".preview.emergentagent.com" in normalized:
            return normalized

    for candidate in candidates:
        normalized = _normalize_assigned_host_base(candidate)
        if normalized:
            return normalized

    return ""


def _rewrite_or_append_env_key(text: str, key: str, value: str) -> tuple[str, bool]:
    replacement = f"{key}={value}"
    pattern = rf"^{re.escape(key)}=.*$"
    if re.search(pattern, text, flags=re.M):
        updated = re.sub(pattern, replacement, text, flags=re.M)
        return updated, updated != text
    return f"{text}\n{replacement}\n", True


def _sync_assigned_host_env(expected_base_url: str) -> Dict[str, Any]:
    expected = _normalize_assigned_host_base(expected_base_url)
    if not expected:
        return {"applied": False, "reason": "expected_base_missing", "updated_keys": []}

    parsed = urlparse(expected)
    expected_host = str(parsed.netloc or "").strip().lower()
    expected_subdomain = expected_host.split(".preview.emergentagent.com", 1)[0] if expected_host.endswith(".preview.emergentagent.com") else ""

    frontend_path = Path("/app/frontend/.env")
    backend_path = Path("/app/backend/.env")
    updated_keys: List[str] = []

    if frontend_path.exists():
        frontend_text = frontend_path.read_text(encoding="utf-8", errors="ignore")
        fe_updates = {
            "REACT_APP_BACKEND_URL": expected,
            "EXPO_PUBLIC_BACKEND_URL": expected,
            "EXPO_PACKAGER_HOSTNAME": expected,
            "EXPO_PACKAGER_PROXY_URL": expected,
        }
        if expected_subdomain:
            fe_updates["EXPO_TUNNEL_SUBDOMAIN"] = expected_subdomain

        dirty = False
        for key, value in fe_updates.items():
            frontend_text, changed = _rewrite_or_append_env_key(frontend_text, key, value)
            if changed:
                updated_keys.append(f"frontend:{key}")
            dirty = dirty or changed
            os.environ[key] = value

        if dirty:
            frontend_path.write_text(frontend_text, encoding="utf-8")

    if backend_path.exists():
        backend_text = backend_path.read_text(encoding="utf-8", errors="ignore")
        be_updates = {
            "FRONTEND_BASE_URL": expected,
            "SSO_REDIRECT_BASE_URL": expected,
        }
        dirty = False
        for key, value in be_updates.items():
            backend_text, changed = _rewrite_or_append_env_key(backend_text, key, value)
            if changed:
                updated_keys.append(f"backend:{key}")
            dirty = dirty or changed
            os.environ[key] = value

        if dirty:
            backend_path.write_text(backend_text, encoding="utf-8")

    return {
        "applied": bool(updated_keys),
        "expected_base_url": expected,
        "expected_host": expected_host,
        "updated_keys": updated_keys,
    }


async def _restart_assigned_host_services(services: List[str]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for service in services:
        name = str(service or "").strip()
        if not name:
            continue
        if name == "backend":
            results.append(
                {
                    "service": name,
                    "ok": False,
                    "status_code": 409,
                    "latency_ms": 0,
                    "output": "blocked: backend restart disabled for assigned-host guard",
                }
            )
            continue
        started = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "supervisorctl",
                "restart",
                name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            text = ((stdout or b"").decode(errors="ignore") + " " + (stderr or b"").decode(errors="ignore")).strip()
            results.append(
                {
                    "service": name,
                    "ok": proc.returncode == 0,
                    "status_code": int(proc.returncode or 0),
                    "latency_ms": elapsed,
                    "output": text[:260],
                }
            )
        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            results.append(
                {
                    "service": name,
                    "ok": False,
                    "status_code": -1,
                    "latency_ms": elapsed,
                    "output": str(exc)[:260],
                }
            )

    return {
        "applied": bool(results),
        "services": results,
        "all_ok": all(bool(item.get("ok")) for item in results) if results else False,
    }


def _default_assigned_host_guard_config() -> Dict[str, Any]:
    return {
        "enabled": True,
        "check_interval_minutes": 5,
        "failure_streak_threshold": 2,
        "repeated_failure_alert_every": 3,
        "restart_cooldown_minutes": 20,
        "auto_fallback_enabled": True,
        "auto_fix_sync_env": True,
        "auto_fix_restart_services": True,
        "state_change_alerts_enabled": True,
        "in_app_alerts_enabled": True,
        "email_alerts_enabled": True,
        "services_to_restart": ["expo", "expo_manual"],
    }


def _sanitize_assigned_host_guard_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    defaults = _default_assigned_host_guard_config()
    merged = {**defaults, **(raw or {})}
    merged["enabled"] = bool(merged.get("enabled"))
    merged["check_interval_minutes"] = max(1, min(int(merged.get("check_interval_minutes") or defaults["check_interval_minutes"]), 60))
    merged["failure_streak_threshold"] = max(1, min(int(merged.get("failure_streak_threshold") or defaults["failure_streak_threshold"]), 20))
    merged["repeated_failure_alert_every"] = max(1, min(int(merged.get("repeated_failure_alert_every") or defaults["repeated_failure_alert_every"]), 20))
    merged["restart_cooldown_minutes"] = max(1, min(int(merged.get("restart_cooldown_minutes") or defaults["restart_cooldown_minutes"]), 180))
    merged["auto_fallback_enabled"] = bool(merged.get("auto_fallback_enabled"))
    merged["auto_fix_sync_env"] = bool(merged.get("auto_fix_sync_env"))
    merged["auto_fix_restart_services"] = bool(merged.get("auto_fix_restart_services"))
    merged["state_change_alerts_enabled"] = bool(merged.get("state_change_alerts_enabled"))
    merged["in_app_alerts_enabled"] = bool(merged.get("in_app_alerts_enabled"))
    merged["email_alerts_enabled"] = bool(merged.get("email_alerts_enabled"))
    services = merged.get("services_to_restart") if isinstance(merged.get("services_to_restart"), list) else defaults["services_to_restart"]
    allowed_services = {"expo", "expo_manual", "frontend"}
    filtered_services: List[str] = []
    for item in services:
        name = str(item).strip()
        if not name or name == "backend":
            continue
        if name in allowed_services and name not in filtered_services:
            filtered_services.append(name)
    merged["services_to_restart"] = filtered_services[:5] or defaults["services_to_restart"]
    return merged


async def _get_assigned_host_guard_config() -> Dict[str, Any]:
    doc = await db.system_runtime_flags.find_one({"key": ASSIGNED_HOST_GUARD_CONFIG_KEY}, {"_id": 0, "value": 1}) or {}
    return _sanitize_assigned_host_guard_config(doc.get("value") if isinstance(doc.get("value"), dict) else {})


async def _run_assigned_host_probe() -> Dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    expected_base_url = _resolve_assigned_host_expected_base().rstrip("/")
    resolved_external_base_url = _resolve_global_parity_external_base_url().rstrip("/") or expected_base_url

    expected_host = str(urlparse(expected_base_url).netloc or "").lower() if expected_base_url else ""
    resolved_host = str(urlparse(resolved_external_base_url).netloc or "").lower() if resolved_external_base_url else ""

    frontend_env_path = Path("/app/frontend/.env")
    backend_env_path = Path("/app/backend/.env")

    frontend_react = _read_env_key(frontend_env_path, "REACT_APP_BACKEND_URL")
    frontend_expo = _read_env_key(frontend_env_path, "EXPO_PUBLIC_BACKEND_URL")
    frontend_tunnel = _read_env_key(frontend_env_path, "EXPO_TUNNEL_SUBDOMAIN")
    backend_front = _read_env_key(backend_env_path, "FRONTEND_BASE_URL")
    backend_sso = _read_env_key(backend_env_path, "SSO_REDIRECT_BASE_URL")

    expected_subdomain = expected_host.split(".preview.emergentagent.com", 1)[0] if expected_host.endswith(".preview.emergentagent.com") else ""

    checks: Dict[str, Any] = {
        "preview_root": {
            "url": resolved_external_base_url,
            "ok": False,
            "status_code": 0,
            "latency_ms": 0,
            "final_url": "",
            "wrapper_detected": False,
            "react_root_hint": False,
            "markers": {},
        },
        "api_health": {
            "url": f"{resolved_external_base_url}/api/health" if resolved_external_base_url else "",
            "ok": False,
            "status_code": 0,
            "latency_ms": 0,
            "body": {},
        },
        "instance_marker": {
            "url": f"{resolved_external_base_url}/api/system/instance-marker" if resolved_external_base_url else "",
            "ok": False,
            "status_code": 0,
            "latency_ms": 0,
            "body": {},
        },
        "env_alignment": {
            "frontend_react": frontend_react,
            "frontend_expo": frontend_expo,
            "frontend_tunnel_subdomain": frontend_tunnel,
            "backend_frontend_base": backend_front,
            "backend_sso_base": backend_sso,
            "expected_base_url": expected_base_url,
            "expected_host": expected_host,
            "expected_tunnel_subdomain": expected_subdomain,
            "ok": False,
        },
    }

    failure_reasons: List[str] = []
    if not expected_base_url or not expected_host:
        failure_reasons.append("expected_preview_endpoint_missing")

    if not resolved_external_base_url:
        failure_reasons.append("resolved_external_base_missing")

    host_alignment_ok = bool(expected_host and resolved_host and expected_host == resolved_host)
    if expected_host and resolved_host and not host_alignment_ok:
        failure_reasons.append(f"resolved_host_mismatch:{resolved_host}!={expected_host}")

    if resolved_external_base_url:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            root_started = time.perf_counter()
            try:
                root_response = await client.get(resolved_external_base_url, timeout=20.0)
                root_latency = round((time.perf_counter() - root_started) * 1000, 2)
                root_probe = _detect_preview_wake_layer_markers(root_response.text)
                markers = root_probe.get("markers") or {}
                hard_blocked = bool(
                    markers.get("ready_to_start_preview")
                    or markers.get("wake_up_servers")
                    or markers.get("no_available_adapters")
                )
                root_ok = bool(200 <= int(root_response.status_code) < 400 and not hard_blocked)
                checks["preview_root"] = {
                    "url": resolved_external_base_url,
                    "ok": root_ok,
                    "status_code": int(root_response.status_code),
                    "latency_ms": root_latency,
                    "final_url": str(root_response.url),
                    "wrapper_detected": hard_blocked,
                    "react_root_hint": bool(root_probe.get("has_react_root_hint")),
                    "markers": markers,
                }
                final_host = str(urlparse(str(root_response.url)).netloc or "").lower()
                if expected_host and final_host and final_host != expected_host:
                    failure_reasons.append(f"redirect_regression:{final_host}!={expected_host}")
                if not root_ok:
                    if hard_blocked:
                        failure_reasons.append("preview_root_wake_wrapper_detected")
                    else:
                        failure_reasons.append(f"preview_root_http_{int(root_response.status_code)}")
            except Exception as exc:
                checks["preview_root"] = {
                    "url": resolved_external_base_url,
                    "ok": False,
                    "status_code": 0,
                    "latency_ms": round((time.perf_counter() - root_started) * 1000, 2),
                    "final_url": "",
                    "wrapper_detected": False,
                    "react_root_hint": False,
                    "markers": {},
                    "error": str(exc)[:280],
                }
                failure_reasons.append("preview_root_probe_failed")

            checks["api_health"] = await _fetch_json_probe(client, f"{resolved_external_base_url}/api/health")
            checks["api_health"]["ok"] = bool(checks["api_health"].get("status_code") == 200)
            if not checks["api_health"].get("ok"):
                failure_reasons.append(f"api_health_http_{checks['api_health'].get('status_code')}")

            checks["instance_marker"] = await _fetch_json_probe(client, f"{resolved_external_base_url}/api/system/instance-marker")
            checks["instance_marker"]["ok"] = bool(checks["instance_marker"].get("status_code") == 200)
            marker_body = checks["instance_marker"].get("body") if isinstance(checks["instance_marker"].get("body"), dict) else {}
            marker_domain = str(marker_body.get("current_domain") or "").strip().rstrip("/")
            marker_host = str(urlparse(marker_domain).netloc or "").lower() if marker_domain else ""
            checks["instance_marker"]["marker_host"] = marker_host
            checks["instance_marker"]["marker_domain"] = marker_domain
            if not checks["instance_marker"].get("ok"):
                failure_reasons.append(f"instance_marker_http_{checks['instance_marker'].get('status_code')}")
            elif expected_host and marker_host and marker_host != expected_host:
                failure_reasons.append(f"instance_marker_host_mismatch:{marker_host}!={expected_host}")

    frontend_react_host = str(urlparse(_normalize_assigned_host_base(frontend_react)).netloc or "").lower() if frontend_react else ""
    frontend_expo_host = str(urlparse(_normalize_assigned_host_base(frontend_expo)).netloc or "").lower() if frontend_expo else ""
    backend_front_host = str(urlparse(_normalize_assigned_host_base(backend_front)).netloc or "").lower() if backend_front else ""
    backend_sso_host = str(urlparse(_normalize_assigned_host_base(backend_sso)).netloc or "").lower() if backend_sso else ""
    env_ok = bool(
        expected_host
        and frontend_react_host == expected_host
        and frontend_expo_host == expected_host
        and backend_front_host == expected_host
        and backend_sso_host == expected_host
        and (not expected_subdomain or str(frontend_tunnel or "").strip().lower() == expected_subdomain)
    )
    checks["env_alignment"]["ok"] = env_ok
    checks["env_alignment"]["frontend_react_host"] = frontend_react_host
    checks["env_alignment"]["frontend_expo_host"] = frontend_expo_host
    checks["env_alignment"]["backend_frontend_base_host"] = backend_front_host
    checks["env_alignment"]["backend_sso_base_host"] = backend_sso_host

    if not env_ok:
        failure_reasons.append("env_alignment_mismatch")

    severity = "healthy"
    if failure_reasons:
        severity = "critical" if any(
            reason.startswith("redirect_regression")
            or reason.startswith("api_health_http")
            or reason.startswith("instance_marker_http")
            for reason in failure_reasons
        ) else "high"

    status = "pass" if not failure_reasons else "fail"
    return {
        "checked_at": checked_at,
        "status": status,
        "severity": severity,
        "expected_base_url": expected_base_url,
        "resolved_external_base_url": resolved_external_base_url,
        "expected_host": expected_host,
        "resolved_host": resolved_host,
        "host_alignment_ok": host_alignment_ok,
        "failure_reasons": failure_reasons,
        "checks": checks,
    }


async def _dispatch_assigned_host_alerts(
    *,
    config: Dict[str, Any],
    previous_status: str,
    current_status: str,
    fail_streak: int,
    state_doc: Dict[str, Any],
    run_doc: Dict[str, Any],
) -> Dict[str, Any]:
    should_alert = False
    reason = "none"
    state_change = bool(previous_status and previous_status != current_status)

    if bool(config.get("state_change_alerts_enabled")) and state_change:
        should_alert = True
        reason = f"state_change:{previous_status}->{current_status}"
    elif current_status == "fail":
        repeat_every = int(config.get("repeated_failure_alert_every") or 3)
        min_fail = int(config.get("failure_streak_threshold") or 2)
        last_repeat_streak = int(state_doc.get("last_repeat_alert_streak") or 0)
        if fail_streak >= min_fail and (fail_streak % repeat_every == 0) and fail_streak != last_repeat_streak:
            should_alert = True
            reason = f"repeat_failure_streak:{fail_streak}"

    if not should_alert:
        return {"sent": 0, "failures": 0, "suppressed": True, "reason": reason}

    title = (
        "Assigned Host Guard: RECOVERED"
        if current_status == "pass"
        else "Assigned Host Guard: ALERT"
    )
    msg_reasons = ", ".join((run_doc.get("failure_reasons") or [])[:3]) or "none"
    fallback = run_doc.get("auto_fallback") if isinstance(run_doc.get("auto_fallback"), dict) else {}
    fallback_text = "applied" if fallback.get("applied") else "not-applied"
    message = (
        f"Status={current_status.upper()} | expected={run_doc.get('expected_host') or 'n/a'} | "
        f"resolved={run_doc.get('resolved_host') or 'n/a'} | fail_streak={fail_streak} | "
        f"fallback={fallback_text} | reasons={msg_reasons}"
    )

    admins = await db.users.find(
        {"is_admin": True},
        {"_id": 0, "user_id": 1, "email": 1},
    ).to_list(160)

    sent = 0
    failures = 0

    from utils.notification_helper import create_notification, create_notification_for_email

    for admin in admins:
        user_id = str(admin.get("user_id") or "").strip()
        email = str(admin.get("email") or "").strip()
        if not user_id:
            continue
        try:
            if bool(config.get("in_app_alerts_enabled")) and bool(config.get("email_alerts_enabled")):
                await create_notification_for_email(
                    user_id=user_id,
                    email=email,
                    title=title,
                    message=message,
                    notif_type="assigned_host_guard_alert",
                )
            elif bool(config.get("in_app_alerts_enabled")):
                await create_notification(
                    user_id=user_id,
                    title=title,
                    message=message,
                    notif_type="assigned_host_guard_alert",
                    data={
                        "reason": reason,
                        "target": "/admin-console?category=overview&tab=assigned-host",
                    },
                )
            elif bool(config.get("email_alerts_enabled")):
                await create_notification_for_email(
                    user_id=user_id,
                    email=email,
                    title=title,
                    message=message,
                    notif_type="assigned_host_guard_alert",
                )
            else:
                continue
            sent += 1
        except Exception:
            failures += 1

    return {
        "sent": sent,
        "failures": failures,
        "suppressed": False,
        "reason": reason,
        "state_change": state_change,
    }


async def _run_assigned_host_guard_cycle(
    *,
    triggered_by: str,
    actor_id: str,
    actor_email: str,
    allow_auto_fallback: bool,
    force_fallback: bool = False,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    run_id = f"assigned_host_guard_{uuid.uuid4().hex[:12]}"
    config = await _get_assigned_host_guard_config()

    state_doc = await db.system_runtime_flags.find_one({"key": ASSIGNED_HOST_GUARD_STATE_KEY}, {"_id": 0}) or {}
    previous_status = str(state_doc.get("last_status") or "unknown")
    previous_fail_streak = int(state_doc.get("fail_streak") or 0)

    probe = await _run_assigned_host_probe()
    current_status = str(probe.get("status") or "fail")
    fail_streak = previous_fail_streak + 1 if current_status == "fail" else 0
    max_fail_streak = max(int(state_doc.get("max_fail_streak") or 0), fail_streak)

    fallback: Dict[str, Any] = {
        "eligible": False,
        "applied": False,
        "cooldown_active": False,
        "cooldown_remaining_seconds": 0,
        "actions": [],
    }

    fallback_threshold = int(config.get("failure_streak_threshold") or 2)
    cooldown_minutes = int(config.get("restart_cooldown_minutes") or 20)
    last_fallback_dt = _parse_iso_datetime(str(state_doc.get("last_fallback_at") or ""))
    cooldown_remaining = 0
    if last_fallback_dt:
        elapsed = (now - last_fallback_dt).total_seconds()
        cooldown_total = max(60, cooldown_minutes * 60)
        if elapsed < cooldown_total:
            cooldown_remaining = int(cooldown_total - elapsed)

    eligible = bool(
        allow_auto_fallback
        and bool(config.get("auto_fallback_enabled"))
        and (force_fallback or (current_status == "fail" and fail_streak >= fallback_threshold))
    )
    fallback["eligible"] = eligible
    fallback["cooldown_remaining_seconds"] = cooldown_remaining
    fallback["cooldown_active"] = bool(cooldown_remaining > 0)

    if eligible and (cooldown_remaining <= 0):
        if bool(config.get("auto_fix_sync_env")):
            sync_result = _sync_assigned_host_env(str(probe.get("expected_base_url") or ""))
            fallback["actions"].append({"type": "sync_env", "result": sync_result})
        if bool(config.get("auto_fix_restart_services")):
            restart_result = await _restart_assigned_host_services(config.get("services_to_restart") or [])
            fallback["actions"].append({"type": "restart_services", "result": restart_result})

        fallback["applied"] = bool(fallback.get("actions"))
        if fallback["applied"]:
            probe_after = await _run_assigned_host_probe()
            probe["post_fallback_probe"] = probe_after
            if str(probe_after.get("status") or "") == "pass":
                probe = probe_after
                current_status = "pass"
                fail_streak = 0

    run_doc: Dict[str, Any] = {
        "run_id": run_id,
        "triggered_by": str(triggered_by or "manual:admin")[:120],
        "created_at": now_iso,
        "created_by": actor_id,
        "created_by_email": actor_email,
        "status": current_status,
        "severity": probe.get("severity") or ("healthy" if current_status == "pass" else "high"),
        "expected_base_url": str(probe.get("expected_base_url") or ""),
        "resolved_external_base_url": str(probe.get("resolved_external_base_url") or ""),
        "expected_host": str(probe.get("expected_host") or ""),
        "resolved_host": str(probe.get("resolved_host") or ""),
        "host_alignment_ok": bool(probe.get("host_alignment_ok")),
        "failure_reasons": list(probe.get("failure_reasons") or []),
        "checks": probe.get("checks") if isinstance(probe.get("checks"), dict) else {},
        "fail_streak": fail_streak,
        "max_fail_streak": max_fail_streak,
        "auto_fallback": fallback,
        "config_snapshot": {
            "check_interval_minutes": int(config.get("check_interval_minutes") or 5),
            "failure_streak_threshold": int(config.get("failure_streak_threshold") or 2),
            "repeated_failure_alert_every": int(config.get("repeated_failure_alert_every") or 3),
            "restart_cooldown_minutes": int(config.get("restart_cooldown_minutes") or 20),
            "auto_fallback_enabled": bool(config.get("auto_fallback_enabled")),
            "auto_fix_sync_env": bool(config.get("auto_fix_sync_env")),
            "auto_fix_restart_services": bool(config.get("auto_fix_restart_services")),
        },
    }

    alert_result = await _dispatch_assigned_host_alerts(
        config=config,
        previous_status=previous_status,
        current_status=current_status,
        fail_streak=fail_streak,
        state_doc=state_doc,
        run_doc=run_doc,
    )
    run_doc["alerts"] = alert_result

    await db[ASSIGNED_HOST_GUARD_RUNS_COLLECTION].insert_one({**run_doc})

    next_state = {
        "key": ASSIGNED_HOST_GUARD_STATE_KEY,
        "last_status": current_status,
        "last_run_at": now_iso,
        "last_run_id": run_id,
        "fail_streak": fail_streak,
        "max_fail_streak": max_fail_streak,
        "last_failure_reasons": run_doc.get("failure_reasons") or [],
        "last_alert_reason": alert_result.get("reason"),
        "last_alert_sent": int(alert_result.get("sent") or 0),
        "last_alert_failures": int(alert_result.get("failures") or 0),
        "last_repeat_alert_streak": fail_streak if str(alert_result.get("reason") or "").startswith("repeat_failure_streak") else int(state_doc.get("last_repeat_alert_streak") or 0),
        "updated_at": now_iso,
    }
    if fallback.get("applied"):
        next_state["last_fallback_at"] = now_iso
        next_state["last_fallback_actions"] = fallback.get("actions") or []
    elif state_doc.get("last_fallback_at"):
        next_state["last_fallback_at"] = state_doc.get("last_fallback_at")
        next_state["last_fallback_actions"] = state_doc.get("last_fallback_actions") or []

    await db.system_runtime_flags.update_one(
        {"key": ASSIGNED_HOST_GUARD_STATE_KEY},
        {"$set": next_state},
        upsert=True,
    )

    return run_doc


class GlobalParitySafeConfigUpdate(BaseModel):
    hourly_min_interval_minutes: Optional[int] = None
    nightly_min_interval_minutes: Optional[int] = None
    min_disk_mb: Optional[float] = None
    hard_floor_mb: Optional[float] = None
    max_load_avg: Optional[float] = None
    max_runtime_seconds: Optional[int] = None
    lock_ttl_seconds: Optional[int] = None


class AssignedHostGuardConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    check_interval_minutes: Optional[int] = None
    failure_streak_threshold: Optional[int] = None
    repeated_failure_alert_every: Optional[int] = None
    restart_cooldown_minutes: Optional[int] = None
    auto_fallback_enabled: Optional[bool] = None
    auto_fix_sync_env: Optional[bool] = None
    auto_fix_restart_services: Optional[bool] = None
    state_change_alerts_enabled: Optional[bool] = None
    in_app_alerts_enabled: Optional[bool] = None
    email_alerts_enabled: Optional[bool] = None


def _default_global_parity_safe_config() -> Dict[str, Any]:
    return {
        "hourly_min_interval_minutes": int(os.environ.get("GLOBAL_PARITY_SAFE_HOURLY_MIN_INTERVAL_MINUTES", "45") or 45),
        "nightly_min_interval_minutes": int(os.environ.get("GLOBAL_PARITY_SAFE_NIGHTLY_MIN_INTERVAL_MINUTES", "720") or 720),
        "min_disk_mb": float(os.environ.get("GLOBAL_PARITY_SAFE_MIN_DISK_MB", "220") or 220),
        "hard_floor_mb": float(os.environ.get("GLOBAL_PARITY_SAFE_HARD_FLOOR_MB", "140") or 140),
        "max_load_avg": float(os.environ.get("GLOBAL_PARITY_SAFE_MAX_LOAD_AVG", "12") or 12),
        "max_runtime_seconds": int(os.environ.get("GLOBAL_PARITY_SAFE_MAX_RUNTIME_SECONDS", "120") or 120),
        "lock_ttl_seconds": int(os.environ.get("GLOBAL_PARITY_SAFE_LOCK_TTL_SECONDS", "900") or 900),
        "maintenance_relax_active": False,
        "maintenance_relax_until": "",
        "maintenance_previous_config": {},
    }


def _sanitize_global_parity_safe_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    defaults = _default_global_parity_safe_config()
    merged = {**defaults, **(raw or {})}
    merged["hourly_min_interval_minutes"] = max(0, min(int(merged.get("hourly_min_interval_minutes") or defaults["hourly_min_interval_minutes"]), 1440))
    merged["nightly_min_interval_minutes"] = max(0, min(int(merged.get("nightly_min_interval_minutes") or defaults["nightly_min_interval_minutes"]), 2880))
    merged["min_disk_mb"] = round(max(80.0, min(float(merged.get("min_disk_mb") or defaults["min_disk_mb"]), 4096.0)), 2)
    merged["hard_floor_mb"] = round(max(50.0, min(float(merged.get("hard_floor_mb") or defaults["hard_floor_mb"]), merged["min_disk_mb"])), 2)
    merged["max_load_avg"] = round(max(1.0, min(float(merged.get("max_load_avg") or defaults["max_load_avg"]), 200.0)), 2)
    merged["max_runtime_seconds"] = max(30, min(int(merged.get("max_runtime_seconds") or defaults["max_runtime_seconds"]), 600))
    merged["lock_ttl_seconds"] = max(60, min(int(merged.get("lock_ttl_seconds") or defaults["lock_ttl_seconds"]), 3600))
    return merged


async def _get_global_parity_safe_config() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    doc = await db.system_runtime_flags.find_one({"key": GLOBAL_PARITY_SAFE_CONFIG_KEY}, {"_id": 0, "value": 1}) or {}
    value = dict(doc.get("value") or {})
    config = _sanitize_global_parity_safe_config(value)

    relax_until = _parse_iso_datetime(str(config.get("maintenance_relax_until") or ""))
    previous_cfg = dict(config.get("maintenance_previous_config") or {})
    relax_active = bool(config.get("maintenance_relax_active")) and bool(relax_until and relax_until > now)

    if bool(config.get("maintenance_relax_active")) and relax_until and relax_until <= now and previous_cfg:
        rollback_cfg = _sanitize_global_parity_safe_config(previous_cfg)
        rollback_cfg.update(
            {
                "maintenance_relax_active": False,
                "maintenance_relax_until": "",
                "maintenance_previous_config": {},
                "maintenance_last_roll_back_at": now_iso,
                "updated_at": now_iso,
            }
        )
        await db.system_runtime_flags.update_one(
            {"key": GLOBAL_PARITY_SAFE_CONFIG_KEY},
            {"$set": {"key": GLOBAL_PARITY_SAFE_CONFIG_KEY, "value": rollback_cfg, "updated_at": now_iso}},
            upsert=True,
        )
        config = rollback_cfg
        relax_active = False

    config["maintenance_relax_active"] = relax_active
    if not relax_active:
        config["maintenance_relax_until"] = ""
    return config


async def _build_global_parity_safe_runtime() -> Dict[str, Any]:
    hourly = await db.system_runtime_flags.find_one(
        {"key": "global_parity_audit_hourly_safe_runtime_state"},
        {"_id": 0},
    ) or {}
    nightly = await db.system_runtime_flags.find_one(
        {"key": "global_parity_audit_nightly_safe_runtime_state"},
        {"_id": 0},
    ) or {}

    hour_dt = _parse_iso_datetime(str(hourly.get("updated_at") or ""))
    night_dt = _parse_iso_datetime(str(nightly.get("updated_at") or ""))
    latest = hourly if (hour_dt and (not night_dt or hour_dt >= night_dt)) else nightly if nightly else hourly

    latest_reasons = list((latest.get("safe_reasons") or [])) if isinstance(latest, dict) else []
    active = bool(latest_reasons) or bool((latest or {}).get("fallback_applied"))

    return {
        "safe_mode_active": active,
        "latest_safe_reasons": latest_reasons,
        "latest_runtime_state": latest or {},
        "hourly_state": hourly or {},
        "nightly_state": nightly or {},
    }


async def _build_fee_visibility_visual_runtime() -> Dict[str, Any]:
    hourly = await db.system_runtime_flags.find_one(
        {"key": "fee_visibility_visual_audit_hourly_safe_runtime_state"},
        {"_id": 0},
    ) or {}
    nightly = await db.system_runtime_flags.find_one(
        {"key": "fee_visibility_visual_audit_nightly_safe_runtime_state"},
        {"_id": 0},
    ) or {}

    hour_dt = _parse_iso_datetime(str(hourly.get("updated_at") or ""))
    night_dt = _parse_iso_datetime(str(nightly.get("updated_at") or ""))
    latest = hourly if (hour_dt and (not night_dt or hour_dt >= night_dt)) else nightly if nightly else hourly

    latest_reasons = list((latest.get("safe_reasons") or [])) if isinstance(latest, dict) else []
    active = bool(latest_reasons) or bool((latest or {}).get("fallback_applied"))

    return {
        "safe_mode_active": active,
        "latest_safe_reasons": latest_reasons,
        "latest_runtime_state": latest or {},
        "hourly_state": hourly or {},
        "nightly_state": nightly or {},
    }


def _extract_preview_cache_hygiene_markers(html: str) -> Dict[str, Any]:
    text = str(html or "")
    return {
        "has_embedded_preview_fix": "rac-embedded-preview-viewport-fix" in text,
        "has_sw_cleanup_key": "rac:sw-preview-cleanup-v1" in text,
        "has_old_sw_register": ("register('/sw.js'" in text) or ('register(\"/sw.js\"' in text),
        "has_preview_canonicalization": "__racIsEmergentHost" in text,
    }


async def _run_preview_cache_hygiene_scan(*, triggered_by: str, actor_id: str, actor_email: str) -> Dict[str, Any]:
    expected_base = _resolve_global_parity_external_base_url().rstrip("/")
    expected_host = str(urlparse(expected_base).hostname or "").lower() if expected_base else ""
    now_iso = datetime.now(timezone.utc).isoformat()

    checks: List[Dict[str, Any]] = []
    raw_payload: Dict[str, Any] = {
        "expected_base": expected_base,
        "expected_host": expected_host,
        "checks": checks,
    }

    if not expected_base or not expected_host:
        return {
            "scan_id": f"preview_cache_hygiene_{uuid.uuid4().hex[:12]}",
            "created_at": now_iso,
            "triggered_by": triggered_by,
            "created_by": actor_id,
            "created_by_email": actor_email,
            "status": "fail",
            "severity": "high",
            "summary": "Missing expected preview base URL configuration",
            "pass_count": 0,
            "fail_count": 1,
            "checks": [
                {
                    "key": "expected_preview_config",
                    "status": "fail",
                    "detail": "No expected preview host resolved from env",
                }
            ],
            "raw_payload": raw_payload,
        }

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=False) as client:
        plans_url = f"{expected_base}/subscription/plans?cacheHygiene={int(time.time())}"
        try:
            response = await client.get(plans_url)
            body = response.text[:350000]
            markers = _extract_preview_cache_hygiene_markers(body)
            marker_ok = (
                markers["has_embedded_preview_fix"]
                and markers["has_sw_cleanup_key"]
                and markers["has_preview_canonicalization"]
                and not markers["has_old_sw_register"]
            )
            checks.append(
                {
                    "key": "expected_host_html_markers",
                    "status": "pass" if marker_ok else "fail",
                    "status_code": int(response.status_code),
                    "detail": f"markers={markers}",
                }
            )
            raw_payload["expected_host_markers"] = markers
            raw_payload["expected_status_code"] = int(response.status_code)
        except Exception as exc:
            checks.append(
                {
                    "key": "expected_host_html_markers",
                    "status": "fail",
                    "status_code": 0,
                    "detail": f"request_error={str(exc)[:180]}",
                }
            )

        try:
            stale_probe = await client.get(
                "http://127.0.0.1:3000/subscription/plans",
                headers={"x-forwarded-host": "app.emergent.sh"},
            )
            location = str(stale_probe.headers.get("location") or "")
            redirect_ok = int(stale_probe.status_code) in (301, 302, 307, 308) and expected_host in location
            checks.append(
                {
                    "key": "stale_host_redirect_to_expected",
                    "status": "pass" if redirect_ok else "fail",
                    "status_code": int(stale_probe.status_code),
                    "detail": f"location={location}",
                }
            )
            raw_payload["stale_redirect"] = {
                "status_code": int(stale_probe.status_code),
                "location": location,
            }
        except Exception as exc:
            checks.append(
                {
                    "key": "stale_host_redirect_to_expected",
                    "status": "fail",
                    "status_code": 0,
                    "detail": f"request_error={str(exc)[:180]}",
                }
            )

        try:
            active_probe = await client.get(
                "http://127.0.0.1:3000/subscription/plans",
                headers={"x-forwarded-host": expected_host},
            )
            no_loop_ok = int(active_probe.status_code) == 200
            checks.append(
                {
                    "key": "active_host_no_redirect_loop",
                    "status": "pass" if no_loop_ok else "fail",
                    "status_code": int(active_probe.status_code),
                    "detail": "expected status=200",
                }
            )
            raw_payload["active_host_status"] = int(active_probe.status_code)
        except Exception as exc:
            checks.append(
                {
                    "key": "active_host_no_redirect_loop",
                    "status": "fail",
                    "status_code": 0,
                    "detail": f"request_error={str(exc)[:180]}",
                }
            )

    pass_count = sum(1 for item in checks if str(item.get("status") or "") == "pass")
    fail_count = sum(1 for item in checks if str(item.get("status") or "") == "fail")
    status = "pass" if fail_count == 0 else "fail"
    severity = "low" if status == "pass" else "high" if fail_count >= 2 else "medium"

    return {
        "scan_id": f"preview_cache_hygiene_{uuid.uuid4().hex[:12]}",
        "created_at": now_iso,
        "triggered_by": triggered_by,
        "created_by": actor_id,
        "created_by_email": actor_email,
        "expected_base": expected_base,
        "expected_host": expected_host,
        "status": status,
        "severity": severity,
        "summary": "Preview cache hygiene healthy" if status == "pass" else "Preview cache hygiene drift detected",
        "pass_count": pass_count,
        "fail_count": fail_count,
        "checks": checks,
        "raw_payload": raw_payload,
    }


async def _dispatch_preview_cache_hygiene_alert_if_needed(scan_doc: Dict[str, Any]) -> Dict[str, Any]:
    from utils.notification_helper import create_notification_for_email

    latest = await db[PREVIEW_CACHE_HYGIENE_AUDITS_COLLECTION].find(
        {},
        {"_id": 0, "status": 1},
    ).sort("created_at", -1).limit(5).to_list(5)

    fail_streak = 0
    for item in latest:
        if str(item.get("status") or "") == "fail":
            fail_streak += 1
            continue
        break

    should_alert = fail_streak >= PREVIEW_CACHE_HYGIENE_INCIDENT_MIN_FAIL_STREAK
    state_doc = await db.system_runtime_flags.find_one(
        {"key": PREVIEW_CACHE_HYGIENE_ALERT_STATE_KEY},
        {"_id": 0},
    ) or {}
    prev_streak = int(state_doc.get("last_notified_streak") or 0)
    cooldown_sent_at = _parse_iso_datetime(str(state_doc.get("last_sent_at") or ""))
    now = datetime.now(timezone.utc)
    cooldown_passed = bool(not cooldown_sent_at or (now - cooldown_sent_at).total_seconds() >= 6 * 60 * 60)
    do_send = bool(should_alert and (fail_streak > prev_streak or cooldown_passed))

    sent = 0
    failures = 0
    if do_send:
        admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1, "email": 1}).to_list(120)
        for admin in admins:
            user_id = str(admin.get("user_id") or "").strip()
            email = str(admin.get("email") or "").strip()
            if not user_id:
                continue
            try:
                await create_notification_for_email(
                    user_id=user_id,
                    email=email,
                    title="Preview Cache Hygiene Alert",
                    message=f"Preview cache hygiene failing (streak={fail_streak}). Latest scan: {scan_doc.get('scan_id')}",
                    notif_type="preview_cache_hygiene_alert",
                )
                sent += 1
            except Exception:
                failures += 1

    await db.system_runtime_flags.update_one(
        {"key": PREVIEW_CACHE_HYGIENE_ALERT_STATE_KEY},
        {
            "$set": {
                "key": PREVIEW_CACHE_HYGIENE_ALERT_STATE_KEY,
                "updated_at": now.isoformat(),
                "last_scan_id": scan_doc.get("scan_id"),
                "last_status": scan_doc.get("status"),
                "fail_streak": fail_streak,
                "last_notified_streak": fail_streak if do_send else prev_streak,
                "last_sent_at": now.isoformat() if do_send else str(state_doc.get("last_sent_at") or ""),
                "sent": sent,
                "failures": failures,
            }
        },
        upsert=True,
    )

    return {
        "should_alert": should_alert,
        "did_send": do_send,
        "fail_streak": fail_streak,
        "sent": sent,
        "failures": failures,
    }


async def _open_preview_cache_hygiene_incident_if_needed(scan_doc: Dict[str, Any], alert_result: Dict[str, Any]) -> Dict[str, Any]:
    fail_streak = int(alert_result.get("fail_streak") or 0)
    if str(scan_doc.get("status") or "") != "fail" or fail_streak < PREVIEW_CACHE_HYGIENE_INCIDENT_MIN_FAIL_STREAK:
        return {
            "opened": False,
            "reason": "below_fail_streak_threshold",
            "threshold": PREVIEW_CACHE_HYGIENE_INCIDENT_MIN_FAIL_STREAK,
            "fail_streak": fail_streak,
            "incident": {},
        }

    state_doc = await db.system_runtime_flags.find_one(
        {"key": PREVIEW_CACHE_HYGIENE_INCIDENT_STATE_KEY},
        {"_id": 0},
    ) or {}
    last_scan_id = str(state_doc.get("last_scan_id") or "")
    last_created_at = _parse_iso_datetime(str(state_doc.get("last_created_at") or ""))
    now = datetime.now(timezone.utc)
    if last_scan_id == str(scan_doc.get("scan_id") or ""):
        return {
            "opened": False,
            "reason": "already_opened_for_scan",
            "threshold": PREVIEW_CACHE_HYGIENE_INCIDENT_MIN_FAIL_STREAK,
            "fail_streak": fail_streak,
            "incident": {},
        }
    if last_created_at and (now - last_created_at).total_seconds() < 60 * 60:
        return {
            "opened": False,
            "reason": "incident_cooldown_60m",
            "threshold": PREVIEW_CACHE_HYGIENE_INCIDENT_MIN_FAIL_STREAK,
            "fail_streak": fail_streak,
            "incident": {},
        }

    incident_id = f"preview_cache_inc_{uuid.uuid4().hex[:12]}"
    now_iso = now.isoformat()
    incident_payload = {
        "incident_id": incident_id,
        "incident_type": "preview_cache_hygiene_drift",
        "source": "preview_cache_hygiene_monitor",
        "status": "open",
        "severity": "high",
        "title": "Preview cache hygiene drift detected",
        "summary": f"Preview cache hygiene failing for {fail_streak} consecutive scans.",
        "created_at": now_iso,
        "created_by": str(scan_doc.get("created_by") or "system_admin"),
        "scan_id": str(scan_doc.get("scan_id") or ""),
        "expected_host": str(scan_doc.get("expected_host") or ""),
        "checks": list(scan_doc.get("checks") or []),
        "incident_actions": [
            {
                "action": "opened",
                "actor_id": str(scan_doc.get("created_by") or "system_admin"),
                "actor_email": str(scan_doc.get("created_by_email") or "system@localhost"),
                "at": now_iso,
                "note": f"Auto-opened by preview cache hygiene monitor (fail_streak={fail_streak}).",
            }
        ],
    }
    await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].insert_one({**incident_payload})
    await db.system_runtime_flags.update_one(
        {"key": PREVIEW_CACHE_HYGIENE_INCIDENT_STATE_KEY},
        {
            "$set": {
                "key": PREVIEW_CACHE_HYGIENE_INCIDENT_STATE_KEY,
                "updated_at": now_iso,
                "last_created_at": now_iso,
                "last_scan_id": str(scan_doc.get("scan_id") or ""),
                "last_incident_id": incident_id,
                "last_fail_streak": fail_streak,
            }
        },
        upsert=True,
    )

    return {
        "opened": True,
        "reason": "opened",
        "threshold": PREVIEW_CACHE_HYGIENE_INCIDENT_MIN_FAIL_STREAK,
        "fail_streak": fail_streak,
        "incident": incident_payload,
    }


def _build_fee_visibility_visual_evidence_csv(audit_doc: Dict[str, Any]) -> str:
    lines: List[str] = []
    header = [
        "baseline_key",
        "label",
        "status",
        "best_diff_ratio",
        "best_candidate_path",
        "candidate_paths",
        "reason",
    ]
    lines.append(",".join(header))

    comparisons = list((audit_doc or {}).get("comparisons") or [])
    for item in comparisons:
        candidate_paths = " | ".join([str(path) for path in (item.get("candidate_paths") or [])])
        row = [
            str(item.get("baseline_key") or "").replace('"', '""'),
            str(item.get("label") or "").replace('"', '""'),
            str(item.get("status") or "").replace('"', '""'),
            str(item.get("best_diff_ratio") if item.get("best_diff_ratio") is not None else "").replace('"', '""'),
            str(item.get("best_candidate_path") or "").replace('"', '""'),
            candidate_paths.replace('"', '""'),
            str(item.get("reason") or "").replace('"', '""'),
        ]
        lines.append(",".join([f'"{value}"' for value in row]))
    return "\n".join(lines)


async def _dispatch_fee_visibility_visual_escalation_if_needed(audit_doc: Dict[str, Any]) -> Dict[str, Any]:
    from utils.notification_helper import create_notification_for_email

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    latest_runs = await db[FEE_VISIBILITY_VISUAL_AUDITS_COLLECTION].find(
        {},
        {
            "_id": 0,
            "audit_id": 1,
            "created_at": 1,
            "overall_status": 1,
            "drift_count": 1,
        },
    ).sort("created_at", -1).limit(10).to_list(10)

    consecutive_fail_count = 0
    for item in latest_runs:
        status = str(item.get("overall_status") or "").lower()
        drift_count = int(item.get("drift_count") or 0)
        if status == "fail" and drift_count > 0:
            consecutive_fail_count += 1
            continue
        break

    is_eligible = consecutive_fail_count >= 2
    state_doc = await db.system_runtime_flags.find_one(
        {"key": FEE_VISIBILITY_VISUAL_ESCALATION_STATE_KEY},
        {"_id": 0},
    ) or {}
    last_sent_at = _parse_iso_datetime(str(state_doc.get("last_sent_at") or ""))
    last_notified_streak = int(state_doc.get("last_notified_streak") or 0)

    cooldown_passed = bool(not last_sent_at or (now - last_sent_at).total_seconds() >= 6 * 60 * 60)
    should_send = bool(is_eligible and (consecutive_fail_count > last_notified_streak or cooldown_passed))

    sent = 0
    failures = 0
    recipients: List[str] = []
    title = "Fee Visibility Visual Drift Escalation"
    message = (
        f"Customer-safe fee visibility contract is failing for {consecutive_fail_count} consecutive runs. "
        f"Latest drift count: {int(audit_doc.get('drift_count') or 0)}. "
        f"Audit ID: {audit_doc.get('audit_id') or 'n/a'}."
    )

    if should_send:
        admins = await db.users.find(
            {"is_admin": True, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "user_id": 1, "email": 1},
        ).to_list(120)
        for admin in admins:
            user_id = str(admin.get("user_id") or "").strip()
            email = str(admin.get("email") or "").strip()
            if not user_id:
                continue
            try:
                await create_notification_for_email(
                    user_id=user_id,
                    email=email,
                    title=title,
                    message=message,
                    notif_type="fee_visibility_visual_drift",
                )
                sent += 1
                if email:
                    recipients.append(email)
            except Exception:
                failures += 1

    escalation_state = {
        "key": FEE_VISIBILITY_VISUAL_ESCALATION_STATE_KEY,
        "updated_at": now_iso,
        "last_audit_id": audit_doc.get("audit_id"),
        "last_status": str(audit_doc.get("overall_status") or "unknown"),
        "consecutive_fail_count": consecutive_fail_count,
        "is_eligible": is_eligible,
        "last_notified_streak": consecutive_fail_count if should_send else (0 if not is_eligible else last_notified_streak),
        "last_sent_at": now_iso if should_send else str(state_doc.get("last_sent_at") or ""),
        "sent": sent,
        "failures": failures,
    }
    await db.system_runtime_flags.update_one(
        {"key": FEE_VISIBILITY_VISUAL_ESCALATION_STATE_KEY},
        {"$set": escalation_state},
        upsert=True,
    )

    return {
        "eligible": is_eligible,
        "consecutive_fail_count": consecutive_fail_count,
        "should_send": should_send,
        "sent": sent,
        "failures": failures,
        "recipients": sorted(set(recipients)),
        "cooldown_hours": 6,
    }


async def _open_fee_visibility_visual_incident_if_needed(audit_doc: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    fail_items = [item for item in list(audit_doc.get("comparisons") or []) if str(item.get("status") or "") == "fail"]
    fail_count = len(fail_items)

    if fail_count < FEE_VISIBILITY_VISUAL_INCIDENT_MIN_FAILS:
        return {
            "opened": False,
            "reason": "below_fail_threshold",
            "threshold": FEE_VISIBILITY_VISUAL_INCIDENT_MIN_FAILS,
            "fail_count": fail_count,
            "incident": {},
        }

    signature = "|".join(sorted([str(item.get("baseline_key") or "") for item in fail_items]))
    state_doc = await db.system_runtime_flags.find_one(
        {"key": FEE_VISIBILITY_VISUAL_INCIDENT_STATE_KEY},
        {"_id": 0},
    ) or {}
    prev_signature = str(state_doc.get("last_signature") or "")
    prev_created_at = _parse_iso_datetime(str(state_doc.get("last_created_at") or ""))
    suppress = bool(
        prev_signature
        and signature
        and prev_signature == signature
        and prev_created_at
        and (now - prev_created_at).total_seconds() < 60 * 60
    )
    if suppress:
        return {
            "opened": False,
            "reason": "cooldown_same_signature_60m",
            "threshold": FEE_VISIBILITY_VISUAL_INCIDENT_MIN_FAILS,
            "fail_count": fail_count,
            "incident": {},
        }

    severity = "high" if fail_count >= 3 else "medium"
    incident_id = f"fee_visual_inc_{uuid.uuid4().hex[:12]}"
    incident_payload = {
        "incident_id": incident_id,
        "incident_type": "fee_visibility_visual_drift",
        "source": "fee_visibility_visual_audit",
        "status": "open",
        "severity": severity,
        "title": "Fee Visibility Visual Drift detected",
        "summary": f"Strict visual baseline drift detected on {fail_count} references.",
        "created_at": now_iso,
        "created_by": str(audit_doc.get("created_by") or "system_admin"),
        "audit_id": str(audit_doc.get("audit_id") or ""),
        "diff_threshold": float(audit_doc.get("diff_threshold") or 0.12),
        "drift_count": int(audit_doc.get("drift_count") or 0),
        "missing_count": int(audit_doc.get("missing_count") or 0),
        "fail_baselines": [
            {
                "baseline_key": str(item.get("baseline_key") or ""),
                "label": str(item.get("label") or ""),
                "best_diff_ratio": item.get("best_diff_ratio"),
                "best_candidate_path": str(item.get("best_candidate_path") or ""),
            }
            for item in fail_items
        ],
    }
    await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].insert_one({**incident_payload})

    notify_sent = 0
    notify_failures = 0
    from utils.notification_helper import create_notification_for_email

    admins = await db.users.find(
        {"is_admin": True},
        {"_id": 0, "user_id": 1, "email": 1},
    ).to_list(120)
    for admin in admins:
        user_id = str(admin.get("user_id") or "").strip()
        email = str(admin.get("email") or "").strip()
        if not user_id:
            continue
        try:
            await create_notification_for_email(
                user_id=user_id,
                email=email,
                title="Visual Drift Incident Opened",
                message=f"Incident {incident_id} opened for fee visibility visual drift ({fail_count} failed baselines).",
                notif_type="fee_visibility_visual_incident",
            )
            notify_sent += 1
        except Exception:
            notify_failures += 1

    await db.system_runtime_flags.update_one(
        {"key": FEE_VISIBILITY_VISUAL_INCIDENT_STATE_KEY},
        {
            "$set": {
                "key": FEE_VISIBILITY_VISUAL_INCIDENT_STATE_KEY,
                "updated_at": now_iso,
                "last_created_at": now_iso,
                "last_signature": signature,
                "last_incident_id": incident_id,
                "last_audit_id": str(audit_doc.get("audit_id") or ""),
                "last_fail_count": fail_count,
                "notify_sent": notify_sent,
                "notify_failures": notify_failures,
            }
        },
        upsert=True,
    )

    return {
        "opened": True,
        "reason": "opened",
        "threshold": FEE_VISIBILITY_VISUAL_INCIDENT_MIN_FAILS,
        "fail_count": fail_count,
        "notification": {
            "sent": notify_sent,
            "failures": notify_failures,
        },
        "incident": incident_payload,
    }


def _global_parity_notification_signature(incident_payload: Dict[str, Any]) -> str:
    return "|".join(
        [
            str(incident_payload.get("external_base_url") or ""),
            str(incident_payload.get("local_instance_id") or ""),
            str(incident_payload.get("external_instance_id") or ""),
            str(incident_payload.get("severity") or ""),
        ]
    )


async def _dispatch_global_parity_incident_notifications(
    incident_payload: Dict[str, Any],
    audit_doc: Dict[str, Any],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    state_key = "global_parity_incident_notification_state"

    state = await db.system_runtime_flags.find_one({"key": state_key}, {"_id": 0}) or {}
    last_sent_at = str(state.get("last_sent_at") or "")
    last_signature = str(state.get("last_signature") or "")
    signature = _global_parity_notification_signature(incident_payload)

    suppress = False
    if last_sent_at and signature and signature == last_signature:
        try:
            prev_dt = datetime.fromisoformat(last_sent_at.replace("Z", "+00:00"))
            if prev_dt.tzinfo is None:
                prev_dt = prev_dt.replace(tzinfo=timezone.utc)
            suppress = (now - prev_dt).total_seconds() < 30 * 60
        except Exception:
            suppress = False

    if suppress:
        return {
            "sent": 0,
            "suppressed": True,
            "reason": "cooldown_30m_same_signature",
        }

    sent = 0
    failures = 0
    from utils.notification_helper import create_notification_for_email

    admins = await db.users.find(
        {"is_admin": True},
        {"_id": 0, "user_id": 1, "email": 1},
    ).to_list(120)

    title = "Global Parity Incident"
    message = (
        f"Parity mismatch detected (severity: {incident_payload.get('severity')}). "
        f"Local={incident_payload.get('local_instance_id') or 'n/a'} | "
        f"External={incident_payload.get('external_instance_id') or 'n/a'}"
    )

    for admin in admins:
        user_id = str(admin.get("user_id") or "").strip()
        email = str(admin.get("email") or "").strip()
        if not user_id:
            continue
        try:
            await create_notification_for_email(
                user_id=user_id,
                email=email,
                title=title,
                message=message,
                notif_type="global_parity_incident",
            )
            sent += 1
        except Exception:
            failures += 1

    await db.system_runtime_flags.update_one(
        {"key": state_key},
        {
            "$set": {
                "key": state_key,
                "last_sent_at": now_iso,
                "last_signature": signature,
                "last_incident_id": incident_payload.get("incident_id"),
                "last_audit_id": audit_doc.get("audit_id"),
                "sent": sent,
                "failures": failures,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    return {
        "sent": sent,
        "failures": failures,
        "suppressed": False,
        "reason": "sent",
    }


@router.get("/global-parity-audit/latest")
async def get_global_parity_audit_latest(limit: int = 24, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fetch_limit = max(5, min(int(limit or 24), 100))
    latest = await db[GLOBAL_PARITY_AUDITS_COLLECTION].find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    history = await db[GLOBAL_PARITY_AUDITS_COLLECTION].find(
        {},
        {
            "_id": 0,
            "audit_id": 1,
            "created_at": 1,
            "overall_status": 1,
            "severity": 1,
            "instance_match": 1,
            "incident_id": 1,
            "local_instance_id": 1,
            "external_instance_id": 1,
            "triggered_by": 1,
        },
    ).sort("created_at", -1).limit(fetch_limit).to_list(fetch_limit)

    latest_incident = await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].find_one(
        {"status": {"$in": ["open", "acknowledged"]}},
        {"_id": 0},
        sort=[("created_at", -1)],
    )

    pass_count = sum(1 for item in history if str(item.get("overall_status") or "") == "pass")
    fail_count = sum(1 for item in history if str(item.get("overall_status") or "") == "fail")
    safe_config = await _get_global_parity_safe_config()
    safe_runtime = await _build_global_parity_safe_runtime()

    return {
        "latest": latest or {},
        "history": history or [],
        "trend": {
            "total": len(history),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_rate": round((pass_count / len(history) * 100), 1) if history else 0,
        },
        "latest_open_incident": latest_incident or {},
        "safe_config": safe_config,
        "safe_runtime": safe_runtime,
    }


@router.get("/global-parity-audit/safe-config")
async def get_global_parity_audit_safe_config(user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    return {
        "safe_config": await _get_global_parity_safe_config(),
        "safe_runtime": await _build_global_parity_safe_runtime(),
    }


@router.post("/global-parity-audit/safe-config")
async def update_global_parity_audit_safe_config(body: GlobalParitySafeConfigUpdate, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    current = await _get_global_parity_safe_config()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    merged = _sanitize_global_parity_safe_config({**current, **updates})
    merged["maintenance_relax_active"] = bool(current.get("maintenance_relax_active"))
    merged["maintenance_relax_until"] = str(current.get("maintenance_relax_until") or "")
    merged["maintenance_previous_config"] = dict(current.get("maintenance_previous_config") or {})
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.system_runtime_flags.update_one(
        {"key": GLOBAL_PARITY_SAFE_CONFIG_KEY},
        {"$set": {"key": GLOBAL_PARITY_SAFE_CONFIG_KEY, "value": merged, "updated_at": merged["updated_at"]}},
        upsert=True,
    )
    return {"status": "ok", "safe_config": await _get_global_parity_safe_config()}


@router.post("/global-parity-audit/safe-config/relax-temporary")
async def relax_global_parity_safe_config_temporarily(user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    current = await _get_global_parity_safe_config()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    relax_until_iso = (now + timedelta(minutes=30)).isoformat()

    base_snapshot = {
        "hourly_min_interval_minutes": int(current.get("hourly_min_interval_minutes") or 45),
        "nightly_min_interval_minutes": int(current.get("nightly_min_interval_minutes") or 720),
        "min_disk_mb": float(current.get("min_disk_mb") or 220),
        "hard_floor_mb": float(current.get("hard_floor_mb") or 140),
        "max_load_avg": float(current.get("max_load_avg") or 12),
        "max_runtime_seconds": int(current.get("max_runtime_seconds") or 120),
        "lock_ttl_seconds": int(current.get("lock_ttl_seconds") or 900),
    }

    relaxed = _sanitize_global_parity_safe_config(
        {
            **base_snapshot,
            "hourly_min_interval_minutes": max(0, int(round(base_snapshot["hourly_min_interval_minutes"] * 0.5))),
            "nightly_min_interval_minutes": max(60, int(round(base_snapshot["nightly_min_interval_minutes"] * 0.5))),
            "min_disk_mb": max(100.0, round(base_snapshot["min_disk_mb"] * 0.6, 2)),
            "hard_floor_mb": max(80.0, round(base_snapshot["hard_floor_mb"] * 0.7, 2)),
            "max_load_avg": round(max(base_snapshot["max_load_avg"] + 3, base_snapshot["max_load_avg"] * 1.5), 2),
            "max_runtime_seconds": min(300, int(base_snapshot["max_runtime_seconds"] + 60)),
            "maintenance_relax_active": True,
            "maintenance_relax_until": relax_until_iso,
            "maintenance_previous_config": base_snapshot,
            "maintenance_started_at": now_iso,
            "updated_at": now_iso,
        }
    )

    await db.system_runtime_flags.update_one(
        {"key": GLOBAL_PARITY_SAFE_CONFIG_KEY},
        {"$set": {"key": GLOBAL_PARITY_SAFE_CONFIG_KEY, "value": relaxed, "updated_at": now_iso}},
        upsert=True,
    )

    return {
        "status": "ok",
        "safe_config": await _get_global_parity_safe_config(),
        "message": "Safe guardrails relaxed for 30 minutes. Automatic rollback is enabled.",
    }


@router.post("/global-parity-audit/run")
async def run_global_parity_audit(
    request: Request,
    run_admin_checks: bool = True,
    triggered_by: str = "manual:admin",
    user=Depends(get_current_user),
):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    external_base_url = _resolve_global_parity_external_base_url()
    local_base_url = "http://127.0.0.1:8001"
    token = _extract_request_auth_token(request)
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        local_marker = await _fetch_json_probe(client, f"{local_base_url}/api/system/instance-marker")
        external_marker = await _fetch_json_probe(
            client,
            f"{external_base_url}/api/system/instance-marker" if external_base_url else "",
        ) if external_base_url else {
            "url": "",
            "status_code": 0,
            "ok": False,
            "latency_ms": 0,
            "error": "External base URL not configured",
            "body": {},
        }

        local_cjm_status = {
            "url": f"{local_base_url}/api/admin/critical-journeys/status",
            "status_code": 0,
            "ok": False,
            "latency_ms": 0,
            "body": {},
            "skipped": True,
        }
        local_cjm_run = {
            "url": f"{local_base_url}/api/admin/critical-journeys/run-now",
            "status_code": 0,
            "ok": False,
            "latency_ms": 0,
            "body": {},
            "skipped": True,
        }
        external_cjm_status = {
            "url": f"{external_base_url}/api/admin/critical-journeys/status" if external_base_url else "",
            "status_code": 0,
            "ok": False,
            "latency_ms": 0,
            "body": {},
            "skipped": True,
        }

        if run_admin_checks and token:
            local_cjm_status = await _fetch_json_probe(
                client,
                f"{local_base_url}/api/admin/critical-journeys/status",
                headers=auth_headers,
                timeout_seconds=20.0,
            )
            local_cjm_status["skipped"] = False

            local_cjm_run = await _fetch_json_probe(
                client,
                f"{local_base_url}/api/admin/critical-journeys/run-now",
                headers=auth_headers,
                timeout_seconds=60.0,
            )
            local_cjm_run["skipped"] = False

            if external_base_url:
                external_cjm_status = await _fetch_json_probe(
                    client,
                    f"{external_base_url}/api/admin/critical-journeys/status",
                    headers=auth_headers,
                    timeout_seconds=20.0,
                )
                external_cjm_status["skipped"] = False

    local_instance_id = str((local_marker.get("body") or {}).get("instance_id") or "")
    external_instance_id = str((external_marker.get("body") or {}).get("instance_id") or "")
    instance_match = bool(local_instance_id and external_instance_id and local_instance_id == external_instance_id)

    parity_pass = bool(local_marker.get("ok") and external_marker.get("ok") and instance_match)
    admin_checks_pass = bool(
        local_cjm_status.get("ok")
        and local_cjm_run.get("ok")
        and (
            external_cjm_status.get("ok")
            if not external_cjm_status.get("skipped")
            else True
        )
    )

    overall_status = "pass" if (parity_pass and (admin_checks_pass or not run_admin_checks)) else "fail"
    severity = "low" if overall_status == "pass" else "critical" if not external_marker.get("ok") else "high"

    now_iso = datetime.now(timezone.utc).isoformat()
    incident_payload: Optional[Dict[str, Any]] = None
    if overall_status != "pass":
        incident_id = f"parity_inc_{uuid.uuid4().hex[:12]}"
        incident_payload = {
            "incident_id": incident_id,
            "status": "open",
            "severity": severity,
            "title": "Global parity mismatch detected",
            "summary": "External preview contract diverges from local runtime contract.",
            "created_at": now_iso,
            "created_by": user.user_id,
            "external_base_url": external_base_url,
            "local_instance_id": local_instance_id,
            "external_instance_id": external_instance_id,
        }
        await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].insert_one({**incident_payload})

    audit_doc = {
        "audit_id": f"parity_audit_{uuid.uuid4().hex[:12]}",
        "created_at": now_iso,
        "created_by": user.user_id,
        "created_by_email": user.email,
        "triggered_by": str(triggered_by or "manual:admin")[:120],
        "external_base_url": external_base_url,
        "run_admin_checks": bool(run_admin_checks),
        "overall_status": overall_status,
        "severity": severity,
        "instance_match": instance_match,
        "local_instance_id": local_instance_id,
        "external_instance_id": external_instance_id,
        "checks": {
            "local_marker": local_marker,
            "external_marker": external_marker,
            "local_critical_journey_status": local_cjm_status,
            "local_critical_journey_run_now": local_cjm_run,
            "external_critical_journey_status": external_cjm_status,
        },
        "incident_id": incident_payload.get("incident_id") if incident_payload else "",
    }

    notification_result = {"sent": 0, "failures": 0, "suppressed": False, "reason": "no_incident"}
    if incident_payload:
        try:
            notification_result = await _dispatch_global_parity_incident_notifications(incident_payload, audit_doc)
        except Exception as exc:
            notification_result = {
                "sent": 0,
                "failures": 1,
                "suppressed": False,
                "reason": f"notification_error:{str(exc)[:100]}",
            }

    audit_doc["notification"] = notification_result
    await db[GLOBAL_PARITY_AUDITS_COLLECTION].insert_one({**audit_doc})

    return {
        "status": "ok",
        "audit": audit_doc,
        "incident": incident_payload or {},
        "notification": notification_result,
        "cta": {
            "label": "Open Incident Board",
            "target_tab": "security-incidents",
            "target_category": "security",
            "has_incident": bool(incident_payload),
        },
    }


@router.post("/global-parity-audit/incidents/{incident_id}/ack")
async def acknowledge_global_parity_incident(incident_id: str, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].update_one(
        {"incident_id": incident_id},
        {
            "$set": {
                "status": "acknowledged",
                "acknowledged_at": now_iso,
                "acknowledged_by": user.user_id,
                "acknowledged_by_email": str(getattr(user, "email", "") or ""),
            },
            "$push": {
                "incident_actions": {
                    "action": "acknowledged",
                    "actor_id": user.user_id,
                    "actor_email": str(getattr(user, "email", "") or ""),
                    "at": now_iso,
                    "note": "",
                }
            },
        },
    )
    doc = await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].find_one({"incident_id": incident_id}, {"_id": 0})
    return {"status": "ok", "incident": doc or {}}


@router.post("/global-parity-audit/incidents/{incident_id}/resolve")
async def resolve_global_parity_incident(incident_id: str, note: str = "", user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].update_one(
        {"incident_id": incident_id},
        {
            "$set": {
                "status": "resolved",
                "resolved_at": now_iso,
                "resolved_by": user.user_id,
                "resolved_by_email": str(getattr(user, "email", "") or ""),
                "resolve_note": str(note or "")[:300],
            },
            "$push": {
                "incident_actions": {
                    "action": "resolved",
                    "actor_id": user.user_id,
                    "actor_email": str(getattr(user, "email", "") or ""),
                    "at": now_iso,
                    "note": str(note or "")[:300],
                }
            },
        },
    )
    doc = await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].find_one({"incident_id": incident_id}, {"_id": 0})
    return {"status": "ok", "incident": doc or {}}


@router.get("/fee-visibility-visual-audit/latest")
async def get_fee_visibility_visual_audit_latest(limit: int = 24, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fetch_limit = max(5, min(int(limit or 24), 100))
    latest = await db[FEE_VISIBILITY_VISUAL_AUDITS_COLLECTION].find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    history = await db[FEE_VISIBILITY_VISUAL_AUDITS_COLLECTION].find(
        {},
        {
            "_id": 0,
            "audit_id": 1,
            "created_at": 1,
            "overall_status": 1,
            "severity": 1,
            "drift_count": 1,
            "missing_count": 1,
            "triggered_by": 1,
            "pass_count": 1,
            "fail_count": 1,
            "baseline_count": 1,
        },
    ).sort("created_at", -1).limit(fetch_limit).to_list(fetch_limit)

    pass_count = sum(1 for item in history if str(item.get("overall_status") or "") == "pass")
    fail_count = sum(1 for item in history if str(item.get("overall_status") or "") == "fail")
    runtime = await _build_fee_visibility_visual_runtime()
    escalation_state = await db.system_runtime_flags.find_one(
        {"key": FEE_VISIBILITY_VISUAL_ESCALATION_STATE_KEY},
        {"_id": 0},
    ) or {}
    latest_open_incident = await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].find_one(
        {
            "incident_type": "fee_visibility_visual_drift",
            "status": {"$in": ["open", "acknowledged"]},
        },
        {"_id": 0},
        sort=[("created_at", -1)],
    ) or {}

    return {
        "latest": latest or {},
        "history": history or [],
        "trend": {
            "total": len(history),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_rate": round((pass_count / len(history) * 100), 1) if history else 0,
        },
        "safe_runtime": runtime,
        "escalation_state": escalation_state,
        "latest_open_incident": latest_open_incident,
        "incident_policy": {
            "min_failed_baselines_to_open": FEE_VISIBILITY_VISUAL_INCIDENT_MIN_FAILS,
            "strict_diff_threshold": 0.12,
        },
    }


@router.post("/fee-visibility-visual-audit/run")
async def run_fee_visibility_visual_audit(triggered_by: str = "manual:admin", user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    audit_doc = await asyncio.to_thread(
        build_fee_visibility_visual_audit,
        triggered_by=str(triggered_by or "manual:admin"),
        actor_id=str(getattr(user, "user_id", "system_admin") or "system_admin"),
        actor_email=str(getattr(user, "email", "system@localhost") or "system@localhost"),
    )
    await db[FEE_VISIBILITY_VISUAL_AUDITS_COLLECTION].insert_one({**audit_doc})
    escalation = await _dispatch_fee_visibility_visual_escalation_if_needed(audit_doc)
    incident_result = await _open_fee_visibility_visual_incident_if_needed(audit_doc)
    audit_doc["escalation"] = escalation
    audit_doc["incident"] = incident_result.get("incident") or {}
    await db[FEE_VISIBILITY_VISUAL_AUDITS_COLLECTION].update_one(
        {"audit_id": audit_doc.get("audit_id")},
        {"$set": {"escalation": escalation, "incident": audit_doc.get("incident")}},
    )

    return {
        "status": "ok",
        "audit": audit_doc,
        "safe_runtime": await _build_fee_visibility_visual_runtime(),
        "escalation": escalation,
        "incident": incident_result,
    }


@router.get("/fee-visibility-visual-audit/evidence/latest.json")
async def download_fee_visibility_visual_audit_latest_json(user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    latest = await db[FEE_VISIBILITY_VISUAL_AUDITS_COLLECTION].find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if not latest:
        raise HTTPException(status_code=404, detail="No visual audit evidence available yet")

    from fastapi.responses import Response as FastAPIResponse

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact": "fee_visibility_visual_audit_evidence",
        "audit": latest,
    }
    filename = f"fee-visibility-visual-evidence-{latest.get('audit_id') or 'latest'}.json"
    return FastAPIResponse(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/fee-visibility-visual-audit/evidence/latest.csv")
async def download_fee_visibility_visual_audit_latest_csv(user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    latest = await db[FEE_VISIBILITY_VISUAL_AUDITS_COLLECTION].find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if not latest:
        raise HTTPException(status_code=404, detail="No visual audit evidence available yet")

    from fastapi.responses import Response as FastAPIResponse

    csv_content = _build_fee_visibility_visual_evidence_csv(latest)
    filename = f"fee-visibility-visual-evidence-{latest.get('audit_id') or 'latest'}.csv"
    return FastAPIResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/preview-cache-hygiene/latest")
async def get_preview_cache_hygiene_latest(limit: int = 24, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fetch_limit = max(5, min(int(limit or 24), 100))
    latest = await db[PREVIEW_CACHE_HYGIENE_AUDITS_COLLECTION].find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    history = await db[PREVIEW_CACHE_HYGIENE_AUDITS_COLLECTION].find(
        {},
        {"_id": 0, "scan_id": 1, "created_at": 1, "status": 1, "severity": 1, "pass_count": 1, "fail_count": 1, "triggered_by": 1},
    ).sort("created_at", -1).limit(fetch_limit).to_list(fetch_limit)

    pass_count = sum(1 for item in history if str(item.get("status") or "") == "pass")
    fail_count = sum(1 for item in history if str(item.get("status") or "") == "fail")
    alert_state = await db.system_runtime_flags.find_one({"key": PREVIEW_CACHE_HYGIENE_ALERT_STATE_KEY}, {"_id": 0}) or {}
    latest_open_incident = await db[GLOBAL_PARITY_INCIDENTS_COLLECTION].find_one(
        {"incident_type": "preview_cache_hygiene_drift", "status": {"$in": ["open", "acknowledged"]}},
        {"_id": 0},
        sort=[("created_at", -1)],
    ) or {}

    return {
        "latest": latest or {},
        "history": history or [],
        "trend": {
            "total": len(history),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_rate": round((pass_count / len(history) * 100), 1) if history else 0,
        },
        "alert_state": alert_state,
        "latest_open_incident": latest_open_incident,
        "incident_policy": {
            "min_fail_streak_to_open": PREVIEW_CACHE_HYGIENE_INCIDENT_MIN_FAIL_STREAK,
        },
    }


@router.post("/preview-cache-hygiene/run")
async def run_preview_cache_hygiene_scan(triggered_by: str = "manual:admin", user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    scan_doc = await _run_preview_cache_hygiene_scan(
        triggered_by=str(triggered_by or "manual:admin"),
        actor_id=str(getattr(user, "user_id", "system_admin") or "system_admin"),
        actor_email=str(getattr(user, "email", "system@localhost") or "system@localhost"),
    )
    await db[PREVIEW_CACHE_HYGIENE_AUDITS_COLLECTION].insert_one({**scan_doc})

    alert_result = await _dispatch_preview_cache_hygiene_alert_if_needed(scan_doc)
    incident_result = await _open_preview_cache_hygiene_incident_if_needed(scan_doc, alert_result)
    scan_doc["alert"] = alert_result
    scan_doc["incident"] = incident_result.get("incident") or {}
    await db[PREVIEW_CACHE_HYGIENE_AUDITS_COLLECTION].update_one(
        {"scan_id": scan_doc.get("scan_id")},
        {"$set": {"alert": alert_result, "incident": scan_doc.get("incident")}},
    )

    return {
        "status": "ok",
        "scan": scan_doc,
        "alert": alert_result,
        "incident": incident_result,
    }


@router.get("/preview-browser-e2e/latest")
async def get_preview_browser_e2e_latest(
    limit: int = 30,
    window_days: int = 7,
    user=Depends(get_current_user),
):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fetch_limit = max(5, min(int(limit or 30), 120))
    days = max(1, min(int(window_days or 7), 30))
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    latest = await db[PREVIEW_BROWSER_E2E_RUNS_COLLECTION].find_one({}, {"_id": 0}, sort=[("ran_at", -1)]) or {}
    history = await db[PREVIEW_BROWSER_E2E_RUNS_COLLECTION].find(
        {},
        {
            "_id": 0,
            "run_id": 1,
            "ran_at": 1,
            "status": 1,
            "gate_status": 1,
            "status_reason_code": 1,
            "blocking_reason": 1,
            "external_lane_status": 1,
            "localhost_fallback_status": 1,
            "challenge_detection_guard": 1,
            "checks": 1,
            "screenshots": 1,
            "transition_event": 1,
        },
    ).sort("ran_at", -1).limit(fetch_limit).to_list(fetch_limit)

    trend_rows = await db[PREVIEW_BROWSER_E2E_RUNS_COLLECTION].find(
        {"ran_at": {"$gte": cutoff_iso}},
        {"_id": 0, "status": 1, "gate_status": 1},
    ).to_list(500)

    def _count(rows: List[Dict[str, Any]], status: str) -> int:
        return sum(1 for row in rows if str(row.get("status") or "").lower() == status)

    pass_count = _count(trend_rows, "pass")
    fail_count = _count(trend_rows, "fail")
    blocked_count = _count(trend_rows, "blocked")
    total = len(trend_rows)

    alert_state = await db.system_runtime_flags.find_one(
        {"key": PREVIEW_BROWSER_E2E_ALERT_STATE_KEY},
        {"_id": 0},
    ) or {}
    runtime_state = await db[PREVIEW_BROWSER_E2E_STATE_COLLECTION].find_one({"key": "global"}, {"_id": 0}) or {}
    heartbeat = await db.scheduler_heartbeats.find_one({"job_id": PREVIEW_BROWSER_E2E_JOB_ID}, {"_id": 0}) or {}

    normalized_history = []
    for item in history:
        checks = item.get("checks") if isinstance(item.get("checks"), list) else []
        screenshots = item.get("screenshots") if isinstance(item.get("screenshots"), list) else []
        normalized_history.append(
            {
                "run_id": item.get("run_id"),
                "ran_at": item.get("ran_at"),
                "status": item.get("status"),
                "gate_status": item.get("gate_status"),
                "status_reason_code": item.get("status_reason_code"),
                "blocking_reason": item.get("blocking_reason"),
                "external_lane_status": item.get("external_lane_status"),
                "localhost_fallback_status": item.get("localhost_fallback_status"),
                "challenge_detection_guard": item.get("challenge_detection_guard") or {},
                "checks_count": len(checks),
                "screenshots_count": len(screenshots),
                "transition_event": item.get("transition_event") or {},
            }
        )

    latest_checks = latest.get("checks") if isinstance(latest.get("checks"), list) else []
    latest_screenshots = latest.get("screenshots") if isinstance(latest.get("screenshots"), list) else []

    return {
        "latest": {
            **latest,
            "checks_count": len(latest_checks),
            "screenshots_count": len(latest_screenshots),
        } if latest else {},
        "history": normalized_history,
        "trend": {
            "window_days": days,
            "total": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "blocked_count": blocked_count,
            "pass_rate": round((pass_count / total) * 100, 1) if total else 0,
        },
        "alert_state": alert_state,
        "runtime_state": runtime_state,
        "heartbeat": heartbeat,
        "job_id": PREVIEW_BROWSER_E2E_JOB_ID,
    }


@router.post("/preview-browser-e2e/run")
async def run_preview_browser_e2e_now(triggered_by: str = "manual:admin", user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    state_doc = await db.system_runtime_flags.find_one(
        {"key": PREVIEW_BROWSER_E2E_MANUAL_TRIGGER_FLAG_KEY},
        {"_id": 0},
    ) or {}
    if state_doc.get("running"):
        started_at = parse_iso_datetime(state_doc.get("started_at"))
        if started_at and (now - started_at).total_seconds() < 900:
            raise HTTPException(status_code=409, detail="Preview browser E2E run already in progress")

    await db.system_runtime_flags.update_one(
        {"key": PREVIEW_BROWSER_E2E_MANUAL_TRIGGER_FLAG_KEY},
        {
            "$set": {
                "key": PREVIEW_BROWSER_E2E_MANUAL_TRIGGER_FLAG_KEY,
                "running": True,
                "started_at": now_iso,
                "triggered_by": str(triggered_by or "manual:admin"),
                "triggered_by_user": str(getattr(user, "email", "admin") or "admin"),
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    async def _runner():
        from scheduler_jobs import scheduled_preview_browser_e2e_wake_and_run

        try:
            await scheduled_preview_browser_e2e_wake_and_run()
        finally:
            end_iso = datetime.now(timezone.utc).isoformat()
            await db.system_runtime_flags.update_one(
                {"key": PREVIEW_BROWSER_E2E_MANUAL_TRIGGER_FLAG_KEY},
                {
                    "$set": {
                        "key": PREVIEW_BROWSER_E2E_MANUAL_TRIGGER_FLAG_KEY,
                        "running": False,
                        "ended_at": end_iso,
                        "updated_at": end_iso,
                    }
                },
                upsert=True,
            )

    asyncio.create_task(_runner())
    return {
        "accepted": True,
        "status": "running",
        "triggered_by": str(triggered_by or "manual:admin"),
        "started_at": now_iso,
        "status_endpoint": "/api/admin/platform-health/preview-browser-e2e/latest",
    }


@router.get("/preview-browser-e2e/backfill-false-positives")
async def preview_browser_e2e_backfill_false_positives_preview(
    limit: int = 120,
    window_days: int = 180,
    profile: str = "standard",
    user=Depends(get_current_user),
):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fetch_limit = max(10, min(int(limit or 120), 1000))
    days = max(7, min(int(window_days or 180), 730))
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    runs = await db[PREVIEW_BROWSER_E2E_RUNS_COLLECTION].find(
        {"ran_at": {"$gte": cutoff_iso}},
        {
            "_id": 0,
            "run_id": 1,
            "ran_at": 1,
            "status": 1,
            "status_reason_code": 1,
            "blocking_reason": 1,
            "challenge_detection_guard": 1,
            "localhost_fallback_status": 1,
            "localhost_fallback": 1,
            "checks": 1,
        },
    ).sort("ran_at", -1).limit(fetch_limit).to_list(fetch_limit)

    normalized_profile = _normalize_backfill_profile(profile)
    candidates: List[Dict[str, Any]] = []
    likely_true_challenge = 0
    likely_false_positive = 0
    for row in runs:
        classification = _classify_preview_browser_e2e_false_positive_candidate(row)
        if not classification.get("eligible"):
            continue
        if classification.get("classification") == "likely_true_challenge":
            likely_true_challenge += 1
        if classification.get("classification") == "likely_false_positive":
            likely_false_positive += 1
        if not _profile_accepts_backfill(classification, normalized_profile):
            continue
        candidates.append(
            {
                "run_id": row.get("run_id"),
                "ran_at": row.get("ran_at"),
                "status": row.get("status"),
                "status_reason_code": row.get("status_reason_code"),
                "recommended_status_reason_code": classification.get("status_reason_code_backfill"),
                "heuristics": classification.get("heuristics", []),
                "confidence": classification.get("confidence", 0.0),
                "guard_version": classification.get("guard_version"),
                "strict_marker_count": classification.get("strict_marker_count", 0),
                "soft_marker_count": classification.get("soft_marker_count", 0),
                "app_shell_marker_count": classification.get("app_shell_marker_count", 0),
                "localhost_fallback_status": classification.get("localhost_fallback_status"),
            }
        )

    return {
        "success": True,
        "profile": normalized_profile,
        "profiles": BACKFILL_SIMULATOR_PROFILES,
        "window_days": days,
        "scanned_count": len(runs),
        "candidate_count": len(candidates),
        "likely_false_positive_count": likely_false_positive,
        "likely_true_challenge_count": likely_true_challenge,
        "signal_badge": _derive_backfill_signal_badge(
            scanned_count=len(runs),
            likely_false_positive=likely_false_positive,
            likely_true_challenge=likely_true_challenge,
        ),
        "backfill_version": PREVIEW_BROWSER_E2E_FALSE_POSITIVE_BACKFILL_VERSION,
        "candidates": candidates,
    }


@router.get("/preview-browser-e2e/backfill-false-positives/simulator")
async def preview_browser_e2e_backfill_false_positives_simulator(
    limit: int = 120,
    window_days: int = 180,
    user=Depends(get_current_user),
):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fetch_limit = max(10, min(int(limit or 120), 1000))
    days = max(7, min(int(window_days or 180), 730))
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    runs = await db[PREVIEW_BROWSER_E2E_RUNS_COLLECTION].find(
        {"ran_at": {"$gte": cutoff_iso}},
        {
            "_id": 0,
            "run_id": 1,
            "ran_at": 1,
            "status": 1,
            "status_reason_code": 1,
            "blocking_reason": 1,
            "challenge_detection_guard": 1,
            "localhost_fallback_status": 1,
            "localhost_fallback": 1,
            "checks": 1,
            "backfill_false_positive": 1,
        },
    ).sort("ran_at", -1).limit(fetch_limit).to_list(fetch_limit)

    profile_rows: List[Dict[str, Any]] = []
    for profile_name in ["strict", "standard", "lenient"]:
        would_update = 0
        already_applied = 0
        likely_true_challenge = 0
        likely_false_positive = 0
        sample_candidates: List[Dict[str, Any]] = []

        for row in runs:
            prior_backfill = row.get("backfill_false_positive") if isinstance(row.get("backfill_false_positive"), dict) else {}
            if prior_backfill.get("status") == "applied":
                already_applied += 1
                continue

            classification = _classify_preview_browser_e2e_false_positive_candidate(row)
            if not classification.get("eligible"):
                continue
            if classification.get("classification") == "likely_true_challenge":
                likely_true_challenge += 1
            if classification.get("classification") == "likely_false_positive":
                likely_false_positive += 1

            if not _profile_accepts_backfill(classification, profile_name):
                continue

            recommended_reason = str(classification.get("status_reason_code_backfill") or "NO_BACKFILL_CHANGE").strip()
            if recommended_reason == "NO_BACKFILL_CHANGE":
                continue

            would_update += 1
            if len(sample_candidates) < 3:
                sample_candidates.append(
                    {
                        "run_id": row.get("run_id"),
                        "status_reason_code": row.get("status_reason_code"),
                        "recommended_status_reason_code": recommended_reason,
                        "confidence": classification.get("confidence", 0.0),
                    }
                )

        profile_rows.append(
            {
                "profile": profile_name,
                "would_update_count": would_update,
                "already_applied_count": already_applied,
                "likely_false_positive_count": likely_false_positive,
                "likely_true_challenge_count": likely_true_challenge,
                "signal_badge": _derive_backfill_signal_badge(
                    scanned_count=len(runs),
                    likely_false_positive=likely_false_positive,
                    likely_true_challenge=likely_true_challenge,
                ),
                "sample_candidates": sample_candidates,
            }
        )

    baseline = next((row for row in profile_rows if row.get("profile") == "standard"), None) or {"would_update_count": 0}
    baseline_count = int(baseline.get("would_update_count") or 0)
    for row in profile_rows:
        row["delta_vs_standard"] = int(row.get("would_update_count") or 0) - baseline_count

    return {
        "success": True,
        "window_days": days,
        "scanned_count": len(runs),
        "profiles": BACKFILL_SIMULATOR_PROFILES,
        "simulation": profile_rows,
        "recommended_default_profile": "standard",
    }


@router.post("/preview-browser-e2e/backfill-false-positives")
async def preview_browser_e2e_backfill_false_positives_apply(
    limit: int = 120,
    window_days: int = 180,
    profile: str = "standard",
    dry_run: bool = False,
    user=Depends(get_current_user),
):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fetch_limit = max(10, min(int(limit or 120), 1000))
    days = max(7, min(int(window_days or 180), 730))
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    actor = str(getattr(user, "email", "admin") or "admin")

    runs = await db[PREVIEW_BROWSER_E2E_RUNS_COLLECTION].find(
        {"ran_at": {"$gte": cutoff_iso}},
        {
            "_id": 0,
            "run_id": 1,
            "ran_at": 1,
            "status": 1,
            "status_reason_code": 1,
            "blocking_reason": 1,
            "challenge_detection_guard": 1,
            "localhost_fallback_status": 1,
            "localhost_fallback": 1,
            "checks": 1,
            "backfill_false_positive": 1,
        },
    ).sort("ran_at", -1).limit(fetch_limit).to_list(fetch_limit)

    normalized_profile = _normalize_backfill_profile(profile)
    updates: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    likely_true_challenge = 0
    likely_false_positive = 0

    for row in runs:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue

        prior_backfill = row.get("backfill_false_positive") if isinstance(row.get("backfill_false_positive"), dict) else {}
        if prior_backfill.get("status") == "applied":
            skipped.append({"run_id": run_id, "reason": "already_applied"})
            continue

        classification = _classify_preview_browser_e2e_false_positive_candidate(row)
        if not classification.get("eligible"):
            continue
        if classification.get("classification") == "likely_true_challenge":
            likely_true_challenge += 1
        if classification.get("classification") == "likely_false_positive":
            likely_false_positive += 1
        if not _profile_accepts_backfill(classification, normalized_profile):
            continue

        recommended_reason = str(classification.get("status_reason_code_backfill") or "NO_BACKFILL_CHANGE").strip()
        if recommended_reason == "NO_BACKFILL_CHANGE":
            continue

        previous_reason = str(row.get("status_reason_code") or "")
        patch_payload = {
            "status_reason_code": recommended_reason,
            "availability_contract.status_reason_code": recommended_reason,
            "backfill_false_positive": {
                "status": "applied" if not dry_run else "dry_run",
                "version": PREVIEW_BROWSER_E2E_FALSE_POSITIVE_BACKFILL_VERSION,
                "applied_at": now_iso,
                "applied_by": actor,
                "previous_status_reason_code": previous_reason,
                "recommended_status_reason_code": recommended_reason,
                "classification": classification,
            },
        }

        updates.append(
            {
                "run_id": run_id,
                "ran_at": row.get("ran_at"),
                "previous_status_reason_code": previous_reason,
                "new_status_reason_code": recommended_reason,
                "heuristics": classification.get("heuristics", []),
                "confidence": classification.get("confidence", 0.0),
            }
        )

        if not dry_run:
            await db[PREVIEW_BROWSER_E2E_RUNS_COLLECTION].update_one(
                {"run_id": run_id},
                {"$set": patch_payload},
            )

    return {
        "success": True,
        "dry_run": bool(dry_run),
        "profile": normalized_profile,
        "profiles": BACKFILL_SIMULATOR_PROFILES,
        "window_days": days,
        "scanned_count": len(runs),
        "updated_count": len(updates),
        "skipped_count": len(skipped),
        "likely_false_positive_count": likely_false_positive,
        "likely_true_challenge_count": likely_true_challenge,
        "signal_badge": _derive_backfill_signal_badge(
            scanned_count=len(runs),
            likely_false_positive=likely_false_positive,
            likely_true_challenge=likely_true_challenge,
        ),
        "backfill_version": PREVIEW_BROWSER_E2E_FALSE_POSITIVE_BACKFILL_VERSION,
        "updates": updates,
        "skipped": skipped,
    }


@router.get("/rbac-drift-monitor")
async def admin_rbac_drift_monitor(limit: int = 500, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    scan_limit = max(50, min(int(limit or 500), 2000))
    discovered_routes = _extract_admin_api_routes_for_drift(limit=scan_limit)

    delegated_patterns = [
        r"^/api/admin/employees/",
        r"^/api/admin/access-control/",
        r"^/api/admin/subscription",
        r"^/api/admin/payment",
    ]
    uncovered = [
        route for route in discovered_routes if not _is_route_covered_by_rbac_policy(route, delegated_patterns)
    ]
    drift_status = "PASS" if len(uncovered) == 0 else "ALERT"

    return {
        "success": True,
        "status": drift_status,
        "scanned_routes": len(discovered_routes),
        "uncovered_route_count": len(uncovered),
        "uncovered_routes": uncovered[:80],
        "policy_registry_size": len(RBAC_ADMIN_POLICY_REGISTRY),
    }


@router.get("/rbac-gate-health")
async def admin_rbac_gate_health(user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(days=7)).isoformat()

    denied_count = await db.authorization_audit_log.count_documents(
        {
            "created_at": {"$gte": window_start},
            "outcome": "denied",
            "metadata.path": {"$regex": r"^/api/admin/"},
        }
    )
    allowed_count = await db.authorization_audit_log.count_documents(
        {
            "created_at": {"$gte": window_start},
            "outcome": "allowed",
            "metadata.path": {"$regex": r"^/api/admin/"},
        }
    )

    total = int(denied_count + allowed_count)
    block_rate = round((float(denied_count) / float(total)) if total > 0 else 0.0, 4)
    health_score = 100 if total == 0 else max(45, int(round(100 - (block_rate * 100 * 0.5))))
    status = "healthy" if health_score >= 85 else "watch" if health_score >= 65 else "critical"

    return {
        "success": True,
        "window_days": 7,
        "admin_allowed_events": int(allowed_count),
        "admin_denied_events": int(denied_count),
        "block_rate": block_rate,
        "health_score": health_score,
        "status": status,
    }


@router.get("/preview-adapter-live-check")
async def get_preview_adapter_live_check(force: bool = False, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = time.time()
    cached_payload = _PREVIEW_ADAPTER_LIVE_CHECK_CACHE.get("payload")
    cached_ts = float(_PREVIEW_ADAPTER_LIVE_CHECK_CACHE.get("ts") or 0)
    cache_valid = bool(cached_payload and ((now - cached_ts) <= PREVIEW_ADAPTER_LIVE_CHECK_CACHE_TTL_SECONDS))

    if not force and cache_valid:
        return {
            **cached_payload,
            "cached": True,
            "cache_ttl_seconds": PREVIEW_ADAPTER_LIVE_CHECK_CACHE_TTL_SECONDS,
        }

    payload = await _run_preview_adapter_live_check()
    _PREVIEW_ADAPTER_LIVE_CHECK_CACHE["ts"] = now
    _PREVIEW_ADAPTER_LIVE_CHECK_CACHE["payload"] = payload

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.system_runtime_flags.update_one(
            {"key": PREVIEW_ADAPTER_LIVE_CHECK_STATE_KEY},
            {
                "$set": {
                    "key": PREVIEW_ADAPTER_LIVE_CHECK_STATE_KEY,
                    "value": payload,
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )
    except Exception as exc:
        logger.warning(f"Failed to persist preview adapter live check state: {exc}")

    return {
        **payload,
        "cached": False,
        "cache_ttl_seconds": PREVIEW_ADAPTER_LIVE_CHECK_CACHE_TTL_SECONDS,
    }


@router.get("/assigned-host/latest")
async def get_assigned_host_guard_latest(limit: int = 40, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    fetch_limit = max(5, min(int(limit or 40), 120))
    latest = await db[ASSIGNED_HOST_GUARD_RUNS_COLLECTION].find_one({}, {"_id": 0}, sort=[("created_at", -1)]) or {}
    history_rows = await db[ASSIGNED_HOST_GUARD_RUNS_COLLECTION].find(
        {},
        {
            "_id": 0,
            "run_id": 1,
            "created_at": 1,
            "status": 1,
            "severity": 1,
            "expected_host": 1,
            "resolved_host": 1,
            "failure_reasons": 1,
            "fail_streak": 1,
            "alerts": 1,
            "auto_fallback": 1,
            "triggered_by": 1,
        },
    ).sort("created_at", -1).limit(fetch_limit).to_list(fetch_limit)

    pass_count = sum(1 for item in history_rows if str(item.get("status") or "").lower() == "pass")
    fail_count = sum(1 for item in history_rows if str(item.get("status") or "").lower() == "fail")
    total = len(history_rows)

    state = await db.system_runtime_flags.find_one({"key": ASSIGNED_HOST_GUARD_STATE_KEY}, {"_id": 0}) or {}
    config = await _get_assigned_host_guard_config()
    heartbeat = await db.scheduler_heartbeats.find_one({"job_id": ASSIGNED_HOST_GUARD_HEARTBEAT_ID}, {"_id": 0}) or {}

    return {
        "latest": latest,
        "history": history_rows,
        "trend": {
            "total": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_rate": round((pass_count / total) * 100, 1) if total else 0,
            "current_fail_streak": int(state.get("fail_streak") or 0),
            "max_fail_streak": int(state.get("max_fail_streak") or 0),
        },
        "state": state,
        "config": config,
        "heartbeat": heartbeat,
        "job_id": ASSIGNED_HOST_GUARD_HEARTBEAT_ID,
    }


@router.post("/assigned-host/config")
async def update_assigned_host_guard_config(body: AssignedHostGuardConfigUpdate, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    current = await _get_assigned_host_guard_config()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    merged = _sanitize_assigned_host_guard_config({**current, **updates})
    now_iso = datetime.now(timezone.utc).isoformat()

    await db.system_runtime_flags.update_one(
        {"key": ASSIGNED_HOST_GUARD_CONFIG_KEY},
        {
            "$set": {
                "key": ASSIGNED_HOST_GUARD_CONFIG_KEY,
                "value": merged,
                "updated_at": now_iso,
                "updated_by": str(getattr(user, "email", "admin") or "admin"),
            }
        },
        upsert=True,
    )

    return {
        "status": "ok",
        "config": await _get_assigned_host_guard_config(),
    }


@router.post("/assigned-host/run")
async def run_assigned_host_guard_now(
    triggered_by: str = "manual:admin",
    allow_auto_fallback: bool = True,
    force_fallback: bool = False,
    user=Depends(get_current_user),
):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    run_doc = await _run_assigned_host_guard_cycle(
        triggered_by=str(triggered_by or "manual:admin")[:120],
        actor_id=str(getattr(user, "user_id", "system_admin") or "system_admin"),
        actor_email=str(getattr(user, "email", "system@localhost") or "system@localhost"),
        allow_auto_fallback=bool(allow_auto_fallback),
        force_fallback=bool(force_fallback),
    )

    return {
        "status": "ok",
        "run": run_doc,
        "cta": {
            "label": "Open Assigned Host",
            "target_tab": "assigned-host",
            "target_category": "overview",
        },
    }


async def _safe_collect_with_timeout(coro, timeout_seconds: float, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = await asyncio.wait_for(coro, timeout=timeout_seconds)
        return result if isinstance(result, dict) else fallback
    except Exception as exc:
        logger.warning(f"Timed/degraded collector path: {exc}")
        return fallback


async def _build_enterprise_control_plane_payload() -> Dict[str, Any]:
    latest_run_task = db.enterprise_auto_audit_history.find_one({}, {"_id": 0}, sort=[("run_at", -1)])
    latest_fix_task = db.platform_health_fixes.find_one({}, {"_id": 0}, sort=[("_stored_at", -1)])
    checkpoints_task = db.enterprise_rollback_checkpoints.find({}, {"_id": 0}).sort("created_at", -1).limit(8).to_list(8)

    latest_run, latest_fix, checkpoints = await asyncio.gather(
        latest_run_task,
        latest_fix_task,
        checkpoints_task,
    )
    latest_run = latest_run or {}
    latest_fix = latest_fix or {}
    checkpoints = checkpoints or []

    enforcement_health, tax_reconciliation, auto_remediation_kpis, slo_state = await asyncio.gather(
        _safe_collect_with_timeout(_collect_enforcement_rule_health(), 4.5, {
            "health_score": 0,
            "status": "degraded",
            "enforcement_rules": {},
            "performance_policy": {},
            "latest_admin_tabs_audit": {},
            "latest_regression_gate": {},
            "latest_growth_monitor": {},
            "slo_auto_mitigation": {},
        }),
        _safe_collect_with_timeout(_collect_tax_reconciliation_command_center(window_hours=24), 5.0, {
            "window_hours": 24,
            "overall_status": "unknown",
            "overall_tax_accuracy_rate": 0,
            "overall_avg_webhook_lag_seconds": 0,
            "providers": [],
            "ledger_integrity": {"status": "unknown", "score": 0},
            "receipt_tax_alerts": {"total_in_window": 0, "open_in_window": 0, "status": "unknown"},
        }),
        _safe_collect_with_timeout(_collect_auto_remediation_kpis(), 5.0, {
            "window_24h": {},
            "window_7d": {},
            "executive_rollup": {"status": "degraded"},
        }),
        _safe_collect_with_timeout(_get_slo_auto_mitigation_state(), 2.5, {
            "policy": _normalize_slo_auto_mitigation_policy({}),
            "runtime": {},
            "current_performance": {},
        }),
    )

    actions = latest_fix.get("actions", []) if isinstance(latest_fix, dict) else []
    stale_urls_before = int((latest_fix.get("before") or {}).get("stale_urls", 0)) if isinstance(latest_fix, dict) else 0
    stale_urls_after = int((latest_fix.get("after") or {}).get("stale_urls", 0)) if isinstance(latest_fix, dict) else 0
    total_fixed = max(stale_urls_before - stale_urls_after, 0)
    caches_cleared = 0
    rebuild_status = "unknown"
    for action in actions:
        if action.get("action") == "clear_caches":
            caches_cleared = len(action.get("cleared") or [])
        if action.get("action") == "rebuild":
            rebuild_status = action.get("status", "unknown")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": {
            "last_run_at": latest_run.get("run_at"),
            "run_id": latest_run.get("run_id"),
            "severity_band": latest_run.get("severity_band", "low"),
            "stages": latest_run.get("pipeline_status", []),
            "final_state": latest_run.get("final_state", {}),
        },
        "latest_autofix_diff": {
            "fixed_at": latest_fix.get("fixed_at") or latest_fix.get("_stored_at"),
            "stale_urls_before": stale_urls_before,
            "stale_urls_after": stale_urls_after,
            "total_fixed": total_fixed,
            "caches_cleared": caches_cleared,
            "rebuild_status": rebuild_status,
        },
        "enforcement_rule_health": enforcement_health,
        "auto_remediation_kpis": auto_remediation_kpis,
        "slo_auto_mitigation": slo_state,
        "tax_reconciliation_command_center": tax_reconciliation,
        "rollback": {
            "latest_checkpoint": latest_run.get("rollback_checkpoint") or (checkpoints[0] if checkpoints else None),
            "recent_checkpoints": checkpoints,
            "total_recent": len(checkpoints),
        },
    }


def _is_valid_email(email: str) -> bool:
    return is_valid_email(email)


async def _get_admin_distribution_recipients() -> List[str]:
    return await get_admin_distribution_recipients()


def _build_enterprise_compliance_report(run_id: str, enforcement_doc: Dict[str, Any], generated_by: str, trigger_mode: str) -> Dict[str, Any]:
    return build_enterprise_compliance_report(run_id, enforcement_doc, generated_by, trigger_mode)


def _build_enterprise_compliance_csv(report: Dict[str, Any]) -> str:
    return build_enterprise_compliance_csv(report)


async def _dispatch_enterprise_compliance_report_email(report: Dict[str, Any], requested_by: str, trigger_mode: str) -> Dict[str, Any]:
    return await dispatch_enterprise_compliance_report_email(report, requested_by, trigger_mode)


def _scan_files_for_patterns(base_dirs: List[str], patterns: List[str], extensions: List[str]) -> List[Dict]:
    return scan_files_for_patterns(base_dirs, patterns, extensions, safe_pattern=SAFE_PATTERN, skip_dirs=SKIP_DIRS)
    """Scan source files for stale URL patterns."""
    issues = []
    for base_dir in base_dirs:
        if not os.path.exists(base_dir):
            continue
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if not any(fname.endswith(ext) for ext in extensions):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", errors="ignore") as f:
                        content = f.read()
                        lines = content.split("\n")
                    # Skip files that already use window.location for their base URL
                    has_safe_base = SAFE_PATTERN in content and "/api" in content
                    for i, line in enumerate(lines):
                        for pat in patterns:
                            if re.search(pat, line):
                                # Check if this line already has the safe pattern
                                if SAFE_PATTERN in line:
                                    continue
                                # Skip lines that are pure variable declarations used as fallback
                                # when the file already has window.location elsewhere
                                if has_safe_base and re.match(r"^\s*const\s+\w+\s*=\s*process\.env\.\w+;\s*$", line):
                                    continue
                                issues.append({
                                    "file": fpath.replace("/app/frontend/", ""),
                                    "line": i + 1,
                                    "code": line.strip()[:120],
                                    "pattern": pat.split(r"\.")[2] if r"\." in pat else pat[:40],
                                    "severity": "high" if "wss://" in line or "ws://" in line else "medium",
                                    "fixable": True,
                                })
                except Exception:
                    pass
    return issues


def _check_build_staleness() -> Dict[str, Any]:
    return check_build_staleness(FRONTEND_DIST, FRONTEND_SRC, FRONTEND_APP, SKIP_DIRS)
    """Check if the production build is stale compared to source."""
    dist_dir = os.path.join(FRONTEND_DIST, "client")
    if not os.path.exists(dist_dir):
        return {"status": "missing", "age_hours": -1, "stale": True, "message": "No production build found"}

    # Get build time from dist modification time
    build_time = os.path.getmtime(dist_dir)
    build_dt = datetime.fromtimestamp(build_time, tz=timezone.utc)
    age = datetime.now(timezone.utc) - build_dt
    age_hours = age.total_seconds() / 3600

    # Check if any source file is newer than the build
    newest_source = 0
    for base in [FRONTEND_SRC, FRONTEND_APP]:
        if not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if any(fname.endswith(ext) for ext in [".tsx", ".ts", ".js", ".jsx"]):
                    mtime = os.path.getmtime(os.path.join(root, fname))
                    newest_source = max(newest_source, mtime)

    source_newer = newest_source > build_time if newest_source > 0 else False

    # Check for stale domains in the build
    stale_in_build = False
    index_files = glob.glob(os.path.join(dist_dir, "_expo/static/js/web/index-*.js"))
    for idx_file in index_files:
        try:
            result = subprocess.run(
                ["grep", "-c", "form-submission-fix\\|js-scanner-suite", idx_file],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip() != "0":
                stale_in_build = True
        except Exception:
            pass

    stale = source_newer or stale_in_build or age_hours > 168  # 7 days
    return {
        "status": "stale" if stale else "fresh",
        "build_time": build_dt.isoformat(),
        "age_hours": round(age_hours, 1),
        "source_newer_than_build": source_newer,
        "stale_domains_in_build": stale_in_build,
        "stale": stale,
        "message": (
            "Stale domains found in build" if stale_in_build
            else "Source files newer than build" if source_newer
            else "Build older than 7 days" if age_hours > 168
            else "Build is fresh"
        ),
    }


def _check_cache_health() -> List[Dict[str, Any]]:
    return check_cache_health(CACHE_DIRS)
    """Check age and size of various caches."""
    results = []
    for cache in CACHE_DIRS:
        path = cache["path"]
        if not os.path.exists(path):
            results.append({
                "label": cache["label"],
                "path": path.replace("/app/frontend/", ""),
                "exists": False,
                "size_mb": 0,
                "age_hours": 0,
                "status": "clean",
                "stale": False,
            })
            continue

        # Calculate size
        total_size = 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total_size += os.path.getsize(fp)
                    except OSError:
                        pass
        except Exception:
            pass
        size_mb = round(total_size / (1024 * 1024), 1)

        # Get age
        mtime = os.path.getmtime(path)
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, tz=timezone.utc)
        age_hours = round(age.total_seconds() / 3600, 1)

        # Stale if cache is too old (except dist which has its own check)
        is_dist = "dist" in path
        stale = (not is_dist and age_hours > 168) or (not is_dist and size_mb > 500)

        results.append({
            "label": cache["label"],
            "path": path.replace("/app/frontend/", ""),
            "exists": True,
            "size_mb": size_mb,
            "age_hours": age_hours,
            "status": "stale" if stale else "healthy",
            "stale": stale,
        })
    return results


def _check_env_consistency() -> Dict[str, Any]:
    return check_env_consistency(FRONTEND_ROOT)
    """Check that .env files have consistent and valid URLs."""
    issues = []
    frontend_env = os.path.join(FRONTEND_ROOT, ".env")
    backend_env = "/app/backend/.env"

    # Check frontend .env
    frontend_url = ""
    if os.path.exists(frontend_env):
        with open(frontend_env) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL=") or line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    val = line.split("=", 1)[1].strip()
                    frontend_url = val
                    if not val.startswith("https://"):
                        issues.append({"field": line.split("=")[0], "issue": "URL does not use HTTPS", "severity": "high"})

    # Check backend .env
    if os.path.exists(backend_env):
        with open(backend_env) as f:
            content = f.read()
            if "MONGO_URL" not in content:
                issues.append({"field": "MONGO_URL", "issue": "Missing from backend .env", "severity": "critical"})

    return {
        "frontend_url": frontend_url,
        "issues": issues,
        "status": "error" if any(i["severity"] == "critical" for i in issues) else "warning" if issues else "healthy",
    }


def _compute_health_score(stale_urls: List, build_info: Dict, cache_health: List, env_info: Dict) -> int:
    return compute_health_score(stale_urls, build_info, cache_health, env_info)
    """Compute overall platform health score 0-100."""
    score = 100

    # Stale URLs: -5 per high severity, -3 per medium
    for issue in stale_urls:
        score -= 5 if issue["severity"] == "high" else 3

    # Build staleness
    if build_info["stale"]:
        if build_info.get("stale_domains_in_build"):
            score -= 25
        elif build_info.get("source_newer_than_build"):
            score -= 15
        else:
            score -= 5

    # Cache health
    for cache in cache_health:
        if cache["stale"]:
            score -= 5

    # Env consistency
    for issue in env_info.get("issues", []):
        score -= 10 if issue["severity"] == "critical" else 5

    return max(0, min(100, score))


def _auto_fix_stale_urls(issues: List[Dict]) -> Dict[str, Any]:
    return auto_fix_stale_urls(issues)
    """Auto-fix stale URL patterns by replacing with window.location.origin."""
    fixed_files = []
    failed_files = []

    for issue in issues:
        if not issue.get("fixable"):
            continue
        fpath = os.path.join("/app/frontend", issue["file"])
        if not os.path.exists(fpath):
            failed_files.append({"file": issue["file"], "reason": "File not found"})
            continue

        try:
            with open(fpath, "r") as f:
                content = f.read()

            original = content

            # Pattern 1: const X = process.env.EXPO_PUBLIC_BACKEND_URL || '';
            content = re.sub(
                r"(const\s+\w+\s*=\s*)process\.env\.EXPO_PUBLIC_BACKEND_URL\s*\|\|\s*''",
                r"\1typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL || '')",
                content
            )
            content = re.sub(
                r"(const\s+\w+\s*=\s*)process\.env\.REACT_APP_BACKEND_URL\s*\|\|\s*''",
                r"\1typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.REACT_APP_BACKEND_URL || '')",
                content
            )

            # Pattern 2: process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || ''
            content = re.sub(
                r"(const\s+\w+\s*=\s*)process\.env\.EXPO_PUBLIC_BACKEND_URL\s*\|\|\s*process\.env\.REACT_APP_BACKEND_URL\s*\|\|\s*''",
                r"\1typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '')",
                content
            )
            content = re.sub(
                r"(const\s+\w+\s*=\s*)process\.env\.REACT_APP_BACKEND_URL\s*\|\|\s*process\.env\.EXPO_PUBLIC_BACKEND_URL\s*\|\|\s*''",
                r"\1typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.REACT_APP_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL || '')",
                content
            )

            # Pattern 3: WebSocket URL replacements
            content = re.sub(
                r"\(process\.env\.EXPO_PUBLIC_BACKEND_URL\s*\|\|\s*''\)\.replace\('https://',\s*'wss://'\)\.replace\('http://',\s*'ws://'\)",
                "(typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL || '')).replace('https://', 'wss://').replace('http://', 'ws://')",
                content
            )

            if content != original:
                with open(fpath, "w") as f:
                    f.write(content)
                fixed_files.append(issue["file"])
            else:
                failed_files.append({"file": issue["file"], "reason": "No matching pattern to fix"})

        except Exception as e:
            failed_files.append({"file": issue["file"], "reason": str(e)[:80]})

    return {"fixed": fixed_files, "failed": failed_files, "fixed_count": len(fixed_files)}


def _auto_fix_caches(stale_caches: List[Dict]) -> List[str]:
    return auto_fix_caches(stale_caches)
    """Clear stale caches (excluding dist)."""
    cleared = []
    for cache in stale_caches:
        if not cache["stale"] or "dist" in cache["path"]:
            continue
        full_path = os.path.join("/app/frontend", cache["path"])
        if os.path.exists(full_path):
            try:
                subprocess.run(["rm", "-rf", full_path], timeout=30)
                cleared.append(cache["label"])
            except Exception:
                pass
    return cleared


async def _store_scan_result(result: Dict):
    return await store_scan_result(result)
    """Store scan result in database."""
    to_store = {**result, "_stored_at": datetime.now(timezone.utc).isoformat()}
    await db.platform_health_scans.insert_one(to_store)


@router.get("/scan")
async def scan_platform_health(user=Depends(get_current_user)):
    """Run a full platform health scan."""
    start = time.time()

    # 1. Scan for stale URLs
    stale_urls = _scan_files_for_patterns(
        [FRONTEND_SRC, FRONTEND_APP],
        STALE_URL_PATTERNS,
        [".tsx", ".ts", ".js", ".jsx"]
    )

    # 2. Check build staleness
    build_info = _check_build_staleness()

    # 3. Check cache health
    cache_health = _check_cache_health()

    # 4. Check env consistency
    env_info = _check_env_consistency()

    # 5. Compute overall score
    score = _compute_health_score(stale_urls, build_info, cache_health, env_info)
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 50 else "F"

    result = {
        "score": score,
        "grade": grade,
        "scan_time": round(time.time() - start, 2),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "stale_urls": {"count": len(stale_urls), "issues": stale_urls},
        "build": build_info,
        "caches": cache_health,
        "env": env_info,
        "categories": {
            "stale_urls": {"status": "error" if stale_urls else "healthy", "count": len(stale_urls)},
            "build_freshness": {"status": "error" if build_info["stale"] else "healthy"},
            "cache_health": {"status": "warning" if any(c["stale"] for c in cache_health) else "healthy"},
            "env_consistency": {"status": env_info["status"]},
        },
        "total_issues": len(stale_urls) + (1 if build_info["stale"] else 0) + sum(1 for c in cache_health if c["stale"]) + len(env_info.get("issues", [])),
        "fixable_issues": len([u for u in stale_urls if u.get("fixable")]) + sum(1 for c in cache_health if c["stale"]),
    }

    await _store_scan_result(result)
    return result


@router.get("/overview")
async def platform_health_overview_alias(user=Depends(get_current_user)):
    """Compatibility alias for legacy /api/admin/platform-health/overview checks."""
    return await scan_platform_health(user)


@router.post("/auto-fix")
async def auto_fix_platform(user=Depends(get_current_user)):
    """100% Automated Safe Auto-Fix: fix stale URLs, clear caches, trigger rebuild if needed."""
    start = time.time()

    # 1. Scan first to find issues
    stale_urls = _scan_files_for_patterns(
        [FRONTEND_SRC, FRONTEND_APP],
        STALE_URL_PATTERNS,
        [".tsx", ".ts", ".js", ".jsx"]
    )
    cache_health = _check_cache_health()
    build_info = _check_build_staleness()

    actions = []

    # 2. Auto-fix stale URLs
    if stale_urls:
        url_fix = _auto_fix_stale_urls(stale_urls)
        actions.append({
            "action": "fix_stale_urls",
            "fixed_count": url_fix["fixed_count"],
            "fixed_files": url_fix["fixed"],
            "failed": url_fix["failed"],
        })

    # 3. Clear stale caches
    stale_caches = [c for c in cache_health if c["stale"]]
    if stale_caches:
        cleared = _auto_fix_caches(stale_caches)
        actions.append({"action": "clear_caches", "cleared": cleared})

    # 4. Trigger rebuild if build is stale or URLs were fixed
    needs_rebuild = build_info["stale"] or (stale_urls and any(a.get("fixed_count", 0) > 0 for a in actions))
    rebuild_status = "skipped"
    rebuild_feature_enabled = str(
        os.environ.get("PLATFORM_HEALTH_ENABLE_AUTOFIX_REBUILD") or "0"
    ).strip() == "1"
    if needs_rebuild:
        if rebuild_feature_enabled:
            try:
                export_cmd = (
                    "cd /app/frontend && "
                    f"CI=1 EXPO_NO_INTERACTIVE=1 NODE_OPTIONS={shlex.quote(FRONTEND_EXPORT_NODE_OPTIONS)} "
                    "node node_modules/expo/bin/cli export --platform web && "
                    "sudo supervisorctl restart expo_manual"
                )
                lock_cmd = f"flock -n {shlex.quote(FRONTEND_EXPORT_LOCKFILE)} -c {shlex.quote(export_cmd)}"

                subprocess.Popen(
                    ["bash", "-lc", lock_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                rebuild_status = "triggered"
                actions.append({"action": "rebuild", "status": "triggered", "message": "Production rebuild started in background with build lock"})
            except Exception as e:
                rebuild_status = "failed"
                actions.append({"action": "rebuild", "status": "failed", "error": str(e)[:100]})
        else:
            rebuild_status = "disabled"
            actions.append({
                "action": "rebuild",
                "status": "disabled",
                "message": "Set PLATFORM_HEALTH_ENABLE_AUTOFIX_REBUILD=1 to allow auto-rebuilds",
            })

    # 5. Re-scan to verify
    post_fix_urls = _scan_files_for_patterns(
        [FRONTEND_SRC, FRONTEND_APP],
        STALE_URL_PATTERNS,
        [".tsx", ".ts", ".js", ".jsx"]
    )

    result = {
        "status": "success",
        "fix_time": round(time.time() - start, 2),
        "fixed_at": datetime.now(timezone.utc).isoformat(),
        "actions": actions,
        "before": {"stale_urls": len(stale_urls), "stale_caches": len(stale_caches), "build_stale": build_info["stale"]},
        "after": {"stale_urls": len(post_fix_urls), "rebuild": rebuild_status},
        "urls_remaining": len(post_fix_urls),
    }

    await db.platform_health_fixes.insert_one({**result, "_stored_at": datetime.now(timezone.utc).isoformat()})
    return result


@router.get("/history")
async def get_scan_history(limit: int = 20, user=Depends(get_current_user)):
    """Get recent scan history."""
    cursor = db.platform_health_scans.find(
        {}, {"_id": 0}
    ).sort("_stored_at", -1).limit(limit)
    scans = await cursor.to_list(length=limit)
    return {"scans": scans, "count": len(scans)}


@router.get("/fix-history")
async def get_fix_history(limit: int = 20, user=Depends(get_current_user)):
    """Get recent auto-fix history."""
    cursor = db.platform_health_fixes.find(
        {}, {"_id": 0}
    ).sort("_stored_at", -1).limit(limit)
    fixes = await cursor.to_list(length=limit)
    return {"fixes": fixes, "count": len(fixes)}


@router.get("/boot-policy-reload-spikes")
async def get_boot_policy_reload_spike_summary(minutes: int = 60, user=Depends(get_current_user)):
    safe_minutes = max(5, min(int(minutes), 24 * 60))
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(minutes=safe_minutes)).isoformat()
    current_window_iso = (now - timedelta(minutes=5)).isoformat()

    telemetry_query = {
        "event_type": "should_reload_true",
        "created_at": {"$gte": since_iso},
    }
    current_window_query = {
        "event_type": "should_reload_true",
        "created_at": {"$gte": current_window_iso},
    }

    total_events = int(await db[BOOT_POLICY_RELOAD_TELEMETRY_COLLECTION].count_documents(telemetry_query))
    current_window_count = int(await db[BOOT_POLICY_RELOAD_TELEMETRY_COLLECTION].count_documents(current_window_query))

    by_host_raw = await db[BOOT_POLICY_RELOAD_TELEMETRY_COLLECTION].aggregate(
        [
            {"$match": telemetry_query},
            {"$group": {"_id": "$host", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8},
        ]
    ).to_list(8)

    monitor_state = await db[BOOT_POLICY_RELOAD_MONITOR_STATE_COLLECTION].find_one(
        {"key": BOOT_POLICY_RELOAD_MONITOR_STATE_KEY},
        {"_id": 0},
    ) or {}

    recent_alerts = await db[BOOT_POLICY_RELOAD_MONITOR_EVENTS_COLLECTION].find(
        {},
        {"_id": 0},
    ).sort("alerted_at", -1).limit(10).to_list(10)

    latest_events = await db[BOOT_POLICY_RELOAD_TELEMETRY_COLLECTION].find(
        telemetry_query,
        {
            "_id": 0,
            "created_at": 1,
            "policy_id": 1,
            "host": 1,
            "source": 1,
            "reason": 1,
            "route_path": 1,
            "reload_attempt": 1,
        },
    ).sort("created_at", -1).limit(25).to_list(25)

    return {
        "window_minutes": safe_minutes,
        "since_iso": since_iso,
        "total_events": total_events,
        "current_window_minutes": 5,
        "current_window_count": current_window_count,
        "by_host": [
            {"host": row.get("_id") or "unknown", "count": int(row.get("count") or 0)}
            for row in by_host_raw
        ],
        "monitor_state": monitor_state,
        "recent_alerts": recent_alerts,
        "latest_events": latest_events,
    }


@router.get("/live-services")
async def get_live_services_status(user=Depends(get_current_user)):
    """Aggregated real-time status of all platform services."""
    import psutil
    from utils.ws_manager import ws_manager

    now = datetime.now(timezone.utc)

    # Email stats
    email_pipeline = [
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]
    email_stats_raw = await db.email_logs.aggregate(email_pipeline).to_list(20)
    email_by_status = {r["_id"]: r["count"] for r in email_stats_raw}
    total_emails = sum(email_by_status.values())
    sent_ok = email_by_status.get("sent", 0)
    email_failed = email_by_status.get("failed", 0)

    # Recent email activity (last 1 hour)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    recent_emails = await db.email_logs.count_documents({"sent_at": {"$gte": one_hour_ago}})

    # Push notification subscribers
    push_subs = await db.push_subscriptions.count_documents({})

    # Notification stats
    notif_total = await db.notifications.count_documents({})
    notif_unread = await db.notifications.count_documents({"read": False})
    notif_today = await db.notifications.count_documents({
        "created_at": {"$gte": now.replace(hour=0, minute=0, second=0).isoformat()}
    })

    # Scheduler heartbeats
    heartbeats = await db.scheduler_heartbeats.find(
        {}, {"_id": 0, "job_id": 1, "status": 1, "last_run": 1}
    ).sort("last_run", -1).to_list(50)
    healthy_beats = sum(1 for h in heartbeats if h.get("status") == "healthy")

    # Automation rules
    rules_count = await db.notification_rules.count_documents({})
    rules_enabled = await db.notification_rules.count_documents({"enabled": True})

    # WebSocket connections
    ws_count = sum(len(conns) for conns in ws_manager.connections.values())

    # Active user sessions
    active_sessions = await db.user_sessions.count_documents({"is_active": True})

    # Realtime reconnect/backoff telemetry (best-effort, client-side emitted)
    telemetry_docs = await db.realtime_connection_health_events.find(
        {},
        {"_id": 0, "captured_at": 1, "events": 1},
    ).sort("timestamp", -1).limit(80).to_list(80)

    telemetry_events = []
    telemetry_cutoff_24h = now - timedelta(hours=24)
    telemetry_cutoff_30m = now - timedelta(minutes=30)
    for doc in telemetry_docs:
        for event in (doc.get("events") or [])[:30]:
            if not isinstance(event, dict):
                continue
            dt = _parse_iso_datetime(event.get("timestamp")) or _parse_iso_datetime(doc.get("captured_at")) or now
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < telemetry_cutoff_24h:
                continue
            telemetry_events.append({
                "dt": dt,
                "event_type": str(event.get("event_type") or "unknown"),
                "reconnect_attempt": int(event.get("reconnect_attempt") or 0),
                "backoff_ms": int(event.get("backoff_ms") or 0),
                "consecutive_failures": int(event.get("consecutive_failures") or 0),
                "metadata": event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
            })

    telemetry_events.sort(key=lambda x: x["dt"], reverse=True)
    telemetry_events_30m = [e for e in telemetry_events if e["dt"] >= telemetry_cutoff_30m]
    connect_attempts_30m = sum(1 for e in telemetry_events_30m if e["event_type"] == "connect_attempt")
    connected_30m = sum(1 for e in telemetry_events_30m if e["event_type"] == "connected")
    disconnected_30m = sum(1 for e in telemetry_events_30m if e["event_type"] == "disconnected")
    errors_30m = sum(1 for e in telemetry_events_30m if e["event_type"] == "error")
    backoff_samples_30m = [
        int(e.get("metadata", {}).get("next_backoff_ms") or e.get("backoff_ms") or 0)
        for e in telemetry_events_30m
        if int(e.get("metadata", {}).get("next_backoff_ms") or e.get("backoff_ms") or 0) > 0
    ]
    latest_telemetry = telemetry_events[0] if telemetry_events else None
    latest_backoff_ms = int((latest_telemetry or {}).get("metadata", {}).get("next_backoff_ms") or (latest_telemetry or {}).get("backoff_ms") or 0)
    latest_failures = int((latest_telemetry or {}).get("consecutive_failures") or 0)
    connect_success_rate = round((connected_30m / max(connect_attempts_30m, 1)) * 100, 1) if connect_attempts_30m > 0 else 100.0

    reconnect_health_status = "healthy"
    if latest_backoff_ms >= 45000 or errors_30m >= 12 or latest_failures >= 6 or (disconnected_30m >= 15 and connect_success_rate < 75):
        reconnect_health_status = "critical"
    elif latest_backoff_ms >= 20000 or errors_30m >= 5 or latest_failures >= 3 or (disconnected_30m >= 6 and connect_success_rate < 85):
        reconnect_health_status = "warning"

    # Uptime (process)
    try:
        proc = psutil.Process()
        uptime_secs = (now - datetime.fromtimestamp(proc.create_time(), tz=timezone.utc)).total_seconds()
        uptime_hours = round(uptime_secs / 3600, 1)
    except Exception:
        uptime_hours = 0

    return {
        "timestamp": now.isoformat(),
        "email": {
            "total_sent": total_emails,
            "delivered": sent_ok,
            "failed": email_failed,
            "success_rate": round((sent_ok / total_emails * 100), 1) if total_emails > 0 else 100,
            "last_hour": recent_emails,
        },
        "push": {
            "subscribers": push_subs,
            "configured": True,
        },
        "notifications": {
            "total": notif_total,
            "unread": notif_unread,
            "today": notif_today,
        },
        "scheduler": {
            "heartbeats_total": len(heartbeats),
            "heartbeats_healthy": healthy_beats,
            "rules_total": rules_count,
            "rules_enabled": rules_enabled,
        },
        "realtime": {
            "ws_connections": ws_count,
            "active_sessions": active_sessions,
            "reconnect_health_status": reconnect_health_status,
            "telemetry_window": "30m",
            "connect_attempts_30m": connect_attempts_30m,
            "connected_30m": connected_30m,
            "disconnected_30m": disconnected_30m,
            "errors_30m": errors_30m,
            "connect_success_rate_30m": connect_success_rate,
            "adaptive_backoff": {
                "current_ms": latest_backoff_ms,
                "avg_ms_30m": round(sum(backoff_samples_30m) / max(len(backoff_samples_30m), 1), 1) if backoff_samples_30m else 0,
                "max_ms_30m": max(backoff_samples_30m) if backoff_samples_30m else 0,
            },
            "latest_event": {
                "event_type": (latest_telemetry or {}).get("event_type"),
                "timestamp": latest_telemetry["dt"].isoformat() if latest_telemetry else None,
                "consecutive_failures": latest_failures,
                "close_code": (latest_telemetry or {}).get("metadata", {}).get("close_code"),
                "close_reason": (latest_telemetry or {}).get("metadata", {}).get("close_reason"),
            },
        },
        "uptime_hours": uptime_hours,
    }


@router.get("/fedapay-webhook-integrity")
async def get_fedapay_webhook_integrity(user=Depends(get_current_user)):
    """Admin diagnostics for FedaPay webhook delivery health and self-healing status."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    from routes.fedapay_client import get_current_webhook_url

    now = datetime.now(timezone.utc)
    last_30m = (now - timedelta(minutes=30)).isoformat()
    last_24h = (now - timedelta(hours=24)).isoformat()

    expected_url = get_current_webhook_url()
    latest_sync = await db.fedapay_webhook_sync_history.find_one({}, {"_id": 0}, sort=[("created_at", -1)]) or {}
    latest_delivery = await db.fedapay_webhook_delivery_log.find_one({}, {"_id": 0}, sort=[("received_at", -1)]) or {}

    queued_total = await db.fedapay_webhook_events.count_documents({"status": "queued"})
    retry_total = await db.fedapay_webhook_events.count_documents({"status": "retry"})
    processing_total = await db.fedapay_webhook_events.count_documents({"status": "processing"})
    dead_total = await db.fedapay_webhook_events.count_documents({"status": "dead"})
    processed_24h = await db.fedapay_webhook_events.count_documents(
        {"status": "processed", "updated_at": {"$gte": last_24h}}
    )
    retry_or_dead_30m = await db.fedapay_webhook_events.count_documents(
        {"status": {"$in": ["retry", "dead"]}, "updated_at": {"$gte": last_30m}}
    )

    recent_failures = await db.fedapay_webhook_events.find(
        {"status": {"$in": ["retry", "dead"]}},
        {
            "_id": 0,
            "event_key": 1,
            "status": 1,
            "attempts": 1,
            "last_error": 1,
            "updated_at": 1,
            "next_retry_at": 1,
        },
    ).sort("updated_at", -1).limit(20).to_list(length=20)

    health_status = "healthy"
    if dead_total > 0 or retry_or_dead_30m >= 3:
        health_status = "warning"
    if dead_total >= 5:
        health_status = "critical"

    return {
        "generated_at": now.isoformat(),
        "health_status": health_status,
        "expected_webhook_url": expected_url,
        "latest_sync": latest_sync,
        "latest_delivery": latest_delivery,
        "queue_state": {
            "queued": queued_total,
            "retry": retry_total,
            "processing": processing_total,
            "dead": dead_total,
            "processed_last_24h": processed_24h,
            "retry_or_dead_last_30m": retry_or_dead_30m,
        },
        "recent_failures": recent_failures,
        "recommendations": [
            "Keep FedaPay webhook URL configured exactly as expected_webhook_url",
            "Investigate recent_failures.last_error if retry/dead rises",
            "Use scheduler heartbeat 'fedapay_webhook_self_heal' as primary uptime signal",
        ],
    }


@router.post("/fedapay-webhook-resync-replay")
async def run_fedapay_webhook_resync_replay(limit: int = 30, user=Depends(get_current_user)):
    """Manual recovery action: resync webhook URL and replay dead-letter events."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    safe_limit = max(1, min(int(limit or 30), 100))

    from routes.fedapay_client import sync_webhook_url
    from routes.payments import run_fedapay_webhook_retry_cycle, run_fedapay_webhook_dead_replay_cycle

    now = datetime.now(timezone.utc)
    last_30m = (now - timedelta(minutes=30)).isoformat()

    sync_result = await sync_webhook_url()
    retry_result = await run_fedapay_webhook_retry_cycle(limit=safe_limit)
    dead_replay_result = await run_fedapay_webhook_dead_replay_cycle(limit=safe_limit)

    queued_total = await db.fedapay_webhook_events.count_documents({"status": "queued"})
    retry_total = await db.fedapay_webhook_events.count_documents({"status": "retry"})
    processing_total = await db.fedapay_webhook_events.count_documents({"status": "processing"})
    dead_total = await db.fedapay_webhook_events.count_documents({"status": "dead"})
    processed_24h = await db.fedapay_webhook_events.count_documents(
        {"status": "processed", "updated_at": {"$gte": (now - timedelta(hours=24)).isoformat()}}
    )
    retry_or_dead_30m = await db.fedapay_webhook_events.count_documents(
        {"status": {"$in": ["retry", "dead"]}, "updated_at": {"$gte": last_30m}}
    )

    health_status = "healthy"
    if dead_total > 0 or retry_or_dead_30m >= 3:
        health_status = "warning"
    if dead_total >= 5:
        health_status = "critical"

    queue_state = {
        "queued": queued_total,
        "retry": retry_total,
        "processing": processing_total,
        "dead": dead_total,
        "processed_last_24h": processed_24h,
        "retry_or_dead_last_30m": retry_or_dead_30m,
    }

    action_record = {
        "action": "fedapay_webhook_resync_replay",
        "triggered_by": user.user_id,
        "triggered_at": now.isoformat(),
        "limit": safe_limit,
        "sync_result": sync_result,
        "retry_result": retry_result,
        "dead_replay_result": dead_replay_result,
        "queue_state": queue_state,
        "health_status": health_status,
    }
    await db.fedapay_webhook_manual_actions.insert_one({**action_record})

    return {
        "ok": True,
        "message": "FedaPay resync + dead-event replay executed",
        "action": action_record["action"],
        "triggered_at": action_record["triggered_at"],
        "triggered_by": action_record["triggered_by"],
        "limit": safe_limit,
        "sync_result": sync_result,
        "retry_result": retry_result,
        "dead_replay_result": dead_replay_result,
        "queue_state": queue_state,
        "health_status": health_status,
    }


@router.post("/full-system-audit")
async def run_full_system_audit(
    safe_auto_fix: bool = True,
    run_domain_autofix: bool = True,
    user=Depends(get_current_user),
):
    """Enterprise full-system audit across platform health, subscription drift, integrations, and DB status."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    started = time.time()

    # 1) Baseline scan
    baseline = await scan_platform_health(user)

    # 2) Safe auto-fix (platform-health scope)
    platform_fix = None
    if safe_auto_fix:
        platform_fix = await auto_fix_platform(user)

    # 3) Domain-wide auto-fix sweep
    domain_summary = {"domains_total": 0, "issues_found": 0, "fixes_applied": 0, "failed_domains": []}
    if run_domain_autofix:
        from routes.admin_autofix_engine import DOMAINS, _execute_fix

        domain_summary["domains_total"] = len(DOMAINS)
        for domain_key in DOMAINS:
            try:
                result = await _execute_fix(domain_key)
                domain_summary["issues_found"] += int(result.get("issues_found", 0) or 0)
                domain_summary["fixes_applied"] += int(result.get("fixes_applied", 0) or 0)
            except Exception as exc:
                domain_summary["failed_domains"].append({"domain": domain_key, "error": str(exc)[:120]})

    # 4) Subscription enforcement drift checks
    from routes.subscription_enforcement import EXEMPT_EMAILS

    subscription_drift = {
        "unknown_plan_count": await db.users.count_documents({"subscription_plan": {"$exists": True, "$nin": ["free", "basic", "premium"]}}),
        "premium_without_role_count": await db.users.count_documents({
            "premium_access": True,
            "$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}],
        }),
        "non_admin_full_access_count": await db.users.count_documents({
            "full_access": True,
            "$or": [{"is_admin": {"$ne": True}}, {"is_admin": {"$exists": False}}],
            "email": {"$nin": list(EXEMPT_EMAILS)},
            "premium_access": {"$ne": True},
            "$and": [
                {"$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}]},
            ],
        }),
    }

    if safe_auto_fix:
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.users.update_many(
            {"subscription_plan": {"$exists": True, "$nin": ["free", "basic", "premium"]}},
            {"$set": {"subscription_plan": "free", "subscription_status": "expired", "payment_verified": False, "updated_at": now_iso}},
        )
        await db.users.update_many(
            {
                "premium_access": True,
                "$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}],
            },
            {"$set": {"premium_access": False, "updated_at": now_iso}},
        )
        await db.users.update_many(
            {
                "full_access": True,
                "$or": [{"is_admin": {"$ne": True}}, {"is_admin": {"$exists": False}}],
                "email": {"$nin": list(EXEMPT_EMAILS)},
                "premium_access": {"$ne": True},
                "$and": [{"$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}]}],
            },
            {"$set": {"full_access": False, "updated_at": now_iso, "full_access_revoked_at": now_iso}},
        )

        subscription_drift = {
            "unknown_plan_count": await db.users.count_documents({"subscription_plan": {"$exists": True, "$nin": ["free", "basic", "premium"]}}),
            "premium_without_role_count": await db.users.count_documents({
                "premium_access": True,
                "$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}],
            }),
            "non_admin_full_access_count": await db.users.count_documents({
                "full_access": True,
                "$or": [{"is_admin": {"$ne": True}}, {"is_admin": {"$exists": False}}],
                "email": {"$nin": list(EXEMPT_EMAILS)},
                "premium_access": {"$ne": True},
                "$and": [{"$or": [{"platform_role": {"$exists": False}}, {"platform_role": None}, {"platform_role": ""}]}],
            }),
        }

    # 5) Integration readiness checks
    sso_docs = await db.sso_status.find({}, {"_id": 0, "provider": 1, "healthy": 1}).to_list(20)
    healthy_sso = sum(1 for d in sso_docs if d.get("healthy") is True)
    integration_status = {
        "sso": {
            "providers_total": len(sso_docs),
            "providers_healthy": healthy_sso,
            "status": "healthy" if len(sso_docs) == 0 or healthy_sso == len(sso_docs) else "warning",
        },
        "email": {
            "resend_configured": bool(os.environ.get("RESEND_API_KEY")),
            "status": "healthy" if os.environ.get("RESEND_API_KEY") else "warning",
        },
        "payments": {
            "stripe_configured": bool(os.environ.get("STRIPE_SECRET_KEY")),
            "paypal_configured": bool(os.environ.get("PAYPAL_CLIENT_ID")),
            "fedapay_configured": bool(os.environ.get("FEDAPAY_SECRET_KEY")),
        },
        "iap": {
            "apple_configured": bool(os.environ.get("APPLE_IAP_SHARED_SECRET")),
            "google_configured": bool(os.environ.get("GOOGLE_PLAY_PACKAGE_NAME")),
            "status": "healthy" if (os.environ.get("APPLE_IAP_SHARED_SECRET") and os.environ.get("GOOGLE_PLAY_PACKAGE_NAME")) else "warning",
        },
    }

    recent_paypal_events = await db.webhook_events.count_documents({
        "provider": {"$in": ["paypal", "PAYPAL"]},
        "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()},
    })
    integration_status["payments"]["paypal_sandbox_depth_test"] = {
        "recent_webhook_events_14d": recent_paypal_events,
        "status": "healthy" if recent_paypal_events > 0 else "warning",
    }

    # 6) DB/API reliability snapshot
    db_health = {
        "users_count": await db.users.count_documents({}),
        "sessions_count": await db.user_sessions.count_documents({}),
        "notifications_count": await db.notifications.count_documents({}),
        "status": "healthy",
    }

    from routes.performance_guardian import build_budget_violations_snapshot, guardian_status
    performance_budget_summary = await build_budget_violations_snapshot(db)
    performance_guardian_summary = await guardian_status(None)

    # 6b) Email localization audit for enterprise notification readiness
    try:
        from routes.email_notifications import run_multilingual_template_localization_audit

        email_localization_audit = await run_multilingual_template_localization_audit(
            lang_codes=["fr", "es", "de"],
            purge_invalid_cache=safe_auto_fix,
        )
    except Exception as exc:
        email_localization_audit = {
            "languages": ["fr", "es", "de"],
            "status": "error",
            "summary": {
                "languages_total": 3,
                "languages_passed": 0,
                "languages_failed": 1,
                "templates_total": 0,
                "total_localization_issues": 1,
                "broken_links_found": 0,
            },
            "error": str(exc)[:200],
        }

    # 7) Final scan after fixes
    final_scan = await scan_platform_health(user)

    # Composite score blending health + enforcement drift + integration status
    drift_penalty = min(
        25,
        subscription_drift["unknown_plan_count"] * 4
        + subscription_drift["premium_without_role_count"] * 4
        + subscription_drift["non_admin_full_access_count"] * 2,
    )
    integration_penalty = 0
    if integration_status["sso"]["providers_total"] > 0 and integration_status["sso"]["status"] != "healthy":
        integration_penalty += 5
    localization_penalty = min(
        15,
        int((email_localization_audit.get("summary") or {}).get("languages_failed", 0) or 0) * 3
        + int((email_localization_audit.get("summary") or {}).get("total_localization_issues", 0) or 0),
    )

    composite_score = max(
        0,
        min(
            100,
            int(final_scan.get("score", 0) - drift_penalty - integration_penalty - localization_penalty),
        ),
    )
    grade = "A" if composite_score >= 90 else "B" if composite_score >= 80 else "C" if composite_score >= 70 else "D"

    return {
        "status": "completed",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - started, 2),
        "safe_auto_fix_enabled": safe_auto_fix,
        "domain_autofix_enabled": run_domain_autofix,
        "baseline_scan": baseline,
        "platform_fix": platform_fix,
        "domain_autofix_summary": domain_summary,
        "subscription_enforcement_drift": subscription_drift,
        "integration_status": integration_status,
        "db_health": db_health,
        "performance_budget_summary": performance_budget_summary,
        "performance_guardian_summary": performance_guardian_summary,
        "email_template_localization_audit": email_localization_audit,
        "email_template_localization_multilingual_audit": email_localization_audit,
        "final_scan": final_scan,
        "composite_health": {
            "score": composite_score,
            "grade": grade,
            "target": 100,
        },
    }


def _audit_admin_tabs_structure() -> dict:
    """Scan admin tab/page files and enforce unique normalized naming map."""
    admin_paths = list(Path("/app/frontend/app/admin").glob("*.tsx")) + list(Path("/app/frontend/app/(tabs)").glob("admin*.tsx"))
    normalized: dict[str, list[str]] = {}
    for path in admin_paths:
        stem = path.stem.lower().replace("_", "-")
        key = stem.replace("admin-", "")
        normalized.setdefault(key, []).append(str(path))

    duplicates = {k: v for k, v in normalized.items() if len(v) > 1}
    return {
        "total_admin_pages": len(admin_paths),
        "normalized_keys": sorted(list(normalized.keys())),
        "duplicate_keys": duplicates,
        "is_unique": len(duplicates) == 0,
    }


def _cleanup_platform_caches() -> dict:
    """Safe cleanup for known transient caches/temp files in preview runtime."""
    cleaned = []
    targets = [
        Path("/app/frontend/.cache"),
        Path("/app/frontend/.expo"),
        Path("/tmp"),
    ]
    for target in targets:
        try:
            if target.name == "tmp":
                for p in target.glob("metro-*"):
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                        cleaned.append(str(p))
                for p in target.glob("haste-map-*"):
                    if p.is_file():
                        p.unlink(missing_ok=True)
                        cleaned.append(str(p))
            else:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                    cleaned.append(str(target))
        except Exception:
            continue
    return {"cleaned_paths": cleaned, "cleaned_count": len(cleaned)}


def _derive_severity_band(score: int, issues: int) -> str:
    return derive_severity_band(score, issues)
    """Map latest audit score/issues to severity bands used by rollback policy."""
    if score < 70 or issues >= 10:
        return "critical"
    if score < 85 or issues >= 5:
        return "high"
    if score < 95 or issues > 0:
        return "medium"
    return "low"


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    return parse_iso_datetime(value)
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _provider_label(provider_key: str) -> str:
    return provider_label(provider_key)
    labels = {
        "stripe": "Stripe",
        "paypal": "PayPal",
        "paypal_js": "PayPal JS",
        "fedapay": "FedaPay",
        "mobile_money_fedapay": "FedaPay",
        "iap_apple": "Apple IAP",
        "iap_google": "Google IAP",
    }
    return labels.get(provider_key, provider_key.replace("_", " ").title())


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    return safe_float(value, fallback)
    try:
        return float(value)
    except Exception:
        return fallback


def _compute_ledger_entry_hash(
    *,
    sequence: int,
    prev_hash: str,
    event_type: str,
    transaction_id: str,
    provider: str,
    user_id: str,
    payload: Dict[str, Any],
    created_at: str,
) -> str:
    return compute_ledger_entry_hash(
        sequence=sequence,
        prev_hash=prev_hash,
        event_type=event_type,
        transaction_id=transaction_id,
        provider=provider,
        user_id=user_id,
        payload=payload,
        created_at=created_at,
    )
    hash_input = json.dumps(
        {
            "sequence": sequence,
            "prev_hash": prev_hash,
            "event_type": event_type,
            "transaction_id": transaction_id,
            "provider": provider,
            "user_id": user_id,
            "payload": payload,
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


async def _collect_tax_reconciliation_command_center(window_hours: int = 24) -> Dict[str, Any]:
    """Build real-time per-provider tax accuracy, webhook lag, and ledger-integrity snapshot."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=window_hours)).isoformat()
    tx_docs = await db.payment_transactions.find(
        {"created_at": {"$gte": cutoff}},
        {
            "_id": 0,
            "provider": 1,
            "gateway": 1,
            "payment_method": 1,
            "transaction_id": 1,
            "session_id": 1,
            "status": 1,
            "payment_status": 1,
            "amount": 1,
            "amount_usd": 1,
            "fee": 1,
            "fee_local": 1,
            "subtotal": 1,
            "tax_amount": 1,
            "tax_rate": 1,
            "tax_provider": 1,
            "processing_fee": 1,
            "amount_gross": 1,
            "total_amount": 1,
            "amount_net": 1,
            "created_at": 1,
            "updated_at": 1,
            "webhook_received_at": 1,
            "provider_capture_payload": 1,
        },
    ).sort("created_at", -1).limit(1200).to_list(1200)

    provider_keys = ["stripe", "paypal", "paypal_js", "fedapay", "iap_apple", "iap_google"]
    buckets: Dict[str, Dict[str, Any]] = {
        key: {"total": 0, "accurate": 0, "reconciled": 0, "lag_samples": []}
        for key in provider_keys
    }

    tolerance = 0.01
    for tx in tx_docs:
        provider = str(tx.get("provider") or tx.get("gateway") or tx.get("payment_method") or "").lower()
        if provider == "mobile_money_fedapay":
            provider = "fedapay"
        if provider not in buckets:
            continue

        bucket = buckets[provider]
        bucket["total"] += 1

        subtotal = _safe_float(tx.get("subtotal"), _safe_float(tx.get("amount", tx.get("amount_usd", 0)), 0.0))
        tax_amount = _safe_float(tx.get("tax_amount"), 0.0)
        processing_fee = _safe_float(tx.get("processing_fee"), _safe_float(tx.get("fee", tx.get("fee_local", 0)), 0.0))
        amount_gross = _safe_float(tx.get("amount_gross"), subtotal + tax_amount)
        total_amount = _safe_float(tx.get("total_amount"), amount_gross)
        amount_net = _safe_float(tx.get("amount_net"), max(total_amount - processing_fee, 0.0))

        gross_ok = abs((subtotal + tax_amount) - amount_gross) <= tolerance
        net_ok = abs((total_amount - processing_fee) - amount_net) <= tolerance
        required_ok = tx.get("subtotal") is not None and tx.get("tax_amount") is not None and tx.get("amount_net") is not None
        provider_policy_ok = True
        if provider == "fedapay":
            provider_policy_ok = (
                abs(_safe_float(tx.get("tax_rate", 0), 0.0) - 0.0825) <= 1e-6
                and str(tx.get("tax_provider", "")).lower() == "fedapay_fixed_rate"
                and abs(tax_amount - (subtotal * 0.0825)) <= max(tolerance, 0.02)
            )

        if gross_ok and net_ok and required_ok and provider_policy_ok:
            bucket["accurate"] += 1

        status = str(tx.get("status") or tx.get("payment_status") or "").lower()
        if status in {"completed", "paid", "active", "success", "succeeded", "expired"}:
            bucket["reconciled"] += 1

        created_at = _parse_iso_datetime(tx.get("created_at"))
        webhook_at = _parse_iso_datetime(tx.get("webhook_received_at"))
        if not webhook_at and tx.get("provider_capture_payload"):
            webhook_at = _parse_iso_datetime(tx.get("updated_at"))

        if created_at and webhook_at:
            lag = max((webhook_at - created_at).total_seconds(), 0)
            bucket["lag_samples"].append(lag)

    provider_rows = []
    total_all = 0
    accurate_all = 0
    lag_all_samples = []

    for key in provider_keys:
        b = buckets[key]
        total = int(b["total"])
        accurate = int(b["accurate"])
        reconciled = int(b["reconciled"])
        tax_accuracy = round((accurate / total) * 100, 1) if total else 100.0
        reconcile_rate = round((reconciled / total) * 100, 1) if total else 100.0
        avg_lag = round(sum(b["lag_samples"]) / len(b["lag_samples"]), 1) if b["lag_samples"] else 0.0
        lag_status = "healthy" if avg_lag < 60 else "warning" if avg_lag <= 300 else "critical"

        provider_rows.append(
            {
                "provider": key,
                "provider_label": _provider_label(key),
                "sample_count": total,
                "accurate_count": accurate,
                "reconciled_count": reconciled,
                "tax_accuracy_rate": tax_accuracy,
                "reconciliation_rate": reconcile_rate,
                "avg_webhook_lag_seconds": avg_lag,
                "lag_status": lag_status,
                "status": "healthy" if tax_accuracy >= 99 and lag_status == "healthy" else "warning" if tax_accuracy >= 95 else "critical",
            }
        )

        total_all += total
        accurate_all += accurate
        lag_all_samples.extend(b["lag_samples"])

    ledger_docs = await db.financial_ledger_entries.find(
        {},
        {
            "_id": 0,
            "sequence": 1,
            "event_type": 1,
            "transaction_id": 1,
            "provider": 1,
            "user_id": 1,
            "payload": 1,
            "prev_hash": 1,
            "entry_hash": 1,
            "created_at": 1,
        },
    ).sort("sequence", 1).limit(800).to_list(800)

    links_checked = 0
    links_valid = 0
    hash_checked = 0
    hash_valid = 0
    prev_entry_hash = ""

    for idx, entry in enumerate(ledger_docs):
        if idx == 0:
            prev_entry_hash = entry.get("entry_hash", "")
            continue

        links_checked += 1
        if entry.get("prev_hash") == prev_entry_hash:
            links_valid += 1

        hash_checked += 1
        expected_hash = _compute_ledger_entry_hash(
            sequence=int(entry.get("sequence", 0) or 0),
            prev_hash=str(entry.get("prev_hash", "")),
            event_type=str(entry.get("event_type", "")),
            transaction_id=str(entry.get("transaction_id", "")),
            provider=str(entry.get("provider", "")),
            user_id=str(entry.get("user_id", "")),
            payload=entry.get("payload", {}) or {},
            created_at=str(entry.get("created_at", "")),
        )
        if expected_hash == entry.get("entry_hash"):
            hash_valid += 1

        prev_entry_hash = entry.get("entry_hash", "")

    link_integrity = round((links_valid / links_checked) * 100, 1) if links_checked else 100.0
    hash_integrity = round((hash_valid / hash_checked) * 100, 1) if hash_checked else 100.0
    ledger_score = round((link_integrity + hash_integrity) / 2, 1)

    tax_alert_total = await db.payment_tax_alerts.count_documents({"created_at": {"$gte": cutoff}})
    tax_alert_open = await db.payment_tax_alerts.count_documents({"created_at": {"$gte": cutoff}, "resolved": False})

    avg_lag_all = round(sum(lag_all_samples) / len(lag_all_samples), 1) if lag_all_samples else 0.0
    overall_tax_accuracy = round((accurate_all / total_all) * 100, 1) if total_all else 100.0
    overall_status = "healthy" if overall_tax_accuracy >= 99 and avg_lag_all < 60 and ledger_score >= 99 and tax_alert_open == 0 else "warning" if overall_tax_accuracy >= 95 and ledger_score >= 95 else "critical"

    return {
        "window_hours": window_hours,
        "overall_status": overall_status,
        "overall_tax_accuracy_rate": overall_tax_accuracy,
        "overall_avg_webhook_lag_seconds": avg_lag_all,
        "providers": provider_rows,
        "ledger_integrity": {
            "status": "healthy" if ledger_score >= 99 else "warning" if ledger_score >= 95 else "critical",
            "score": ledger_score,
            "hash_integrity_rate": hash_integrity,
            "link_integrity_rate": link_integrity,
            "entries_checked": len(ledger_docs),
        },
        "receipt_tax_alerts": {
            "total_in_window": int(tax_alert_total),
            "open_in_window": int(tax_alert_open),
            "status": "healthy" if tax_alert_open == 0 else "warning",
        },
    }


async def _collect_enforcement_rule_health() -> Dict[str, Any]:
    return await collect_enforcement_rule_health(
        db=db,
        normalize_policy=_normalize_slo_auto_mitigation_policy,
        policy_flag_key=SLO_POLICY_FLAG_KEY,
    )


async def _create_remediation_rollback_checkpoint(
    *,
    user: Any,
    trigger: str,
    severity_band: str,
    score: int,
    issues: int,
    source_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    return await create_remediation_rollback_checkpoint(
        db=db,
        rollback_policies=ROLLBACK_POLICIES,
        user=user,
        trigger=trigger,
        severity_band=severity_band,
        score=score,
        issues=issues,
        source_run_id=source_run_id,
    )


def _build_pipeline_stage_status(
    *,
    latest_scan: Dict[str, Any],
    final_score: int,
    final_issues: int,
    enforcement_health: Dict[str, Any],
    checkpoint_id: str,
) -> List[Dict[str, Any]]:
    return build_pipeline_stage_status(
        latest_scan=latest_scan,
        final_score=final_score,
        final_issues=final_issues,
        enforcement_health=enforcement_health,
        checkpoint_id=checkpoint_id,
    )


def _parse_datetime_value(raw_value: Any) -> Optional[datetime]:
    return parse_datetime_value(raw_value)
    """Best-effort datetime parser for ISO strings/datetime objects."""
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=timezone.utc)
        return raw_value.astimezone(timezone.utc)

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    return None


def _safe_float(raw_value: Any, default: float = 0.0) -> float:
    return safe_float(raw_value, default)
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _percentile(values: List[float], percentile: float) -> float:
    return platform_percentile(values, percentile)
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = max(0, min(len(sorted_values) - 1, int(round((percentile / 100.0) * (len(sorted_values) - 1)))))
    return float(sorted_values[rank])


def _normalize_slo_auto_mitigation_policy(raw_policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return normalize_slo_auto_mitigation_policy(raw_policy, DEFAULT_SLO_AUTO_MITIGATION_POLICY)
    source = raw_policy or {}
    normalized = {
        "enabled": bool(source.get("enabled", DEFAULT_SLO_AUTO_MITIGATION_POLICY["enabled"])),
        "p95_latency_threshold_ms": int(max(120, min(5000, int(source.get("p95_latency_threshold_ms", DEFAULT_SLO_AUTO_MITIGATION_POLICY["p95_latency_threshold_ms"]))))),
        "min_samples": int(max(10, min(2000, int(source.get("min_samples", DEFAULT_SLO_AUTO_MITIGATION_POLICY["min_samples"]))))),
        "breach_consecutive_checks": int(max(1, min(12, int(source.get("breach_consecutive_checks", DEFAULT_SLO_AUTO_MITIGATION_POLICY["breach_consecutive_checks"]))))),
        "cooldown_minutes": int(max(1, min(720, int(source.get("cooldown_minutes", DEFAULT_SLO_AUTO_MITIGATION_POLICY["cooldown_minutes"]))))),
        "check_interval_seconds": int(max(30, min(3600, int(source.get("check_interval_seconds", DEFAULT_SLO_AUTO_MITIGATION_POLICY["check_interval_seconds"]))))),
        "auto_fix_recipes": [
            str(item).strip() for item in (source.get("auto_fix_recipes") or DEFAULT_SLO_AUTO_MITIGATION_POLICY["auto_fix_recipes"]) if str(item).strip()
        ],
    }
    if not normalized["auto_fix_recipes"]:
        normalized["auto_fix_recipes"] = list(DEFAULT_SLO_AUTO_MITIGATION_POLICY["auto_fix_recipes"])
    return normalized


async def _get_slo_auto_mitigation_state() -> Dict[str, Any]:
    from routes.platform_monitor import build_slo_latency_snapshot

    policy_flag = await db.system_runtime_flags.find_one({"key": SLO_POLICY_FLAG_KEY}, {"_id": 0}) or {}
    runtime_flag = await db.system_runtime_flags.find_one({"key": SLO_RUNTIME_FLAG_KEY}, {"_id": 0}) or {}
    policy = _normalize_slo_auto_mitigation_policy((policy_flag.get("value") or {}) if isinstance(policy_flag.get("value"), dict) else {})
    runtime = (runtime_flag.get("value") or {}) if isinstance(runtime_flag.get("value"), dict) else {}
    return {
        "policy": policy,
        "runtime": runtime,
        "current_performance": build_slo_latency_snapshot(),
    }


async def run_slo_auto_mitigation_cycle(*, triggered_by: str = "manual") -> Dict[str, Any]:
    from routes.config import get_app_config
    from routes.feature_registry import get_feature_registry
    from routes.performance_guardian import auto_fix_check

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    state = await _get_slo_auto_mitigation_state()
    policy = state["policy"]
    runtime = state.get("runtime") or {}
    perf_snapshot = state.get("current_performance") or {}

    sample_count = int(perf_snapshot.get("sample_count") or 0)
    p95_ms = float(perf_snapshot.get("global_p95_ms") or 0.0)
    threshold = int(policy.get("p95_latency_threshold_ms") or DEFAULT_SLO_AUTO_MITIGATION_POLICY["p95_latency_threshold_ms"])

    if not policy.get("enabled"):
        runtime_update = {
            **runtime,
            "last_checked_at": now_iso,
            "last_result": "disabled",
            "last_triggered_by": triggered_by,
            "current_p95_ms": p95_ms,
            "current_sample_count": sample_count,
            "consecutive_breach_count": 0,
            "breach_active": False,
        }
        await db.system_runtime_flags.update_one(
            {"key": SLO_RUNTIME_FLAG_KEY},
            {"$set": {"key": SLO_RUNTIME_FLAG_KEY, "value": runtime_update, "updated_at": now_iso}},
            upsert=True,
        )
        return {"status": "disabled", "policy": policy, "runtime": runtime_update, "current_performance": perf_snapshot, "actions": []}

    if sample_count < int(policy.get("min_samples") or 0):
        runtime_update = {
            **runtime,
            "last_checked_at": now_iso,
            "last_result": "insufficient_data",
            "last_triggered_by": triggered_by,
            "current_p95_ms": p95_ms,
            "current_sample_count": sample_count,
            "consecutive_breach_count": 0,
            "breach_active": False,
        }
        await db.system_runtime_flags.update_one(
            {"key": SLO_RUNTIME_FLAG_KEY},
            {"$set": {"key": SLO_RUNTIME_FLAG_KEY, "value": runtime_update, "updated_at": now_iso}},
            upsert=True,
        )
        return {
            "status": "insufficient_data",
            "reason": f"sample_count({sample_count}) below min_samples({policy.get('min_samples')})",
            "policy": policy,
            "runtime": runtime_update,
            "current_performance": perf_snapshot,
            "actions": [],
        }

    breach = p95_ms > threshold
    prev_breach_count = int(runtime.get("consecutive_breach_count") or 0)
    breach_count = prev_breach_count + 1 if breach else 0
    breach_checks_required = int(policy.get("breach_consecutive_checks") or 1)

    cooldown_minutes = int(policy.get("cooldown_minutes") or 20)
    last_mitigated_at = _parse_datetime_value(runtime.get("last_mitigated_at"))
    cooldown_ok = True
    if last_mitigated_at:
        cooldown_ok = (now - last_mitigated_at).total_seconds() >= cooldown_minutes * 60

    should_mitigate = bool(breach and breach_count >= breach_checks_required and cooldown_ok)
    actions: List[Dict[str, Any]] = []

    if should_mitigate:
        recipes = set(policy.get("auto_fix_recipes") or [])

        if "warm_hot_caches" in recipes:
            try:
                await get_app_config(version="slo-auto-mitigation")
                await get_feature_registry()
                actions.append({"action": "warm_hot_caches", "status": "applied"})
            except Exception as exc:
                actions.append({"action": "warm_hot_caches", "status": "failed", "error": str(exc)[:160]})

        if "guardian_auto_fix" in recipes:
            try:
                await auto_fix_check()
                actions.append({"action": "guardian_auto_fix", "status": "applied"})
            except Exception as exc:
                actions.append({"action": "guardian_auto_fix", "status": "failed", "error": str(exc)[:160]})

        if "platform_auto_fix" in recipes:
            try:
                fix_result = await auto_fix_platform(_AutoMitigationAdminContext("slo_auto_mitigation", "admin@realaicoach.app"))
                actions.append(
                    {
                        "action": "platform_auto_fix",
                        "status": "applied" if str(fix_result.get("status")) == "success" else "warning",
                        "fix_time": fix_result.get("fix_time"),
                        "urls_remaining": fix_result.get("urls_remaining"),
                    }
                )
            except Exception as exc:
                actions.append({"action": "platform_auto_fix", "status": "failed", "error": str(exc)[:160]})

    result_status = "healthy"
    if breach and not should_mitigate:
        result_status = "breach_detected"
    if breach and should_mitigate:
        result_status = "mitigated"

    runtime_update = {
        **runtime,
        "last_checked_at": now_iso,
        "last_triggered_by": triggered_by,
        "last_result": result_status,
        "current_p95_ms": round(p95_ms, 1),
        "current_sample_count": sample_count,
        "p95_threshold_ms": threshold,
        "consecutive_breach_count": breach_count,
        "breach_active": breach,
        "last_breach_at": now_iso if breach else runtime.get("last_breach_at"),
        "last_actions": actions,
    }
    if should_mitigate:
        runtime_update["last_mitigated_at"] = now_iso

    await db.system_runtime_flags.update_one(
        {"key": SLO_RUNTIME_FLAG_KEY},
        {"$set": {"key": SLO_RUNTIME_FLAG_KEY, "value": runtime_update, "updated_at": now_iso}},
        upsert=True,
    )

    history_record = {
        "run_at": now_iso,
        "triggered_by": triggered_by,
        "status": result_status,
        "breach": breach,
        "mitigated": should_mitigate,
        "sample_count": sample_count,
        "p95_ms": round(p95_ms, 1),
        "threshold_ms": threshold,
        "consecutive_breach_count": breach_count,
        "actions": actions,
    }
    await db[SLO_HISTORY_COLLECTION].insert_one({**history_record})

    return {
        "status": result_status,
        "breach": breach,
        "mitigated": should_mitigate,
        "policy": policy,
        "runtime": runtime_update,
        "current_performance": perf_snapshot,
        "actions": actions,
    }


async def _collect_auto_remediation_kpis() -> Dict[str, Any]:
    """Compute executive auto-remediation KPIs for 24h and 7d windows."""
    now = datetime.now(timezone.utc)
    windows = {
        "window_24h": now - timedelta(hours=24),
        "window_7d": now - timedelta(days=7),
    }

    fix_docs = await db.platform_health_fixes.find({}, {"_id": 0}).sort("_stored_at", -1).limit(900).to_list(900)
    scan_docs = await db.platform_health_scans.find({}, {"_id": 0}).sort("_stored_at", -1).limit(1200).to_list(1200)
    route_docs = await db.route_health_history.find({}, {"_id": 0}).sort("timestamp", -1).limit(1200).to_list(1200)
    regression_docs = await db.platform_regression_gate_history.find({}, {"_id": 0}).sort("run_at", -1).limit(1200).to_list(1200)

    normalized_scans: List[Dict[str, Any]] = []
    for row in scan_docs:
        scanned_at = _parse_datetime_value(row.get("scanned_at") or row.get("_stored_at"))
        if not scanned_at:
            continue

        caches = row.get("caches") or []
        cache_stale = any(bool((cache or {}).get("stale")) for cache in caches if isinstance(cache, dict))
        build_stale = bool((row.get("build") or {}).get("stale"))

        normalized_scans.append({
            "timestamp": scanned_at,
            "total_issues": int(row.get("total_issues", 0) or 0),
            "score": _safe_float(row.get("score", 0), 0.0),
            "stale_urls": int((row.get("stale_urls") or {}).get("count", 0) or 0),
            "stale_cache": bool(cache_stale or build_stale),
        })

    normalized_scans.sort(key=lambda item: item["timestamp"])
    issue_scans = [item for item in normalized_scans if item["total_issues"] > 0]

    mttr_events: List[Dict[str, Any]] = []
    for row in fix_docs:
        fixed_at = _parse_datetime_value(row.get("fixed_at") or row.get("_stored_at"))
        if not fixed_at:
            continue

        before = row.get("before") or {}
        after = row.get("after") or {}

        before_stale_urls = int(before.get("stale_urls", 0) or 0)
        before_stale_caches = int(before.get("stale_caches", 0) or 0)
        before_build_stale = bool(before.get("build_stale"))
        had_detected_issue = bool(before_stale_urls > 0 or before_stale_caches > 0 or before_build_stale)
        if not had_detected_issue:
            continue

        detection_scan = None
        for scan in reversed(issue_scans):
            if scan["timestamp"] <= fixed_at:
                detection_scan = scan
                break

        fallback_minutes = max(0.0, _safe_float(row.get("fix_time", 0), 0.0) / 60.0)
        if detection_scan:
            computed_minutes = max(0.0, (fixed_at - detection_scan["timestamp"]).total_seconds() / 60.0)
            mttr_minutes = round(max(computed_minutes, fallback_minutes), 2)
        else:
            mttr_minutes = round(fallback_minutes, 2)

        mttr_events.append({
            "fixed_at": fixed_at,
            "detected_at": detection_scan["timestamp"].isoformat() if detection_scan else None,
            "mttr_minutes": mttr_minutes,
            "before_stale_urls": before_stale_urls,
            "after_stale_urls": int((after or {}).get("stale_urls", 0) or 0),
        })

    normalized_route_history: List[Dict[str, Any]] = []
    for row in route_docs:
        ts = _parse_datetime_value(row.get("timestamp"))
        if not ts:
            continue

        direct_integrity = _safe_float(row.get("direct_integrity_pct", 0), 0.0)
        redirect_success = _safe_float(row.get("redirect_success_pct", 0), 0.0)
        p95_latency = _safe_float(row.get("p95_latency_ms", 0), 0.0)
        latency_score = max(0.0, min(100.0, 100.0 - (p95_latency / 25.0)))
        score = round((direct_integrity * 0.45) + (redirect_success * 0.45) + (latency_score * 0.10), 2)

        normalized_route_history.append({
            "timestamp": ts,
            "score": score,
            "direct_integrity_pct": direct_integrity,
            "redirect_success_pct": redirect_success,
            "p95_latency_ms": p95_latency,
        })

    normalized_route_history.sort(key=lambda item: item["timestamp"])

    regression_history: List[Dict[str, Any]] = []
    for row in regression_docs:
        ts = _parse_datetime_value(row.get("run_at"))
        if not ts:
            continue
        regression_history.append({
            "timestamp": ts,
            "score": _safe_float(row.get("score", 0), 0.0),
        })

    regression_history.sort(key=lambda item: item["timestamp"])

    def build_mttr_window(cutoff: datetime) -> Dict[str, Any]:
        window_events = [event for event in mttr_events if event["fixed_at"] >= cutoff]
        values = [event["mttr_minutes"] for event in window_events]

        if not values:
            return {
                "mean_minutes": None,
                "median_minutes": None,
                "p95_minutes": None,
                "latest_minutes": None,
                "sample_count": 0,
                "status": "insufficient_data",
            }

        mean_minutes = round(sum(values) / len(values), 2)
        median_minutes = round(_percentile(values, 50), 2)
        p95_minutes = round(_percentile(values, 95), 2)
        latest_minutes = values[-1]
        status = "healthy" if mean_minutes <= 30 else "warning" if mean_minutes <= 90 else "critical"

        return {
            "mean_minutes": mean_minutes,
            "median_minutes": median_minutes,
            "p95_minutes": p95_minutes,
            "latest_minutes": latest_minutes,
            "sample_count": len(values),
            "status": status,
        }

    def build_stale_cache_window(cutoff: datetime) -> Dict[str, Any]:
        scans_in_window = [scan for scan in normalized_scans if scan["timestamp"] >= cutoff]
        scans_before_window = [scan for scan in normalized_scans if scan["timestamp"] < cutoff]

        previous_state = scans_before_window[-1]["stale_cache"] if scans_before_window else False
        recurrence_count = 0
        stale_scan_count = 0
        latest_state = previous_state

        for scan in scans_in_window:
            current_state = bool(scan["stale_cache"])
            if current_state:
                stale_scan_count += 1
            if current_state and not previous_state:
                recurrence_count += 1
            previous_state = current_state
            latest_state = current_state

        total_scans = len(scans_in_window)
        recurrence_rate_pct = round((recurrence_count / total_scans) * 100, 2) if total_scans else 0.0
        stale_rate_pct = round((stale_scan_count / total_scans) * 100, 2) if total_scans else 0.0

        if total_scans == 0:
            status = "insufficient_data"
        elif recurrence_count == 0 and stale_scan_count == 0:
            status = "healthy"
        elif recurrence_count <= 1 and stale_rate_pct <= 35:
            status = "warning"
        else:
            status = "critical"

        return {
            "recurrence_count": recurrence_count,
            "recurrence_rate_pct": recurrence_rate_pct,
            "scans_with_stale_cache": stale_scan_count,
            "scans_total": total_scans,
            "stale_rate_pct": stale_rate_pct,
            "current_state": "stale" if latest_state else "healthy",
            "status": status,
        }

    def build_route_health_window(cutoff: datetime) -> Dict[str, Any]:
        route_rows = [row for row in normalized_route_history if row["timestamp"] >= cutoff]
        source = "route_health_history"

        if not route_rows:
            route_rows = [row for row in regression_history if row["timestamp"] >= cutoff]
            source = "platform_regression_gate_history"

        if not route_rows:
            return {
                "score": None,
                "latest_score": None,
                "trend_delta": None,
                "sample_count": 0,
                "avg_p95_latency_ms": None,
                "direct_integrity_pct": None,
                "direct_integrity": None,
                "protected_integrity_pct": None,
                "protected_integrity": None,
                "redirect_success_pct": None,
                "source": source,
                "status": "insufficient_data",
            }

        scores = [_safe_float(row.get("score", 0), 0.0) for row in route_rows]
        avg_score = round(sum(scores) / len(scores), 2)
        latest_score = round(scores[-1], 2)
        trend_delta = round(scores[-1] - scores[0], 2) if len(scores) > 1 else 0.0

        avg_p95_latency_ms = None
        direct_integrity_pct = None
        protected_integrity_pct = None
        redirect_success_pct = None
        if source == "route_health_history":
            avg_p95_latency_ms = round(sum(_safe_float(row.get("p95_latency_ms", 0), 0.0) for row in route_rows) / len(route_rows), 2)
            direct_integrity_pct = round(sum(_safe_float(row.get("direct_integrity_pct", 0), 0.0) for row in route_rows) / len(route_rows), 2)
            protected_integrity_pct = round(sum(_safe_float(row.get("protected_integrity_pct", 0), 0.0) for row in route_rows) / len(route_rows), 2)
            redirect_success_pct = round(sum(_safe_float(row.get("redirect_success_pct", 0), 0.0) for row in route_rows) / len(route_rows), 2)

        status = "healthy" if avg_score >= 95 else "warning" if avg_score >= 85 else "critical"
        return {
            "score": avg_score,
            "latest_score": latest_score,
            "trend_delta": trend_delta,
            "sample_count": len(route_rows),
            "avg_p95_latency_ms": avg_p95_latency_ms,
            "direct_integrity_pct": direct_integrity_pct,
            "direct_integrity": direct_integrity_pct,
            "protected_integrity_pct": protected_integrity_pct,
            "protected_integrity": protected_integrity_pct,
            "redirect_success_pct": redirect_success_pct,
            "source": source,
            "status": status,
        }

    mttr_windows = {window_key: build_mttr_window(cutoff) for window_key, cutoff in windows.items()}
    stale_windows = {window_key: build_stale_cache_window(cutoff) for window_key, cutoff in windows.items()}
    route_windows = {window_key: build_route_health_window(cutoff) for window_key, cutoff in windows.items()}

    mttr_24h = mttr_windows["window_24h"].get("mean_minutes")
    stale_24h = stale_windows["window_24h"].get("recurrence_count", 0)
    route_24h = route_windows["window_24h"].get("score")

    if mttr_24h is None or route_24h is None:
        executive_status = "warning"
    elif mttr_24h <= 30 and stale_24h == 0 and route_24h >= 95:
        executive_status = "healthy"
    elif mttr_24h <= 90 and stale_24h <= 2 and route_24h >= 85:
        executive_status = "warning"
    else:
        executive_status = "critical"

    return {
        "generated_at": now.isoformat(),
        "window_definitions": {
            "window_24h": "Last 24 hours",
            "window_7d": "Last 7 days",
        },
        "mttr": {
            "unit": "minutes",
            **mttr_windows,
        },
        "stale_cache_recurrence": {
            "unit": "count",
            **stale_windows,
        },
        "route_health_score": {
            "scale": "0-100",
            **route_windows,
        },
        "executive_rollup": {
            "status": executive_status,
            "mttr_minutes_24h": mttr_24h,
            "stale_cache_recurrence_24h": stale_24h,
            "route_health_score_24h": route_24h,
        },
    }


@router.post("/enterprise-auto-audit")
async def run_enterprise_auto_audit(user=Depends(get_current_user)):
    """Global autonomous enterprise audit + safe auto-repair with persistent enforcement rules."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    started = datetime.now(timezone.utc)
    cleanup_result = _cleanup_platform_caches()

    perf_policy = {
        "lazy_loading": True,
        "response_caching": True,
        "asset_compression": True,
        "db_query_guardrails": True,
        "api_retry_policy": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.performance_optimization_rules.update_one(
        {"rule_id": "global_enterprise_perf"},
        {"$set": {"rule_id": "global_enterprise_perf", **perf_policy}},
        upsert=True,
    )

    passes = []
    final_result = None
    for _ in range(3):
        result = await run_full_system_audit(safe_auto_fix=True, run_domain_autofix=True, user=user)
        passes.append({
            "score": result.get("composite_health", {}).get("score", 0),
            "grade": result.get("composite_health", {}).get("grade", "F"),
            "issues": result.get("final_scan", {}).get("total_issues", 999),
        })
        final_result = result
        if (result.get("composite_health", {}).get("score", 0) >= 100) and (result.get("final_scan", {}).get("total_issues", 1) == 0):
            break

    from scheduler_jobs import scheduled_e2e_regression_gate, scheduled_growth_integrity_monitor

    await scheduled_e2e_regression_gate()
    await scheduled_growth_integrity_monitor()

    admin_tabs_audit = _audit_admin_tabs_structure()
    await db.admin_tabs_audit_history.insert_one(
        {
            "run_at": datetime.now(timezone.utc).isoformat(),
            **admin_tabs_audit,
        }
    )

    enforcement_rules = {
        "rule_id": "enterprise_permanent_enforcement",
        "enabled": True,
        "safe_auto_fix_required": True,
        "regression_gate_required": True,
        "growth_monitor_required": True,
        "admin_tabs_uniqueness_required": True,
        "performance_policy_required": True,
        "slo_auto_mitigation_required": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.enterprise_enforcement_rules.update_one(
        {"rule_id": "enterprise_permanent_enforcement"},
        {"$set": enforcement_rules},
        upsert=True,
    )

    latest_scan = await scan_platform_health(user)
    duration = (datetime.now(timezone.utc) - started).total_seconds()
    final_score = max(
        int((final_result or {}).get("composite_health", {}).get("score", 0)),
        int(latest_scan.get("score", 0) or 0),
    )
    final_issues = int(latest_scan.get("total_issues", 0) or 0)
    severity_band = _derive_severity_band(final_score, final_issues)
    run_id = f"enterprise_audit_{int(datetime.now(timezone.utc).timestamp())}"

    checkpoint = await _create_remediation_rollback_checkpoint(
        user=user,
        trigger="enterprise_auto_audit",
        severity_band=severity_band,
        score=final_score,
        issues=final_issues,
        source_run_id=run_id,
    )

    enforcement_health = await _collect_enforcement_rule_health()
    pipeline_status = _build_pipeline_stage_status(
        latest_scan=latest_scan,
        final_score=final_score,
        final_issues=final_issues,
        enforcement_health=enforcement_health,
        checkpoint_id=checkpoint["checkpoint_id"],
    )

    await db.enterprise_auto_audit_history.insert_one(
        {
            "run_id": run_id,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration, 2),
            "severity_band": severity_band,
            "pipeline_status": pipeline_status,
            "final_state": {
                "score": final_score,
                "issues": final_issues,
                "stable": final_score >= 100 and final_issues == 0,
            },
            "rollback_checkpoint": checkpoint,
            "enforcement_health": enforcement_health,
            "auto_fix_passes": passes,
        }
    )

    return {
        "status": "completed",
        "run_id": run_id,
        "duration_seconds": round(duration, 2),
        "pipeline": ["detect", "diagnose", "repair", "optimize", "validate", "lock_permanent_fix"],
        "pipeline_status": pipeline_status,
        "cleanup": cleanup_result,
        "performance_policy": perf_policy,
        "auto_fix_passes": passes,
        "admin_tabs_audit": admin_tabs_audit,
        "persistent_enforcement": enforcement_rules,
        "enforcement_health": enforcement_health,
        "severity_band": severity_band,
        "rollback_checkpoint": checkpoint,
        "latest_scan": latest_scan,
        "final_state": {
            "score": final_score,
            "issues": final_issues,
            "stable": final_score >= 100 and final_issues == 0,
        },
    }


@router.get("/enterprise-control-plane")
async def get_enterprise_control_plane(user=Depends(get_current_user)):
    """Unified live dashboard for enterprise pipeline status, latest diff, enforcement health and rollback checkpoints."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now_ts = time.time()
    cached_data = _ENTERPRISE_CONTROL_PLANE_CACHE.get("data")
    cached_ts = float(_ENTERPRISE_CONTROL_PLANE_CACHE.get("ts") or 0.0)

    if cached_data and (now_ts - cached_ts) < ENTERPRISE_CONTROL_PLANE_CACHE_TTL_SECONDS:
        return {**cached_data, "cache": "hit"}

    if cached_data:
        if not _ENTERPRISE_CONTROL_PLANE_CACHE.get("refreshing"):
            _ENTERPRISE_CONTROL_PLANE_CACHE["refreshing"] = True

            async def _refresh_cache_async():
                try:
                    fresh = await _build_enterprise_control_plane_payload()
                    _ENTERPRISE_CONTROL_PLANE_CACHE["data"] = fresh
                    _ENTERPRISE_CONTROL_PLANE_CACHE["ts"] = time.time()
                except Exception as exc:
                    logger.warning(f"Enterprise control-plane cache refresh failed: {exc}")
                finally:
                    _ENTERPRISE_CONTROL_PLANE_CACHE["refreshing"] = False

            asyncio.create_task(_refresh_cache_async())

        return {**cached_data, "cache": "stale"}

    try:
        fresh = await asyncio.wait_for(_build_enterprise_control_plane_payload(), timeout=12)
        _ENTERPRISE_CONTROL_PLANE_CACHE["data"] = fresh
        _ENTERPRISE_CONTROL_PLANE_CACHE["ts"] = time.time()
        _ENTERPRISE_CONTROL_PLANE_CACHE["refreshing"] = False
        return {**fresh, "cache": "miss"}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Enterprise control plane is warming up. Retry shortly.")


@router.get("/enterprise-standard/status")
async def get_enterprise_standard_status(user=Depends(get_current_user)):
    """Unified permanent enforcement status for platform integrity/performance standard."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    latest_scan = await db.platform_health_scans.find_one({}, {"_id": 0}, sort=[("_stored_at", -1)]) or {}
    latest_fix = await db.platform_health_fixes.find_one({}, {"_id": 0}, sort=[("_stored_at", -1)]) or {}
    latest_audit = await db.enterprise_auto_audit_history.find_one({}, {"_id": 0}, sort=[("run_at", -1)]) or {}
    latest_assurance = await db.global_experience_assurance_history.find_one({}, {"_id": 0}, sort=[("run_at", -1)]) or {}
    latest_email_localization = await db.email_template_localization_audits.find_one({}, {"_id": 0}, sort=[("run_at", -1)]) or {}
    latest_multilingual_email_localization = await db.email_template_multilingual_localization_audits.find_one({}, {"_id": 0}, sort=[("run_at", -1)]) or {}
    learning_runtime = await db.learn_hub_assurance_runtime.find_one({"key": "learning_hub_assurance_runtime"}, {"_id": 0}) or {}
    from routes.performance_guardian import build_budget_violations_snapshot, guardian_status
    performance_budget_snapshot = await build_budget_violations_snapshot(db)
    performance_guardian_snapshot = await guardian_status(None)
    slo_state = await _get_slo_auto_mitigation_state()

    watched_jobs = [
        "platform_cache_freshness_guard",
        "platform_e2e_regression_gate",
        "platform_full_auto_audit",
        "enterprise_lock_cycle",
        "enterprise_standard_weekly_guard",
        "slo_breach_auto_mitigation",
        "global_experience_assurance",
        "learning_hub_assurance_guard",
        "learning_hub_video_maintenance",
        "fedapay_webhook_self_heal",
    ]
    heartbeats = await db.scheduler_heartbeats.find(
        {"job_id": {"$in": watched_jobs}},
        {"_id": 0, "job_id": 1, "status": 1, "last_run": 1, "message": 1},
    ).to_list(len(watched_jobs) + 5)
    by_job = {str(h.get("job_id")): h for h in heartbeats}

    healthy_jobs = sum(1 for j in watched_jobs if str((by_job.get(j) or {}).get("status")) == "healthy")
    framework_status = "healthy"
    score = int(latest_scan.get("score", 0) or 0)
    issues = int(latest_scan.get("total_issues", 0) or 0)
    if issues > 0 or score < 95:
        framework_status = "warning"
    if (
        int(performance_budget_snapshot.get("total_violations", 0) or 0) > 0
        or len(performance_budget_snapshot.get("stale_insufficient_routes") or []) > 0
        or str(performance_guardian_snapshot.get("status") or "unknown") != "healthy"
    ):
        framework_status = "warning"
    if healthy_jobs < max(1, int(len(watched_jobs) * 0.6)):
        framework_status = "critical"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "framework_status": framework_status,
        "platform": {
            "latest_scan_score": score,
            "latest_scan_issues": issues,
            "latest_scan": latest_scan,
            "latest_fix": latest_fix,
            "latest_enterprise_audit": latest_audit,
            "latest_email_localization_audit": latest_email_localization,
            "latest_multilingual_email_localization_audit": latest_multilingual_email_localization,
            "performance_guardian": performance_guardian_snapshot,
            "performance_budget_snapshot": performance_budget_snapshot,
            "slo_auto_mitigation": slo_state,
        },
        "learning_hub": {
            "assurance_runtime": learning_runtime,
            "latest_global_assurance": latest_assurance,
        },
        "scheduler": {
            "watched_jobs": watched_jobs,
            "healthy_jobs": healthy_jobs,
            "heartbeats": heartbeats,
        },
        "cadence": {
            "cache_freshness": "every 10 min",
            "global_experience_assurance": "every 20 min",
            "e2e_regression_gate": "every 30 min",
            "enterprise_lock_cycle": "hourly",
            "enterprise_standard_weekly_guard": "weekly (Sunday)",
            "slo_breach_auto_mitigation": "every 3 min",
            "full_auto_audit": "every 2 hours",
            "learning_hub_assurance": "every 15 min",
            "video_maintenance": "every 30 min",
        },
    }


@router.get("/enterprise-standard/slo-auto-mitigation")
async def get_slo_auto_mitigation(user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await _get_slo_auto_mitigation_state()


@router.post("/enterprise-standard/slo-auto-mitigation/config")
async def update_slo_auto_mitigation_config(request: Request, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json()
    current = await _get_slo_auto_mitigation_state()
    policy = dict(current.get("policy") or {})

    for field in [
        "enabled",
        "p95_latency_threshold_ms",
        "min_samples",
        "breach_consecutive_checks",
        "cooldown_minutes",
        "check_interval_seconds",
        "auto_fix_recipes",
    ]:
        if field in body:
            policy[field] = body[field]

    normalized = _normalize_slo_auto_mitigation_policy(policy)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.system_runtime_flags.update_one(
        {"key": SLO_POLICY_FLAG_KEY},
        {
            "$set": {
                "key": SLO_POLICY_FLAG_KEY,
                "value": normalized,
                "updated_at": now_iso,
                "updated_by": getattr(user, "email", "admin"),
            }
        },
        upsert=True,
    )
    _ENTERPRISE_CONTROL_PLANE_CACHE["data"] = None
    _ENTERPRISE_CONTROL_PLANE_CACHE["ts"] = 0.0

    return {
        "status": "ok",
        "policy": normalized,
        "updated_at": now_iso,
    }


@router.post("/enterprise-standard/slo-auto-mitigation/run-now")
async def run_slo_auto_mitigation_now(user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await run_slo_auto_mitigation_cycle(triggered_by=f"admin:{getattr(user, 'user_id', 'admin')}:manual")
    _ENTERPRISE_CONTROL_PLANE_CACHE["data"] = None
    _ENTERPRISE_CONTROL_PLANE_CACHE["ts"] = 0.0
    return result


@router.post("/enterprise-standard/enforce-now")
async def enforce_enterprise_standard_now(user=Depends(get_current_user)):
    """Run complete enterprise integrity/performance enforcement immediately."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    run_id = f"enterprise_standard_{int(datetime.now(timezone.utc).timestamp())}"
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.enterprise_standard_enforcement_history.insert_one(
        {
            "run_id": run_id,
            "triggered_at": now_iso,
            "triggered_by": user.user_id,
            "status": "running",
            "phase": "queued",
            "duration_seconds": 0,
        }
    )

    async def _run_enforcement(run_id_value: str, user_id_value: str):
        started = datetime.now(timezone.utc)
        try:
            await db.enterprise_standard_enforcement_history.update_one(
                {"run_id": run_id_value},
                {"$set": {"phase": "baseline_scan", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )

            baseline = await scan_platform_health(user)
            fixes = None
            if int(baseline.get("total_issues", 0) or 0) > 0:
                await db.enterprise_standard_enforcement_history.update_one(
                    {"run_id": run_id_value},
                    {"$set": {"phase": "auto_fix", "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                fixes = await auto_fix_platform(user)

            await db.enterprise_standard_enforcement_history.update_one(
                {"run_id": run_id_value},
                {"$set": {"phase": "enterprise_audit", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            enterprise_audit = await run_enterprise_auto_audit(user)

            from routes.ai_learning_hub import run_learning_hub_assurance_cycle
            from routes.fedapay_client import sync_webhook_url
            from routes.payments import run_fedapay_webhook_retry_cycle, run_fedapay_webhook_dead_replay_cycle

            await db.enterprise_standard_enforcement_history.update_one(
                {"run_id": run_id_value},
                {"$set": {"phase": "learning_assurance", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            learning_assurance = await run_learning_hub_assurance_cycle(
                triggered_by=f"admin:{user_id_value}:enterprise-standard"
            )

            await db.enterprise_standard_enforcement_history.update_one(
                {"run_id": run_id_value},
                {"$set": {"phase": "payment_webhook_assurance", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            fedapay_sync = await sync_webhook_url()
            fedapay_retry = await run_fedapay_webhook_retry_cycle(limit=50)
            fedapay_dead_replay = await run_fedapay_webhook_dead_replay_cycle(limit=20)

            final_scan = await scan_platform_health(user)
            final_score = int(final_scan.get("score", 0) or 0)
            final_issues = int(final_scan.get("total_issues", 0) or 0)
            status = "healthy"
            if final_issues > 0 or final_score < 95 or str(learning_assurance.get("status")) != "healthy":
                status = "warning"
            if str(fedapay_sync.get("status")) not in {"ok", "skipped"}:
                status = "critical"

            result = {
                "status": status,
                "phase": "completed",
                "baseline": baseline,
                "fixes": fixes,
                "enterprise_audit": enterprise_audit,
                "learning_hub_assurance": learning_assurance,
                "fedapay": {
                    "sync": fedapay_sync,
                    "retry": fedapay_retry,
                    "dead_replay": fedapay_dead_replay,
                },
                "final_scan": final_scan,
                "final_state": {
                    "score": final_score,
                    "issues": final_issues,
                    "stable": status == "healthy",
                },
                "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.enterprise_standard_enforcement_history.update_one(
                {"run_id": run_id_value},
                {"$set": result},
            )

            try:
                report_payload = _build_enterprise_compliance_report(
                    run_id=run_id_value,
                    enforcement_doc=result,
                    generated_by=str(user_id_value or "system"),
                    trigger_mode="auto",
                )
                await db.enterprise_integrity_runbook_reports.update_one(
                    {"run_id": run_id_value},
                    {"$set": report_payload},
                    upsert=True,
                )
                email_distribution = await _dispatch_enterprise_compliance_report_email(
                    report=report_payload,
                    requested_by=str(user_id_value or "system"),
                    trigger_mode="auto",
                )
                await db.enterprise_integrity_runbook_reports.update_one(
                    {"run_id": run_id_value},
                    {"$set": {"email_distribution": email_distribution}},
                    upsert=True,
                )
                await db.enterprise_standard_enforcement_history.update_one(
                    {"run_id": run_id_value},
                    {
                        "$set": {
                            "compliance_report": {
                                "report_id": report_payload.get("report_id"),
                                "generated_at": report_payload.get("generated_at"),
                                "email_distribution": email_distribution,
                            }
                        }
                    },
                )
            except Exception as email_exc:
                logger.warning(f"Enterprise compliance email distribution failed for {run_id_value}: {email_exc}")
            _ENTERPRISE_CONTROL_PLANE_CACHE["data"] = None
            _ENTERPRISE_CONTROL_PLANE_CACHE["ts"] = 0.0
        except Exception as exc:
            await db.enterprise_standard_enforcement_history.update_one(
                {"run_id": run_id_value},
                {
                    "$set": {
                        "status": "error",
                        "phase": "failed",
                        "error": str(exc),
                        "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 2),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )

    asyncio.create_task(_run_enforcement(run_id, user.user_id))

    return {
        "accepted": True,
        "run_id": run_id,
        "status": "running",
        "status_endpoint": f"/api/admin/platform-health/enterprise-standard/enforcement/{run_id}",
    }


@router.get("/enterprise-standard/enforcement/{run_id}")
async def get_enterprise_standard_enforcement_run(run_id: str, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    doc = await db.enterprise_standard_enforcement_history.find_one({"run_id": run_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found")
    return doc


class EnterpriseRunbookCloseRequest(BaseModel):
    close_reason: Optional[str] = None


@router.post("/enterprise-standard/enforcement/{run_id}/close")
async def close_enterprise_standard_enforcement_run(
    run_id: str,
    body: Optional[EnterpriseRunbookCloseRequest] = None,
    request: Request = None,
    user=Depends(get_current_user),
):
    """Finalize (close) a completed enterprise runbook with strict Autonomous Engine gate enforcement."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    run_doc = await db.enterprise_standard_enforcement_history.find_one({"run_id": run_id}, {"_id": 0})
    if not run_doc:
        raise HTTPException(status_code=404, detail="Run not found")

    phase = str(run_doc.get("phase", "")).lower()
    if phase != "completed":
        raise HTTPException(status_code=409, detail="Runbook must be completed before closure")

    close_reason = str((body or EnterpriseRunbookCloseRequest()).close_reason or "manual_runbook_closure")

    from routes.autonomous_engine import evaluate_completion_gate_and_audit

    evaluated = await evaluate_completion_gate_and_audit(
        user=user,
        source_endpoint=f"/api/admin/platform-health/enterprise-standard/enforcement/{run_id}/close",
        workflow_type="enterprise_standard_enforcement",
        workflow_id=run_id,
        close_reason=close_reason,
        context={
            "run_status": run_doc.get("status"),
            "run_phase": run_doc.get("phase"),
            "request_path": str(getattr(request, "url", "") or ""),
        },
    )

    gate_lock = evaluated.get("gate_lock", {})
    audit_entry = evaluated.get("audit_entry", {})
    latest_output = gate_lock.get("latest_run_output") or {}
    gate_priority = ["TESTS", "VALIDATION", "PERFORMANCE", "E2E", "VISUAL"]
    failing_gate = next((g for g in gate_priority if str(latest_output.get(g, "")).upper() == "FAIL"), "STATUS")

    base_url = (os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get("FRONTEND_BASE_URL") or "").rstrip("/")
    failing_gate_url = (
        f"{base_url}/admin-console?category=operations&tab=autonomous-engine&focus_gate={str(failing_gate).lower()}"
        if base_url
        else f"/admin-console?category=operations&tab=autonomous-engine&focus_gate={str(failing_gate).lower()}"
    )

    if evaluated.get("blocked"):
        await db.enterprise_standard_enforcement_history.update_one(
            {"run_id": run_id},
            {
                "$set": {
                    "last_closure_attempt": {
                        "attempted_at": datetime.now(timezone.utc).isoformat(),
                        "attempted_by": getattr(user, "email", "admin"),
                        "close_reason": close_reason,
                        "blocked": True,
                        "audit_id": audit_entry.get("audit_id"),
                        "failing_gate": failing_gate,
                        "failing_gate_url": failing_gate_url,
                    },
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

        try:

            attempted_by = str(getattr(user, "email", "admin"))
            recipients = {"admin@realaicoach.app", attempted_by}

            from utils.email_service import send_catalog_template
            for recipient in recipients:
                if not recipient:
                    continue
                await send_catalog_template(
                    recipient_email=recipient,
                    template_key="system_alert_admin",
                    alert_type="Runbook Closure Blocked",
                    severity="CRITICAL",
                    description="Autonomous Engine strict hard-gate prevented runbook closure. Immediate review required.",
                    component="Autonomous Engine / Platform Health",
                )
        except Exception:
            pass

        raise HTTPException(
            status_code=423,
            detail={
                "message": "Runbook closure blocked by Autonomous Engine strict hard-gate.",
                "completion_blocked": True,
                "run_id": run_id,
                "gate_lock": gate_lock,
                "audit_entry": audit_entry,
                "failing_gate": failing_gate,
                "failing_gate_url": failing_gate_url,
            },
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    closure_doc = {
        "closed": True,
        "closed_at": now_iso,
        "closed_by": getattr(user, "email", "admin"),
        "closed_by_user_id": str(getattr(user, "user_id", "")),
        "close_reason": close_reason,
        "audit_id": audit_entry.get("audit_id"),
        "gate_snapshot": gate_lock,
    }

    await db.enterprise_standard_enforcement_history.update_one(
        {"run_id": run_id},
        {
            "$set": {
                "closure": closure_doc,
                "last_closure_attempt": {
                    "attempted_at": now_iso,
                    "attempted_by": getattr(user, "email", "admin"),
                    "close_reason": close_reason,
                    "blocked": False,
                    "audit_id": audit_entry.get("audit_id"),
                },
                "updated_at": now_iso,
            }
        },
    )

    updated = await db.enterprise_standard_enforcement_history.find_one({"run_id": run_id}, {"_id": 0})
    return {
        "closed": True,
        "run_id": run_id,
        "closure": closure_doc,
        "gate_lock": gate_lock,
        "audit_entry": audit_entry,
        "run": updated,
    }


@router.get("/enterprise-standard/enforcement/{run_id}/compliance-report")
async def get_enterprise_standard_compliance_report(run_id: str, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    report = await db.enterprise_integrity_runbook_reports.find_one({"run_id": run_id}, {"_id": 0})
    if report:
        return report

    run_doc = await db.enterprise_standard_enforcement_history.find_one({"run_id": run_id}, {"_id": 0})
    if not run_doc:
        raise HTTPException(status_code=404, detail="Run not found")
    if str(run_doc.get("phase", "")).lower() != "completed":
        raise HTTPException(status_code=409, detail="Compliance report available after run completion")

    report_payload = _build_enterprise_compliance_report(
        run_id=run_id,
        enforcement_doc=run_doc,
        generated_by=str(getattr(user, "user_id", "admin") or "admin"),
        trigger_mode="manual",
    )
    await db.enterprise_integrity_runbook_reports.update_one(
        {"run_id": run_id},
        {"$set": report_payload},
        upsert=True,
    )
    return report_payload


@router.post("/enterprise-standard/enforcement/{run_id}/email-report")
async def email_enterprise_standard_compliance_report(run_id: str, user=Depends(get_current_user)):
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    run_doc = await db.enterprise_standard_enforcement_history.find_one({"run_id": run_id}, {"_id": 0})
    if not run_doc:
        raise HTTPException(status_code=404, detail="Run not found")
    if str(run_doc.get("phase", "")).lower() != "completed":
        raise HTTPException(status_code=409, detail="Runbook must be completed before email distribution")

    report = await db.enterprise_integrity_runbook_reports.find_one({"run_id": run_id}, {"_id": 0})
    if not report:
        report = _build_enterprise_compliance_report(
            run_id=run_id,
            enforcement_doc=run_doc,
            generated_by=str(getattr(user, "user_id", "admin") or "admin"),
            trigger_mode="manual",
        )
        await db.enterprise_integrity_runbook_reports.update_one(
            {"run_id": run_id},
            {"$set": report},
            upsert=True,
        )

    distribution = await _dispatch_enterprise_compliance_report_email(
        report=report,
        requested_by=str(getattr(user, "user_id", "admin") or "admin"),
        trigger_mode="manual",
    )
    await db.enterprise_integrity_runbook_reports.update_one(
        {"run_id": run_id},
        {"$set": {"email_distribution": distribution}},
        upsert=True,
    )
    await db.enterprise_standard_enforcement_history.update_one(
        {"run_id": run_id},
        {
            "$set": {
                "compliance_report": {
                    "report_id": report.get("report_id"),
                    "generated_at": report.get("generated_at"),
                    "email_distribution": distribution,
                }
            }
        },
    )

    return {
        "status": distribution.get("status", "unknown"),
        "run_id": run_id,
        "report_id": report.get("report_id"),
        "email_distribution": distribution,
    }


@router.post("/enterprise-control-plane/rollback/{checkpoint_id}/restore")
async def restore_enterprise_checkpoint(checkpoint_id: str, user=Depends(get_current_user)):
    """Restore enterprise enforcement/performance rules from a stored rollback checkpoint."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    checkpoint = await db.enterprise_rollback_checkpoints.find_one(
        {"checkpoint_id": checkpoint_id},
        {"_id": 0},
    )
    if not checkpoint:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    snapshots = checkpoint.get("snapshots") or {}
    enforcement_snapshot = snapshots.get("enterprise_enforcement_rules") or {}
    perf_snapshot = snapshots.get("performance_optimization_rules") or {}

    restored = {"enforcement_rules": False, "performance_policy": False}
    now_iso = datetime.now(timezone.utc).isoformat()

    if enforcement_snapshot:
        await db.enterprise_enforcement_rules.update_one(
            {"rule_id": enforcement_snapshot.get("rule_id", "enterprise_permanent_enforcement")},
            {"$set": {**enforcement_snapshot, "restored_at": now_iso, "restored_from_checkpoint": checkpoint_id}},
            upsert=True,
        )
        restored["enforcement_rules"] = True

    if perf_snapshot:
        await db.performance_optimization_rules.update_one(
            {"rule_id": perf_snapshot.get("rule_id", "global_enterprise_perf")},
            {"$set": {**perf_snapshot, "restored_at": now_iso, "restored_from_checkpoint": checkpoint_id}},
            upsert=True,
        )
        restored["performance_policy"] = True

    await db.enterprise_rollback_events.insert_one(
        {
            "event_id": f"rollback_event_{int(datetime.now(timezone.utc).timestamp())}",
            "checkpoint_id": checkpoint_id,
            "restored_at": now_iso,
            "restored_by": getattr(user, "email", None) or "system",
            "severity_band": checkpoint.get("severity_band", "unknown"),
            "restored": restored,
        }
    )

    return {
        "status": "restored",
        "checkpoint_id": checkpoint_id,
        "restored": restored,
        "restored_at": now_iso,
    }


# ── IAP Reconciliation Dashboard ───────────────────────────────────
@router.get("/iap-reconciliation")
async def get_iap_reconciliation_dashboard(
    window_hours: int = 168,
    user=Depends(get_current_user),
):
    """Production-grade IAP (Apple/Google) deep reconciliation dashboard."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=window_hours)).isoformat()

    iap_txs = await db.payment_transactions.find(
        {
            "created_at": {"$gte": cutoff},
            "$or": [
                {"provider": {"$in": ["iap_apple", "iap_google", "apple", "google"]}},
                {"payment_method": {"$in": ["iap_apple", "iap_google", "apple_iap", "google_iap"]}},
            ],
        },
        {"_id": 0},
    ).sort("created_at", -1).limit(500).to_list(500)

    apple_txs = [t for t in iap_txs if "apple" in str(t.get("provider", t.get("payment_method", ""))).lower()]
    google_txs = [t for t in iap_txs if "google" in str(t.get("provider", t.get("payment_method", ""))).lower()]

    def _summarize(txs, label):
        total = len(txs)
        completed = sum(1 for t in txs if str(t.get("status", t.get("payment_status", ""))).lower() in {"completed", "paid", "active", "succeeded"})
        refunded = sum(1 for t in txs if str(t.get("status", t.get("payment_status", ""))).lower() in {"refunded", "reversed"})
        pending = total - completed - refunded
        revenue = sum(float(t.get("amount_gross", t.get("amount", 0)) or 0) for t in txs if str(t.get("status", t.get("payment_status", ""))).lower() in {"completed", "paid", "active", "succeeded"})
        with_tax = sum(1 for t in txs if float(t.get("tax_amount", 0) or 0) > 0)
        with_ledger = sum(1 for t in txs if t.get("transaction_id"))
        return {
            "provider": label,
            "total_transactions": total,
            "completed": completed,
            "pending": pending,
            "refunded": refunded,
            "reconciliation_rate": round((completed / total) * 100, 1) if total else 100.0,
            "total_revenue": round(revenue, 2),
            "tax_compliance_rate": round((with_tax / total) * 100, 1) if total else 100.0,
            "ledger_coverage": round((with_ledger / total) * 100, 1) if total else 100.0,
            "status": "healthy" if (not total or (completed / total) >= 0.9) else "warning" if (completed / total) >= 0.7 else "critical",
        }

    apple_summary = _summarize(apple_txs, "Apple IAP")
    google_summary = _summarize(google_txs, "Google Play")

    # Recent IAP transactions for inspection
    recent = []
    for t in iap_txs[:20]:
        recent.append({
            "transaction_id": t.get("transaction_id", "N/A"),
            "provider": t.get("provider", t.get("payment_method", "unknown")),
            "amount": t.get("amount_gross", t.get("amount", 0)),
            "currency": t.get("currency", "USD"),
            "status": t.get("status", t.get("payment_status", "unknown")),
            "tax_amount": t.get("tax_amount", 0),
            "created_at": t.get("created_at", ""),
            "user_id": t.get("user_id", ""),
        })

    return {
        "window_hours": window_hours,
        "generated_at": now.isoformat(),
        "apple": apple_summary,
        "google": google_summary,
        "combined": {
            "total_transactions": apple_summary["total_transactions"] + google_summary["total_transactions"],
            "total_revenue": round(apple_summary["total_revenue"] + google_summary["total_revenue"], 2),
            "overall_reconciliation_rate": round(
                ((apple_summary["completed"] + google_summary["completed"]) /
                 max(apple_summary["total_transactions"] + google_summary["total_transactions"], 1)) * 100, 1
            ),
        },
        "recent_transactions": recent,
        "config": {
            "apple_configured": bool(os.environ.get("APPLE_IAP_SHARED_SECRET")),
            "google_configured": bool(os.environ.get("GOOGLE_PLAY_PACKAGE_NAME")),
        },
    }


# ── Tax/Fee Explainability Overlay Engine ──────────────────────────
@router.get("/tax-explainability/{transaction_id}")
async def get_tax_explainability(transaction_id: str, user=Depends(get_current_user)):
    """Deep tax/fee explainability overlay for a given transaction."""
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    tx = await db.payment_transactions.find_one(
        {"transaction_id": transaction_id},
        {"_id": 0},
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    ledger = await db.financial_ledger_entries.find_one(
        {"transaction_id": transaction_id},
        {"_id": 0},
    )

    jurisdiction = tx.get("jurisdiction", {})
    country = jurisdiction.get("country", "") if isinstance(jurisdiction, dict) else ""
    state = jurisdiction.get("state", "") if isinstance(jurisdiction, dict) else ""

    subtotal = float(tx.get("subtotal", tx.get("amount", 0)) or 0)
    tax_amount = float(tx.get("tax_amount", 0) or 0)
    tax_rate = float(tx.get("tax_rate", 0) or 0)
    processing_fee = float(tx.get("processing_fee", 0) or 0)
    amount_gross = float(tx.get("amount_gross", subtotal + tax_amount) or 0)
    amount_net = float(tx.get("amount_net", max(amount_gross - processing_fee, 0)) or 0)
    provider = str(tx.get("provider", tx.get("payment_method", ""))).lower()

    # Determine tax rule applied
    tax_rule = "standard_jurisdiction"
    tax_rule_detail = f"Tax calculated based on jurisdiction: {country}-{state}" if state else f"Tax calculated based on country: {country}"
    if provider in ("fedapay", "mobile_money_fedapay"):
        tax_rule = "fedapay_fixed_8.25%"
        tax_rule_detail = "Fixed 8.25% tax applied to all FedaPay transactions per platform policy."
    elif country == "FR" or (country == "CA" and state == "QC"):
        if country == "FR":
            tax_rule = "eu_vat_france"
            tax_rule_detail = f"EU VAT applied at {tax_rate * 100:.1f}% for digital services in France."
        else:
            tax_rule = "canada_gst_qst"
            tax_rule_detail = f"GST (5%) + QST (9.975%) = {tax_rate * 100:.3f}% applied for Quebec, Canada."

    # Build breakdown
    breakdown = tx.get("tax_breakdown", {})

    return {
        "transaction_id": transaction_id,
        "explainability": {
            "subtotal": round(subtotal, 2),
            "tax": {
                "amount": round(tax_amount, 2),
                "rate": round(tax_rate, 4),
                "rate_display": f"{tax_rate * 100:.2f}%",
                "rule": tax_rule,
                "rule_detail": tax_rule_detail,
                "breakdown": breakdown,
                "jurisdiction": {"country": country, "state": state},
            },
            "processing_fee": {
                "amount": round(processing_fee, 2),
                "provider": provider,
                "policy": "Provider processing fee charged separately. Not included in tax calculation.",
            },
            "gross_amount": round(amount_gross, 2),
            "gross_formula": f"Subtotal ({round(subtotal, 2)}) + Tax ({round(tax_amount, 2)}) = {round(amount_gross, 2)}",
            "net_amount": round(amount_net, 2),
            "net_formula": f"Gross ({round(amount_gross, 2)}) - Processing Fee ({round(processing_fee, 2)}) = {round(amount_net, 2)}",
            "currency": tx.get("currency", "USD"),
            "product_type": tx.get("product_type", "Digital Platform Access"),
        },
        "ledger": {
            "recorded": ledger is not None,
            "sequence": ledger.get("sequence") if ledger else None,
            "entry_hash": ledger.get("entry_hash") if ledger else None,
        },
        "metadata": {
            "provider": provider,
            "plan": tx.get("plan_id", ""),
            "billing_period": tx.get("billing_period", ""),
            "created_at": tx.get("created_at", ""),
        },
    }



# ── Factory Gate Health Endpoints ──

@router.get("/factory-gate/summary")
async def get_factory_gate_summary(user=Depends(get_current_user)):
    """Get factory gate health summary for admin card."""
    from services.platform_health.factory_gate import get_gate_summary
    return await get_gate_summary()


@router.get("/factory-gate/trends")
async def get_factory_gate_trends(days: int = 14, user=Depends(get_current_user)):
    """Get factory gate PASS/FAIL trends."""
    from services.platform_health.factory_gate import get_gate_trends
    return await get_gate_trends(days=min(days, 90))


@router.get("/factory-gate/history")
async def get_factory_gate_history(limit: int = 30, user=Depends(get_current_user)):
    """Get factory gate run history."""
    from services.platform_health.factory_gate import get_gate_history
    return {"runs": await get_gate_history(limit=min(limit, 100))}


@router.post("/factory-gate/record")
async def record_factory_gate_result(request: Request, user=Depends(get_current_user)):
    """Record a factory gate run result (called by CI pipeline or admin)."""
    from services.platform_health.factory_gate import record_gate_result
    body = await request.json()
    result = await record_gate_result(body)
    return {"status": "recorded", "result": result}


# ── Executive Quality Trend Analytics + Cross-Dashboard Drill-Down ──

@router.get("/executive/quality-trends")
async def get_executive_quality_trends(days: int = 30, user=Depends(get_current_user)):
    """Executive quality trend analytics across all quality domains."""
    from services.platform_health.quality_trends import get_quality_trend_snapshot
    return await get_quality_trend_snapshot(days=min(days, 90))


@router.get("/executive/quality-drill-down")
async def get_executive_quality_drill_down(domain: str = "health", days: int = 14, user=Depends(get_current_user)):
    """Drill-down into a specific quality domain (health, gate, slo, enforcement)."""
    from services.platform_health.quality_trends import get_drill_down
    return await get_drill_down(domain=domain, days=min(days, 90))


@router.get("/executive/stale-link-risk")
async def get_executive_stale_link_risk(user=Depends(get_current_user)):
    """Executive stale-link risk score for Admin Console visibility."""
    from services.platform_health.stale_link_risk import get_stale_link_risk_snapshot
    return await get_stale_link_risk_snapshot()


# ── Signed PDF Compliance Report ──

@router.get("/enterprise-standard/enforcement/{run_id}/compliance-report/pdf")
async def get_enterprise_compliance_report_pdf(run_id: str, user=Depends(get_current_user)):
    """Download a signed PDF compliance report for a specific enforcement run."""
    from services.platform_health.compliance_pdf import generate_compliance_pdf
    from fastapi.responses import Response as FastAPIResponse
    from utils.pdf_v15_filename import build_pdf_v15_filename

    enforcement_doc = await db.enterprise_standard_enforcement_history.find_one(
        {"run_id": run_id}, {"_id": 0}
    )
    if not enforcement_doc:
        raise HTTPException(status_code=404, detail="Enforcement run not found")

    report = _build_enterprise_compliance_report(run_id, enforcement_doc, user.email, "pdf_download")
    pdf_bytes = generate_compliance_pdf(report)

    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("compliance", run_id)}"',
            "X-Report-ID": report.get("report_id", run_id),
        },
    )


# ── SLO Safe Mode Profile Presets ──

SLO_SAFE_MODE_PRESETS = {
    "conservative": {
        "label": "Conservative",
        "description": "Strict thresholds, low tolerance. Best for production-critical workloads.",
        "p95_latency_threshold_ms": 200,
        "min_samples": 60,
        "breach_consecutive_checks": 1,
        "cooldown_minutes": 10,
        "check_interval_seconds": 120,
        "auto_fix_recipes": ["warm_hot_caches", "guardian_auto_fix", "platform_auto_fix"],
    },
    "balanced": {
        "label": "Balanced",
        "description": "Moderate thresholds with reasonable tolerance. Good for most workloads.",
        "p95_latency_threshold_ms": 300,
        "min_samples": 40,
        "breach_consecutive_checks": 2,
        "cooldown_minutes": 20,
        "check_interval_seconds": 180,
        "auto_fix_recipes": ["warm_hot_caches", "guardian_auto_fix", "platform_auto_fix"],
    },
    "aggressive": {
        "label": "Aggressive",
        "description": "Relaxed thresholds, high tolerance. Minimizes false positives in dev/staging.",
        "p95_latency_threshold_ms": 500,
        "min_samples": 20,
        "breach_consecutive_checks": 4,
        "cooldown_minutes": 45,
        "check_interval_seconds": 300,
        "auto_fix_recipes": ["warm_hot_caches"],
    },
}


@router.get("/enterprise-standard/slo-auto-mitigation/presets")
async def get_slo_presets(user=Depends(require_admin)):
    """Get available SLO Safe Mode profile presets."""
    current_policy = await db.admin_settings.find_one({"key": SLO_POLICY_FLAG_KEY}, {"_id": 0})
    normalized = _normalize_slo_auto_mitigation_policy(current_policy)
    # Detect which preset matches current config
    active_preset = "custom"
    for key, preset in SLO_SAFE_MODE_PRESETS.items():
        if (normalized.get("p95_latency_threshold_ms") == preset["p95_latency_threshold_ms"]
                and normalized.get("breach_consecutive_checks") == preset["breach_consecutive_checks"]
                and normalized.get("cooldown_minutes") == preset["cooldown_minutes"]):
            active_preset = key
            break
    return {"presets": SLO_SAFE_MODE_PRESETS, "active_preset": active_preset, "current_policy": normalized}


@router.post("/enterprise-standard/slo-auto-mitigation/apply-preset")
async def apply_slo_preset(request: Request, user=Depends(require_admin)):
    """Apply a Safe Mode profile preset to the SLO auto-mitigation policy."""
    body = await request.json()
    preset_key = body.get("preset", "balanced")
    if preset_key not in SLO_SAFE_MODE_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {preset_key}. Options: {list(SLO_SAFE_MODE_PRESETS.keys())}")

    preset = SLO_SAFE_MODE_PRESETS[preset_key]
    current = await db.admin_settings.find_one({"key": SLO_POLICY_FLAG_KEY}, {"_id": 0}) or {}
    updated = {
        "key": SLO_POLICY_FLAG_KEY,
        "enabled": current.get("enabled", False),
        "p95_latency_threshold_ms": preset["p95_latency_threshold_ms"],
        "min_samples": preset["min_samples"],
        "breach_consecutive_checks": preset["breach_consecutive_checks"],
        "cooldown_minutes": preset["cooldown_minutes"],
        "check_interval_seconds": preset["check_interval_seconds"],
        "auto_fix_recipes": preset["auto_fix_recipes"],
        "applied_preset": preset_key,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.admin_settings.update_one({"key": SLO_POLICY_FLAG_KEY}, {"$set": updated}, upsert=True)
    return {"status": "applied", "preset": preset_key, "policy": _normalize_slo_auto_mitigation_policy(updated)}


# ── Anomaly-Aware Adaptive SLO Thresholds ──

@router.get("/enterprise-standard/slo-auto-mitigation/adaptive-thresholds")
async def get_adaptive_slo_thresholds(user=Depends(require_admin)):
    """Compute time-of-day and load-aware adaptive p95 thresholds to reduce false positives."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()

    # Get recent SLO check history
    history = await db.enterprise_slo_auto_mitigation_history.find(
        {"checked_at": {"$gte": cutoff_24h}},
        {"_id": 0, "p95_ms": 1, "sample_count": 1, "checked_at": 1, "result": 1}
    ).sort("checked_at", -1).limit(500).to_list(500)

    if not history:
        return {"adaptive_enabled": False, "reason": "insufficient_data", "data_points": 0}

    # Bucket by hour-of-day
    hourly_buckets: Dict[int, list] = {h: [] for h in range(24)}
    for entry in history:
        try:
            ts = entry.get("checked_at", "")
            hour = int(ts[11:13]) if len(ts) > 13 else 0
            p95 = entry.get("p95_ms", 0)
            if p95 and p95 > 0:
                hourly_buckets[hour].append(p95)
        except (ValueError, IndexError):
            continue

    # Compute adaptive bands per hour
    adaptive_bands = {}
    for hour, values in hourly_buckets.items():
        if len(values) < 3:
            adaptive_bands[hour] = {"p95_mean": None, "p95_p90": None, "samples": len(values), "suggested_threshold": None}
            continue
        sorted_vals = sorted(values)
        mean = round(sum(sorted_vals) / len(sorted_vals), 1)
        p90_idx = int(len(sorted_vals) * 0.9)
        p90 = sorted_vals[min(p90_idx, len(sorted_vals) - 1)]
        # Suggested threshold = p90 + 20% headroom
        suggested = round(p90 * 1.2, 0)
        adaptive_bands[hour] = {"p95_mean": mean, "p95_p90": round(p90, 1), "samples": len(values), "suggested_threshold": suggested}

    # Overall adaptive recommendation
    all_p95 = [v for vals in hourly_buckets.values() for v in vals]
    overall_mean = round(sum(all_p95) / max(len(all_p95), 1), 1) if all_p95 else 0
    breach_count = sum(1 for e in history if e.get("result") == "breach_detected")
    total = len(history)

    return {
        "adaptive_enabled": True,
        "data_points": total,
        "overall_p95_mean_ms": overall_mean,
        "breach_rate_24h": round(breach_count / max(total, 1) * 100, 1),
        "breach_count_24h": breach_count,
        "hourly_bands": adaptive_bands,
        "recommendation": "tighten" if breach_count == 0 and overall_mean < 150 else "maintain" if breach_count / max(total, 1) < 0.15 else "relax",
    }
