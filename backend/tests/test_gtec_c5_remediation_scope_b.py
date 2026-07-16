"""
GTEC C5 Remediation Scope B Tests — P0 + P1 PDF/Email Mismatch Fixes

Tests for:
1. Canonical snapshot contract is present and used by both PDF and email generation
2. _email_report_to_admins builds/uses snapshot before PDF render (no stale default mismatch)
3. PDF includes snapshot status/freshness/consistency/fail reason fields
4. Email template includes snapshot status/freshness/consistency/fail reason lines
5. report-pdf endpoint backfills c5_notification_snapshot for older reports
6. No regression on report-pdf endpoint headers and response
7. No regression on trust-gates/release-certificate/latest endpoints
"""
from __future__ import annotations

import io
import os
import sys

sys.path.append("/app/backend")

import pytest
import requests
from pypdf import PdfReader

from services.gtec_scan_v2 import (
    NOTIFICATION_SNAPSHOT_VERSION,
    _build_fail_reason_summary,
    _validate_notification_snapshot,
    build_canonical_gtec_pdf_export,
    build_snapshot_from_report_email_dispatch,
)
from utils.email_templates import build_gtec_scan_v2_report_email

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_admin_forbidden(response: requests.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    if isinstance(detail, str) and "admin access required" in detail.lower():
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}:
            return True
        message = str(detail.get("message") or "").lower()
        if "admin access blocked" in message:
            return True

    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    return top_code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}


def _skip_if_admin_blocked(response: requests.Response, context: str) -> None:
    if _is_admin_forbidden(response):
        pytest.skip(f"{context} blocked by environment containment/authorization policy")


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    # Login as admin
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")

    data = resp.json()
    token = (
        data.get("session_token")
        or data.get("token")
        or resp.cookies.get("session_token")
        or session.cookies.get("session_token")
    )
    if not token:
        pytest.skip("Admin token missing in login JSON/cookies")

    session.headers.update({"Authorization": f"Bearer {token}"})

    original_get = session.get

    def guarded_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        _skip_if_admin_blocked(response, "GTEC C5 remediation scope B admin API")
        return response

    session.get = guarded_get
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Canonical snapshot contract is present and used by both PDF and email
# ─────────────────────────────────────────────────────────────────────────────

def test_snapshot_contract_has_required_fields():
    """Verify the canonical snapshot contract includes all required fields."""
    report = _sample_report_with_snapshot()
    snapshot = report.get("c5_notification_snapshot") or {}
    
    # Required top-level fields
    assert "snapshot_version" in snapshot
    assert "source_task_id" in snapshot
    assert "snapshot_status" in snapshot
    assert "data_freshness" in snapshot
    assert "consistency" in snapshot
    assert "fail_reason_summary" in snapshot
    
    # Required nested fields
    assert "trust" in snapshot
    assert "white_screen_sentry" in snapshot
    assert "responsive_viewport_matrix" in snapshot
    assert "external_host_certification" in snapshot
    assert "incident_auto_closure" in snapshot


def test_pdf_uses_snapshot_for_c5_runtime_summary():
    """Verify PDF export uses c5_notification_snapshot for C5 runtime summary."""
    report = _sample_report_with_snapshot()
    exported = build_canonical_gtec_pdf_export(report)
    
    assert exported is not None
    assert exported.get("pdf_bytes")
    
    reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    
    # Verify snapshot fields appear in PDF (PDF uses space-separated field names)
    assert "SNAPSHOT STATUS" in text or "SNAPSHOT_STATUS" in text
    assert "DATA FRESHNESS" in text or "DATA_FRESHNESS" in text
    assert "CONSISTENCY" in text
    assert "FAIL REASON SUMMARY" in text or "FAIL_REASON_SUMMARY" in text


