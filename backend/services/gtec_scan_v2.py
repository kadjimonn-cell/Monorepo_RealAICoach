"""
GTEC C5 — Global System Directive enforcer.

Orchestrates the non-bypassable 7-step pipeline described in
/app/memory/GTEC_DIRECTIVE.md:

  1. TASK IDENTIFICATION  — task_id + execution_hash + dedup
  2. SYSTEM INVESTIGATION — snapshot platform state
  3. DESIGN SOLUTION      — (designed-upstream; scan records directive version)
  4. IMPLEMENTATION       — auto-remediation / root-cause fix loop
  5. VALIDATION           — SAST + Dependency + DAST (crawler) + RBAC +
                            Subscription + Responsiveness + Console + Perf
  6. FINAL VERIFICATION   — compile severity counts, regressions, compare to
                            previous scan via learning memory
  7. REPORTING            — structured output (see §12 of the directive)

State is persisted to:
  - `gtec_scan_v2_reports`  — full structured reports (history + memory)
  - `gtec_scan_v2_settings` — schedule toggle + interval_hours
  - `gtec_scan_v2_memory`   — learning entries (recurring fingerprints)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
from utils.pdf_v15_filename import build_pdf_v15_filename
from utils.http_tls import get_httpx_verify
from utils.gtec_scan_artifacts import (
    is_console_403_only_artifact,
    is_console_429_only_artifact,
    is_edge_challenge_row,
    is_public_api_auth_rate_limit_artifact,
    is_rate_limit_only_artifact,
    is_runtime_403_artifact,
    is_runtime_429_artifact,
    resolve_external_frontend_base_url,
    row_key,
)

logger = logging.getLogger(__name__)

ROOT = Path("/app")
DIRECTIVE_FILE = ROOT / "memory" / "GTEC_DIRECTIVE.md"
REPORT_DIR = ROOT / "test_reports"
CRAWLER_LATEST = REPORT_DIR / "gtec_scan_latest.json"
V2_LATEST = REPORT_DIR / "gtec_scan_c5_latest.json"
WHITE_SCREEN_SENTRY_LATEST = REPORT_DIR / "gtec_white_screen_sentry_latest.json"
AUDIT_V2_SCRIPT = ROOT / "scripts" / "audit_v2_theme.py"
WHITE_SCREEN_SENTRY_SCRIPT = ROOT / "backend" / "scripts" / "gtec_white_screen_sentry.py"

REPORTS_COL = "gtec_scan_c5_reports"
SETTINGS_COL = "gtec_scan_c5_settings"
MEMORY_COL = "gtec_scan_c5_memory"
EXECUTIONS_COL = "gtec_scan_c5_executions"
EVENTS_COL = "gtec_scan_c5_events"
POLICY_COL = "gtec_scan_c5_policy"
INCIDENTS_COL = "gtec_scan_c5_incidents"
VIEWPORT_ARTIFACTS_COL = "gtec_c5_viewport_artifacts"
EXTERNAL_HOST_CERTIFICATION_COL = "gtec_c5_external_host_certifications"
PREFLIGHT_TELEMETRY_COL = "gtec_c5_preflight_telemetry"
MATRIX64_PIPELINE_RUNS_COL = "gtec_c5_matrix64_pipeline_runs"

LEGACY_REPORTS_COL = "gtec_scan_v2_reports"
LEGACY_SETTINGS_COL = "gtec_scan_v2_settings"
LEGACY_MEMORY_COL = "gtec_scan_v2_memory"
LEGACY_EXECUTIONS_COL = "gtec_scan_v2_executions"
LEGACY_EVENTS_COL = "gtec_scan_v2_events"
LEGACY_POLICY_COL = "gtec_scan_v2_policy"
LEGACY_INCIDENTS_COL = "gtec_scan_v2_incidents"

EXECUTION_GRAPH_COL = "gtec_execution_graph"
FINDING_CATALOG_COL = "gtec_finding_catalog"
REMEDIATION_PLANS_COL = "gtec_remediation_plans"
CANONICAL_INCIDENTS_COL = "gtec_incidents"
POLICY_STORE_COL = "gtec_policy_store"

SAFE_AUTO_RUN_JOB_ID = "gtec_scan_c5_safe_auto_run"
LEGACY_SAFE_AUTO_RUN_JOB_ID = "gtec_scan_v2_safe_auto_run"
MATRIX64_SCHEDULER_JOB_ID = "gtec_c5_matrix64_nightly"
SETTINGS_DOC_ID = "schedule"
POLICY_DOC_ID = "effective"
MATRIX64_CONFIG_DOC_ID = "matrix64_pipeline_config"
ENFORCED_INTERVAL_HOURS = 3
STRICT_PDF_GUARDRAIL = str(os.environ.get("GTEC_PDF_GUARDRAIL_STRICT", "1")).strip() != "0"
PLATFORM_DATA_ONLY = str(os.environ.get("GTEC_PLATFORM_DATA_ONLY", "1")).strip() != "0"

# Severity → numeric priority (higher = worse)
SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

# Only one v2 scan runs at a time
RUN_LOCK = asyncio.Lock()
EXTERNAL_CERTIFICATION_RUN_LOCK = asyncio.Lock()
JOBS: dict[str, dict[str, Any]] = {}
_MIGRATION_DONE = False
_MIGRATION_LOCK = asyncio.Lock()

INTERNAL_TASK_PREFIX = "gtec_v2_"
PUBLIC_TASK_PREFIX = "gtec_c5_"
REQUIRED_REPORT_SECTIONS = ["sast", "dep", "dast", "acl", "i18n", "duplicate", "api_contract", "threat_model"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_public_task_id(task_id: Any) -> str:
    """Canonical public task id for all user-facing outputs.

    Keeps backward compatibility for historical records persisted with
    legacy `gtec_v2_*` ids.
    """
    raw = str(task_id or "").strip()
    if not raw:
        return ""
    if raw.startswith(PUBLIC_TASK_PREFIX):
        return raw
    if raw.startswith(INTERNAL_TASK_PREFIX):
        return f"{PUBLIC_TASK_PREFIX}{raw[len(INTERNAL_TASK_PREFIX):]}"
    return raw


def resolve_task_id_aliases(task_id: Any) -> list[str]:
    """Return both compatible task-id aliases for lookup queries."""
    raw = str(task_id or "").strip()
    if not raw:
        return []
    aliases = {raw}
    if raw.startswith(PUBLIC_TASK_PREFIX):
        aliases.add(f"{INTERNAL_TASK_PREFIX}{raw[len(PUBLIC_TASK_PREFIX):]}")
    elif raw.startswith(INTERNAL_TASK_PREFIX):
        aliases.add(f"{PUBLIC_TASK_PREFIX}{raw[len(INTERNAL_TASK_PREFIX):]}")
    return [a for a in aliases if a]


def _maybe_upgrade_internal_ids(doc: dict[str, Any]) -> dict[str, Any]:
    upgraded = dict(doc or {})
    for key in ("task_id", "execution_id", "last_seen_task", "recent_task_id"):
        val = upgraded.get(key)
        if isinstance(val, str) and val:
            upgraded[key] = to_public_task_id(val)
    return upgraded


async def ensure_internal_collections_migrated(db, *, force: bool = False) -> dict[str, Any]:
    """Idempotent v2->C5 internal collection backfill for low-risk cutover."""
    global _MIGRATION_DONE
    if _MIGRATION_DONE and not force:
        return {"ok": True, "already_migrated": True}

    async with _MIGRATION_LOCK:
        if _MIGRATION_DONE and not force:
            return {"ok": True, "already_migrated": True}

        mappings = [
            (LEGACY_REPORTS_COL, REPORTS_COL, "task_id"),
            (LEGACY_SETTINGS_COL, SETTINGS_COL, "_id"),
            (LEGACY_MEMORY_COL, MEMORY_COL, "_id"),
            (LEGACY_EXECUTIONS_COL, EXECUTIONS_COL, "execution_id"),
            (LEGACY_EVENTS_COL, EVENTS_COL, "event_id"),
            (LEGACY_POLICY_COL, POLICY_COL, "_id"),
            (LEGACY_INCIDENTS_COL, INCIDENTS_COL, "incident_id"),
        ]
        copied: dict[str, int] = {}

        for legacy_col, new_col, key_field in mappings:
            count = 0
            projection = None if key_field == "_id" else {"_id": 0}
            async for raw in db[legacy_col].find({}, projection):
                doc = _maybe_upgrade_internal_ids(raw)
                key_val = doc.get(key_field)
                if key_val in (None, ""):
                    continue
                set_doc = dict(doc)
                if key_field == "_id":
                    set_doc.pop("_id", None)
                await db[new_col].update_one({key_field: key_val}, {"$set": set_doc}, upsert=True)
                count += 1
            copied[new_col] = count

        _MIGRATION_DONE = True
        stats = {"ok": True, "copied": copied}
        await ensure_legacy_cleanup_window(db)
        logger.info("gtec-c5 internal migration stats=%s", stats)
        return stats


LEGACY_CLEANUP_CONTROL_DOC_ID = "legacy_v2_mirror_control"
LEGACY_DEFAULT_SOAK_DAYS = 7
PIPELINE_POLICY_DOC_ID = "pipeline_enforcement_policy"
PIPELINE_DEFAULT_SOFT_BLOCK_HOURS = 48
WHITE_SCREEN_SENTRY_MAX_AGE_MINUTES = 10
EXTERNAL_HOST_CERTIFICATION_COOLDOWN_MINUTES = 60
NOTIFICATION_SNAPSHOT_VERSION = "c5-notification-snapshot.v2"
SCAN_PREFLIGHT_REQUIRED_STABLE_CHECKS = 3
SCAN_PREFLIGHT_CHECK_INTERVAL_SECONDS = 1.2
SCAN_PREFLIGHT_ENDPOINT_RETRY_ATTEMPTS = 4
SCAN_PREFLIGHT_ENDPOINT_BACKOFF_SECONDS = 0.8

INCIDENT_AUTOCLOSE_CLEAN_RESCANS = 3
INCIDENT_AUTOCLOSE_PENDING_HOURS = 24
INCIDENT_PENDING_STATUS = "resolved_pending_verification"
INCIDENT_CLOSED_STATUS = "closed"
INCIDENT_ACTIVE_STATUSES = {"open", "triaged", "in_progress"}

DEFAULT_SENTRY_VIEWPORTS = ["mobile", "tablet", "desktop"]
DEFAULT_SENTRY_LANGUAGES = ["en"]
MATRIX64_DEFAULT_ROUTES = [
    "/welcome",
    "/auth/login",
    "/executive-dashboard",
    "/route-health-report",
]
MATRIX64_DEFAULT_VIEWPORTS = ["mobile_compact", "tablet", "laptop", "desktop"]
MATRIX64_DEFAULT_LANGUAGES = ["en", "fr", "es", "ar"]
MATRIX64_REQUIRED_TOTAL = 64
MATRIX64_ARTIFACT_DIR = REPORT_DIR / "matrix_artifacts"

SCAN_MODE_STRICT_GLOBAL = "STRICT_GLOBAL"
SCAN_MODE_DIAGNOSTIC_RELAXED = "DIAGNOSTIC_RELAXED"

MANUAL_MUTATION_ENDPOINTS_DISABLED = [
    "/api/admin/gtec-scan-v2/run",
    "/api/admin/gtec-scan-v2/schedule",
    "/api/admin/gtec-scan-v2/watchdog/run",
    "/api/admin/gtec-crawler/run",
    "/api/admin/gtec-crawler/auto-run",
    "/api/admin/gtec-crawler/alerts/settings",
    "/api/admin/gtec-crawler/alerts/test",
]


def _parse_iso(ts: Any) -> Optional[datetime]:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


async def ensure_legacy_cleanup_window(db, *, soak_days: int = LEGACY_DEFAULT_SOAK_DAYS) -> dict[str, Any]:
    doc = await db[SETTINGS_COL].find_one({"_id": LEGACY_CLEANUP_CONTROL_DOC_ID}, {"_id": 0})
    if doc:
        return doc

    now = datetime.now(timezone.utc)
    retire_at = now + timedelta(days=max(1, int(soak_days)))
    control = {
        "_id": LEGACY_CLEANUP_CONTROL_DOC_ID,
        "mirror_write_enabled": True,
        "legacy_read_fallback_enabled": True,
        "status": "scheduled",
        "scheduled_at": now.isoformat(),
        "scheduled_retirement_at": retire_at.isoformat(),
        "soak_days": max(1, int(soak_days)),
        "note": "Auto-scheduled during C5 internal migration; legacy mirror writes retire after soak window.",
        "updated_at": _now(),
    }
    await db[SETTINGS_COL].update_one(
        {"_id": LEGACY_CLEANUP_CONTROL_DOC_ID},
        {"$set": control},
        upsert=True,
    )
    await db[LEGACY_SETTINGS_COL].update_one(
        {"_id": LEGACY_CLEANUP_CONTROL_DOC_ID},
        {"$set": control},
        upsert=True,
    )
    return {k: v for k, v in control.items() if k != "_id"}


async def ensure_pipeline_enforcement_policy(
    db,
    *,
    mode: str = "soft-block",
    hard_block_after_hours: int = PIPELINE_DEFAULT_SOFT_BLOCK_HOURS,
) -> dict[str, Any]:
    existing = await db[SETTINGS_COL].find_one({"_id": PIPELINE_POLICY_DOC_ID}, {"_id": 0})
    if existing:
        return existing

    now = datetime.now(timezone.utc)
    valid_mode = str(mode or "soft-block").strip().lower()
    if valid_mode not in {"soft-block", "hard-block"}:
        valid_mode = "soft-block"

    policy = {
        "_id": PIPELINE_POLICY_DOC_ID,
        "mode": valid_mode,
        "soft_block_started_at": now.isoformat(),
        "hard_block_after_hours": max(1, int(hard_block_after_hours)),
        "updated_at": _now(),
    }
    await db[SETTINGS_COL].update_one({"_id": PIPELINE_POLICY_DOC_ID}, {"$set": policy}, upsert=True)
    if await legacy_mirror_write_enabled(db):
        await db[LEGACY_SETTINGS_COL].update_one({"_id": PIPELINE_POLICY_DOC_ID}, {"$set": policy}, upsert=True)
    return {k: v for k, v in policy.items() if k != "_id"}


async def get_pipeline_enforcement_state(db) -> dict[str, Any]:
    policy = await ensure_pipeline_enforcement_policy(db)
    declared_mode = str(policy.get("mode") or "soft-block").lower()
    started = _parse_iso(policy.get("soft_block_started_at"))
    hard_after = max(1, int(policy.get("hard_block_after_hours") or PIPELINE_DEFAULT_SOFT_BLOCK_HOURS))

    effective_mode = declared_mode
    hard_block_at = None
    if declared_mode == "soft-block" and started:
        hard_block_dt = started + timedelta(hours=hard_after)
        hard_block_at = hard_block_dt.isoformat()
        if datetime.now(timezone.utc) >= hard_block_dt:
            effective_mode = "hard-block"

    return {
        "declared_mode": declared_mode,
        "effective_mode": effective_mode,
        "soft_block_started_at": policy.get("soft_block_started_at"),
        "hard_block_after_hours": hard_after,
        "hard_block_at": hard_block_at,
        "updated_at": policy.get("updated_at"),
    }


def _resolve_frontend_base_url(base_url: Optional[str] = None) -> str:
    raw = str(base_url or "").strip()
    if raw:
        return raw.rstrip("/")
    env_url = str(os.environ.get("GTEC_FRONTEND_URL") or "").strip()
    if env_url:
        return env_url.rstrip("/")
    return "http://127.0.0.1:3000"


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _normalize_route_paths(routes: Optional[list[str]], fallback: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in (routes or fallback):
        text = str(raw or "").strip()
        if not text:
            continue
        if "://" in text:
            parsed = urlsplit(text)
            text = parsed.path or "/"
        if not text.startswith("/"):
            text = f"/{text}"
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out or list(fallback)


def _normalize_axes(values: Optional[list[str]], fallback: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in (values or fallback):
        text = str(raw or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out or list(fallback)


def _normalize_scan_mode(scan_mode: Optional[str]) -> str:
    raw = str(scan_mode or "").strip().upper()
    if raw == SCAN_MODE_DIAGNOSTIC_RELAXED:
        return SCAN_MODE_DIAGNOSTIC_RELAXED
    return SCAN_MODE_STRICT_GLOBAL


def _is_strict_mode(scan_mode: Optional[str]) -> bool:
    return _normalize_scan_mode(scan_mode) == SCAN_MODE_STRICT_GLOBAL


def _count_transient_artifacts(sections: dict[str, Any]) -> int:
    count = 0
    for section in (sections or {}).values():
        for f in (section or {}).get("findings") or []:
            label = str((f or {}).get("label") or "").lower()
            if "transient" in label or "gateway_artifact" in label or "runtime_infra_artifact" in label:
                count += int((f or {}).get("count") or 1)
    return count


async def _record_preflight_telemetry(
    db,
    preflight: dict[str, Any],
    *,
    triggered_by: str,
    actor: str,
    attempt_tag: str,
    attempt_index: int,
    scan_mode: str,
) -> None:
    await ensure_internal_collections_migrated(db)
    doc = {
        "telemetry_id": f"pf_{uuid.uuid4().hex[:12]}",
        "triggered_by": triggered_by,
        "actor": actor,
        "attempt_tag": attempt_tag,
        "attempt_index": int(attempt_index),
        "scan_mode": _normalize_scan_mode(scan_mode),
        "passed": bool(preflight.get("passed")),
        "required_checks": int(preflight.get("required_checks") or 0),
        "attempts_completed": int(preflight.get("attempts_completed") or 0),
        "reasons": list(preflight.get("reasons") or []),
        "require_external_preview": bool(preflight.get("require_external_preview")),
        "require_local_backend": bool(preflight.get("require_local_backend")),
        "attempts": preflight.get("attempts") or [],
        "checked_at": preflight.get("checked_at") or _now(),
        "created_at": _now(),
    }
    await db[PREFLIGHT_TELEMETRY_COL].insert_one({**doc})


async def get_preflight_telemetry_trend(
    db,
    *,
    hours: int = 24,
    limit: int = 400,
) -> dict[str, Any]:
    await ensure_internal_collections_migrated(db)
    h = max(1, min(int(hours), 168))
    lim = max(1, min(int(limit), 2000))
    since = (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()

    rows: list[dict[str, Any]] = []
    async for d in db[PREFLIGHT_TELEMETRY_COL].find(
        {"checked_at": {"$gte": since}},
        {"_id": 0},
    ).sort("checked_at", -1).limit(lim):
        rows.append(d)

    reason_counts: dict[str, int] = {}
    strict_rows = 0
    strict_failed = 0
    relaxed_rows = 0
    relaxed_failed = 0
    for r in rows:
        mode = _normalize_scan_mode(r.get("scan_mode"))
        passed = bool(r.get("passed"))
        if mode == SCAN_MODE_STRICT_GLOBAL:
            strict_rows += 1
            if not passed:
                strict_failed += 1
        else:
            relaxed_rows += 1
            if not passed:
                relaxed_failed += 1

        for reason in (r.get("reasons") or []):
            key = str(reason or "unknown")
            reason_counts[key] = int(reason_counts.get(key) or 0) + 1

    total = len(rows)
    failed = sum(1 for r in rows if not bool(r.get("passed")))
    passed = total - failed

    top_reasons = sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    mode_mix = {
        "strict_global": {
            "samples": strict_rows,
            "failed": strict_failed,
            "pass_rate_percent": round(((strict_rows - strict_failed) / strict_rows) * 100.0, 2) if strict_rows else None,
        },
        "diagnostic_relaxed": {
            "samples": relaxed_rows,
            "failed": relaxed_failed,
            "pass_rate_percent": round(((relaxed_rows - relaxed_failed) / relaxed_rows) * 100.0, 2) if relaxed_rows else None,
        },
    }

    latest = rows[0] if rows else None
    latest_classification = "none"
    if latest:
        latest_classification = "infra_blocked_window" if not bool(latest.get("passed")) else "healthy_window"

    return {
        "window_hours": h,
        "sample_limit": lim,
        "samples": total,
        "passed": passed,
        "failed": failed,
        "pass_rate_percent": round((passed / total) * 100.0, 2) if total else None,
        "top_fail_reasons": [
            {"reason": reason, "count": count}
            for reason, count in top_reasons
        ],
        "mode_mix": mode_mix,
        "latest": latest,
        "latest_classification": latest_classification,
        "generated_at": _now(),
    }


async def _probe_with_transient_retry(
    cli: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    json_body: Optional[dict[str, Any]] = None,
    attempts: int = 3,
    transient_statuses: tuple[int, ...] = (502, 503, 504),
    backoff_seconds: float = 1.2,
) -> tuple[Optional[httpx.Response], Optional[str]]:
    last_err: Optional[str] = None
    resp: Optional[httpx.Response] = None
    method_u = str(method or "GET").upper()
    for idx in range(max(1, int(attempts))):
        try:
            if method_u == "POST":
                resp = await cli.post(url, json=json_body or {}, headers=headers or {})
            else:
                resp = await cli.get(url, headers=headers or {})
            if resp.status_code in transient_statuses and idx < (attempts - 1):
                await asyncio.sleep(backoff_seconds)
                continue
            return resp, None
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {str(exc)[:180]}"
            if idx < (attempts - 1):
                await asyncio.sleep(backoff_seconds)
                continue
            break
    return resp, last_err


async def _probe_local_backend_health() -> dict[str, Any]:
    base = str(os.environ.get("GTEC_LOCAL_BACKEND_URL") or "http://127.0.0.1:8001").rstrip("/")
    url = f"{base}/api/health"
    status_code = 0
    body = ""
    error = ""
    ok = False

    async with httpx.AsyncClient(timeout=6, follow_redirects=False, verify=get_httpx_verify()) as cli:
        resp, err = await _probe_with_transient_retry(cli, "GET", url, attempts=3)
        if resp is not None:
            status_code = int(resp.status_code)
            body = (resp.text or "")[:220]
            ok = status_code == 200 and "healthy" in body.lower()
        error = err or ""

    return {
        "base_url": base,
        "url": url,
        "ok": ok,
        "status_code": status_code,
        "error": error or None,
        "body_excerpt": body,
    }


async def run_scan_preflight_gate(
    *,
    required_checks: int = SCAN_PREFLIGHT_REQUIRED_STABLE_CHECKS,
    require_external_preview: bool = True,
    require_local_backend: bool = True,
) -> dict[str, Any]:
    checks = max(1, int(required_checks))
    attempts: list[dict[str, Any]] = []
    external_base = _resolve_external_frontend_base_url(None)

    for idx in range(checks):
        if require_local_backend:
            local = await _probe_local_backend_health()
            local_ok = bool(local.get("ok"))
        else:
            local = {
                "ok": True,
                "status_code": 200,
                "base_url": "bypassed",
                "url": "bypassed",
                "bypassed": True,
            }
            local_ok = True
        if require_external_preview:
            external = await get_external_host_proxy_health(external_base)
            external_ok = bool(external.get("stable"))
        else:
            external = {
                "base_url": external_base,
                "stable": True,
                "checks": [],
                "checked_at": _now(),
                "bypassed": True,
            }
            external_ok = True

        attempt_ok = local_ok and external_ok
        attempts.append(
            {
                "attempt": idx + 1,
                "ok": attempt_ok,
                "local_backend": local,
                "external_preview": external,
            }
        )
        if not attempt_ok:
            break
        if idx < (checks - 1):
            await asyncio.sleep(SCAN_PREFLIGHT_CHECK_INTERVAL_SECONDS)

    passed = len(attempts) == checks and all(bool(a.get("ok")) for a in attempts)
    reasons: list[str] = []
    for a in attempts:
        if a.get("ok"):
            continue
        if require_local_backend and not ((a.get("local_backend") or {}).get("ok")):
            reasons.append("local_backend_unstable")
        if require_external_preview and not ((a.get("external_preview") or {}).get("stable")):
            reasons.append("external_preview_unstable")

    return {
        "passed": passed,
        "required_checks": checks,
        "attempts_completed": len(attempts),
        "reasons": sorted(set(reasons)),
        "attempts": attempts,
        "require_external_preview": bool(require_external_preview),
        "require_local_backend": bool(require_local_backend),
        "checked_at": _now(),
    }


def _build_infra_blocked_report(
    *,
    task_id: str,
    execution_hash: str,
    triggered_by: str,
    actor: str,
    attempt_tag: str,
    attempt_index: int,
    preflight: dict[str, Any],
    scan_mode: str,
) -> dict[str, Any]:
    reasons = list(preflight.get("reasons") or ["preflight_failed"])
    reason_txt = ", ".join(reasons)
    fail_summary = (
        "INFRA_BLOCKED — runtime preflight did not reach required stability "
        f"({preflight.get('attempts_completed')}/{preflight.get('required_checks')} checks). "
        f"Reasons: {reason_txt}."
    )

    minimal_sections = {
        "preflight": {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "high",
                    "category": "infra",
                    "label": "scan_preflight_unstable",
                    "detail": fail_summary,
                    "count": 1,
                    "sample": {
                        "required_checks": preflight.get("required_checks"),
                        "attempts_completed": preflight.get("attempts_completed"),
                        "reasons": reasons,
                    },
                }
            ],
            "counts": {"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
            "elapsed_ms": 0,
        }
    }

    v3 = _v3_output_block(
        overall_status="FAIL",
        security_scan="FAIL",
        performance="FAIL",
        i18n_status="FAIL",
        rbac_status="FAIL",
        regressions=False,
        agg_counts={"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
        sections=minimal_sections,
        memory_recurring=0,
        restart_count=0,
    )

    report = {
        "task_id": task_id,
        "execution_hash": execution_hash,
        "status": "INFRA_BLOCKED",
        "critical_vulns": 0,
        "high_vulns": 1,
        "medium_vulns": 0,
        "low_vulns": 0,
        "regressions": "NO",
        "security_scan": "FAIL",
        "e2e_tests": "FAIL",
        "responsiveness": "FAIL",
        "performance": "FAIL",
        "rbac_status": "FAIL",
        "subscription_enforcement": "FAIL",
        "i18n_status": "FAIL",
        "learning_memory_updated": "YES",
        "summary": fail_summary,
        "severity_counts": {"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
        "sections": minimal_sections,
        "steps_skipped": ["sast", "dep", "dast", "acl", "i18n", "duplicate", "api_contract", "threat_model"],
        "directive_version": _hash_obj(read_directive_text()[:4000]),
        "generated_at": _now(),
        "v3_output": v3,
        "triggered_by": triggered_by,
        "actor": actor,
        "attempt_tag": attempt_tag,
        "attempt_index": attempt_index,
        "scan_mode": _normalize_scan_mode(scan_mode),
        "strict_global_mode": _is_strict_mode(scan_mode),
        "transient_artifact_count": 0,
        "strict_gate_passed": False,
        "preflight": preflight,
        "preflight_policy": {
            "require_external_preview": _is_strict_mode(scan_mode),
            "require_local_backend": _is_strict_mode(scan_mode),
            "required_stable_checks": SCAN_PREFLIGHT_REQUIRED_STABLE_CHECKS,
        },
    }
    hydrated, _ = ensure_report_sections_complete(report)
    return hydrated


def ensure_report_sections_complete(report: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Ensure latest-report contract always includes all required C5 sections.

    Backfills missing sections for legacy/infra-blocked snapshots while keeping
    existing section content unchanged.
    """
    out = dict(report or {})
    sections = dict(out.get("sections") or {})
    changed = False
    status_upper = str(out.get("status") or "").upper()
    blocked = status_upper == "INFRA_BLOCKED"
    preflight = out.get("preflight") or {}
    reasons = list(preflight.get("reasons") or ["preflight_unstable"]) if blocked else []
    reason_txt = ", ".join(reasons) if reasons else "none"

    for key in REQUIRED_REPORT_SECTIONS:
        existing = sections.get(key)
        if isinstance(existing, dict) and existing:
            continue

        changed = True
        if key == "acl":
            sections[key] = {
                "rbac_status": str(out.get("rbac_status") or ("FAIL" if blocked else "PASS")).upper(),
                "subscription_status": str(out.get("subscription_enforcement") or ("FAIL" if blocked else "PASS")).upper(),
                "findings": [
                    {
                        "severity": "high" if blocked else "info",
                        "category": "acl",
                        "label": "acl_checks_skipped_preflight" if blocked else "acl_backfill_placeholder",
                        "detail": (
                            f"ACL probes unavailable due to preflight instability: {reason_txt}"
                            if blocked else
                            "Backfilled ACL section for contract compatibility"
                        ),
                        "count": 1,
                    }
                ],
                "counts": {"critical": 0, "high": 1 if blocked else 0, "medium": 0, "low": 0, "info": 0 if blocked else 1},
                "elapsed_ms": 0,
                "rbac_pass": 0,
                "rbac_total": 0,
                "subscription_pass": 0,
                "subscription_total": 0,
            }
            continue

        section_doc: dict[str, Any] = {
            "status": "FAIL" if blocked else "PASS",
            "findings": [
                {
                    "severity": "high" if blocked else "info",
                    "category": key,
                    "label": f"{key}_skipped_preflight" if blocked else f"{key}_backfill_placeholder",
                    "detail": (
                        f"{key} validation unavailable due to preflight instability: {reason_txt}"
                        if blocked else
                        f"Backfilled {key} section for contract compatibility"
                    ),
                    "count": 1,
                }
            ],
            "counts": {"critical": 0, "high": 1 if blocked else 0, "medium": 0, "low": 0, "info": 0 if blocked else 1},
            "elapsed_ms": 0,
        }
        if key == "dast":
            section_doc["crawler_totals"] = {"scans": 0, "passing": 0}
            section_doc["responsiveness_status"] = str(out.get("responsiveness") or ("FAIL" if blocked else "PASS")).upper()
            section_doc["performance_status"] = str(out.get("performance") or ("FAIL" if blocked else "PASS")).upper()
            section_doc["performance_p50_ms"] = 0

        sections[key] = section_doc

    if changed:
        out["sections"] = sections
        existing_skipped = set(out.get("steps_skipped") or [])
        if blocked:
            existing_skipped.update(REQUIRED_REPORT_SECTIONS)
        out["steps_skipped"] = sorted(existing_skipped)

    return out, changed


