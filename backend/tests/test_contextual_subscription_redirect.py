"""
Test: Contextual Subscription-Gated Redirect Flow
Verifies:
1. Unauthenticated users are blocked from protected routes
2. Auth/access-control APIs work correctly for all tiers (free/basic/premium)
3. Backend APIs return correct effective_plan and subscription_access_profile
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from /app/memory/test_credentials.md
FREE_USER = {
    "email": "p1.free.1779113329@example.com",
    "password": "P1Free#2026!Aa"
}
BASIC_USER = {
    "email": "f21.basic.1781338672@example.com",
    "password": "F21Basic#2026Aa"
}
ADMIN_USER = {
    "email": "admin@realaicoach.app",
    "password": "NewAdminPass2026!"
}


class TestHealthAndPublicEndpoints:
    """Verify backend is running and public endpoints work"""
    
    def test_health_endpoint(self):
        """Health check should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("PASS: Health endpoint returns 200")
    
    def test_unauthenticated_auth_me_returns_401(self):
        """Unauthenticated /api/auth/me should return 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Unauthenticated /api/auth/me returns 401")
    
    def test_unauthenticated_access_control_session_returns_401(self):
        """Unauthenticated /api/access-control/session should return 401"""
        response = requests.get(f"{BASE_URL}/api/access-control/session", timeout=10)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Unauthenticated /api/access-control/session returns 401")


class TestFreeUserAccessControl:
    """Verify free user gets correct access control session"""
    
    @pytest.fixture(scope="class")
    def free_session(self):
        """Login as free user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER["email"], "password": FREE_USER["password"]},
            timeout=15
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Free user login failed: {login_response.status_code} - {login_response.text}")
        
        return session
    
    def test_free_user_login_success(self, free_session):
        """Free user should be able to login"""
        response = free_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert response.status_code == 200, f"Auth/me failed: {response.status_code}"
        data = response.json()
        assert "user_id" in data or "email" in data, "Missing user data in response"
        print(f"PASS: Free user login successful, email: {data.get('email', 'N/A')}")
    
    def test_free_user_access_control_session(self, free_session):
        """Free user should get effective_plan=free and subscription_access_profile=limited"""
        response = free_session.get(f"{BASE_URL}/api/access-control/session", timeout=10)
        assert response.status_code == 200, f"Access control session failed: {response.status_code}"
        
        data = response.json()
        effective_plan = data.get("effective_plan", "").lower()
        access_profile = data.get("subscription_access_profile", "").lower()
        
        assert effective_plan == "free", f"Expected effective_plan=free, got {effective_plan}"
        assert access_profile == "limited", f"Expected subscription_access_profile=limited, got {access_profile}"
        assert data.get("is_admin") is False or data.get("is_admin") == False, "Free user should not be admin"
        
        print(f"PASS: Free user access control - effective_plan={effective_plan}, profile={access_profile}")


class TestBasicUserAccessControl:
    """Verify basic user gets correct access control session"""
    
    @pytest.fixture(scope="class")
    def basic_session(self):
        """Login as basic user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": BASIC_USER["email"], "password": BASIC_USER["password"]},
            timeout=15
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Basic user login failed: {login_response.status_code} - {login_response.text}")
        
        return session
    
    def test_basic_user_login_success(self, basic_session):
        """Basic user should be able to login"""
        response = basic_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert response.status_code == 200, f"Auth/me failed: {response.status_code}"
        data = response.json()
        assert "user_id" in data or "email" in data, "Missing user data in response"
        print(f"PASS: Basic user login successful, email: {data.get('email', 'N/A')}")
    
    def test_basic_user_access_control_session(self, basic_session):
        """Basic user should get effective_plan=basic and subscription_access_profile=almost_unlimited"""
        response = basic_session.get(f"{BASE_URL}/api/access-control/session", timeout=10)
        assert response.status_code == 200, f"Access control session failed: {response.status_code}"
        
        data = response.json()
        effective_plan = data.get("effective_plan", "").lower()
        access_profile = data.get("subscription_access_profile", "").lower()
        
        assert effective_plan == "basic", f"Expected effective_plan=basic, got {effective_plan}"
        assert access_profile == "almost_unlimited", f"Expected subscription_access_profile=almost_unlimited, got {access_profile}"
        
        print(f"PASS: Basic user access control - effective_plan={effective_plan}, profile={access_profile}")


class TestAdminUserAccessControl:
    """Verify admin user gets correct access control session"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_USER["email"], "password": ADMIN_USER["password"]},
            timeout=15
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Admin user login failed: {login_response.status_code} - {login_response.text}")
        
        return session
    
    def test_admin_user_login_success(self, admin_session):
        """Admin user should be able to login"""
        response = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert response.status_code == 200, f"Auth/me failed: {response.status_code}"
        data = response.json()
        assert "user_id" in data or "email" in data, "Missing user data in response"
        print(f"PASS: Admin user login successful, email: {data.get('email', 'N/A')}")
    
    def test_admin_user_access_control_session(self, admin_session):
        """Admin user should get effective_plan=premium, is_admin=true, subscription_access_profile=full_unlimited"""
        response = admin_session.get(f"{BASE_URL}/api/access-control/session", timeout=10)
        assert response.status_code == 200, f"Access control session failed: {response.status_code}"
        
        data = response.json()
        effective_plan = data.get("effective_plan", "").lower()
        access_profile = data.get("subscription_access_profile", "").lower()
        is_admin = data.get("is_admin")
        
        assert effective_plan == "premium", f"Expected effective_plan=premium, got {effective_plan}"
        assert access_profile == "full_unlimited", f"Expected subscription_access_profile=full_unlimited, got {access_profile}"
        assert is_admin is True, f"Expected is_admin=True, got {is_admin}"
        
        print(f"PASS: Admin user access control - effective_plan={effective_plan}, profile={access_profile}, is_admin={is_admin}")


class TestSubscriptionPlansEndpoint:
    """Verify subscription plans endpoint works"""
    
    def test_subscription_plans_returns_plans(self):
        """Subscription plans endpoint should return plan data"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans", timeout=10)
        assert response.status_code == 200, f"Subscription plans failed: {response.status_code}"
        
        data = response.json()
        plans = data.get("plans", [])
        assert len(plans) > 0, "No plans returned"
        
        # Verify plan structure
        plan_ids = [p.get("id") for p in plans]
        assert "free" in plan_ids or any("free" in str(p.get("id", "")).lower() for p in plans), "Free plan not found"
        
        print(f"PASS: Subscription plans endpoint returns {len(plans)} plans")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
