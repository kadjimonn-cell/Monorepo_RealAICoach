"""
Auth & Access Control Checkpoint Tests
Tests for verifying:
1. Unauthenticated users are blocked from protected routes
2. Login flow works correctly
3. Access control session returns correct subscription tier info
4. Subscription tier gating is enforced
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
BASIC_USER_EMAIL = "f21.basic.1781338672@example.com"
BASIC_USER_PASSWORD = "F21Basic#2026Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestHealthCheck:
    """Health check tests - run first"""
    
    def test_backend_health(self):
        """Verify backend is healthy"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Backend health check failed: {response.status_code}"
        print("✓ Backend health check passed")


class TestUnauthenticatedAccess:
    """Test that unauthenticated users are blocked from protected routes"""
    
    def test_auth_me_unauthenticated(self):
        """Verify /api/auth/me returns 401 for unauthenticated requests"""
        response = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/auth/me correctly returns 401 for unauthenticated users")
    
    def test_access_control_session_unauthenticated(self):
        """Verify /api/access-control/session returns 401 for unauthenticated requests"""
        response = requests.get(f"{BASE_URL}/api/access-control/session", timeout=10)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/access-control/session correctly returns 401 for unauthenticated users")


class TestFreeUserLogin:
    """Test login flow and access control for free user"""
    
    @pytest.fixture
    def free_user_session(self):
        """Login as free user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            # Check if 2FA is required
            if data.get("requires_2fa"):
                pytest.skip("2FA required for free user - skipping authenticated tests")
            return session
        else:
            pytest.skip(f"Login failed with status {login_response.status_code}")
    
    def test_free_user_login(self):
        """Test free user can login successfully"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
        )
        
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Check if 2FA is required or login succeeded
        if data.get("requires_2fa"):
            print("✓ Free user login initiated - 2FA required")
            assert "user_id" in data, "Missing user_id in 2FA response"
        else:
            print("✓ Free user login successful")
            assert "email" in data or "user_id" in data, "Missing user data in response"
    
    def test_free_user_auth_me(self, free_user_session):
        """Test /api/auth/me returns user data for authenticated free user"""
        response = free_user_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "email" in data, "Missing email in auth/me response"
        print(f"✓ /api/auth/me returns user data: {data.get('email')}")
    
    def test_free_user_access_control_session(self, free_user_session):
        """Test access control session returns correct tier for free user"""
        response = free_user_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        effective_plan = data.get("effective_plan", "")
        access_profile = data.get("subscription_access_profile", "")
        
        print("✓ Free user access control session:")
        print(f"  - effective_plan: {effective_plan}")
        print(f"  - subscription_access_profile: {access_profile}")
        
        # Free user should have limited access
        assert effective_plan == "free", f"Expected free plan, got {effective_plan}"
        assert access_profile == "limited", f"Expected limited profile, got {access_profile}"


class TestBasicUserLogin:
    """Test login flow and access control for basic user"""
    
    @pytest.fixture
    def basic_user_session(self):
        """Login as basic user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": BASIC_USER_EMAIL, "password": BASIC_USER_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            if data.get("requires_2fa"):
                pytest.skip("2FA required for basic user - skipping authenticated tests")
            return session
        else:
            pytest.skip(f"Login failed with status {login_response.status_code}")
    
    def test_basic_user_login(self):
        """Test basic user can login successfully"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": BASIC_USER_EMAIL, "password": BASIC_USER_PASSWORD}
        )
        
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        data = response.json()
        
        if data.get("requires_2fa"):
            print("✓ Basic user login initiated - 2FA required")
        else:
            print("✓ Basic user login successful")
    
    def test_basic_user_access_control_session(self, basic_user_session):
        """Test access control session returns correct tier for basic user"""
        response = basic_user_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        effective_plan = data.get("effective_plan", "")
        access_profile = data.get("subscription_access_profile", "")
        
        print("✓ Basic user access control session:")
        print(f"  - effective_plan: {effective_plan}")
        print(f"  - subscription_access_profile: {access_profile}")
        
        # Basic user should have almost_unlimited access
        assert effective_plan == "basic", f"Expected basic plan, got {effective_plan}"
        assert access_profile == "almost_unlimited", f"Expected almost_unlimited profile, got {access_profile}"


class TestAdminUserLogin:
    """Test login flow and access control for admin user"""
    
    @pytest.fixture
    def admin_session(self):
        """Login as admin and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            if data.get("requires_2fa"):
                pytest.skip("2FA required for admin - skipping authenticated tests")
            return session
        else:
            pytest.skip(f"Admin login failed with status {login_response.status_code}")
    
    def test_admin_login(self):
        """Test admin can login successfully"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        assert response.status_code == 200, f"Admin login failed: {response.status_code} - {response.text}"
        data = response.json()
        
        if data.get("requires_2fa"):
            print("✓ Admin login initiated - 2FA required")
        else:
            print("✓ Admin login successful")
    
    def test_admin_access_control_session(self, admin_session):
        """Test access control session returns premium for admin"""
        response = admin_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        effective_plan = data.get("effective_plan", "")
        is_admin = data.get("is_admin", False)
        
        print("✓ Admin access control session:")
        print(f"  - effective_plan: {effective_plan}")
        print(f"  - is_admin: {is_admin}")
        
        # Admin should have premium access
        assert effective_plan == "premium", f"Expected premium plan for admin, got {effective_plan}"
        assert is_admin == True, "Admin should have is_admin=True"


class TestRouteBlockTelemetry:
    """Test route block telemetry endpoint"""
    
    def test_route_block_telemetry_accepts_post(self):
        """Verify route block telemetry endpoint accepts POST"""
        response = requests.post(
            f"{BASE_URL}/api/auth-compliance/route-block",
            json={
                "path": "/test-path",
                "reason": "test_reason",
                "source": "test_source"
            },
            headers={"Content-Type": "application/json"}
        )
        # Should accept the telemetry (200 or 204)
        assert response.status_code in [200, 204, 201], f"Telemetry endpoint failed: {response.status_code}"
        print("✓ Route block telemetry endpoint accepts POST")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