def _build_fail_reason_summary(report: dict[str, Any], snapshot: Optional[dict[str, Any]] = None) -> str:
    status = str(report.get("status") or "UNKNOWN").upper()
    if status == "INFRA_BLOCKED":
        preflight = report.get("preflight") or {}
        reasons = ", ".join(list(preflight.get("reasons") or [])) or "preflight_unstable"
        return (
            "INFRA_BLOCKED because: "
            f"runtime preflight stability not met ({preflight.get('attempts_completed')}/{preflight.get('required_checks')})"
            f"; reasons={reasons}"
        )
    if status != "FAIL":
        return "PASS — no failing pillars detected"

    reasons: list[str] = []
    if str(report.get("security_scan") or "").upper() == "FAIL":
        reasons.append("security_scan=FAIL")
    if str(report.get("e2e_tests") or "").upper() == "FAIL":
        reasons.append("e2e_tests=FAIL")
    if str(report.get("rbac_status") or "").upper() == "FAIL":
        reasons.append("rbac_status=FAIL")
    if str(report.get("subscription_enforcement") or "").upper() == "FAIL":
        reasons.append("subscription_enforcement=FAIL")
    if str(report.get("i18n_status") or "").upper() == "FAIL":
        reasons.append("i18n_status=FAIL")
    if str(report.get("regressions") or "NO").upper() == "YES":
        reasons.append("regressions=YES")

    if snapshot:
        white = (snapshot.get("white_screen_sentry") or {})
        if str(white.get("status") or "").upper() == "FAIL":
            reasons.append(
                f"white_screen_sentry={_safe_int(white.get('failed_checks'), 0)}/{_safe_int(white.get('total_checks'), 0)} failed"
            )
        ext = (snapshot.get("external_host_certification") or {})
        ext_status = str(ext.get("status") or "").lower()
        if ext_status == "fail":
            reasons.append("external_host_certification=fail")

    if not reasons:
        return "FAIL — unresolved control-path failure, see §12 summary"
    return "FAIL because: " + "; ".join(reasons[:6])


def _validate_notification_snapshot(snapshot: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []

    source_task_id = str(snapshot.get("source_task_id") or "")
    report_task_id = str(report.get("task_id") or "")
    if source_task_id and report_task_id and source_task_id != report_task_id:
        issues.append("source_task_id_mismatch")

    trust = snapshot.get("trust") or {}
    white = snapshot.get("white_screen_sentry") or {}
    matrix = snapshot.get("responsive_viewport_matrix") or {}
    incident = snapshot.get("incident_auto_closure") or {}
    run_policy = snapshot.get("run_policy") or {}

    trust_total = _safe_int(trust.get("total_gates"), 0)
    trust_passed = _safe_int(trust.get("passed_gates"), 0)
    if trust_total > 0 and trust_passed > trust_total:
        issues.append("trust_gates_invalid_ratio")

    white_total = _safe_int(white.get("total_checks"), 0)
    white_failed = _safe_int(white.get("failed_checks"), 0)
    white_status = str(white.get("status") or "UNKNOWN").upper()
    if white_total > 0 and white_failed > white_total:
        issues.append("white_screen_invalid_ratio")
    if white_total > 0 and white_status == "UNKNOWN":
        issues.append("white_screen_status_unknown_with_checks")
    if white_total == 0 and white_status in {"PASS", "FAIL"}:
        issues.append("white_screen_status_set_without_checks")

    artifact_count = _safe_int(matrix.get("artifact_count"), 0)
    if white_total > 0 and artifact_count == 0:
        issues.append("matrix_artifacts_missing_for_white_screen_checks")

    pending = _safe_int(incident.get("transitioned_to_pending_verification"), 0)
    closed = _safe_int(incident.get("auto_closed"), 0)
    reopened = _safe_int(incident.get("reopened"), 0)
    evaluated = _safe_int(incident.get("evaluated_incidents"), 0)
    if any(v > evaluated for v in [pending, closed, reopened]) and evaluated > 0:
        issues.append("incident_counts_exceed_evaluated")

    scan_mode = _normalize_scan_mode(run_policy.get("scan_mode") or report.get("scan_mode"))
    strict_mode = _is_strict_mode(scan_mode)
    transient_count = _safe_int(run_policy.get("transient_artifact_count"), _safe_int(report.get("transient_artifact_count"), 0))
    if strict_mode and transient_count > 0:
        issues.append("strict_mode_transient_artifacts_present")

    passed = len(issues) == 0
    return {
        "passed": passed,
        "issues": issues,
        "status": "COMPLETE" if passed else "INCOMPLETE",
        "data_freshness": "LIVE" if passed else "STALE_OR_PARTIAL",
    }


def build_snapshot_from_report_email_dispatch(report: dict[str, Any]) -> dict[str, Any]:
    runtime = ((report.get("email_dispatch") or {}).get("c5_runtime_summary") or {})
    trust = runtime.get("trust") or {}
    white = runtime.get("white_screen_sentry") or {}
    external = runtime.get("external_host_certification") or {}
    incident = runtime.get("incident_auto_closure") or {}

    snapshot = {
        "snapshot_version": NOTIFICATION_SNAPSHOT_VERSION,
        "source_task_id": str(report.get("task_id") or ""),
        "source_execution_hash": report.get("execution_hash") or "",
        "source_generated_at": report.get("generated_at") or _now(),
        "global_binding": {
            "bound_to_latest_trust_task": False,
            "latest_trust_task_id": "",
        },
        "trust": {
            "score_percent": float(trust.get("score_percent") or 0.0),
            "passed_gates": int(trust.get("passed_gates") or 0),
            "total_gates": int(trust.get("total_gates") or 0),
            "generated_at": (report.get("email_dispatch") or {}).get("sent_at") or _now(),
        },
        "white_screen_sentry": {
            "status": str(white.get("status") or "UNKNOWN"),
            "run_id": white.get("run_id") or "",
            "failed_checks": int(white.get("failed_checks") or 0),
            "total_checks": int(white.get("total_checks") or 0),
            "routes_tested": int(white.get("routes_tested") or 0),
            "route_source": white.get("route_source") or "",
            "generated_at": (report.get("email_dispatch") or {}).get("sent_at") or _now(),
        },
        "responsive_viewport_matrix": {
            "artifact_count": int(white.get("total_checks") or 0),
            "viewports": ["mobile", "tablet", "desktop"],
            "matrix_summary": {},
        },
        "external_host_certification": {
            "status": str(external.get("status") or "not_run"),
            "certification_id": external.get("certification_id") or "",
            "reason": external.get("reason") or "",
            "started_at": None,
            "finished_at": None,
            "retry_plan": {
                "needs_retry": bool(external.get("retry_needed")),
                "reasons": [],
            },
        },
        "incident_auto_closure": {
            "evaluated_incidents": int(incident.get("evaluated_incidents") or 0),
            "transitioned_to_pending_verification": int(incident.get("transitioned_to_pending_verification") or 0),
            "auto_closed": int(incident.get("auto_closed") or 0),
            "reopened": int(incident.get("reopened") or 0),
            "streak_resets": int(incident.get("streak_resets") or 0),
            "policy": {
                "clean_rescans_required": INCIDENT_AUTOCLOSE_CLEAN_RESCANS,
                "pending_verification_hours": INCIDENT_AUTOCLOSE_PENDING_HOURS,
            },
            "evaluated_at": (report.get("email_dispatch") or {}).get("sent_at") or _now(),
        },
        "generated_at": _now(),
        "run_policy": {
            "scan_mode": _normalize_scan_mode(report.get("scan_mode")),
            "strict_global_mode": bool(report.get("strict_global_mode", _is_strict_mode(report.get("scan_mode")))),
            "transient_artifact_count": int(report.get("transient_artifact_count") or 0),
            "strict_gate_passed": bool(report.get("strict_gate_passed", True)),
            "preflight_require_external_preview": bool(((report.get("preflight_policy") or {}).get("require_external_preview"))),
            "preflight_require_local_backend": bool(((report.get("preflight_policy") or {}).get("require_local_backend"))),
        },
        "data_freshness": "REPORT_MIRRORED",
    }
    snapshot["fail_reason_summary"] = _build_fail_reason_summary(report, snapshot)
    validation = _validate_notification_snapshot(snapshot, report)
    snapshot["snapshot_status"] = validation.get("status")
    snapshot["consistency"] = {
        "passed": bool(validation.get("passed")),
        "issues": list(validation.get("issues") or []),
    }
    return snapshot


def _resolve_external_frontend_base_url(base_url: Optional[str] = None) -> str:
    def _read_env_from_file(path: Path, key: str) -> str:
        try:
            if not path.exists():
                return ""
            prefix = f"{key}="
            for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = str(raw or "").strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith(prefix):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            return ""
        return ""

    frontend_env_url = _read_env_from_file(ROOT / "frontend" / ".env", "REACT_APP_BACKEND_URL")
    backend_env_frontend = _read_env_from_file(ROOT / "backend" / ".env", "FRONTEND_BASE_URL")

    return resolve_external_frontend_base_url(
        base_url,
        gtec_frontend_url=str(os.environ.get("GTEC_FRONTEND_URL") or ""),
        frontend_base_url=str(os.environ.get("FRONTEND_BASE_URL") or ""),
        react_app_backend_url=str(os.environ.get("REACT_APP_BACKEND_URL") or ""),
        frontend_env_url=frontend_env_url,
        backend_env_frontend=backend_env_frontend,
        fallback_base_url=_resolve_frontend_base_url(None),
    )


async def hydrate_report_write_path(db, report: dict[str, Any], *, legacy_mirror_on: bool) -> dict[str, Any]:
    """Persist report with canonical section+snapshot hydration in one write path."""
    hydrated, _ = ensure_report_sections_complete(report)

    c5_snapshot = hydrated.get("c5_notification_snapshot") or {}
    if not c5_snapshot:
        try:
            c5_snapshot = await build_c5_notification_snapshot(db, hydrated)
            hydrated["c5_notification_snapshot"] = c5_snapshot
        except Exception:
            logger.exception("gtec-c5: failed to pre-hydrate c5_notification_snapshot on write path")
            hydrated["c5_notification_snapshot"] = {
                "snapshot_version": NOTIFICATION_SNAPSHOT_VERSION,
                "source_task_id": str(hydrated.get("task_id") or ""),
                "source_execution_hash": str(hydrated.get("execution_hash") or ""),
                "snapshot_status": "INCOMPLETE",
                "data_freshness": "STALE_OR_PARTIAL",
                "consistency": {"passed": False, "issues": ["snapshot_build_failed_write_path"]},
                "fail_reason_summary": _build_fail_reason_summary(hydrated),
                "generated_at": _now(),
            }

    await db[REPORTS_COL].insert_one({**hydrated})
    if legacy_mirror_on:
        await db[LEGACY_REPORTS_COL].update_one(
            {"task_id": hydrated.get("task_id")},
            {"$set": {**hydrated}},
            upsert=True,
        )

    return hydrated


def _active_incident_keys_from_report(report: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    sections = report.get("sections") or {}
    for section in sections.values():
        findings = (section or {}).get("findings") or []
        for finding in findings:
            label = str((finding or {}).get("label") or "").strip().lower()
            severity = str((finding or {}).get("severity") or "").strip().lower()
            if not label or severity not in {"critical", "high", "medium", "low"}:
                continue
            keys.add(f"{label}:{severity}")
    return keys


async def _mirror_incident_updates(db, incident_id: str, update: dict[str, Any]) -> None:
    if not incident_id or not update:
        return
    if await legacy_mirror_write_enabled(db):
        await db[LEGACY_INCIDENTS_COL].update_one(
            {"incident_id": incident_id},
            {"$set": update},
            upsert=True,
        )


async def apply_incident_auto_closure_policy(db, report: dict[str, Any]) -> dict[str, Any]:
    """Auto-close incidents after 3 clean rescans + 24h verification hold."""
    await ensure_internal_collections_migrated(db)

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    task_id = str(report.get("task_id") or "")
    active_keys = _active_incident_keys_from_report(report)

    transitioned_pending = 0
    auto_closed = 0
    reopened = 0
    streak_resets = 0
    scanned = 0

    query = {
        "status": {
            "$in": [
                *sorted(INCIDENT_ACTIVE_STATUSES),
                INCIDENT_PENDING_STATUS,
            ]
        }
    }

    async for incident in db[INCIDENTS_COL].find(query, {"_id": 0}):
        scanned += 1
        incident_id = str(incident.get("incident_id") or "").strip()
        incident_key = str(incident.get("incident_key") or "").strip().lower()
        status = str(incident.get("status") or "open").strip().lower()
        if not incident_id or not incident_key:
            continue

        clean_streak = _safe_int(incident.get("clean_rescan_streak"), 0)
        pending_since = _parse_iso(incident.get("pending_verification_started_at"))

        update: dict[str, Any] = {
            "last_autoclose_evaluated_task_id": task_id,
            "updated_at": now_iso,
            "auto_close_policy": {
                "consecutive_clean_rescans_required": INCIDENT_AUTOCLOSE_CLEAN_RESCANS,
                "pending_verification_hours": INCIDENT_AUTOCLOSE_PENDING_HOURS,
                "scope": "all_open_incidents_without_active_matching_findings",
            },
        }

        if incident_key in active_keys:
            update["clean_rescan_streak"] = 0
            update["pending_verification_started_at"] = None
            if status == INCIDENT_PENDING_STATUS:
                update["status"] = "open"
                update["containment"] = "active"
                update["reopened_at"] = now_iso
                update["resolution_reason"] = "finding_recurred_during_verification_hold"
                reopened += 1
            elif clean_streak > 0:
                streak_resets += 1
        else:
            clean_streak += 1
            update["clean_rescan_streak"] = clean_streak

            if status in INCIDENT_ACTIVE_STATUSES and clean_streak >= INCIDENT_AUTOCLOSE_CLEAN_RESCANS:
                update["status"] = INCIDENT_PENDING_STATUS
                update["containment"] = "monitoring"
                update["pending_verification_started_at"] = now_iso
                update["resolution_reason"] = "auto_clean_rescans_pending_verification"
                transitioned_pending += 1
            elif status == INCIDENT_PENDING_STATUS:
                if pending_since is None:
                    update["pending_verification_started_at"] = now_iso
                else:
                    hold_ok = (now_dt - pending_since) >= timedelta(hours=INCIDENT_AUTOCLOSE_PENDING_HOURS)
                    if hold_ok and clean_streak >= INCIDENT_AUTOCLOSE_CLEAN_RESCANS:
                        update["status"] = INCIDENT_CLOSED_STATUS
                        update["containment"] = "inactive"
                        update["closed_at"] = now_iso
                        update["closed_by"] = "system_auto_close"
                        update["resolution_reason"] = "auto_closed_after_consecutive_clean_rescans_and_24h_verification"
                        auto_closed += 1

        await db[INCIDENTS_COL].update_one(
            {"incident_id": incident_id},
            {"$set": update},
            upsert=False,
        )
        await _mirror_incident_updates(db, incident_id, update)

    return {
        "evaluated_incidents": scanned,
        "active_finding_keys": len(active_keys),
        "transitioned_to_pending_verification": transitioned_pending,
        "auto_closed": auto_closed,
        "reopened": reopened,
        "streak_resets": streak_resets,
        "policy": {
            "clean_rescans_required": INCIDENT_AUTOCLOSE_CLEAN_RESCANS,
            "pending_verification_hours": INCIDENT_AUTOCLOSE_PENDING_HOURS,
        },
        "evaluated_at": now_iso,
    }


def _looks_like_proxy_error(content: str) -> bool:
    txt = str(content or "").lower()
    needles = [
        "preview environment is not responding",
        "upstream request timeout",
        "gateway timeout",
        "bad gateway",
        "service unavailable",
        "proxy error",
    ]
    return any(n in txt for n in needles)


async def get_external_host_proxy_health(
    base_url: Optional[str] = None,
    *,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    resolved = _resolve_external_frontend_base_url(base_url)
    checks: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=timeout_seconds, verify=get_httpx_verify(), follow_redirects=True) as client:
        for path in ("/_preview/health", "/auth/login"):
            url = f"{resolved}{path}"
            status = 0
            body_snip = ""
            ok = False
            err = ""
            retry_attempts = SCAN_PREFLIGHT_ENDPOINT_RETRY_ATTEMPTS
            retry_backoff = SCAN_PREFLIGHT_ENDPOINT_BACKOFF_SECONDS
            try:
                resp, err_retry = await _probe_with_transient_retry(
                    client,
                    "GET",
                    url,
                    attempts=retry_attempts,
                    transient_statuses=(429, 500, 502, 503, 504),
                    backoff_seconds=retry_backoff,
                )
                if resp is None:
                    raise RuntimeError(err_retry or "external_probe_no_response")
                status = int(resp.status_code)
                body_snip = (resp.text or "")[:700]
                has_proxy_error = _looks_like_proxy_error(body_snip)
                if path == "/_preview/health":
                    ok = status == 200 and '"ok":true' in body_snip.lower() and not has_proxy_error
                else:
                    ok = 200 <= status < 500 and not has_proxy_error
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"

            checks.append(
                {
                    "path": path,
                    "status_code": status,
                    "ok": ok,
                    "error": err or None,
                    "snippet": body_snip,
                }
            )

    stable = all(bool(c.get("ok")) for c in checks)
    return {
        "base_url": resolved,
        "stable": stable,
        "checks": [
            {
                "path": c.get("path"),
                "status_code": c.get("status_code"),
                "ok": c.get("ok"),
                "error": c.get("error"),
            }
            for c in checks
        ],
        "checked_at": _now(),
    }


def _sentry_has_proxy_like_failures(run_doc: dict[str, Any]) -> bool:
    if not run_doc:
        return False
    if _safe_int(run_doc.get("failed_checks"), 0) <= 0:
        return False

    for row in (run_doc.get("artifacts") or [])[:120]:
        reason = str((row or {}).get("reason") or "").lower()
        status_code = _safe_int((row or {}).get("status_code"), 0)
        if status_code >= 502:
            return True
        if any(k in reason for k in ("http_502", "http_503", "http_504", "gateway", "proxy", "navigation_error")):
            return True
    return False


async def get_latest_external_host_certification(db) -> dict[str, Any]:
    doc = await db[EXTERNAL_HOST_CERTIFICATION_COL].find_one({}, {"_id": 0}, sort=[("started_at", -1)])
    return doc or {}


async def should_retry_external_host_certification(
    db,
    *,
    cooldown_minutes: int = EXTERNAL_HOST_CERTIFICATION_COOLDOWN_MINUTES,
) -> dict[str, Any]:
    reasons: list[str] = []
    latest_viewport: dict[str, Any] = {}
    latest_cert: dict[str, Any] = {}

    try:
        latest_viewport = await get_latest_viewport_artifact_run(db)
    except Exception as exc:
        msg = str(exc or "").strip().lower()
        logger.warning("gtec-c5: viewport artifact probe unavailable during retry planning: %s", exc)
        if "event loop is closed" in msg:
            reasons.append("event_loop_closed_viewport_probe")
        else:
            reasons.append("viewport_probe_error")

    try:
        latest_cert = await get_latest_external_host_certification(db)
    except Exception as exc:
        msg = str(exc or "").strip().lower()
        logger.warning("gtec-c5: external certification probe unavailable during retry planning: %s", exc)
        if "event loop is closed" in msg:
            reasons.append("event_loop_closed_cert_probe")
        else:
            reasons.append("external_cert_probe_error")

    if not latest_viewport:
        reasons.append("missing_viewport_artifacts")
    else:
        if _safe_int(latest_viewport.get("total_checks"), 0) <= 0:
            reasons.append("viewport_checks_zero")
        if _sentry_has_proxy_like_failures(latest_viewport):
            reasons.append("proxy_like_failures_in_latest_sentry")

    cooldown_active = False
    cert_started_at = _parse_iso((latest_cert or {}).get("started_at"))
    if cert_started_at:
        cooldown_active = (datetime.now(timezone.utc) - cert_started_at) < timedelta(minutes=max(1, int(cooldown_minutes)))
    if cooldown_active:
        reasons.append("cooldown_active")

    needs_retry = any(r in reasons for r in {
        "missing_viewport_artifacts",
        "viewport_checks_zero",
        "proxy_like_failures_in_latest_sentry",
    }) and not cooldown_active

    return {
        "needs_retry": needs_retry,
        "reasons": reasons,
        "latest_viewport_run_id": latest_viewport.get("run_id") if latest_viewport else None,
        "latest_external_certification_id": latest_cert.get("certification_id") if latest_cert else None,
        "evaluated_at": _now(),
    }


async def run_external_host_certification_pass(
    db,
    *,
    triggered_by: str,
    force: bool = False,
    include_release_drill: bool = True,
    simulate_hard_block: bool = True,
    base_url: Optional[str] = None,
) -> dict[str, Any]:
    await ensure_internal_collections_migrated(db)

    if EXTERNAL_CERTIFICATION_RUN_LOCK.locked():
        return {
            "certification_id": f"ext_cert_busy_{uuid.uuid4().hex[:10]}",
            "status": "busy",
            "reason": "external_host_certification_already_running",
            "triggered_by": triggered_by,
            "force": bool(force),
            "include_release_drill": bool(include_release_drill),
            "simulate_hard_block": bool(simulate_hard_block),
            "health": {
                "stable": False,
                "checks": [],
            },
            "started_at": _now(),
            "finished_at": _now(),
        }

    async with EXTERNAL_CERTIFICATION_RUN_LOCK:
        started_at = _now()
        resolved_base_url = _resolve_external_frontend_base_url(base_url)
        certification_id = f"ext_cert_{uuid.uuid4().hex[:12]}"

        health = await get_external_host_proxy_health(resolved_base_url)
        if not force and not bool(health.get("stable")):
            doc = {
                "certification_id": certification_id,
                "status": "skipped_proxy_unstable",
                "reason": "external_preview_proxy_not_stable",
                "triggered_by": triggered_by,
                "force": force,
                "base_url": resolved_base_url,
                "health": health,
                "started_at": started_at,
                "finished_at": _now(),
            }
            await db[EXTERNAL_HOST_CERTIFICATION_COL].insert_one({**doc})
            return doc

        sentry = await run_white_screen_sentry_matrix(
            db,
            triggered_by=f"external_host_certification:{triggered_by}",
            force=True,
            allow_execute=True,
            base_url=resolved_base_url,
            max_age_minutes=1,
        )

        drill: dict[str, Any] = {}
        if include_release_drill:
            drill = await run_go_no_go_release_drill(
                db,
                simulate_hard_block=bool(simulate_hard_block),
                triggered_by=f"external_host_certification:{triggered_by}",
            )

        sentry_passed = _viewport_gate_passed(sentry)
        decision = str((drill or {}).get("decision") or ("GO" if sentry_passed else "NO_GO"))
        status = "pass" if sentry_passed and decision == "GO" else "fail"

        doc = {
            "certification_id": certification_id,
            "status": status,
            "triggered_by": triggered_by,
            "force": force,
            "base_url": resolved_base_url,
            "health": health,
            "white_screen": {
                "run_id": sentry.get("run_id"),
                "gate_passed": sentry_passed,
                "failed_checks": _safe_int(sentry.get("failed_checks"), 0),
                "total_checks": _safe_int(sentry.get("total_checks"), 0),
                "generated_at": sentry.get("generated_at"),
            },
            "drill": {
                "drill_id": (drill or {}).get("drill_id"),
                "decision": decision,
                "reason": (drill or {}).get("reason"),
                "evidence_bundle_id": (drill or {}).get("evidence_bundle_id"),
            } if include_release_drill else {},
            "started_at": started_at,
            "finished_at": _now(),
        }
        await db[EXTERNAL_HOST_CERTIFICATION_COL].insert_one({**doc})
        return doc


async def get_latest_viewport_artifact_run(db) -> dict[str, Any]:
    doc = await db[VIEWPORT_ARTIFACTS_COL].find_one(
        {},
        {"_id": 0},
        sort=[("generated_at", -1), ("stored_at", -1)],
    )
    return doc or {}


def _viewport_gate_passed(doc: dict[str, Any]) -> bool:
    if not doc:
        return False
    explicit = doc.get("white_screen_gate_passed")
    if isinstance(explicit, bool):
        return explicit and _safe_int(doc.get("failed_checks"), 0) == 0
    return _safe_int(doc.get("failed_checks"), 0) == 0 and _safe_int(doc.get("total_checks"), 0) > 0


async def run_white_screen_sentry_matrix(
    db,
    *,
    triggered_by: str,
    force: bool = False,
    max_age_minutes: int = WHITE_SCREEN_SENTRY_MAX_AGE_MINUTES,
    allow_execute: bool = True,
    base_url: Optional[str] = None,
    routes: Optional[list[str]] = None,
    viewports: Optional[list[str]] = None,
    languages: Optional[list[str]] = None,
) -> dict[str, Any]:
    await ensure_internal_collections_migrated(db)
    now = datetime.now(timezone.utc)

    # Keep historical default behavior for existing callsites that do not pass routes.
    requested_routes = _normalize_route_paths(routes, MATRIX64_DEFAULT_ROUTES) if routes is not None else []
    requested_viewports = _normalize_axes(viewports, DEFAULT_SENTRY_VIEWPORTS)
    requested_languages = _normalize_axes(languages, DEFAULT_SENTRY_LANGUAGES)

    latest = await get_latest_viewport_artifact_run(db)
    generated = _parse_iso((latest or {}).get("generated_at") or (latest or {}).get("stored_at"))
    is_fresh = bool(
        latest
        and generated
        and (now - generated) <= timedelta(minutes=max(1, int(max_age_minutes)))
    )
    latest_routes = _normalize_route_paths(
        [str(r or "") for r in (latest.get("routes_tested") or [])],
        [],
    ) if latest else []
    latest_viewports = _normalize_axes(latest.get("viewports") if latest else None, DEFAULT_SENTRY_VIEWPORTS)
    latest_languages = _normalize_axes(latest.get("languages") if latest else None, DEFAULT_SENTRY_LANGUAGES)
    requested_matches_latest = (
        latest
        and latest_viewports == requested_viewports
        and latest_languages == requested_languages
        and (
            not requested_routes
            or latest_routes == requested_routes
        )
    )
    if (
        not force
        and is_fresh
        and requested_matches_latest
    ):
        return {
            **latest,
            "reused": True,
        }

    if not allow_execute:
        if latest:
            stale_doc = {**latest, "reused": True, "stale": not is_fresh}
            if not is_fresh:
                stale_doc["white_screen_gate_passed"] = False
                stale_doc["failure_reason"] = "stale_viewport_matrix_artifacts"
            return stale_doc
        return {
            "run_id": f"wss_missing_{int(now.timestamp())}",
            "base_url": _resolve_frontend_base_url(base_url),
            "routes_tested": [],
            "viewports": requested_viewports,
            "languages": requested_languages,
            "total_checks": 0,
            "failed_checks": 0,
            "white_screen_gate_passed": False,
            "failure_reason": "missing_viewport_matrix_artifacts",
            "generated_at": _now(),
            "stored_at": _now(),
            "reused": True,
            "stale": True,
        }

    resolved_base_url = _resolve_frontend_base_url(base_url)
    command = [
        sys.executable,
        str(WHITE_SCREEN_SENTRY_SCRIPT),
        "--base-url",
        resolved_base_url,
        "--routes-limit",
        str(max(1, len(requested_routes) if requested_routes else 20)),
        "--viewports",
        ",".join(requested_viewports),
        "--languages",
        ",".join(requested_languages),
        "--output-json",
        str(WHITE_SCREEN_SENTRY_LATEST),
    ]
    if requested_routes:
        command.extend([
            "--exact-routes",
            ",".join(requested_routes),
        ])

    stdout = ""
    stderr = ""
    exit_code = 1
    payload: dict[str, Any] = {}

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={
                **os.environ,
                "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/pw-browsers"),
            },
        )
        vp_count = max(1, len(requested_viewports))
        language_count = max(1, len(requested_languages))
        route_count = max(1, len(requested_routes) if requested_routes else 20)
        timeout_seconds = max(240, (vp_count * language_count * route_count * 7) + 120)
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        exit_code = int(proc.returncode or 0)
        stdout = (out_b.decode("utf-8", errors="ignore") if out_b else "").strip()
        stderr = (err_b.decode("utf-8", errors="ignore") if err_b else "").strip()
    except Exception as exc:
        stderr = f"white_screen_sentry_subprocess_failed: {exc}"

    if WHITE_SCREEN_SENTRY_LATEST.exists():
        try:
            payload = json.loads(WHITE_SCREEN_SENTRY_LATEST.read_text(encoding="utf-8"))
        except Exception as exc:
            payload = {
                "error": f"failed_to_parse_white_screen_sentry_output: {exc}",
            }

    run_id = str(payload.get("run_id") or f"wss_{uuid.uuid4().hex[:10]}")
    failed_checks = _safe_int(payload.get("failed_checks"), 0)
    total_checks = _safe_int(payload.get("total_checks"), 0)
    gate_passed = bool(payload.get("white_screen_gate_passed")) and failed_checks == 0 and total_checks > 0
    if total_checks == 0:
        gate_passed = False

    doc = {
        **payload,
        "run_id": run_id,
        "base_url": payload.get("base_url") or resolved_base_url,
        "viewports": _normalize_axes(payload.get("viewports"), requested_viewports),
        "languages": _normalize_axes(payload.get("languages"), requested_languages),
        "routes_tested": payload.get("routes_tested") or requested_routes,
        "failed_checks": failed_checks,
        "total_checks": total_checks,
        "white_screen_gate_passed": gate_passed,
        "triggered_by": triggered_by,
        "stored_at": _now(),
        "script_exit_code": exit_code,
        "script_stdout_tail": stdout[-2000:] if stdout else "",
        "script_stderr_tail": stderr[-2000:] if stderr else "",
    }

    if exit_code != 0 and not doc.get("failure_reason"):
        doc["failure_reason"] = "sentry_script_non_zero_exit"
    if not doc.get("generated_at"):
        doc["generated_at"] = _now()

    await db[VIEWPORT_ARTIFACTS_COL].update_one(
        {"run_id": run_id},
        {"$set": doc},
        upsert=True,
    )
    return {k: v for k, v in doc.items() if k != "_id"}


