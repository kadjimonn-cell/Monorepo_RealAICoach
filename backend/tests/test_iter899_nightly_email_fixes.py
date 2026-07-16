"""Iteration 899 — Verification of the 5 nightly monitoring email fixes.

Covers:
  1) SAST scanner returns PASS (0 high-severity findings) and still catches
     real secrets/shell-injection when a temp fixture is added.
  2) TDZ scanner reports 0 critical issues on the real frontend tree, but
     still flags real TDZ vectors (hook deps + synchronous useMemo body call)
     while ignoring safe useEffect body-only calls.
  3) preview_host_guard.py --mode startup and --mode ci both pass after the
     BLOCKED_TOKEN -> BLOCKED_HOST_MARKER rename.
  4) build_accessibility_audit_alert_email status logic (PASSED / WARNING /
     CRITICAL) and category_breakdown formatting (no raw python dicts).
  5) performance_reports._collect_report_data includes 'avg_response_ms' key
     (None when no samples) + send_performance_report display path renders
     "n/a (no samples yet)" instead of "0ms".
  6) scheduler.py GTEC C5 email params derive metric/condition from
     degrade_reasons (code inspection assertions on source text).
  7) Backend regression: /api/health 200, admin login 200.
"""

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import requests

# Ensure /app/backend on sys.path so 'routes.*' & 'utils.*' resolve
BACKEND_DIR = Path("/app/backend")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback: pull from frontend/.env
    _env = Path("/app/frontend/.env").read_text().splitlines()
    for line in _env:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


# ─── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ─── 1) SAST Scan ────────────────────────────────────────────────────────

def _run_sast():
    """Invoke the async _run_sast_scan from cwd=/app/backend."""
    from routes.autonomous_engine.zero_trust import _run_sast_scan
    return asyncio.get_event_loop().run_until_complete(_run_sast_scan())


def test_sast_scan_passes_clean(event_loop):
    """SAST scan must return PASS with 0 high-severity findings (baseline)."""
    result = _run_sast()
    assert result["status"] == "PASS", (
        f"SAST expected PASS, got {result['status']} with "
        f"{result['findings_count']} findings: "
        f"{[f for f in result['findings'] if f['severity'] == 'high'][:5]}"
    )
    high_findings = [f for f in result["findings"] if f["severity"] == "high"]
    assert len(high_findings) == 0, f"High-severity findings not expected: {high_findings}"
    assert result["scanned_files"] > 0


def test_sast_scan_catches_real_issues(event_loop):
    """Negative test: temporary bad file must be flagged, then removed."""
    # NOTE: SAST only scans first 200 files (rglob order). Place at top-level
    # of /app/backend/ where the walk starts, guaranteeing inclusion.
    fixture = BACKEND_DIR / "_iter899_sast_fixture.py"
    fixture.write_text(
        'password = "supersecretvalue123"\n'
        'import subprocess\n'
        'subprocess.run("ls -la", shell=True)\n'
    )
    try:
        result = _run_sast()
        rules = {f["rule"] for f in result["findings"] if fixture.name in f["file"]}
        assert "hardcoded_secret" in rules, f"Expected hardcoded_secret in {rules}"
        assert "shell_injection_risk" in rules, f"Expected shell_injection_risk in {rules}"
        assert result["status"] == "FAIL", "Adding a high-severity finding must flip status to FAIL"
    finally:
        fixture.unlink(missing_ok=True)

    # Post-cleanup: scan is PASS again
    result_after = _run_sast()
    assert result_after["status"] == "PASS", (
        f"Post-cleanup scan should PASS; got {result_after['status']} with "
        f"{[f for f in result_after['findings'] if f['severity']=='high'][:5]}"
    )


# ─── 2) TDZ Scanner ──────────────────────────────────────────────────────

def test_tdz_scanner_zero_critical():
    """run_full_scan must report 0 critical TDZ issues on live frontend."""
    from routes.code_health_scanner import run_full_scan
    result = run_full_scan()
    # Critical bucket = TDZ findings only (per _scan_file_for_tdz)
    tdz_critical = [i for i in result["issues"] if i.get("type") == "TDZ" and i.get("severity") == "critical"]
    assert len(tdz_critical) == 0, (
        f"Expected 0 TDZ critical issues, got {len(tdz_critical)}: "
        f"{tdz_critical[:5]}"
    )


def test_tdz_scanner_positive_and_negative_fixture(tmp_path):
    """Real TDZ vectors must be flagged, safe useEffect body-only must not."""
    from routes.code_health_scanner import _scan_file_for_tdz

    fixture = tmp_path / "Screen.tsx"
    fixture.write_text(
        "import React, { useEffect, useMemo } from 'react';\n"
        "\n"
        "export function Screen() {\n"
        "  useEffect(() => { safeCall(); }, [loadData]);\n"
        "  const memoVal = useMemo(() => compute(), []);\n"
        "  const loadData = async () => { return 1; };\n"
        "  const compute = () => 42;\n"
        "  const safeCall = () => console.log('ok');\n"
        "  return null;\n"
        "}\n"
    )
    issues = _scan_file_for_tdz(str(fixture))
    flagged = {i["function"] for i in issues}
    assert "loadData" in flagged, f"useEffect deps 'loadData' should be flagged; got {flagged}"
    assert "compute" in flagged, f"useMemo body call 'compute' should be flagged; got {flagged}"
    assert "safeCall" not in flagged, (
        f"useEffect body-only call 'safeCall' must NOT be flagged; got {flagged}"
    )


