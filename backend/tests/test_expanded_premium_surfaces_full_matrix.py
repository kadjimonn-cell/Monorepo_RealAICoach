"""Full matrix test for expanded free-limited route premium surfaces.

Tests:
1. Free users blocked from expanded premium surfaces
2. Basic users allowed on expanded premium surfaces
3. Premium users allowed on expanded premium surfaces
4. Existing premium-only routes (/workspace) remain premium-only
5. Admin-only routes remain admin-only
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
FREE_USER = ("p1.free.1779113329@example.com", "P1Free#2026!Aa")
BASIC_USER = ("f22.basic.20260613@example.com", "F22Basic#2026Aa")
PREMIUM_USER = ("f22.premium.20260613@example.com", "F22Premium#2026Aa")
ADMIN_USER = ("admin@realaicoach.app", "NewAdminPass2026!")

# Expanded premium surfaces (free blocked, basic/premium allowed)
EXPANDED_PREMIUM_SURFACES = [
    "/features/content-studio",
    "/features/decision-coach",
    "/features/ai-automations",
    "/features/analytics-reports",
    "/features/ai-enterprise",
    "/mini-apps/ai-accounting",
    "/mini-apps/creator-exchange",
    "/subscription/mobile-money",
]

# Existing premium-only routes (free/basic blocked, premium allowed)
PREMIUM_ONLY_ROUTES = [
    "/workspace",
    "/content-studio",
]

# Admin-only routes
ADMIN_ONLY_ROUTES = [
    "/job-platform-admin",
    "/admin-console",
    "/executive-dashboard",
    "/team-management",
]


def _login(email: str, password: str) -> requests.Session:
    """Login and return authenticated session."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    login_resp = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30
    )
    assert login_resp.status_code == 200, f"Login failed for {email}: {login_resp.status_code} {login_resp.text}"
    return s


def _check_route(session: requests.Session, path: str) -> dict:
    """Check route access via backend policy engine."""
    resp = session.post(
        f"{BASE_URL}/api/access-control/check-route",
        json={"path": path, "method": "GET"},
        timeout=30
    )
    assert resp.status_code == 200, f"check-route failed for {path}: {resp.status_code} {resp.text}"
    return resp.json()


class TestExpandedPremiumSurfacesFreeUser:
    """Free user should be blocked from all expanded premium surfaces."""
    
    @pytest.fixture(scope="class")
    def free_session(self):
        return _login(*FREE_USER)
    
    @pytest.mark.parametrize("route", EXPANDED_PREMIUM_SURFACES)
    def test_free_blocked_from_expanded_surface(self, free_session, route):
        result = _check_route(free_session, route)
        assert result.get("allowed") is False, f"Free user should be blocked from {route}: {result}"
        # Reason should indicate subscription/plan requirement
        assert result.get("reason") in {
            "subscription_required", 
            "premium_required", 
            "basic_required",
            "free_limited_access"
        }, f"Unexpected block reason for {route}: {result}"


class TestExpandedPremiumSurfacesBasicUser:
    """Basic user should be allowed on all expanded premium surfaces."""
    
    @pytest.fixture(scope="class")
    def basic_session(self):
        return _login(*BASIC_USER)
    
    @pytest.mark.parametrize("route", EXPANDED_PREMIUM_SURFACES)
    def test_basic_allowed_on_expanded_surface(self, basic_session, route):
        result = _check_route(basic_session, route)
        assert result.get("allowed") is True, f"Basic user should be allowed on {route}: {result}"


class TestExpandedPremiumSurfacesPremiumUser:
    """Premium user should be allowed on all expanded premium surfaces."""
    
    @pytest.fixture(scope="class")
    def premium_session(self):
        return _login(*PREMIUM_USER)
    
    @pytest.mark.parametrize("route", EXPANDED_PREMIUM_SURFACES)
    def test_premium_allowed_on_expanded_surface(self, premium_session, route):
        result = _check_route(premium_session, route)
        assert result.get("allowed") is True, f"Premium user should be allowed on {route}: {result}"


