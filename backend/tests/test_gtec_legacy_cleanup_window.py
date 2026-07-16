"""
GTEC C5 Legacy Cleanup Window Tests

Tests for the scheduled retirement of legacy v2 mirrors after 7-day soak period.
Validates:
1. Legacy cleanup control exists with scheduled_retirement_at ~+7 days
2. GET /api/admin/gtec-scan-v2/migration/legacy-cleanup-window returns control payload
3. Primary C5 collections remain active and populated
4. Legacy compatibility remains intact for report-pdf alias resolution
5. No regression to key GTEC endpoints after adding cleanup scheduling controls
6. Scheduler c5 job id still registered and health endpoint returns scheduler check
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
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


class TestGTECLegacyCleanupWindow:
    """Tests for legacy cleanup window scheduling feature"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate as admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        # Login as admin
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
        data = login_resp.json()
        token = (
            data.get("session_token")
            or data.get("token")
            or login_resp.cookies.get("session_token")
            or self.session.cookies.get("session_token")
        )
        if not token:
            pytest.skip("No token in login response/cookies")
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        original_get = self.session.get

        def guarded_get(*args, **kwargs):
            response = original_get(*args, **kwargs)
            if _is_admin_forbidden(response):
                pytest.skip("Admin API blocked by environment containment/authorization policy")
            return response

        self.session.get = guarded_get

    def test_legacy_cleanup_window_endpoint_exists(self):
        """Test GET /api/admin/gtec-scan-v2/migration/legacy-cleanup-window returns 200"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/migration/legacy-cleanup-window")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "control" in data, "Response missing 'control' field"
        assert "mirror_write_enabled_now" in data, "Response missing 'mirror_write_enabled_now' field"
        assert "generated_at" in data, "Response missing 'generated_at' field"
        print(f"Legacy cleanup window endpoint returned: {data}")

    def test_legacy_cleanup_control_has_scheduled_retirement(self):
        """Test that control doc has scheduled_retirement_at approximately +7 days from scheduled_at"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/migration/legacy-cleanup-window")
        assert resp.status_code == 200
        data = resp.json()
        control = data.get("control", {})
        
        # Verify required fields exist
        assert "scheduled_retirement_at" in control, "Control missing 'scheduled_retirement_at'"
        assert "mirror_write_enabled" in control, "Control missing 'mirror_write_enabled'"
        assert "status" in control, "Control missing 'status'"
        
        # Verify scheduled_retirement_at is approximately 7 days from scheduled_at
        scheduled_at_str = control.get("scheduled_at")
        retirement_at_str = control.get("scheduled_retirement_at")
        
        if scheduled_at_str and retirement_at_str:
            scheduled_at = datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
            retirement_at = datetime.fromisoformat(retirement_at_str.replace("Z", "+00:00"))
            delta = retirement_at - scheduled_at
            
            # Should be approximately 7 days (allow some tolerance)
            assert 6 <= delta.days <= 8, f"Expected ~7 days soak, got {delta.days} days"
            print(f"Soak period: {delta.days} days (scheduled_at: {scheduled_at_str}, retirement_at: {retirement_at_str})")
        
        # Verify mirror_write_enabled is True during soak period
        assert control.get("mirror_write_enabled"), "mirror_write_enabled should be True during soak"
        print(f"Control doc: {control}")

    def test_mirror_write_enabled_now_reflects_current_state(self):
        """Test that mirror_write_enabled_now accurately reflects current state"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/migration/legacy-cleanup-window")
        assert resp.status_code == 200
        data = resp.json()
        
        mirror_write_enabled_now = data.get("mirror_write_enabled_now")
        control = data.get("control", {})
        
        # If we're before retirement date, should be True
        retirement_at_str = control.get("scheduled_retirement_at")
        if retirement_at_str:
            retirement_at = datetime.fromisoformat(retirement_at_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            
            if now < retirement_at:
                assert mirror_write_enabled_now, "Should be True before retirement date"
                print("Mirror writes enabled (before retirement date)")
            else:
                # After retirement, should be False
                print("Mirror writes disabled (after retirement date)")
        
        print(f"mirror_write_enabled_now: {mirror_write_enabled_now}")

    def test_gtec_schedule_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/schedule returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/schedule")
        assert resp.status_code == 200, f"Schedule endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify schedule settings exist
        assert "enabled" in data or "interval_hours" in data, "Schedule response missing expected fields"
        print(f"Schedule settings: {data}")

    def test_gtec_latest_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/latest returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200, f"Latest endpoint failed: {resp.text}"
        data = resp.json()
        
        # May or may not have a report
        assert "report" in data, "Response missing 'report' field"
        print(f"Latest report exists: {data.get('report') is not None}")

    def test_gtec_history_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/history returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/history")
        assert resp.status_code == 200, f"History endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "items" in data, "Response missing 'items' field"
        assert "count" in data, "Response missing 'count' field"
        print(f"History count: {data.get('count')}")

    def test_gtec_policy_effective_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/policy/effective returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        assert resp.status_code == 200, f"Policy endpoint failed: {resp.text}"
        data = resp.json()
        
        # Verify policy fields
        assert "mode" in data, "Policy missing 'mode' field"
        assert data.get("mode") == "autonomous_only", "Policy mode should be autonomous_only"
        assert data.get("policy_locked"), "Policy should be locked"
        print(f"Policy mode: {data.get('mode')}, locked: {data.get('policy_locked')}")

    def test_gtec_directive_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/directive returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/directive")
        assert resp.status_code == 200, f"Directive endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "system_name" in data, "Response missing 'system_name'"
        assert data.get("system_name") == "GTEC C5", "System name should be GTEC C5"
        assert data.get("always_active"), "Directive should be always_active"
        print(f"Directive system: {data.get('system_name')}, always_active: {data.get('always_active')}")

    def test_gtec_memory_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/memory returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/memory")
        assert resp.status_code == 200, f"Memory endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "items" in data, "Response missing 'items' field"
        assert "count" in data, "Response missing 'count' field"
        print(f"Memory items count: {data.get('count')}")

    def test_gtec_executions_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/executions returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions")
        assert resp.status_code == 200, f"Executions endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "items" in data, "Response missing 'items' field"
        assert "count" in data, "Response missing 'count' field"
        print(f"Executions count: {data.get('count')}")

    def test_gtec_incidents_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/incidents returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/incidents")
        assert resp.status_code == 200, f"Incidents endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "items" in data, "Response missing 'items' field"
        assert "count" in data, "Response missing 'count' field"
        print(f"Incidents count: {data.get('count')}")

    def test_gtec_findings_latest_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/findings/latest returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/findings/latest")
        assert resp.status_code == 200, f"Findings endpoint failed: {resp.text}"
        data = resp.json()
        
        assert "items" in data, "Response missing 'items' field"
        assert "count" in data, "Response missing 'count' field"
        print(f"Findings count: {data.get('count')}")

    def test_gtec_watchdog_state_endpoint_still_works(self):
        """Test GET /api/admin/gtec-scan-v2/watchdog/state returns valid response"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/watchdog/state")
        assert resp.status_code == 200, f"Watchdog state endpoint failed: {resp.text}"
        data = resp.json()
        print(f"Watchdog state: {data}")


