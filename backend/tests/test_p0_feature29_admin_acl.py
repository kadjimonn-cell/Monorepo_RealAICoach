"""
P0 Verification: Feature 29 Admin ACL + Free User Access Tests
Tests:
1. Free user MUST NOT access /api/podcasts/v2/admin/conversion-dashboard (403)
2. Admin user MUST access /api/podcasts/v2/admin/conversion-dashboard (200)
3. Free user CAN access /api/podcasts/v2/bootstrap (200)
4. Free user CAN access /api/podcasts/v2/season-arc (200)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestFeature29AdminACL:
    """Feature 29 Admin ACL verification tests"""

    @pytest.fixture(scope="class")
    def free_user_session(self):
        """Login as free user and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Free user login failed: {login_response.status_code} - {login_response.text}")
        
        return session

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin user and return session with cookies"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text}")
        
        return session

    def test_free_user_blocked_from_admin_conversion_dashboard(self, free_user_session):
        """Free user MUST NOT access /api/podcasts/v2/admin/conversion-dashboard"""
        response = free_user_session.get(
            f"{BASE_URL}/api/podcasts/v2/admin/conversion-dashboard"
        )
        
        # Should be 403 Forbidden for non-admin users
        assert response.status_code == 403, (
            f"Expected 403 for free user accessing admin endpoint, got {response.status_code}. "
            f"Response: {response.text[:500]}"
        )
        
        # Verify error message indicates admin access required
        data = response.json()
        assert "Admin" in str(data.get("error", "")) or "admin" in str(data.get("message", "")).lower(), (
            f"Expected admin access error message, got: {data}"
        )
        print("PASS: Free user correctly blocked from admin endpoint (403)")

    def test_admin_user_can_access_conversion_dashboard(self, admin_session):
        """Admin user MUST access /api/podcasts/v2/admin/conversion-dashboard successfully"""
        response = admin_session.get(
            f"{BASE_URL}/api/podcasts/v2/admin/conversion-dashboard"
        )
        
        # Should be 200 OK for admin users
        assert response.status_code == 200, (
            f"Expected 200 for admin accessing admin endpoint, got {response.status_code}. "
            f"Response: {response.text[:500]}"
        )
        
        # Verify response contains expected KPI fields
        data = response.json()
        assert "kpis" in data or "feature_id" in data, (
            f"Expected kpis or feature_id in response, got: {list(data.keys())}"
        )
        print("PASS: Admin user can access conversion dashboard (200)")
        print(f"Response keys: {list(data.keys())}")

    def test_free_user_can_access_bootstrap(self, free_user_session):
        """Free user CAN access /api/podcasts/v2/bootstrap"""
        response = free_user_session.get(
            f"{BASE_URL}/api/podcasts/v2/bootstrap"
        )
        
        # Should be 200 OK for free users (in FREE_PATTERNS)
        assert response.status_code == 200, (
            f"Expected 200 for free user accessing bootstrap, got {response.status_code}. "
            f"Response: {response.text[:500]}"
        )
        
        data = response.json()
        assert "feature_id" in data or "catalog" in data, (
            f"Expected feature_id or catalog in response, got: {list(data.keys())}"
        )
        print("PASS: Free user can access bootstrap endpoint (200)")

    def test_free_user_can_access_season_arc(self, free_user_session):
        """Free user CAN access /api/podcasts/v2/season-arc"""
        response = free_user_session.get(
            f"{BASE_URL}/api/podcasts/v2/season-arc"
        )
        
        # Should be 200 OK for free users (in FREE_PATTERNS)
        assert response.status_code == 200, (
            f"Expected 200 for free user accessing season-arc, got {response.status_code}. "
            f"Response: {response.text[:500]}"
        )
        print("PASS: Free user can access season-arc endpoint (200)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