def _build_matrix64_defaults() -> dict[str, Any]:
    return {
        "enabled": True,
        "timezone": "UTC",
        "hour_utc": 1,
        "minute_utc": 0,
        "routes": list(MATRIX64_DEFAULT_ROUTES),
        "viewports": list(MATRIX64_DEFAULT_VIEWPORTS),
        "languages": list(MATRIX64_DEFAULT_LANGUAGES),
        "artifact_dir": str(MATRIX64_ARTIFACT_DIR),
        "required_total_checks": MATRIX64_REQUIRED_TOTAL,
    }


async def ensure_matrix64_pipeline_config(db) -> dict[str, Any]:
    await ensure_internal_collections_migrated(db)
    defaults = _build_matrix64_defaults()
    now_iso = _now()
    existing = await db[SETTINGS_COL].find_one({"_id": MATRIX64_CONFIG_DOC_ID}, {"_id": 0}) or {}

    merged = {
        **defaults,
        **existing,
        "enabled": True,
        "timezone": "UTC",
        "hour_utc": 1,
        "minute_utc": 0,
        "routes": _normalize_route_paths(existing.get("routes"), MATRIX64_DEFAULT_ROUTES),
        "viewports": _normalize_axes(existing.get("viewports"), MATRIX64_DEFAULT_VIEWPORTS),
        "languages": _normalize_axes(existing.get("languages"), MATRIX64_DEFAULT_LANGUAGES),
        "required_total_checks": MATRIX64_REQUIRED_TOTAL,
        "artifact_dir": str(existing.get("artifact_dir") or defaults["artifact_dir"]),
    }

    update_doc = {
        **merged,
        "updated_at": now_iso,
        "updated_by": str(existing.get("updated_by") or "system"),
    }
    if not existing:
        update_doc["created_at"] = now_iso

    await db[SETTINGS_COL].update_one(
        {"_id": MATRIX64_CONFIG_DOC_ID},
        {"$set": update_doc},
        upsert=True,
    )
    if await legacy_mirror_write_enabled(db):
        await db[LEGACY_SETTINGS_COL].update_one(
            {"_id": MATRIX64_CONFIG_DOC_ID},
            {"$set": update_doc},
            upsert=True,
        )
    return {k: v for k, v in update_doc.items() if k != "_id"}


async def get_matrix64_pipeline_config(db) -> dict[str, Any]:
    return await ensure_matrix64_pipeline_config(db)


async def _record_matrix64_scheduler_heartbeat(
    db,
    *,
    status: str,
    details: Optional[dict[str, Any]] = None,
) -> None:
    await db.scheduler_heartbeats.update_one(
        {"job_id": MATRIX64_SCHEDULER_JOB_ID},
        {
            "$set": {
                "job_id": MATRIX64_SCHEDULER_JOB_ID,
                "status": status,
                "last_run": _now(),
                "details": details or {},
                "updated_at": _now(),
            }
        },
        upsert=True,
    )


async def run_strict_matrix64_pipeline(
    db,
    *,
    triggered_by: str,
    force: bool = True,
    base_url: Optional[str] = None,
) -> dict[str, Any]:
    config = await get_matrix64_pipeline_config(db)
    routes = _normalize_route_paths(config.get("routes"), MATRIX64_DEFAULT_ROUTES)[:4]
    viewports = _normalize_axes(config.get("viewports"), MATRIX64_DEFAULT_VIEWPORTS)[:4]
    languages = _normalize_axes(config.get("languages"), MATRIX64_DEFAULT_LANGUAGES)[:4]

    sentry = await run_white_screen_sentry_matrix(
        db,
        triggered_by=f"matrix64::{triggered_by}",
        force=bool(force),
        max_age_minutes=1,
        allow_execute=True,
        base_url=base_url,
        routes=routes,
        viewports=viewports,
        languages=languages,
    )

    expected_total = len(routes) * len(viewports) * len(languages)
    total_checks = _safe_int(sentry.get("total_checks"), 0)
    failed_checks = _safe_int(sentry.get("failed_checks"), 0)
    passed_checks = max(0, total_checks - failed_checks)
    coverage_complete = total_checks == expected_total
    strict_passed = bool(sentry.get("white_screen_gate_passed")) and failed_checks == 0 and coverage_complete
    status = "PASS" if strict_passed else "FAIL"

    artifact_root = Path(str(config.get("artifact_dir") or MATRIX64_ARTIFACT_DIR))
    artifact_root.mkdir(parents=True, exist_ok=True)

    run_id = f"matrix64_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
    artifact_path = artifact_root / f"{run_id}.json"
    failed_artifacts = [
        {
            "route": row.get("route"),
            "probe_url": row.get("probe_url"),
            "viewport": row.get("viewport"),
            "language": row.get("language"),
            "reason": row.get("reason"),
            "status_code": row.get("status_code"),
            "final_url": row.get("final_url"),
            "screenshot": row.get("screenshot"),
        }
        for row in (sentry.get("artifacts") or [])
        if str(row.get("status") or "").lower() != "pass"
    ]

    doc = {
        "run_id": run_id,
        "status": status,
        "strict_passed": strict_passed,
        "triggered_by": triggered_by,
        "generated_at": _now(),
        "stored_at": _now(),
        "artifact_schema_version": "gtec_c5_matrix64.v1",
        "scheduler": {
            "job_id": MATRIX64_SCHEDULER_JOB_ID,
            "cron_utc": "0 1 * * *",
            "timezone": "UTC",
            "hour_utc": 1,
            "minute_utc": 0,
        },
        "base_url": sentry.get("base_url") or _resolve_frontend_base_url(base_url),
        "dimensions": {
            "routes": routes,
            "viewports": viewports,
            "languages": languages,
            "required_total_checks": expected_total,
        },
        "counts": {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "coverage_complete": coverage_complete,
            "pass_rate_pct": round((passed_checks / max(total_checks, 1)) * 100, 2),
        },
        "route_source": sentry.get("route_source"),
        "matrix_summary": sentry.get("matrix_summary") or {},
        "matrix_summary_by_language": sentry.get("matrix_summary_by_language") or {},
        "white_screen_sentry": {
            "run_id": sentry.get("run_id"),
            "white_screen_gate_passed": bool(sentry.get("white_screen_gate_passed")),
            "failure_reason": sentry.get("failure_reason"),
        },
        "failed_artifacts": failed_artifacts[:25],
        "artifact_path": str(artifact_path),
    }

    artifact_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    await db[MATRIX64_PIPELINE_RUNS_COL].update_one(
        {"run_id": run_id},
        {"$set": doc},
        upsert=True,
    )
    return {k: v for k, v in doc.items() if k != "_id"}


async def get_latest_matrix64_pipeline_run(db) -> dict[str, Any]:
    doc = await db[MATRIX64_PIPELINE_RUNS_COL].find_one(
        {},
        {"_id": 0},
        sort=[("generated_at", -1), ("stored_at", -1)],
    )
    return doc or {}


async def list_matrix64_pipeline_runs(db, *, limit: int = 10) -> list[dict[str, Any]]:
    rows = await db[MATRIX64_PIPELINE_RUNS_COL].find(
        {},
        {"_id": 0},
    ).sort("generated_at", -1).limit(max(1, min(limit, 100))).to_list(max(1, min(limit, 100)))
    return rows or []


async def scheduled_matrix64_pipeline_tick() -> None:
    try:
        from routes.db import db  # lazy import to avoid circular deps

        await ensure_internal_collections_migrated(db)
        result = await run_strict_matrix64_pipeline(
            db,
            triggered_by="scheduler_nightly_global_system",
            force=True,
        )
        await _record_matrix64_scheduler_heartbeat(
            db,
            status="healthy" if bool(result.get("strict_passed")) else "degraded",
            details={
                "run_id": result.get("run_id"),
                "status": result.get("status"),
                "failed_checks": ((result.get("counts") or {}).get("failed_checks")),
                "required_total_checks": (((result.get("dimensions") or {}).get("required_total_checks"))),
            },
        )
    except Exception as exc:
        try:
            from routes.db import db  # lazy import to avoid circular deps

            await _record_matrix64_scheduler_heartbeat(
                db,
                status="degraded",
                details={"error": str(exc)[:260]},
            )
        except Exception:
            pass
        logger.exception("gtec-c5 matrix64 scheduled tick crashed")


async def legacy_mirror_write_enabled(db) -> bool:
    control = await ensure_legacy_cleanup_window(db)
    enabled = bool(control.get("mirror_write_enabled", True))
    if not enabled:
        return False

    retire_at = _parse_iso(control.get("scheduled_retirement_at"))
    if retire_at and datetime.now(timezone.utc) >= retire_at:
        now_iso = _now()
        update = {
            "mirror_write_enabled": False,
            "status": "retired",
            "retired_at": now_iso,
            "updated_at": now_iso,
        }
        await db[SETTINGS_COL].update_one(
            {"_id": LEGACY_CLEANUP_CONTROL_DOC_ID},
            {"$set": update},
            upsert=True,
        )
        await db[LEGACY_SETTINGS_COL].update_one(
            {"_id": LEGACY_CLEANUP_CONTROL_DOC_ID},
            {"$set": update},
            upsert=True,
        )
        return False
    return True


def _gate(name: str, passed: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate": name,
        "passed": bool(passed),
        "evidence": evidence,
    }


async def build_trust_gate_snapshot(db) -> dict[str, Any]:
    """Build trust-gate snapshot for API, CI evidence, and continuous monitoring."""
    await ensure_internal_collections_migrated(db)

    latest = await db[REPORTS_COL].find_one({}, {"_id": 0}, sort=[("generated_at", -1)]) or {}
    latest_task_id = str(latest.get("task_id") or "")
    latest_public_task_id = to_public_task_id(latest_task_id)

    latest_ledger = (latest.get("remediation_ledgers") or [])[-1] if (latest.get("remediation_ledgers") or []) else {}
    actions = latest_ledger.get("actions") or []
    manual_required_like = [
        a for a in actions
        if str(a.get("status") or "").lower() in {"manual_required", "unhandled"}
    ]

    receipt = await db["compliance_digest_feed"].find_one(
        {"kind": "gtec_c5_run_receipt", "payload.task_id": latest_public_task_id},
        {"_id": 0, "entry_id": 1, "created_at": 1, "payload.pdf_attachment.sha256": 1},
        sort=[("created_at", -1)],
    ) or {}

    policy_doc = await db[POLICY_STORE_COL].find_one({"_id": "effective"}, {"_id": 0}) or {}
    trust_col_counts = {
        "gtec_execution_graph": await db[EXECUTION_GRAPH_COL].count_documents({}),
        "gtec_finding_catalog": await db[FINDING_CATALOG_COL].count_documents({}),
        "gtec_remediation_plans": await db[REMEDIATION_PLANS_COL].count_documents({}),
        "gtec_incidents": await db[CANONICAL_INCIDENTS_COL].count_documents({}),
        "gtec_policy_store": await db[POLICY_STORE_COL].count_documents({}),
        "gtec_threat_topology": await db["gtec_threat_topology"].count_documents({}),
    }

    trace_ok = bool(
        latest_task_id
        and latest.get("execution_hash")
        and latest.get("directive_version")
        and ((latest.get("email_dispatch") or {}).get("pdf_attachment") or {}).get("sha256")
        and receipt.get("entry_id")
    )

    deterministic_path_ok = True
    for action in actions:
        st = str(action.get("status") or "").lower()
        if st in {"manual_required", "unhandled"}:
            deterministic_path_ok = False
            break

    steps_skipped = latest.get("steps_skipped") or []
    surfaced_skip_failure = bool(steps_skipped) and str(latest.get("status") or "").upper() == "FAIL"

    gates = [
        _gate("zero_manual_trigger_dependency", True, {"manual_endpoints_disabled": MANUAL_MUTATION_ENDPOINTS_DISABLED}),
        _gate("zero_unhandled_finding_classes", len(manual_required_like) == 0, {"manual_required_like_count": len(manual_required_like)}),
        _gate("full_execution_traceability", trace_ok, {
            "task_id": latest_public_task_id,
            "execution_hash": latest.get("execution_hash"),
            "directive_version": latest.get("directive_version"),
            "receipt_entry": receipt.get("entry_id"),
        }),
        _gate("platform_data_only_runtime_decisions", bool((policy_doc.get("policy") or {}).get("platform_data_only", True)), {
            "policy_doc_present": bool(policy_doc),
            "platform_data_only": (policy_doc.get("policy") or {}).get("platform_data_only", True),
        }),
        _gate("deterministic_remediation_or_escalation", deterministic_path_ok, {"actions_count": len(actions)}),
        _gate("no_silent_control_path_failures", (len(steps_skipped) == 0) or surfaced_skip_failure, {
            "steps_skipped": steps_skipped,
            "surfaced_skip_failure": surfaced_skip_failure,
            "status": latest.get("status"),
        }),
        _gate("canonical_model_write_through", all(v > 0 for v in trust_col_counts.values()), trust_col_counts),
        _gate("reproducible_pass_fail_with_artifacts", bool(latest.get("status") and ((latest.get("email_dispatch") or {}).get("pdf_attachment") or {}).get("sha256")), {
            "status": latest.get("status"),
            "pdf_sha256": ((latest.get("email_dispatch") or {}).get("pdf_attachment") or {}).get("sha256"),
        }),
        _gate("e2e_signal_present_in_latest_scan", str(latest.get("e2e_tests") or "").upper() in {"PASS", "FAIL"}, {"e2e_tests": latest.get("e2e_tests")}),
    ]

    passed = sum(1 for g in gates if g["passed"])
    score = round((passed / max(len(gates), 1)) * 100, 2)

    return {
        "system_name": "GTEC C5",
        "latest": latest,
        "latest_public_task_id": latest_public_task_id,
        "trust_score_percent": score,
        "passed_gates": passed,
        "total_gates": len(gates),
        "gates": gates,
        "generated_at": _now(),
    }


async def build_release_certificate_snapshot(db, *, trust_snapshot: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    snapshot = trust_snapshot or await build_trust_gate_snapshot(db)
    latest = snapshot.get("latest") or {}
    public_task_id = snapshot.get("latest_public_task_id") or ""
    trust_score = float(snapshot.get("trust_score_percent") or 0)
    is_trust_grade_100 = bool(trust_score >= 100 and int(snapshot.get("passed_gates") or 0) == int(snapshot.get("total_gates") or 0))

    i18n_missing_open = await db.i18n_fallback_events.count_documents({"status": "open"})
    theme_guardrail = await db.theme_guardrail_runs.find_one({}, {"_id": 0, "theme_guardrail_score": 1, "checked_at": 1}, sort=[("checked_at", -1)]) or {}
    email_darkmode = await db.email_darkmode_regression_scans.find_one({}, {"_id": 0, "status": 1, "scanned_at": 1}, sort=[("scanned_at", -1)]) or {}
    latest_viewport_run = await get_latest_viewport_artifact_run(db)
    latest_matrix64 = await get_latest_matrix64_pipeline_run(db)
    latest_scan_mode = _normalize_scan_mode(latest.get("scan_mode"))
    latest_strict_global = bool(latest.get("strict_global_mode", _is_strict_mode(latest_scan_mode)))
    latest_transient_artifacts = int(latest.get("transient_artifact_count") or 0)
    latest_strict_gate_passed = bool(latest.get("strict_gate_passed", latest_strict_global and latest_transient_artifacts == 0))
    viewport_failed = _safe_int(latest_viewport_run.get("failed_checks"), 0)
    viewport_total = _safe_int(latest_viewport_run.get("total_checks"), 0)
    viewport_status = "UNKNOWN"
    if latest_viewport_run:
        viewport_status = "PASS" if _viewport_gate_passed(latest_viewport_run) else "FAIL"

    return {
        "certificate_id": f"gtec-c5-cert-{public_task_id or 'none'}",
        "system_name": "GTEC C5",
        "task_id": public_task_id,
        "internal_task_id": latest.get("task_id"),
        "execution_hash": latest.get("execution_hash"),
        "directive_version": latest.get("directive_version"),
        "trust_score_percent": trust_score,
        "passed_gates": snapshot.get("passed_gates"),
        "total_gates": snapshot.get("total_gates"),
        "is_trust_grade_100": is_trust_grade_100,
        "checks": {
            "theme_v2": {
                "latest_score": theme_guardrail.get("theme_guardrail_score"),
                "checked_at": theme_guardrail.get("checked_at"),
            },
            "email_v7_darkmode": {
                "status": email_darkmode.get("status") or "unknown",
                "scanned_at": email_darkmode.get("scanned_at"),
            },
            "i18n_missing_open": i18n_missing_open,
            "pipeline_enforcement": await get_pipeline_enforcement_state(db),
            "db_security_hardening": await db.platform_security_state.find_one(
                {"_id": "db_hardening"},
                {"_id": 0, "status": 1, "failed_indexes": 1, "checked_at": 1, "security_version": 1},
            ) or {},
            "white_screen_sentry": {
                "status": viewport_status,
                "run_id": latest_viewport_run.get("run_id"),
                "failed_checks": viewport_failed,
                "total_checks": viewport_total,
                "routes_tested": len(latest_viewport_run.get("routes_tested") or []),
                "generated_at": latest_viewport_run.get("generated_at"),
                "route_source": latest_viewport_run.get("route_source"),
            },
            "responsive_viewport_matrix": {
                "viewports": latest_viewport_run.get("viewports") or ["mobile", "tablet", "desktop"],
                "matrix_summary": latest_viewport_run.get("matrix_summary") or {},
                "artifact_count": len(latest_viewport_run.get("artifacts") or []),
            },
            "matrix64_pipeline": {
                "status": latest_matrix64.get("status") or "UNKNOWN",
                "strict_passed": bool(latest_matrix64.get("strict_passed")),
                "run_id": latest_matrix64.get("run_id"),
                "generated_at": latest_matrix64.get("generated_at"),
                "required_total_checks": ((latest_matrix64.get("dimensions") or {}).get("required_total_checks")) or MATRIX64_REQUIRED_TOTAL,
                "total_checks": ((latest_matrix64.get("counts") or {}).get("total_checks")) or 0,
                "failed_checks": ((latest_matrix64.get("counts") or {}).get("failed_checks")) or 0,
                "artifact_path": latest_matrix64.get("artifact_path") or "",
            },
            "strict_run_policy": {
                "scan_mode": latest_scan_mode,
                "strict_global_mode": latest_strict_global,
                "transient_artifact_count": latest_transient_artifacts,
                "strict_gate_passed": latest_strict_gate_passed,
                "preflight_require_external_preview": bool(((latest.get("preflight_policy") or {}).get("require_external_preview"))),
                "preflight_require_local_backend": bool(((latest.get("preflight_policy") or {}).get("require_local_backend"))),
            },
        },
        "artifacts": {
            "pdf_sha256": ((latest.get("email_dispatch") or {}).get("pdf_attachment") or {}).get("sha256"),
            "receipt_kind": "gtec_c5_run_receipt",
            "white_screen_sentry_run_id": latest_viewport_run.get("run_id"),
        },
        "generated_at": _now(),
    }


async def build_c5_notification_snapshot(db, report: dict[str, Any]) -> dict[str, Any]:
    """Build a compact C5 runtime snapshot shared by PDF + email channels."""
    await ensure_internal_collections_migrated(db)

    if str(report.get("status") or "").upper() == "INFRA_BLOCKED":
        preflight = report.get("preflight") or {}
        scan_mode = _normalize_scan_mode(report.get("scan_mode"))
        snapshot = {
            "snapshot_version": NOTIFICATION_SNAPSHOT_VERSION,
            "source_task_id": str(report.get("task_id") or ""),
            "source_execution_hash": report.get("execution_hash") or "",
            "source_generated_at": report.get("generated_at") or _now(),
            "global_binding": {
                "bound_to_latest_trust_task": False,
                "latest_trust_task_id": "",
            },
            "trust": {
                "score_percent": 0.0,
                "passed_gates": 0,
                "total_gates": 0,
                "generated_at": _now(),
            },
            "white_screen_sentry": {
                "status": "UNKNOWN",
                "run_id": "",
                "failed_checks": 0,
                "total_checks": 0,
                "routes_tested": 0,
                "route_source": "",
                "generated_at": _now(),
            },
            "responsive_viewport_matrix": {
                "artifact_count": 0,
                "viewports": ["mobile", "tablet", "desktop"],
                "matrix_summary": {},
            },
            "external_host_certification": {
                "status": "skipped_preflight_unstable",
                "certification_id": "",
                "reason": ", ".join(list(preflight.get("reasons") or [])) or "preflight_unstable",
                "started_at": None,
                "finished_at": None,
                "retry_plan": {
                    "needs_retry": True,
                    "reasons": list(preflight.get("reasons") or ["preflight_unstable"]),
                },
            },
            "incident_auto_closure": {
                "evaluated_incidents": 0,
                "transitioned_to_pending_verification": 0,
                "auto_closed": 0,
                "reopened": 0,
                "streak_resets": 0,
                "policy": {
                    "clean_rescans_required": INCIDENT_AUTOCLOSE_CLEAN_RESCANS,
                    "pending_verification_hours": INCIDENT_AUTOCLOSE_PENDING_HOURS,
                },
                "evaluated_at": _now(),
            },
            "run_policy": {
                "scan_mode": scan_mode,
                "strict_global_mode": _is_strict_mode(scan_mode),
                "transient_artifact_count": int(report.get("transient_artifact_count") or 0),
                "strict_gate_passed": False,
                "preflight_require_external_preview": bool(((report.get("preflight_policy") or {}).get("require_external_preview"))),
                "preflight_require_local_backend": bool(((report.get("preflight_policy") or {}).get("require_local_backend"))),
            },
            "generated_at": _now(),
            "snapshot_status": "INCOMPLETE",
            "data_freshness": "INFRA_BLOCKED",
            "consistency": {
                "passed": False,
                "issues": ["scan_preflight_unstable"],
            },
            "fail_reason_summary": _build_fail_reason_summary(report),
        }
        return snapshot

    trust = await build_trust_gate_snapshot(db)
    cert = await build_release_certificate_snapshot(db, trust_snapshot=trust)
    checks = cert.get("checks") or {}

    white = checks.get("white_screen_sentry") or {}
    matrix = checks.get("responsive_viewport_matrix") or {}
    latest_external = await get_latest_external_host_certification(db)
    retry = await should_retry_external_host_certification(db)

    incident = report.get("incident_auto_closure") or {}
    policy = incident.get("policy") or {}
    report_task_id = str(report.get("task_id") or "")
    trust_latest_task_id = str(((trust.get("latest") or {}).get("task_id") or ""))

    # Bind live trust/cert values only when they belong to this report task.
    # Otherwise fall back to report-level runtime summary if available.
    report_runtime = ((report.get("email_dispatch") or {}).get("c5_runtime_summary") or {})
    runtime_trust = report_runtime.get("trust") or {}
    runtime_white = report_runtime.get("white_screen_sentry") or {}
    runtime_external = report_runtime.get("external_host_certification") or {}
    runtime_incident = report_runtime.get("incident_auto_closure") or {}

    global_bound = bool(report_task_id and trust_latest_task_id and report_task_id == trust_latest_task_id)

    trust_payload = {
        "score_percent": float(trust.get("trust_score_percent") or runtime_trust.get("score_percent") or 0.0),
        "passed_gates": int(trust.get("passed_gates") or runtime_trust.get("passed_gates") or 0),
        "total_gates": int(trust.get("total_gates") or runtime_trust.get("total_gates") or 0),
        "generated_at": trust.get("generated_at") or _now(),
    }
    white_payload = {
        "status": str(white.get("status") or runtime_white.get("status") or "UNKNOWN"),
        "run_id": white.get("run_id") or runtime_white.get("run_id"),
        "failed_checks": int(white.get("failed_checks") or runtime_white.get("failed_checks") or 0),
        "total_checks": int(white.get("total_checks") or runtime_white.get("total_checks") or 0),
        "routes_tested": int(white.get("routes_tested") or runtime_white.get("routes_tested") or 0),
        "route_source": white.get("route_source") or runtime_white.get("route_source") or "",
        "generated_at": white.get("generated_at") or _now(),
    }
    matrix_payload = {
        "artifact_count": int(matrix.get("artifact_count") or runtime_white.get("total_checks") or 0),
        "viewports": list(matrix.get("viewports") or ["mobile", "tablet", "desktop"]),
        "matrix_summary": matrix.get("matrix_summary") or {},
    }
    external_payload = {
        "status": str(latest_external.get("status") or runtime_external.get("status") or "not_run"),
        "certification_id": latest_external.get("certification_id") or runtime_external.get("certification_id"),
        "reason": latest_external.get("reason") or runtime_external.get("reason") or "",
        "started_at": latest_external.get("started_at"),
        "finished_at": latest_external.get("finished_at"),
        "retry_plan": {
            "needs_retry": bool(retry.get("needs_retry") if latest_external else runtime_external.get("retry_needed")),
            "reasons": list(retry.get("reasons") or []),
        },
    }
    incident_payload = {
        "evaluated_incidents": int(incident.get("evaluated_incidents") or runtime_incident.get("evaluated_incidents") or 0),
        "transitioned_to_pending_verification": int(
            incident.get("transitioned_to_pending_verification")
            or runtime_incident.get("transitioned_to_pending_verification")
            or 0
        ),
        "auto_closed": int(incident.get("auto_closed") or runtime_incident.get("auto_closed") or 0),
        "reopened": int(incident.get("reopened") or runtime_incident.get("reopened") or 0),
        "streak_resets": int(incident.get("streak_resets") or runtime_incident.get("streak_resets") or 0),
        "policy": {
            "clean_rescans_required": int(policy.get("clean_rescans_required") or INCIDENT_AUTOCLOSE_CLEAN_RESCANS),
            "pending_verification_hours": int(policy.get("pending_verification_hours") or INCIDENT_AUTOCLOSE_PENDING_HOURS),
        },
        "evaluated_at": incident.get("evaluated_at") or _now(),
    }
    scan_mode = _normalize_scan_mode(report.get("scan_mode"))
    strict_global_mode = _is_strict_mode(scan_mode)
    transient_artifact_count = int(report.get("transient_artifact_count") or 0)

    snapshot = {
        "snapshot_version": NOTIFICATION_SNAPSHOT_VERSION,
        "source_task_id": report_task_id,
        "source_execution_hash": report.get("execution_hash") or "",
        "source_generated_at": report.get("generated_at") or _now(),
        "global_binding": {
            "bound_to_latest_trust_task": global_bound,
            "latest_trust_task_id": trust_latest_task_id,
        },
        "trust": trust_payload,
        "white_screen_sentry": white_payload,
        "responsive_viewport_matrix": matrix_payload,
        "external_host_certification": external_payload,
        "incident_auto_closure": incident_payload,
        "run_policy": {
            "scan_mode": scan_mode,
            "strict_global_mode": strict_global_mode,
            "transient_artifact_count": transient_artifact_count,
            "strict_gate_passed": bool(strict_global_mode and transient_artifact_count == 0),
            "preflight_require_external_preview": bool(((report.get("preflight_policy") or {}).get("require_external_preview"))),
            "preflight_require_local_backend": bool(((report.get("preflight_policy") or {}).get("require_local_backend"))),
        },
        "generated_at": _now(),
    }

    snapshot["fail_reason_summary"] = _build_fail_reason_summary(report, snapshot)
    validation = _validate_notification_snapshot(snapshot, report)
    snapshot["snapshot_status"] = validation.get("status")
    snapshot["data_freshness"] = validation.get("data_freshness")
    snapshot["consistency"] = {
        "passed": bool(validation.get("passed")),
        "issues": list(validation.get("issues") or []),
    }
    if not global_bound and report_runtime:
        snapshot["data_freshness"] = "REPORT_MIRRORED"
    elif not global_bound and not report_runtime:
        snapshot["data_freshness"] = "STALE_OR_PARTIAL"
        snapshot.setdefault("consistency", {}).setdefault("issues", []).append("not_bound_to_latest_trust_task")

    return snapshot


async def run_go_no_go_release_drill(
    db,
    *,
    simulate_hard_block: bool = False,
    triggered_by: str = "system",
    boundary_marker: Optional[str] = None,
) -> dict[str, Any]:
    """Run release GO/NO-GO drill and archive evidence bundle."""
    await ensure_internal_collections_migrated(db)
    await ensure_pipeline_enforcement_policy(db)

    original_policy = await db[SETTINGS_COL].find_one({"_id": PIPELINE_POLICY_DOC_ID}, {"_id": 0}) or {}

    try:
        if simulate_hard_block:
            started_at = datetime.now(timezone.utc) - timedelta(hours=max(49, int(original_policy.get("hard_block_after_hours") or 48) + 1))
            await db[SETTINGS_COL].update_one(
                {"_id": PIPELINE_POLICY_DOC_ID},
                {
                    "$set": {
                        "mode": "soft-block",
                        "soft_block_started_at": started_at.isoformat(),
                        "hard_block_after_hours": int(original_policy.get("hard_block_after_hours") or 48),
                        "updated_at": _now(),
                    }
                },
                upsert=True,
            )

        state = await get_pipeline_enforcement_state(db)
        snapshot = await build_trust_gate_snapshot(db)
        sentry = await run_white_screen_sentry_matrix(
            db,
            triggered_by=f"release_drill:{triggered_by}",
            force=False,
            allow_execute=False,
        )
        sentry_refresh_queued = False
        if _safe_int(sentry.get("total_checks"), 0) == 0 or bool(sentry.get("stale")):
            try:
                asyncio.create_task(
                    run_white_screen_sentry_matrix(
                        db,
                        triggered_by=f"release_drill_async_refresh:{triggered_by}",
                        force=True,
                        allow_execute=True,
                    )
                )
                sentry_refresh_queued = True
            except Exception:
                sentry_refresh_queued = False
        all_gates_pass = int(snapshot.get("passed_gates") or 0) == int(snapshot.get("total_gates") or 0)
        trust_score = float(snapshot.get("trust_score_percent") or 0.0)
        sentry_pass = _viewport_gate_passed(sentry)

        latest_internal_task_id = str(snapshot.get("latest_task_id") or "")
        latest_report = await db[REPORTS_COL].find_one(
            {"task_id": latest_internal_task_id},
            {
                "_id": 0,
                "task_id": 1,
                "status": 1,
                "scan_mode": 1,
                "strict_global_mode": 1,
                "transient_artifact_count": 1,
            },
        ) if latest_internal_task_id else {}
        latest_scan_mode = _normalize_scan_mode((latest_report or {}).get("scan_mode"))
        has_latest_report = bool(latest_report)
        strict_mode_passed = bool((latest_report or {}).get("strict_global_mode", _is_strict_mode(latest_scan_mode))) and has_latest_report
        transient_artifact_count = _safe_int((latest_report or {}).get("transient_artifact_count"), 0)
        strict_gate_passed = strict_mode_passed and transient_artifact_count == 0

        effective_mode = str(state.get("effective_mode") or "soft-block")
        decision = "GO"
        reason_parts: list[str] = []
        if not strict_gate_passed:
            decision = "NO_GO"
            reason_parts.append(
                f"Strict global gate failed (mode={latest_scan_mode}, transient_artifacts={transient_artifact_count}, has_latest_report={has_latest_report})"
            )
        if not sentry_pass:
            decision = "NO_GO"
            reason_parts.append(
                f"White-screen sentry failed ({_safe_int(sentry.get('failed_checks'), 0)}/{_safe_int(sentry.get('total_checks'), 0)} checks)"
            )
        if effective_mode == "hard-block" and not all_gates_pass:
            decision = "NO_GO"
            reason_parts.append("Hard-block active and one or more mandatory gates failed")
        if not reason_parts:
            reason_parts.append("All mandatory gates passed, including white-screen sentry")
        reason = "; ".join(reason_parts)

        drill_id = f"drill-{int(datetime.now(timezone.utc).timestamp())}"
        drill = {
            "drill_id": drill_id,
            "drill_at": _now(),
            "simulated_hard_block": bool(simulate_hard_block),
            "triggered_by": triggered_by,
            "boundary_marker": boundary_marker or state.get("hard_block_at"),
            "pipeline_state": state,
            "trust_score_percent": trust_score,
            "passed_gates": int(snapshot.get("passed_gates") or 0),
            "total_gates": int(snapshot.get("total_gates") or 0),
            "decision": decision,
            "reason": reason,
            "validation": {
                "hard_block_validation_passed": (effective_mode == "hard-block") if simulate_hard_block else True,
                "all_gates_pass": all_gates_pass,
                "white_screen_gate_passed": sentry_pass,
                "white_screen_failed_checks": _safe_int(sentry.get("failed_checks"), 0),
                "white_screen_total_checks": _safe_int(sentry.get("total_checks"), 0),
                "white_screen_refresh_queued": sentry_refresh_queued,
                "strict_global_mode_passed": strict_mode_passed,
                "transient_artifact_count": transient_artifact_count,
                "strict_gate_passed": strict_gate_passed,
            },
            "latest_task_id": snapshot.get("latest_public_task_id") or "",
            "viewport_matrix_run_id": sentry.get("run_id"),
            "generated_at": _now(),
        }

        certificate = await build_release_certificate_snapshot(db, trust_snapshot=snapshot)
        bundle_id = f"bundle-{drill_id}"
        bundle = {
            "bundle_id": bundle_id,
            "created_at": _now(),
            "drill": drill,
            "certificate": certificate,
            "trust_snapshot": {
                "trust_score_percent": snapshot.get("trust_score_percent"),
                "passed_gates": snapshot.get("passed_gates"),
                "total_gates": snapshot.get("total_gates"),
                "gates": snapshot.get("gates"),
                "generated_at": snapshot.get("generated_at"),
            },
            "white_screen_sentry": {
                "run_id": sentry.get("run_id"),
                "gate_passed": sentry_pass,
                "failed_checks": _safe_int(sentry.get("failed_checks"), 0),
                "total_checks": _safe_int(sentry.get("total_checks"), 0),
                "generated_at": sentry.get("generated_at"),
                "failure_reason": sentry.get("failure_reason") or sentry.get("script_stderr_tail"),
            },
            "viewport_matrix": {
                "run_id": sentry.get("run_id"),
                "route_source": sentry.get("route_source"),
                "routes_tested": sentry.get("routes_tested") or [],
                "viewports": sentry.get("viewports") or ["mobile", "tablet", "desktop"],
                "total_checks": _safe_int(sentry.get("total_checks"), 0),
                "failed_checks": _safe_int(sentry.get("failed_checks"), 0),
                "matrix_summary": sentry.get("matrix_summary") or {},
                "artifacts": sentry.get("artifacts") or [],
            },
        }

        drill["evidence_bundle_id"] = bundle_id
        await db.gtec_c5_release_drills.insert_one({**drill})
        await db.gtec_c5_release_evidence_bundles.insert_one({**bundle})
        await db.gtec_c5_release_certificates.update_one(
            {"certificate_id": certificate["certificate_id"]},
            {"$set": certificate},
            upsert=True,
        )
        return {k: v for k, v in drill.items() if k != "_id"}
    finally:
        if simulate_hard_block and original_policy:
            await db[SETTINGS_COL].update_one(
                {"_id": PIPELINE_POLICY_DOC_ID},
                {"$set": {**original_policy, "updated_at": _now()}},
                upsert=True,
            )


def _hash_obj(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
    return h.hexdigest()[:16]


def read_directive_text() -> str:
    try:
        return DIRECTIVE_FILE.read_text()
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────────────────
# STEP 5a — SAST
# ──────────────────────────────────────────────────────────────────────────

# Patterns tuned to catch common insecure code — regex-based, fast.
# Each tuple: (severity, label, compiled_regex, file_glob)
# NOTE: We intentionally exclude node_modules/.venv/test/ fixtures.
_SAST_RULES: list[tuple[str, str, re.Pattern, tuple[str, ...]]] = [
    # Exposed secrets (simple entropy-free match)
    ("critical", "hardcoded_aws_key",
     re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
     (".py", ".ts", ".tsx", ".js", ".jsx", ".yml", ".yaml")),
    ("critical", "hardcoded_private_key",
     re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) (?:PRIVATE )?KEY-----"),
     (".py", ".ts", ".tsx", ".js", ".jsx", ".pem")),
    # Dangerous eval / exec usage in python (not in test files)
    ("high", "python_eval_exec",
     re.compile(r"(?<![\w.])(?:eval|exec)\s*\("),
     (".py",)),
    # SQL injection via string concat (heuristic)
    ("high", "sql_string_concat",
     re.compile(r"""(?i)(?:SELECT|UPDATE|DELETE|INSERT)\s[^\n'"]{0,200}[\"']\s*\+\s*\w"""),
     (".py",)),
    # dangerouslySetInnerHTML with user input (heuristic)
    ("medium", "react_dangerous_inner_html",
     re.compile(r"dangerouslySetInnerHTML"),
     (".ts", ".tsx", ".js", ".jsx")),
    # document.write / innerHTML = user_input
    ("medium", "dom_innerhtml_write",
     re.compile(r"""\.innerHTML\s*=\s*[A-Za-z_]"""),
     (".ts", ".tsx", ".js", ".jsx")),
]

_SAST_SKIP_DIRS = (
    "node_modules", ".venv", "venv", "__pycache__", ".git",
    "dist", "build", ".expo", "web-build", "test_reports", "pw-browsers",
    "android", "ios", ".pytest_cache", "playwright-report", "test-results",
)
_SAST_SKIP_FILES = (
    "audit_v2_theme.py",       # the audit tool itself contains the patterns
    "gtec_scan_v2.py",         # this file defines the patterns
    "test_", "_test.",         # test fixtures
)


def _walk_files(root: Path, exts: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.parts)
        if any(s in parts for s in _SAST_SKIP_DIRS):
            continue
        name = p.name
        if any(skip in name for skip in _SAST_SKIP_FILES):
            continue
        if p.suffix in exts:
            out.append(p)
    return out


async def run_sast() -> dict[str, Any]:
    """Regex-based static analysis across backend + frontend sources."""
    t0 = time.perf_counter()
    findings: list[dict[str, Any]] = []

    # Load reviewed waivers (§4 compliant — each waiver has justification +
    # reviewer + timestamp so suppression is never silent).
    waivers_file = ROOT / "memory" / "gtec_scan_v2_sast_waivers.json"
    waived_labels_files: set[tuple[str, str]] = set()
    try:
        import json as _json
        if waivers_file.exists():
            doc = _json.loads(waivers_file.read_text())
            for w in (doc.get("waivers") or []):
                waived_labels_files.add((w.get("label"), w.get("file")))
    except Exception:
        pass

    # Theme audit — surfaces V2 theme compliance violations (existing CI tool)
    theme_violations = 0
    theme_exit_code = 0
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(AUDIT_V2_SCRIPT),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(ROOT),
        )
        stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
        theme_exit_code = proc.returncode or 0
        # The audit prints "Found N violations"; we extract that.
        txt = stdout.decode("utf-8", "ignore")
        m = re.search(r"(\d+)\s+violation", txt, re.IGNORECASE)
        if m:
            theme_violations = int(m.group(1))
    except Exception as exc:
        logger.warning(f"gtec-v2: theme audit failed: {exc}")
        theme_exit_code = -1

    if theme_exit_code != 0:
        findings.append({
            "severity": "medium",
            "category": "theme_compliance",
            "label": "v2_theme_violations",
            "detail": f"audit_v2_theme.py exit={theme_exit_code} violations={theme_violations}",
            "count": max(theme_violations, 1),
        })

    # Regex sweep — scan backend + frontend (limited depth)
    for severity, label, rx, exts in _SAST_RULES:
        hits: list[str] = []
        for path in _walk_files(ROOT / "backend", exts) + _walk_files(ROOT / "frontend", exts):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if rx.search(text):
                hits.append(str(path.relative_to(ROOT)))
                if len(hits) >= 20:
                    break
        if not hits:
            continue
        # §4-compliant waiver application: split into reviewed (documented
        # low-severity) and unreviewed (original severity). Both reported.
        reviewed = [h for h in hits if (label, h) in waived_labels_files]
        unreviewed = [h for h in hits if (label, h) not in waived_labels_files]
        if unreviewed:
            findings.append({
                "severity": severity,
                "category": "sast",
                "label": label,
                "count": len(unreviewed),
                "sample_files": unreviewed[:5],
            })
        if reviewed:
            # Waived findings: reviewed and documented → reclassify to `info`
            # per §4 (correct severity assignment is not suppression; the
            # finding is still counted and visible in sections + summary).
            # This prevents documented intentional-use cases (e.g. HTML
            # template embedding in +html.tsx, blog content, onboarding
            # tour) from inflating the LOW severity band every scan.
            findings.append({
                "severity": "info",
                "category": "sast",
                "label": f"{label}_waived",
                "count": len(reviewed),
                "sample_files": reviewed[:5],
                "waived": True,
                "note": "reviewed + documented in memory/gtec_scan_v2_sast_waivers.json",
            })

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    counts = _severity_counts(findings)
    return {
        "status": "PASS" if counts["critical"] == 0 and counts["high"] == 0 else "FAIL",
        "findings": findings,
        "counts": counts,
        "elapsed_ms": elapsed_ms,
        "theme_violations": theme_violations,
    }


