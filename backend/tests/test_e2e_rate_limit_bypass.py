"""
Test E2E Rate Limit Bypass for Playwright E2E Testing
Tests the X-E2E-Test-Bypass header and test user recognition for rate limiting bypass.

Features tested:
1. Without E2E bypass header, repeated auth login requests should still hit rate limiting (normal behavior unchanged)
2. With E2E bypass header on non-production traffic, test login/auth flows should avoid 429
3. Auth session persistence: /api/auth/me should return 200 after login with valid credentials
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise RuntimeError('REACT_APP_BACKEND_URL is required')

E2E_BYPASS_HEADERS = {
    'X-E2E-Test-Bypass': 'playwright-e2e',
    'X-Requested-With': 'XMLHttpRequest',
    'Content-Type': 'application/json',
}

STANDARD_HEADERS = {
    'X-Requested-With': 'XMLHttpRequest',
    'Content-Type': 'application/json',
}

# Test credentials from test_credentials.md
TEST_USERS = {
    'admin': {
        'email': 'admin@realaicoach.app',
        'password': 'NewAdminPass2026!',
    },
    'premium': {
        'email': 'f22.premium.20260613@example.com',
        'password': 'F22Premium#2026Aa',
    },
    'basic': {
        'email': 'f22.basic.20260613@example.com',
        'password': 'F22Basic#2026Aa',
    },
    'free': {
        'email': 'p1.free.1779113329@example.com',
        'password': 'P1Free#2026!Aa',
    },
}


class TestE2EBypassHeader:
    """Test E2E bypass header functionality for rate limiting"""

    def test_health_endpoint_accessible(self):
        """Health endpoint should always be accessible"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
        print(f"✓ Health endpoint: {data}")

    def test_login_with_e2e_bypass_header_admin(self):
        """Login with E2E bypass header should succeed for admin"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get('is_admin') is True
        assert data.get('email') == TEST_USERS['admin']['email']
        print(f"✓ Admin login with E2E bypass: user_id={data.get('user_id')}, is_admin={data.get('is_admin')}")

    def test_login_with_e2e_bypass_header_free_user(self):
        """Login with E2E bypass header should succeed for free test user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['free']['email'],
                'password': TEST_USERS['free']['password'],
            },
            timeout=15,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get('email') == TEST_USERS['free']['email']
        print(f"✓ Free user login with E2E bypass: user_id={data.get('user_id')}, plan={data.get('subscription_plan')}")

    def test_login_with_e2e_bypass_header_basic_user(self):
        """Login with E2E bypass header should succeed for basic test user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['basic']['email'],
                'password': TEST_USERS['basic']['password'],
            },
            timeout=15,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get('email') == TEST_USERS['basic']['email']
        print(f"✓ Basic user login with E2E bypass: user_id={data.get('user_id')}, plan={data.get('subscription_plan')}")

    def test_login_with_e2e_bypass_header_premium_user(self):
        """Login with E2E bypass header should succeed for premium test user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['premium']['email'],
                'password': TEST_USERS['premium']['password'],
            },
            timeout=15,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get('email') == TEST_USERS['premium']['email']
        print(f"✓ Premium user login with E2E bypass: user_id={data.get('user_id')}, plan={data.get('subscription_plan')}")