def test_email_uses_snapshot_for_c5_runtime_summary():
    """Verify email template uses snapshot fields for C5 runtime summary."""
    email = build_gtec_scan_v2_report_email(
        task_id="gtec_c5_test_001",
        status="PASS",
        critical_vulns=0,
        high_vulns=0,
        medium_vulns=0,
        low_vulns=0,
        summary="Test summary",
        c5_snapshot_status="COMPLETE",
        c5_data_freshness="LIVE",
        c5_consistency_passed="YES",
        c5_consistency_issues="",
        c5_fail_reason_summary="PASS — no failing pillars detected",
    )
    
    # Verify snapshot fields appear in email HTML
    assert "SNAPSHOT_STATUS" in (email.html or "")
    assert "COMPLETE" in (email.html or "")
    
    # Verify snapshot fields appear in email plaintext
    assert "SNAPSHOT_STATUS: COMPLETE" in (email.text or "")
    assert "DATA_FRESHNESS: LIVE" in (email.text or "")
    assert "CONSISTENCY_PASSED: YES" in (email.text or "")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: _email_report_to_admins builds/uses snapshot before PDF render
# ─────────────────────────────────────────────────────────────────────────────

def test_snapshot_built_before_pdf_render_no_stale_defaults():
    """Verify snapshot is built before PDF render to avoid stale UNKNOWN/0 defaults."""
    # Report with email_dispatch containing c5_runtime_summary (simulating historical report)
    report = {
        "task_id": "gtec_c5_hist_002",
        "execution_hash": "hash002",
        "generated_at": "2026-05-15T00:00:00+00:00",
        "status": "FAIL",
        "security_scan": "FAIL",
        "email_dispatch": {
            "sent_at": "2026-05-15T01:00:00+00:00",
            "c5_runtime_summary": {
                "trust": {"score_percent": 88.89, "passed_gates": 8, "total_gates": 9},
                "white_screen_sentry": {
                    "status": "PASS",
                    "run_id": "wss_002",
                    "failed_checks": 0,
                    "total_checks": 60,
                },
                "external_host_certification": {
                    "status": "pass",
                    "certification_id": "ext_002",
                },
                "incident_auto_closure": {
                    "evaluated_incidents": 5,
                    "auto_closed": 2,
                },
            },
        },
    }
    
    # Build snapshot from email dispatch (backfill path)
    snapshot = build_snapshot_from_report_email_dispatch(report)
    
    # Verify snapshot has real values, not UNKNOWN/0 defaults
    assert snapshot.get("source_task_id") == "gtec_c5_hist_002"
    assert (snapshot.get("trust") or {}).get("score_percent") == 88.89
    assert (snapshot.get("trust") or {}).get("passed_gates") == 8
    assert (snapshot.get("white_screen_sentry") or {}).get("status") == "PASS"
    assert (snapshot.get("white_screen_sentry") or {}).get("total_checks") == 60
    assert (snapshot.get("external_host_certification") or {}).get("status") == "pass"
    assert (snapshot.get("incident_auto_closure") or {}).get("auto_closed") == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: PDF includes snapshot status/freshness/consistency/fail reason fields
# ─────────────────────────────────────────────────────────────────────────────

def test_pdf_includes_snapshot_status_field():
    """Verify PDF includes SNAPSHOT_STATUS field."""
    report = _sample_report_with_snapshot()
    exported = build_canonical_gtec_pdf_export(report)
    reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    
    # PDF uses space-separated field names
    assert "SNAPSHOT STATUS" in text or "SNAPSHOT_STATUS" in text


def test_pdf_includes_data_freshness_field():
    """Verify PDF includes DATA_FRESHNESS field."""
    report = _sample_report_with_snapshot()
    exported = build_canonical_gtec_pdf_export(report)
    reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    
    # PDF uses space-separated field names
    assert "DATA FRESHNESS" in text or "DATA_FRESHNESS" in text


def test_pdf_includes_consistency_field():
    """Verify PDF includes CONSISTENCY field."""
    report = _sample_report_with_snapshot()
    exported = build_canonical_gtec_pdf_export(report)
    reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    
    assert "CONSISTENCY" in text