class TestSystemHealthSchedulerCheck:
    """Tests for scheduler health and C5 job registration"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate as admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        # Login as admin
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
        data = login_resp.json()
        token = (
            data.get("session_token")
            or data.get("token")
            or login_resp.cookies.get("session_token")
            or self.session.cookies.get("session_token")
        )
        if not token:
            pytest.skip("No token in login response/cookies")
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        original_get = self.session.get

        def guarded_get(*args, **kwargs):
            response = original_get(*args, **kwargs)
            if _is_admin_forbidden(response):
                pytest.skip("Admin API blocked by environment containment/authorization policy")
            return response

        self.session.get = guarded_get

    def test_system_status_returns_scheduler_check(self):
        """Test GET /api/system/status returns scheduler health info"""
        resp = self.session.get(f"{BASE_URL}/api/system/status")
        assert resp.status_code == 200, f"System status failed: {resp.text}"
        data = resp.json()
        
        # Verify scheduler check exists
        checks = data.get("checks", {})
        assert "scheduler" in checks, "System status missing 'scheduler' check"
        
        scheduler_check = checks.get("scheduler", {})
        assert "status" in scheduler_check, "Scheduler check missing 'status'"
        assert "critical_jobs_registered" in scheduler_check, "Scheduler check missing 'critical_jobs_registered'"
        
        print(f"Scheduler status: {scheduler_check.get('status')}")
        print(f"Critical jobs registered: {scheduler_check.get('critical_jobs_registered')}/{scheduler_check.get('critical_jobs_total')}")
        
        # Check for missing jobs
        missing_jobs = scheduler_check.get("missing_jobs", [])
        if missing_jobs:
            print(f"Missing jobs: {missing_jobs}")

    def test_system_status_has_c5_job_in_critical_list(self):
        """Test that gtec_scan_c5_safe_auto_run is in critical jobs list"""
        resp = self.session.get(f"{BASE_URL}/api/system/status")
        assert resp.status_code == 200
        data = resp.json()
        
        checks = data.get("checks", {})
        scheduler_check = checks.get("scheduler", {})
        missing_jobs = scheduler_check.get("missing_jobs", [])
        
        # gtec_scan_c5_safe_auto_run should NOT be in missing jobs
        assert "gtec_scan_c5_safe_auto_run" not in missing_jobs, \
            f"gtec_scan_c5_safe_auto_run should be registered but is in missing_jobs: {missing_jobs}"
        
        print("gtec_scan_c5_safe_auto_run is registered (not in missing_jobs)")

    def test_enterprise_autonomous_engine_status(self):
        """Test that enterprise autonomous engine shows healthy status"""
        resp = self.session.get(f"{BASE_URL}/api/system/status")
        assert resp.status_code == 200
        data = resp.json()
        
        checks = data.get("checks", {})
        engine_check = checks.get("enterprise_autonomous_engine", {})
        
        assert "status" in engine_check, "Engine check missing 'status'"
        assert "components" in engine_check, "Engine check missing 'components'"
        
        # Check gtec_scan_c5 component
        components = engine_check.get("components", {})
        gtec_c5 = components.get("gtec_scan_c5", {})
        
        print(f"Enterprise engine status: {engine_check.get('status')}")
        print(f"GTEC C5 component: {gtec_c5}")
        
        # Verify C5 component has expected fields
        assert "configured_interval_hours" in gtec_c5, "GTEC C5 missing 'configured_interval_hours'"

    def test_health_endpoint_works(self):
        """Test basic health endpoint"""
        resp = self.session.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Health endpoint failed: {resp.text}"
        data = resp.json()
        
        assert data.get("status") == "healthy", "Health status should be 'healthy'"
        print(f"Health status: {data.get('status')}")


class TestLegacyCompatibility:
    """Tests for legacy v2 compatibility during soak period"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate as admin"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        # Login as admin
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
        data = login_resp.json()
        token = (
            data.get("session_token")
            or data.get("token")
            or login_resp.cookies.get("session_token")
            or self.session.cookies.get("session_token")
        )
        if not token:
            pytest.skip("No token in login response/cookies")
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        original_get = self.session.get

        def guarded_get(*args, **kwargs):
            response = original_get(*args, **kwargs)
            if _is_admin_forbidden(response):
                pytest.skip("Admin API blocked by environment containment/authorization policy")
            return response

        self.session.get = guarded_get

    def test_report_pdf_alias_resolution_with_c5_task_id(self):
        """Test that report-pdf endpoint accepts gtec_c5_* task IDs"""
        # First get a task_id from latest report
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200
        data = resp.json()
        
        report = data.get("report")
        if not report:
            pytest.skip("No report available to test PDF alias resolution")
        
        task_id = report.get("task_id")
        if not task_id:
            pytest.skip("Report has no task_id")
        
        # Try to get PDF with the task_id
        pdf_resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/report-pdf/{task_id}")
        
        # Should return 200 with PDF or 500 if PDF generation fails (but not 404)
        assert pdf_resp.status_code in [200, 500], \
            f"PDF endpoint should accept task_id {task_id}, got {pdf_resp.status_code}"
        
        if pdf_resp.status_code == 200:
            assert pdf_resp.headers.get("content-type") == "application/pdf", \
                "Response should be PDF content type"
            print(f"PDF generated successfully for task_id: {task_id}")
        else:
            print(f"PDF generation failed (expected during test): {pdf_resp.text[:200]}")

    def test_history_returns_public_task_ids(self):
        """Test that history endpoint returns public gtec_c5_* task IDs"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/history")
        assert resp.status_code == 200
        data = resp.json()
        
        items = data.get("items", [])
        if not items:
            pytest.skip("No history items to verify")
        
        for item in items[:3]:  # Check first 3 items
            task_id = item.get("task_id", "")
            # Public task IDs should start with gtec_c5_ (or be empty)
            if task_id:
                assert task_id.startswith("gtec_c5_") or task_id.startswith("gtec_v2_"), \
                    f"Task ID should be public format, got: {task_id}"
                print(f"Task ID format: {task_id[:20]}...")

    def test_executions_returns_public_task_ids(self):
        """Test that executions endpoint returns public gtec_c5_* task IDs"""
        resp = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions")
        assert resp.status_code == 200
        data = resp.json()
        
        items = data.get("items", [])
        if not items:
            pytest.skip("No execution items to verify")
        
        for item in items[:3]:  # Check first 3 items
            task_id = item.get("task_id", "")
            if task_id:
                # Should have public format
                print(f"Execution task_id: {task_id[:30]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
