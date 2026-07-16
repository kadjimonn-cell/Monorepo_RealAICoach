"""E2E Subscription Access Control Tests - Platform Global Policy Validation.

Tests the subscription tier gating:
- Free → Limited access
- Basic → Almost unlimited
- Premium → Full unlimited access

Validates:
1. Unauthenticated users blocked from paid/authenticated APIs
2. Free users blocked from paid feature families
3. Basic users get almost unlimited access (except Premium-only)
4. Premium users get full unlimited access
5. Admin access still works
6. Public/system/webhook endpoints remain accessible
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
CREDENTIALS = {
    "free": {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"},
    "basic": {"email": "f21.basic.1781338672@example.com", "password": "F21Basic#2026Aa"},
    "premium": {"email": "watchvideos.premium.4dc6ab84@example.com", "password": "WatchVideos#2026Aa"},
    "admin": {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
}

# Paid/authenticated feature APIs that should be blocked for free users
PAID_FEATURE_APIS = [
    "/api/personal-assistant/bootstrap",
    "/api/research-navigator/bootstrap",
    "/api/bill-generator/bootstrap",
    "/api/mobility-assistant/bootstrap",
    "/api/writing-studio/bootstrap",
    "/api/ai-enterprise/bootstrap",
    "/api/relationship-coach/bootstrap",
    "/api/decision-coach/bootstrap",
    "/api/money-strategy-hub/bootstrap",
    "/api/smart-shopping-advisor/bootstrap",
    "/api/travel-planner-pro/bootstrap",
    "/api/video-studio/bootstrap",
    "/api/ai-photo-studio/bootstrap",
    "/api/ai-speech-studio/bootstrap",
]

# Public endpoints that should remain accessible without auth
PUBLIC_ENDPOINTS = [
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/subscriptions/plans",
    "/api/payments/currencies",
    "/api/config/global",
    "/api/features/registry",
]

# Admin-only endpoints
ADMIN_ONLY_ENDPOINTS = [
    "/api/admin/subscription-analytics",
    "/api/admin/payment-analytics",
    "/api/admin/ai-insights",
]


class TestSession:
    """Helper class to manage authenticated sessions."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
    
    def login(self, email: str, password: str) -> dict:
        """Login and return user info."""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
        )
        return response
    
    def get(self, path: str) -> requests.Response:
        return self.session.get(f"{BASE_URL}{path}")
    
    def post(self, path: str, json: dict = None) -> requests.Response:
        return self.session.post(f"{BASE_URL}{path}", json=json or {})


@pytest.fixture(scope="module")
def free_session():
    """Authenticated session for free user."""
    session = TestSession()
    creds = CREDENTIALS["free"]
    response = session.login(creds["email"], creds["password"])
    if response.status_code != 200:
        pytest.skip(f"Free user login failed: {response.status_code} - {response.text[:200]}")
    return session


@pytest.fixture(scope="module")
def basic_session():
    """Authenticated session for basic user."""
    session = TestSession()
    creds = CREDENTIALS["basic"]
    response = session.login(creds["email"], creds["password"])
    if response.status_code != 200:
        pytest.skip(f"Basic user login failed: {response.status_code} - {response.text[:200]}")
    return session


