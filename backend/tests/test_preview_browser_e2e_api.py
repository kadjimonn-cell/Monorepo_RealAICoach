"""
Test Preview Browser E2E API Contract Verification

Tests the preview-browser-e2e latest endpoint to verify:
1. Deterministic status contract fields are present
2. status_reason_code is available in latest run payload
3. localhost fallback metadata fields are available when external preview is blocked
4. Admin endpoint exposes reason/lane fields
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text[:200]}")
    
    return session


class TestPreviewBrowserE2ELatestEndpoint:
    """Tests for /admin/platform-health/preview-browser-e2e/latest endpoint"""
    
    def test_endpoint_requires_admin_auth(self):
        """Verify endpoint requires admin authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_endpoint_returns_200_for_admin(self, admin_session):
        """Verify endpoint returns 200 for authenticated admin"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:300]}"
    
    def test_response_has_latest_field(self, admin_session):
        """Verify response contains 'latest' field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        assert "latest" in data, "Response missing 'latest' field"
    
    def test_response_has_trend_field(self, admin_session):
        """Verify response contains 'trend' field with expected structure"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        assert "trend" in data, "Response missing 'trend' field"
        trend = data["trend"]
        assert "window_days" in trend, "Trend missing 'window_days'"
        assert "total" in trend, "Trend missing 'total'"
        assert "pass_count" in trend, "Trend missing 'pass_count'"
        assert "fail_count" in trend, "Trend missing 'fail_count'"
        assert "blocked_count" in trend, "Trend missing 'blocked_count'"
        assert "pass_rate" in trend, "Trend missing 'pass_rate'"
    
    def test_response_has_alert_state_field(self, admin_session):
        """Verify response contains 'alert_state' field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        assert "alert_state" in data, "Response missing 'alert_state' field"
    
    def test_response_has_heartbeat_field(self, admin_session):
        """Verify response contains 'heartbeat' field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        assert "heartbeat" in data, "Response missing 'heartbeat' field"
    
    def test_response_has_history_field(self, admin_session):
        """Verify response contains 'history' field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data, "Response missing 'history' field"
        assert isinstance(data["history"], list), "'history' should be a list"


class TestPreviewBrowserE2EStatusReasonCode:
    """Tests for status_reason_code field in preview-browser-e2e payload"""
    
    def test_latest_has_status_reason_code_field(self, admin_session):
        """Verify latest run payload has status_reason_code field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        # If there's a latest run, it should have status_reason_code
        if latest and latest.get("run_id"):
            assert "status_reason_code" in latest, "Latest run missing 'status_reason_code' field"
            print(f"status_reason_code: {latest.get('status_reason_code')}")
    
    def test_history_items_have_status_reason_code(self, admin_session):
        """Verify history items have status_reason_code field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])
        
        # Check first few history items if available
        for idx, item in enumerate(history[:3]):
            assert "status_reason_code" in item, f"History item {idx} missing 'status_reason_code'"
            print(f"History item {idx} status_reason_code: {item.get('status_reason_code')}")