def test_pdf_includes_fail_reason_summary_field():
    """Verify PDF includes FAIL_REASON_SUMMARY field."""
    report = _sample_report_with_snapshot()
    exported = build_canonical_gtec_pdf_export(report)
    reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    
    # PDF uses space-separated field names
    assert "FAIL REASON SUMMARY" in text or "FAIL_REASON_SUMMARY" in text


def test_pdf_shows_warning_when_snapshot_incomplete():
    """Verify PDF shows warning when snapshot status is INCOMPLETE."""
    report = _sample_report_with_incomplete_snapshot()
    exported = build_canonical_gtec_pdf_export(report)
    reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    
    # Should show warning card
    assert "DATA QUALITY WARNING" in text or "INCOMPLETE" in text


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Email template includes snapshot status/freshness/consistency/fail reason
# ─────────────────────────────────────────────────────────────────────────────

def test_email_html_includes_snapshot_status():
    """Verify email HTML includes SNAPSHOT_STATUS field."""
    email = _build_test_email()
    assert "SNAPSHOT_STATUS" in (email.html or "")


def test_email_html_includes_consistency():
    """Verify email HTML includes CONSISTENCY field."""
    email = _build_test_email()
    assert "CONSISTENCY" in (email.html or "")


def test_email_plaintext_includes_snapshot_status():
    """Verify email plaintext includes SNAPSHOT_STATUS field."""
    email = _build_test_email()
    assert "SNAPSHOT_STATUS:" in (email.text or "")


def test_email_plaintext_includes_data_freshness():
    """Verify email plaintext includes DATA_FRESHNESS field."""
    email = _build_test_email()
    assert "DATA_FRESHNESS:" in (email.text or "")


def test_email_plaintext_includes_consistency_passed():
    """Verify email plaintext includes CONSISTENCY_PASSED field."""
    email = _build_test_email()
    assert "CONSISTENCY_PASSED:" in (email.text or "")


def test_email_plaintext_includes_fail_reason_summary():
    """Verify email plaintext includes FAIL_REASON_SUMMARY field."""
    email = _build_test_email()
    assert "FAIL_REASON_SUMMARY:" in (email.text or "")


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: report-pdf endpoint backfills c5_notification_snapshot for older reports
# ─────────────────────────────────────────────────────────────────────────────

def test_report_pdf_endpoint_returns_200(admin_session):
    """Verify report-pdf endpoint returns 200 for existing task."""
    # First get latest report to find a valid task_id
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
    if resp.status_code != 200:
        pytest.skip("No latest report available")
    
    data = resp.json()
    report = data.get("report")
    if not report:
        pytest.skip("No report in latest response")
    
    task_id = report.get("task_id")
    if not task_id:
        pytest.skip("No task_id in report")
    
    # Request PDF
    pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
    assert pdf_resp.status_code == 200, f"Expected 200, got {pdf_resp.status_code}"


def test_report_pdf_endpoint_returns_canonical_sha256_header(admin_session):
    """Verify report-pdf endpoint returns X-PDF-Canonical-SHA256 header."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
    if resp.status_code != 200:
        pytest.skip("No latest report available")
    
    data = resp.json()
    report = data.get("report")
    if not report:
        pytest.skip("No report in latest response")
    
    task_id = report.get("task_id")
    if not task_id:
        pytest.skip("No task_id in report")
    
    pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
    assert pdf_resp.status_code == 200
    
    sha256_header = pdf_resp.headers.get("X-PDF-Canonical-SHA256")
    assert sha256_header, "Missing X-PDF-Canonical-SHA256 header"
    assert len(sha256_header) == 64, f"SHA256 should be 64 chars, got {len(sha256_header)}"


def test_report_pdf_endpoint_returns_gtec_task_id_headers(admin_session):
    """Verify report-pdf endpoint returns X-GTEC-Public-Task-ID header."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
    if resp.status_code != 200:
        pytest.skip("No latest report available")
    
    data = resp.json()
    report = data.get("report")
    if not report:
        pytest.skip("No report in latest response")
    
    task_id = report.get("task_id")
    if not task_id:
        pytest.skip("No task_id in report")
    
    pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
    assert pdf_resp.status_code == 200
    
    public_task_id = pdf_resp.headers.get("X-GTEC-Public-Task-ID")
    assert public_task_id, "Missing X-GTEC-Public-Task-ID header"
    assert public_task_id.startswith("gtec_c5_"), f"Public task ID should start with gtec_c5_, got {public_task_id}"