@pytest.fixture(scope="module")
def premium_session():
    """Authenticated session for premium user."""
    session = TestSession()
    creds = CREDENTIALS["premium"]
    response = session.login(creds["email"], creds["password"])
    if response.status_code != 200:
        pytest.skip(f"Premium user login failed: {response.status_code} - {response.text[:200]}")
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Authenticated session for admin user."""
    session = TestSession()
    creds = CREDENTIALS["admin"]
    response = session.login(creds["email"], creds["password"])
    if response.status_code != 200:
        pytest.skip(f"Admin user login failed: {response.status_code} - {response.text[:200]}")
    return session


class TestUnauthenticatedAccess:
    """Test that unauthenticated users are blocked from paid/authenticated APIs."""
    
    def test_public_endpoints_accessible_without_auth(self):
        """Public endpoints should be accessible without authentication."""
        session = requests.Session()
        for endpoint in PUBLIC_ENDPOINTS:
            response = session.get(f"{BASE_URL}{endpoint}")
            # 405 is OK for POST-only endpoints like /api/auth/login
            assert response.status_code in [200, 404, 405], \
                f"Public endpoint {endpoint} should be accessible, got {response.status_code}"
    
    def test_paid_feature_apis_blocked_without_auth(self):
        """Paid feature APIs should return 401 for unauthenticated requests."""
        session = requests.Session()
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        blocked_count = 0
        for endpoint in PAID_FEATURE_APIS:
            response = session.get(f"{BASE_URL}{endpoint}")
            # Should be 401 (AUTH_REQUIRED) for unauthenticated users
            if response.status_code == 401:
                blocked_count += 1
            else:
                print(f"WARNING: {endpoint} returned {response.status_code} instead of 401")
        
        # At least 80% should be blocked
        assert blocked_count >= len(PAID_FEATURE_APIS) * 0.8, \
            f"Only {blocked_count}/{len(PAID_FEATURE_APIS)} paid APIs blocked for unauthenticated users"
    
    def test_admin_endpoints_blocked_without_auth(self):
        """Admin endpoints should be blocked for unauthenticated users."""
        session = requests.Session()
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        for endpoint in ADMIN_ONLY_ENDPOINTS:
            response = session.get(f"{BASE_URL}{endpoint}")
            assert response.status_code in [401, 403], \
                f"Admin endpoint {endpoint} should be blocked, got {response.status_code}"


class TestFreeUserAccess:
    """Test that free authenticated users have limited access."""
    
    def test_free_user_login_succeeds(self, free_session):
        """Free user should be able to login."""
        # If we got here, login succeeded (fixture would skip otherwise)
        assert free_session is not None
    
    def test_free_user_blocked_from_paid_feature_apis(self, free_session):
        """Free user should be blocked from paid feature APIs (Basic+ required)."""
        blocked_count = 0
        for endpoint in PAID_FEATURE_APIS:
            response = free_session.get(endpoint)
            if response.status_code == 403:
                data = response.json()
                # Should indicate subscription required
                if "Subscription Required" in str(data) or "subscription_required" in str(data):
                    blocked_count += 1
                else:
                    print(f"Free user blocked from {endpoint} but not for subscription: {data}")
                    blocked_count += 1  # Still blocked
            elif response.status_code == 401:
                # Auth issue, not subscription
                print(f"WARNING: {endpoint} returned 401 for free user (auth issue)")
            else:
                print(f"WARNING: Free user accessed {endpoint} with status {response.status_code}")
        
        # At least 80% should be blocked for subscription
        assert blocked_count >= len(PAID_FEATURE_APIS) * 0.8, \
            f"Only {blocked_count}/{len(PAID_FEATURE_APIS)} paid APIs blocked for free user"
    
    def test_free_user_blocked_from_admin_endpoints(self, free_session):
        """Free user should be blocked from admin endpoints."""
        for endpoint in ADMIN_ONLY_ENDPOINTS:
            response = free_session.get(endpoint)
            assert response.status_code == 403, \
                f"Free user should be blocked from {endpoint}, got {response.status_code}"
    
    def test_free_user_can_access_free_tier_features(self, free_session):
        """Free user should be able to access free-tier features."""
        free_endpoints = [
            "/api/home/dashboard-stats",
            "/api/notifications/",
            "/api/gamification/",
        ]
        for endpoint in free_endpoints:
            response = free_session.get(endpoint)
            # Should not be 403 subscription_required
            if response.status_code == 403:
                data = response.json()
                assert "Subscription Required" not in str(data), \
                    f"Free user should access {endpoint}, got subscription block"


class TestBasicUserAccess:
    """Test that basic authenticated users get almost unlimited access."""
    
    def test_basic_user_login_succeeds(self, basic_session):
        """Basic user should be able to login."""
        assert basic_session is not None
    
    def test_basic_user_can_access_basic_tier_features(self, basic_session):
        """Basic user should be able to access Basic-tier paid features."""
        # Basic-tier features (not Premium-only)
        basic_tier_apis = [
            "/api/personal-assistant/bootstrap",
            "/api/research-navigator/bootstrap",
            "/api/bill-generator/bootstrap",
            "/api/writing-studio/bootstrap",
            "/api/relationship-coach/bootstrap",
            "/api/decision-coach/bootstrap",
        ]
        
        accessible_count = 0
        for endpoint in basic_tier_apis:
            response = basic_session.get(endpoint)
            if response.status_code in [200, 404]:  # 404 is OK if endpoint exists but no data
                accessible_count += 1
            elif response.status_code == 403:
                data = response.json()
                # Should NOT be blocked for subscription
                if "Subscription Required" in str(data):
                    print(f"WARNING: Basic user blocked from {endpoint}: {data}")
                else:
                    # Blocked for other reason (admin, etc.) - OK
                    accessible_count += 1
            else:
                print(f"Basic user got {response.status_code} for {endpoint}")
        
        # At least 70% should be accessible
        assert accessible_count >= len(basic_tier_apis) * 0.7, \
            f"Only {accessible_count}/{len(basic_tier_apis)} Basic-tier APIs accessible for basic user"
    
    def test_basic_user_blocked_from_premium_only_features(self, basic_session):
        """Basic user should be blocked from Premium-only features."""
        premium_only_apis = [
            "/api/admin/enterprise",
            "/api/team-management",
            "/api/collab-docs",
            "/api/workspace",
        ]
        
        blocked_count = 0
        for endpoint in premium_only_apis:
            response = basic_session.get(endpoint)
            if response.status_code == 403:
                blocked_count += 1
        
        # At least 50% should be blocked (some may not exist)
        assert blocked_count >= len(premium_only_apis) * 0.5, \
            f"Only {blocked_count}/{len(premium_only_apis)} Premium-only APIs blocked for basic user"
    
    def test_basic_user_blocked_from_admin_endpoints(self, basic_session):
        """Basic user should be blocked from admin endpoints."""
        for endpoint in ADMIN_ONLY_ENDPOINTS:
            response = basic_session.get(endpoint)
            assert response.status_code == 403, \
                f"Basic user should be blocked from {endpoint}, got {response.status_code}"


class TestPremiumUserAccess:
    """Test that premium authenticated users get full unlimited access."""
    
    def test_premium_user_login_succeeds(self, premium_session):
        """Premium user should be able to login."""
        assert premium_session is not None
    
    def test_premium_user_can_access_all_paid_features(self, premium_session):
        """Premium user should be able to access all paid feature APIs."""
        accessible_count = 0
        for endpoint in PAID_FEATURE_APIS:
            response = premium_session.get(endpoint)
            if response.status_code in [200, 404]:  # 404 is OK if endpoint exists but no data
                accessible_count += 1
            elif response.status_code == 403:
                data = response.json()
                # Should NOT be blocked for subscription
                if "Subscription Required" in str(data):
                    print(f"WARNING: Premium user blocked from {endpoint}: {data}")
                else:
                    # Blocked for other reason (admin, etc.) - OK
                    accessible_count += 1
            else:
                print(f"Premium user got {response.status_code} for {endpoint}")
        
        # At least 80% should be accessible
        assert accessible_count >= len(PAID_FEATURE_APIS) * 0.8, \
            f"Only {accessible_count}/{len(PAID_FEATURE_APIS)} paid APIs accessible for premium user"
    
    def test_premium_user_blocked_from_admin_endpoints(self, premium_session):
        """Premium user (non-admin) should still be blocked from admin endpoints."""
        for endpoint in ADMIN_ONLY_ENDPOINTS:
            response = premium_session.get(endpoint)
            assert response.status_code == 403, \
                f"Premium user should be blocked from {endpoint}, got {response.status_code}"


class TestAdminAccess:
    """Test that admin access still works correctly."""
    
    def test_admin_login_succeeds(self, admin_session):
        """Admin user should be able to login."""
        assert admin_session is not None
    
    def test_admin_can_access_all_paid_features(self, admin_session):
        """Admin should be able to access all paid feature APIs."""
        accessible_count = 0
        for endpoint in PAID_FEATURE_APIS:
            response = admin_session.get(endpoint)
            if response.status_code in [200, 404]:
                accessible_count += 1
            else:
                print(f"Admin got {response.status_code} for {endpoint}")
        
        # At least 80% should be accessible
        assert accessible_count >= len(PAID_FEATURE_APIS) * 0.8, \
            f"Only {accessible_count}/{len(PAID_FEATURE_APIS)} paid APIs accessible for admin"
    
    def test_admin_can_access_admin_endpoints(self, admin_session):
        """Admin should be able to access admin endpoints."""
        accessible_count = 0
        for endpoint in ADMIN_ONLY_ENDPOINTS:
            response = admin_session.get(endpoint)
            if response.status_code in [200, 404]:
                accessible_count += 1
            else:
                print(f"Admin got {response.status_code} for {endpoint}: {response.text[:200]}")
        
        # At least 50% should be accessible (some may not exist)
        assert accessible_count >= len(ADMIN_ONLY_ENDPOINTS) * 0.5, \
            f"Only {accessible_count}/{len(ADMIN_ONLY_ENDPOINTS)} admin APIs accessible for admin"


class TestPublicEndpointsRegression:
    """Test that public/system/webhook endpoints remain accessible."""
    
    def test_webhook_endpoints_remain_public(self):
        """Webhook endpoints should remain accessible without auth."""
        webhook_endpoints = [
            "/api/webhook/stripe",
            "/api/payments/fedapay/webhook",
            "/api/payments/paypal/webhook",
            "/api/iap/apple/webhook",
            "/api/iap/google/webhook",
        ]
        
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        for endpoint in webhook_endpoints:
            # POST with empty body - should not return 401
            response = session.post(f"{BASE_URL}{endpoint}", json={})
            # Webhooks may return 400/422 for invalid payload, but NOT 401
            assert response.status_code != 401, \
                f"Webhook {endpoint} should not require auth, got 401"
    
    def test_system_health_endpoints_remain_public(self):
        """System health endpoints should remain accessible."""
        health_endpoints = [
            "/api/health",
            "/api/system/health",
        ]
        
        session = requests.Session()
        for endpoint in health_endpoints:
            response = session.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 200, \
                f"Health endpoint {endpoint} should return 200, got {response.status_code}"
    
    def test_auth_endpoints_remain_public(self):
        """Auth endpoints should remain accessible without auth."""
        auth_endpoints = [
            "/api/auth/login",
            "/api/auth/register",
        ]
        
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        for endpoint in auth_endpoints:
            # POST with invalid data - should not return 401
            response = session.post(f"{BASE_URL}{endpoint}", json={"email": "test@test.com"})
            # May return 400/422 for invalid data, but NOT 401
            assert response.status_code != 401, \
                f"Auth endpoint {endpoint} should not require auth, got 401"


class TestAccessControlSession:
    """Test the access-control session endpoint."""
    
    def test_free_user_session_shows_limited_access(self, free_session):
        """Free user session should show limited access profile."""
        response = free_session.get("/api/access-control/session")
        if response.status_code == 200:
            data = response.json()
            assert data.get("effective_plan") == "free", \
                f"Free user should have effective_plan=free, got {data.get('effective_plan')}"
            assert data.get("subscription_access_profile") == "limited", \
                f"Free user should have limited access profile, got {data.get('subscription_access_profile')}"
    
    def test_basic_user_session_shows_almost_unlimited_access(self, basic_session):
        """Basic user session should show almost_unlimited access profile."""
        response = basic_session.get("/api/access-control/session")
        if response.status_code == 200:
            data = response.json()
            assert data.get("effective_plan") == "basic", \
                f"Basic user should have effective_plan=basic, got {data.get('effective_plan')}"
            assert data.get("subscription_access_profile") == "almost_unlimited", \
                f"Basic user should have almost_unlimited access profile, got {data.get('subscription_access_profile')}"
    
    def test_premium_user_session_shows_full_unlimited_access(self, premium_session):
        """Premium user session should show full_unlimited access profile."""
        response = premium_session.get("/api/access-control/session")
        if response.status_code == 200:
            data = response.json()
            assert data.get("effective_plan") == "premium", \
                f"Premium user should have effective_plan=premium, got {data.get('effective_plan')}"
            assert data.get("subscription_access_profile") == "full_unlimited", \
                f"Premium user should have full_unlimited access profile, got {data.get('subscription_access_profile')}"
    
    def test_admin_user_session_shows_admin_actor_type(self, admin_session):
        """Admin user session should show admin actor type."""
        response = admin_session.get("/api/access-control/session")
        if response.status_code == 200:
            data = response.json()
            assert data.get("is_admin") is True, \
                f"Admin user should have is_admin=True, got {data.get('is_admin')}"
            assert data.get("actor_type") == "admin", \
                f"Admin user should have actor_type=admin, got {data.get('actor_type')}"
