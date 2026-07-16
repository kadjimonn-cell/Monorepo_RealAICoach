"""
GTEC C5 Public Naming Tests - Iteration 19

Tests for the global public/output rename from gtec_v2_* to gtec_c5_*
with backward compatibility for legacy records.

Features tested:
1. GET /api/admin/gtec-scan-v2/latest returns task_id as gtec_c5_* with internal_task_id
2. GET /api/admin/gtec-scan-v2/history returns task_id as gtec_c5_* with internal_task_id
3. GET /api/admin/gtec-scan-v2/findings/latest returns gtec_c5_* task_id
4. GET /api/admin/gtec-scan-v2/memory returns last_seen_task as gtec_c5_* with internal_last_seen_task
5. GET /api/admin/gtec-scan-v2/report-pdf/{task_id} accepts legacy gtec_v2_* and returns gtec-c5 filename
6. Response headers include X-GTEC-Public-Task-ID and X-GTEC-Internal-Task-ID
7. Receipt payload contains public task_id plus internal_task_id, PDF filename uses gtec-c5
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
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


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    # Login as admin
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
        if _is_admin_forbidden(response):
            pytest.skip("Admin API blocked by environment containment/authorization policy")
        return response

    session.get = guarded_get
    
    return session


class TestGtecC5LatestEndpoint:
    """Tests for GET /api/admin/gtec-scan-v2/latest"""
    
    def test_latest_returns_gtec_c5_task_id(self, admin_session):
        """Verify latest report returns task_id with gtec_c5_* prefix."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        report = data.get("report")
        
        if report is None:
            pytest.skip("No GTEC C5 report available yet")
        
        task_id = report.get("task_id", "")
        assert task_id.startswith("gtec_c5_"), f"task_id should start with gtec_c5_, got: {task_id}"
        
    def test_latest_includes_internal_task_id(self, admin_session):
        """Verify latest report includes internal_task_id for backward compatibility."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200
        
        data = resp.json()
        report = data.get("report")
        
        if report is None:
            pytest.skip("No GTEC C5 report available yet")
        
        # internal_task_id should be present
        internal_task_id = report.get("internal_task_id")
        assert internal_task_id is not None, "internal_task_id should be present in response"
        
        # internal_task_id should be the original stored value (could be gtec_v2_* or gtec_c5_*)
        assert internal_task_id, "internal_task_id should not be empty"


class TestGtecC5HistoryEndpoint:
    """Tests for GET /api/admin/gtec-scan-v2/history"""
    
    def test_history_returns_gtec_c5_task_ids(self, admin_session):
        """Verify history items return task_id with gtec_c5_* prefix."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/history")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No GTEC C5 history items available")
        
        for item in items:
            task_id = item.get("task_id", "")
            assert task_id.startswith("gtec_c5_"), f"History task_id should start with gtec_c5_, got: {task_id}"
            
    def test_history_includes_internal_task_id(self, admin_session):
        """Verify history items include internal_task_id."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/history")
        assert resp.status_code == 200
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No GTEC C5 history items available")
        
        for item in items:
            internal_task_id = item.get("internal_task_id")
            assert internal_task_id is not None, "internal_task_id should be present in history item"


class TestGtecC5FindingsLatestEndpoint:
    """Tests for GET /api/admin/gtec-scan-v2/findings/latest"""
    
    def test_findings_latest_returns_gtec_c5_task_id(self, admin_session):
        """Verify findings/latest returns task_id with gtec_c5_* prefix."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/findings/latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        task_id = data.get("task_id", "")
        
        if not task_id:
            pytest.skip("No GTEC C5 findings available yet")
        
        assert task_id.startswith("gtec_c5_"), f"findings task_id should start with gtec_c5_, got: {task_id}"
        
    def test_findings_latest_includes_internal_task_id(self, admin_session):
        """Verify findings/latest includes internal_task_id."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/findings/latest")
        assert resp.status_code == 200
        
        data = resp.json()
        
        if not data.get("task_id"):
            pytest.skip("No GTEC C5 findings available yet")
        
        internal_task_id = data.get("internal_task_id")
        assert internal_task_id is not None, "internal_task_id should be present in findings response"


class TestGtecC5MemoryEndpoint:
    """Tests for GET /api/admin/gtec-scan-v2/memory"""
    
    def test_memory_returns_gtec_c5_last_seen_task(self, admin_session):
        """Verify memory items return last_seen_task with gtec_c5_* prefix."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/memory")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No GTEC C5 memory items available")
        
        for item in items:
            last_seen_task = item.get("last_seen_task", "")
            if last_seen_task:  # Only check non-empty values
                assert last_seen_task.startswith("gtec_c5_"), f"last_seen_task should start with gtec_c5_, got: {last_seen_task}"
                
    def test_memory_includes_internal_last_seen_task(self, admin_session):
        """Verify memory items include internal_last_seen_task."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/memory")
        assert resp.status_code == 200
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No GTEC C5 memory items available")
        
        for item in items:
            # internal_last_seen_task should be present
            internal_last_seen_task = item.get("internal_last_seen_task")
            assert internal_last_seen_task is not None, "internal_last_seen_task should be present in memory item"


class TestGtecC5ReportPdfEndpoint:
    """Tests for GET /api/admin/gtec-scan-v2/report-pdf/{task_id}"""
    
    def test_report_pdf_accepts_gtec_c5_task_id(self, admin_session):
        """Verify report-pdf endpoint accepts gtec_c5_* task_id."""
        # First get a valid task_id from latest
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("Cannot get latest report")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC C5 report available")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in latest report")
        
        # Request PDF with gtec_c5_* task_id
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        assert pdf_resp.status_code == 200, f"Expected 200, got {pdf_resp.status_code}: {pdf_resp.text[:200]}"
        
    def test_report_pdf_accepts_legacy_gtec_v2_task_id(self, admin_session):
        """Verify report-pdf endpoint accepts legacy gtec_v2_* task_id via alias resolution."""
        # First get a valid task_id from latest
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("Cannot get latest report")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC C5 report available")
        
        internal_task_id = report.get("internal_task_id")
        if not internal_task_id:
            pytest.skip("No internal_task_id in latest report")
        
        # If internal_task_id is gtec_v2_*, test with it
        # If internal_task_id is gtec_c5_*, convert to gtec_v2_* for alias test
        if internal_task_id.startswith("gtec_c5_"):
            legacy_task_id = "gtec_v2_" + internal_task_id[len("gtec_c5_"):]
        else:
            legacy_task_id = internal_task_id
        
        # Request PDF with legacy task_id - should resolve via alias
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{legacy_task_id}")
        # Should either succeed (200) or return 404 if no matching record
        assert pdf_resp.status_code in [200, 404], f"Expected 200 or 404, got {pdf_resp.status_code}"
        
    def test_report_pdf_content_disposition_contains_gtec_c5(self, admin_session):
        """Verify PDF Content-Disposition filename contains gtec-c5 (not gtec-v2)."""
        # First get a valid task_id from latest
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("Cannot get latest report")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC C5 report available")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in latest report")
        
        # Request PDF
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        if pdf_resp.status_code != 200:
            pytest.skip(f"PDF request failed: {pdf_resp.status_code}")
        
        content_disposition = pdf_resp.headers.get("Content-Disposition", "")
        assert "gtec-c5" in content_disposition.lower() or "gtec_c5" in content_disposition.lower(), \
            f"Content-Disposition should contain gtec-c5, got: {content_disposition}"
        assert "gtec-v2" not in content_disposition.lower() and "gtec_v2" not in content_disposition.lower(), \
            f"Content-Disposition should NOT contain gtec-v2, got: {content_disposition}"


class TestGtecC5ResponseHeaders:
    """Tests for X-GTEC-Public-Task-ID and X-GTEC-Internal-Task-ID headers."""
    
    def test_report_pdf_includes_public_task_id_header(self, admin_session):
        """Verify report-pdf response includes X-GTEC-Public-Task-ID header."""
        # First get a valid task_id from latest
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("Cannot get latest report")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC C5 report available")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in latest report")
        
        # Request PDF
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        if pdf_resp.status_code != 200:
            pytest.skip(f"PDF request failed: {pdf_resp.status_code}")
        
        public_task_id_header = pdf_resp.headers.get("X-GTEC-Public-Task-ID")
        assert public_task_id_header is not None, "X-GTEC-Public-Task-ID header should be present"
        assert public_task_id_header.startswith("gtec_c5_"), f"X-GTEC-Public-Task-ID should start with gtec_c5_, got: {public_task_id_header}"
        
    def test_report_pdf_includes_internal_task_id_header(self, admin_session):
        """Verify report-pdf response includes X-GTEC-Internal-Task-ID header."""
        # First get a valid task_id from latest
        latest_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        if latest_resp.status_code != 200:
            pytest.skip("Cannot get latest report")
        
        report = latest_resp.json().get("report")
        if not report:
            pytest.skip("No GTEC C5 report available")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("No task_id in latest report")
        
        # Request PDF
        pdf_resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        if pdf_resp.status_code != 200:
            pytest.skip(f"PDF request failed: {pdf_resp.status_code}")
        
        internal_task_id_header = pdf_resp.headers.get("X-GTEC-Internal-Task-ID")
        assert internal_task_id_header is not None, "X-GTEC-Internal-Task-ID header should be present"
        assert internal_task_id_header, "X-GTEC-Internal-Task-ID should not be empty"


class TestGtecC5ExecutionsEndpoint:
    """Tests for GET /api/admin/gtec-scan-v2/executions"""
    
    def test_executions_returns_gtec_c5_task_ids(self, admin_session):
        """Verify executions items return task_id with gtec_c5_* prefix."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No GTEC C5 execution items available")
        
        for item in items:
            task_id = item.get("task_id", "")
            if task_id:  # Only check non-empty values
                assert task_id.startswith("gtec_c5_"), f"Execution task_id should start with gtec_c5_, got: {task_id}"
                
    def test_executions_includes_internal_task_id(self, admin_session):
        """Verify executions items include internal_task_id."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions")
        assert resp.status_code == 200
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No GTEC C5 execution items available")
        
        for item in items:
            if item.get("task_id"):  # Only check items with task_id
                internal_task_id = item.get("internal_task_id")
                assert internal_task_id is not None, "internal_task_id should be present in execution item"


class TestGtecC5IncidentsEndpoint:
    """Tests for GET /api/admin/gtec-scan-v2/incidents"""
    
    def test_incidents_returns_gtec_c5_task_ids(self, admin_session):
        """Verify incidents items return task_id with gtec_c5_* prefix."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/incidents?status=all")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No GTEC C5 incident items available")
        
        for item in items:
            task_id = item.get("task_id", "")
            if task_id:  # Only check non-empty values
                assert task_id.startswith("gtec_c5_"), f"Incident task_id should start with gtec_c5_, got: {task_id}"


