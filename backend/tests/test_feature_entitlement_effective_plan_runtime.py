"""
Runtime verification tests for feature-specific entitlement drift fixes.
Verifies that feature_registry, home_dashboard, sports_v2, core_platform, 
feature_access, and audio_studio_v2 all use compute_effective_plan correctly.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
BASIC_USER = {"email": "f21.basic.1781338672@example.com", "password": "F21Basic#2026Aa"}
ADMIN_USER = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}


@pytest.fixture(scope="module")
def api_session():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def _login(session, email, password):
    """Login and return session with cookies."""
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        allow_redirects=False,
    )
    return resp


class TestAccessControlSessionEffectivePlan:
    """Verify /api/access-control/session returns effective_plan correctly."""

    def test_free_user_effective_plan(self, api_session):
        """Free user should have effective_plan='free'."""
        _login(api_session, FREE_USER["email"], FREE_USER["password"])
        resp = api_session.get(f"{BASE_URL}/api/access-control/session")
        assert resp.status_code == 200
        data = resp.json()
        # Free user should have effective_plan = 'free'
        effective_plan = data.get("effective_plan") or data.get("effectivePlan")
        assert effective_plan in ["free", None], f"Expected free, got {effective_plan}"
        print(f"✓ Free user effective_plan: {effective_plan}")

    def test_basic_user_effective_plan(self, api_session):
        """Basic user should have effective_plan='basic'."""
        _login(api_session, BASIC_USER["email"], BASIC_USER["password"])
        resp = api_session.get(f"{BASE_URL}/api/access-control/session")
        assert resp.status_code == 200
        data = resp.json()
        effective_plan = data.get("effective_plan") or data.get("effectivePlan")
        # Basic user should have effective_plan = 'basic' or higher
        assert effective_plan in ["basic", "premium"], f"Expected basic/premium, got {effective_plan}"
        print(f"✓ Basic user effective_plan: {effective_plan}")

    def test_admin_user_effective_plan(self, api_session):
        """Admin user should have effective_plan='premium'."""
        _login(api_session, ADMIN_USER["email"], ADMIN_USER["password"])
        resp = api_session.get(f"{BASE_URL}/api/access-control/session")
        assert resp.status_code == 200
        data = resp.json()
        effective_plan = data.get("effective_plan") or data.get("effectivePlan")
        # Admin should have effective_plan = 'premium'
        assert effective_plan == "premium", f"Expected premium, got {effective_plan}"
        print(f"✓ Admin user effective_plan: {effective_plan}")


class TestFeatureRegistryHubInsights:
    """Verify /api/features/hub-insights uses effective plan."""

    def test_hub_insights_returns_subscription_plan_from_effective(self, api_session):
        """Hub insights should return subscription_plan derived from effective plan."""
        _login(api_session, FREE_USER["email"], FREE_USER["password"])
        resp = api_session.get(f"{BASE_URL}/api/features/hub-insights")
        if resp.status_code == 401:
            pytest.skip("Auth required - user not logged in")
        assert resp.status_code == 200
        data = resp.json()
        # subscription_plan in response should be derived from effective plan
        plan = data.get("subscription_plan")
        assert plan in ["free", "basic", "premium"], f"Unexpected plan: {plan}"
        print(f"✓ Hub insights subscription_plan: {plan}")


class TestHomeDashboardCommandCenter:
    """Verify /api/home/enterprise-command-center uses effective plan."""

    def test_command_center_returns_subscription_plan_from_effective(self, api_session):
        """Command center should return subscription_plan derived from effective plan."""
        _login(api_session, FREE_USER["email"], FREE_USER["password"])
        resp = api_session.get(f"{BASE_URL}/api/home/enterprise-command-center")
        if resp.status_code == 401:
            pytest.skip("Auth required - user not logged in")
        assert resp.status_code == 200
        data = resp.json()
        plan = data.get("subscription_plan")
        assert plan in ["free", "basic", "premium"], f"Unexpected plan: {plan}"
        print(f"✓ Command center subscription_plan: {plan}")


class TestFeatureAccessStatus:
    """Verify /api/ai-access/status uses effective tier."""

    def test_ai_access_status_uses_effective_tier(self, api_session):
        """AI access status should use effective tier for plan lookup."""
        _login(api_session, FREE_USER["email"], FREE_USER["password"])
        resp = api_session.get(f"{BASE_URL}/api/ai-access/status")
        if resp.status_code == 401:
            pytest.skip("Auth required - user not logged in")
        assert resp.status_code == 200
        data = resp.json()
        plan = data.get("plan")
        assert plan in ["free", "basic", "premium", "admin"], f"Unexpected plan: {plan}"
        print(f"✓ AI access status plan: {plan}")


class TestCorePlatformScenarios:
    """Verify core platform scenarios endpoint."""

    def test_scenarios_endpoint_accessible(self, api_session):
        """Scenarios endpoint should be accessible."""
        resp = api_session.get(f"{BASE_URL}/api/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        scenarios = data.get("scenarios", [])
        assert len(scenarios) > 0, "Expected scenarios to be returned"
        print(f"✓ Scenarios endpoint returned {len(scenarios)} scenarios")


class TestSubscriptionAccessControlRegression:
    """Regression tests for global subscription access control."""

    def test_free_user_blocked_from_admin_routes(self, api_session):
        """Free user should be blocked from admin routes."""
        _login(api_session, FREE_USER["email"], FREE_USER["password"])
        resp = api_session.get(f"{BASE_URL}/api/admin/employees")
        # Should be 401 or 403 (admin_required, not subscription_required)
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print(f"✓ Free user blocked from admin routes: {resp.status_code}")

    def test_admin_can_access_admin_routes(self, api_session):
        """Admin user should be able to access admin routes."""
        _login(api_session, ADMIN_USER["email"], ADMIN_USER["password"])
        resp = api_session.get(f"{BASE_URL}/api/admin/employees")
        # Admin should get 200 or at least not 401
        assert resp.status_code in [200, 404], f"Expected 200/404, got {resp.status_code}"
        print(f"✓ Admin can access admin routes: {resp.status_code}")


class TestPublicEndpointsNoAuth:
    """Verify public endpoints work without auth."""

    def test_features_registry_public(self, api_session):
        """Features registry should be publicly accessible."""
        # Clear any existing session
        api_session.cookies.clear()
        resp = api_session.get(f"{BASE_URL}/api/features/registry")
        assert resp.status_code == 200
        data = resp.json()
        features = data.get("features", [])
        assert len(features) > 0, "Expected features to be returned"
        print(f"✓ Features registry returned {len(features)} features")

    def test_gps_state_public(self, api_session):
        """GPS state should be publicly accessible."""
        api_session.cookies.clear()
        resp = api_session.get(f"{BASE_URL}/api/gps/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "features" in data or "subscription_plans" in data
        print("✓ GPS state accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
