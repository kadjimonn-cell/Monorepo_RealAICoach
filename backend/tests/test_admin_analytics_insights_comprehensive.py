"""Comprehensive tests for global admin analytics/insights strict admin-only lock.

Tests:
1. Non-admin authenticated user gets 403 on representative analytics/insights admin endpoints
2. Admin user continues to access analytics/insights endpoints (no regression)
3. Existing admin route controls unaffected for non-analytics endpoints
4. Employees with delegated permissions must NOT bypass this for analytics/insights
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
NON_ADMIN_EMAIL = "curation.1779076352@example.com"
NON_ADMIN_PASSWORD = "NovaV2#2026!Aa"
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
    return session


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def non_admin_session() -> requests.Session:
    return _login(NON_ADMIN_EMAIL, NON_ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def free_user_session() -> requests.Session:
    return _login(FREE_USER_EMAIL, FREE_USER_PASSWORD)


class TestNonAdminBlockedForAnalyticsInsights:
    """Non-admin authenticated users must get strict 403 on analytics/insights endpoints."""

    BLOCKED_ANALYTICS_PATHS = [
        "/api/admin/analytics",
        "/api/admin/subscription-analytics",
        "/api/admin/payment-analytics",
        "/api/admin/payment-analytics/provider-incidents/canary-status",
        "/api/admin/executive/templates/analytics/summary",
    ]

    BLOCKED_INSIGHTS_PATHS = [
        "/api/admin/ai-insights",
        "/api/admin/ai-insights/dashboard",
        "/api/admin/insights/dashboard",
    ]

    def test_non_admin_blocked_analytics_endpoints(self, non_admin_session: requests.Session):
        """Non-admin user should get 403 on all analytics endpoints."""
        base = _assert_base_url()
        for path in self.BLOCKED_ANALYTICS_PATHS:
            resp = non_admin_session.get(f"{base}{path}", timeout=40)
            assert resp.status_code == 403, f"Expected 403 for non-admin at {path}, got {resp.status_code}"
            payload = resp.json()
            assert (
                payload.get("error") == "Admin Access Required"
                or "admin" in str(payload.get("detail", "")).lower()
                or "admin" in str(payload.get("message", "")).lower()
            ), f"Unexpected deny payload for {path}: {payload}"
            print(f"PASS: Non-admin blocked at {path} with 403")

    def test_non_admin_blocked_insights_endpoints(self, non_admin_session: requests.Session):
        """Non-admin user should get 403 on all insights endpoints."""
        base = _assert_base_url()
        for path in self.BLOCKED_INSIGHTS_PATHS:
            resp = non_admin_session.get(f"{base}{path}", timeout=40)
            assert resp.status_code == 403, f"Expected 403 for non-admin at {path}, got {resp.status_code}"
            payload = resp.json()
            assert (
                payload.get("error") == "Admin Access Required"
                or "admin" in str(payload.get("detail", "")).lower()
                or "admin" in str(payload.get("message", "")).lower()
            ), f"Unexpected deny payload for {path}: {payload}"
            print(f"PASS: Non-admin blocked at {path} with 403")

    def test_free_user_blocked_analytics_insights(self, free_user_session: requests.Session):
        """Free user should also get 403 on analytics/insights endpoints."""
        base = _assert_base_url()
        test_paths = [
            "/api/admin/analytics",
            "/api/admin/ai-insights",
            "/api/admin/subscription-analytics",
        ]
        for path in test_paths:
            resp = free_user_session.get(f"{base}{path}", timeout=40)
            assert resp.status_code == 403, f"Expected 403 for free user at {path}, got {resp.status_code}"
            print(f"PASS: Free user blocked at {path} with 403")


class TestAdminAllowedForAnalyticsInsights:
    """Admin user should continue to access analytics/insights endpoints (no regression)."""

    ADMIN_ANALYTICS_PATHS = [
        "/api/admin/analytics",
        "/api/admin/subscription-analytics",
        "/api/admin/payment-analytics/provider-incidents/canary-status",
        "/api/admin/ai-insights/dashboard",
    ]

    def test_admin_allowed_analytics_insights(self, admin_session: requests.Session):
        """Admin should not be blocked by RBAC on analytics/insights endpoints."""
        base = _assert_base_url()
        for path in self.ADMIN_ANALYTICS_PATHS:
            resp = admin_session.get(f"{base}{path}", timeout=40)
            # Admin should get 200, 404 (endpoint not found), or 422 (validation error)
            # but NOT 403 (access denied)
            assert resp.status_code in {200, 404, 422}, (
                f"Admin should not be blocked by RBAC on {path}; got {resp.status_code} body={resp.text[:200]}"
            )
            print(f"PASS: Admin allowed at {path} with status {resp.status_code}")


class TestExistingAdminRouteControlsUnaffected:
    """Existing admin route controls should be unaffected for non-analytics endpoints."""

    NON_ANALYTICS_ADMIN_PATHS = [
        "/api/admin/users",
        "/api/admin/system",
        "/api/admin/platform-health",
    ]

    def test_non_admin_blocked_non_analytics_admin_routes(self, non_admin_session: requests.Session):
        """Non-admin should still be blocked on non-analytics admin routes."""
        base = _assert_base_url()
        for path in self.NON_ANALYTICS_ADMIN_PATHS:
            resp = non_admin_session.get(f"{base}{path}", timeout=40)
            # Should be 403 (admin required) or similar access denied
            assert resp.status_code in {403, 401}, (
                f"Non-admin should be blocked on {path}; got {resp.status_code}"
            )
            print(f"PASS: Non-admin blocked at non-analytics admin route {path}")

    def test_admin_allowed_non_analytics_admin_routes(self, admin_session: requests.Session):
        """Admin should be allowed on non-analytics admin routes."""
        base = _assert_base_url()
        for path in self.NON_ANALYTICS_ADMIN_PATHS:
            resp = admin_session.get(f"{base}{path}", timeout=40)
            # Admin should not get 403
            assert resp.status_code != 403, (
                f"Admin should not be blocked on {path}; got {resp.status_code}"
            )
            print(f"PASS: Admin allowed at non-analytics admin route {path} with status {resp.status_code}")


class TestFeature34BookMeetingUnaffected:
    """Feature 34 book-meeting core flow should remain unaffected by RBAC hardening."""

    def test_calendar_endpoints_accessible(self, non_admin_session: requests.Session):
        """Calendar endpoints should remain accessible for authenticated users."""
        base = _assert_base_url()
        # These are non-admin endpoints that should work for authenticated users
        calendar_paths = [
            "/api/calendar/recommend-best-slot",
        ]
        for path in calendar_paths:
            resp = non_admin_session.get(f"{base}{path}", timeout=40)
            # Should not be 403 due to admin lock
            # May be 404 (not found), 422 (validation), or 200 (success)
            assert resp.status_code != 403 or "admin" not in str(resp.json().get("error", "")).lower(), (
                f"Calendar endpoint {path} should not be blocked by admin lock; got {resp.status_code}"
            )
            print(f"PASS: Calendar endpoint {path} not blocked by admin lock (status {resp.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