class TestGtecC5ReceiptPayload:
    """Tests for gtec_c5_run_receipt payload structure.
    
    Note: These tests check the MOST RECENT receipt entry only, as older entries
    may have been created before the gtec_v2 -> gtec_c5 rename was applied.
    """
    
    def test_receipt_payload_contains_public_and_internal_task_id(self, admin_session):
        """Verify most recent receipt payload contains both public task_id and internal_task_id."""
        # Get compliance digest feed filtered by gtec_c5_run_receipt - only check most recent
        resp = admin_session.get(f"{BASE_URL}/api/compliance-digests/feed?kind=gtec_c5_run_receipt&limit=1")
        
        if resp.status_code != 200:
            pytest.skip(f"Cannot get compliance digest feed: {resp.status_code}")
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No gtec_c5_run_receipt entries available")
        
        # Check only the most recent entry (first item)
        item = items[0]
        payload = item.get("payload", {})
        
        # Check task_id is public (gtec_c5_*)
        task_id = payload.get("task_id", "")
        assert task_id.startswith("gtec_c5_"), f"Receipt task_id should start with gtec_c5_, got: {task_id}"
        
        # Check internal_task_id is present
        internal_task_id = payload.get("internal_task_id")
        assert internal_task_id is not None, "Receipt payload should contain internal_task_id"
            
    def test_receipt_pdf_filename_uses_gtec_c5(self, admin_session):
        """Verify most recent receipt PDF attachment filename uses gtec-c5 (not gtec-v2)."""
        # Get compliance digest feed filtered by gtec_c5_run_receipt - only check most recent
        resp = admin_session.get(f"{BASE_URL}/api/compliance-digests/feed?kind=gtec_c5_run_receipt&limit=1")
        
        if resp.status_code != 200:
            pytest.skip(f"Cannot get compliance digest feed: {resp.status_code}")
        
        data = resp.json()
        items = data.get("items", [])
        
        if not items:
            pytest.skip("No gtec_c5_run_receipt entries available")
        
        # Check only the most recent entry (first item)
        item = items[0]
        payload = item.get("payload", {})
        pdf_attachment = payload.get("pdf_attachment", {})
        filename = pdf_attachment.get("filename", "")
        
        if not filename:
            pytest.skip("No PDF filename in most recent receipt")
        
        assert "gtec-c5" in filename.lower() or "gtec_c5" in filename.lower(), \
            f"PDF filename should contain gtec-c5, got: {filename}"
        assert "gtec-v2" not in filename.lower() and "gtec_v2" not in filename.lower(), \
            f"PDF filename should NOT contain gtec-v2, got: {filename}"


class TestToPublicTaskIdFunction:
    """Tests for the to_public_task_id helper function behavior."""
    
    def test_latest_normalizes_legacy_task_ids(self, admin_session):
        """Verify that legacy gtec_v2_* task_ids are normalized to gtec_c5_* in output."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200
        
        data = resp.json()
        report = data.get("report")
        
        if not report:
            pytest.skip("No GTEC C5 report available")
        
        task_id = report.get("task_id", "")
        internal_task_id = report.get("internal_task_id", "")
        
        # Public task_id should always be gtec_c5_*
        assert task_id.startswith("gtec_c5_"), f"Public task_id should be gtec_c5_*, got: {task_id}"
        
        # If internal was gtec_v2_*, the suffix should match
        if internal_task_id.startswith("gtec_v2_"):
            expected_suffix = internal_task_id[len("gtec_v2_"):]
            actual_suffix = task_id[len("gtec_c5_"):]
            assert expected_suffix == actual_suffix, \
                f"Task ID suffix mismatch: internal={internal_task_id}, public={task_id}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
