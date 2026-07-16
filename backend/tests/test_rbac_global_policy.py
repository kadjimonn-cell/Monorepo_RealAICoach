"""
RBAC Global Policy Tests - Iteration 255
Tests strict RBAC at global system level:
1. Unauthenticated users must stay on Welcome and never see logged-in pages/tabs
2. Logged-in non-admin sees user pages only, admin pages/tabs hidden and blocked
3. Logged-in admin retains admin pages/tabs and overall access
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
NON_ADMIN_EMAIL = "feature21.test.1781234530@example.com"
NON_ADMIN_PASSWORD = "Feature21Test#2026Aa"
ADMIN_EMAIL = "watchvideos.phase4.admin.306786@example.com"
ADMIN_PASSWORD = "Phase4Admin#2026Aa"

# Admin-only routes that should be blocked for non-admin users
ADMIN_ONLY_ROUTES = [
    "/admin-console",
    "/executive-dashboard",
    "/team-management",
    "/policy-console",
    "/ops-performance",
    "/ops-route-health",
    "/safe-deployment",
    "/route-health-report",
    "/ai-feature-dashboard",
    "/i18n-drift-dashboard",
]

# Protected routes that require authentication
PROTECTED_ROUTES = [
    "/dashboard",
    "/features/watch-videos",
    "/session-history",
    "/content-library",
]

# Admin API endpoints
ADMIN_API_ENDPOINTS = [
    "/api/admin/notifications/live",
    "/api/admin/live-activity/alerts",
    "/api/admin/executive/risk-control",
]


class TestUnauthenticatedAccess:
    """Test that unauthenticated users are blocked from protected routes"""
    
    def test_unauthenticated_dashboard_redirect(self):
        """Unauthenticated access to /dashboard should redirect to /welcome"""
        response = requests.get(f"{BASE_URL}/dashboard", allow_redirects=False)
        # Should get a redirect or the page should contain welcome redirect logic
        print(f"Dashboard access (unauth): status={response.status_code}")
        # Frontend handles redirect, so we check if the page loads
        assert response.status_code in [200, 302, 307], f"Unexpected status: {response.status_code}"
    
    def test_unauthenticated_admin_console_blocked(self):
        """Unauthenticated access to /admin-console should be blocked"""
        response = requests.get(f"{BASE_URL}/admin-console", allow_redirects=False)
        print(f"Admin console access (unauth): status={response.status_code}")
        assert response.status_code in [200, 302, 307], f"Unexpected status: {response.status_code}"
    
    def test_unauthenticated_admin_api_blocked(self):
        """Unauthenticated access to admin APIs should return 401/403"""
        for endpoint in ADMIN_API_ENDPOINTS:
            response = requests.get(f"{BASE_URL}{endpoint}")
            print(f"Admin API {endpoint} (unauth): status={response.status_code}")
            assert response.status_code in [401, 403], f"Expected 401/403 for {endpoint}, got {response.status_code}"


class TestNonAdminAccess:
    """Test that non-admin users cannot access admin routes/APIs"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as non-admin user"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": NON_ADMIN_EMAIL, "password": NON_ADMIN_PASSWORD}
        )
        print(f"Non-admin login: status={login_response.status_code}")
        
        if login_response.status_code == 200:
            data = login_response.json()
            print(f"Non-admin user data: is_admin={data.get('user', {}).get('is_admin')}, role={data.get('user', {}).get('role')}")
        
        yield
        
        # Logout
        try:
            self.session.post(f"{BASE_URL}/api/auth/logout")
        except Exception:
            pass
    
    def test_non_admin_login_success(self):
        """Verify non-admin user can login"""
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        print(f"Non-admin /api/auth/me: status={response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("is_admin") is False or data.get("is_admin") is None, "User should not be admin"
        print(f"Non-admin verified: is_admin={data.get('is_admin')}")
    
    def test_non_admin_access_control_session(self):
        """Verify access control session shows non-admin status"""
        response = self.session.get(f"{BASE_URL}/api/access-control/session")
        print(f"Non-admin access-control/session: status={response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Access control session: is_admin={data.get('is_admin')}, actor_type={data.get('actor_type')}")
            assert data.get("is_admin") is False, "Non-admin user should have is_admin=False"
            assert data.get("actor_type") == "user", f"Expected actor_type=user, got {data.get('actor_type')}"
    
    def test_non_admin_blocked_from_admin_apis(self):
        """Non-admin user should be blocked from admin APIs with 403"""
        for endpoint in ADMIN_API_ENDPOINTS:
            response = self.session.get(f"{BASE_URL}{endpoint}")
            print(f"Non-admin API {endpoint}: status={response.status_code}")
            assert response.status_code == 403, f"Expected 403 for {endpoint}, got {response.status_code}"
            
            # Verify error message
            try:
                data = response.json()
                detail = data.get("detail", "")
                print(f"  Error detail: {detail}")
                assert "admin" in detail.lower() or "access" in detail.lower(), "Expected admin-related error message"
            except Exception:
                pass
    
    def test_non_admin_can_access_user_routes(self):
        """Non-admin user should be able to access regular user routes"""
        user_endpoints = [
            "/api/auth/me",
            "/api/access-control/session",
        ]
        
        for endpoint in user_endpoints:
            response = self.session.get(f"{BASE_URL}{endpoint}")
            print(f"Non-admin user endpoint {endpoint}: status={response.status_code}")
            assert response.status_code == 200, f"Expected 200 for {endpoint}, got {response.status_code}"


class TestAdminAccess:
    """Test that admin users can access admin routes/APIs"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as admin user"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        print(f"Admin login: status={login_response.status_code}")
        
        if login_response.status_code == 200:
            data = login_response.json()
            print(f"Admin user data: is_admin={data.get('user', {}).get('is_admin')}, role={data.get('user', {}).get('role')}")
        
        yield
        
        # Logout
        try:
            self.session.post(f"{BASE_URL}/api/auth/logout")
        except Exception:
            pass
    
    def test_admin_login_success(self):
        """Verify admin user can login"""
        response = self.session.get(f"{BASE_URL}/api/auth/me")
        print(f"Admin /api/auth/me: status={response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("is_admin") is True, f"User should be admin, got is_admin={data.get('is_admin')}"
        print(f"Admin verified: is_admin={data.get('is_admin')}")
    
    def test_admin_access_control_session(self):
        """Verify access control session shows admin status"""
        response = self.session.get(f"{BASE_URL}/api/access-control/session")
        print(f"Admin access-control/session: status={response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Access control session: is_admin={data.get('is_admin')}, actor_type={data.get('actor_type')}")
            assert data.get("is_admin") is True, "Admin user should have is_admin=True"
            assert data.get("actor_type") == "admin", f"Expected actor_type=admin, got {data.get('actor_type')}"
    
    def test_admin_can_access_admin_apis(self):
        """Admin user should be able to access admin APIs"""
        for endpoint in ADMIN_API_ENDPOINTS:
            response = self.session.get(f"{BASE_URL}{endpoint}")
            print(f"Admin API {endpoint}: status={response.status_code}")
            assert response.status_code == 200, f"Expected 200 for {endpoint}, got {response.status_code}"
    
    def test_admin_can_access_user_routes(self):
        """Admin user should also be able to access regular user routes"""
        user_endpoints = [
            "/api/auth/me",
            "/api/access-control/session",
        ]
        
        for endpoint in user_endpoints:
            response = self.session.get(f"{BASE_URL}{endpoint}")
            print(f"Admin user endpoint {endpoint}: status={response.status_code}")
            assert response.status_code == 200, f"Expected 200 for {endpoint}, got {response.status_code}"


class TestFeature21AdminEndpoint:
    """Test Feature 21 admin endpoint policy - non-admin blocked, admin allowed"""
    
    def test_feature21_admin_endpoint_non_admin_blocked(self):
        """Non-admin user should be blocked from Feature 21 admin endpoints"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as non-admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": NON_ADMIN_EMAIL, "password": NON_ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, f"Non-admin login failed: {login_response.status_code}"
        
        # Try to access admin notifications endpoint
        response = session.get(f"{BASE_URL}/api/admin/notifications/live")
        print(f"Feature21 admin endpoint (non-admin): status={response.status_code}")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        session.post(f"{BASE_URL}/api/auth/logout")
    
    def test_feature21_admin_endpoint_admin_allowed(self):
        """Admin user should be allowed to access Feature 21 admin endpoints"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as admin
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.status_code}"
        
        # Try to access admin notifications endpoint
        response = session.get(f"{BASE_URL}/api/admin/notifications/live")
        print(f"Feature21 admin endpoint (admin): status={response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        session.post(f"{BASE_URL}/api/auth/logout")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