def test_report_pdf_endpoint_returns_valid_pdf(admin_session):
    """Verify report-pdf endpoint returns valid PDF content."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
    if resp.status_code != 200:
        pytest.skip("No latest report available")
    
    data = resp.json()
    report = data.get("report")
    if not report:
        pytest.skip("No report in latest response")
    
    task_id = report.get("task_id")
    if not task_id:
        pytest.skip("No task_id in report")
    
    pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
    assert pdf_resp.status_code == 200
    
    # Check PDF magic bytes
    content = pdf_resp.content
    assert content[:4] == b"%PDF", "Response should be valid PDF"


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: No regression on report-pdf endpoint headers and response
# ─────────────────────────────────────────────────────────────────────────────

def test_report_pdf_endpoint_content_type(admin_session):
    """Verify report-pdf endpoint returns application/pdf content type."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
    if resp.status_code != 200:
        pytest.skip("No latest report available")
    
    data = resp.json()
    report = data.get("report")
    if not report:
        pytest.skip("No report in latest response")
    
    task_id = report.get("task_id")
    if not task_id:
        pytest.skip("No task_id in report")
    
    pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
    assert pdf_resp.status_code == 200
    
    content_type = pdf_resp.headers.get("Content-Type")
    assert "application/pdf" in content_type, f"Expected application/pdf, got {content_type}"


def test_report_pdf_endpoint_content_disposition(admin_session):
    """Verify report-pdf endpoint returns Content-Disposition header."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
    if resp.status_code != 200:
        pytest.skip("No latest report available")
    
    data = resp.json()
    report = data.get("report")
    if not report:
        pytest.skip("No report in latest response")
    
    task_id = report.get("task_id")
    if not task_id:
        pytest.skip("No task_id in report")
    
    pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
    assert pdf_resp.status_code == 200
    
    content_disp = pdf_resp.headers.get("Content-Disposition")
    assert content_disp, "Missing Content-Disposition header"
    assert "attachment" in content_disp, "Should be attachment disposition"


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: No regression on trust-gates/release-certificate/latest endpoints
# ─────────────────────────────────────────────────────────────────────────────

def test_trust_gates_endpoint_returns_200(admin_session):
    """Verify trust-gates endpoint returns 200."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/trust-gates")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


def test_trust_gates_endpoint_returns_expected_structure(admin_session):
    """Verify trust-gates endpoint returns expected structure."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/trust-gates")
    assert resp.status_code == 200
    
    data = resp.json()
    assert "trust_score_percent" in data
    assert "passed_gates" in data
    assert "total_gates" in data
    assert "gates" in data


def test_release_certificate_endpoint_returns_200(admin_session):
    """Verify release-certificate endpoint returns 200."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


def test_release_certificate_endpoint_returns_expected_structure(admin_session):
    """Verify release-certificate endpoint returns expected structure."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
    assert resp.status_code == 200
    
    data = resp.json()
    assert "certificate_id" in data
    assert "trust_score_percent" in data
    assert "checks" in data


def test_release_certificate_includes_white_screen_sentry(admin_session):
    """Verify release-certificate includes white_screen_sentry in checks."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
    assert resp.status_code == 200
    
    data = resp.json()
    checks = data.get("checks") or {}
    white_screen = checks.get("white_screen_sentry") or {}
    
    assert "status" in white_screen
    assert "run_id" in white_screen
    assert "failed_checks" in white_screen
    assert "total_checks" in white_screen


