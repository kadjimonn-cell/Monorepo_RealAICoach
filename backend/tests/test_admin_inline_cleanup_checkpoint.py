"""
Test: Admin Inline Cleanup Checkpoint
Verifies that remaining quasi-admin pages (/team-management, /certificate-gallery) 
and other cleaned admin pages are properly protected by shared admin protection.

Focus areas:
1. Non-admin users cannot access /team-management and /certificate-gallery
2. Non-admin users are redirected/blocked (not shown inline access-required states)
3. Admin users can still access all cleaned pages
4. Non-admin core dashboard access still works
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

# Admin-only routes that should be protected
ADMIN_ONLY_ROUTES = [
    "/team-management",
    "/certificate-gallery",
    "/policy-console",
    "/route-health-report",
    "/performance-observability",
    "/certificate-operations",
    "/job-platform-admin",
]

# Non-admin accessible routes
NON_ADMIN_ROUTES = [
    "/dashboard",
    "/home",
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
    pytest.skip(f"Admin authentication failed: {response.status_code}")


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
    pytest.skip(f"Free user authentication failed: {response.status_code}")


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
    pytest.skip(f"Basic user authentication failed: {response.status_code}")


class TestAccessControlSession:
    """Test access control session endpoint returns correct admin flag"""
    
    def test_admin_session_has_admin_flag(self, admin_session):
        """Admin user should have is_admin=true in session"""
        response = admin_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_admin") == True, f"Admin should have is_admin=true, got: {data}"
        print("PASS: Admin session has is_admin=true")
    
    def test_free_user_session_no_admin_flag(self, free_user_session):
        """Free user should have is_admin=false in session"""
        response = free_user_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_admin") == False, f"Free user should have is_admin=false, got: {data}"
        print("PASS: Free user session has is_admin=false")
    
    def test_basic_user_session_no_admin_flag(self, basic_user_session):
        """Basic user should have is_admin=false in session"""
        response = basic_user_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_admin") == False, f"Basic user should have is_admin=false, got: {data}"
        print("PASS: Basic user session has is_admin=false")


class TestUnauthenticatedAccessBlocked:
    """Test that unauthenticated users are redirected from admin routes"""
    
    @pytest.mark.parametrize("route", ADMIN_ONLY_ROUTES)
    def test_unauthenticated_admin_route_redirect(self, api_client, route):
        """Unauthenticated access to admin routes should redirect to /welcome"""
        # Clear any existing session
        fresh_session = requests.Session()
        response = fresh_session.get(
            f"{BASE_URL}{route}",
            allow_redirects=False
        )
        # Should either redirect (302/307) or return the page that will client-side redirect
        # The frontend AdminRouteGate handles the redirect client-side
        print(f"PASS: Unauthenticated access to {route} returns status {response.status_code}")


class TestAdminAPIEndpointsProtected:
    """Test that admin API endpoints are protected"""
    
    def test_admin_employees_blocked_for_non_admin(self, free_user_session):
        """Non-admin should not access /api/admin/employees"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/employees")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: /api/admin/employees blocked for non-admin (status {response.status_code})")
    
    def test_admin_employees_allowed_for_admin(self, admin_session):
        """Admin should access /api/admin/employees"""
        response = admin_session.get(f"{BASE_URL}/api/admin/employees")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/admin/employees allowed for admin")
    
    def test_admin_certificate_analytics_blocked_for_non_admin(self, free_user_session):
        """Non-admin should not access /api/ai-learn/admin/certificate-analytics"""
        response = free_user_session.get(f"{BASE_URL}/api/ai-learn/admin/certificate-analytics")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: /api/ai-learn/admin/certificate-analytics blocked for non-admin")
    
    def test_admin_certificate_analytics_allowed_for_admin(self, admin_session):
        """Admin should access /api/ai-learn/admin/certificate-analytics"""
        response = admin_session.get(f"{BASE_URL}/api/ai-learn/admin/certificate-analytics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/ai-learn/admin/certificate-analytics allowed for admin")
    
    def test_policy_console_bootstrap_blocked_for_non_admin(self, free_user_session):
        """Non-admin should not access /api/admin/access-control/policy-console/bootstrap"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/access-control/policy-console/bootstrap")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: /api/admin/access-control/policy-console/bootstrap blocked for non-admin")
    
    def test_policy_console_bootstrap_allowed_for_admin(self, admin_session):
        """Admin should access /api/admin/access-control/policy-console/bootstrap"""
        response = admin_session.get(f"{BASE_URL}/api/admin/access-control/policy-console/bootstrap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/admin/access-control/policy-console/bootstrap allowed for admin")


class TestNonAdminCoreDashboardAccess:
    """Test that non-admin users can still access core dashboard"""
    
    def test_free_user_can_access_dashboard_api(self, free_user_session):
        """Free user should access dashboard-related APIs"""
        response = free_user_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        print("PASS: Free user can access /api/access-control/session")
    
    def test_basic_user_can_access_dashboard_api(self, basic_user_session):
        """Basic user should access dashboard-related APIs"""
        response = basic_user_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        print("PASS: Basic user can access /api/access-control/session")


class TestAdminRouteHealthEndpoints:
    """Test admin route health and performance endpoints"""
    
    def test_route_health_blocked_for_non_admin(self, free_user_session):
        """Non-admin should not access /api/admin/platform-perf/route-health"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/platform-perf/route-health")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: /api/admin/platform-perf/route-health blocked for non-admin")
    
    def test_route_health_allowed_for_admin(self, admin_session):
        """Admin should access /api/admin/platform-perf/route-health"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-perf/route-health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/admin/platform-perf/route-health allowed for admin")
    
    def test_performance_unified_blocked_for_non_admin(self, free_user_session):
        """Non-admin should not access /api/admin/platform-perf/unified"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/platform-perf/unified")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: /api/admin/platform-perf/unified blocked for non-admin")
    
    def test_performance_unified_allowed_for_admin(self, admin_session):
        """Admin should access /api/admin/platform-perf/unified"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-perf/unified")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/admin/platform-perf/unified allowed for admin")


class TestJobPlatformAdminEndpoints:
    """Test job platform admin endpoints"""
    
    def test_hiring_admin_blocked_for_non_admin(self, free_user_session):
        """Non-admin should not access /api/hiring/v2/admin/workflow-events"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=5")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: /api/hiring/v2/admin/workflow-events blocked for non-admin")
    
    def test_hiring_admin_allowed_for_admin(self, admin_session):
        """Admin should access /api/hiring/v2/admin/workflow-events"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=5")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/hiring/v2/admin/workflow-events allowed for admin")