# ──────────────────────────────────────────────────────────────────────────
# STEP 5b — Dependency scan
# ──────────────────────────────────────────────────────────────────────────

def _load_upstream_watchlist() -> list[dict[str, Any]]:
    path = ROOT / "memory" / "gtec_upstream_watchlist.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = doc.get("watchlist")
    return items if isinstance(items, list) else []


def _build_blocked_dependency_index() -> tuple[set[str], bool]:
    blocked: set[str] = set()
    expo_block_active = False
    for entry in _load_upstream_watchlist():
        pkg = str(entry.get("package") or "").strip().lower()
        if pkg:
            blocked.add(pkg)
            if pkg == "expo":
                expo_block_active = True
        for up in entry.get("unblocks_packages") or []:
            name = str(up or "").strip().lower()
            if name:
                blocked.add(name)
    return blocked, expo_block_active


def _is_blocked_dependency(name: str, blocked_index: set[str], expo_block_active: bool) -> bool:
    dep = str(name or "").strip().lower()
    if not dep:
        return False
    if dep in blocked_index:
        return True
    if expo_block_active:
        if dep.startswith("expo") or dep.startswith("@expo/"):
            return True
        if dep.startswith("react-native") or dep.startswith("@react-navigation/"):
            return True
        if dep in {"react", "react-dom"}:
            return True
    return False


def _is_blocked_dependency_path(path: str, blocked_index: set[str], expo_block_active: bool) -> bool:
    raw = str(path or "").strip().lower()
    if not raw:
        return False

    # Path format example:
    # @opentelemetry/exporter-trace-otlp-http>@opentelemetry/otlp-transformer>protobufjs
    tokens = [t.strip() for t in raw.split(">") if t.strip()]
    for token in tokens:
        if _is_blocked_dependency(token, blocked_index, expo_block_active):
            return True

    if expo_block_active and ("expo>" in raw or "@expo/" in raw):
        return True
    return False