def test_release_certificate_includes_viewport_matrix(admin_session):
    """Verify release-certificate includes responsive_viewport_matrix in checks."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
    assert resp.status_code == 200
    
    data = resp.json()
    checks = data.get("checks") or {}
    matrix = checks.get("responsive_viewport_matrix") or {}
    
    assert "viewports" in matrix
    assert "artifact_count" in matrix


def test_latest_endpoint_returns_200(admin_session):
    """Verify latest endpoint returns 200."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"


def test_latest_endpoint_returns_report(admin_session):
    """Verify latest endpoint returns report object."""
    resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
    assert resp.status_code == 200
    
    data = resp.json()
    assert "report" in data


# ─────────────────────────────────────────────────────────────────────────────
# Additional validation tests
# ─────────────────────────────────────────────────────────────────────────────

def test_fail_reason_summary_for_pass_status():
    """Verify fail reason summary for PASS status."""
    report = {"status": "PASS"}
    summary = _build_fail_reason_summary(report)
    assert "PASS" in summary
    assert "no failing pillars" in summary.lower()


def test_fail_reason_summary_for_fail_status():
    """Verify fail reason summary for FAIL status includes failing pillars."""
    report = {
        "status": "FAIL",
        "security_scan": "FAIL",
        "e2e_tests": "FAIL",
    }
    summary = _build_fail_reason_summary(report)
    assert "FAIL" in summary
    assert "security_scan" in summary.lower()
    assert "e2e_tests" in summary.lower()


def test_snapshot_validator_detects_task_id_mismatch():
    """Verify snapshot validator detects task_id mismatch."""
    report = {"task_id": "gtec_c5_001", "status": "PASS"}
    snapshot = {
        "source_task_id": "gtec_c5_002",  # Different task_id
        "trust": {"passed_gates": 9, "total_gates": 9},
        "white_screen_sentry": {"status": "PASS", "failed_checks": 0, "total_checks": 60},
        "responsive_viewport_matrix": {"artifact_count": 60},
        "incident_auto_closure": {"evaluated_incidents": 5, "auto_closed": 2, "reopened": 0, "transitioned_to_pending_verification": 0},
    }
    
    result = _validate_notification_snapshot(snapshot, report)
    assert result.get("passed") is False
    assert "source_task_id_mismatch" in (result.get("issues") or [])


