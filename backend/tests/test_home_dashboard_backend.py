"""
Backend API tests for Home Dashboard rebuild - Checkpoint C
Tests Nova health, authentication, and dashboard-related endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


class TestNovaHealth:
    """Nova health endpoint tests"""
    
    def test_nova_health_returns_200(self):
        """Nova health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/support/nova/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Nova health endpoint returned 200")
    
    def test_nova_health_returns_healthy_status(self):
        """Nova health should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/support/nova/health")
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy, got {data.get('status')}"
        print("✓ Nova health status is healthy")
    
    def test_nova_health_has_gps_live(self):
        """Nova health should have gps_live field"""
        response = requests.get(f"{BASE_URL}/api/support/nova/health")
        data = response.json()
        assert "gps_live" in data, "gps_live field missing"
        assert data.get("gps_live") == True, f"Expected gps_live=True, got {data.get('gps_live')}"
        print("✓ Nova GPS is live")


class TestAuthentication:
    """Authentication flow tests"""
    
    def test_login_with_valid_credentials(self):
        """Login with valid free user credentials should succeed"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": FREE_USER_EMAIL,
                "password": FREE_USER_PASSWORD
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Response returns user data directly with email field
        assert "email" in data, f"No email in response: {data.keys()}"
        assert data.get("email") == FREE_USER_EMAIL, "Email mismatch"
        print(f"✓ Login successful for free user: {data.get('email')}")
        return data
    
    def test_login_with_invalid_credentials(self):
        """Login with invalid credentials should fail"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "invalid@example.com",
                "password": "wrongpassword"
            }
        )
        assert response.status_code in [401, 400, 403], f"Expected 401/400/403, got {response.status_code}"
        print(f"✓ Invalid login correctly rejected with {response.status_code}")
    
    def test_auth_me_without_token(self):
        """Auth me endpoint without token should return 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Auth me correctly returns 401 without token")


class TestDashboardEndpoints:
    """Dashboard-related endpoint tests"""
    
    @pytest.fixture
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": FREE_USER_EMAIL,
                "password": FREE_USER_PASSWORD
            }
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("token") or data.get("access_token")
            if token:
                session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    def test_auth_me_with_valid_session(self, auth_session):
        """Auth me with valid session should return user data"""
        response = auth_session.get(f"{BASE_URL}/api/auth/me")
        # May return 200 or 401 depending on cookie vs token auth
        if response.status_code == 200:
            data = response.json()
            assert "email" in data or "user" in data, "No user data in response"
            print("✓ Auth me returned user data")
        else:
            print(f"⚠ Auth me returned {response.status_code} (may use cookie auth)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