class TestPreviewBrowserE2ELaneFields:
    """Tests for external_lane_status and localhost_fallback_status fields"""
    
    def test_latest_has_external_lane_status(self, admin_session):
        """Verify latest run has external_lane_status field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        if latest and latest.get("run_id"):
            assert "external_lane_status" in latest, "Latest run missing 'external_lane_status' field"
            print(f"external_lane_status: {latest.get('external_lane_status')}")
    
    def test_latest_has_localhost_fallback_status(self, admin_session):
        """Verify latest run has localhost_fallback_status field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        if latest and latest.get("run_id"):
            assert "localhost_fallback_status" in latest, "Latest run missing 'localhost_fallback_status' field"
            print(f"localhost_fallback_status: {latest.get('localhost_fallback_status')}")
    
    def test_history_items_have_lane_fields(self, admin_session):
        """Verify history items have lane status fields"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])
        
        for idx, item in enumerate(history[:3]):
            assert "external_lane_status" in item, f"History item {idx} missing 'external_lane_status'"
            assert "localhost_fallback_status" in item, f"History item {idx} missing 'localhost_fallback_status'"
            print(f"History item {idx}: external={item.get('external_lane_status')}, localhost={item.get('localhost_fallback_status')}")


class TestPreviewBrowserE2ELocalhostFallbackMetadata:
    """Tests for localhost fallback metadata when external preview is blocked"""
    
    def test_latest_has_localhost_fallback_object(self, admin_session):
        """Verify latest run has localhost_fallback object with metadata"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        if latest and latest.get("run_id"):
            assert "localhost_fallback" in latest, "Latest run missing 'localhost_fallback' object"
            fallback = latest.get("localhost_fallback", {})
            
            # Verify expected fields in localhost_fallback object
            expected_fields = ["executed", "base_url", "pass", "pass_count", "fail_count", "checks_count"]
            for field in expected_fields:
                assert field in fallback, f"localhost_fallback missing '{field}' field"
            
            print(f"localhost_fallback: executed={fallback.get('executed')}, pass={fallback.get('pass')}, pass_count={fallback.get('pass_count')}, fail_count={fallback.get('fail_count')}")
    
    def test_latest_has_availability_contract(self, admin_session):
        """Verify latest run has availability_contract with deterministic fields"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        if latest and latest.get("run_id"):
            assert "availability_contract" in latest, "Latest run missing 'availability_contract' object"
            contract = latest.get("availability_contract", {})
            
            # Verify expected fields in availability_contract
            expected_fields = ["status", "status_reason_code", "external_probe", "localhost_fallback_executed", "deterministic_outcome", "allowed_statuses"]
            for field in expected_fields:
                assert field in contract, f"availability_contract missing '{field}' field"
            
            # Verify allowed_statuses contains expected values
            allowed = contract.get("allowed_statuses", [])
            assert "PASS" in allowed, "allowed_statuses missing 'PASS'"
            assert "FAIL" in allowed, "allowed_statuses missing 'FAIL'"
            assert "BLOCKED" in allowed, "allowed_statuses missing 'BLOCKED'"
            
            print(f"availability_contract: status={contract.get('status')}, reason_code={contract.get('status_reason_code')}, deterministic={contract.get('deterministic_outcome')}")


class TestPreviewBrowserE2EBlockingReason:
    """Tests for blocking_reason field"""
    
    def test_latest_has_blocking_reason_field(self, admin_session):
        """Verify latest run has blocking_reason field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        if latest and latest.get("run_id"):
            assert "blocking_reason" in latest, "Latest run missing 'blocking_reason' field"
            print(f"blocking_reason: {latest.get('blocking_reason')}")
    
    def test_history_items_have_blocking_reason(self, admin_session):
        """Verify history items have blocking_reason field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])
        
        for idx, item in enumerate(history[:3]):
            assert "blocking_reason" in item, f"History item {idx} missing 'blocking_reason'"


class TestPreviewBrowserE2ETransitionEvent:
    """Tests for transition_event field"""
    
    def test_latest_has_transition_event(self, admin_session):
        """Verify latest run has transition_event field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        if latest and latest.get("run_id"):
            assert "transition_event" in latest, "Latest run missing 'transition_event' field"
            transition = latest.get("transition_event", {})
            print(f"transition_event: changed={transition.get('changed')}, transition={transition.get('transition')}")
    
    def test_history_items_have_transition_event(self, admin_session):
        """Verify history items have transition_event field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])
        
        for idx, item in enumerate(history[:3]):
            assert "transition_event" in item, f"History item {idx} missing 'transition_event'"


class TestPreviewBrowserE2EChecksAndScreenshots:
    """Tests for checks and screenshots fields"""
    
    def test_latest_has_checks_count(self, admin_session):
        """Verify latest run has checks_count field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        if latest and latest.get("run_id"):
            assert "checks_count" in latest, "Latest run missing 'checks_count' field"
            print(f"checks_count: {latest.get('checks_count')}")
    
    def test_latest_has_screenshots_count(self, admin_session):
        """Verify latest run has screenshots_count field"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        latest = data.get("latest", {})
        
        if latest and latest.get("run_id"):
            assert "screenshots_count" in latest, "Latest run missing 'screenshots_count' field"
            print(f"screenshots_count: {latest.get('screenshots_count')}")
    
    def test_history_items_have_counts(self, admin_session):
        """Verify history items have checks_count and screenshots_count"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])
        
        for idx, item in enumerate(history[:3]):
            assert "checks_count" in item, f"History item {idx} missing 'checks_count'"
            assert "screenshots_count" in item, f"History item {idx} missing 'screenshots_count'"