class TestExistingPremiumOnlyRoutes:
    """Existing premium-only routes should remain premium-only (no regression)."""
    
    @pytest.fixture(scope="class")
    def free_session(self):
        return _login(*FREE_USER)
    
    @pytest.fixture(scope="class")
    def basic_session(self):
        return _login(*BASIC_USER)
    
    @pytest.fixture(scope="class")
    def premium_session(self):
        return _login(*PREMIUM_USER)
    
    @pytest.mark.parametrize("route", PREMIUM_ONLY_ROUTES)
    def test_free_blocked_from_premium_only(self, free_session, route):
        result = _check_route(free_session, route)
        assert result.get("allowed") is False, f"Free user should be blocked from premium-only {route}: {result}"
    
    @pytest.mark.parametrize("route", PREMIUM_ONLY_ROUTES)
    def test_basic_blocked_from_premium_only(self, basic_session, route):
        result = _check_route(basic_session, route)
        # Basic should also be blocked from premium-only routes
        assert result.get("allowed") is False, f"Basic user should be blocked from premium-only {route}: {result}"
    
    @pytest.mark.parametrize("route", PREMIUM_ONLY_ROUTES)
    def test_premium_allowed_on_premium_only(self, premium_session, route):
        result = _check_route(premium_session, route)
        assert result.get("allowed") is True, f"Premium user should be allowed on premium-only {route}: {result}"


class TestAdminOnlyRoutes:
    """Admin-only routes should remain admin-only (no leakage to non-admin)."""
    
    @pytest.fixture(scope="class")
    def free_session(self):
        return _login(*FREE_USER)
    
    @pytest.fixture(scope="class")
    def basic_session(self):
        return _login(*BASIC_USER)
    
    @pytest.fixture(scope="class")
    def premium_session(self):
        return _login(*PREMIUM_USER)
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        return _login(*ADMIN_USER)
    
    @pytest.mark.parametrize("route", ADMIN_ONLY_ROUTES)
    def test_free_blocked_from_admin_only(self, free_session, route):
        result = _check_route(free_session, route)
        assert result.get("allowed") is False, f"Free user should be blocked from admin-only {route}: {result}"
        assert result.get("reason") == "admin_required", f"Reason should be admin_required for {route}: {result}"
    
    @pytest.mark.parametrize("route", ADMIN_ONLY_ROUTES)
    def test_basic_blocked_from_admin_only(self, basic_session, route):
        result = _check_route(basic_session, route)
        assert result.get("allowed") is False, f"Basic user should be blocked from admin-only {route}: {result}"
        assert result.get("reason") == "admin_required", f"Reason should be admin_required for {route}: {result}"
    
    @pytest.mark.parametrize("route", ADMIN_ONLY_ROUTES)
    def test_premium_blocked_from_admin_only(self, premium_session, route):
        result = _check_route(premium_session, route)
        assert result.get("allowed") is False, f"Premium user should be blocked from admin-only {route}: {result}"
        assert result.get("reason") == "admin_required", f"Reason should be admin_required for {route}: {result}"
    
    @pytest.mark.parametrize("route", ADMIN_ONLY_ROUTES)
    def test_admin_allowed_on_admin_only(self, admin_session, route):
        result = _check_route(admin_session, route)
        assert result.get("allowed") is True, f"Admin user should be allowed on admin-only {route}: {result}"


class TestJobPlatformEmployerRoute:
    """Specific test for /job-platform-employer redirect behavior."""
    
    @pytest.fixture(scope="class")
    def free_session(self):
        return _login(*FREE_USER)
    
    @pytest.fixture(scope="class")
    def basic_session(self):
        return _login(*BASIC_USER)
    
    def test_free_blocked_from_job_platform_employer(self, free_session):
        result = _check_route(free_session, "/job-platform-employer")
        assert result.get("allowed") is False, f"Free user should be blocked from /job-platform-employer: {result}"
        # Should redirect to subscription plans
        assert result.get("redirect_to") == "/subscription/plans" or result.get("reason") in {
            "subscription_required", "basic_required", "free_limited_access"
        }, f"Free user should be redirected to /subscription/plans: {result}"
    
    def test_basic_allowed_on_job_platform_employer(self, basic_session):
        result = _check_route(basic_session, "/job-platform-employer")
        assert result.get("allowed") is True, f"Basic user should be allowed on /job-platform-employer: {result}"
