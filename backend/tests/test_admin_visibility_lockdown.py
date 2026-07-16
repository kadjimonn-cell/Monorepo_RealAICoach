"""
Admin Visibility Lockdown Tests
Tests for verifying non-admin users cannot access admin-only routes and features.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
BASIC_EMAIL = "f22.basic.20260613@example.com"
BASIC_PASSWORD = "F22Basic#2026Aa"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


class TestAdminVisibilityLockdown:
    """Test suite for admin visibility lockdown verification"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if response.status_code == 200:
            data = response.json()
            if data.get("requires_2fa"):
                pytest.skip("Admin requires 2FA - skipping admin tests")
            return session
        pytest.skip(f"Admin login failed: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def basic_session(self):
        """Get authenticated basic user session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_EMAIL,
            "password": BASIC_PASSWORD
        })
        
        if response.status_code == 200:
            data = response.json()
            if data.get("requires_2fa"):
                pytest.skip("Basic user requires 2FA - skipping basic user tests")
            return session
        pytest.skip(f"Basic user login failed: {response.status_code}")
    
    @pytest.fixture(scope="class")
    def free_session(self):
        """Get authenticated free user session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_EMAIL,
            "password": FREE_PASSWORD
        })
        
        if response.status_code == 200:
            data = response.json()
            if data.get("requires_2fa"):
                pytest.skip("Free user requires 2FA - skipping free user tests")
            return session
        pytest.skip(f"Free user login failed: {response.status_code}")
    
    # ==================== Admin User Tests ====================
    
    def test_admin_can_access_auth_me(self, admin_session):
        """Admin user should have is_admin=true in /auth/me response"""
        response = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("is_admin") == True, f"Admin should have is_admin=true, got: {data.get('is_admin')}"
        print("✅ Admin user has is_admin=true")
    
    def test_admin_can_access_admin_features_lifecycle(self, admin_session):
        """Admin should be able to access /admin/features/lifecycle-audit"""
        response = admin_session.get(f"{BASE_URL}/api/admin/features/lifecycle-audit")
        # Admin should get 200 or at least not 403
        assert response.status_code != 403, "Admin should not get 403 for lifecycle-audit"
        print(f"✅ Admin can access features lifecycle audit (status: {response.status_code})")
    
    def test_admin_can_access_system_health(self, admin_session):
        """Admin should be able to access /system/health"""
        response = admin_session.get(f"{BASE_URL}/api/system/health")
        # Admin should get 200 or at least not 403
        assert response.status_code != 403, "Admin should not get 403 for system health"
        print(f"✅ Admin can access system health (status: {response.status_code})")
    
    # ==================== Non-Admin User Tests ====================
    
    def test_basic_user_is_not_admin(self, basic_session):
        """Basic user should NOT have is_admin=true in /auth/me response"""
        response = basic_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        
        data = response.json()
        is_admin = data.get("is_admin")
        # is_admin should be False, None, or not present
        assert is_admin != True, f"Basic user should NOT have is_admin=true, got: {is_admin}"
        print(f"✅ Basic user does NOT have is_admin=true (is_admin={is_admin})")
    
    def test_free_user_is_not_admin(self, free_session):
        """Free user should NOT have is_admin=true in /auth/me response"""
        response = free_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        
        data = response.json()
        is_admin = data.get("is_admin")
        # is_admin should be False, None, or not present
        assert is_admin != True, f"Free user should NOT have is_admin=true, got: {is_admin}"
        print(f"✅ Free user does NOT have is_admin=true (is_admin={is_admin})")
    
    def test_basic_user_cannot_access_admin_features_lifecycle(self, basic_session):
        """Non-admin should NOT be able to access /admin/features/lifecycle-audit"""
        response = basic_session.get(f"{BASE_URL}/api/admin/features/lifecycle-audit")
        # Non-admin should get 401 or 403
        assert response.status_code in [401, 403], f"Non-admin should get 401/403 for lifecycle-audit, got: {response.status_code}"
        print(f"✅ Basic user blocked from features lifecycle audit (status: {response.status_code})")
    
    def test_free_user_cannot_access_admin_features_lifecycle(self, free_session):
        """Non-admin should NOT be able to access /admin/features/lifecycle-audit"""
        response = free_session.get(f"{BASE_URL}/api/admin/features/lifecycle-audit")
        # Non-admin should get 401 or 403
        assert response.status_code in [401, 403], f"Non-admin should get 401/403 for lifecycle-audit, got: {response.status_code}"
        print(f"✅ Free user blocked from features lifecycle audit (status: {response.status_code})")
    
    def test_basic_user_access_control_session(self, basic_session):
        """Basic user access-control session should NOT have is_admin=true"""
        response = basic_session.get(f"{BASE_URL}/api/access-control/session")
        if response.status_code == 200:
            data = response.json()
            is_admin = data.get("is_admin")
            actor_type = data.get("actor_type")
            assert is_admin != True, f"Basic user access-control should NOT have is_admin=true, got: {is_admin}"
            assert actor_type != "admin", f"Basic user should NOT have actor_type=admin, got: {actor_type}"
            print(f"✅ Basic user access-control session: is_admin={is_admin}, actor_type={actor_type}")
        else:
            print(f"⚠️ Access-control session returned {response.status_code}")
    
    def test_free_user_access_control_session(self, free_session):
        """Free user access-control session should NOT have is_admin=true"""
        response = free_session.get(f"{BASE_URL}/api/access-control/session")
        if response.status_code == 200:
            data = response.json()
            is_admin = data.get("is_admin")
            actor_type = data.get("actor_type")
            assert is_admin != True, f"Free user access-control should NOT have is_admin=true, got: {is_admin}"
            assert actor_type != "admin", f"Free user should NOT have actor_type=admin, got: {actor_type}"
            print(f"✅ Free user access-control session: is_admin={is_admin}, actor_type={actor_type}")
        else:
            print(f"⚠️ Access-control session returned {response.status_code}")


class TestAdminOnlyEndpoints:
    """Test that admin-only endpoints are properly protected"""
    
    @pytest.fixture(scope="class")
    def basic_session(self):
        """Get authenticated basic user session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_EMAIL,
            "password": BASIC_PASSWORD
        })
        
        if response.status_code == 200:
            data = response.json()
            if data.get("requires_2fa"):
                pytest.skip("Basic user requires 2FA")
            return session
        pytest.skip(f"Basic user login failed: {response.status_code}")
    
    def test_admin_referrals_integrity_blocked(self, basic_session):
        """Non-admin should be blocked from /referrals/admin/integrity-alerts"""
        response = basic_session.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts")
        assert response.status_code in [401, 403, 404], f"Expected 401/403/404, got: {response.status_code}"
        print(f"✅ Non-admin blocked from referrals admin integrity (status: {response.status_code})")
    
    def test_admin_referrals_fraud_policy_blocked(self, basic_session):
        """Non-admin should be blocked from /referrals/admin/fraud-policy/recommendation"""
        response = basic_session.get(f"{BASE_URL}/api/referrals/admin/fraud-policy/recommendation")
        assert response.status_code in [401, 403, 404], f"Expected 401/403/404, got: {response.status_code}"
        print(f"✅ Non-admin blocked from referrals admin fraud policy (status: {response.status_code})")
    
    def test_team_management_blocked(self, basic_session):
        """Non-admin should be blocked from /team-management endpoints"""
        response = basic_session.get(f"{BASE_URL}/api/team-management/members")
        assert response.status_code in [401, 403, 404], f"Expected 401/403/404, got: {response.status_code}"
        print(f"✅ Non-admin blocked from team management (status: {response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
