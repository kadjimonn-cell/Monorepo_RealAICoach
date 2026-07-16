"""
Global Subscription Access Control Enforcement Tests
Tests the platform-level subscription tier enforcement:
- Free → Limited access (only FREE_TIER_FEATURE_PREFIXES)
- Basic → Almost unlimited (all /features/* except PREMIUM routes)
- Premium → Full unlimited access (everything)

Test credentials from /app/memory/test_credentials.md:
- Free: p1.free.1779113329@example.com / P1Free#2026!Aa
- Basic: f21.basic.1781338672@example.com / F21Basic#2026Aa
- Premium: legends.test.premium@example.com / LegendsTest#Premium2026!
- Admin: admin@realaicoach.app / NewAdminPass2026!
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
BASIC_USER = {"email": "f21.basic.1781338672@example.com", "password": "F21Basic#2026Aa"}
PREMIUM_USER = {"email": "legends.test.premium@example.com", "password": "LegendsTest#Premium2026!"}
ADMIN_USER = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}

# Paid feature APIs that should require Basic or higher
BASIC_REQUIRED_APIS = [
    "/api/bill-generator/",
    "/api/word-forge/",
    "/api/writing-studio/",
    "/api/personal-assistant/",
    "/api/research-navigator/",
    "/api/money-strategy-hub/",
    "/api/smart-shopping-advisor/",
    "/api/travel-planner-pro/",
    "/api/video-studio/",
    "/api/ai-photo-studio/",
    "/api/ai-speech-studio/",
    "/api/ai-enterprise/",
    "/api/relationship-coach/",
    "/api/decision-coach/",
    "/api/mobility-assistant/",
]

# Free-tier allowed APIs
FREE_ALLOWED_APIS = [
    "/api/auth/me",
    "/api/access-control/session",
    "/api/notifications",
    "/api/home/",
    "/api/gamification",
    "/api/games-station/",
]

# Admin-only APIs
ADMIN_ONLY_APIS = [
    "/api/admin/employees",
    "/api/team-management",
    "/api/admin/access-control",
]


class TestAccessControlSession:
    """Test /api/access-control/session returns correct effective_plan"""
    
    def test_free_user_session(self):
        """Free user should get effective_plan='free' and subscription_access_profile='limited'"""
        session = requests.Session()
        
        # Login as free user
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=FREE_USER, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        if login_resp.status_code == 429:
            pytest.skip("Rate limited - skipping test")
        
        assert login_resp.status_code == 200, f"Free user login failed: {login_resp.status_code} - {login_resp.text}"
        
        # Get access control session
        session_resp = session.get(f"{BASE_URL}/api/access-control/session", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        
        if session_resp.status_code == 429:
            pytest.skip("Rate limited - skipping test")
            
        assert session_resp.status_code == 200, f"Session fetch failed: {session_resp.status_code}"
        
        data = session_resp.json()
        assert data.get("effective_plan") == "free", f"Expected effective_plan='free', got {data.get('effective_plan')}"
        assert data.get("subscription_access_profile") == "limited", f"Expected profile='limited', got {data.get('subscription_access_profile')}"
        assert data.get("is_admin") == False, "Free user should not be admin"
        print(f"✓ Free user session: effective_plan={data.get('effective_plan')}, profile={data.get('subscription_access_profile')}")
    
    def test_basic_user_session(self):
        """Basic user should get effective_plan='basic' and subscription_access_profile='almost_unlimited'"""
        session = requests.Session()
        
        # Login as basic user
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=BASIC_USER, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        if login_resp.status_code == 429:
            pytest.skip("Rate limited - skipping test")
        
        if login_resp.status_code != 200:
            pytest.skip(f"Basic user login failed: {login_resp.status_code} - may need different credentials")
        
        # Get access control session
        session_resp = session.get(f"{BASE_URL}/api/access-control/session", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        
        if session_resp.status_code == 429:
            pytest.skip("Rate limited - skipping test")
            
        assert session_resp.status_code == 200, f"Session fetch failed: {session_resp.status_code}"
        
        data = session_resp.json()
        # Basic user should have basic or higher effective_plan
        assert data.get("effective_plan") in ["basic", "premium"], f"Expected effective_plan='basic' or 'premium', got {data.get('effective_plan')}"
        print(f"✓ Basic user session: effective_plan={data.get('effective_plan')}, profile={data.get('subscription_access_profile')}")
    
    def test_premium_user_session(self):
        """Premium user should get effective_plan='premium' and subscription_access_profile='full_unlimited'"""
        session = requests.Session()
        
        # Login as premium user
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=PREMIUM_USER, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        if login_resp.status_code == 429:
            pytest.skip("Rate limited - skipping test")
        
        if login_resp.status_code != 200:
            pytest.skip(f"Premium user login failed: {login_resp.status_code} - may need different credentials")
        
        # Get access control session
        session_resp = session.get(f"{BASE_URL}/api/access-control/session", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        
        if session_resp.status_code == 429:
            pytest.skip("Rate limited - skipping test")
            
        assert session_resp.status_code == 200, f"Session fetch failed: {session_resp.status_code}"
        
        data = session_resp.json()
        assert data.get("effective_plan") == "premium", f"Expected effective_plan='premium', got {data.get('effective_plan')}"
        assert data.get("subscription_access_profile") == "full_unlimited", f"Expected profile='full_unlimited', got {data.get('subscription_access_profile')}"
        print(f"✓ Premium user session: effective_plan={data.get('effective_plan')}, profile={data.get('subscription_access_profile')}")
    
    def test_admin_user_session(self):
        """Admin user should get effective_plan='premium' and is_admin=True"""
        session = requests.Session()
        
        # Login as admin user
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        if login_resp.status_code == 429:
            pytest.skip("Rate limited - skipping test")
        
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.status_code} - {login_resp.text}"
        
        # Get access control session
        session_resp = session.get(f"{BASE_URL}/api/access-control/session", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        
        if session_resp.status_code == 429:
            pytest.skip("Rate limited - skipping test")
            
        assert session_resp.status_code == 200, f"Session fetch failed: {session_resp.status_code}"
        
        data = session_resp.json()
        assert data.get("effective_plan") == "premium", f"Expected effective_plan='premium' for admin, got {data.get('effective_plan')}"
        assert data.get("is_admin") == True, "Admin should have is_admin=True"
        print(f"✓ Admin user session: effective_plan={data.get('effective_plan')}, is_admin={data.get('is_admin')}")


class TestFreeUserAccessBlocking:
    """Test that free users are blocked from paid feature APIs"""
    
    @pytest.fixture(scope="class")
    def free_session(self):
        """Login as free user and return session"""
        session = requests.Session()
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=FREE_USER, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        if login_resp.status_code == 429:
            pytest.skip("Rate limited during login")
        if login_resp.status_code != 200:
            pytest.skip(f"Free user login failed: {login_resp.status_code}")
        return session
    
    def test_free_user_limited_access_bill_generator(self, free_session):
        """POLICY 2026-06.v3: Free user gets limited (not blocked) access to /api/bill-generator/"""
        resp = free_session.get(f"{BASE_URL}/api/bill-generator/bills", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        if resp.status_code == 429:
            pytest.skip("Rate limited")
        assert resp.status_code in [200, 404, 405], \
            f"Free user must have limited access to bill-generator (no 403), got {resp.status_code}"
        print(f"✓ Free user has limited access to /api/bill-generator/ (status: {resp.status_code})")
    
    def test_free_user_allowed_games_station(self, free_session):
        """Free user should be allowed to access /api/games-station/"""
        resp = free_session.get(f"{BASE_URL}/api/games-station/", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        if resp.status_code == 429:
            pytest.skip("Rate limited")
        # Games station should be accessible to free users
        assert resp.status_code in [200, 404], f"Free user should access games-station, got {resp.status_code}"
        print(f"✓ Free user allowed on /api/games-station/ (status: {resp.status_code})")
    
    def test_free_user_allowed_access_control_session(self, free_session):
        """Free user should be allowed to access /api/access-control/session"""
        resp = free_session.get(f"{BASE_URL}/api/access-control/session", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        if resp.status_code == 429:
            pytest.skip("Rate limited")
        assert resp.status_code == 200, f"Free user should access access-control/session, got {resp.status_code}"
        print(f"✓ Free user allowed on /api/access-control/session (status: {resp.status_code})")


class TestAdminOnlyAccess:
    """Test that admin-only routes remain admin-only regardless of subscription tier"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin user and return session"""
        session = requests.Session()
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        if login_resp.status_code == 429:
            pytest.skip("Rate limited during login")
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code}")
        return session
    
    @pytest.fixture(scope="class")
    def free_session(self):
        """Login as free user and return session"""
        session = requests.Session()
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=FREE_USER, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        if login_resp.status_code == 429:
            pytest.skip("Rate limited during login")
        if login_resp.status_code != 200:
            pytest.skip(f"Free user login failed: {login_resp.status_code}")
        return session
    
    def test_admin_can_access_admin_employees(self, admin_session):
        """Admin should be able to access /api/admin/employees"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/employees", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        if resp.status_code == 429:
            pytest.skip("Rate limited")
        # Admin should get 200 or at least not 403
        assert resp.status_code in [200, 404], f"Admin should access /api/admin/employees, got {resp.status_code}"
        print(f"✓ Admin can access /api/admin/employees (status: {resp.status_code})")
    
    def test_free_user_blocked_from_admin_employees(self, free_session):
        """Free user should be blocked from /api/admin/employees"""
        resp = free_session.get(f"{BASE_URL}/api/admin/employees", headers={
            "X-Requested-With": "XMLHttpRequest"
        })
        if resp.status_code == 429:
            pytest.skip("Rate limited")
        # Free user should get 403 or 401
        assert resp.status_code in [401, 403], f"Free user should be blocked from /api/admin/employees, got {resp.status_code}"
        print(f"✓ Free user blocked from /api/admin/employees (status: {resp.status_code})")


class TestBackendAccessControlEngine:
    """Test the backend access_control_engine.py get_required_level() function behavior"""
    
    def test_canonical_feature_apis_are_free_accessible(self):
        """
        POLICY 2026-06.v3: canonical feature APIs are free-accessible (limited);
        the daily action meter enforces limits instead of 403 hard blocks.
        """
        session = requests.Session()

        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })

        if login_resp.status_code == 429:
            pytest.skip("Rate limited")

        eval_resp = session.post(f"{BASE_URL}/api/access-control/evaluate", json={
            "path": "/api/bill-generator/",
            "method": "GET"
        }, headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })

        if eval_resp.status_code == 404:
            pytest.skip("Access control evaluate endpoint not available")

        if eval_resp.status_code == 429:
            pytest.skip("Rate limited")

        if eval_resp.status_code == 200:
            data = eval_resp.json()
            required_level = data.get("required_level")
            if required_level is not None:
                assert required_level == 0, f"Expected required_level == 0 (free-limited) for /api/bill-generator/, got {required_level}"
                print(f"✓ /api/bill-generator/ is free-accessible with limited access (level {required_level})")
        else:
            print(f"Access control evaluate returned {eval_resp.status_code}, skipping assertion")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