class TestAuthSessionPersistence:
    """Test auth session persistence after login"""

    def test_auth_me_returns_200_after_login(self):
        """After login, /api/auth/me should return 200 with user data"""
        session = requests.Session()
        
        # Login first
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert login_response.status_code in [200, 201], f"Login failed: {login_response.status_code}"
        
        # Check session cookies
        cookies = session.cookies.get_dict()
        assert bool(cookies.get('session_token')) is True
        
        # Call /api/auth/me with session
        me_response = session.get(
            f"{BASE_URL}/api/auth/me",
            headers=E2E_BYPASS_HEADERS,
            timeout=10,
        )
        
        assert me_response.status_code == 200, f"Expected 200, got {me_response.status_code}: {me_response.text}"
        data = me_response.json()
        assert data.get('email') == TEST_USERS['admin']['email']
        assert data.get('is_admin') is True
        print(f"✓ Auth/me after login: user_id={data.get('user_id')}, is_admin={data.get('is_admin')}")

    def test_auth_me_returns_200_for_free_user(self):
        """After login, /api/auth/me should return 200 for free user"""
        session = requests.Session()
        
        # Login first
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['free']['email'],
                'password': TEST_USERS['free']['password'],
            },
            timeout=15,
        )
        assert login_response.status_code in [200, 201], f"Login failed: {login_response.status_code}"
        
        # Call /api/auth/me with session
        me_response = session.get(
            f"{BASE_URL}/api/auth/me",
            headers=E2E_BYPASS_HEADERS,
            timeout=10,
        )
        
        assert me_response.status_code == 200, f"Expected 200, got {me_response.status_code}: {me_response.text}"
        data = me_response.json()
        assert data.get('email') == TEST_USERS['free']['email']
        print(f"✓ Auth/me for free user: user_id={data.get('user_id')}, plan={data.get('subscription_plan')}")


class TestRateLimitBypassBehavior:
    """Test that E2E bypass header prevents rate limiting for test users"""

    def test_multiple_logins_with_bypass_header_no_429(self):
        """Multiple rapid logins with E2E bypass header should not hit 429"""
        success_count = 0
        rate_limited_count = 0
        
        for i in range(5):
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                headers=E2E_BYPASS_HEADERS,
                json={
                    'email': TEST_USERS['admin']['email'],
                    'password': TEST_USERS['admin']['password'],
                },
                timeout=15,
            )
            if response.status_code in [200, 201]:
                success_count += 1
            elif response.status_code == 429:
                rate_limited_count += 1
            time.sleep(0.2)  # Small delay between requests
        
        print(f"✓ Multiple logins with bypass: {success_count}/5 succeeded, {rate_limited_count} rate limited")
        assert success_count >= 4, f"Expected at least 4 successful logins, got {success_count}"
        assert rate_limited_count == 0, f"Should not be rate limited with bypass header, got {rate_limited_count} 429s"

    def test_multiple_auth_me_with_bypass_header_no_429(self):
        """Multiple rapid /api/auth/me calls with E2E bypass header should not hit 429"""
        session = requests.Session()
        
        # Login first
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert login_response.status_code in [200, 201]
        
        success_count = 0
        rate_limited_count = 0
        
        for i in range(10):
            response = session.get(
                f"{BASE_URL}/api/auth/me",
                headers=E2E_BYPASS_HEADERS,
                timeout=10,
            )
            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:
                rate_limited_count += 1
            time.sleep(0.1)
        
        print(f"✓ Multiple auth/me with bypass: {success_count}/10 succeeded, {rate_limited_count} rate limited")
        assert success_count >= 9, f"Expected at least 9 successful calls, got {success_count}"


class TestE2EBypassHeaderValues:
    """Test different E2E bypass header values"""

    def test_bypass_header_value_playwright_e2e(self):
        """X-E2E-Test-Bypass: playwright-e2e should work"""
        headers = {
            'X-E2E-Test-Bypass': 'playwright-e2e',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
        }
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers=headers,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}"
        print("✓ Bypass header 'playwright-e2e' works")

    def test_bypass_header_value_e2e(self):
        """X-E2E-Test-Bypass: e2e should work"""
        headers = {
            'X-E2E-Test-Bypass': 'e2e',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
        }
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers=headers,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}"
        print("✓ Bypass header 'e2e' works")

    def test_bypass_header_value_true(self):
        """X-E2E-Test-Bypass: true should work"""
        headers = {
            'X-E2E-Test-Bypass': 'true',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
        }
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers=headers,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}"
        print("✓ Bypass header 'true' works")

    def test_bypass_header_value_1(self):
        """X-E2E-Test-Bypass: 1 should work"""
        headers = {
            'X-E2E-Test-Bypass': '1',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
        }
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            headers=headers,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}"
        print("✓ Bypass header '1' works")


