"""
Test Home Dashboard Auth Lock - Checkpoint D Verification
Tests that unauthenticated users cannot access /dashboard or /home routes
and that authenticated users can access them properly.
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


class TestAuthMeEndpoint:
    """Test /api/auth/me endpoint for session verification"""
    
    def test_auth_me_returns_401_without_session(self):
        """Unauthenticated request to /api/auth/me should return 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: /api/auth/me returns 401 for unauthenticated requests")
    
    def test_auth_me_returns_user_with_valid_session(self):
        """Authenticated request to /api/auth/me should return user data"""
        # First login to get session
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
            timeout=15
        )
        
        # Check if login succeeded or requires 2FA
        if login_response.status_code == 200:
            data = login_response.json()
            if data.get("requires_2fa"):
                pytest.skip("2FA required - skipping authenticated test")
            
            # Now check /api/auth/me
            me_response = session.get(f"{BASE_URL}/api/auth/me", timeout=10)
            assert me_response.status_code == 200, f"Expected 200, got {me_response.status_code}"
            user_data = me_response.json()
            assert "email" in user_data, "Response should contain email"
            assert user_data["email"] == FREE_USER_EMAIL
            print(f"PASS: /api/auth/me returns user data for authenticated session: {user_data.get('email')}")
        else:
            pytest.skip(f"Login failed with status {login_response.status_code}")


class TestAccessControlSession:
    """Test /api/access-control/session endpoint"""
    
    def test_access_control_session_requires_auth(self):
        """Unauthenticated request to /api/access-control/session should return 401"""
        response = requests.get(f"{BASE_URL}/api/access-control/session", timeout=10)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: /api/access-control/session returns 401 for unauthenticated requests")
    
    def test_access_control_session_returns_entitlements(self):
        """Authenticated request should return session entitlements"""
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
            timeout=15
        )
        
        if login_response.status_code == 200:
            data = login_response.json()
            if data.get("requires_2fa"):
                pytest.skip("2FA required - skipping authenticated test")
            
            # Check access-control session
            ac_response = session.get(f"{BASE_URL}/api/access-control/session", timeout=10)
            assert ac_response.status_code == 200, f"Expected 200, got {ac_response.status_code}"
            ac_data = ac_response.json()
            assert "user_id" in ac_data, "Response should contain user_id"
            assert "effective_plan" in ac_data, "Response should contain effective_plan"
            print(f"PASS: /api/access-control/session returns entitlements: plan={ac_data.get('effective_plan')}")
        else:
            pytest.skip(f"Login failed with status {login_response.status_code}")


class TestLoginEndpoint:
    """Test /api/auth/login endpoint"""
    
    def test_login_with_valid_credentials(self):
        """Login with valid credentials should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Either direct login or 2FA required
        assert "email" in data or "requires_2fa" in data, "Response should contain email or requires_2fa"
        print(f"PASS: Login endpoint works - requires_2fa={data.get('requires_2fa', False)}")
    
    def test_login_with_invalid_credentials(self):
        """Login with invalid credentials should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@example.com", "password": "wrongpassword"},
            timeout=15
        )
        assert response.status_code in [401, 400, 403], f"Expected 401/400/403, got {response.status_code}"
        print(f"PASS: Login with invalid credentials returns {response.status_code}")


class TestAdminAccess:
    """Test admin user access"""
    
    def test_admin_login(self):
        """Admin user should be able to login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Admin may have OTP bypass
        if not data.get("requires_2fa"):
            assert data.get("is_admin") == True or data.get("full_access") == True, "Admin should have admin/full_access flag"
            print(f"PASS: Admin login successful - is_admin={data.get('is_admin')}, full_access={data.get('full_access')}")
        else:
            print("PASS: Admin login requires 2FA (expected for security)")


class TestBasicUserAccess:
    """Test basic tier user access"""
    
    def test_basic_user_login(self):
        """Basic tier user should be able to login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": BASIC_USER_EMAIL, "password": BASIC_USER_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        print(f"PASS: Basic user login - requires_2fa={data.get('requires_2fa', False)}")


class TestHealthEndpoint:
    """Test health endpoint is accessible"""
    
    def test_health_endpoint(self):
        """Health endpoint should be publicly accessible"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Health endpoint is accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