# ─── 3) Preview Host Guard ───────────────────────────────────────────────

def test_preview_host_guard_startup_mode():
    proc = subprocess.run(
        [sys.executable, "scripts/preview_host_guard.py", "--mode", "startup"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"startup guard failed rc={proc.returncode}: {combined[-500:]}"
    assert "PASSED" in combined, f"Expected PASSED marker: {combined[-500:]}"


def test_preview_host_guard_ci_mode():
    proc = subprocess.run(
        [sys.executable, "scripts/preview_host_guard.py", "--mode", "ci"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"ci guard failed rc={proc.returncode}: {combined[-1000:]}"
    assert "PASSED" in combined, f"Expected PASSED marker: {combined[-500:]}"


def test_preview_host_guard_renamed_symbol():
    """BLOCKED_TOKEN must be gone; BLOCKED_HOST_MARKER present."""
    src = (BACKEND_DIR / "scripts" / "preview_host_guard.py").read_text()
    assert "BLOCKED_HOST_MARKER" in src
    assert re.search(r"\bBLOCKED_TOKEN\b", src) is None, "Old BLOCKED_TOKEN symbol still present"


# ─── 4) Accessibility Email Template ─────────────────────────────────────

def test_accessibility_email_warning_when_no_critical_low_score():
    from utils.email_templates import build_accessibility_audit_alert_email
    tpl = build_accessibility_audit_alert_email(
        score=60, total_issues=88, critical_count=0,
        category_breakdown="images: 30 issue(s)<br/>contrast: 58 issue(s)"
    )
    assert "CRITICAL" not in tpl.subject, f"Should NOT be CRITICAL: {tpl.subject}"
    assert "WARNING" in tpl.subject, f"Expected WARNING in subject: {tpl.subject}"


def test_accessibility_email_critical_when_criticals_present():
    from utils.email_templates import build_accessibility_audit_alert_email
    tpl = build_accessibility_audit_alert_email(
        score=85, total_issues=10, critical_count=2,
        category_breakdown="images: 2 issue(s)"
    )
    assert "CRITICAL" in tpl.subject, f"Expected CRITICAL subject: {tpl.subject}"


def test_accessibility_email_passed_when_perfect():
    from utils.email_templates import build_accessibility_audit_alert_email
    tpl = build_accessibility_audit_alert_email(
        score=100, total_issues=0, critical_count=0, category_breakdown=""
    )
    assert "PASSED" in tpl.subject


def test_accessibility_email_no_raw_python_dicts():
    """category_breakdown must not contain raw {'count': ...} dumps."""
    from utils.email_templates import build_accessibility_audit_alert_email
    tpl = build_accessibility_audit_alert_email(
        score=60, total_issues=88, critical_count=0,
        category_breakdown="images: 30 issue(s)<br/>contrast: 58 issue(s)"
    )
    assert "{'count':" not in tpl.html, "Raw python dict leaked into email HTML"
    assert "{'count':" not in tpl.text


# ─── 5) Performance Report Avg Response ──────────────────────────────────

def test_performance_report_avg_response_key_present(event_loop):
    from routes.performance_reports import _collect_report_data
    data = asyncio.get_event_loop().run_until_complete(_collect_report_data("daily"))
    assert "api" in data
    assert "avg_response_ms" in data["api"], f"Missing avg_response_ms key: {list(data['api'].keys())}"
    val = data["api"]["avg_response_ms"]
    assert val is None or isinstance(val, (int, float)), f"avg_response_ms wrong type: {type(val)}"


def test_performance_report_display_handles_none_avg():
    """Inspect the source of send_performance_report for None-safe formatting."""
    src = (BACKEND_DIR / "routes" / "performance_reports.py").read_text()
    assert "n/a (no samples yet)" in src, "Fallback text for null avg missing"
    # Ensure the display uses the ternary based on avg_response_ms is None
    assert re.search(r"avg_response_ms", src)
    assert re.search(r"%Y-%m-%d %H:%M UTC", src), "Human-readable generated_at format missing"


# ─── 6) GTEC C5 Scheduler Alert Params ───────────────────────────────────

def test_gtec_c5_alert_derives_metric_from_degrade_reasons():
    src = (BACKEND_DIR / "scheduler.py").read_text()
    # Must include the branch that switches metric based on trust_score
    assert 'trust_score_percent' in src
    assert 'white_screen_sentry_failed_checks' in src
    # Must reference degrade_reasons in the action_taken text
    assert "Degrade reasons:" in src
    # And it must NOT still hard-code "trust_score_percent >= 100" nonsense
    assert '"trust_score_percent", ">=", "100"' not in src
    assert re.search(r'trust_score_percent"\s*,\s*"<"\s*,\s*"100"', src), \
        "Expected trust_score_percent < 100 branch not found"


# ─── 7) Backend Regression ───────────────────────────────────────────────

def test_health_endpoint_200():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200, f"/api/health returned {r.status_code}"


def test_admin_login_200():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"Admin login failed {r.status_code}: {r.text[:300]}"
    body = r.json()
    # Admin login returns the user object directly (email + is_admin flag).
    assert body.get("email") == ADMIN_EMAIL, f"Unexpected login body: {list(body.keys())[:10]}"
    assert body.get("is_admin") is True, "Admin user should have is_admin=true"
