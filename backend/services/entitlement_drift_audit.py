"""Scheduled Entitlement Drift Audit.

Scans enforcement-sensitive backend/frontend files for risky raw
`subscription_plan` usage so entitlement regressions are flagged before
release. Persists results to MongoDB and dispatches a lightweight admin
alert/digest when new risky findings appear.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AUDIT_COLLECTION = "entitlement_drift_audit_log"
AUDIT_EVENT_TYPE = "entitlement_drift_audit"
PROJECT_ROOT = Path("/app")

SENSITIVE_GLOBS = (
    "backend/routes/**/*.py",
    "backend/services/**/*.py",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.tsx",
    "frontend/app/**/*.ts",
    "frontend/app/**/*.tsx",
)

RISKY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"get\(\s*['\"]subscription_plan['\"]", "dict lookup"),
    (r"\[['\"]subscription_plan['\"]\]", "index lookup"),
    (r"getattr\([^\n]{0,80}subscription_plan", "attribute fallback"),
)

ALLOWLIST_PATH_MARKERS: dict[str, tuple[str, ...]] = {
    "backend/utils/access_control_engine.py": ("compute_effective_plan", "build_session_entitlements", "build_feature_entitlements"),
    "backend/shared/pricing_policy.py": tuple(),
    "backend/tests/test_feature_entitlement_divergence_fix_contract.py": tuple(),
    "backend/tests/test_admin_legacy_diagnostics_effective_plan.py": tuple(),
    "backend/tests/test_entitlement_drift_audit_job.py": tuple(),
    "backend/tests/test_scheduler_all_jobs_max_instances_contract.py": tuple(),
    "frontend/src/context/AccessControlContext.tsx": ("effectivePlan",),
    "frontend/src/context/SubscriptionContext.tsx": ("effectivePlan",),
    "frontend/src/utils/subscription.ts": ("effective_plan",),
}

BASELINE_ALLOWLIST_PATHS: set[str] = {
    "backend/routes/ab_prompt_testing.py",
    "backend/routes/access_control.py",
    "backend/routes/admin_console.py",
    "backend/routes/admin_general_analytics.py",
    "backend/routes/admin_payment_analytics.py",
    "backend/routes/admin_payments_tax_intelligence.py",
    "backend/routes/admin_sessions.py",
    "backend/routes/admin_subscription_analytics.py",
    "backend/routes/ai_feature_analytics.py",
    "backend/routes/ai_learning_hub.py",
    "backend/routes/ai_panel_insights.py",
    "backend/routes/ai_coaching_team.py",
    "backend/routes/ai_usage_analytics.py",
    "backend/routes/ai_user_insights.py",
    "backend/routes/auth.py",
    "backend/routes/feature_access.py",
    "backend/routes/feature_registry.py",
    "backend/routes/home_dashboard.py",
    "backend/routes/payments_admin_maintenance_routes.py",
    "backend/routes/payments_reporting_routes.py",
    "backend/routes/payments_user_analytics_routes.py",
    "backend/routes/platform_analytics.py",
    "backend/routes/sports_v2_service.py",
}


def _iter_sensitive_files() -> list[Path]:
    files: list[Path] = []
    for pattern in SENSITIVE_GLOBS:
        files.extend(PROJECT_ROOT.glob(pattern))
    return sorted({p for p in files if p.is_file()})


def _is_allowlisted(path_str: str, content: str) -> bool:
    markers = ALLOWLIST_PATH_MARKERS.get(path_str)
    if markers is None:
        return False
    if not markers:
        return True
    return all(marker in content for marker in markers)


def scan_entitlement_drift() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    files_scanned = 0

    for file_path in _iter_sensitive_files():
        rel_path = file_path.relative_to(PROJECT_ROOT).as_posix()
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            logger.warning("[entitlement-drift] unable to read %s: %s", rel_path, exc)
            continue

        files_scanned += 1
        if rel_path in BASELINE_ALLOWLIST_PATHS:
            continue
        if _is_allowlisted(rel_path, content):
            continue

        file_findings: list[dict[str, Any]] = []
        for pattern, label in RISKY_PATTERNS:
            for match in re.finditer(pattern, content):
                line_no = content.count("\n", 0, match.start()) + 1
                file_findings.append(
                    {
                        "path": rel_path,
                        "line": line_no,
                        "pattern": label,
                        "snippet": content.splitlines()[line_no - 1].strip()[:220],
                        "severity": "high" if rel_path.startswith("backend/routes/") or rel_path.startswith("frontend/src/context/") else "medium",
                    }
                )

        findings.extend(file_findings)

    findings.sort(key=lambda item: (item["path"], item["line"]))
    high = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]

    return {
        "files_scanned": files_scanned,
        "finding_count": len(findings),
        "high_risk_count": len(high),
        "medium_risk_count": len(medium),
        "findings": findings,
        "status": "pass" if not findings else "warning" if not high else "fail",
    }


def _build_summary(record: dict[str, Any]) -> tuple[str, str, dict[str, Any], str]:
    high = int(record.get("new_high_risk_count") or 0)
    medium = int(record.get("new_medium_risk_count") or 0)
    total = int(record.get("new_finding_count") or 0)
    status = str(record.get("status") or "unknown")

    if total == 0:
        return (
            "warning",
            "Entitlement drift audit all-clear",
            {
                "Files scanned": str(record.get("files_scanned") or 0),
                "Risky findings": "0",
            },
            "No new risky raw subscription_plan usage was detected in enforcement-sensitive files.",
        )

    top_findings = (record.get("new_findings") or [])[:3]
    fields = {
        "Files scanned": str(record.get("files_scanned") or 0),
        "New high risk": str(high),
        "New medium risk": str(medium),
        "New findings": str(total),
        "Audit status": status.upper(),
    }
    for idx, finding in enumerate(top_findings, 1):
        fields[f"#{idx} {finding.get('path')}"] = f"line {finding.get('line')} • {finding.get('pattern')}"

    severity = "critical" if high > 0 else "warning"
    summary = (
        f"Detected {total} new risky raw subscription_plan usage pattern(s) across sensitive files. "
        f"High risk: {high}. Medium risk: {medium}."
    )
    title = "Entitlement drift audit flagged risky plan reads"
    return severity, title, fields, summary


def _finding_key(finding: dict[str, Any]) -> str:
    return f"{finding.get('path')}::{finding.get('line')}::{finding.get('pattern')}"


async def run_entitlement_drift_audit(trigger: str = "scheduled_daily") -> dict[str, Any]:
    from routes.db import db
    from services.webhook_alerts import send_alert

    now = datetime.now(timezone.utc)
    audit = scan_entitlement_drift()

    previous = await db[AUDIT_COLLECTION].find_one({}, {"_id": 0}, sort=[("generated_at", -1)])
    baseline_established = previous is None
    previous_findings = (previous or {}).get("findings") or []
    previous_keys = {_finding_key(item) for item in previous_findings}
    if baseline_established:
        previous_keys = {_finding_key(item) for item in audit["findings"]}
        new_findings: list[dict[str, Any]] = []
    else:
        new_findings = [item for item in audit["findings"] if _finding_key(item) not in previous_keys]
    new_high = [item for item in new_findings if item.get("severity") == "high"]
    new_medium = [item for item in new_findings if item.get("severity") == "medium"]

    decorated = {
        **audit,
        "baseline_established": baseline_established,
        "new_findings": new_findings,
        "new_finding_count": len(new_findings),
        "new_high_risk_count": len(new_high),
        "new_medium_risk_count": len(new_medium),
    }
    severity, title, fields, summary = _build_summary(decorated)

    should_alert = (not baseline_established) and decorated["new_finding_count"] > 0
    effective_status = "pass" if decorated["new_finding_count"] == 0 else ("warning" if decorated["new_high_risk_count"] == 0 else "fail")

    frontend_base = (os.environ.get("FRONTEND_BASE_URL") or "").rstrip("/")
    url = f"{frontend_base}/admin-console?category=dev&tab=code-health" if frontend_base else None

    dispatch_res: dict[str, Any] = {"dispatched": False, "skipped": True}
    if should_alert:
        try:
            dispatch_res = await send_alert(
                event_type=AUDIT_EVENT_TYPE,
                severity=severity,
                title=title,
                summary=summary,
                fields=fields,
                url=url,
            )
        except Exception as exc:
            logger.warning("[entitlement-drift] alert dispatch failed: %s", exc)
            dispatch_res = {"dispatched": False, "error": str(exc)[:200]}

    record = {
        "generated_at": now.isoformat(),
        "trigger": trigger,
        "status": effective_status,
        "baseline_established": baseline_established,
        "raw_scan_status": audit["status"],
        "files_scanned": audit["files_scanned"],
        "finding_count": audit["finding_count"],
        "high_risk_count": audit["high_risk_count"],
        "medium_risk_count": audit["medium_risk_count"],
        "new_finding_count": decorated["new_finding_count"],
        "new_high_risk_count": decorated["new_high_risk_count"],
        "new_medium_risk_count": decorated["new_medium_risk_count"],
        "findings": audit["findings"][:50],
        "new_findings": new_findings[:25],
        "alert_dispatched": bool(dispatch_res.get("dispatched")),
        "baseline_previous_finding_count": len(previous_keys),
        "summary": summary,
        "title": title,
        "severity": severity,
    }
    try:
        await db[AUDIT_COLLECTION].insert_one({**record})
    except Exception as exc:
        logger.warning("[entitlement-drift] log persist failed: %s", exc)

    logger.info(
        "[entitlement-drift] trigger=%s status=%s findings=%s high=%s dispatched=%s",
        trigger,
        record["status"],
        record["new_finding_count"],
        record["new_high_risk_count"],
        record["alert_dispatched"],
    )
    return record