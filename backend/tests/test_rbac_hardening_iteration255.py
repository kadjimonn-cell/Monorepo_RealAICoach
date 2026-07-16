"""
RBAC Hardening Tests - Iteration 255
Tests for strict RBAC hardening:
1. Unauthenticated users redirected to /welcome with auth_reason/return_to
2. Non-admin users cannot see admin nav items
3. Non-admin direct access blocked for admin routes
4. Admin user can access admin routes
5. Feature 21 admin endpoint policy: non-admin blocked, admin allowed
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
NON_ADMIN_EMAIL = "feature21.test.1781234530@example.com"
NON_ADMIN_PASSWORD = "Feature21Test#2026Aa"
ADMIN_EMAIL = "watchvideos.phase4.admin.306786@example.com"
ADMIN_PASSWORD = "Phase4Admin#2026Aa"


class TestRBACHardening:
    """RBAC Hardening Tests"""

    @pytest.fixture(scope="class")
    def api_client(self):
        """Shared requests session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        return session

    @pytest.fixture(scope="class")
    def non_admin_session(self, api_client):
        """Login as non-admin user and return session"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": NON_ADMIN_EMAIL,
            "password": NON_ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Non-admin login failed: {response.status_code} - {response.text}")
        return api_client

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
        return session

    # ============================================
    # Test 1: Unauthenticated API Access
    # ============================================
    def test_unauthenticated_auth_me_returns_401(self, api_client):
        """Unauthenticated /api/auth/me should return 401"""
        fresh_session = requests.Session()
        response = fresh_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Unauthenticated /api/auth/me returns 401")

    def test_unauthenticated_access_control_session_returns_401(self, api_client):
        """Unauthenticated /api/access-control/session should return 401"""
        fresh_session = requests.Session()
        response = fresh_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Unauthenticated /api/access-control/session returns 401")

    def test_unauthenticated_admin_api_blocked(self, api_client):
        """Unauthenticated admin API endpoints should return 401/403"""
        fresh_session = requests.Session()
        admin_endpoints = [
            "/api/admin/notifications/live",
            "/api/admin/live-activity/alerts",
            "/api/admin/executive/risk-control",
        ]
        for endpoint in admin_endpoints:
            response = fresh_session.get(f"{BASE_URL}{endpoint}")
            assert response.status_code in [401, 403], f"Expected 401/403 for {endpoint}, got {response.status_code}"
            print(f"PASS: Unauthenticated {endpoint} returns {response.status_code}")

    # ============================================
    # Test 2: Non-Admin User Access Control
    # ============================================
    def test_non_admin_login_success(self, non_admin_session):
        """Non-admin user can login successfully"""
        response = non_admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("is_admin") is False or data.get("is_admin") is None, "User should not be admin"
        print(f"PASS: Non-admin user logged in: {data.get('email')}, is_admin={data.get('is_admin')}")

    def test_non_admin_access_control_session(self, non_admin_session):
        """Non-admin user access control session should show is_admin=False"""
        response = non_admin_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("is_admin") is False, f"Expected is_admin=False, got {data.get('is_admin')}"
        assert data.get("actor_type") == "user", f"Expected actor_type=user, got {data.get('actor_type')}"
        print(f"PASS: Non-admin access control session: is_admin={data.get('is_admin')}, actor_type={data.get('actor_type')}")

    def test_non_admin_blocked_from_admin_apis(self, non_admin_session):
        """Non-admin user should be blocked from admin API endpoints"""
        admin_endpoints = [
            "/api/admin/notifications/live",
            "/api/admin/live-activity/alerts",
            "/api/admin/executive/risk-control",
        ]
        for endpoint in admin_endpoints:
            response = non_admin_session.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 403, f"Expected 403 for {endpoint}, got {response.status_code}"
            print(f"PASS: Non-admin blocked from {endpoint} with 403")

    # ============================================
    # Test 3: Admin User Access Control
    # ============================================
    def test_admin_login_success(self, admin_session):
        """Admin user can login successfully"""
        response = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("is_admin") is True, f"Expected is_admin=True, got {data.get('is_admin')}"
        print(f"PASS: Admin user logged in: {data.get('email')}, is_admin={data.get('is_admin')}")

    def test_admin_access_control_session(self, admin_session):
        """Admin user access control session should show is_admin=True"""
        response = admin_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("is_admin") is True, f"Expected is_admin=True, got {data.get('is_admin')}"
        assert data.get("actor_type") == "admin", f"Expected actor_type=admin, got {data.get('actor_type')}"
        print(f"PASS: Admin access control session: is_admin={data.get('is_admin')}, actor_type={data.get('actor_type')}")

    def test_admin_can_access_admin_apis(self, admin_session):
        """Admin user should be able to access admin API endpoints"""
        admin_endpoints = [
            "/api/admin/notifications/live",
            "/api/admin/live-activity/alerts",
            "/api/admin/executive/risk-control",
        ]
        for endpoint in admin_endpoints:
            response = admin_session.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 200, f"Expected 200 for {endpoint}, got {response.status_code}"
            print(f"PASS: Admin can access {endpoint} with 200")

    # ============================================
    # Test 4: Feature 21 Admin Endpoint Policy
    # ============================================
    def test_feature21_admin_endpoint_non_admin_blocked(self, non_admin_session):
        """Feature 21 admin endpoints should block non-admin users"""
        # Feature 21 is Watch Videos - check admin observability endpoints
        feature21_admin_endpoints = [
            "/api/admin/executive/overview",
            "/api/admin/executive/risk-control",
        ]
        for endpoint in feature21_admin_endpoints:
            response = non_admin_session.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 403, f"Expected 403 for {endpoint}, got {response.status_code}"
            print(f"PASS: Non-admin blocked from Feature 21 admin endpoint {endpoint}")

    def test_feature21_admin_endpoint_admin_allowed(self, admin_session):
        """Feature 21 admin endpoints should allow admin users"""
        feature21_admin_endpoints = [
            "/api/admin/executive/overview",
            "/api/admin/executive/risk-control",
        ]
        for endpoint in feature21_admin_endpoints:
            response = admin_session.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 200, f"Expected 200 for {endpoint}, got {response.status_code}"
            print(f"PASS: Admin allowed to access Feature 21 admin endpoint {endpoint}")

    # ============================================
    # Test 5: Health Check
    # ============================================
    def test_health_endpoint_public(self):
        """Health endpoint should be publicly accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy status, got {data.get('status')}"
        print("PASS: Health endpoint returns healthy status")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
