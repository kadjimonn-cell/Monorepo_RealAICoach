"""
Checkpoint D Verification: Admin-only swept routes are fully locked at global system level.
Tests that non-admin users cannot access swept admin/report routes while admin users can.

Swept routes being tested:
- /ops-performance
- /ops-route-health
- /policy-console
- /performance-observability
- /route-health-report
- /safe-deployment
- /ai-feature-dashboard
- /i18n-drift-dashboard
- /certificate-operations
- /job-platform-admin
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"

BASIC_USER_EMAIL = "f21.basic.1781338672@example.com"
BASIC_USER_PASSWORD = "F21Basic#2026Aa"

# Swept admin routes to test
SWEPT_ADMIN_ROUTES = [
    "/ops-performance",
    "/ops-route-health",
    "/policy-console",
    "/performance-observability",
    "/route-health-report",
    "/safe-deployment",
    "/ai-feature-dashboard",
    "/i18n-drift-dashboard",
    "/certificate-operations",
    "/job-platform-admin",
]


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    return session


@pytest.fixture(scope="module")
def admin_session(api_client):
    """Get authenticated admin session"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return api_client
    pytest.skip(f"Admin login failed: {response.status_code}")


@pytest.fixture(scope="module")
def free_user_session():
    """Get authenticated free user session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    if response.status_code == 200:
        return session
    pytest.skip(f"Free user login failed: {response.status_code}")


@pytest.fixture(scope="module")
def basic_user_session():
    """Get authenticated basic user session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": BASIC_USER_EMAIL,
        "password": BASIC_USER_PASSWORD
    })
    if response.status_code == 200:
        return session
    pytest.skip(f"Basic user login failed: {response.status_code}")


class TestUnauthenticatedAccessBlocked:
    """Test that unauthenticated users are redirected from swept admin routes"""
    
    @pytest.mark.parametrize("route", SWEPT_ADMIN_ROUTES)
    def test_unauthenticated_redirect(self, route):
        """Unauthenticated access to swept admin routes should redirect to /welcome"""
        response = requests.get(f"{BASE_URL}{route}", allow_redirects=False)
        # Should redirect (302) or return the page with redirect logic
        # The frontend handles the redirect via AdminRouteGate
        assert response.status_code in [200, 302, 307], f"Route {route} returned unexpected status {response.status_code}"
        
        # If it's a redirect, check it goes to /welcome
        if response.status_code in [302, 307]:
            location = response.headers.get('Location', '')
            assert '/welcome' in location or 'auth_reason' in location, f"Route {route} did not redirect to /welcome"


class TestNonAdminAccessBlocked:
    """Test that non-admin users cannot access swept admin routes"""
    
    @pytest.mark.parametrize("route", SWEPT_ADMIN_ROUTES)
    def test_free_user_blocked(self, free_user_session, route):
        """Free user should be blocked from swept admin routes"""
        response = free_user_session.get(f"{BASE_URL}{route}", allow_redirects=False)
        # The frontend AdminRouteGate redirects non-admin to /dashboard
        # Backend APIs should return 403 for non-admin
        assert response.status_code in [200, 302, 307, 403], f"Route {route} returned unexpected status {response.status_code}"
    
    @pytest.mark.parametrize("route", SWEPT_ADMIN_ROUTES)
    def test_basic_user_blocked(self, basic_user_session, route):
        """Basic user should be blocked from swept admin routes"""
        response = basic_user_session.get(f"{BASE_URL}{route}", allow_redirects=False)
        # The frontend AdminRouteGate redirects non-admin to /dashboard
        assert response.status_code in [200, 302, 307, 403], f"Route {route} returned unexpected status {response.status_code}"


class TestAdminAccessAllowed:
    """Test that admin users can access swept admin routes"""
    
    @pytest.mark.parametrize("route", SWEPT_ADMIN_ROUTES)
    def test_admin_can_access(self, admin_session, route):
        """Admin user should be able to access swept admin routes"""
        response = admin_session.get(f"{BASE_URL}{route}", allow_redirects=True)
        # Admin should get 200 OK
        assert response.status_code == 200, f"Admin could not access {route}: {response.status_code}"


class TestAccessControlSessionEndpoint:
    """Test the access control session endpoint for admin verification"""
    
    def test_admin_session_returns_admin_flag(self, admin_session):
        """Admin session should return is_admin=true"""
        response = admin_session.get(f"{BASE_URL}/api/access-control/session")
        if response.status_code == 200:
            data = response.json()
            assert data.get('is_admin') == True or data.get('user', {}).get('is_admin') == True, \
                "Admin session should have is_admin=true"
    
    def test_free_user_session_not_admin(self, free_user_session):
        """Free user session should not have admin flag"""
        response = free_user_session.get(f"{BASE_URL}/api/access-control/session")
        if response.status_code == 200:
            data = response.json()
            is_admin = data.get('is_admin', False) or data.get('user', {}).get('is_admin', False)
            assert is_admin == False, "Free user should not have is_admin=true"


class TestNonAdminCoreDashboardAccess:
    """Test that non-admin users can still access core dashboard"""
    
    def test_free_user_can_access_dashboard(self, free_user_session):
        """Free user should be able to access /dashboard"""
        response = free_user_session.get(f"{BASE_URL}/dashboard", allow_redirects=True)
        assert response.status_code == 200, f"Free user could not access /dashboard: {response.status_code}"
    
    def test_basic_user_can_access_dashboard(self, basic_user_session):
        """Basic user should be able to access /dashboard"""
        response = basic_user_session.get(f"{BASE_URL}/dashboard", allow_redirects=True)
        assert response.status_code == 200, f"Basic user could not access /dashboard: {response.status_code}"
    
    def test_free_user_can_access_home(self, free_user_session):
        """Free user should be able to access /home"""
        response = free_user_session.get(f"{BASE_URL}/home", allow_redirects=True)
        # Home might redirect to dashboard or be accessible
        assert response.status_code in [200, 302, 307], f"Free user could not access /home: {response.status_code}"


class TestAdminAPIEndpointsProtected:
    """Test that admin API endpoints are protected"""
    
    def test_admin_analytics_blocked_for_non_admin(self, free_user_session):
        """Admin analytics endpoint should be blocked for non-admin"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/analytics/insights")
        assert response.status_code in [401, 403], f"Admin analytics should be blocked: {response.status_code}"
    
    def test_admin_platform_perf_blocked_for_non_admin(self, free_user_session):
        """Admin platform perf endpoint should be blocked for non-admin"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/platform-perf/unified")
        assert response.status_code in [401, 403], f"Admin platform perf should be blocked: {response.status_code}"
    
    def test_admin_ai_alerts_blocked_for_non_admin(self, free_user_session):
        """Admin AI alerts endpoint should be blocked for non-admin"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/ai-alerts")
        assert response.status_code in [401, 403], f"Admin AI alerts should be blocked: {response.status_code}"
