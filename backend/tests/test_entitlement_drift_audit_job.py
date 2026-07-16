"""Unit tests for scheduled entitlement drift audit job."""

from __future__ import annotations

import asyncio
from pathlib import Path

from services.entitlement_drift_audit import _build_summary, scan_entitlement_drift


def test_scan_entitlement_drift_returns_structured_payload() -> None:
    result = scan_entitlement_drift()
    assert "files_scanned" in result
    assert "finding_count" in result
    assert "high_risk_count" in result
    assert "findings" in result
    assert result["status"] in {"pass", "warning", "fail"}


def test_build_summary_all_clear_branch() -> None:
    severity, title, fields, summary = _build_summary(
        {"files_scanned": 12, "new_finding_count": 0, "new_high_risk_count": 0, "new_medium_risk_count": 0, "new_findings": [], "status": "pass"}
    )
    assert severity == "warning"
    assert "all-clear" in title.lower()
    assert fields["Risky findings"] == "0"
    assert "No new risky raw subscription_plan usage" in summary


def test_build_summary_findings_branch() -> None:
    severity, title, fields, summary = _build_summary(
        {
            "files_scanned": 50,
            "new_finding_count": 2,
            "new_high_risk_count": 1,
            "new_medium_risk_count": 1,
            "status": "fail",
            "new_findings": [
                {"path": "backend/routes/example.py", "line": 10, "pattern": "dict lookup", "severity": "high"},
                {"path": "frontend/src/example.ts", "line": 6, "pattern": "direct assignment/read", "severity": "medium"},
            ],
        }
    )
    assert severity == "critical"
    assert "flagged risky plan reads" in title.lower()
    assert fields["New high risk"] == "1"
    assert "Detected 2 new risky raw subscription_plan usage pattern" in summary


def test_scheduler_contract_contains_job_registration() -> None:
    source = Path("/app/backend/scheduler.py").read_text(encoding="utf-8")
    assert 'id="daily_entitlement_drift_audit"' in source
    assert 'CronTrigger(hour=8, minute=20)' in source


def test_scan_function_is_callable_without_async_runtime_errors() -> None:
    loop = asyncio.new_event_loop()
    try:
        result = scan_entitlement_drift()
        assert isinstance(result.get("findings"), list)
    finally:
        loop.close()


def test_first_run_is_designed_to_establish_baseline_not_alert() -> None:
    source = Path("/app/backend/services/entitlement_drift_audit.py").read_text(encoding="utf-8")
    assert 'baseline_established = previous is None' in source
    assert 'new_findings: list[dict[str, Any]] = []' in source
    assert 'should_alert = (not baseline_established) and decorated["new_finding_count"] > 0' in source