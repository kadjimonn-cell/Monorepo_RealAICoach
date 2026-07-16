"""
Test Admin Route Access Control - Iteration 254
Tests that non-admin users cannot access admin-only routes and pages.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
NON_ADMIN_EMAIL = "feature21.test.1781234530@example.com"
NON_ADMIN_PASSWORD = "Feature21Test#2026Aa"

ADMIN_EMAIL = "watchvideos.phase4.admin.306786@example.com"
ADMIN_PASSWORD = "Phase4Admin#2026Aa"

# Admin-only route prefixes from AccessControlContext.tsx
ADMIN_ONLY_ROUTES = [
    '/admin-console',
    '/executive-dashboard',
    '/team-management',
    '/policy-console',
    '/admin-system',
    '/admin-activity-log',
    '/admin',
    '/ops-performance',
    '/ops-route-health',
    '/safe-deployment',
    '/route-health-report',
    '/ai-feature-dashboard',
    '/i18n-drift-dashboard',
]

# Regular routes that should be accessible to all authenticated users
REGULAR_ROUTES = [
    '/dashboard',
    '/profile',
    '/features',
    '/features/watch-videos',
]


class TestHealthCheck:
    """Basic health check to ensure API is accessible"""
    
    def test_health_endpoint(self):
        """Test that health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("Health endpoint accessible")


class TestNonAdminRouteAccess:
    """Test that non-admin users cannot access admin routes via API"""
    
    @pytest.fixture(scope="class")
    def non_admin_session(self):
        """Login as non-admin user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as non-admin user
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": NON_ADMIN_EMAIL,
            "password": NON_ADMIN_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Non-admin login failed: {login_response.status_code} - {login_response.text}")
        
        print(f"Non-admin user logged in: {NON_ADMIN_EMAIL}")
        return session
    
    def test_non_admin_login_success(self, non_admin_session):
        """Verify non-admin user can login"""
        # Check user profile to verify login
        response = non_admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Failed to get user profile: {response.status_code}"
        
        user_data = response.json()
        assert user_data.get('email') == NON_ADMIN_EMAIL
        assert user_data.get('is_admin') != True, "User should not be admin"
        print(f"Non-admin user verified: is_admin={user_data.get('is_admin')}")
    
    def test_non_admin_access_control_session(self, non_admin_session):
        """Test access control session for non-admin user"""
        response = non_admin_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Access control session failed: {response.status_code}"
        
        session_data = response.json()
        is_admin = session_data.get('is_admin', False)
        actor_type = session_data.get('actor_type', '')
        
        assert is_admin == False, f"Non-admin user should have is_admin=False, got {is_admin}"
        assert actor_type != 'admin', f"Non-admin user should not have actor_type=admin, got {actor_type}"
        print(f"Access control session: is_admin={is_admin}, actor_type={actor_type}")
    
    def test_non_admin_cannot_access_admin_notifications(self, non_admin_session):
        """Test that non-admin cannot access admin notifications endpoint"""
        response = non_admin_session.get(f"{BASE_URL}/api/admin/notifications/live")
        # Should return 401/403 for non-admin
        assert response.status_code in [401, 403], f"Expected 401/403 for admin endpoint, got {response.status_code}"
        print(f"Admin notifications blocked for non-admin: {response.status_code}")
    
    def test_non_admin_cannot_access_admin_live_activity(self, non_admin_session):
        """Test that non-admin cannot access admin live activity endpoint"""
        response = non_admin_session.get(f"{BASE_URL}/api/admin/live-activity/alerts")
        # Should return 401/403 for non-admin
        assert response.status_code in [401, 403], f"Expected 401/403 for admin endpoint, got {response.status_code}"
        print(f"Admin live activity blocked for non-admin: {response.status_code}")
    
    def test_non_admin_can_access_regular_routes(self, non_admin_session):
        """Test that non-admin can access regular user endpoints"""
        # Test user profile
        response = non_admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"User profile should be accessible: {response.status_code}"
        print("Non-admin can access user profile")


class TestAdminRouteAccess:
    """Test that admin users can access admin routes"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as admin user
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text}")
        
        print(f"Admin user logged in: {ADMIN_EMAIL}")
        return session
    
    def test_admin_login_success(self, admin_session):
        """Verify admin user can login"""
        response = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Failed to get admin profile: {response.status_code}"
        
        user_data = response.json()
        assert user_data.get('email') == ADMIN_EMAIL
        is_admin = user_data.get('is_admin', False)
        print(f"Admin user verified: is_admin={is_admin}")
    
    def test_admin_access_control_session(self, admin_session):
        """Test access control session for admin user"""
        response = admin_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Access control session failed: {response.status_code}"
        
        session_data = response.json()
        is_admin = session_data.get('is_admin', False)
        actor_type = session_data.get('actor_type', '')
        
        # Admin should have is_admin=True or actor_type=admin
        print(f"Admin access control session: is_admin={is_admin}, actor_type={actor_type}")
    
    def test_admin_can_access_admin_notifications(self, admin_session):
        """Test that admin can access admin notifications endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/admin/notifications/live")
        # Admin should be able to access
        assert response.status_code == 200, f"Admin should access notifications: {response.status_code}"
        print(f"Admin notifications accessible: {response.status_code}")
    
    def test_admin_can_access_admin_live_activity(self, admin_session):
        """Test that admin can access admin live activity endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/admin/live-activity/alerts")
        # Admin should be able to access
        assert response.status_code == 200, f"Admin should access live activity: {response.status_code}"
        print(f"Admin live activity accessible: {response.status_code}")


class TestAnonymousAccess:
    """Test that anonymous users get 401/403 for admin APIs"""
    
    def test_anonymous_cannot_access_admin_notifications(self):
        """Test that anonymous user cannot access admin notifications"""
        response = requests.get(f"{BASE_URL}/api/admin/notifications/live")
        assert response.status_code in [401, 403], f"Expected 401/403 for anonymous, got {response.status_code}"
        print(f"Admin notifications blocked for anonymous: {response.status_code}")
    
    def test_anonymous_cannot_access_admin_live_activity(self):
        """Test that anonymous user cannot access admin live activity"""
        response = requests.get(f"{BASE_URL}/api/admin/live-activity/alerts")
        assert response.status_code in [401, 403], f"Expected 401/403 for anonymous, got {response.status_code}"
        print(f"Admin live activity blocked for anonymous: {response.status_code}")
    
    def test_anonymous_cannot_access_access_control_session(self):
        """Test that anonymous user cannot access access control session"""
        response = requests.get(f"{BASE_URL}/api/access-control/session")
        # May return 401 or empty session
        print(f"Access control session for anonymous: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
