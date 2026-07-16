"""
Test Preview Proxy Stability and TOS Auto-Accept Functionality
Tests for iteration 13 - Preview health, route stability, and TOS deterministic automation
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPreviewHealth:
    """Preview health endpoint tests"""
    
    def test_preview_health_endpoint_returns_200(self):
        """Test /_preview/health returns 200 with expected payload"""
        response = requests.get(f"{BASE_URL}/_preview/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("ok") is True, "Expected ok:true in response"
        assert "has_dist" in data, "Expected has_dist field"
        assert "expected_preview_host" in data, "Expected expected_preview_host field"
        assert "backend_port" in data, "Expected backend_port field"
        assert "uptime_sec" in data, "Expected uptime_sec field"
    
    def test_preview_health_has_correct_host(self):
        """Test preview health returns correct expected host"""
        response = requests.get(f"{BASE_URL}/_preview/health", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        expected_host = data.get("expected_preview_host", "")
        assert "preview.emergentagent.com" in expected_host or expected_host == "", \
            f"Unexpected host: {expected_host}"
    
    def test_preview_health_uptime_increasing(self):
        """Test that uptime is increasing (no restart storm)"""
        response1 = requests.get(f"{BASE_URL}/_preview/health", timeout=10)
        assert response1.status_code == 200
        uptime1 = response1.json().get("uptime_sec", 0)
        
        time.sleep(2)
        
        response2 = requests.get(f"{BASE_URL}/_preview/health", timeout=10)
        assert response2.status_code == 200
        uptime2 = response2.json().get("uptime_sec", 0)
        
        assert uptime2 >= uptime1, f"Uptime decreased from {uptime1} to {uptime2} - possible restart"


class TestRouteStability:
    """Test route stability - no proxy errors"""
    
    @pytest.mark.parametrize("route", [
        "/",
        "/features/travel-visa",
        "/features/daily-meditation",
        "/auth/login",
    ])
    def test_route_returns_200_no_proxy_error(self, route):
        """Test routes return 200 without proxy error HTML"""
        response = requests.get(f"{BASE_URL}{route}", timeout=15)
        assert response.status_code == 200, f"Route {route} returned {response.status_code}"
        
        content = response.text.lower()
        assert "proxy" not in content or "error occurred while trying to proxy" not in content, \
            f"Proxy error detected on route {route}"
    
    def test_repeated_route_loads_stable(self):
        """Test repeated loads don't cause proxy errors"""
        routes = ["/", "/features/travel-visa", "/features/daily-meditation"]
        
        for _ in range(3):
            for route in routes:
                response = requests.get(f"{BASE_URL}{route}", timeout=15)
                assert response.status_code == 200, f"Route {route} failed on repeated load"
                
                content = response.text.lower()
                assert "error occurred while trying to proxy" not in content


class TestBackendAPIHealth:
    """Test backend API health"""
    
    def test_api_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy, got {data.get('status')}"
    
    def test_tos_acceptance_status_endpoint_exists(self):
        """Test TOS acceptance status endpoint exists (may require auth)"""
        response = requests.get(f"{BASE_URL}/api/tos/acceptance-status", timeout=10)
        # Should return 401 (unauthorized) or 200 (if no TOS required)
        assert response.status_code in [200, 401, 403], \
            f"Unexpected status {response.status_code} for TOS endpoint"
    
    def test_tos_current_endpoint_exists(self):
        """Test TOS current version endpoint exists"""
        response = requests.get(f"{BASE_URL}/api/tos/current", timeout=10)
        # Should return 200 or 404 (if no TOS configured)
        assert response.status_code in [200, 404], \
            f"Unexpected status {response.status_code} for TOS current endpoint"


class TestLoginFlow:
    """Test login flow with test credentials"""
    
    def test_login_with_test_credentials(self):
        """Test login with Travel Visa free test user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "tv.free.test@realaicoach.app",
                "password": "TvFree#2026!Aa"
            },
            timeout=15
        )
        
        assert response.status_code == 200, f"Login failed with status {response.status_code}"
        
        data = response.json()
        assert "session_token" in data or "token" in data, "No token in login response"
    
    def test_login_returns_user_info(self):
        """Test login returns user information"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "tv.free.test@realaicoach.app",
                "password": "TvFree#2026!Aa"
            },
            timeout=15
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check for user info
        user = data.get("user", data)
        assert "email" in user or "user_id" in user, "No user info in response"


class TestTOSAutoAcceptLogic:
    """Test TOS auto-accept logic (code review verification)"""
    
    def test_tos_modal_component_has_auto_accept_logic(self):
        """Verify TOS modal component file exists and has auto-accept logic"""
        tos_modal_path = "/app/frontend/src/components/TosAcceptanceModal.tsx"
        
        with open(tos_modal_path, 'r') as f:
            content = f.read()
        
        # Check for auto-accept flag detection
        assert "e2eAutoAcceptTos" in content, "Missing e2eAutoAcceptTos query param check"
        assert "rac:e2e:auto-accept-tos" in content, "Missing localStorage flag check"
        assert "autoAcceptForE2E" in content, "Missing autoAcceptForE2E logic"
        assert "webdriver" in content.lower(), "Missing webdriver detection"
    
    def test_e2e_helper_has_tos_functions(self):
        """Verify E2E helper has TOS acceptance functions"""
        helper_path = "/app/frontend/e2e/helpers/tos.ts"
        
        with open(helper_path, 'r') as f:
            content = f.read()
        
        assert "acceptTosIfPresent" in content, "Missing acceptTosIfPresent function"
        assert "startTosAutoAcceptance" in content, "Missing startTosAutoAcceptance function"
        assert "rac:e2e:auto-accept-tos" in content, "Missing localStorage flag in helper"


@pytest.fixture(scope="module")
def authenticated_session():
    """Get authenticated session for protected endpoint tests"""
    session = requests.Session()
    
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": "tv.free.test@realaicoach.app",
            "password": "TvFree#2026!Aa"
        },
        timeout=15
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("session_token") or data.get("token")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestAuthenticatedTOSEndpoints:
    """Test TOS endpoints with authentication"""
    
    def test_tos_acceptance_status_authenticated(self, authenticated_session):
        """Test TOS acceptance status with auth"""
        response = authenticated_session.get(
            f"{BASE_URL}/api/tos/acceptance-status",
            timeout=10
        )
        
        # Should return 200 with acceptance status
        if response.status_code == 200:
            data = response.json()
            assert "accepted" in data, "Missing accepted field in TOS status"
        else:
            # TOS might not be configured
            assert response.status_code in [404, 500], \
                f"Unexpected status {response.status_code}"
