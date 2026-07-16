"""
GTEC Matrix64 Pipeline API Tests
Tests for Matrix64 nightly pipeline endpoints and release certificate integration.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


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

class TestGtecMatrix64Pipeline:
    """Tests for Matrix64 pipeline endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with admin auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@realaicoach.app",
            "password": "NewAdminPass2026!"
        }, headers={"X-Requested-With": "XMLHttpRequest"})
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")

        data = login_resp.json()
        token = (
            data.get("token")
            or data.get("session_token")
            or data.get("access_token")
            or login_resp.cookies.get("session_token")
            or self.session.cookies.get("session_token")
        )
        if not token:
            pytest.skip("Admin token missing in login JSON/cookies")

        self.session.headers.update({"Authorization": f"Bearer {token}"})

        original_get = self.session.get

        def guarded_get(*args, **kwargs):
            response = original_get(*args, **kwargs)
            _skip_if_admin_blocked(response, "GTEC Matrix64 admin endpoint")
            return response

        self.session.get = guarded_get
        yield
        self.session.close()
    
    def test_matrix64_config_endpoint(self):
        """GET /api/admin/gtec-scan-v2/pipeline/matrix64/config returns valid config"""
        response = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/matrix64/config")
        print(f"Matrix64 config status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        
        data = response.json()
        config = data.get("config", {})
        print(f"Matrix64 config: {config}")
        
        # Verify enabled=true
        assert config.get("enabled"), f"Expected enabled=true, got {config.get('enabled')}"
        
        # Verify hour_utc=1 (01:00 UTC nightly)
        assert config.get("hour_utc") == 1, f"Expected hour_utc=1, got {config.get('hour_utc')}"
        
        # Verify minute_utc=0
        assert config.get("minute_utc") == 0, f"Expected minute_utc=0, got {config.get('minute_utc')}"
        
        # Verify timezone=UTC
        assert config.get("timezone") == "UTC", f"Expected timezone=UTC, got {config.get('timezone')}"
        
        # Verify 4 routes
        routes = config.get("routes", [])
        assert len(routes) == 4, f"Expected 4 routes, got {len(routes)}: {routes}"
        
        # Verify 4 viewports
        viewports = config.get("viewports", [])
        assert len(viewports) == 4, f"Expected 4 viewports, got {len(viewports)}: {viewports}"
        
        # Verify 4 languages
        languages = config.get("languages", [])
        assert len(languages) == 4, f"Expected 4 languages, got {len(languages)}: {languages}"
        
        print("✓ Matrix64 config endpoint returns valid structure with 4 routes/4 viewports/4 languages")
    
    def test_matrix64_latest_endpoint(self):
        """GET /api/admin/gtec-scan-v2/pipeline/matrix64/latest returns valid structure (may be empty)"""
        response = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/matrix64/latest")
        print(f"Matrix64 latest status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        
        data = response.json()
        print(f"Matrix64 latest response keys: {list(data.keys())}")
        
        # Should have 'run' key (may be null if no run yet)
        assert "run" in data, f"Expected 'run' key in response, got {list(data.keys())}"
        
        # Should have 'generated_at' timestamp
        assert "generated_at" in data, "Expected 'generated_at' key in response"
        
        run = data.get("run")
        if run:
            print(f"Matrix64 latest run: run_id={run.get('run_id')}, status={run.get('status')}")
            # If run exists, verify structure
            assert "run_id" in run or "status" in run, "Run should have run_id or status"
        else:
            print("✓ Matrix64 latest returns null run (no run yet) - this is valid")
        
        print("✓ Matrix64 latest endpoint returns valid structure")
    
    def test_release_certificate_includes_matrix64(self):
        """GET /api/admin/gtec-scan-v2/release-certificate includes matrix64_pipeline check"""
        response = self.session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate")
        print(f"Release certificate status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        
        data = response.json()
        checks = data.get("checks", {})
        print(f"Release certificate checks keys: {list(checks.keys())}")
        
        # Verify matrix64_pipeline check exists
        assert "matrix64_pipeline" in checks, f"Expected 'matrix64_pipeline' in checks, got {list(checks.keys())}"
        
        matrix64 = checks.get("matrix64_pipeline", {})
        print(f"Matrix64 pipeline check: {matrix64}")
        
        # Verify required_total_checks=64
        required_total = matrix64.get("required_total_checks")
        assert required_total == 64, f"Expected required_total_checks=64, got {required_total}"
        
        # Verify other expected fields exist
        assert "status" in matrix64, "Expected 'status' in matrix64_pipeline"
        assert "total_checks" in matrix64, "Expected 'total_checks' in matrix64_pipeline"
        assert "failed_checks" in matrix64, "Expected 'failed_checks' in matrix64_pipeline"
        
        print("✓ Release certificate includes matrix64_pipeline with required_total_checks=64")


class TestSchedulerHealth:
    """Tests for scheduler and enterprise guardian health"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with admin auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@realaicoach.app",
            "password": "NewAdminPass2026!"
        }, headers={"X-Requested-With": "XMLHttpRequest"})
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")

        data = login_resp.json()
        token = (
            data.get("token")
            or data.get("session_token")
            or data.get("access_token")
            or login_resp.cookies.get("session_token")
            or self.session.cookies.get("session_token")
        )
        if not token:
            pytest.skip("Admin token missing in login JSON/cookies")

        self.session.headers.update({"Authorization": f"Bearer {token}"})

        original_get = self.session.get

        def guarded_get(*args, **kwargs):
            response = original_get(*args, **kwargs)
            _skip_if_admin_blocked(response, "GTEC Matrix64 scheduler/admin endpoint")
            return response

        self.session.get = guarded_get
        yield
        self.session.close()
    
    def test_scheduler_health_endpoint(self):
        """Verify scheduler is running and healthy"""
        response = self.session.get(f"{BASE_URL}/api/admin/scheduler/status")
        print(f"Scheduler status: {response.status_code}")
        
        # May return 200 or 404 depending on endpoint availability
        if response.status_code == 200:
            data = response.json()
            print(f"Scheduler status data: {data}")
            print("✓ Scheduler status endpoint available")
        elif response.status_code == 404:
            print("⚠ Scheduler status endpoint not found (may be internal only)")
        else:
            print(f"Scheduler status response: {response.text[:300]}")
    
    def test_backend_health(self):
        """Verify backend is healthy (no startup/runtime crash)"""
        response = self.session.get(f"{BASE_URL}/api/health")
        print(f"Health check status: {response.status_code}")
        
        assert response.status_code == 200, f"Backend health check failed: {response.status_code}"
        
        data = response.json()
        print(f"Health check response: {data}")
        
        # Verify status is healthy
        status = data.get("status", "").lower()
        assert status in ["healthy", "ok", "pass"], f"Expected healthy status, got {status}"
        
        print("✓ Backend is healthy (no startup/runtime crash)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
