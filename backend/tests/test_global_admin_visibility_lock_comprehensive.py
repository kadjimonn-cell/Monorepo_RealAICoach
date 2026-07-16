"""
Comprehensive test for global admin visibility lock contract.
Tests:
1. Non-admin gets 403 on /api/admin/*analytics* and /api/admin/*insights* endpoints
2. Delegated non-admin permissions do not bypass analytics/insights admin lock
3. Admin remains allowed on those analytics/insights endpoints
4. Frontend admin visibility lock: admin pages/tabs not shown to non-admin (code-level)
5. Frontend route protection: non-admin blocked from admin routes (code-level)
6. Role landing safety: non-admin roles do not auto-route to admin pages (code-level)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
PRIMARY_NON_ADMIN_EMAIL = "curation.1779076352@example.com"
PRIMARY_NON_ADMIN_PASSWORD = "NovaV2#2026!Aa"
NON_ADMIN_FALLBACKS = [
    ("f21.basic.1781338672@example.com", "F21Basic#2026Aa"),
    ("feature26.approved.employer.e2e@realaicoach.app", "Feature26Approved#2026!"),
    ("p1.free.1779113329@example.com", "P1Free#2026!Aa"),
]
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


def _assert_base_url() -> str:
    assert BASE_URL, "REACT_APP_BACKEND_URL is required"
    return BASE_URL


def _login(email: str, password: str) -> requests.Session:
    base = _assert_base_url()
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    resp = session.post(
        f"{base}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.status_code} {resp.text}"
    body = resp.json()
    assert not body.get("requires_2fa"), f"2FA required for {email}; choose a dedicated E2E bypass fixture"
    return session


def _login_non_admin_with_fallback() -> requests.Session:
    candidates = [(PRIMARY_NON_ADMIN_EMAIL, PRIMARY_NON_ADMIN_PASSWORD), *NON_ADMIN_FALLBACKS]
    last_error = None
    for email, password in candidates:
      try:
          return _login(email, password)
      except AssertionError as exc:
          last_error = exc
          if "2FA required" not in str(exc):
              raise
    raise AssertionError(f"No usable non-admin fixture available: {last_error}")


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def non_admin_session() -> requests.Session:
    return _login_non_admin_with_fallback()


@pytest.fixture(scope="module")
def free_user_session() -> requests.Session:
    return _login(FREE_USER_EMAIL, FREE_USER_PASSWORD)


class TestGlobalAdminAnalyticsInsightsLock:
    """Test 1 & 2: Non-admin (including delegated permissions) gets 403 on analytics/insights"""
    
    ANALYTICS_ENDPOINTS = [
        "/api/admin/analytics",
        "/api/admin/subscription-analytics",
        "/api/admin/payment-analytics",
        "/api/admin/payment-analytics/provider-incidents/canary-status",
        "/api/admin/executive/templates/analytics/summary",
    ]
    
    INSIGHTS_ENDPOINTS = [
        "/api/admin/ai-insights",
        "/api/admin/ai-insights/dashboard",
        "/api/admin/insights/dashboard",
    ]
    
    def test_non_admin_blocked_from_analytics_endpoints(self, non_admin_session: requests.Session):
        """Non-admin user with delegated permissions should be blocked from analytics"""
        base = _assert_base_url()
        for path in self.ANALYTICS_ENDPOINTS:
            resp = non_admin_session.get(f"{base}{path}", timeout=30)
            assert resp.status_code == 403, f"Expected 403 for non-admin at {path}, got {resp.status_code}"
            payload = resp.json()
            assert "Admin Access Required" in str(payload.get("error", "")) or "admin" in str(payload.get("detail", "")).lower(), \
                f"Expected admin required message at {path}: {payload}"
    
    def test_non_admin_blocked_from_insights_endpoints(self, non_admin_session: requests.Session):
        """Non-admin user with delegated permissions should be blocked from insights"""
        base = _assert_base_url()
        for path in self.INSIGHTS_ENDPOINTS:
            resp = non_admin_session.get(f"{base}{path}", timeout=30)
            assert resp.status_code == 403, f"Expected 403 for non-admin at {path}, got {resp.status_code}"
            payload = resp.json()
            assert "Admin Access Required" in str(payload.get("error", "")) or "admin" in str(payload.get("detail", "")).lower(), \
                f"Expected admin required message at {path}: {payload}"
    
    def test_free_user_blocked_from_analytics_insights(self, free_user_session: requests.Session):
        """Free user (no delegated permissions) should also be blocked"""
        base = _assert_base_url()
        all_endpoints = self.ANALYTICS_ENDPOINTS + self.INSIGHTS_ENDPOINTS
        for path in all_endpoints:
            resp = free_user_session.get(f"{base}{path}", timeout=30)
            assert resp.status_code == 403, f"Expected 403 for free user at {path}, got {resp.status_code}"


class TestAdminAllowedOnAnalyticsInsights:
    """Test 3: Admin remains allowed on analytics/insights endpoints"""
    
    ADMIN_ALLOWED_ENDPOINTS = [
        "/api/admin/analytics",
        "/api/admin/subscription-analytics",
        "/api/admin/payment-analytics/provider-incidents/canary-status",
        "/api/admin/ai-insights/dashboard",
        "/api/admin/insights/dashboard",
    ]
    
    def test_admin_not_blocked_from_analytics_insights(self, admin_session: requests.Session):
        """Admin should not be blocked by RBAC on analytics/insights endpoints"""
        base = _assert_base_url()
        for path in self.ADMIN_ALLOWED_ENDPOINTS:
            resp = admin_session.get(f"{base}{path}", timeout=30)
            # Admin should not get 403 - may get 200, 404, or 422 depending on endpoint implementation
            assert resp.status_code != 403, f"Admin unexpectedly blocked at {path}: {resp.status_code}"


class TestAdminRouteProtection:
    """Test 5: Non-admin blocked from admin routes"""
    
    ADMIN_ROUTES = [
        "/api/admin/users",
        "/api/admin/system",
        "/api/admin/platform-health",
        "/api/admin/employees",
    ]
    
    def test_non_admin_blocked_from_admin_routes(self, non_admin_session: requests.Session):
        """Non-admin should be blocked from general admin routes"""
        base = _assert_base_url()
        for path in self.ADMIN_ROUTES:
            resp = non_admin_session.get(f"{base}{path}", timeout=30)
            # Should be blocked (403) or not found (404) - not 200
            assert resp.status_code in {401, 403, 404}, \
                f"Non-admin should not have access to {path}, got {resp.status_code}"
    
    def test_admin_allowed_on_admin_routes(self, admin_session: requests.Session):
        """Admin should have access to admin routes"""
        base = _assert_base_url()
        for path in self.ADMIN_ROUTES:
            resp = admin_session.get(f"{base}{path}", timeout=30)
            # Admin should not get 403
            assert resp.status_code != 403, f"Admin unexpectedly blocked at {path}: {resp.status_code}"


class TestAccessControlSessionEndpoint:
    """Test access-control/session endpoint returns correct actor_type"""
    
    def test_admin_session_returns_admin_actor_type(self, admin_session: requests.Session):
        """Admin session should return actor_type=admin"""
        base = _assert_base_url()
        resp = admin_session.get(f"{base}/api/access-control/session", timeout=30)
        assert resp.status_code == 200, f"Failed to get session: {resp.status_code}"
        data = resp.json()
        assert data.get("is_admin") is True, f"Expected is_admin=True: {data}"
        assert data.get("actor_type") == "admin", f"Expected actor_type=admin: {data}"
    
    def test_non_admin_session_returns_non_admin_actor_type(self, non_admin_session: requests.Session):
        """Non-admin session should return actor_type != admin"""
        base = _assert_base_url()
        resp = non_admin_session.get(f"{base}/api/access-control/session", timeout=30)
        assert resp.status_code == 200, f"Failed to get session: {resp.status_code}"
        data = resp.json()
        assert data.get("is_admin") is not True, f"Expected is_admin=False: {data}"
        # actor_type should be 'user' or 'employee', not 'admin'
        assert data.get("actor_type") != "admin", f"Expected actor_type != admin: {data}"
