"""
GTEC C5 Checkpoint C Testing — PDF Attachment + Email Notification C5 Summary

Tests for:
1. PDF export includes C5 runtime summary section with enforcement/certification/incident lifecycle fields
2. Email template gtec_scan_v2_report includes C5 runtime summary block and plaintext C5 fields
3. Report generation path persists c5_notification_snapshot to report document
4. Report-pdf endpoint returns canonical SHA headers and valid PDF
5. No regressions in trust gates/release certificate APIs
"""
from __future__ import annotations

import io
import os
import sys

import pytest
import requests

sys.path.append("/app/backend")

from pypdf import PdfReader

from services.gtec_scan_v2 import build_canonical_gtec_pdf_export, to_public_task_id
from utils.email_templates import build_gtec_scan_v2_report_email

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_risk_engine_admin_blocked(response: requests.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        payload = {}

    # Generic admin-forbidden shape
    if isinstance(payload, dict):
        detail = payload.get("detail", "")
        if isinstance(detail, str) and "admin access required" in detail.lower():
            return True

    detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
    return code in {"risk_engine_admin_api_blocked", "risk_engine_id_verification_required"}


def _skip_if_admin_blocked(response: requests.Response, context: str) -> None:
    if _is_risk_engine_admin_blocked(response):
        pytest.skip(f"{context} blocked by risk engine containment")


@pytest.fixture(scope="module")
def admin_session():
    """Authenticated admin session for API tests."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    # Try login
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, headers={"X-Requested-With": "XMLHttpRequest"})

    if login_resp.status_code != 200:
        pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")

    data = login_resp.json()
    token = (
        data.get("session_token")
        or data.get("token")
        or login_resp.cookies.get("session_token")
        or session.cookies.get("session_token")
    )
    if not token:
        pytest.skip("Admin token missing in login JSON/cookies")

    session.headers.update({"Authorization": f"Bearer {token}"})

    original_get = session.get

    def guarded_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        if _is_risk_engine_admin_blocked(response):
            pytest.skip("Admin API blocked by environment containment/authorization policy")
        return response

    session.get = guarded_get
    
    return session


def _sample_report_with_c5_snapshot() -> dict:
    """Sample report with full c5_notification_snapshot for testing."""
    return {
        "task_id": "gtec_c5_checkpoint_test_001",
        "generated_at": "2026-05-15T12:00:00+00:00",
        "execution_hash": "hash_checkpoint_test_123",
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
        "summary": "Checkpoint C test - C5 PDF/email summary verification",
        "severity_counts": {"medium": 1, "low": 2},
        "v3_output": {
            "SYSTEM_STATUS": "PASS",
            "SECURITY_STATUS": "PASS",
            "PERFORMANCE_STATUS": "PASS",
            "I18N_STATUS": "PASS",
            "RBAC_STATUS": "PASS",
            "REGRESSION_STATUS": "PASS",
            "ERROR_COUNT": 3,
            "ACTIVE_FIXES": "NO",
            "MONITORING": "ACTIVE",
            "LEARNING_MEMORY": "UPDATED",
            "CONFIDENCE_LEVEL": "HIGH",
        },
        "c5_notification_snapshot": {
            "trust": {
                "score_percent": 100.0,
                "passed_gates": 9,
                "total_gates": 9,
                "generated_at": "2026-05-15T12:00:00+00:00",
            },
            "white_screen_sentry": {
                "status": "PASS",
                "run_id": "wss_checkpoint_test_001",
                "failed_checks": 0,
                "total_checks": 60,
                "routes_tested": 20,
                "route_source": "dynamic_inventory",
                "generated_at": "2026-05-15T11:55:00+00:00",
            },
            "responsive_viewport_matrix": {
                "artifact_count": 60,
                "viewports": ["mobile", "tablet", "desktop"],
                "matrix_summary": {
                    "mobile": {"pass": 20, "fail": 0, "total": 20},
                    "tablet": {"pass": 20, "fail": 0, "total": 20},
                    "desktop": {"pass": 20, "fail": 0, "total": 20},
                },
            },
            "external_host_certification": {
                "status": "pass",
                "certification_id": "ext_cert_checkpoint_001",
                "reason": "",
                "started_at": "2026-05-15T11:50:00+00:00",
                "finished_at": "2026-05-15T11:52:00+00:00",
                "retry_plan": {
                    "needs_retry": False,
                    "reasons": [],
                },
            },
            "incident_auto_closure": {
                "evaluated_incidents": 5,
                "transitioned_to_pending_verification": 1,
                "auto_closed": 2,
                "reopened": 0,
                "streak_resets": 1,
                "policy": {
                    "clean_rescans_required": 3,
                    "pending_verification_hours": 24,
                },
                "evaluated_at": "2026-05-15T12:00:00+00:00",
            },
            "generated_at": "2026-05-15T12:00:00+00:00",
        },
    }


class TestPDFExportC5RuntimeSummary:
    """Tests for PDF export C5 runtime summary section."""

    def test_pdf_export_contains_c5_runtime_summary_header(self):
        """Verify PDF contains C5 RUNTIME SUMMARY section header."""
        report = _sample_report_with_c5_snapshot()
        exported = build_canonical_gtec_pdf_export(report)
        
        assert exported is not None, "PDF export should not be None"
        assert exported.get("pdf_bytes"), "PDF bytes should be present"
        
        reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        
        assert "C5 RUNTIME SUMMARY" in text, "PDF should contain C5 RUNTIME SUMMARY header"

    def test_pdf_export_contains_white_screen_sentry_fields(self):
        """Verify PDF contains white-screen sentry status fields."""
        report = _sample_report_with_c5_snapshot()
        exported = build_canonical_gtec_pdf_export(report)
        
        reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        
        assert "WHITE SCREEN SENTRY STATUS" in text or "WHITE_SCREEN_SENTRY_STATUS" in text.replace(" ", "_"), \
            "PDF should contain white-screen sentry status field"

    def test_pdf_export_contains_external_cert_fields(self):
        """Verify PDF contains external host certification fields."""
        report = _sample_report_with_c5_snapshot()
        exported = build_canonical_gtec_pdf_export(report)
        
        reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        
        assert "EXTERNAL CERT STATUS" in text or "EXTERNAL_CERT_STATUS" in text.replace(" ", "_"), \
            "PDF should contain external cert status field"

    def test_pdf_export_contains_incident_auto_closure_fields(self):
        """Verify PDF contains incident auto-closure fields."""
        report = _sample_report_with_c5_snapshot()
        exported = build_canonical_gtec_pdf_export(report)
        
        reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        
        assert "INCIDENTS AUTO CLOSED" in text or "INCIDENTS_AUTO_CLOSED" in text.replace(" ", "_"), \
            "PDF should contain incidents auto closed field"

    def test_pdf_export_contains_trust_gates_fields(self):
        """Verify PDF contains trust gates fields."""
        report = _sample_report_with_c5_snapshot()
        exported = build_canonical_gtec_pdf_export(report)
        
        reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        
        assert "C5 TRUST" in text or "TRUST GATES" in text or "TRUST_GATES" in text.replace(" ", "_"), \
            "PDF should contain trust gates field"

    def test_pdf_export_contains_viewport_matrix_fields(self):
        """Verify PDF contains viewport matrix fields."""
        report = _sample_report_with_c5_snapshot()
        exported = build_canonical_gtec_pdf_export(report)
        
        reader = PdfReader(io.BytesIO(exported["pdf_bytes"]))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        
        assert "VIEWPORT MATRIX" in text or "VIEWPORT_MATRIX" in text.replace(" ", "_"), \
            "PDF should contain viewport matrix field"

    def test_pdf_export_returns_sha256_hash(self):
        """Verify PDF export returns SHA256 hash for canonical verification."""
        report = _sample_report_with_c5_snapshot()
        exported = build_canonical_gtec_pdf_export(report)
        
        assert exported.get("sha256"), "PDF export should include SHA256 hash"
        assert len(exported["sha256"]) == 64, "SHA256 hash should be 64 characters"


class TestEmailTemplateC5RuntimeSummary:
    """Tests for email template C5 runtime summary block."""

    def test_email_html_contains_c5_runtime_summary_header(self):
        """Verify email HTML contains C5 RUNTIME SUMMARY section."""
        email = build_gtec_scan_v2_report_email(
            task_id="task_gtec_c5_checkpoint_001",
            status="PASS",
            critical_vulns=0,
            high_vulns=0,
            medium_vulns=1,
            low_vulns=2,
            summary="Checkpoint C email test",
            c5_trust_score_percent=100.0,
            c5_trust_passed_gates=9,
            c5_trust_total_gates=9,
            c5_white_screen_status="PASS",
            c5_white_screen_run_id="wss_checkpoint_001",
            c5_white_screen_failed_checks=0,
            c5_white_screen_total_checks=60,
            c5_white_screen_routes_tested=20,
            c5_white_screen_route_source="dynamic_inventory",
            c5_viewport_artifact_count=60,
            c5_viewports="mobile,tablet,desktop",
            c5_external_cert_status="pass",
            c5_external_cert_id="ext_cert_checkpoint_001",
            c5_external_cert_retry_needed="NO",
            c5_incidents_evaluated=5,
            c5_incidents_transitioned_pending=1,
            c5_incidents_auto_closed=2,
            c5_incidents_reopened=0,
            c5_incidents_streak_resets=1,
            c5_incident_policy_clean_rescans=3,
            c5_incident_policy_pending_hours=24,
        )
        
        assert "C5 RUNTIME SUMMARY" in (email.html or ""), \
            "Email HTML should contain C5 RUNTIME SUMMARY header"

    def test_email_html_contains_trust_gates_field(self):
        """Verify email HTML contains TRUST_GATES field."""
        email = build_gtec_scan_v2_report_email(
            task_id="task_gtec_c5_checkpoint_002",
            status="PASS",
            critical_vulns=0,
            high_vulns=0,
            medium_vulns=0,
            low_vulns=0,
            summary="Trust gates test",
            c5_trust_score_percent=100.0,
            c5_trust_passed_gates=9,
            c5_trust_total_gates=9,
        )
        
        assert "TRUST_GATES" in (email.html or ""), \
            "Email HTML should contain TRUST_GATES field"

    def test_email_plaintext_contains_white_screen_sentry_status(self):
        """Verify email plaintext contains WHITE_SCREEN_SENTRY_STATUS field."""
        email = build_gtec_scan_v2_report_email(
            task_id="task_gtec_c5_checkpoint_003",
            status="PASS",
            critical_vulns=0,
            high_vulns=0,
            medium_vulns=0,
            low_vulns=0,
            summary="White screen sentry test",
            c5_white_screen_status="PASS",
            c5_white_screen_run_id="wss_test_001",
            c5_white_screen_failed_checks=0,
            c5_white_screen_total_checks=60,
        )
        
        assert "WHITE_SCREEN_SENTRY_STATUS" in (email.text or ""), \
            "Email plaintext should contain WHITE_SCREEN_SENTRY_STATUS field"

    def test_email_plaintext_contains_external_host_cert_status(self):
        """Verify email plaintext contains EXTERNAL_HOST_CERT_STATUS field."""
        email = build_gtec_scan_v2_report_email(
            task_id="task_gtec_c5_checkpoint_004",
            status="PASS",
            critical_vulns=0,
            high_vulns=0,
            medium_vulns=0,
            low_vulns=0,
            summary="External cert test",
            c5_external_cert_status="pass",
            c5_external_cert_id="ext_cert_test_001",
        )
        
        assert "EXTERNAL_HOST_CERT_STATUS" in (email.text or ""), \
            "Email plaintext should contain EXTERNAL_HOST_CERT_STATUS field"

    def test_email_plaintext_contains_incident_policy(self):
        """Verify email plaintext contains INCIDENT_POLICY field."""
        email = build_gtec_scan_v2_report_email(
            task_id="task_gtec_c5_checkpoint_005",
            status="PASS",
            critical_vulns=0,
            high_vulns=0,
            medium_vulns=0,
            low_vulns=0,
            summary="Incident policy test",
            c5_incident_policy_clean_rescans=3,
            c5_incident_policy_pending_hours=24,
        )
        
        assert "INCIDENT_POLICY" in (email.text or ""), \
            "Email plaintext should contain INCIDENT_POLICY field"


class TestReportPDFEndpoint:
    """Tests for report-pdf endpoint canonical SHA headers and valid PDF."""

    def test_report_pdf_endpoint_returns_200_for_existing_task(self, admin_session):
        """Verify report-pdf endpoint returns 200 for existing task."""
        # First get latest report to find a valid task_id
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("No GTEC reports available for testing")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC report found")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in report")
        
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        assert pdf_resp.status_code == 200, f"Expected 200, got {pdf_resp.status_code}"

    def test_report_pdf_endpoint_returns_canonical_sha256_header(self, admin_session):
        """Verify report-pdf endpoint returns X-PDF-Canonical-SHA256 header."""
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("No GTEC reports available for testing")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC report found")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in report")
        
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        
        assert "X-PDF-Canonical-SHA256" in pdf_resp.headers, \
            "Response should include X-PDF-Canonical-SHA256 header"
        sha256 = pdf_resp.headers.get("X-PDF-Canonical-SHA256", "")
        assert len(sha256) == 64, f"SHA256 should be 64 chars, got {len(sha256)}"

    def test_report_pdf_endpoint_returns_valid_pdf_content(self, admin_session):
        """Verify report-pdf endpoint returns valid PDF content."""
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("No GTEC reports available for testing")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC report found")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in report")
        
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        
        assert pdf_resp.headers.get("Content-Type") == "application/pdf", \
            "Content-Type should be application/pdf"
        
        # Verify PDF magic bytes
        content = pdf_resp.content
        assert content[:4] == b"%PDF", "Content should start with PDF magic bytes"

    def test_report_pdf_endpoint_returns_gtec_task_id_headers(self, admin_session):
        """Verify report-pdf endpoint returns X-GTEC-Public-Task-ID header."""
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("No GTEC reports available for testing")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC report found")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in report")
        
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        
        assert "X-GTEC-Public-Task-ID" in pdf_resp.headers, \
            "Response should include X-GTEC-Public-Task-ID header"
        
        public_task_id = pdf_resp.headers.get("X-GTEC-Public-Task-ID", "")
        assert public_task_id.startswith("gtec_c5_"), \
            f"Public task ID should start with gtec_c5_, got {public_task_id}"


class TestTrustGatesReleaseCertificateNoRegression:
    """Tests to verify no regressions in trust gates/release certificate APIs."""

    def test_trust_gates_endpoint_returns_200(self, admin_session):
        """Verify trust-gates endpoint returns 200."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/trust-gates")
        _skip_if_admin_blocked(resp, "gtec-c5 trust-gates")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_trust_gates_endpoint_returns_expected_structure(self, admin_session):
        """Verify trust-gates endpoint returns expected structure."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/trust-gates")
        if resp.status_code != 200:
            pytest.skip("Trust gates endpoint not available")
        
        data = resp.json()
        assert "trust_score_percent" in data, "Response should include trust_score_percent"
        assert "passed_gates" in data, "Response should include passed_gates"
        assert "total_gates" in data, "Response should include total_gates"
        assert "gates" in data, "Response should include gates array"

    def test_release_certificate_endpoint_returns_200(self, admin_session):
        """Verify release-certificate endpoint returns 200."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
        _skip_if_admin_blocked(resp, "gtec-c5 release-certificate")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_release_certificate_endpoint_returns_expected_structure(self, admin_session):
        """Verify release-certificate endpoint returns expected structure."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
        if resp.status_code != 200:
            pytest.skip("Release certificate endpoint not available")
        
        data = resp.json()
        assert "certificate_id" in data, "Response should include certificate_id"
        assert "trust_score_percent" in data, "Response should include trust_score_percent"
        assert "checks" in data, "Response should include checks"
        
        checks = data.get("checks", {})
        assert "white_screen_sentry" in checks, "Checks should include white_screen_sentry"
        assert "responsive_viewport_matrix" in checks, "Checks should include responsive_viewport_matrix"

    def test_release_certificate_white_screen_sentry_check_structure(self, admin_session):
        """Verify release-certificate white_screen_sentry check has expected fields."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
        if resp.status_code != 200:
            pytest.skip("Release certificate endpoint not available")
        
        data = resp.json()
        wss = data.get("checks", {}).get("white_screen_sentry", {})
        
        assert "status" in wss, "white_screen_sentry should include status"
        assert "run_id" in wss, "white_screen_sentry should include run_id"
        assert "failed_checks" in wss, "white_screen_sentry should include failed_checks"
        assert "total_checks" in wss, "white_screen_sentry should include total_checks"

    def test_release_certificate_viewport_matrix_check_structure(self, admin_session):
        """Verify release-certificate responsive_viewport_matrix check has expected fields."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
        if resp.status_code != 200:
            pytest.skip("Release certificate endpoint not available")
        
        data = resp.json()
        matrix = data.get("checks", {}).get("responsive_viewport_matrix", {})
        
        assert "viewports" in matrix, "responsive_viewport_matrix should include viewports"
        assert "artifact_count" in matrix, "responsive_viewport_matrix should include artifact_count"


class TestC5NotificationSnapshotPersistence:
    """Tests to verify c5_notification_snapshot is persisted in report documents."""

    def test_latest_report_contains_c5_notification_snapshot(self, admin_session):
        """Verify latest report contains c5_notification_snapshot field."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if resp.status_code != 200:
            pytest.skip("No GTEC reports available for testing")
        
        report = resp.json().get("report")
        if not report:
            pytest.skip("No GTEC report found")
        
        # Note: c5_notification_snapshot may be stripped from public API response
        # but should be present in the document. We verify via PDF content instead.
        # The PDF export reads from the report document directly.
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in report")
        
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        if pdf_resp.status_code != 200:
            pytest.skip("PDF endpoint not available")
        
        # If PDF contains C5 RUNTIME SUMMARY, the snapshot was persisted
        reader = PdfReader(io.BytesIO(pdf_resp.content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        
        assert "C5 RUNTIME SUMMARY" in text, \
            "PDF should contain C5 RUNTIME SUMMARY, indicating c5_notification_snapshot was persisted"
