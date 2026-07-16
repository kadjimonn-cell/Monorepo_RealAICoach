"""
Feature 27 - Preview Browser E2E Stabilization Tests
Tests for P0/P1 requirements:
- P0: Admin Operations Console preview card renders with key evidence fields
- P0: Preview card shows reason code and lane status fields
- P1: GET /api/admin/platform-health/preview-browser-e2e/latest returns deterministic schema
- P1: POST /api/admin/platform-health/preview-browser-e2e/run accepts admin+CSRF
- P1: latest.history includes status_reason_code/external_lane_status/localhost_fallback_status
- P1: GET /api/admin/platform-health/preview-adapter-live-check returns stable payload
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "http://localhost:8001"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestPreviewBrowserE2EEndpoints:
    """Test suite for Preview Browser E2E endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with admin authentication"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"  # CSRF header
        })
        
        # Login as admin
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        
        yield
        
        self.session.close()
    
    # ============================================
    # P1: GET /api/admin/platform-health/preview-browser-e2e/latest
    # ============================================
    
    def test_preview_browser_e2e_latest_returns_200(self):
        """P1: Endpoint returns 200 for authenticated admin"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_preview_browser_e2e_latest_has_deterministic_schema(self):
        """P1: Response has deterministic schema with latest/history/trend"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify top-level keys
        assert "latest" in data, "Missing 'latest' key in response"
        assert "history" in data, "Missing 'history' key in response"
        assert "trend" in data, "Missing 'trend' key in response"
        assert "alert_state" in data, "Missing 'alert_state' key in response"
        assert "heartbeat" in data, "Missing 'heartbeat' key in response"
        assert "job_id" in data, "Missing 'job_id' key in response"
    
    def test_preview_browser_e2e_latest_trend_structure(self):
        """P1: Trend object has correct structure"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200
        data = response.json()
        trend = data.get("trend", {})
        
        # Verify trend structure
        assert "window_days" in trend, "Missing 'window_days' in trend"
        assert "total" in trend, "Missing 'total' in trend"
        assert "pass_count" in trend, "Missing 'pass_count' in trend"
        assert "fail_count" in trend, "Missing 'fail_count' in trend"
        assert "blocked_count" in trend, "Missing 'blocked_count' in trend"
        assert "pass_rate" in trend, "Missing 'pass_rate' in trend"
    
    def test_preview_browser_e2e_latest_has_status_reason_code(self):
        """P0/P1: Latest object includes status_reason_code field"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        # If there's a latest run, verify status_reason_code exists
        if latest:
            assert "status_reason_code" in latest, "Missing 'status_reason_code' in latest"
            # Verify it's not empty/null when there's a run
            if latest.get("run_id"):
                assert latest.get("status_reason_code"), "status_reason_code should not be empty when run exists"
    
    def test_preview_browser_e2e_latest_has_lane_status_fields(self):
        """P0/P1: Latest object includes external_lane_status and localhost_fallback_status"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        # If there's a latest run, verify lane status fields exist
        if latest and latest.get("run_id"):
            assert "external_lane_status" in latest, "Missing 'external_lane_status' in latest"
            assert "localhost_fallback_status" in latest, "Missing 'localhost_fallback_status' in latest"
    
    def test_preview_browser_e2e_history_includes_projection_fields(self):
        """P1: History items include status_reason_code/external_lane_status/localhost_fallback_status"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])
        
        # If there's history, verify each item has the required fields
        for item in history:
            assert "status_reason_code" in item, f"Missing 'status_reason_code' in history item: {item}"
            assert "external_lane_status" in item, f"Missing 'external_lane_status' in history item: {item}"
            assert "localhost_fallback_status" in item, f"Missing 'localhost_fallback_status' in history item: {item}"
    
    def test_preview_browser_e2e_latest_availability_contract(self):
        """P1: Latest includes availability_contract with deterministic fields"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        # If there's a latest run with availability_contract
        if latest and latest.get("availability_contract"):
            contract = latest["availability_contract"]
            assert "status" in contract, "Missing 'status' in availability_contract"
            assert "status_reason_code" in contract, "Missing 'status_reason_code' in availability_contract"
            assert "deterministic_outcome" in contract, "Missing 'deterministic_outcome' in availability_contract"
            assert "allowed_statuses" in contract, "Missing 'allowed_statuses' in availability_contract"
    
    def test_preview_browser_e2e_latest_requires_admin(self):
        """P1: Endpoint requires admin authentication"""
        # Create new session without auth
        unauth_session = requests.Session()
        unauth_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = unauth_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest"
        )
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        unauth_session.close()
    
    # ============================================
    # P1: POST /api/admin/platform-health/preview-browser-e2e/run
    # ============================================
    
    def test_preview_browser_e2e_run_accepts_admin_with_csrf(self):
        """P1: POST run endpoint accepts admin with CSRF header"""
        response = self.session.post(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/run?triggered_by=manual:admin"
        )
        # Should return 200 (accepted) or 409 (already running)
        assert response.status_code in [200, 409], f"Expected 200 or 409, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("accepted") == True, "Expected 'accepted: true' in response"
            assert data.get("status") == "running", "Expected 'status: running' in response"
            assert "started_at" in data, "Missing 'started_at' in response"
            assert "status_endpoint" in data, "Missing 'status_endpoint' in response"
    
    def test_preview_browser_e2e_run_requires_admin(self):
        """P1: POST run endpoint requires admin authentication"""
        # Create new session without auth
        unauth_session = requests.Session()
        unauth_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = unauth_session.post(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/run?triggered_by=manual:admin"
        )
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        unauth_session.close()
    
    # ============================================
    # P1: GET /api/admin/platform-health/preview-adapter-live-check
    # ============================================
    
    def test_preview_adapter_live_check_returns_200(self):
        """P1: Live check endpoint returns 200 for authenticated admin"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-adapter-live-check"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_preview_adapter_live_check_has_stable_payload(self):
        """P1: Live check returns stable payload with root/api check results"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-adapter-live-check"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify top-level keys
        assert "status" in data, "Missing 'status' key in response"
        assert "checked_at" in data, "Missing 'checked_at' key in response"
        assert "base_url" in data, "Missing 'base_url' key in response"
        assert "checks" in data, "Missing 'checks' key in response"
    
    def test_preview_adapter_live_check_has_preview_root_check(self):
        """P1: Live check includes preview_root check result"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-adapter-live-check"
        )
        assert response.status_code == 200
        data = response.json()
        checks = data.get("checks", {})
        
        assert "preview_root" in checks, "Missing 'preview_root' in checks"
        preview_root = checks["preview_root"]
        assert "url" in preview_root, "Missing 'url' in preview_root"
        assert "status_code" in preview_root, "Missing 'status_code' in preview_root"
        assert "ok" in preview_root, "Missing 'ok' in preview_root"
    
    def test_preview_adapter_live_check_has_api_health_check(self):
        """P1: Live check includes api_health check result"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-adapter-live-check"
        )
        assert response.status_code == 200
        data = response.json()
        checks = data.get("checks", {})
        
        assert "api_health" in checks, "Missing 'api_health' in checks"
        api_health = checks["api_health"]
        assert "url" in api_health, "Missing 'url' in api_health"
        assert "status_code" in api_health, "Missing 'status_code' in api_health"
        assert "ok" in api_health, "Missing 'ok' in api_health"
    
    def test_preview_adapter_live_check_has_cache_info(self):
        """P1: Live check includes cache information"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-adapter-live-check"
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "cached" in data, "Missing 'cached' key in response"
        assert "cache_ttl_seconds" in data, "Missing 'cache_ttl_seconds' key in response"
    
    def test_preview_adapter_live_check_force_refresh(self):
        """P1: Live check with force=true bypasses cache"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-adapter-live-check?force=true"
        )
        assert response.status_code == 200
        data = response.json()
        
        # When force=true, cached should be false
        assert data.get("cached") == False, "Expected 'cached: false' when force=true"
    
    def test_preview_adapter_live_check_requires_admin(self):
        """P1: Live check endpoint requires admin authentication"""
        # Create new session without auth
        unauth_session = requests.Session()
        unauth_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = unauth_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-adapter-live-check"
        )
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        unauth_session.close()


class TestPreviewBrowserE2EDeterministicFailure:
    """Test suite for deterministic failure persistence when Playwright runtime is missing"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with admin authentication"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as admin
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        
        yield
        
        self.session.close()
    
    def test_latest_shows_deterministic_failure_when_playwright_missing(self):
        """P1: When Playwright runtime is missing, latest shows deterministic failure record"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        # If there's a run and it failed due to Playwright missing
        if latest and latest.get("run_id"):
            status = latest.get("status", "").lower()
            reason_code = latest.get("status_reason_code", "")
            
            # If the failure is due to Playwright runtime missing
            if "playwright" in reason_code.lower() or "runtime" in reason_code.lower():
                assert status in ["fail", "blocked"], f"Expected fail/blocked status for Playwright missing, got {status}"
                assert reason_code, "status_reason_code should not be empty for Playwright failure"
                print(f"Verified deterministic failure: status={status}, reason_code={reason_code}")
    
    def test_latest_has_blocking_reason_for_runtime_failure(self):
        """P1: When runtime fails, blocking_reason contains error details"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest?limit=5&window_days=7"
        )
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        # If there's a run with a blocking reason
        if latest and latest.get("blocking_reason"):
            blocking_reason = latest["blocking_reason"]
            assert isinstance(blocking_reason, str), "blocking_reason should be a string"
            assert len(blocking_reason) > 0, "blocking_reason should not be empty"
            print(f"Blocking reason: {blocking_reason[:200]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