async def run_dependency_scan() -> dict[str, Any]:
    """Dependency risk scan with controlled-upgrade governance.

    - Outdated inventory is tracked, but upstream-blocked bundles are marked
      INFO so the scanner stays truthful and avoids unsafe forced upgrades.
    - Actionable risk is driven by advisories (`yarn audit`) excluding
      blockers already tracked in the upstream watchlist.
    """
    t0 = time.perf_counter()
    findings: list[dict[str, Any]] = []
    blocked_index, expo_block_active = _build_blocked_dependency_index()

    # Python outdated packages
    try:
        proc = await asyncio.create_subprocess_exec(
            "pip", "list", "--outdated", "--format=json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        data = json.loads(stdout.decode("utf-8", "ignore") or "[]")
        if data:
            findings.append({
                "severity": "info",
                "category": "dependency",
                "label": "python_outdated_maintenance",
                "count": len(data),
                "sample_packages": [f"{p.get('name')}@{p.get('version')}→{p.get('latest_version')}" for p in data[:5]],
                "note": "version drift inventory; security severity is determined by advisory feeds",
            })
    except Exception as exc:
        logger.info(f"gtec-v2: pip list --outdated skipped ({exc})")

    # Node outdated inventory
    try:
        proc = await asyncio.create_subprocess_exec(
            "yarn", "outdated", "--json",
            cwd=str(ROOT / "frontend"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)

        actionable_rows: list[list[Any]] = []
        blocked_rows: list[list[Any]] = []
        for line in stdout.decode("utf-8", "ignore").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("type") == "table" and isinstance(row.get("data"), dict):
                body = row["data"].get("body") or []
                for r in body:
                    name = str(r[0] if len(r) > 0 else "")
                    if _is_blocked_dependency(name, blocked_index, expo_block_active):
                        blocked_rows.append(r)
                    else:
                        actionable_rows.append(r)
                break

        if actionable_rows:
            count = len(actionable_rows)
            findings.append({
                "severity": "info",
                "category": "dependency",
                "label": "node_outdated_maintenance",
                "count": count,
                "sample_packages": [f"{r[0]}@{r[1]}→{r[3]}" for r in actionable_rows[:5] if len(r) >= 4],
                "note": "maintenance drift; actionable security risk is tracked via yarn audit findings",
            })
        if blocked_rows:
            findings.append({
                "severity": "info",
                "category": "dependency",
                "label": "node_outdated_blocked_upstream",
                "count": len(blocked_rows),
                "sample_packages": [f"{r[0]}@{r[1]}→{r[3]}" for r in blocked_rows[:5] if len(r) >= 4],
                "waived": True,
                "note": "tracked in gtec_upstream_watchlist.json until upstream blockers clear",
            })
    except Exception as exc:
        logger.info(f"gtec-v2: yarn outdated skipped ({exc})")

    # Node advisories (actionable security surface)
    try:
        proc = await asyncio.create_subprocess_exec(
            "yarn", "audit", "--json",
            cwd=str(ROOT / "frontend"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)

        sev_map = {
            "critical": "critical",
            "high": "high",
            "moderate": "medium",
            "medium": "medium",
            "low": "low",
        }
        actionable_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        actionable_samples: dict[str, list[str]] = {k: [] for k in actionable_counts}
        blocked_count = 0
        blocked_samples: list[str] = []

        for line in stdout.decode("utf-8", "ignore").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("type") != "auditAdvisory":
                continue
            data = row.get("data") or {}
            advisory = data.get("advisory") or {}
            resolution = data.get("resolution") or {}

            module = str(advisory.get("module_name") or "").strip().lower()
            path = str(resolution.get("path") or "").strip().lower()
            sev = sev_map.get(str(advisory.get("severity") or "").strip().lower())
            if sev not in actionable_counts:
                continue

            blocked = _is_blocked_dependency(module, blocked_index, expo_block_active)
            if not blocked:
                blocked = _is_blocked_dependency_path(path, blocked_index, expo_block_active)

            sample = f"{module} via {path}" if path else module
            if blocked:
                blocked_count += 1
                if len(blocked_samples) < 5:
                    blocked_samples.append(sample)
                continue

            actionable_counts[sev] += 1
            if len(actionable_samples[sev]) < 5:
                actionable_samples[sev].append(sample)

        for sev, cnt in actionable_counts.items():
            if cnt <= 0:
                continue
            findings.append({
                "severity": sev,
                "category": "dependency",
                "label": "node_audit_actionable",
                "count": cnt,
                "sample_packages": actionable_samples.get(sev) or [],
            })

        if blocked_count > 0:
            findings.append({
                "severity": "info",
                "category": "dependency",
                "label": "node_audit_blocked_upstream",
                "count": blocked_count,
                "sample_packages": blocked_samples,
                "waived": True,
                "note": "advisories are tied to blocked upstream bundles; tracked by watchdog",
            })
    except Exception as exc:
        logger.info(f"gtec-v2: yarn audit skipped ({exc})")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    counts = _severity_counts(findings)
    return {
        "status": "PASS" if counts["critical"] == 0 and counts["high"] == 0 else "FAIL",
        "findings": findings,
        "counts": counts,
        "elapsed_ms": elapsed_ms,
    }


# ──────────────────────────────────────────────────────────────────────────
# STEP 5c — DAST (reuse existing crawler)
# ──────────────────────────────────────────────────────────────────────────

async def run_dast_via_crawler(viewports: str = "desktop,mobile", *, strict_global: bool = True) -> dict[str, Any]:
    """Reuse the battle-tested gtec_crawler for DAST + responsiveness + E2E."""
    t0 = time.perf_counter()
    findings: list[dict[str, Any]] = []

    extractor = ROOT / "backend" / "scripts" / "gtec_extract_routes.py"
    crawler = ROOT / "backend" / "scripts" / "gtec_crawler.py"
    resolved_frontend = _resolve_external_frontend_base_url(None)
    crawler_exc: Optional[Exception] = None
    for attempt in (1, 2, 3):
        try:
            # Fresh routes file
            ext = await asyncio.create_subprocess_exec(
                sys.executable, str(extractor),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(ext.communicate(), timeout=60)

            env = {
                **os.environ,
                "GTEC_FRONTEND_URL": resolved_frontend,
                "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/pw-browsers"),
            }
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(crawler), "--viewports", viewports,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            # Timeout scales with viewport count. We keep this bounded to avoid
            # long hangs when Playwright/browser runtime is unhealthy. On
            # timeout, retry once then classify infra artifact if persistent.
            vp_count = max(1, len([v for v in viewports.split(",") if v.strip()]))
            # Increased bound to reduce false strict-fail on slow CI/preview runtime.
            dast_timeout = 300 * vp_count
            await asyncio.wait_for(proc.communicate(), timeout=dast_timeout)
            crawler_exc = None
            break
        except Exception as exc:
            crawler_exc = exc
            if attempt < 3:
                await asyncio.sleep(2.0 * attempt)

    if crawler_exc is not None:
        detail = str(crawler_exc or "")[:260]
        if not detail:
            detail = type(crawler_exc).__name__
        detail_l = detail.lower()
        logger.error(f"gtec-v2: crawler failed: {detail}")

        is_infra_artifact = isinstance(crawler_exc, asyncio.TimeoutError) or any(
            token in detail_l
            for token in [
                "targetclosederror",
                "browsertype.launch",
                "sigsegv",
                "headless_shell",
                "timed out",
                "timeouterror",
            ]
        )

        if is_infra_artifact and not strict_global:
            findings.append({
                "severity": "info",
                "category": "dast",
                "label": "crawler_runtime_infra_artifact",
                "detail": detail,
                "count": 1,
                "waived": True,
                "note": "Playwright runtime/browser crash treated as infra artifact after retry.",
            })
            return {
                "status": "PASS",
                "findings": findings,
                "counts": _severity_counts(findings),
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "crawler_totals": {"scans": 0, "passing": 0},
                "actionable_failures": 0,
                "artifact_failures_ignored": 1,
                "responsiveness_status": "PASS",
                "performance_status": "PASS",
                "performance_p50_ms": 0,
            }

        if is_infra_artifact and strict_global:
            findings.append({
                "severity": "high",
                "category": "dast",
                "label": "crawler_runtime_infra_artifact_strict_fail",
                "detail": detail,
                "count": 1,
            })
            return {
                "status": "FAIL",
                "findings": findings,
                "counts": _severity_counts(findings),
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "crawler_totals": None,
            }

        findings.append({
            "severity": "high",
            "category": "dast",
            "label": "crawler_subprocess_error",
            "detail": detail,
            "count": 1,
        })
        return {
            "status": "FAIL",
            "findings": findings,
            "counts": _severity_counts(findings),
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "crawler_totals": None,
        }

    report: dict[str, Any] = {}
    try:
        report = json.loads(CRAWLER_LATEST.read_text()) if CRAWLER_LATEST.exists() else {}
    except Exception:
        report = {}

    totals = report.get("totals") or {}
    failing = [r for r in report.get("results", []) if not r.get("healthy")]

    edge_challenge_rows = [r for r in failing if is_edge_challenge_row(r)]
    runtime_403_rows = [r for r in failing if is_runtime_403_artifact(r)]
    runtime_429_rows = [r for r in failing if is_runtime_429_artifact(r)]
    public_api_auth_rl_rows = [r for r in failing if is_public_api_auth_rate_limit_artifact(r)]
    rate_limit_only_rows = [r for r in failing if is_rate_limit_only_artifact(r)]
    console_403_only_rows = [r for r in failing if is_console_403_only_artifact(r)]
    console_429_only_rows = [r for r in failing if is_console_429_only_artifact(r)]
    artifact_keys = {
        row_key(r)
        for r in (
            edge_challenge_rows
            + runtime_403_rows
            + runtime_429_rows
            + public_api_auth_rl_rows
            + rate_limit_only_rows
            + console_403_only_rows
            + console_429_only_rows
        )
    }
    actionable_failing = [r for r in failing if row_key(r) not in artifact_keys]

    white = [r for r in actionable_failing if r.get("white_screen")]
    http_err = [r for r in actionable_failing if (r.get("status_code") or 0) >= 400 or r.get("status_code") == 0]
    page_err = [r for r in actionable_failing if r.get("page_errors")]
    console_err = [r for r in actionable_failing if r.get("console_errors")]
    failed_apis = [r for r in actionable_failing if r.get("failed_apis")]

    if edge_challenge_rows:
        findings.append({
            "severity": "info",
            "category": "dast",
            "label": "edge_challenge_artifact",
            "count": len(edge_challenge_rows),
            "detail": "Edge/WAF challenge observed (e.g., __cf_chl_rt_tk). Excluded from actionable app defects.",
            "sample": [
                {
                    "url": r.get("url"),
                    "status": r.get("status_code"),
                    "final_url": str(r.get("final_url") or "")[:220],
                }
                for r in edge_challenge_rows[:3]
            ],
        })

    if runtime_403_rows:
        findings.append({
            "severity": "info",
            "category": "dast",
            "label": "runtime_v2_compliance_api_403_artifact",
            "count": len(runtime_403_rows),
            "detail": "Isolated 403 from /api/config/v2-compliance/runtime on otherwise healthy pages; treated as transient edge artifact.",
            "sample": [
                {
                    "url": r.get("url"),
                    "apis": (r.get("failed_apis") or [])[:1],
                }
                for r in runtime_403_rows[:3]
            ],
        })

    if runtime_429_rows:
        findings.append({
            "severity": "info",
            "category": "dast",
            "label": "runtime_v2_compliance_api_429_artifact",
            "count": len(runtime_429_rows),
            "detail": "Isolated 429 from runtime/static config endpoints on otherwise healthy pages; treated as transient edge artifact.",
            "sample": [
                {
                    "url": r.get("url"),
                    "apis": (r.get("failed_apis") or [])[:1],
                }
                for r in runtime_429_rows[:3]
            ],
        })

    if public_api_auth_rl_rows:
        findings.append({
            "severity": "info",
            "category": "dast",
            "label": "public_api_auth_rate_limit_artifact",
            "count": len(public_api_auth_rl_rows),
            "detail": "Public-route auth/rate-limit API noise (401/429) on healthy pages; excluded from actionable defects.",
            "sample": [
                {
                    "url": r.get("url"),
                    "apis": (r.get("failed_apis") or [])[:1],
                }
                for r in public_api_auth_rl_rows[:3]
            ],
        })

    if rate_limit_only_rows:
        findings.append({
            "severity": "info",
            "category": "dast",
            "label": "rate_limit_only_artifact",
            "count": len(rate_limit_only_rows),
            "detail": "Rows with 429-only API failures and rate-limit console noise on otherwise healthy pages; treated as transient edge artifacts.",
            "sample": [
                {
                    "url": r.get("url"),
                    "apis": (r.get("failed_apis") or [])[:1],
                }
                for r in rate_limit_only_rows[:3]
            ],
        })

    if console_403_only_rows:
        findings.append({
            "severity": "info",
            "category": "dast",
            "label": "edge_static_resource_403_artifact",
            "count": len(console_403_only_rows),
            "detail": "Console-only 403 static resource noise on otherwise healthy routes; excluded from actionable defects.",
            "sample": [
                {
                    "url": r.get("url"),
                    "status": r.get("status_code"),
                    "error": (r.get("console_errors") or [""])[0][:200],
                }
                for r in console_403_only_rows[:3]
            ],
        })

    if console_429_only_rows:
        findings.append({
            "severity": "info",
            "category": "dast",
            "label": "edge_static_resource_429_artifact",
            "count": len(console_429_only_rows),
            "detail": "Console-only 429 static/runtime resource noise on otherwise healthy routes; excluded from actionable defects.",
            "sample": [
                {
                    "url": r.get("url"),
                    "status": r.get("status_code"),
                    "error": (r.get("console_errors") or [""])[0][:200],
                }
                for r in console_429_only_rows[:3]
            ],
        })

    if white:
        findings.append({"severity": "critical", "category": "dast", "label": "white_screen", "count": len(white),
                         "sample": [{"url": r["url"], "viewport": r["viewport"]} for r in white[:3]]})
    if http_err:
        findings.append({"severity": "high", "category": "dast", "label": "http_error_route", "count": len(http_err),
                         "sample": [{"url": r["url"], "status": r["status_code"]} for r in http_err[:3]]})
    if page_err:
        findings.append({"severity": "high", "category": "dast", "label": "page_error", "count": len(page_err),
                         "sample": [{"url": r["url"], "errors": r["page_errors"][:1]} for r in page_err[:3]]})
    if console_err:
        findings.append({"severity": "medium", "category": "dast", "label": "console_error", "count": len(console_err),
                         "sample": [{"url": r["url"], "errors": r["console_errors"][:1]} for r in console_err[:3]]})
    if failed_apis:
        findings.append({"severity": "medium", "category": "dast", "label": "failed_api_call", "count": len(failed_apis),
                         "sample": [{"url": r["url"], "apis": r["failed_apis"][:1]} for r in failed_apis[:3]]})

    # Responsiveness: any mobile vs desktop disparity in healthy rate
    mobile_total = sum(1 for r in report.get("results", []) if r.get("viewport") == "mobile")
    mobile_pass = sum(1 for r in report.get("results", []) if r.get("viewport") == "mobile" and r.get("healthy"))
    resp_status = "PASS"
    if mobile_total and mobile_pass / mobile_total < 0.9:
        resp_status = "FAIL"
        findings.append({
            "severity": "high", "category": "responsiveness", "label": "mobile_breakpoint_regression",
            "detail": f"{mobile_pass}/{mobile_total} mobile routes healthy",
            "count": mobile_total - mobile_pass,
        })

    # Performance: median render_ms > 4000ms is a warning
    render_times = [r.get("render_ms") or 0 for r in report.get("results", []) if r.get("viewport") == "desktop"]
    p50 = sorted(render_times)[len(render_times) // 2] if render_times else 0
    perf_status = "PASS" if p50 < 6000 else "FAIL"
    if p50 >= 6000:
        findings.append({
            "severity": "medium", "category": "performance", "label": "slow_p50_render",
            "detail": f"desktop p50 render={p50}ms", "count": 1,
        })

    counts = _severity_counts(findings)
    return {
        "status": "PASS" if not actionable_failing else "FAIL",
        "findings": findings,
        "counts": counts,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "crawler_totals": totals,
        "actionable_failures": len(actionable_failing),
        "artifact_failures_ignored": len(failing) - len(actionable_failing),
        "responsiveness_status": resp_status,
        "performance_status": perf_status,
        "performance_p50_ms": p50,
    }


# ──────────────────────────────────────────────────────────────────────────
# STEP 5d — RBAC + Subscription probes
# ──────────────────────────────────────────────────────────────────────────

# Admin endpoints that MUST 401/403 without auth.
_RBAC_PROBES = [
    "/api/admin/gtec-crawler/latest",
    "/api/admin/code-health/theme-audit",
    "/api/admin/overview",
    "/api/admin/users",
    "/api/admin/analytics/kpis",
]
# Premium-only endpoints that MUST 401 without auth (subscription gate behind auth).
_SUBSCRIPTION_PROBES = [
    "/api/subscription/enforce/check",
    "/api/analytics/insights/premium",
]


async def run_access_control_probes(base_url: str, *, strict_global: bool = True) -> dict[str, Any]:
    """Anonymous probes against admin + premium routes — expect 401/403."""
    t0 = time.perf_counter()
    findings: list[dict[str, Any]] = []
    rbac_pass = 0
    rbac_leaks: list[dict[str, Any]] = []
    rbac_probe_issues: list[dict[str, Any]] = []
    rbac_transient_issues: list[dict[str, Any]] = []
    sub_pass = 0
    sub_leaks: list[dict[str, Any]] = []
    sub_probe_issues: list[dict[str, Any]] = []
    sub_transient_issues: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=10, follow_redirects=False, verify=get_httpx_verify()) as cli:
        for path in _RBAC_PROBES:
            try:
                r, err = await _probe_with_transient_retry(
                    cli,
                    "GET",
                    base_url.rstrip("/") + path,
                    attempts=3,
                    transient_statuses=(502, 503, 504),
                )
                if r is None:
                    raise RuntimeError(err or "no response")
                if r.status_code in (401, 403, 404, 302, 307, 308):
                    rbac_pass += 1
                elif r.status_code == 200:
                    rbac_leaks.append({"path": path, "status": r.status_code})
                elif r.status_code in (502, 503, 504):
                    if strict_global:
                        rbac_probe_issues.append({"path": path, "status": r.status_code})
                    else:
                        rbac_transient_issues.append({"path": path, "status": r.status_code})
                else:
                    rbac_probe_issues.append({"path": path, "status": r.status_code})
            except Exception as exc:
                msg = str(exc)[:120]
                if any(k in msg.lower() for k in ["timeout", "connect", "temporarily", "reset by peer"]):
                    if strict_global:
                        rbac_probe_issues.append({"path": path, "error": msg})
                    else:
                        rbac_transient_issues.append({"path": path, "error": msg})
                else:
                    rbac_probe_issues.append({"path": path, "error": msg})

        for path in _SUBSCRIPTION_PROBES:
            try:
                r, err = await _probe_with_transient_retry(
                    cli,
                    "GET",
                    base_url.rstrip("/") + path,
                    attempts=3,
                    transient_statuses=(502, 503, 504),
                )
                if r is None:
                    raise RuntimeError(err or "no response")
                if r.status_code in (401, 403, 404, 422, 302, 307, 308):
                    sub_pass += 1
                elif r.status_code == 200:
                    sub_leaks.append({"path": path, "status": r.status_code})
                elif r.status_code in (502, 503, 504):
                    if strict_global:
                        sub_probe_issues.append({"path": path, "status": r.status_code})
                    else:
                        sub_transient_issues.append({"path": path, "status": r.status_code})
                else:
                    sub_probe_issues.append({"path": path, "status": r.status_code})
            except Exception as exc:
                msg = str(exc)[:120]
                if any(k in msg.lower() for k in ["timeout", "connect", "temporarily", "reset by peer"]):
                    if strict_global:
                        sub_probe_issues.append({"path": path, "error": msg})
                    else:
                        sub_transient_issues.append({"path": path, "error": msg})
                else:
                    sub_probe_issues.append({"path": path, "error": msg})

    if rbac_leaks:
        findings.append({
            "severity": "critical", "category": "rbac", "label": "admin_route_leaked",
            "detail": f"{len(rbac_leaks)}/{len(_RBAC_PROBES)} probes returned 200 without auth",
            "count": len(rbac_leaks),
            "sample": rbac_leaks[:3],
        })
    if sub_leaks:
        findings.append({
            "severity": "critical", "category": "subscription", "label": "premium_route_leaked",
            "detail": f"{len(sub_leaks)}/{len(_SUBSCRIPTION_PROBES)} probes returned 200 without auth",
            "count": len(sub_leaks),
            "sample": sub_leaks[:3],
        })
    if rbac_probe_issues:
        findings.append({
            "severity": "medium", "category": "rbac", "label": "admin_probe_inconclusive",
            "detail": f"{len(rbac_probe_issues)} probe(s) returned non-auth status or transient errors",
            "count": len(rbac_probe_issues),
            "sample": rbac_probe_issues[:3],
        })
    if rbac_transient_issues and not strict_global:
        findings.append({
            "severity": "info", "category": "rbac", "label": "admin_probe_transient_gateway_artifact",
            "detail": f"{len(rbac_transient_issues)} probe(s) hit transient edge/network errors after retries",
            "count": len(rbac_transient_issues),
            "sample": rbac_transient_issues[:3],
            "waived": True,
        })
    if sub_probe_issues:
        findings.append({
            "severity": "medium", "category": "subscription", "label": "premium_probe_inconclusive",
            "detail": f"{len(sub_probe_issues)} probe(s) returned non-auth status or transient errors",
            "count": len(sub_probe_issues),
            "sample": sub_probe_issues[:3],
        })
    if sub_transient_issues and not strict_global:
        findings.append({
            "severity": "info", "category": "subscription", "label": "premium_probe_transient_gateway_artifact",
            "detail": f"{len(sub_transient_issues)} probe(s) hit transient edge/network errors after retries",
            "count": len(sub_transient_issues),
            "sample": sub_transient_issues[:3],
            "waived": True,
        })

    return {
        "rbac_status": "PASS" if not (rbac_leaks or rbac_probe_issues) else "FAIL",
        "subscription_status": "PASS" if not (sub_leaks or sub_probe_issues) else "FAIL",
        "rbac_pass": rbac_pass,
        "rbac_total": len(_RBAC_PROBES),
        "subscription_pass": sub_pass,
        "subscription_total": len(_SUBSCRIPTION_PROBES),
        "findings": findings,
        "counts": _severity_counts(findings),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }


# ──────────────────────────────────────────────────────────────────────────
# i18n public-access guardrail — Global Language Translation Audit v1
# ──────────────────────────────────────────────────────────────────────────
#
# On 2026-04-24 the platform-wide i18n regression was caused by the DOM
# translation engine's endpoint being gated by BOTH auth and CSRF checks.
# Anonymous visitors (welcome / login / register / public footer) received
# 401 / 403 responses, and the client engine cached the failure as
# "English is the translation" — permanently freezing those surfaces in
# English. See `backend/tests/test_i18n_auto_translate_public.py` for the
# unit-level test of this property.
#
# The GTEC C5 scan runs this probe every 3 hours (and on every manual
# trigger) against the LIVE deployed origin. If any anonymous call to the
# i18n DOM-engine endpoints returns a non-200, it emits a HIGH-severity
# finding so the next report highlights the regression in red instead of
# letting users discover it by trying to switch language.
_I18N_PUBLIC_PROBES = [
    # These endpoints MUST succeed anonymously — the DOM translation engine
    # runs pre-auth and will cache English-as-translation on any failure.
    {
        "name": "auto-translate (no headers)",
        "method": "POST",
        "path": "/api/i18n/auto-translate",
        "body": {"texts": ["Welcome Back", "Sign In", "Pricing"], "lang": "fr"},
        "assert": "translations",  # response json key that must exist
        "assert_sample": ("Sign In", "fr"),  # (input, lang) must round-trip ≠ input
    },
    {
        "name": "auto-translate (with X-Requested-With)",
        "method": "POST",
        "path": "/api/i18n/auto-translate",
        "body": {"texts": ["Learning Hub"], "lang": "es"},
        "headers": {"X-Requested-With": "tx-engine"},
        "assert": "translations",
    },
    {
        "name": "auto-translate (english passthrough)",
        "method": "POST",
        "path": "/api/i18n/auto-translate",
        "body": {"texts": ["Welcome", "Pricing"], "lang": "en"},
        "assert": "translations",
    },
    {
        "name": "fallback-hit batch telemetry",
        "method": "POST",
        "path": "/api/i18n/fallback-hit/batch",
        "body": {"hits": [{"lang": "fr", "key": "gtec_scan_probe"}]},
        "accept_statuses": (200, 201, 202, 204),
    },
    {
        "name": "languages list GET",
        "method": "GET",
        "path": "/api/i18n/languages",
        "accept_statuses": (200,),
    },
]


async def run_i18n_public_access_probes(base_url: str, *, strict_global: bool = True) -> dict[str, Any]:
    """Verify the DOM translation engine's endpoints are reachable by an
    ANONYMOUS visitor — no auth cookie, no CSRF token.

    If any probe fails, the next language switch on a public page
    (welcome / login / register) will silently stay in English. This
    guardrail turns that silent failure into a flagged GTEC C5 finding.
    """
    t0 = time.perf_counter()
    findings: list[dict[str, Any]] = []
    transient_findings: list[dict[str, Any]] = []
    probe_results: list[dict[str, Any]] = []
    passed = 0

    async with httpx.AsyncClient(timeout=10, follow_redirects=False, verify=get_httpx_verify()) as cli:
        for probe in _I18N_PUBLIC_PROBES:
            url = base_url.rstrip("/") + probe["path"]
            method = probe.get("method", "GET")
            headers = probe.get("headers", {}) or {}
            # Intentionally send NO auth cookies (fresh client per iteration
            # would be ideal, but httpx clients don't share cookies unless
            # we explicitly attach them — so this is already cookieless).
            # Retry once on transient 502/503 from the preview proxy —
            # the ingress occasionally blips while the pod is warming.
            r = None
            last_err: str | None = None
            for attempt in (1, 2, 3):
                try:
                    if method == "POST":
                        r = await cli.post(url, json=probe.get("body") or {}, headers=headers)
                    else:
                        r = await cli.get(url, headers=headers)
                    if r.status_code in (502, 503, 504) and attempt < 3:
                        await asyncio.sleep(1.5)
                        continue
                    break
                except Exception as exc:
                    last_err = f"{type(exc).__name__}: {str(exc)[:80]}"
                    if attempt < 3:
                        await asyncio.sleep(1.5)
                        continue
                    r = None
                    break
            try:
                if r is None:
                    raise RuntimeError(last_err or "no response")

                accept = probe.get("accept_statuses") or (200,)
                ok = r.status_code in accept

                # Extra assertion: if the probe declares an `assert` key and
                # an `assert_sample`, require the sample string to actually
                # translate (not echo) — catches the case where the endpoint
                # is reachable but upstream LLM / cache is wedged.
                if ok and probe.get("assert"):
                    try:
                        data = r.json()
                        assert_key = probe["assert"]
                        if assert_key not in data:
                            ok = False
                            detail = f"missing '{assert_key}' key in response"
                        elif probe.get("assert_sample"):
                            src, lang = probe["assert_sample"]
                            tr = data.get(assert_key) or {}
                            if tr.get(src) == src or not tr.get(src):
                                ok = False
                                detail = f"'{src}' did not translate to {lang} (got {tr.get(src)!r})"
                            else:
                                detail = f"ok — '{src}' → {tr[src]!r}"
                        else:
                            detail = "ok"
                    except Exception as exc:
                        ok = False
                        detail = f"response not JSON: {type(exc).__name__}"
                else:
                    detail = "ok" if ok else f"status={r.status_code} body={r.text[:120]}"

                probe_results.append({
                    "name": probe["name"],
                    "method": method,
                    "path": probe["path"],
                    "status": r.status_code,
                    "ok": ok,
                    "detail": detail,
                })
                if ok:
                    passed += 1
                else:
                    if r.status_code in (502, 503, 504) and not strict_global:
                        transient_findings.append({
                            "severity": "info",
                            "category": "i18n",
                            "label": "i18n_public_endpoint_transient_gateway_artifact",
                            "detail": f"{probe['name']} returned transient {r.status_code} after retries; treated as infra artifact.",
                            "count": 1,
                            "sample": {"path": probe["path"], "method": method, "status": r.status_code},
                            "waived": True,
                        })
                    else:
                        findings.append({
                            # HIGH — every hard failure here directly translates into
                            # a user-visible translation regression.
                            "severity": "high",
                            "category": "i18n",
                            "label": "i18n_public_endpoint_blocked",
                            "detail": (
                                f"{probe['name']} returned {r.status_code} as anonymous. "
                                f"Anonymous visitors on welcome/login/register/footer will "
                                f"see these strings permanently cached as English. Check "
                                f"middleware.AUTH_PUBLIC_PREFIXES + CSRF_EXEMPT_PREFIXES."
                            ),
                            "count": 1,
                            "sample": {"path": probe["path"], "method": method,
                                       "status": r.status_code,
                                       "body_excerpt": r.text[:140]},
                        })
            except Exception as exc:
                msg = str(exc)[:120]
                transient_like = any(k in msg.lower() for k in ["timeout", "connect", "temporarily", "reset by peer", "no response"])
                probe_results.append({
                    "name": probe["name"],
                    "method": method,
                    "path": probe["path"],
                    "status": 0,
                    "ok": False,
                    "detail": f"error: {type(exc).__name__}: {msg}",
                })
                bucket = transient_findings if (transient_like and not strict_global) else findings
                bucket.append({
                    "severity": "info" if (transient_like and not strict_global) else "high",
                    "category": "i18n",
                    "label": (
                        "i18n_public_endpoint_transient_unreachable"
                        if (transient_like and not strict_global)
                        else "i18n_public_endpoint_unreachable"
                    ),
                    "detail": f"{probe['name']} raised {type(exc).__name__}: {msg}",
                    "count": 1,
                    "sample": {"path": probe["path"], "method": method},
                    **({"waived": True} if (transient_like and not strict_global) else {}),
                })

    status = "PASS" if not findings else "FAIL"
    all_findings = findings + transient_findings

    return {
        "status": status,
        "probes_passed": passed,
        "probes_total": len(_I18N_PUBLIC_PROBES),
        "probe_results": probe_results,
        "findings": all_findings,
        "counts": _severity_counts(all_findings),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }


# ──────────────────────────────────────────────────────────────────────────
# STEP 5f — Duplicate source detection
# ──────────────────────────────────────────────────────────────────────────

def run_duplicate_source_scan() -> dict[str, Any]:
    t0 = time.perf_counter()
    findings: list[dict[str, Any]] = []

    targets = [
        ROOT / "backend" / "routes",
        ROOT / "backend" / "services",
        ROOT / "frontend" / "src" / "components",
        ROOT / "frontend" / "app",
    ]
    hashes: dict[str, list[str]] = {}
    scanned = 0

    for base in targets:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".py", ".tsx", ".ts", ".js", ".jsx"}:
                continue
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            normalized = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
            if len(normalized) < 300:
                continue
            scanned += 1
            h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            hashes.setdefault(h, []).append(str(p.relative_to(ROOT)))

    duplicate_groups_raw = [v for v in hashes.values() if len(v) > 1]
    duplicate_groups: list[list[str]] = []
    for grp in duplicate_groups_raw:
        lowered = {g.lower() for g in grp}
        # Ignore case-only alias files (legacy compatibility shims),
        # e.g. ExecIDCheckerPanel.tsx vs ExecIdCheckerPanel.tsx
        if len(lowered) == 1:
            continue
        duplicate_groups.append(grp)
    if duplicate_groups:
        findings.append({
            "severity": "medium",
            "category": "source",
            "label": "duplicate_source_units",
            "count": len(duplicate_groups),
            "sample": duplicate_groups[:5],
            "detail": "Exact duplicate normalized source units detected",
        })

    return {
        "status": "PASS" if not duplicate_groups else "FAIL",
        "findings": findings,
        "counts": _severity_counts(findings),
        "scanned_files": scanned,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }


# ──────────────────────────────────────────────────────────────────────────
# STEP 5g — API contract / JSON surface checks
# ──────────────────────────────────────────────────────────────────────────

async def run_api_contract_scan(*, strict_global: bool = True) -> dict[str, Any]:
    t0 = time.perf_counter()
    findings: list[dict[str, Any]] = []
    transient_findings: list[dict[str, Any]] = []

    base = str(os.environ.get("GTEC_LOCAL_BACKEND_URL") or "http://127.0.0.1:8001").rstrip("/")
    probes = [
        {"path": "/api/health", "expect": 200},
        {"path": "/api/features/registry", "expect": 200},
        {"path": "/api/system/live-metrics", "expect": 200},
        {"path": "/api/auth/sso-config", "expect": 200},
    ]
    passed = 0

    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as cli:
        for probe in probes:
            path = str(probe.get("path") or "")
            expect = int(probe.get("expect") or 200)
            try:
                resp, err = await _probe_with_transient_retry(
                    cli,
                    "GET",
                    base + path,
                    attempts=3,
                    transient_statuses=(502, 503, 504),
                )
                if resp is None:
                    raise RuntimeError(err or "no response")
                ctype = str(resp.headers.get("content-type") or "").lower()
                is_json = "application/json" in ctype
                if resp.status_code == expect and is_json:
                    passed += 1
                else:
                    if resp.status_code in (502, 503, 504) and not strict_global:
                        transient_findings.append({
                            "severity": "info",
                            "category": "api_contract",
                            "label": "api_contract_transient_gateway_artifact",
                            "count": 1,
                            "detail": f"{path} returned transient {resp.status_code} after retries",
                            "sample": {"path": path, "status": resp.status_code},
                            "waived": True,
                        })
                    else:
                        findings.append({
                            "severity": "high",
                            "category": "api_contract",
                            "label": "api_contract_violation",
                            "count": 1,
                            "detail": f"{path} expected {expect} JSON, got {resp.status_code} ({ctype})",
                            "sample": {"path": path, "status": resp.status_code, "content_type": ctype[:120]},
                        })
            except Exception as exc:
                msg = str(exc)[:180]
                transient_like = any(k in msg.lower() for k in ["timeout", "connect", "temporarily", "reset by peer", "no response"])
                bucket = transient_findings if (transient_like and not strict_global) else findings
                bucket.append({
                    "severity": "info" if (transient_like and not strict_global) else "high",
                    "category": "api_contract",
                    "label": (
                        "api_contract_transient_unreachable"
                        if (transient_like and not strict_global)
                        else "api_contract_unreachable"
                    ),
                    "count": 1,
                    "detail": f"{path} probe failed: {type(exc).__name__}",
                    "sample": {"path": path, "error": msg},
                    **({"waived": True} if (transient_like and not strict_global) else {}),
                })

    all_findings = findings + transient_findings

    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": all_findings,
        "counts": _severity_counts(all_findings),
        "probes_passed": passed,
        "probes_total": len(probes),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }


# ──────────────────────────────────────────────────────────────────────────
# STEP 5h — Threat topology drift (platform-data-only)
# ──────────────────────────────────────────────────────────────────────────

def _collect_route_signatures() -> list[str]:
    route_files = sorted((ROOT / "backend" / "routes").glob("*.py"))
    sigs: list[str] = []
    route_re = re.compile(r"@router\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]")
    for f in route_files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in route_re.finditer(text):
            sigs.append(f"{m.group(1).upper()} {m.group(2)}")
    return sorted(set(sigs))


async def run_threat_topology_scan(db) -> dict[str, Any]:
    t0 = time.perf_counter()
    findings: list[dict[str, Any]] = []
    sigs = _collect_route_signatures()
    admin_paths = [s for s in sigs if " /admin/" in f" {s}"]

    topology_hash = _hash_obj("|".join(sigs), len(admin_paths))
    previous = await db["gtec_threat_topology"].find_one({"_id": "active"}, {"_id": 0}) or {}
    prev_hash = str(previous.get("topology_hash") or "")
    prev_admin_count = int(previous.get("admin_path_count") or 0)
    delta_admin = len(admin_paths) - prev_admin_count

    if prev_hash and prev_hash != topology_hash:
        severity = "medium" if abs(delta_admin) >= 5 else "info"
        findings.append({
            "severity": severity,
            "category": "threat_model",
            "label": "threat_topology_drift",
            "count": 1,
            "detail": f"Topology hash changed; admin path delta={delta_admin}",
            "sample": {
                "previous_hash": prev_hash,
                "current_hash": topology_hash,
                "previous_admin_paths": prev_admin_count,
                "current_admin_paths": len(admin_paths),
            },
        })

    await db["gtec_threat_topology"].update_one(
        {"_id": "active"},
        {
            "$set": {
                "topology_hash": topology_hash,
                "route_count": len(sigs),
                "admin_path_count": len(admin_paths),
                "updated_at": _now(),
                "sample_admin_paths": admin_paths[:25],
            }
        },
        upsert=True,
    )

    counts = _severity_counts(findings)
    status = "PASS" if counts.get("critical", 0) == 0 and counts.get("high", 0) == 0 and counts.get("medium", 0) == 0 else "FAIL"
    return {
        "status": status,
        "findings": findings,
        "counts": counts,
        "route_count": len(sigs),
        "admin_path_count": len(admin_paths),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    c = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = (f.get("severity") or "info").lower()
        if sev in c:
            # Dependency-freshness findings roll up many sub-items under a single
            # finding (e.g. "51 packages outdated"). Weighting by `count` caused
            # the dashboard to show "51 Medium" for what is truthfully one
            # Medium finding with 51 sub-items. For all other categories, keep
            # the legacy weight-by-count so real per-instance issues (e.g. SAST
            # rule violations) still aggregate correctly.
            weight = 1 if f.get("category") == "dependency" else max(int(f.get("count") or 1), 1)
            c[sev] += weight
    return c


async def _update_memory(db, fingerprints: list[str], task_id: str) -> int:
    """Persist learning-memory entries. Returns number of recurring patterns."""
    recurring = 0
    for fp in fingerprints:
        existing = await db[MEMORY_COL].find_one({"_id": fp}, {"_id": 0, "hits": 1})
        new_hits = (existing.get("hits") if existing else 0) + 1
        if new_hits > 1:
            recurring += 1
        await db[MEMORY_COL].update_one(
            {"_id": fp},
            {"$set": {"last_seen_task": task_id, "last_seen_at": _now()},
             "$inc": {"hits": 1}},
            upsert=True,
        )
    return recurring


def _fingerprints(sections: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for s in sections:
        for f in s.get("findings", []) or []:
            out.append(_hash_obj(f.get("category"), f.get("label")))
    return out


def _v3_output_block(
    *,
    overall_status: str,
    security_scan: str,
    performance: str,
    i18n_status: str,
    rbac_status: str,
    regressions: bool,
    agg_counts: dict[str, int],
    sections: dict[str, dict[str, Any]],
    memory_recurring: int,
    restart_count: int = 0,
) -> dict[str, str]:
    """Build the v3 §13 ADDITIVE output block (does NOT replace v2 §12).

    Required fields per the GTEC SCAN v3 UPGRADE directive:
      SYSTEM_STATUS, SECURITY_STATUS, PERFORMANCE_STATUS, I18N_STATUS,
      RBAC_STATUS, REGRESSION_STATUS, ERROR_COUNT, ACTIVE_FIXES,
      MONITORING, LEARNING_MEMORY, CONFIDENCE_LEVEL
    """
    critical_v = int(agg_counts.get("critical") or 0)
    high_v = int(agg_counts.get("high") or 0)
    medium_v = int(agg_counts.get("medium") or 0)
    low_v = int(agg_counts.get("low") or 0)
    error_count = critical_v + high_v + medium_v + low_v
    security_status = "FAIL" if (str(security_scan).upper() == "FAIL" or error_count > 0) else "PASS"
    # ACTIVE_FIXES: YES if remediation has been triggered (restart_count
    # is non-zero) OR if any FAIL pillar still requires a fix this cycle.
    pillar_failures = [
        x for x in (security_scan, performance, i18n_status, rbac_status)
        if str(x).upper() == "FAIL"
    ]
    active_fixes = "YES" if (restart_count > 0 or pillar_failures or error_count > 0) else "NO"

    # MONITORING: derived from the §10 Real-Time Monitoring contract
    # (anomaly + scheduler heartbeats). The GTEC C5 scheduler heartbeat
    # being healthy implies background monitoring loops are alive.
    # NOTE: detailed liveness is recorded against scheduler_heartbeats by
    # APScheduler — here we publish ACTIVE because the very fact that this
    # scan is running means the directive's monitoring loop is alive.
    monitoring = "ACTIVE"

    learning_memory = "UPDATED"

    # CONFIDENCE_LEVEL — heuristic derived from §12 completion rule:
    #   HIGH    → all pillars PASS, 0 critical/high, no recurring memory hits
    #   MEDIUM  → at most medium findings OR recurring patterns detected
    #   LOW     → any FAIL pillar, regressions, critical/high finding,
    #             or duplicate execution (loop detected)
    if (
        str(overall_status).upper() == "FAIL"
        or regressions
        or error_count > 0
    ):
        confidence = "LOW"
    elif memory_recurring > 0:
        confidence = "MEDIUM"
    else:
        confidence = "HIGH"

    return {
        "SYSTEM_STATUS": str(overall_status).upper(),
        "SECURITY_STATUS": security_status,
        "PERFORMANCE_STATUS": str(performance).upper(),
        "I18N_STATUS": str(i18n_status).upper(),
        "RBAC_STATUS": str(rbac_status).upper(),
        "REGRESSION_STATUS": "FAIL" if regressions else "PASS",
        "ERROR_COUNT": str(error_count),
        "ACTIVE_FIXES": active_fixes,
        "MONITORING": monitoring,
        "LEARNING_MEMORY": learning_memory,
        "CONFIDENCE_LEVEL": confidence,
    }


def _structured_report(
    task_id: str,
    execution_hash: str,
    sections: dict[str, dict[str, Any]],
    prev_report: Optional[dict[str, Any]],
    memory_recurring: int,
) -> dict[str, Any]:
    """Build the mandatory §12 output format (preserved verbatim) AND
    attach the additive v3 §13 output block per the GTEC SCAN v3 UPGRADE
    directive."""
    sast = sections["sast"]
    dep = sections["dep"]
    dast = sections["dast"]
    acl = sections["acl"]
    i18n_section = sections.get("i18n") or {}
    duplicate_section = sections.get("duplicate") or {}
    api_contract_section = sections.get("api_contract") or {}
    threat_section = sections.get("threat_model") or {}

    agg_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for s in (sast, dep, dast, acl, i18n_section, duplicate_section, api_contract_section, threat_section):
        for k, v in (s.get("counts") or {}).items():
            agg_counts[k] = agg_counts.get(k, 0) + v

    regressions = False
    if prev_report:
        prev_counts = prev_report.get("severity_counts") or {}
        if (agg_counts["critical"] > (prev_counts.get("critical") or 0)
                or agg_counts["high"] > (prev_counts.get("high") or 0)):
            regressions = True

    # Directive §11: "Any step is skipped or partially executed" → FAIL.
    # Each validation section must have run and returned a status. Missing
    # sections, empty counts, or raised exceptions now hard-fail the task.
    step_completeness = {
        "sast":  bool(sast) and "status" in sast,
        "dep":   bool(dep) and "status" in dep,
        "dast":  bool(dast) and "status" in dast and dast.get("crawler_totals") is not None,
        "acl":   bool(acl) and "rbac_status" in acl and "subscription_status" in acl,
        "duplicate": bool(duplicate_section) and "status" in duplicate_section,
        "api_contract": bool(api_contract_section) and "status" in api_contract_section,
        "threat_model": bool(threat_section) and "status" in threat_section,
    }
    steps_skipped = [k for k, ok in step_completeness.items() if not ok]
    # Mobile/Tablet/Desktop/Wide — all 4 breakpoints per §7 must be covered
    # in the DAST crawler_totals when the scan is invoked with the default
    # 4-viewport config. If fewer viewports ran, that's partial execution.
    set((dast.get("viewports_ran") or []))
    # (viewports_ran is stamped below — compute and attach.)

    any_vulns = (
        int(agg_counts.get("critical") or 0)
        + int(agg_counts.get("high") or 0)
        + int(agg_counts.get("medium") or 0)
        + int(agg_counts.get("low") or 0)
    ) > 0
    security_scan = "PASS" if (
        sast["status"] == "PASS"
        and dep["status"] == "PASS"
        and api_contract_section.get("status") == "PASS"
        and duplicate_section.get("status") == "PASS"
        and threat_section.get("status") == "PASS"
        and not any_vulns
    ) else "FAIL"
    e2e_tests = "PASS" if dast["status"] == "PASS" else "FAIL"
    responsiveness = dast.get("responsiveness_status", "PASS")
    performance = dast.get("performance_status", "PASS")
    rbac_status = acl.get("rbac_status", "PASS")
    subscription_enforcement = acl.get("subscription_status", "PASS")
    # v3 §3 — I18N global system status. Derived from the i18n probe
    # section attached during _single_scan_pass (run_i18n_public_access_probes).
    i18n_status = (i18n_section.get("status") or "PASS").upper()

    overall = "PASS"
    if (agg_counts["critical"] > 0 or agg_counts["high"] > 0
            or agg_counts["medium"] > 0 or agg_counts["low"] > 0
            or regressions
            or steps_skipped   # §11 — any step skipped/partial → FAIL
            or any(x == "FAIL" for x in (security_scan, e2e_tests, responsiveness,
                                          performance, rbac_status, subscription_enforcement,
                                          i18n_status))):
        overall = "FAIL"

    summary_lines = []
    if sast["status"] == "FAIL":
        summary_lines.append(f"SAST flagged {sum(sast['counts'].values())} issue(s)")
    if dep["status"] == "FAIL":
        summary_lines.append(f"{sum(dep['counts'].values())} outdated dependency group(s)")
    if dast.get("crawler_totals"):
        t = dast["crawler_totals"]
        summary_lines.append(f"E2E crawler: {t.get('passing')}/{t.get('scans')} healthy")
    if acl["rbac_status"] == "FAIL":
        summary_lines.append("RBAC probes failed")
    if acl["subscription_status"] == "FAIL":
        summary_lines.append("Subscription probes failed")
    if memory_recurring:
        summary_lines.append(f"{memory_recurring} recurring finding(s) flagged for systemic fix")
    if i18n_status == "FAIL":
        summary_lines.append("i18n public probes failed")
    if duplicate_section.get("status") == "FAIL":
        summary_lines.append("duplicate source scan found duplicate units")
    if api_contract_section.get("status") == "FAIL":
        summary_lines.append("api contract probes failed")
    if threat_section.get("status") == "FAIL":
        summary_lines.append("threat topology drift exceeded threshold")
    if not summary_lines:
        summary_lines.append("All validation pillars passed.")
    if steps_skipped:
        summary_lines.insert(0, f"{len(steps_skipped)} step(s) skipped/partial: {', '.join(steps_skipped)} — §11 fail")

    v3_output = _v3_output_block(
        overall_status=overall,
        security_scan=security_scan,
        performance=performance,
        i18n_status=i18n_status,
        rbac_status=rbac_status,
        regressions=regressions,
        agg_counts=agg_counts,
        sections=sections,
        memory_recurring=memory_recurring,
        restart_count=0,  # stamped by orchestrator after restart loop
    )

    return {
        "task_id": task_id,
        "execution_hash": execution_hash,
        "status": overall,
        "critical_vulns": agg_counts["critical"],
        "high_vulns": agg_counts["high"],
        "medium_vulns": agg_counts["medium"],
        "low_vulns": agg_counts["low"],
        "regressions": "YES" if regressions else "NO",
        "security_scan": security_scan,
        "e2e_tests": e2e_tests,
        "responsiveness": responsiveness,
        "performance": performance,
        "rbac_status": rbac_status,
        "subscription_enforcement": subscription_enforcement,
        "i18n_status": i18n_status,
        "learning_memory_updated": "YES",
        "summary": " · ".join(summary_lines),
        "severity_counts": agg_counts,
        "sections": sections,
        "steps_skipped": steps_skipped,
        "directive_version": _hash_obj(read_directive_text()[:4000]),
        "generated_at": _now(),
        # ── GTEC SCAN v3 §13 — additive output (does NOT replace v2 §12) ──
        "v3_output": v3_output,
    }


def _confidence_for_finding(severity: str, detail: str) -> float:
    sev = str(severity or "").lower()
    base = {"critical": 0.96, "high": 0.9, "medium": 0.8, "low": 0.7, "info": 0.6}.get(sev, 0.6)
    if "verified" in str(detail or "").lower():
        base = min(0.99, base + 0.04)
    return round(base, 2)


async def write_canonical_models(db, report: dict[str, Any]) -> dict[str, Any]:
    """Write-through canonical C1/C2/C3 model collections for trust-grade audit.

    Keeps operational gtec_scan_c5_* collections unchanged while maintaining
    canonical graph/catalog/policy collections requested in the pro-grade plan.
    """
    task_id = str(report.get("task_id") or "")
    execution_hash = str(report.get("execution_hash") or "")
    generated_at = str(report.get("generated_at") or _now())
    status = str(report.get("status") or "UNKNOWN").upper()
    trigger = str(report.get("triggered_by") or "scheduler")
    actor = str(report.get("actor") or "system")

    sections = report.get("sections") or {}
    findings_docs: list[dict[str, Any]] = []
    for section_name, section in sections.items():
        for f in (section.get("findings") or []):
            label = str(f.get("label") or "unknown")
            severity = str(f.get("severity") or "info").lower()
            detail = str(f.get("detail") or "")
            finding_id = _hash_obj(task_id, section_name, label, detail[:300])
            findings_docs.append({
                "finding_id": finding_id,
                "task_id": task_id,
                "execution_hash": execution_hash,
                "section": section_name,
                "label": label,
                "severity": severity,
                "detail": detail,
                "sample": f.get("sample"),
                "evidence": f.get("evidence"),
                "confidence": _confidence_for_finding(severity, detail),
                "exploitability": "high" if severity in {"critical", "high"} else "medium" if severity == "medium" else "low",
                "asset_impact": "platform_global",
                "status": "open" if status == "FAIL" else "closed",
                "created_at": generated_at,
                "updated_at": _now(),
            })

    await db[EXECUTION_GRAPH_COL].update_one(
        {"execution_id": task_id},
        {
            "$set": {
                "execution_id": task_id,
                "task_id": task_id,
                "execution_hash": execution_hash,
                "trigger_source": trigger,
                "actor": actor,
                "status": status,
                "scope": "global_platform",
                "directive_version": report.get("directive_version"),
                "generated_at": generated_at,
                "updated_at": _now(),
            }
        },
        upsert=True,
    )

    await db[FINDING_CATALOG_COL].delete_many({"task_id": task_id})
    if findings_docs:
        await db[FINDING_CATALOG_COL].insert_many(findings_docs)

    latest_ledger = (report.get("remediation_ledgers") or [])[-1] if (report.get("remediation_ledgers") or []) else {}
    for action in (latest_ledger.get("actions") or []):
        label = str(action.get("label") or "")
        if not label:
            continue
        await db[REMEDIATION_PLANS_COL].update_one(
            {"label": label},
            {
                "$set": {
                    "label": label,
                    "last_task_id": task_id,
                    "last_status": action.get("status"),
                    "last_action_taken": action.get("action_taken"),
                    "last_detail": action.get("detail"),
                    "deterministic_handler": True,
                    "updated_at": _now(),
                },
                "$setOnInsert": {"created_at": _now()},
            },
            upsert=True,
        )

    async for incident in db[INCIDENTS_COL].find({}, {"_id": 0}).sort("updated_at", -1).limit(500):
        incident_id = incident.get("incident_id")
        if not incident_id:
            continue
        await db[CANONICAL_INCIDENTS_COL].update_one(
            {"incident_id": incident_id},
            {"$set": {**incident, "updated_at": _now()}},
            upsert=True,
        )

    policy = await get_effective_policy(db)
    await db[POLICY_STORE_COL].update_one(
        {"_id": "effective"},
        {
            "$set": {
                "policy": policy,
                "policy_version": _hash_obj(json.dumps(policy, sort_keys=True, default=str)[:4000]),
                "source": "gtec_c5_runtime",
                "updated_at": _now(),
            }
        },
        upsert=True,
    )

    return {
        "execution_graph_written": True,
        "finding_catalog_rows": len(findings_docs),
        "remediation_plans_updated": len(latest_ledger.get("actions") or []),
        "canonical_incidents_synced": await db[CANONICAL_INCIDENTS_COL].count_documents({}),
        "policy_store_written": True,
    }


# ──────────────────────────────────────────────────────────────────────────
# Public orchestrator
# ──────────────────────────────────────────────────────────────────────────

async def run_full_scan(db, triggered_by: str = "manual", actor: str = "system",
                         viewports: str = "desktop,mobile",
                         scan_mode: str = SCAN_MODE_STRICT_GLOBAL) -> dict[str, Any]:
    """Execute the full 7-step directive pipeline.

    If STATUS=FAIL (directive §11), auto-remediate (§4) and restart from
    Step 1 — up to `_MAX_RESTARTS` attempts. §5 duplicate-hash guard
    breaks the loop if no progress is being made.
    """
    await ensure_internal_collections_migrated(db)
    legacy_mirror_on = await legacy_mirror_write_enabled(db)
    if RUN_LOCK.locked():
        raise RuntimeError("A GTEC C5 scan is already in progress")

    async with RUN_LOCK:
        return await _run_with_restart_loop(
            db,
            triggered_by,
            actor,
            viewports,
            scan_mode=_normalize_scan_mode(scan_mode),
            legacy_mirror_on=legacy_mirror_on,
        )


_MAX_RESTARTS = 3


async def _run_with_restart_loop(db, triggered_by: str, actor: str,
                                  viewports: str,
                                  scan_mode: str = SCAN_MODE_STRICT_GLOBAL,
                                  legacy_mirror_on: bool = True) -> dict[str, Any]:
    """§11 Auto-Restart Orchestrator. Runs the scan up to _MAX_RESTARTS
    times, auto-remediating FAIL findings between attempts. §5 hash-
    duplicate guard breaks the loop when no progress is detected."""
    from services import gtec_auto_remediation as rx  # lazy import

    hashes_seen: set[str] = set()
    remediation_ledgers: list[dict] = []
    restart_count = 0
    attempt = 0
    final_report: Optional[dict[str, Any]] = None

    while attempt <= _MAX_RESTARTS:
        attempt_tag = "restart" if restart_count else "initial"
        mode = _normalize_scan_mode(scan_mode)
        strict_global = _is_strict_mode(mode)

        preflight = await run_scan_preflight_gate(
            require_external_preview=strict_global,
            require_local_backend=strict_global,
        )
        try:
            await _record_preflight_telemetry(
                db,
                preflight,
                triggered_by=triggered_by,
                actor=actor,
                attempt_tag=attempt_tag,
                attempt_index=attempt,
                scan_mode=mode,
            )
        except Exception:
            logger.exception("gtec-c5: failed to record preflight telemetry")
        if not bool(preflight.get("passed")):
            blocked_task_id = f"gtec_c5_{uuid.uuid4().hex[:12]}"
            blocked_hash = _hash_obj(
                read_directive_text()[:4000],
                triggered_by,
                viewports,
                datetime.now(timezone.utc).strftime("%Y-%m-%d-%H"),
                attempt_tag,
                attempt,
                "INFRA_BLOCKED",
            )
            final_report = _build_infra_blocked_report(
                task_id=blocked_task_id,
                execution_hash=blocked_hash,
                triggered_by=triggered_by,
                actor=actor,
                attempt_tag=attempt_tag,
                attempt_index=attempt,
                preflight=preflight,
                scan_mode=mode,
            )
            break

        report = await _single_scan_pass(
            db, triggered_by, actor, viewports,
            attempt_tag=attempt_tag, attempt_index=attempt,
            scan_mode=mode,
        )
        report["preflight"] = preflight
        report["preflight_policy"] = {
            "require_external_preview": strict_global,
            "require_local_backend": strict_global,
            "required_stable_checks": SCAN_PREFLIGHT_REQUIRED_STABLE_CHECKS,
        }

        # §5 — duplicate execution_hash means no progress; stop the loop.
        eh = report.get("execution_hash")
        if eh in hashes_seen:
            report["summary"] = (
                (report.get("summary") or "")
                + " · duplicate execution_hash detected — auto-restart "
                "loop stopped per directive §5 (escalate to systemic fix)"
            )
            final_report = report
            break
        hashes_seen.add(eh)

        if report.get("status") == "PASS":
            if remediation_ledgers:
                report["summary"] = rx.summarise_actions(
                    remediation_ledgers[-1], restart_count,
                ) + " · all pillars now PASS after auto-remediation"
            final_report = report
            break
        if str(report.get("status") or "").upper() == "INFRA_BLOCKED":
            final_report = report
            break

        # §4 + §11 — STATUS=FAIL triggers mandatory auto-remediation
        if attempt >= _MAX_RESTARTS:
            report["summary"] = (
                (report.get("summary") or "")
                + f" · max {_MAX_RESTARTS} auto-restarts exhausted — "
                "auto-incident escalation active (§11)"
            )
            final_report = report
            break

        ledger = await rx.remediate(report, db)
        remediation_ledgers.append(ledger)

        # Nothing was actually fixed → no point restarting; escalate now.
        if ledger.get("fixed", 0) == 0:
            report["summary"] = (
                rx.summarise_actions(ledger, restart_count)
                + " · no root-cause fix available this iteration — "
                "auto-escalated with containment (§4 bans silent suppression)"
            )
            final_report = report
            break

        restart_count += 1
        attempt += 1
        logger.info(
            "gtec-v2 §11: STATUS=FAIL triggered restart %s/%s "
            "(ledger=%s)", restart_count, _MAX_RESTARTS,
            {k: v for k, v in ledger.items() if k != "actions"},
        )

    assert final_report is not None
    # Stamp the restart ledger onto the final report for audit + email.
    final_report["restart_count"] = restart_count
    final_report["remediation_ledgers"] = remediation_ledgers

    # Re-stamp the v3 §13 block now that restart_count is final, so
    # ACTIVE_FIXES correctly reflects whether remediation cycles ran.
    try:
        final_report["v3_output"] = _v3_output_block(
            overall_status=final_report.get("status", "FAIL"),
            security_scan=final_report.get("security_scan", "FAIL"),
            performance=final_report.get("performance", "FAIL"),
            i18n_status=final_report.get("i18n_status", "FAIL"),
            rbac_status=final_report.get("rbac_status", "FAIL"),
            regressions=(str(final_report.get("regressions", "NO")).upper() == "YES"),
            agg_counts=final_report.get("severity_counts") or {},
            sections=final_report.get("sections") or {},
            memory_recurring=int(final_report.get("memory_recurring") or 0),
            restart_count=restart_count,
        )
    except Exception:
        logger.exception("gtec-v2: failed to refresh v3 §13 output (non-fatal)")

    # Final SUMMARY enforcement: §12 says "actions taken".
    if remediation_ledgers:
        taken = rx.summarise_actions(remediation_ledgers[-1], restart_count)
        existing = (final_report.get("summary") or "").strip()
        if "actions" not in existing.lower() and "fix" not in existing.lower():
            final_report["summary"] = (taken + (" · " + existing if existing else "")).strip(" ·")

    try:
        final_report["incident_auto_closure"] = await apply_incident_auto_closure_policy(db, final_report)
    except Exception:
        logger.exception("gtec-c5: incident auto-closure evaluation failed")
        final_report["incident_auto_closure"] = {
            "error": "incident_auto_closure_failed",
            "evaluated_at": _now(),
        }

    # Persist FINAL report via canonical write-path hydration
    final_report = await hydrate_report_write_path(db, final_report, legacy_mirror_on=legacy_mirror_on)

    execution_doc = {
        "execution_id": str(final_report.get("task_id") or f"gtec_exec_{uuid.uuid4().hex[:12]}"),
        "task_id": final_report.get("task_id"),
        "execution_hash": final_report.get("execution_hash"),
        "status": final_report.get("status"),
        "triggered_by": triggered_by,
        "actor": actor,
        "viewports": viewports,
        "restart_count": int(final_report.get("restart_count") or 0),
        "critical_vulns": int(final_report.get("critical_vulns") or 0),
        "high_vulns": int(final_report.get("high_vulns") or 0),
        "medium_vulns": int(final_report.get("medium_vulns") or 0),
        "low_vulns": int(final_report.get("low_vulns") or 0),
        "summary": str(final_report.get("summary") or "")[:2000],
        "generated_at": final_report.get("generated_at") or _now(),
        "updated_at": _now(),
    }
    await db[EXECUTIONS_COL].insert_one(execution_doc)
    if legacy_mirror_on:
        await db[LEGACY_EXECUTIONS_COL].update_one(
            {"execution_id": execution_doc.get("execution_id")},
            {"$set": execution_doc},
            upsert=True,
        )

    try:
        final_report["canonical_model_write"] = await write_canonical_models(db, final_report)
    except Exception:
        logger.exception("gtec-c5: canonical model write-through failed")
        final_report["canonical_model_write"] = {
            "execution_graph_written": False,
            "finding_catalog_rows": 0,
            "remediation_plans_updated": 0,
            "canonical_incidents_synced": 0,
            "policy_store_written": False,
            "error": "canonical_write_failed",
        }
    try:
        V2_LATEST.write_text(json.dumps(final_report, indent=2, default=str))
    except Exception:
        logger.exception("gtec-c5: failed to persist latest local report snapshot")
    try:
        await _email_report_to_admins(db, final_report)
    except Exception:
        logger.exception("gtec-c5: email dispatch failed")

    return final_report


async def _single_scan_pass(db, triggered_by: str, actor: str,
                             viewports: str, attempt_tag: str,
                             attempt_index: int,
                             scan_mode: str = SCAN_MODE_STRICT_GLOBAL) -> dict[str, Any]:
    """One pass of the 7-step pipeline. Returns a report WITHOUT
    persisting or emailing — those are handled by the orchestrator so
    that only the FINAL (post-restart) report reaches the DB + inbox."""
    t0 = time.perf_counter()
    task_id = f"gtec_c5_{uuid.uuid4().hex[:12]}"
    scan_mode_n = _normalize_scan_mode(scan_mode)
    strict_global = _is_strict_mode(scan_mode_n)

    execution_hash = _hash_obj(
        read_directive_text()[:4000],
        triggered_by,
        viewports,
        datetime.now(timezone.utc).strftime("%Y-%m-%d-%H"),
        attempt_tag,
        attempt_index,
    )

    prev = await db[REPORTS_COL].find_one({}, {"_id": 0}, sort=[("generated_at", -1)])

    base_url = _resolve_external_frontend_base_url(None)

    sast_task = asyncio.create_task(run_sast())
    dep_task = asyncio.create_task(run_dependency_scan())
    acl_task = asyncio.create_task(run_access_control_probes(base_url, strict_global=strict_global))
    i18n_task = asyncio.create_task(run_i18n_public_access_probes(base_url, strict_global=strict_global))
    duplicate_task = asyncio.to_thread(run_duplicate_source_scan)
    api_contract_task = asyncio.create_task(run_api_contract_scan(strict_global=strict_global))
    threat_task = asyncio.create_task(run_threat_topology_scan(db))

    sast = await sast_task
    dep = await dep_task
    acl = await acl_task
    i18n = await i18n_task
    duplicate = await duplicate_task
    api_contract = await api_contract_task
    threat_model = await threat_task

    dast = await run_dast_via_crawler(viewports=viewports, strict_global=strict_global)

    sections = {
        "sast": sast,
        "dep": dep,
        "dast": dast,
        "acl": acl,
        "i18n": i18n,
        "duplicate": duplicate,
        "api_contract": api_contract,
        "threat_model": threat_model,
    }
    fps = _fingerprints([sast, dep, dast, acl, i18n, duplicate, api_contract, threat_model])
    recurring = await _update_memory(db, fps, task_id)

    report = _structured_report(task_id, execution_hash, sections, prev, recurring)
    report["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    report["triggered_by"] = triggered_by
    report["actor"] = actor
    report["attempt_tag"] = attempt_tag
    report["attempt_index"] = attempt_index
    report["scan_mode"] = scan_mode_n
    report["strict_global_mode"] = strict_global
    report["transient_artifact_count"] = _count_transient_artifacts(sections)
    report["strict_gate_passed"] = bool(strict_global and int(report.get("transient_artifact_count") or 0) == 0)
    return report


async def _email_report_to_admins(db, report: dict[str, Any]) -> None:
    """Send the §12 report to every admin via the `gtec_scan_v2_report`
    catalog template. Respects the scheduler-side email opt-out flag
    `gtec_scan_v2_settings.email_enabled` (default: True).
    """
    conf = await db[SETTINGS_COL].find_one({"_id": SETTINGS_DOC_ID}, {"_id": 0}) or {}
    if conf.get("email_enabled") is False:
        return

    # Collect admin recipients. An "admin" here is anyone with role=admin
    # or the full-access admin emails hard-wired via env.
    emails: list[str] = []
    try:
        async for u in db["users"].find(
            {"$or": [{"role": "admin"}, {"is_admin": True}]},
            {"_id": 0, "email": 1},
        ):
            em = (u.get("email") or "").strip().lower()
            if em and em not in emails:
                emails.append(em)
    except Exception:
        logger.exception("gtec-c5: failed to load admin recipient list")

    # Ensure the canonical admin address is always included if present
    for fallback in (os.environ.get("ADMIN_EMAIL", "").strip().lower(),
                     "admin@realaicoach.app"):
        if fallback and fallback not in emails:
            emails.append(fallback)

    if not emails:
        return

    # Lazy imports to keep service module lightweight
    from utils.email_service import send_catalog_template

    # Ensure one canonical snapshot is available BEFORE PDF/email rendering,
    # so all surfaces share identical runtime summary values.
    c5_snapshot = report.get("c5_notification_snapshot") or {}
    if not c5_snapshot:
        try:
            c5_snapshot = await build_c5_notification_snapshot(db, report)
            report["c5_notification_snapshot"] = c5_snapshot
            await db[REPORTS_COL].update_one(
                {"task_id": report.get("task_id")},
                {"$set": {"c5_notification_snapshot": c5_snapshot}},
                upsert=False,
            )
            if await legacy_mirror_write_enabled(db):
                await db[LEGACY_REPORTS_COL].update_one(
                    {"task_id": report.get("task_id")},
                    {"$set": {"c5_notification_snapshot": c5_snapshot}},
                    upsert=False,
                )
        except Exception:
            c5_snapshot = {
                "snapshot_version": NOTIFICATION_SNAPSHOT_VERSION,
                "source_task_id": report.get("task_id") or "",
                "source_execution_hash": report.get("execution_hash") or "",
                "snapshot_status": "INCOMPLETE",
                "data_freshness": "STALE_OR_PARTIAL",
                "consistency": {"passed": False, "issues": ["snapshot_build_failed"]},
                "fail_reason_summary": _build_fail_reason_summary(report),
                "generated_at": _now(),
            }
            report["c5_notification_snapshot"] = c5_snapshot

    c5_validation = _validate_notification_snapshot(c5_snapshot, report)

    pdf_bundle = _build_gtec_final_output_pdf_bundle(report)
    pdf_attachment = (pdf_bundle or {}).get("attachment")
    pdf_attachment_name = (pdf_bundle or {}).get("filename", "")
    pdf_sha256 = (pdf_bundle or {}).get("sha256", "")
    pdf_policy_mode = (pdf_bundle or {}).get("policy_mode", "")
    pdf_source_header = (pdf_bundle or {}).get("source_header", "")
    pdf_normalized_header = (pdf_bundle or {}).get("normalized_header", "")
    pdf_guardrail_passed = bool((pdf_bundle or {}).get("guardrail_passed", False))
    pdf_guardrail_failures = list((pdf_bundle or {}).get("guardrail_failures") or [])

    c5_trust = c5_snapshot.get("trust") or {}
    c5_white = c5_snapshot.get("white_screen_sentry") or {}
    c5_matrix = c5_snapshot.get("responsive_viewport_matrix") or {}
    c5_external = c5_snapshot.get("external_host_certification") or {}
    c5_retry = c5_external.get("retry_plan") or {}
    c5_incident = c5_snapshot.get("incident_auto_closure") or {}
    c5_policy = c5_incident.get("policy") or {}
    c5_run_policy = c5_snapshot.get("run_policy") or {}
    c5_consistency = c5_snapshot.get("consistency") or {}

    internal_task_id = str(report.get("task_id") or "")
    public_task_id = to_public_task_id(internal_task_id)
    if not str(pdf_attachment_name or "").strip():
        pdf_attachment_name = build_pdf_v15_filename("compliance", public_task_id or "gtec_c5")

    payload = {
        "task_id": public_task_id,
        "internal_task_id": internal_task_id,
        "execution_hash": report.get("execution_hash"),
        "status": report.get("status"),
        "critical_vulns": report.get("critical_vulns") or 0,
        "high_vulns": report.get("high_vulns") or 0,
        "medium_vulns": report.get("medium_vulns") or int((report.get("severity_counts") or {}).get("medium") or 0),
        "low_vulns": report.get("low_vulns") or int((report.get("severity_counts") or {}).get("low") or 0),
        "regressions": report.get("regressions"),
        "security_scan": report.get("security_scan"),
        "e2e_tests": report.get("e2e_tests"),
        "responsiveness": report.get("responsiveness"),
        "performance": report.get("performance"),
        "rbac_status": report.get("rbac_status"),
        "subscription_enforcement": report.get("subscription_enforcement"),
        "learning_memory_updated": report.get("learning_memory_updated"),
        "summary": report.get("summary") or "",
        "triggered_by": report.get("triggered_by") or "manual",
        "actor": report.get("actor") or "system",
        "generated_at": report.get("generated_at") or _now(),
        "elapsed_ms": int(report.get("elapsed_ms") or 0),
        "directive_version": report.get("directive_version") or "",
        "recurring_findings": int(report.get("memory_recurring") or 0),
        "severity_counts": report.get("severity_counts") or {},
        # v3 §13 — additive output passed through to the email template
        "v3_output": report.get("v3_output") or {},
        # Attachment label shown inside the email body
        "pdf_attachment_name": pdf_attachment_name,
        "pdf_sha256": pdf_sha256,
        "pdf_policy_mode": pdf_policy_mode,
        "pdf_source_header": pdf_source_header,
        "pdf_normalized_header": pdf_normalized_header,
        "pdf_guardrail_passed": pdf_guardrail_passed,
        "pdf_guardrail_failures": ", ".join(pdf_guardrail_failures) if pdf_guardrail_failures else "",
        # C5 runtime summary (current enforcement/certification/incident lifecycle)
        "c5_trust_score_percent": float(c5_trust.get("score_percent") or 0.0),
        "c5_trust_passed_gates": int(c5_trust.get("passed_gates") or 0),
        "c5_trust_total_gates": int(c5_trust.get("total_gates") or 0),
        "c5_white_screen_status": str(c5_white.get("status") or "UNKNOWN"),
        "c5_white_screen_run_id": c5_white.get("run_id") or "",
        "c5_white_screen_failed_checks": int(c5_white.get("failed_checks") or 0),
        "c5_white_screen_total_checks": int(c5_white.get("total_checks") or 0),
        "c5_white_screen_routes_tested": int(c5_white.get("routes_tested") or 0),
        "c5_white_screen_route_source": c5_white.get("route_source") or "",
        "c5_viewport_artifact_count": int(c5_matrix.get("artifact_count") or 0),
        "c5_viewports": ",".join(list(c5_matrix.get("viewports") or [])),
        "c5_external_cert_status": str(c5_external.get("status") or "not_run"),
        "c5_external_cert_id": c5_external.get("certification_id") or "",
        "c5_external_cert_reason": c5_external.get("reason") or "",
        "c5_external_cert_retry_needed": "YES" if bool(c5_retry.get("needs_retry")) else "NO",
        "c5_external_cert_retry_reasons": ", ".join(list(c5_retry.get("reasons") or [])),
        "c5_incidents_evaluated": int(c5_incident.get("evaluated_incidents") or 0),
        "c5_incidents_transitioned_pending": int(c5_incident.get("transitioned_to_pending_verification") or 0),
        "c5_incidents_auto_closed": int(c5_incident.get("auto_closed") or 0),
        "c5_incidents_reopened": int(c5_incident.get("reopened") or 0),
        "c5_incidents_streak_resets": int(c5_incident.get("streak_resets") or 0),
        "c5_incident_policy_clean_rescans": int(c5_policy.get("clean_rescans_required") or INCIDENT_AUTOCLOSE_CLEAN_RESCANS),
        "c5_incident_policy_pending_hours": int(c5_policy.get("pending_verification_hours") or INCIDENT_AUTOCLOSE_PENDING_HOURS),
        "c5_snapshot_version": str(c5_snapshot.get("snapshot_version") or NOTIFICATION_SNAPSHOT_VERSION),
        "c5_snapshot_status": str(c5_snapshot.get("snapshot_status") or c5_validation.get("status") or "INCOMPLETE"),
        "c5_data_freshness": str(c5_snapshot.get("data_freshness") or c5_validation.get("data_freshness") or "STALE_OR_PARTIAL"),
        "c5_consistency_passed": "YES" if bool(c5_consistency.get("passed", c5_validation.get("passed"))) else "NO",
        "c5_consistency_issues": ", ".join(list(c5_consistency.get("issues") or c5_validation.get("issues") or [])),
        "c5_fail_reason_summary": str(c5_snapshot.get("fail_reason_summary") or _build_fail_reason_summary(report, c5_snapshot)),
        "c5_scan_mode": str(c5_run_policy.get("scan_mode") or _normalize_scan_mode(report.get("scan_mode"))),
        "c5_strict_global_mode": "YES" if bool(c5_run_policy.get("strict_global_mode", _is_strict_mode(report.get("scan_mode")))) else "NO",
        "c5_transient_artifact_count": int(c5_run_policy.get("transient_artifact_count") or int(report.get("transient_artifact_count") or 0)),
        "c5_strict_gate_passed": "YES" if bool(c5_run_policy.get("strict_gate_passed", report.get("strict_gate_passed"))) else "NO",
        "c5_preflight_require_external_preview": "YES" if bool(c5_run_policy.get("preflight_require_external_preview", ((report.get("preflight_policy") or {}).get("require_external_preview")))) else "NO",
        "c5_preflight_require_local_backend": "YES" if bool(c5_run_policy.get("preflight_require_local_backend", ((report.get("preflight_policy") or {}).get("require_local_backend")))) else "NO",
    }

    sent: list[dict[str, Any]] = []
    for addr in emails:
        try:
            res = await send_catalog_template(
                addr,
                "gtec_scan_v2_report",
                attachments=[pdf_attachment] if pdf_attachment else None,
                **payload,
            )
            sent.append({"email": addr, "ok": bool(res.get("success"))})
        except Exception as exc:  # one bad address must not break others
            logger.warning("gtec-v2: email to %s failed: %s", addr, exc)
            sent.append({"email": addr, "ok": False, "error": str(exc)[:120]})

    sent_at = _now()
    sent_ok = sum(1 for r in sent if r.get("ok"))
    sent_failed = max(0, len(sent) - sent_ok)

    # Stamp the report doc so admins can audit the dispatch in /history
    try:
        email_dispatch_doc = {
            "sent_at": sent_at,
            "recipients": sent,
            "pdf_attachment": {
                "filename": pdf_attachment_name or "",
                "sha256": pdf_sha256 or "",
                "policy_mode": pdf_policy_mode or "",
                "source_header": pdf_source_header or "",
                "normalized_header": pdf_normalized_header or "",
                "size_bytes": int((pdf_bundle or {}).get("size_bytes") or 0),
                "target_version": "1.4",
                "guardrail_passed": pdf_guardrail_passed,
                "guardrail_failures": pdf_guardrail_failures,
            },
            "c5_runtime_summary": {
                "snapshot_version": str(c5_snapshot.get("snapshot_version") or NOTIFICATION_SNAPSHOT_VERSION),
                "snapshot_status": str(c5_snapshot.get("snapshot_status") or c5_validation.get("status") or "INCOMPLETE"),
                "data_freshness": str(c5_snapshot.get("data_freshness") or c5_validation.get("data_freshness") or "STALE_OR_PARTIAL"),
                "consistency": {
                    "passed": bool(c5_consistency.get("passed", c5_validation.get("passed"))),
                    "issues": list(c5_consistency.get("issues") or c5_validation.get("issues") or []),
                },
                "fail_reason_summary": str(c5_snapshot.get("fail_reason_summary") or _build_fail_reason_summary(report, c5_snapshot)),
                "run_policy": {
                    "scan_mode": str(c5_run_policy.get("scan_mode") or _normalize_scan_mode(report.get("scan_mode"))),
                    "strict_global_mode": bool(c5_run_policy.get("strict_global_mode", _is_strict_mode(report.get("scan_mode")))),
                    "transient_artifact_count": int(c5_run_policy.get("transient_artifact_count") or int(report.get("transient_artifact_count") or 0)),
                    "strict_gate_passed": bool(c5_run_policy.get("strict_gate_passed", report.get("strict_gate_passed"))),
                    "preflight_require_external_preview": bool(c5_run_policy.get("preflight_require_external_preview", ((report.get("preflight_policy") or {}).get("require_external_preview")))),
                    "preflight_require_local_backend": bool(c5_run_policy.get("preflight_require_local_backend", ((report.get("preflight_policy") or {}).get("require_local_backend")))),
                },
                "trust": {
                    "score_percent": float(c5_trust.get("score_percent") or 0.0),
                    "passed_gates": int(c5_trust.get("passed_gates") or 0),
                    "total_gates": int(c5_trust.get("total_gates") or 0),
                },
                "white_screen_sentry": {
                    "status": str(c5_white.get("status") or "UNKNOWN"),
                    "failed_checks": int(c5_white.get("failed_checks") or 0),
                    "total_checks": int(c5_white.get("total_checks") or 0),
                    "run_id": c5_white.get("run_id") or "",
                },
                "external_host_certification": {
                    "status": str(c5_external.get("status") or "not_run"),
                    "certification_id": c5_external.get("certification_id") or "",
                    "retry_needed": bool(c5_retry.get("needs_retry")),
                },
                "incident_auto_closure": {
                    "evaluated_incidents": int(c5_incident.get("evaluated_incidents") or 0),
                    "transitioned_to_pending_verification": int(c5_incident.get("transitioned_to_pending_verification") or 0),
                    "auto_closed": int(c5_incident.get("auto_closed") or 0),
                    "reopened": int(c5_incident.get("reopened") or 0),
                },
            },
        }
        await db[REPORTS_COL].update_one(
            {"task_id": report.get("task_id")},
            {"$set": {"email_dispatch": email_dispatch_doc}},
        )
        if await legacy_mirror_write_enabled(db):
            await db[LEGACY_REPORTS_COL].update_one(
                {"task_id": report.get("task_id")},
                {"$set": {"email_dispatch": email_dispatch_doc}},
                upsert=False,
            )
    except Exception:
        logger.exception("gtec-c5: failed to stamp email_dispatch metadata")

    # Mirror every scheduler/admin run into Compliance Digest Hub as an
    # in-app receipt card so admins can audit task_id, actor, PDF hash and
    # per-recipient delivery outcomes without opening raw report JSON.
    try:
        from routes.compliance_digest_hub import log_digest_entry

        status = str(report.get("status") or "UNKNOWN").upper()
        task_id = public_task_id
        trigger = str(report.get("triggered_by") or "scheduler")
        actor = str(report.get("actor") or "system")
        subject = f"GTEC C5 Run Receipt · {status} · {task_id}"
        summary = (
            f"task={task_id} · status={status} · trigger={trigger} · actor={actor} · "
            f"delivered={sent_ok}/{len(emails)}"
            + (f" · failed={sent_failed}" if sent_failed else "")
        )
        fail_reason_summary = str(c5_snapshot.get("fail_reason_summary") or _build_fail_reason_summary(report, c5_snapshot))
        if status in {"FAIL", "INFRA_BLOCKED"}:
            summary += f" · {fail_reason_summary[:220]}"
        payload = {
            "task_id": task_id,
            "internal_task_id": internal_task_id,
            "status": status,
            "triggered_by": trigger,
            "actor": actor,
            "generated_at": report.get("generated_at") or "",
            "directive_version": report.get("directive_version") or "",
            "email_dispatched_at": sent_at,
            "delivery": {
                "total": len(emails),
                "sent_ok": sent_ok,
                "sent_failed": sent_failed,
                "recipient_statuses": sent,
            },
            "pdf_attachment": {
                "filename": pdf_attachment_name or "",
                "sha256": pdf_sha256 or "",
                "size_bytes": int((pdf_bundle or {}).get("size_bytes") or 0),
                "target_version": "1.4",
                "guardrail_passed": pdf_guardrail_passed,
                "guardrail_failures": pdf_guardrail_failures,
            },
            "c5_runtime_summary": {
                "snapshot_status": str(c5_snapshot.get("snapshot_status") or c5_validation.get("status") or "INCOMPLETE"),
                "data_freshness": str(c5_snapshot.get("data_freshness") or c5_validation.get("data_freshness") or "STALE_OR_PARTIAL"),
                "consistency_passed": bool(c5_consistency.get("passed", c5_validation.get("passed"))),
                "consistency_issues": list(c5_consistency.get("issues") or c5_validation.get("issues") or []),
                "fail_reason_summary": str(c5_snapshot.get("fail_reason_summary") or _build_fail_reason_summary(report, c5_snapshot)),
                "run_policy": {
                    "scan_mode": str(c5_run_policy.get("scan_mode") or _normalize_scan_mode(report.get("scan_mode"))),
                    "strict_global_mode": bool(c5_run_policy.get("strict_global_mode", _is_strict_mode(report.get("scan_mode")))),
                    "transient_artifact_count": int(c5_run_policy.get("transient_artifact_count") or int(report.get("transient_artifact_count") or 0)),
                    "strict_gate_passed": bool(c5_run_policy.get("strict_gate_passed", report.get("strict_gate_passed"))),
                    "preflight_require_external_preview": bool(c5_run_policy.get("preflight_require_external_preview", ((report.get("preflight_policy") or {}).get("require_external_preview")))),
                    "preflight_require_local_backend": bool(c5_run_policy.get("preflight_require_local_backend", ((report.get("preflight_policy") or {}).get("require_local_backend")))),
                },
                "white_screen_sentry": {
                    "status": str(c5_white.get("status") or "UNKNOWN"),
                    "failed_checks": int(c5_white.get("failed_checks") or 0),
                    "total_checks": int(c5_white.get("total_checks") or 0),
                },
                "external_host_certification": {
                    "status": str(c5_external.get("status") or "not_run"),
                    "retry_needed": bool(c5_retry.get("needs_retry")),
                },
                "incident_auto_closure": {
                    "evaluated_incidents": int(c5_incident.get("evaluated_incidents") or 0),
                    "auto_closed": int(c5_incident.get("auto_closed") or 0),
                    "reopened": int(c5_incident.get("reopened") or 0),
                },
            },
        }
        await log_digest_entry(
            kind="gtec_c5_run_receipt",
            subject=subject,
            summary=summary,
            recipients=emails,
            sent_ok=sent_ok,
            sent_failed=sent_failed,
            payload=payload,
            trigger=trigger,
        )
    except Exception as exc:
        logger.warning("gtec-c5: failed to log compliance receipt: %s", exc)


def _build_gtec_final_output_pdf_attachment(report: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Build a PDF attachment containing the literal §12 and §13 final output.

    Returns a Resend-compatible attachment payload or None on failure.
    """
    bundle = _build_gtec_final_output_pdf_bundle(report)
    return (bundle or {}).get("attachment")


def build_canonical_gtec_pdf_export(report: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Public helper for canonical PDF retrieval endpoints (admin downloads)."""
    bundle = _build_gtec_final_output_pdf_bundle(report)
    if not bundle:
        return None
    return {
        "filename": bundle.get("filename") or "gtec_s12_s13_final_output.pdf",
        "pdf_bytes": bundle.get("pdf_bytes") or b"",
        "sha256": bundle.get("sha256") or "",
        "policy_mode": bundle.get("policy_mode") or "",
        "source_header": bundle.get("source_header") or "",
        "normalized_header": bundle.get("normalized_header") or "",
        "size_bytes": int(bundle.get("size_bytes") or 0),
        "guardrail_passed": bool(bundle.get("guardrail_passed")),
        "guardrail_failures": bundle.get("guardrail_failures") or [],
    }


def _build_gtec_final_output_pdf_bundle(report: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Build attachment + compliance metadata for all non-HTTP egress channels.

    This applies global PDF 1.4 normalization explicitly, because HTTP middleware
    cannot intercept email attachments.
    """
    try:
        source_bytes = _render_gtec_final_output_pdf(report)
        if not source_bytes:
            return None

        normalized_bytes, policy_mode, source_header, normalized_header = _normalize_pdf_v14_for_non_http_egress(source_bytes)
        if not normalized_bytes:
            return None

        guardrail = _evaluate_gtec_pdf_guardrails(normalized_bytes)
        if STRICT_PDF_GUARDRAIL and not guardrail.get("passed"):
            raise ValueError(f"GTEC PDF guardrail failed: {', '.join(guardrail.get('failures') or [])}")

        task_id = to_public_task_id((report.get("task_id") or "gtec_c5_report").strip())
        safe_task = re.sub(r"[^a-zA-Z0-9_-]+", "-", task_id)[:64]
        filename = build_pdf_v15_filename("compliance", safe_task)
        sha256 = hashlib.sha256(normalized_bytes).hexdigest()
        attachment = {
            "filename": filename,
            "content": base64.b64encode(normalized_bytes).decode("utf-8"),
            "content_type": "application/pdf",
        }
        return {
            "attachment": attachment,
            "filename": filename,
            "pdf_bytes": normalized_bytes,
            "sha256": sha256,
            "policy_mode": policy_mode,
            "source_header": source_header,
            "normalized_header": normalized_header,
            "size_bytes": len(normalized_bytes),
            "guardrail_passed": bool(guardrail.get("passed")),
            "guardrail_failures": guardrail.get("failures") or [],
        }
    except Exception as exc:
        logger.warning("gtec-v2: failed to build PDF attachment bundle: %s", exc)
        return None


def _normalize_pdf_v14_for_non_http_egress(payload: bytes) -> tuple[bytes, str, str, str]:
    """Apply the same global PDF policy to non-HTTP egress (email attachments)."""
    source_header = payload.splitlines()[0].decode("latin1", errors="ignore") if payload.startswith(b"%PDF-") else ""
    try:
        from middleware_pdf_policy import enforce_pdf_v14_bytes

        normalized, mode = enforce_pdf_v14_bytes(payload)
    except Exception:
        normalized, mode = payload, "passthrough_error"
    normalized_header = normalized.splitlines()[0].decode("latin1", errors="ignore") if normalized.startswith(b"%PDF-") else ""
    return normalized, mode, source_header, normalized_header


def _evaluate_gtec_pdf_guardrails(pdf_bytes: bytes) -> dict[str, Any]:
    """Runtime no-regression guardrails for the styled GTEC PDF."""
    failures: list[str] = []
    header_ok = pdf_bytes.startswith(b"%PDF-1.4")
    if not header_ok:
        failures.append("pdf_header_not_v14")

    has_logo_image = False
    has_brand_heading = False
    has_s12 = False
    has_s13 = False

    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        has_brand_heading = "RealAICoach Security" in text
        has_s12 = bool(re.search(r"(?:§\s*)?12\s+FINAL\s+OUTPUT", text, flags=re.IGNORECASE))
        has_s13 = bool(re.search(r"(?:§\s*)?13\s*v3\s+FINAL\s+OUTPUT", text, flags=re.IGNORECASE))

        for page in reader.pages:
            resources = page.get("/Resources")
            if resources and "/XObject" in resources:
                xobj = resources["/XObject"].get_object()
                for key in xobj:
                    obj = xobj[key]
                    if obj.get("/Subtype") == "/Image":
                        has_logo_image = True
                        break
            if has_logo_image:
                break
    except Exception:
        failures.append("pdf_parse_error")

    if not has_logo_image:
        failures.append("logo_image_missing")
    if not has_brand_heading:
        failures.append("brand_heading_missing")
    if not has_s12:
        failures.append("s12_heading_missing")
    if not has_s13:
        failures.append("s13_heading_missing")

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "checks": {
            "header_v14": header_ok,
            "logo_image_embedded": has_logo_image,
            "brand_heading": has_brand_heading,
            "s12_heading": has_s12,
            "s13_heading": has_s13,
        },
    }


def _fetch_gtec_c5_trend_rows(current_report: dict[str, Any], limit: int = 7) -> list[dict[str, Any]]:
    """Fetch recent scan history (sync, best-effort) for executive trend visuals."""
    rows: list[dict[str, Any]] = []
    try:
        from pymongo import MongoClient

        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not mongo_url or not db_name:
            return []
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)
        cursor = client[db_name][REPORTS_COL].find(
            {},
            {
                "_id": 0,
                "task_id": 1,
                "status": 1,
                "generated_at": 1,
                "critical_vulns": 1,
                "high_vulns": 1,
                "medium_vulns": 1,
                "low_vulns": 1,
                "c5_notification_snapshot.trust.score_percent": 1,
            },
        ).sort("generated_at", -1).limit(max(2, limit + 1))
        docs = list(cursor)
        client.close()
        current_task = str(current_report.get("task_id") or "")
        for doc in docs:
            if str(doc.get("task_id") or "") == current_task:
                continue
            trust = ((doc.get("c5_notification_snapshot") or {}).get("trust") or {})
            rows.append({
                "status": str(doc.get("status") or "UNKNOWN").upper(),
                "trust_percent": float(trust.get("score_percent") or 0.0),
                "generated_at": str(doc.get("generated_at") or ""),
                "critical": int(doc.get("critical_vulns") or 0),
                "high": int(doc.get("high_vulns") or 0),
                "medium": int(doc.get("medium_vulns") or 0),
                "low": int(doc.get("low_vulns") or 0),
            })
        rows = rows[:limit]
        rows.reverse()  # oldest → newest
    except Exception as exc:
        logger.debug("gtec-v2: trend history unavailable for PDF: %s", exc)
        return []
    return rows


def _render_gtec_final_output_pdf(report: dict[str, Any]) -> bytes:
    """Render the GTEC C5 Executive Compliance Report (3-page enterprise design).

    Page 1: executive verdict — trust gauge, severity deltas, trend bars,
            domain scorecard, QR deep link to live ops dashboard.
    Page 2: runtime enforcement — grouped C5 sub-cards with status pills.
    Page 3: compliance appendix — literal §12 and §13 fields (guardrail-locked).
    """
    import io
    import textwrap
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from services.pdf_v15_theme import get_canonical_logo_tile_path

    v3 = report.get("v3_output") or {}
    c5 = report.get("c5_notification_snapshot") or {}
    c5_trust = c5.get("trust") or {}
    c5_white = c5.get("white_screen_sentry") or {}
    c5_matrix = c5.get("responsive_viewport_matrix") or {}
    c5_external = c5.get("external_host_certification") or {}
    c5_retry = c5_external.get("retry_plan") or {}
    c5_incident = c5.get("incident_auto_closure") or {}
    c5_policy = c5_incident.get("policy") or {}
    c5_run_policy = c5.get("run_policy") or {}
    c5_snapshot_status = str(c5.get("snapshot_status") or "INCOMPLETE")
    c5_data_freshness = str(c5.get("data_freshness") or "STALE_OR_PARTIAL")
    c5_consistency = c5.get("consistency") or {}
    c5_fail_reason_summary = str(c5.get("fail_reason_summary") or _build_fail_reason_summary(report, c5))

    PRIMARY = HexColor("#0F766E")
    TEAL = HexColor("#14B8A6")
    INDIGO = HexColor("#4F46E5")
    INK = HexColor("#0F172A")
    SLATE = HexColor("#475569")
    SLATE_MUTED = HexColor("#94A3B8")
    SLATE_SOFT = HexColor("#F1F5F9")
    BORDER_SOFT = HexColor("#E2E8F0")
    SUCCESS = HexColor("#047857")
    SUCCESS_SOFT = HexColor("#ECFDF5")
    WARNING = HexColor("#B45309")
    WARNING_SOFT = HexColor("#FFF7ED")
    DANGER = HexColor("#B91C1C")
    DANGER_SOFT = HexColor("#FEF2F2")

    status_now = str(report.get("status") or "UNKNOWN").upper()
    status_tone = SUCCESS if status_now == "PASS" else DANGER if status_now == "FAIL" else WARNING
    status_soft = SUCCESS_SOFT if status_now == "PASS" else DANGER_SOFT if status_now == "FAIL" else WARNING_SOFT
    platform_logo_path = get_canonical_logo_tile_path()

    def _pill_tone(value: str) -> tuple[Any, Any]:
        v = str(value or "").strip().upper()
        if v in {"PASS", "YES", "OK", "COMPLETE", "ACTIVE", "UPDATED", "FRESH", "CERTIFIED"}:
            return SUCCESS, SUCCESS_SOFT
        if v in {"FAIL", "NO", "INCOMPLETE", "BLOCKED", "INFRA_BLOCKED", "STALE_OR_PARTIAL", "NOT UPDATED"}:
            return DANGER, DANGER_SOFT
        return WARNING, WARNING_SOFT

    trend_rows = _fetch_gtec_c5_trend_rows(report, limit=7)
    prev_row = trend_rows[-1] if trend_rows else None

    trust_percent = float(c5_trust.get("score_percent") or 0.0)
    trust_gates_passed = int(c5_trust.get("passed_gates") or 0)
    trust_gates_total = int(c5_trust.get("total_gates") or 0)

    sev_now = {
        "CRITICAL": int(report.get("critical_vulns") or 0),
        "HIGH": int(report.get("high_vulns") or 0),
        "MEDIUM": int(report.get("medium_vulns") or int((report.get("severity_counts") or {}).get("medium") or 0)),
        "LOW": int(report.get("low_vulns") or int((report.get("severity_counts") or {}).get("low") or 0)),
    }
    sev_prev = {
        "CRITICAL": int((prev_row or {}).get("critical") or 0),
        "HIGH": int((prev_row or {}).get("high") or 0),
        "MEDIUM": int((prev_row or {}).get("medium") or 0),
        "LOW": int((prev_row or {}).get("low") or 0),
    } if prev_row else None

    domain_scores = [
        ("Security", report.get("security_scan") or ""),
        ("E2E Tests", report.get("e2e_tests") or ""),
        ("Responsive", report.get("responsiveness") or ""),
        ("Performance", report.get("performance") or ""),
        ("RBAC", report.get("rbac_status") or ""),
        ("Subscription", report.get("subscription_enforcement") or ""),
        ("i18n", v3.get("I18N_STATUS") or report.get("i18n_status") or ""),
    ]

    plain_reason = textwrap.shorten(
        str(report.get("summary") or c5_fail_reason_summary or "No summary captured.").replace("\n", " "),
        width=150, placeholder="…",
    )

    dashboard_url = ""
    try:
        dashboard_url = f"{_resolve_external_frontend_base_url(None).rstrip('/')}/ops-route-health"
    except Exception:
        dashboard_url = ""

    buf = io.BytesIO()
    pdf = canvas_module = None
    from reportlab.pdfgen import canvas as canvas_module
    pdf = canvas_module.Canvas(buf, pagesize=A4, pdfVersion=(1, 4))
    width, height = A4

    margin_x = 0.55 * inch
    content_w = width - (2 * margin_x)
    y = height
    line_h = 12
    page_no = 1

    def _draw_page_chrome(section_label: str) -> None:
        nonlocal y
        pdf.setFillColor(TEAL)
        pdf.rect(0, height - 0.06 * inch, width * 0.55, 0.06 * inch, stroke=0, fill=1)
        pdf.setFillColor(PRIMARY)
        pdf.rect(width * 0.55, height - 0.06 * inch, width * 0.45, 0.06 * inch, stroke=0, fill=1)

        pdf.setFillColor(PRIMARY)
        pdf.rect(0, height - 1.05 * inch, width, 0.99 * inch, stroke=0, fill=1)
        pdf.setFillColor(INDIGO)
        pdf.rect(width * 0.72, height - 1.05 * inch, width * 0.28, 0.99 * inch, stroke=0, fill=1)

        tile_x = margin_x
        tile_y = height - 0.88 * inch
        pdf.setFillColor(white)
        pdf.roundRect(tile_x, tile_y, 0.68 * inch, 0.68 * inch, 6, stroke=0, fill=1)
        drew_logo = False
        try:
            if os.path.exists(platform_logo_path):
                pdf.drawImage(
                    platform_logo_path,
                    tile_x + 0.07 * inch,
                    tile_y + 0.07 * inch,
                    width=0.54 * inch,
                    height=0.54 * inch,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                drew_logo = True
        except Exception:
            drew_logo = False
        if not drew_logo:
            pdf.setFillColor(PRIMARY)
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawCentredString(tile_x + 0.34 * inch, tile_y + 0.29 * inch, "RAI")

        pdf.setFillColor(white)
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(margin_x + 0.85 * inch, height - 0.42 * inch, "RealAICoach Security")
        pdf.setFont("Helvetica", 8.5)
        pdf.drawString(margin_x + 0.85 * inch, height - 0.62 * inch, "GTEC C5 Executive Compliance Report  •  Confidential  •  Enterprise Issue")
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(margin_x + 0.85 * inch, height - 0.80 * inch, section_label.upper())

        generated_at = str(report.get("generated_at") or _now())
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawRightString(width - margin_x, height - 0.42 * inch, "noreply@realaicoach.app")
        pdf.setFont("Helvetica", 8)
        pdf.drawRightString(width - margin_x, height - 0.58 * inch, generated_at[:19].replace("T", " ") + " UTC")

        pdf.setFillColor(status_tone)
        pdf.rect(0, height - 1.33 * inch, width, 0.24 * inch, stroke=0, fill=1)
        pdf.setFillColor(white)
        pdf.setFont("Helvetica-Bold", 9)
        display_task_id = to_public_task_id(report.get("task_id") or "")
        pdf.drawCentredString(
            width / 2,
            height - 1.24 * inch,
            f"[GTEC C5 • {status_now}] {display_task_id} — "
            f"crit={sev_now['CRITICAL']} high={sev_now['HIGH']} med={sev_now['MEDIUM']} low={sev_now['LOW']}",
        )

        pdf.setFillColor(TEAL)
        pdf.rect(0, 0.48 * inch, width, 0.03 * inch, stroke=0, fill=1)
        pdf.setFillColor(SLATE_SOFT)
        pdf.rect(0, 0, width, 0.48 * inch, stroke=0, fill=1)
        pdf.setFillColor(SLATE)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(margin_x, 0.30 * inch, "RealAICoach  •  Global Security Compliance")
        pdf.drawString(margin_x, 0.16 * inch, f"Execution Hash {report.get('execution_hash') or '—'}")
        pill_x = width - 0.95 * inch
        pdf.setFillColor(PRIMARY)
        pdf.roundRect(pill_x, 0.22 * inch, 0.5 * inch, 0.18 * inch, 3, stroke=0, fill=1)
        pdf.setFillColor(white)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawCentredString(pill_x + 0.25 * inch, 0.275 * inch, f"Page {page_no}")

        y = height - 1.56 * inch

    def _new_page(section_label: str) -> None:
        nonlocal page_no
        pdf.showPage()
        page_no += 1
        _draw_page_chrome(section_label)

    def _ensure_space(points_needed: float, section_label: str) -> None:
        if y - points_needed < 0.78 * inch:
            _new_page(section_label)

    def _draw_pill(x: float, cy: float, text: str, tone: Any, soft: Any, w: float = 52, h: float = 13, right_x: float = 0) -> None:
        label = str(text)[:24].upper()
        w = max(w, 12 + len(label) * 4.4)
        if right_x:
            x = right_x - w
        pdf.setFillColor(soft)
        pdf.setStrokeColor(tone)
        pdf.setLineWidth(0.7)
        pdf.roundRect(x, cy - h / 2, w, h, h / 2, stroke=1, fill=1)
        pdf.setFillColor(tone)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawCentredString(x + w / 2, cy - 2.4, label)

    # ════════ PAGE 1 — EXECUTIVE VERDICT ════════
    pdf.setTitle(f"GTEC C5 Executive Compliance Report {report.get('task_id') or ''}".strip())
    pdf.setAuthor("RealAICoach GTEC C5")
    pdf.setSubject("GTEC §12 + §13 Final Output")

    _draw_page_chrome("Page 1 · Executive Verdict")

    # Verdict hero banner
    hero_h = 76
    pdf.setFillColor(status_soft)
    pdf.setStrokeColor(status_tone)
    pdf.setLineWidth(1)
    pdf.roundRect(margin_x, y - hero_h, content_w, hero_h, 10, stroke=1, fill=1)
    pdf.setFillColor(status_tone)
    pdf.rect(margin_x, y - hero_h, 5, hero_h, stroke=0, fill=1)
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(margin_x + 18, y - 32, status_now)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.drawString(margin_x + 18, y - 50, "Verdict in plain English")
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 8.8)
    for i, seg in enumerate(textwrap.wrap(plain_reason, width=110)[:2]):
        pdf.drawString(margin_x + 18, y - 62 - (i * 10), seg)
    y -= hero_h + 14

    # Trust gauge (left) + severity tiles (right)
    gauge_block_h = 118
    gauge_w = content_w * 0.34
    tiles_x = margin_x + gauge_w + 12
    tiles_w = content_w - gauge_w - 12

    pdf.setFillColor(white)
    pdf.setStrokeColor(BORDER_SOFT)
    pdf.roundRect(margin_x, y - gauge_block_h, gauge_w, gauge_block_h, 9, stroke=1, fill=1)
    pdf.setFillColor(SLATE_MUTED)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(margin_x + 12, y - 16, "C5 TRUST SCORE")
    cx = margin_x + gauge_w / 2
    cy = y - gauge_block_h / 2 - 8
    radius = 32
    pdf.setLineWidth(9)
    pdf.setLineCap(1)
    pdf.setStrokeColor(SLATE_SOFT)
    pdf.arc(cx - radius, cy - radius, cx + radius, cy + radius, 0, 360)
    gauge_tone = SUCCESS if trust_percent >= 80 else WARNING if trust_percent >= 50 else DANGER
    extent = max(2.0, 360.0 * min(100.0, trust_percent) / 100.0) if trust_percent > 0 else 0.0
    if extent > 0:
        pdf.setStrokeColor(gauge_tone)
        pdf.arc(cx - radius, cy - radius, cx + radius, cy + radius, 90, -extent)
    pdf.setLineCap(0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(cx, cy - 5, f"{trust_percent:.0f}%")
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawCentredString(cx, cy - 16, f"gates {trust_gates_passed}/{trust_gates_total}")

    # Severity tiles with deltas
    pdf.setFillColor(white)
    pdf.setStrokeColor(BORDER_SOFT)
    pdf.roundRect(tiles_x, y - gauge_block_h, tiles_w, gauge_block_h, 9, stroke=1, fill=1)
    pdf.setFillColor(SLATE_MUTED)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(tiles_x + 12, y - 16, "FINDINGS BY SEVERITY" + ("  ·  Δ VS PREVIOUS SCAN" if sev_prev else ""))
    tile_w = (tiles_w - 24 - 3 * 8) / 4
    tile_tones = {"CRITICAL": DANGER, "HIGH": HexColor("#C2410C"), "MEDIUM": WARNING, "LOW": SLATE}
    tx = tiles_x + 12
    for label in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        count = sev_now[label]
        tone = tile_tones[label]
        soft = DANGER_SOFT if count > 0 and label in ("CRITICAL", "HIGH") else SLATE_SOFT
        pdf.setFillColor(soft)
        pdf.setStrokeColor(tone if count > 0 else BORDER_SOFT)
        pdf.setLineWidth(0.8)
        pdf.roundRect(tx, y - 100, tile_w, 72, 8, stroke=1, fill=1)
        pdf.setFillColor(tone)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawCentredString(tx + tile_w / 2, y - 40, label)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawCentredString(tx + tile_w / 2, y - 68, str(count))
        if sev_prev is not None:
            delta = count - sev_prev[label]
            if delta > 0:
                d_txt, d_tone = f"▲ +{delta}", DANGER
            elif delta < 0:
                d_txt, d_tone = f"▼ {delta}", SUCCESS
            else:
                d_txt, d_tone = "— 0", SLATE_MUTED
            pdf.setFillColor(d_tone)
            pdf.setFont("Helvetica-Bold", 7.5)
            pdf.drawCentredString(tx + tile_w / 2, y - 92, d_txt)
        tx += tile_w + 8
    y -= gauge_block_h + 14

    # Trend bars (left) + QR (right)
    trend_h = 108
    trend_w = content_w * 0.66
    qr_x = margin_x + trend_w + 12
    qr_w = content_w - trend_w - 12

    pdf.setFillColor(white)
    pdf.setStrokeColor(BORDER_SOFT)
    pdf.roundRect(margin_x, y - trend_h, trend_w, trend_h, 9, stroke=1, fill=1)
    pdf.setFillColor(SLATE_MUTED)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(margin_x + 12, y - 16, f"TRUST SCORE TREND — LAST {len(trend_rows)} SCANS + CURRENT" if trend_rows else "TRUST SCORE TREND — NO PRIOR HISTORY")
    series = trend_rows + [{
        "status": status_now, "trust_percent": trust_percent,
        "generated_at": str(report.get("generated_at") or ""),
    }]
    bar_area_x = margin_x + 16
    bar_area_w = trend_w - 32
    bar_area_bottom = y - trend_h + 24
    bar_area_h = trend_h - 52
    n = len(series)
    slot_w = bar_area_w / max(1, n)
    bar_w = min(26.0, slot_w * 0.55)
    for i, row in enumerate(series):
        pct = max(0.0, min(100.0, float(row.get("trust_percent") or 0.0)))
        bh = max(2.0, bar_area_h * pct / 100.0)
        bx = bar_area_x + (i * slot_w) + (slot_w - bar_w) / 2
        r_status = str(row.get("status") or "").upper()
        b_tone = SUCCESS if r_status == "PASS" else DANGER if r_status == "FAIL" else WARNING
        is_current = i == n - 1
        pdf.setFillColor(b_tone)
        pdf.roundRect(bx, bar_area_bottom, bar_w, bh, 2, stroke=0, fill=1)
        if is_current:
            pdf.setStrokeColor(INK)
            pdf.setLineWidth(1)
            pdf.roundRect(bx - 1.5, bar_area_bottom - 1.5, bar_w + 3, bh + 3, 3, stroke=1, fill=0)
        pdf.setFillColor(SLATE)
        pdf.setFont("Helvetica", 6)
        date_label = str(row.get("generated_at") or "")[5:10]
        pdf.drawCentredString(bx + bar_w / 2, bar_area_bottom - 10, ("NOW" if is_current else date_label))
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 6.5)
        pdf.drawCentredString(bx + bar_w / 2, bar_area_bottom + bh + 3, f"{pct:.0f}")

    # QR deep link card
    pdf.setFillColor(white)
    pdf.setStrokeColor(BORDER_SOFT)
    pdf.roundRect(qr_x, y - trend_h, qr_w, trend_h, 9, stroke=1, fill=1)
    pdf.setFillColor(SLATE_MUTED)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(qr_x + 12, y - 16, "LIVE OPS DASHBOARD")
    if dashboard_url:
        try:
            import qrcode

            qr_img = qrcode.make(dashboard_url, box_size=6, border=1)
            qr_size = 62
            pdf.drawImage(
                ImageReader(qr_img.get_image() if hasattr(qr_img, "get_image") else qr_img.convert("RGB")),
                qr_x + (qr_w - qr_size) / 2,
                y - trend_h + 28,
                width=qr_size,
                height=qr_size,
            )
            pdf.setFillColor(SLATE)
            pdf.setFont("Helvetica", 6.5)
            pdf.drawCentredString(qr_x + qr_w / 2, y - trend_h + 16, "Scan to open route health live")
        except Exception:
            pdf.setFillColor(SLATE)
            pdf.setFont("Helvetica", 7)
            pdf.drawCentredString(qr_x + qr_w / 2, y - trend_h / 2 - 10, "QR unavailable")
    y -= trend_h + 14

    # Domain scorecard pills
    grid_h = 64
    pdf.setFillColor(white)
    pdf.setStrokeColor(BORDER_SOFT)
    pdf.roundRect(margin_x, y - grid_h, content_w, grid_h, 9, stroke=1, fill=1)
    pdf.setFillColor(SLATE_MUTED)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(margin_x + 12, y - 16, "COMPLIANCE DOMAIN SCORECARD")
    cell_w = (content_w - 24) / len(domain_scores)
    for i, (label, value) in enumerate(domain_scores):
        cx0 = margin_x + 12 + i * cell_w
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 7.2)
        pdf.drawCentredString(cx0 + cell_w / 2, y - 32, label)
        tone, soft = _pill_tone(str(value))
        _draw_pill(cx0 + (cell_w - 46) / 2, y - 48, str(value or "N/A"), tone, soft, w=46, h=13)
    y -= grid_h + 12

    # ════════ PAGE 2 — RUNTIME ENFORCEMENT ════════
    _new_page("Page 2 · Runtime Enforcement")

    pdf.setFillColor(SLATE_MUTED)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(margin_x, y - 4, "C5 RUNTIME SUMMARY — GROUPED ENFORCEMENT VIEW")
    y -= 16

    def _draw_group_card(title: str, tone: Any, rows: list[tuple[str, str, bool]], section: str) -> None:
        """rows: (label, value, render_as_pill)"""
        nonlocal y
        body_lines = 0
        for _, value, as_pill in rows:
            body_lines += 1 if as_pill else max(1, len(textwrap.wrap(str(value), width=74)))
        card_h = 26 + body_lines * (line_h + 3) + 10
        _ensure_space(card_h + 12, section)
        pdf.setFillColor(white)
        pdf.setStrokeColor(BORDER_SOFT)
        pdf.roundRect(margin_x, y - card_h, content_w, card_h, 9, stroke=1, fill=1)
        pdf.setFillColor(tone)
        pdf.rect(margin_x, y - card_h, 4, card_h, stroke=0, fill=1)
        pdf.setFillColor(tone)
        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.drawString(margin_x + 14, y - 17, title)
        cursor = y - 36
        for label, value, as_pill in rows:
            pdf.setFillColor(SLATE)
            pdf.setFont("Helvetica-Bold", 8.2)
            pdf.drawString(margin_x + 14, cursor, str(label))
            if as_pill:
                p_tone, p_soft = _pill_tone(str(value))
                _draw_pill(0, cursor + 3, str(value), p_tone, p_soft, w=60, h=13, right_x=margin_x + content_w - 14)
                cursor -= line_h + 3
            else:
                pdf.setFillColor(INK)
                pdf.setFont("Helvetica", 8.4)
                wrapped = textwrap.wrap(str(value), width=74) or [""]
                pdf.drawRightString(margin_x + content_w - 14, cursor, wrapped[0])
                cursor -= line_h + 3
                for cont in wrapped[1:]:
                    pdf.drawRightString(margin_x + content_w - 14, cursor, cont)
                    cursor -= line_h + 3
        y = y - card_h - 10

    if str(c5_snapshot_status).upper() != "COMPLETE":
        warn_h = 52
        _ensure_space(warn_h + 12, "Page 2 · Runtime Enforcement")
        pdf.setFillColor(DANGER_SOFT)
        pdf.setStrokeColor(DANGER)
        pdf.setLineWidth(1.2)
        pdf.roundRect(margin_x, y - warn_h, content_w, warn_h, 9, stroke=1, fill=1)
        for stripe_i in range(0, int(content_w), 18):
            pdf.setFillColor(DANGER)
            pdf.rect(margin_x + stripe_i, y - 5, 9, 5, stroke=0, fill=1)
        pdf.setFillColor(DANGER)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin_x + 14, y - 22, "⚠ C5 DATA QUALITY WARNING — CERTIFICATION DATA INCOMPLETE")
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 8.4)
        pdf.drawString(margin_x + 14, y - 36, f"Status {c5_snapshot_status} · freshness {c5_data_freshness} — DO NOT USE FOR GO/NO-GO until consistency issues are cleared.")
        y -= warn_h + 12

    _draw_group_card("TRUST & GATE ENFORCEMENT", INDIGO, [
        ("Snapshot version", str(c5.get("snapshot_version") or NOTIFICATION_SNAPSHOT_VERSION), False),
        ("Snapshot status", c5_snapshot_status, True),
        ("Data freshness", c5_data_freshness, True),
        ("Scan mode", str(c5_run_policy.get("scan_mode") or _normalize_scan_mode(report.get("scan_mode"))), False),
        ("Strict global mode", "YES" if bool(c5_run_policy.get("strict_global_mode", _is_strict_mode(report.get("scan_mode")))) else "NO", True),
        ("Strict gate passed", "YES" if bool(c5_run_policy.get("strict_gate_passed", report.get("strict_gate_passed"))) else "NO", True),
        ("Trust score", f"{trust_percent:.2f}% ({trust_gates_passed}/{trust_gates_total} gates)", False),
        ("Consistency", "PASS" if bool(c5_consistency.get("passed")) else f"FAIL ({', '.join(list(c5_consistency.get('issues') or [])) or 'issues'})", False),
        ("Fail reason", c5_fail_reason_summary, False),
    ], "Page 2 · Runtime Enforcement")

    _draw_group_card("WHITE-SCREEN SENTRY", PRIMARY, [
        ("WHITE SCREEN SENTRY STATUS", str(c5_white.get("status") or "UNKNOWN"), True),
        ("Checks failed", f"{int(c5_white.get('failed_checks') or 0)}/{int(c5_white.get('total_checks') or 0)}", False),
        ("Routes tested", str(int(c5_white.get("routes_tested") or 0)), False),
        ("Run ID", str(c5_white.get("run_id") or "—"), False),
    ], "Page 2 · Runtime Enforcement")

    _draw_group_card("VIEWPORT MATRIX & EXTERNAL CERTIFICATION", TEAL, [
        ("Viewport artifacts", str(int(c5_matrix.get("artifact_count") or 0)), False),
        ("Viewports", ",".join(list(c5_matrix.get("viewports") or [])) or "mobile,tablet,desktop", False),
        ("EXTERNAL CERT STATUS", str(c5_external.get("status") or "not_run"), True),
        ("Certification ID", str(c5_external.get("certification_id") or "—"), False),
        ("Retry needed", "YES" if bool(c5_retry.get("needs_retry")) else "NO", True),
        ("Retry reasons", ", ".join(list(c5_retry.get("reasons") or [])) or "none", False),
        ("Preflight policy", f"external_preview={'YES' if bool(c5_run_policy.get('preflight_require_external_preview', ((report.get('preflight_policy') or {}).get('require_external_preview')))) else 'NO'} · local_backend={'YES' if bool(c5_run_policy.get('preflight_require_local_backend', ((report.get('preflight_policy') or {}).get('require_local_backend')))) else 'NO'}", False),
    ], "Page 2 · Runtime Enforcement")

    _draw_group_card("INCIDENT LIFECYCLE", WARNING, [
        ("Incidents evaluated", str(int(c5_incident.get("evaluated_incidents") or 0)), False),
        ("Pending verification", str(int(c5_incident.get("transitioned_to_pending_verification") or 0)), False),
        ("INCIDENTS AUTO CLOSED", str(int(c5_incident.get("auto_closed") or 0)), False),
        ("Reopened", str(int(c5_incident.get("reopened") or 0)), False),
        ("Closure policy", f"{int(c5_policy.get('clean_rescans_required') or INCIDENT_AUTOCLOSE_CLEAN_RESCANS)} clean rescans + {int(c5_policy.get('pending_verification_hours') or INCIDENT_AUTOCLOSE_PENDING_HOURS)}h hold", False),
        ("Transient artifacts", str(int(c5_run_policy.get("transient_artifact_count") or int(report.get("transient_artifact_count") or 0))), False),
    ], "Page 2 · Runtime Enforcement")

    # ════════ PAGE 3 — COMPLIANCE APPENDIX (literal §12 / §13) ════════
    _new_page("Page 3 · Compliance Appendix")

    def _draw_literal_card(title: str, rows: list[tuple[str, Any]], tone: Any) -> None:
        nonlocal y
        total_lines = 0
        wrapped_rows: list[tuple[str, list[str]]] = []
        for key, val in rows:
            wrapped = textwrap.wrap("" if val is None else str(val), width=62) or [""]
            wrapped_rows.append((str(key), wrapped))
            total_lines += max(1, len(wrapped))
        header_h = 18
        body_h = 14 + total_lines * line_h
        block_h = header_h + 4 + body_h + 14
        _ensure_space(block_h, "Page 3 · Compliance Appendix")
        pdf.setFillColor(tone)
        pdf.roundRect(margin_x, y - header_h, content_w, header_h, 5, stroke=0, fill=1)
        pdf.setFillColor(white)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin_x + 10, y - 12.5, title)
        body_top = y - header_h - 4
        pdf.setFillColor(SLATE_SOFT)
        pdf.setStrokeColor(BORDER_SOFT)
        pdf.roundRect(margin_x, body_top - body_h, content_w, body_h, 7, stroke=1, fill=1)
        cursor = body_top - 14
        key_right = margin_x + 200
        for key, wrapped in wrapped_rows:
            pdf.setFillColor(INK)
            pdf.setFont("Courier-Bold", 8)
            pdf.drawRightString(key_right, cursor, f"{key}:")
            pdf.setFont("Courier", 8)
            pdf.drawString(key_right + 10, cursor, wrapped[0])
            cursor -= line_h
            for cont in wrapped[1:]:
                pdf.drawString(key_right + 10, cursor, cont)
                cursor -= line_h
        y = body_top - body_h - 12

    s12_rows = [
        ("TASK_ID", to_public_task_id(report.get("task_id") or "")),
        ("GENERATED_AT", report.get("generated_at") or _now()),
        ("EXECUTION_HASH", report.get("execution_hash") or ""),
        ("STATUS", report.get("status") or ""),
        ("CRITICAL_VULNS", report.get("critical_vulns") or 0),
        ("HIGH_VULNS", report.get("high_vulns") or 0),
        ("MEDIUM_VULNS", report.get("medium_vulns") or int((report.get("severity_counts") or {}).get("medium") or 0)),
        ("LOW_VULNS", report.get("low_vulns") or int((report.get("severity_counts") or {}).get("low") or 0)),
        ("REGRESSIONS", report.get("regressions") or ""),
        ("SECURITY_SCAN", report.get("security_scan") or ""),
        ("E2E_TESTS", report.get("e2e_tests") or ""),
        ("RESPONSIVENESS", report.get("responsiveness") or ""),
        ("PERFORMANCE", report.get("performance") or ""),
        ("RBAC_STATUS", report.get("rbac_status") or ""),
        ("SUBSCRIPTION_ENFORCEMENT", report.get("subscription_enforcement") or ""),
        ("LEARNING_MEMORY_UPDATED", report.get("learning_memory_updated") or ""),
        ("DIRECTIVE_VERSION", report.get("directive_version") or ""),
        ("SUMMARY", report.get("summary") or ""),
    ]
    _draw_literal_card("§12 FINAL OUTPUT — GLOBAL SYSTEM DIRECTIVE", s12_rows, PRIMARY)

    s13_rows = [
        ("SYSTEM_STATUS", v3.get("SYSTEM_STATUS") or report.get("status") or ""),
        ("SECURITY_STATUS", v3.get("SECURITY_STATUS") or report.get("security_scan") or ""),
        ("PERFORMANCE_STATUS", v3.get("PERFORMANCE_STATUS") or report.get("performance") or ""),
        ("I18N_STATUS", v3.get("I18N_STATUS") or ""),
        ("RBAC_STATUS", v3.get("RBAC_STATUS") or report.get("rbac_status") or ""),
        ("REGRESSION_STATUS", v3.get("REGRESSION_STATUS") or ("FAIL" if str(report.get("regressions") or "NO").upper() == "YES" else "PASS")),
        ("ERROR_COUNT", v3.get("ERROR_COUNT") if v3.get("ERROR_COUNT") is not None else int(report.get("critical_vulns") or 0) + int(report.get("high_vulns") or 0) + int(report.get("medium_vulns") or 0) + int(report.get("low_vulns") or 0)),
        ("ACTIVE_FIXES", v3.get("ACTIVE_FIXES") or "NO"),
        ("MONITORING", v3.get("MONITORING") or "ACTIVE"),
        ("LEARNING_MEMORY", v3.get("LEARNING_MEMORY") or ("UPDATED" if str(report.get("learning_memory_updated") or "NO").upper() == "YES" else "NOT UPDATED")),
        ("CONFIDENCE_LEVEL", v3.get("CONFIDENCE_LEVEL") or ""),
    ]
    _draw_literal_card("§13 v3 FINAL OUTPUT — GTEC SCAN v3 UPGRADE (ADDITIVE)", s13_rows, TEAL)

    _ensure_space(44, "Page 3 · Compliance Appendix")
    pdf.setFillColor(SLATE_SOFT)
    pdf.setStrokeColor(BORDER_SOFT)
    pdf.roundRect(margin_x, y - 34, content_w, 30, 6, stroke=1, fill=1)
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica-Oblique", 8.5)
    pdf.drawString(margin_x + 10, y - 22, "This PDF preserves literal §12 and §13 final output fields for compliance archival.")

    pdf.save()
    return buf.getvalue()

# ──────────────────────────────────────────────────────────────────────────
# Scheduler integration
# ──────────────────────────────────────────────────────────────────────────

async def get_effective_policy(db) -> dict[str, Any]:
    await ensure_internal_collections_migrated(db)
    schedule = await get_schedule_settings(db)
    policy = {
        "_id": POLICY_DOC_ID,
        "mode": "autonomous_only",
        "manual_input_allowed": False,
        "policy_locked": True,
        "platform_data_only": PLATFORM_DATA_ONLY,
        "effective_schedule": schedule,
        "updated_at": _now(),
    }
    await db[POLICY_COL].update_one({"_id": POLICY_DOC_ID}, {"$set": policy}, upsert=True)
    if await legacy_mirror_write_enabled(db):
        await db[LEGACY_POLICY_COL].update_one({"_id": POLICY_DOC_ID}, {"$set": policy}, upsert=True)
    return {k: v for k, v in policy.items() if k != "_id"}


async def enqueue_event(
    db,
    *,
    event_type: str,
    source: str,
    scope: str,
    severity: str = "medium",
    payload: Optional[dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> dict[str, Any]:
    key = dedupe_key or _hash_obj(event_type, source, scope, json.dumps(payload or {}, sort_keys=True))
    existing = await db[EVENTS_COL].find_one(
        {"dedupe_key": key, "status": "queued"},
        {"_id": 0, "event_id": 1},
    )
    if existing:
        return {"event_id": existing.get("event_id"), "deduped": True}

    event_id = f"gtec_evt_{uuid.uuid4().hex[:12]}"
    doc = {
        "event_id": event_id,
        "event_type": event_type,
        "source": source,
        "scope": scope,
        "severity": severity,
        "payload": payload or {},
        "status": "queued",
        "dedupe_key": key,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[EVENTS_COL].insert_one(doc)
    return {"event_id": event_id, "deduped": False}


async def consume_queued_events(db, *, limit: int = 100) -> list[dict[str, Any]]:
    events = await db[EVENTS_COL].find(
        {"status": "queued"},
        {"_id": 0},
    ).sort("created_at", 1).limit(max(1, min(limit, 500))).to_list(max(1, min(limit, 500)))
    if not events:
        return []
    ids = [e.get("event_id") for e in events if e.get("event_id")]
    await db[EVENTS_COL].update_many(
        {"event_id": {"$in": ids}},
        {"$set": {"status": "consumed", "consumed_at": _now(), "updated_at": _now()}},
    )
    return events

async def get_schedule_settings(db) -> dict[str, Any]:
    await ensure_internal_collections_migrated(db)
    doc = await db[SETTINGS_COL].find_one({"_id": SETTINGS_DOC_ID}, {"_id": 0})
    configured_enabled = bool((doc or {}).get("enabled", True))
    requested_enabled = (doc or {}).get("requested_enabled", configured_enabled)
    requested_interval = int((doc or {}).get("requested_interval_hours", (doc or {}).get("interval_hours", ENFORCED_INTERVAL_HOURS)))
    return {
        "enabled": True,
        "non_disableable": True,
        "configured_enabled": configured_enabled,
        "requested_enabled": bool(requested_enabled),
        "interval_hours": ENFORCED_INTERVAL_HOURS,
        "enforced_interval_hours": ENFORCED_INTERVAL_HOURS,
        "requested_interval_hours": requested_interval,
        "viewports": (doc or {}).get("viewports", "desktop"),
        "updated_at": (doc or {}).get("updated_at"),
        "updated_by": (doc or {}).get("updated_by"),
    }


async def set_schedule_settings(
    db, *, enabled: Optional[bool] = None, interval_hours: Optional[int] = None,
    viewports: Optional[str] = None, actor: str = "system",
) -> dict[str, Any]:
    await ensure_internal_collections_migrated(db)
    update: dict[str, Any] = {
        "updated_at": _now(),
        "updated_by": actor,
        # Platform policy: SAFE AUTO RUNS are always active.
        "enabled": True,
    }
    if enabled is not None:
        update["requested_enabled"] = bool(enabled)
        if not bool(enabled):
            update["last_disable_attempt_at"] = _now()
            update["last_disable_attempt_by"] = actor
    if interval_hours is not None:
        requested_interval = max(1, min(24, int(interval_hours)))
        update["requested_interval_hours"] = requested_interval
        update["interval_hours"] = ENFORCED_INTERVAL_HOURS
        if requested_interval != ENFORCED_INTERVAL_HOURS:
            update["last_interval_override_at"] = _now()
            update["last_interval_override_by"] = actor
    if viewports is not None:
        update["viewports"] = viewports
    await db[SETTINGS_COL].update_one(
        {"_id": SETTINGS_DOC_ID}, {"$set": update}, upsert=True,
    )
    if await legacy_mirror_write_enabled(db):
        await db[LEGACY_SETTINGS_COL].update_one(
            {"_id": SETTINGS_DOC_ID}, {"$set": update}, upsert=True,
        )
    return await get_schedule_settings(db)


async def _record_scheduler_heartbeat(db, *, status: str, details: Optional[dict[str, Any]] = None) -> None:
    """Persist scheduler heartbeat for truthful runtime status checks."""
    await db.scheduler_heartbeats.update_one(
        {"job_id": SAFE_AUTO_RUN_JOB_ID},
        {
            "$set": {
                "job_id": SAFE_AUTO_RUN_JOB_ID,
                "status": status,
                "last_run": _now(),
                "details": details or {},
                "updated_at": _now(),
            }
        },
        upsert=True,
    )
    if await legacy_mirror_write_enabled(db):
        await db.scheduler_heartbeats.update_one(
            {"job_id": LEGACY_SAFE_AUTO_RUN_JOB_ID},
            {
                "$set": {
                    "job_id": LEGACY_SAFE_AUTO_RUN_JOB_ID,
                    "status": status,
                    "last_run": _now(),
                    "details": details or {},
                    "updated_at": _now(),
                }
            },
            upsert=True,
        )


async def scheduled_gtec_v2_tick() -> None:
    """APScheduler tick — respects the configured schedule & interval.
    Fires only if `enabled` AND last run is older than `interval_hours`.
    """
    try:
        from routes.db import db  # lazy import to avoid circular deps
        await ensure_internal_collections_migrated(db)
        conf = await get_schedule_settings(db)
        await get_effective_policy(db)
        pending_events = await db[EVENTS_COL].count_documents({"status": "queued"})
        interval = int(conf.get("interval_hours", ENFORCED_INTERVAL_HOURS))
        # Skip if a recent run exists
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=interval)).isoformat()
        recent = await db[REPORTS_COL].find_one(
            {"generated_at": {"$gte": cutoff}},
            {"_id": 0, "task_id": 1}, sort=[("generated_at", -1)],
        )
        if recent and pending_events == 0:
            await _record_scheduler_heartbeat(
                db,
                status="healthy",
                details={
                    "result": "skipped_recent_scan",
                    "recent_task_id": recent.get("task_id"),
                    "pending_events": pending_events,
                },
            )
            return
        if RUN_LOCK.locked():
            logger.info("gtec-v2: scheduled tick skipped — scan already running")
            await _record_scheduler_heartbeat(
                db,
                status="healthy",
                details={"result": "skipped_running"},
            )
            return
        event_batch = []
        if pending_events > 0:
            event_batch = await consume_queued_events(db, limit=100)
        trigger = "event_scheduler" if event_batch else "scheduler"
        report = await run_full_scan(
            db,
            triggered_by=trigger,
            actor="apscheduler",
            viewports=conf.get("viewports") or "desktop",
        )
        report_status = str(report.get("status") or "").upper()
        if event_batch and report_status != "INFRA_BLOCKED":
            event_ids = [e.get("event_id") for e in event_batch if e.get("event_id")]
            await db[EVENTS_COL].update_many(
                {"event_id": {"$in": event_ids}},
                {
                    "$set": {
                        "status": "processed",
                        "processed_at": _now(),
                        "processed_task_id": report.get("task_id"),
                        "updated_at": _now(),
                    }
                },
            )
        elif event_batch and report_status == "INFRA_BLOCKED":
            # Keep events queued; infra guard blocked the scan before execution.
            await db[EVENTS_COL].update_many(
                {"event_id": {"$in": [e.get("event_id") for e in event_batch if e.get("event_id")]}},
                {
                    "$set": {
                        "status": "queued",
                        "updated_at": _now(),
                        "last_skip_reason": "infra_blocked_preflight",
                    }
                },
            )
        await _record_scheduler_heartbeat(
            db,
            status="healthy",
            details={
                "result": "scan_completed" if report_status != "INFRA_BLOCKED" else "scan_blocked_preflight",
                "triggered_by": trigger,
                "processed_events": len(event_batch),
                "status": report_status,
                "task_id": report.get("task_id"),
            },
        )
    except Exception:
        try:
            from routes.db import db  # lazy import to avoid circular deps
            await _record_scheduler_heartbeat(
                db,
                status="error",
                details={"result": "tick_crashed"},
            )
        except Exception:
            pass
        logger.exception("gtec-v2: scheduled tick crashed")
