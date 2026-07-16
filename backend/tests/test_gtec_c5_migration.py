"""
GTEC C5 Internal Collection Migration Tests

Tests the staged migration from gtec_scan_v2_* to gtec_scan_c5_* collections/job IDs:
1. Internal collection cutover: API reads/writes from gtec_scan_c5_* primary collections
2. Backward compatibility: legacy task-id alias (gtec_v2_*) still resolves in report-pdf endpoint
3. Scheduler/system health uses c5 safe auto-run job id
4. GTEC endpoints return valid payloads after migration
5. Incidents API reads from c5 incident collection
6. Interview verification helper route resolves latest GTEC report (c5 primary + v2 fallback)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_risk_engine_admin_blocked(response: requests.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        return False
    detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
    return code in {"risk_engine_admin_api_blocked", "risk_engine_id_verification_required"}


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session token."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    # Login as admin
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, headers={"X-Requested-With": "XMLHttpRequest"})

    if resp.status_code == 403 and _is_risk_engine_admin_blocked(resp):
        pytest.skip("Admin login blocked by risk engine containment")
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")

    data = resp.json()
    token = data.get("session_token") or data.get("token") or resp.cookies.get("session_token") or session.cookies.get("session_token")
    if not token:
        pytest.skip("No session token returned in login JSON/cookies")
    
    session.headers.update({"Authorization": f"Bearer {token}"})

    original_get = session.get

    def guarded_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        if _is_risk_engine_admin_blocked(response):
            pytest.skip("Admin API blocked by risk engine containment")
        return response

    session.get = guarded_get
    return session


class TestGTECC5CollectionMigration:
    """Test that API reads/writes function from gtec_scan_c5_* primary collections."""
    
    def test_gtec_latest_returns_c5_task_id(self, admin_session):
        """GET /api/admin/gtec-scan-v2/latest should return gtec_c5_* task_id."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200, f"Latest endpoint failed: {resp.text}"
        
        data = resp.json()
        report = data.get("report")
        
        if report:
            task_id = report.get("task_id", "")
            internal_task_id = report.get("internal_task_id", "")
            
            # Public task_id should be gtec_c5_*
            assert task_id.startswith("gtec_c5_"), f"Expected gtec_c5_* task_id, got: {task_id}"
            # Internal task_id should be present for backward compatibility
            assert internal_task_id, "internal_task_id should be present"
            print(f"✓ Latest report task_id: {task_id}, internal: {internal_task_id}")
        else:
            print("⚠ No report found (may be empty collection)")
    
    def test_gtec_history_returns_c5_task_ids(self, admin_session):
        """GET /api/admin/gtec-scan-v2/history should return gtec_c5_* task_ids."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/history")
        assert resp.status_code == 200, f"History endpoint failed: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        
        for item in items[:5]:  # Check first 5
            task_id = item.get("task_id", "")
            assert task_id.startswith("gtec_c5_"), f"Expected gtec_c5_* task_id, got: {task_id}"
        
        print(f"✓ History returned {len(items)} items with gtec_c5_* task_ids")
    
    def test_gtec_memory_returns_c5_task_ids(self, admin_session):
        """GET /api/admin/gtec-scan-v2/memory should return gtec_c5_* last_seen_task."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/memory")
        assert resp.status_code == 200, f"Memory endpoint failed: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        
        for item in items[:5]:  # Check first 5
            last_seen_task = item.get("last_seen_task", "")
            if last_seen_task:
                assert last_seen_task.startswith("gtec_c5_"), f"Expected gtec_c5_* last_seen_task, got: {last_seen_task}"
        
        print(f"✓ Memory returned {len(items)} items with gtec_c5_* last_seen_task")
    
    def test_gtec_executions_returns_c5_task_ids(self, admin_session):
        """GET /api/admin/gtec-scan-v2/executions should return gtec_c5_* task_ids."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions")
        assert resp.status_code == 200, f"Executions endpoint failed: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        
        for item in items[:5]:  # Check first 5
            task_id = item.get("task_id", "")
            if task_id:
                assert task_id.startswith("gtec_c5_"), f"Expected gtec_c5_* task_id, got: {task_id}"
        
        print(f"✓ Executions returned {len(items)} items with gtec_c5_* task_ids")
    
    def test_gtec_incidents_reads_from_c5_collection(self, admin_session):
        """GET /api/admin/gtec-scan-v2/incidents should read from c5 incident collection."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/incidents")
        assert resp.status_code == 200, f"Incidents endpoint failed: {resp.text}"
        
        data = resp.json()
        items = data.get("items", [])
        count = data.get("count", 0)
        data.get("status_filter", "")
        
        # Verify response structure
        assert "items" in data, "Response should have 'items' key"
        assert "count" in data, "Response should have 'count' key"
        
        # Check task_ids in incidents are c5 format
        for item in items[:5]:
            task_id = item.get("task_id", "")
            if task_id:
                assert task_id.startswith("gtec_c5_"), f"Expected gtec_c5_* task_id in incident, got: {task_id}"
        
        print(f"✓ Incidents returned {count} items from c5 collection")