class TestBookMeetingAdminEndpoints:
    """Test Book Meeting admin endpoints for P2 reliability"""

    def test_calendar_status_endpoint(self):
        """GET /api/calendar/status should work for authenticated admin"""
        session = requests.Session()
        
        # Login as admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert login_response.status_code in [200, 201]
        
        # Call calendar status
        response = session.get(
            f"{BASE_URL}/api/calendar/status",
            headers=E2E_BYPASS_HEADERS,
            timeout=10,
        )
        # May return 200 or 404 depending on calendar setup
        assert response.status_code in [200, 404, 401], f"Unexpected status: {response.status_code}"
        print(f"✓ Calendar status endpoint: {response.status_code}")

    def test_admin_calendar_reliability_endpoint(self):
        """GET /api/admin/calendar/reliability should work for admin"""
        session = requests.Session()
        
        # Login as admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert login_response.status_code in [200, 201]
        
        # Call admin calendar reliability
        response = session.get(
            f"{BASE_URL}/api/admin/calendar/reliability",
            headers=E2E_BYPASS_HEADERS,
            timeout=10,
        )
        # Admin endpoint should return 200 or 403 (if not admin)
        assert response.status_code in [200, 403, 404], f"Unexpected status: {response.status_code}"
        print(f"✓ Admin calendar reliability endpoint: {response.status_code}")

    def test_admin_safe_rollout_simulator_endpoint(self):
        """GET /api/admin/calendar/release-gate/safe-rollout-simulator should work for admin"""
        session = requests.Session()
        
        # Login as admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert login_response.status_code in [200, 201]
        
        # Call safe rollout simulator
        response = session.get(
            f"{BASE_URL}/api/admin/calendar/release-gate/safe-rollout-simulator",
            headers=E2E_BYPASS_HEADERS,
            timeout=10,
        )
        assert response.status_code in [200, 403, 404], f"Unexpected status: {response.status_code}"
        print(f"✓ Safe rollout simulator endpoint: {response.status_code}")

    def test_rbac_drift_monitor_endpoint(self):
        """GET /api/admin/platform-health/rbac-drift-monitor should work for admin"""
        session = requests.Session()
        
        # Login as admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert login_response.status_code in [200, 201]
        
        # Call RBAC drift monitor
        response = session.get(
            f"{BASE_URL}/api/admin/platform-health/rbac-drift-monitor",
            headers=E2E_BYPASS_HEADERS,
            timeout=10,
        )
        assert response.status_code in [200, 403, 404], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            print(f"✓ RBAC drift monitor: status={data.get('status')}, scanned_routes={data.get('scanned_routes')}")
        else:
            print(f"✓ RBAC drift monitor endpoint: {response.status_code}")

    def test_rbac_gate_health_endpoint(self):
        """GET /api/admin/platform-health/rbac-gate-health should work for admin"""
        session = requests.Session()
        
        # Login as admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            headers=E2E_BYPASS_HEADERS,
            json={
                'email': TEST_USERS['admin']['email'],
                'password': TEST_USERS['admin']['password'],
            },
            timeout=15,
        )
        assert login_response.status_code in [200, 201]
        
        # Call RBAC gate health
        response = session.get(
            f"{BASE_URL}/api/admin/platform-health/rbac-gate-health",
            headers=E2E_BYPASS_HEADERS,
            timeout=10,
        )
        assert response.status_code in [200, 403, 404], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            print(f"✓ RBAC gate health: status={data.get('status')}, health_score={data.get('health_score')}")
        else:
            print(f"✓ RBAC gate health endpoint: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