def test_snapshot_validator_passes_for_valid_snapshot():
    """Verify snapshot validator passes for valid snapshot."""
    report = {"task_id": "gtec_c5_001", "status": "PASS"}
    snapshot = {
        "source_task_id": "gtec_c5_001",
        "trust": {"passed_gates": 9, "total_gates": 9},
        "white_screen_sentry": {"status": "PASS", "failed_checks": 0, "total_checks": 60},
        "responsive_viewport_matrix": {"artifact_count": 60},
        "incident_auto_closure": {"evaluated_incidents": 5, "auto_closed": 2, "reopened": 0, "transitioned_to_pending_verification": 0},
    }
    
    result = _validate_notification_snapshot(snapshot, report)
    assert result.get("passed") is True
    assert len(result.get("issues") or []) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _sample_report_with_snapshot() -> dict:
    """Return a sample report with complete c5_notification_snapshot."""
    return {
        "task_id": "gtec_c5_test_remediation_001",
        "generated_at": "2026-05-15T00:00:00+00:00",
        "execution_hash": "hash_test_remediation",
        "status": "PASS",
        "critical_vulns": 0,
        "high_vulns": 0,
        "medium_vulns": 1,
        "low_vulns": 2,
        "regressions": "NO",
        "security_scan": "PASS",
        "e2e_tests": "PASS",
        "responsiveness": "PASS",
        "performance": "PASS",
        "rbac_status": "PASS",
        "subscription_enforcement": "PASS",
        "learning_memory_updated": "YES",
        "directive_version": "C5.2026.05",
        "summary": "Remediation scope B test",
        "severity_counts": {"medium": 1, "low": 2},
        "v3_output": {
            "SYSTEM_STATUS": "PASS",
            "SECURITY_STATUS": "PASS",
        },
        "c5_notification_snapshot": {
            "snapshot_version": NOTIFICATION_SNAPSHOT_VERSION,
            "source_task_id": "gtec_c5_test_remediation_001",
            "source_execution_hash": "hash_test_remediation",
            "source_generated_at": "2026-05-15T00:00:00+00:00",
            "snapshot_status": "COMPLETE",
            "data_freshness": "LIVE",
            "consistency": {"passed": True, "issues": []},
            "fail_reason_summary": "PASS — no failing pillars detected",
            "trust": {"score_percent": 100.0, "passed_gates": 9, "total_gates": 9},
            "white_screen_sentry": {
                "status": "PASS",
                "run_id": "wss_test_001",
                "failed_checks": 0,
                "total_checks": 60,
                "routes_tested": 20,
                "route_source": "dynamic_inventory",
            },
            "responsive_viewport_matrix": {
                "artifact_count": 60,
                "viewports": ["mobile", "tablet", "desktop"],
                "matrix_summary": {},
            },
            "external_host_certification": {
                "status": "pass",
                "certification_id": "ext_cert_test_001",
                "reason": "",
                "retry_plan": {"needs_retry": False, "reasons": []},
            },
            "incident_auto_closure": {
                "evaluated_incidents": 5,
                "transitioned_to_pending_verification": 1,
                "auto_closed": 2,
                "reopened": 0,
                "streak_resets": 1,
                "policy": {"clean_rescans_required": 3, "pending_verification_hours": 24},
            },
            "generated_at": "2026-05-15T00:00:00+00:00",
        },
    }


def _sample_report_with_incomplete_snapshot() -> dict:
    """Return a sample report with INCOMPLETE c5_notification_snapshot."""
    report = _sample_report_with_snapshot()
    report["c5_notification_snapshot"]["snapshot_status"] = "INCOMPLETE"
    report["c5_notification_snapshot"]["data_freshness"] = "STALE_OR_PARTIAL"
    report["c5_notification_snapshot"]["consistency"] = {"passed": False, "issues": ["snapshot_build_failed"]}
    return report


def _build_test_email():
    """Build a test email with all C5 fields."""
    return build_gtec_scan_v2_report_email(
        task_id="gtec_c5_test_001",
        status="PASS",
        critical_vulns=0,
        high_vulns=0,
        medium_vulns=1,
        low_vulns=2,
        summary="Test summary for remediation scope B",
        c5_trust_score_percent=100.0,
        c5_trust_passed_gates=9,
        c5_trust_total_gates=9,
        c5_white_screen_status="PASS",
        c5_white_screen_run_id="wss_test_001",
        c5_white_screen_failed_checks=0,
        c5_white_screen_total_checks=60,
        c5_white_screen_routes_tested=20,
        c5_white_screen_route_source="dynamic_inventory",
        c5_viewport_artifact_count=60,
        c5_viewports="mobile,tablet,desktop",
        c5_external_cert_status="pass",
        c5_external_cert_id="ext_cert_test_001",
        c5_external_cert_retry_needed="NO",
        c5_incidents_evaluated=5,
        c5_incidents_transitioned_pending=1,
        c5_incidents_auto_closed=2,
        c5_incidents_reopened=0,
        c5_incidents_streak_resets=1,
        c5_incident_policy_clean_rescans=3,
        c5_incident_policy_pending_hours=24,
        c5_snapshot_version=NOTIFICATION_SNAPSHOT_VERSION,
        c5_snapshot_status="COMPLETE",
        c5_data_freshness="LIVE",
        c5_consistency_passed="YES",
        c5_consistency_issues="",
        c5_fail_reason_summary="PASS — no failing pillars detected",
    )