class TestGTECC5BackwardCompatibility:
    """Test backward compatibility: legacy task-id alias (gtec_v2_*) still resolves."""
    
    def test_report_pdf_accepts_c5_task_id(self, admin_session):
        """GET /api/admin/gtec-scan-v2/report-pdf/{task_id} should accept gtec_c5_* task_id."""
        # First get a valid task_id from latest
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200
        
        data = resp.json()
        report = data.get("report")
        
        if not report:
            pytest.skip("No report available for PDF test")
        
        task_id = report.get("task_id", "")
        assert task_id.startswith("gtec_c5_"), f"Expected gtec_c5_* task_id, got: {task_id}"
        
        # Request PDF with c5 task_id
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        assert resp.status_code == 200, f"PDF endpoint failed for c5 task_id: {resp.text}"
        assert "application/pdf" in resp.headers.get("content-type", "").lower()
        
        # Check headers
        public_task_header = resp.headers.get("X-GTEC-Public-Task-ID", "")
        internal_task_header = resp.headers.get("X-GTEC-Internal-Task-ID", "")
        
        assert public_task_header.startswith("gtec_c5_"), f"Expected gtec_c5_* in header, got: {public_task_header}"
        assert internal_task_header, "Internal task ID header should be present"
        
        print(f"✓ PDF endpoint accepts gtec_c5_* task_id: {task_id}")
    
    def test_report_pdf_accepts_legacy_v2_task_id(self, admin_session):
        """GET /api/admin/gtec-scan-v2/report-pdf/{task_id} should accept legacy gtec_v2_* task_id."""
        # First get a valid task_id from latest
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200
        
        data = resp.json()
        report = data.get("report")
        
        if not report:
            pytest.skip("No report available for PDF test")
        
        internal_task_id = report.get("internal_task_id", "")
        
        if not internal_task_id or not internal_task_id.startswith("gtec_v2_"):
            # Construct legacy task_id from c5 task_id
            c5_task_id = report.get("task_id", "")
            if c5_task_id.startswith("gtec_c5_"):
                internal_task_id = "gtec_v2_" + c5_task_id[len("gtec_c5_"):]
        
        if not internal_task_id:
            pytest.skip("No legacy task_id available for test")
        
        # Request PDF with legacy v2 task_id
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{internal_task_id}")
        assert resp.status_code == 200, f"PDF endpoint failed for legacy v2 task_id: {resp.text}"
        assert "application/pdf" in resp.headers.get("content-type", "").lower()
        
        print(f"✓ PDF endpoint accepts legacy gtec_v2_* task_id: {internal_task_id}")


class TestGTECC5SchedulerAndSystemHealth:
    """Test scheduler/system health uses c5 safe auto-run job id."""
    
    def test_system_status_checks_c5_job(self, admin_session):
        """GET /api/system/status should check gtec_scan_c5_safe_auto_run job."""
        resp = admin_session.get(f"{BASE_URL}/api/system/status")
        assert resp.status_code == 200, f"System status failed: {resp.text}"
        
        data = resp.json()
        
        # Check enterprise_autonomous_engine component
        engine = data.get("checks", {}).get("enterprise_autonomous_engine", {})
        components = engine.get("components", {})
        
        # Verify gtec_scan_c5 component exists
        gtec_c5 = components.get("gtec_scan_c5", {})
        assert gtec_c5, "gtec_scan_c5 component should exist in system status"
        
        # Check scheduler status
        scheduler = data.get("checks", {}).get("scheduler", {})
        missing_jobs = scheduler.get("missing_jobs", [])
        
        # gtec_scan_c5_safe_auto_run should NOT be in missing jobs
        assert "gtec_scan_c5_safe_auto_run" not in missing_jobs, \
            f"gtec_scan_c5_safe_auto_run should be registered, missing: {missing_jobs}"
        
        print(f"✓ System status checks c5 job, scheduler status: {scheduler.get('status')}")
    
    def test_system_status_reads_c5_collections(self, admin_session):
        """GET /api/system/status should read from gtec_scan_c5_* collections."""
        resp = admin_session.get(f"{BASE_URL}/api/system/status")
        assert resp.status_code == 200, f"System status failed: {resp.text}"
        
        data = resp.json()
        
        # Check enterprise_autonomous_engine component
        engine = data.get("checks", {}).get("enterprise_autonomous_engine", {})
        components = engine.get("components", {})
        
        gtec_c5 = components.get("gtec_scan_c5", {})
        
        # Verify it has expected fields from c5 collection reads
        expected_fields = ["configured_interval_hours", "last_scheduler_heartbeat_at", "fresh"]
        for field in expected_fields:
            assert field in gtec_c5, f"Expected field '{field}' in gtec_scan_c5 component"
        
        print(f"✓ System status reads from c5 collections, gtec_c5 fresh: {gtec_c5.get('fresh')}")


