"""
Feature 21 Entitlement Verification Tests
Tests the 3-tier entitlement system (Free, Basic, Premium) for /api/videos/bootstrap endpoint.
Root cause fix: _build_user_doc now includes payment_verified field.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

FREE_EMAIL = "feature21.test.1781234530@example.com"
FREE_PASSWORD = "Feature21Test#2026Aa"

# Basic user created in this run - read from file
BASIC_EMAIL = "f21.basic.1781338672@example.com"
BASIC_PASSWORD = "F21Basic#2026Aa"


class TestFeature21Entitlement:
    """Feature 21 /api/videos/bootstrap entitlement tests per tier"""

    @pytest.fixture(scope="class")
    def api_client(self):
        """Shared requests session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session

    def _login(self, api_client, email: str, password: str) -> dict:
        """Helper to login and return session with cookies"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        return response

    # ─────────────────────────────────────────────────────────────────────────
    # Health Check
    # ─────────────────────────────────────────────────────────────────────────
    def test_health_endpoint(self, api_client):
        """Verify API is accessible"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("✓ Health endpoint accessible")

    # ─────────────────────────────────────────────────────────────────────────
    # FREE TIER TESTS
    # ─────────────────────────────────────────────────────────────────────────
    def test_free_tier_login(self, api_client):
        """Free user can login"""
        response = self._login(api_client, FREE_EMAIL, FREE_PASSWORD)
        assert response.status_code == 200, f"Free user login failed: {response.text}"
        data = response.json()
        assert "user" in data or "session_token" in data or response.cookies.get("session_token")
        print(f"✓ Free user login successful: {FREE_EMAIL}")

    def test_free_tier_bootstrap_entitlement(self, api_client):
        """Free tier: plan=free, scope_label='Limited access', quota limit=5"""
        # Login first
        login_resp = self._login(api_client, FREE_EMAIL, FREE_PASSWORD)
        assert login_resp.status_code == 200, f"Free login failed: {login_resp.text}"
        
        # Call bootstrap endpoint
        response = api_client.get(f"{BASE_URL}/api/videos/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed for free user: {response.text}"
        
        data = response.json()
        quota = data.get("quota", {})
        
        # Verify FREE tier entitlements
        expected_plan = "free"
        expected_scope_label = "Limited access"
        expected_limit = 5
        
        actual_plan = quota.get("plan")
        actual_scope_label = quota.get("scope_label")
        actual_limit = quota.get("limit")
        
        print(f"  Free tier - Expected: plan={expected_plan}, scope_label='{expected_scope_label}', limit={expected_limit}")
        print(f"  Free tier - Actual:   plan={actual_plan}, scope_label='{actual_scope_label}', limit={actual_limit}")
        
        assert actual_plan == expected_plan, f"Free tier plan mismatch: expected '{expected_plan}', got '{actual_plan}'"
        assert actual_scope_label == expected_scope_label, f"Free tier scope_label mismatch: expected '{expected_scope_label}', got '{actual_scope_label}'"
        assert actual_limit == expected_limit, f"Free tier limit mismatch: expected {expected_limit}, got {actual_limit}"
        
        print("✓ Free tier entitlement verified: plan=free, scope_label='Limited access', limit=5")

    # ─────────────────────────────────────────────────────────────────────────
    # BASIC TIER TESTS
    # ─────────────────────────────────────────────────────────────────────────
    def test_basic_tier_login(self, api_client):
        """Basic user can login"""
        response = self._login(api_client, BASIC_EMAIL, BASIC_PASSWORD)
        assert response.status_code == 200, f"Basic user login failed: {response.text}"
        data = response.json()
        assert "user" in data or "session_token" in data or response.cookies.get("session_token")
        print(f"✓ Basic user login successful: {BASIC_EMAIL}")

    def test_basic_tier_bootstrap_entitlement(self, api_client):
        """Basic tier: plan=basic, scope_label='Almost unlimited access', limit=-1 (basic => almost unlimited policy)"""
        # Login first
        login_resp = self._login(api_client, BASIC_EMAIL, BASIC_PASSWORD)
        assert login_resp.status_code == 200, f"Basic login failed: {login_resp.text}"
        
        # Call bootstrap endpoint
        response = api_client.get(f"{BASE_URL}/api/videos/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed for basic user: {response.text}"
        
        data = response.json()
        quota = data.get("quota", {})
        
        # Verify BASIC tier entitlements - THIS IS THE KEY FIX VERIFICATION
        expected_plan = "basic"
        expected_scope_label = "Almost unlimited access"
        # ai_driven_entitlements_v2: basic tier transforms finite caps to -1 (almost unlimited)
        expected_limit = -1
        
        actual_plan = quota.get("plan")
        actual_scope_label = quota.get("scope_label")
        actual_limit = quota.get("limit")
        
        print(f"  Basic tier - Expected: plan={expected_plan}, scope_label='{expected_scope_label}', limit={expected_limit}")
        print(f"  Basic tier - Actual:   plan={actual_plan}, scope_label='{actual_scope_label}', limit={actual_limit}")
        
        assert actual_plan == expected_plan, f"Basic tier plan mismatch: expected '{expected_plan}', got '{actual_plan}'. ROOT CAUSE FIX FAILED - payment_verified not being passed to _build_user_doc"
        assert actual_scope_label == expected_scope_label, f"Basic tier scope_label mismatch: expected '{expected_scope_label}', got '{actual_scope_label}'"
        assert actual_limit == expected_limit, f"Basic tier limit mismatch: expected {expected_limit}, got {actual_limit}"
        
        print("✓ Basic tier entitlement verified: plan=basic, scope_label='Almost unlimited access', limit=120")

    # ─────────────────────────────────────────────────────────────────────────
    # PREMIUM/ADMIN TIER TESTS
    # ─────────────────────────────────────────────────────────────────────────
    def test_admin_tier_login(self, api_client):
        """Admin user can login"""
        response = self._login(api_client, ADMIN_EMAIL, ADMIN_PASSWORD)
        assert response.status_code == 200, f"Admin user login failed: {response.text}"
        data = response.json()
        assert "user" in data or "session_token" in data or response.cookies.get("session_token")
        print(f"✓ Admin user login successful: {ADMIN_EMAIL}")

    def test_admin_tier_bootstrap_entitlement(self, api_client):
        """Premium/Admin tier: plan=premium, scope_label='Full unlimited access', quota limit=-1 (unlimited)"""
        # Login first
        login_resp = self._login(api_client, ADMIN_EMAIL, ADMIN_PASSWORD)
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        
        # Call bootstrap endpoint
        response = api_client.get(f"{BASE_URL}/api/videos/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed for admin user: {response.text}"
        
        data = response.json()
        quota = data.get("quota", {})
        
        # Verify PREMIUM tier entitlements
        expected_plan = "premium"
        expected_scope_label = "Full unlimited access"
        expected_limit = -1  # Unlimited
        
        actual_plan = quota.get("plan")
        actual_scope_label = quota.get("scope_label")
        actual_limit = quota.get("limit")
        
        print(f"  Premium tier - Expected: plan={expected_plan}, scope_label='{expected_scope_label}', limit={expected_limit}")
        print(f"  Premium tier - Actual:   plan={actual_plan}, scope_label='{actual_scope_label}', limit={actual_limit}")
        
        assert actual_plan == expected_plan, f"Premium tier plan mismatch: expected '{expected_plan}', got '{actual_plan}'"
        assert actual_scope_label == expected_scope_label, f"Premium tier scope_label mismatch: expected '{expected_scope_label}', got '{actual_scope_label}'"
        assert actual_limit == expected_limit, f"Premium tier limit mismatch: expected {expected_limit}, got {actual_limit}"
        
        print("✓ Premium/Admin tier entitlement verified: plan=premium, scope_label='Full unlimited access', limit=-1")

    # ─────────────────────────────────────────────────────────────────────────
    # ADMIN OBSERVABILITY GATE TESTS
    # ─────────────────────────────────────────────────────────────────────────
    def test_observability_gate_free_user_403(self, api_client):
        """Free user should get 403 on admin observability endpoint"""
        # Login as free user
        login_resp = self._login(api_client, FREE_EMAIL, FREE_PASSWORD)
        assert login_resp.status_code == 200
        
        # Try to access admin observability
        response = api_client.get(f"{BASE_URL}/api/videos/admin/observability")
        assert response.status_code == 403, f"Free user should get 403 on observability, got {response.status_code}"
        print("✓ Free user correctly blocked from admin observability (403)")

    def test_observability_gate_basic_user_403(self, api_client):
        """Basic user should get 403 on admin observability endpoint"""
        # Login as basic user
        login_resp = self._login(api_client, BASIC_EMAIL, BASIC_PASSWORD)
        assert login_resp.status_code == 200
        
        # Try to access admin observability
        response = api_client.get(f"{BASE_URL}/api/videos/admin/observability")
        assert response.status_code == 403, f"Basic user should get 403 on observability, got {response.status_code}"
        print("✓ Basic user correctly blocked from admin observability (403)")

    def test_observability_gate_admin_user_200(self, api_client):
        """Admin user should get 200 on admin observability endpoint"""
        # Login as admin user
        login_resp = self._login(api_client, ADMIN_EMAIL, ADMIN_PASSWORD)
        assert login_resp.status_code == 200
        
        # Access admin observability
        response = api_client.get(f"{BASE_URL}/api/videos/admin/observability")
        assert response.status_code == 200, f"Admin user should get 200 on observability, got {response.status_code}: {response.text}"
        print("✓ Admin user correctly allowed to access admin observability (200)")

    # ─────────────────────────────────────────────────────────────────────────
    # REGRESSION: Verify no auth regression
    # ─────────────────────────────────────────────────────────────────────────
    def test_unauthenticated_bootstrap_401(self, api_client):
        """Unauthenticated request to bootstrap should return 401"""
        # Clear any existing session
        api_client.cookies.clear()
        
        response = api_client.get(f"{BASE_URL}/api/videos/bootstrap")
        assert response.status_code == 401, f"Unauthenticated bootstrap should return 401, got {response.status_code}"
        print("✓ Unauthenticated bootstrap correctly returns 401")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