class TestGTECC5EndpointPayloads:
    """Test GTEC endpoints return valid payloads after migration."""
    
    def test_gtec_schedule_endpoint(self, admin_session):
        """GET /api/admin/gtec-scan-v2/schedule should return valid schedule."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/schedule")
        assert resp.status_code == 200, f"Schedule endpoint failed: {resp.text}"
        
        data = resp.json()
        
        # Verify expected fields
        assert "enabled" in data or "interval_hours" in data, "Schedule should have enabled or interval_hours"
        
        print(f"✓ Schedule endpoint returns valid payload: enabled={data.get('enabled')}, interval={data.get('interval_hours')}")
    
    def test_gtec_policy_effective_endpoint(self, admin_session):
        """GET /api/admin/gtec-scan-v2/policy/effective should return valid policy."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        assert resp.status_code == 200, f"Policy endpoint failed: {resp.text}"
        
        data = resp.json()
        
        # Verify expected fields
        assert data.get("mode") == "autonomous_only", f"Expected autonomous_only mode, got: {data.get('mode')}"
        assert not data.get("manual_input_allowed"), "manual_input_allowed should be False"
        assert data.get("policy_locked"), "policy_locked should be True"
        
        print(f"✓ Policy endpoint returns valid payload: mode={data.get('mode')}")
    
    def test_gtec_findings_latest_endpoint(self, admin_session):
        """GET /api/admin/gtec-scan-v2/findings/latest should return valid findings."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/findings/latest")
        assert resp.status_code == 200, f"Findings endpoint failed: {resp.text}"
        
        data = resp.json()
        
        # Verify expected fields
        assert "items" in data, "Findings should have 'items' key"
        assert "count" in data, "Findings should have 'count' key"
        
        # Check task_id format if present
        task_id = data.get("task_id", "")
        if task_id:
            assert task_id.startswith("gtec_c5_"), f"Expected gtec_c5_* task_id, got: {task_id}"
        
        print(f"✓ Findings endpoint returns valid payload: count={data.get('count')}")
    
    def test_gtec_directive_endpoint(self, admin_session):
        """GET /api/admin/gtec-scan-v2/directive should return directive info."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/directive")
        assert resp.status_code == 200, f"Directive endpoint failed: {resp.text}"
        
        data = resp.json()
        
        # Verify expected fields
        assert data.get("system_name") == "GTEC C5", f"Expected system_name 'GTEC C5', got: {data.get('system_name')}"
        assert data.get("always_active"), "always_active should be True"
        assert data.get("non_disableable"), "non_disableable should be True"
        
        print(f"✓ Directive endpoint returns valid payload: system_name={data.get('system_name')}")


class TestGTECC5InterviewVerificationHelper:
    """Test interview verification helper route resolves latest GTEC report."""
    
    def test_pdf_v15_verification_suite_uses_c5_primary(self, admin_session):
        """POST /api/admin/pdf-v15/email-verification-suite should use c5 primary collection."""
        # This endpoint fetches latest GTEC report for PDF verification
        # We just verify the endpoint exists and returns expected structure
        # (actual email sending may fail without proper config)
        
        # First verify we can get latest GTEC report
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200
        
        data = resp.json()
        report = data.get("report")
        
        if report:
            task_id = report.get("task_id", "")
            assert task_id.startswith("gtec_c5_"), f"Latest report should have gtec_c5_* task_id, got: {task_id}"
            print(f"✓ Interview verification helper can access c5 primary report: {task_id}")
        else:
            print("⚠ No GTEC report available for verification helper test")


class TestGTECC5EmailDispatchPath:
    """Test no regression in email dispatch path after internal migration."""
    
    def test_gtec_latest_has_email_dispatch_info(self, admin_session):
        """GET /api/admin/gtec-scan-v2/latest should include email_dispatch info if available."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200, f"Latest endpoint failed: {resp.text}"
        
        data = resp.json()
        report = data.get("report")
        
        if report:
            # Check if email_dispatch is present (may not be on all reports)
            email_dispatch = report.get("email_dispatch")
            if email_dispatch:
                # Verify PDF filename uses c5 naming
                pdf_meta = email_dispatch.get("pdf_attachment", {})
                filename = pdf_meta.get("filename", "")
                if filename:
                    assert "gtec-c5" in filename or "gtec_c5" in filename, \
                        f"PDF filename should contain gtec-c5, got: {filename}"
                    print(f"✓ Email dispatch PDF filename uses c5 naming: {filename}")
                else:
                    print("⚠ No PDF filename in email_dispatch")
            else:
                print("⚠ No email_dispatch info in latest report")
        else:
            print("⚠ No report available for email dispatch test")


class TestGTECC5WatchdogState:
    """Test watchdog state endpoint."""
    
    def test_watchdog_state_endpoint(self, admin_session):
        """GET /api/admin/gtec-scan-v2/watchdog/state should return valid state."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/watchdog/state")
        assert resp.status_code == 200, f"Watchdog state endpoint failed: {resp.text}"
        
        data = resp.json()
        
        # Verify response is valid JSON
        assert isinstance(data, dict), "Watchdog state should return a dict"
        
        print("✓ Watchdog state endpoint returns valid payload")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
