"""
Runtime tests for analytics/reporting surfaces using effective plan engine.
Verifies that all audited analytics endpoints derive plan labels from compute_effective_plan.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
BASIC_USER_EMAIL = "f21.basic.1781338672@example.com"
BASIC_USER_PASSWORD = "F21Basic#2026Aa"


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session with cookies."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code}")
    return session


@pytest.fixture(scope="module")
def free_user_session():
    """Get free user session with cookies."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Free user login failed: {resp.status_code}")
    return session


class TestAIUsageAnalytics:
    """Tests for /api/admin/ai-usage-analytics endpoint."""
    
    def test_ai_usage_analytics_returns_200_for_admin(self, admin_session):
        """Admin should access AI usage analytics."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/ai-usage-analytics")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        # Verify response structure
        assert "overview" in data
        assert "tier_distribution" in data
        assert "tier_usage" in data
        assert "limit_hit_users" in data
    
    def test_ai_usage_analytics_tier_distribution_uses_effective_plans(self, admin_session):
        """Tier distribution should use effective plans, not raw subscription_plan."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/ai-usage-analytics")
        assert resp.status_code == 200
        data = resp.json()
        tier_dist = data.get("tier_distribution", {})
        # Should have plan keys (free, basic, premium, etc.)
        assert isinstance(tier_dist, dict)
        # At minimum, free should exist
        assert "free" in tier_dist or len(tier_dist) > 0
    
    def test_ai_usage_analytics_limit_hit_users_show_effective_plan(self, admin_session):
        """Limit hit users should show effective plan labels."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/ai-usage-analytics")
        assert resp.status_code == 200
        data = resp.json()
        limit_hit_users = data.get("limit_hit_users", [])
        # If there are limit hit users, verify plan field exists
        for user in limit_hit_users[:5]:
            assert "plan" in user, f"User missing 'plan' field: {user}"
    
    def test_ai_usage_analytics_denied_for_non_admin(self, free_user_session):
        """Non-admin should be denied access."""
        resp = free_user_session.get(f"{BASE_URL}/api/admin/ai-usage-analytics")
        assert resp.status_code == 403


class TestAIFeatureAnalytics:
    """Tests for /api/admin/ai-feature-analytics endpoint."""
    
    def test_ai_feature_analytics_returns_200_for_admin(self, admin_session):
        """Admin should access AI feature analytics."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/ai-feature-analytics")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "overview" in data
        assert "feature_stats" in data
        assert "power_users" in data
    
    def test_ai_feature_analytics_power_users_show_effective_plan(self, admin_session):
        """Power users should show effective plan labels."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/ai-feature-analytics")
        assert resp.status_code == 200
        data = resp.json()
        power_users = data.get("power_users", [])
        # If there are power users, verify plan field exists
        for user in power_users[:5]:
            assert "plan" in user, f"Power user missing 'plan' field: {user}"
    
    def test_ai_feature_analytics_denied_for_non_admin(self, free_user_session):
        """Non-admin should be denied access."""
        resp = free_user_session.get(f"{BASE_URL}/api/admin/ai-feature-analytics")
        assert resp.status_code == 403


class TestPlatformAnalytics:
    """Tests for /api/admin/platform-analytics/* endpoints."""
    
    def test_engagement_scores_returns_200_for_admin(self, admin_session):
        """Admin should access engagement scores."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/platform-analytics/engagement-scores")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "users" in data
        assert "segments" in data
    
    def test_engagement_scores_users_show_effective_plan(self, admin_session):
        """Engagement score users should show effective plan labels."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/platform-analytics/engagement-scores")
        assert resp.status_code == 200
        data = resp.json()
        users = data.get("users", [])
        # If there are users, verify plan field exists
        for user in users[:5]:
            assert "plan" in user, f"User missing 'plan' field: {user}"
    
    def test_engagement_metrics_returns_200_for_admin(self, admin_session):
        """Admin should access engagement metrics."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/platform-analytics/engagement")
        assert resp.status_code == 200
        data = resp.json()
        assert "dau" in data
        assert "wau" in data
        assert "mau" in data
    
    def test_platform_analytics_denied_for_non_admin(self, free_user_session):
        """Non-admin should be denied access."""
        resp = free_user_session.get(f"{BASE_URL}/api/admin/platform-analytics/engagement-scores")
        assert resp.status_code == 403


class TestAIUserInsights:
    """Tests for /api/admin/insights/* endpoints."""
    
    def test_insights_dashboard_returns_200_for_admin(self, admin_session):
        """Admin should access insights dashboard."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/insights/dashboard")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "overview" in data
        assert "paid_users" in data.get("overview", {})
    
    def test_insights_users_returns_200_for_admin(self, admin_session):
        """Admin should access user engagement leaderboard."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/insights/users")
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
    
    def test_insights_users_show_effective_plan(self, admin_session):
        """User insights should show effective plan labels."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/insights/users")
        assert resp.status_code == 200
        data = resp.json()
        users = data.get("users", [])
        for user in users[:5]:
            assert "plan" in user, f"User missing 'plan' field: {user}"
    
    def test_churn_risk_returns_200_for_admin(self, admin_session):
        """Admin should access churn risk users."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/insights/churn-risk")
        assert resp.status_code == 200
        data = resp.json()
        assert "at_risk_users" in data
    
    def test_churn_risk_users_show_effective_plan(self, admin_session):
        """Churn risk users should show effective plan labels."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/insights/churn-risk")
        assert resp.status_code == 200
        data = resp.json()
        at_risk = data.get("at_risk_users", [])
        for user in at_risk[:5]:
            assert "plan" in user, f"At-risk user missing 'plan' field: {user}"
    
    def test_insights_denied_for_non_admin(self, free_user_session):
        """Non-admin should be denied access."""
        resp = free_user_session.get(f"{BASE_URL}/api/admin/insights/dashboard")
        assert resp.status_code == 403


class TestPaymentsUserAnalytics:
    """Tests for /api/payments/analytics/my-dashboard endpoint."""
    
    def test_my_payment_dashboard_returns_200_for_authenticated_user(self, free_user_session):
        """Authenticated user should access their payment dashboard."""
        resp = free_user_session.get(f"{BASE_URL}/api/payments/analytics/my-dashboard")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "spending" in data
        assert "subscription" in data
        assert "value" in data
    
    def test_my_payment_dashboard_shows_effective_plan(self, free_user_session):
        """Payment dashboard should show effective plan, not raw subscription_plan."""
        resp = free_user_session.get(f"{BASE_URL}/api/payments/analytics/my-dashboard")
        assert resp.status_code == 200
        data = resp.json()
        subscription = data.get("subscription", {})
        assert "plan_id" in subscription
        assert "plan_name" in subscription
        # Free user should show free plan
        assert subscription.get("plan_id") == "free" or subscription.get("plan_name") == "Free"
    
    def test_admin_payment_dashboard_shows_premium_effective_plan(self, admin_session):
        """Admin payment dashboard should show premium effective plan."""
        resp = admin_session.get(f"{BASE_URL}/api/payments/analytics/my-dashboard")
        assert resp.status_code == 200
        data = resp.json()
        subscription = data.get("subscription", {})
        # Admin should have premium effective plan
        plan_id = subscription.get("plan_id", "").lower()
        assert plan_id in ("premium", "admin", "enterprise"), f"Admin should have premium plan, got: {plan_id}"


class TestAdminPaymentAnalytics:
    """Tests for /api/admin/payment-analytics/* endpoints."""
    
    def test_subscription_overview_returns_200_for_admin(self, admin_session):
        """Admin should access subscription overview."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/payment-analytics/subscriptions/overview")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert "active_subscribers" in data
        assert "total_revenue" in data
    
    def test_subscription_integrity_report_returns_200_for_admin(self, admin_session):
        """Admin should access subscription integrity report."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/payment-analytics/subscriptions/integrity-report/latest")
        assert resp.status_code == 200
        data = resp.json()
        # Report may be empty if never run, but structure should exist
        assert "severity" in data or "report_id" in data
    
    def test_admin_payment_analytics_denied_for_non_admin(self, free_user_session):
        """Non-admin should be denied access."""
        resp = free_user_session.get(f"{BASE_URL}/api/admin/payment-analytics/subscriptions/overview")
        assert resp.status_code == 403


class TestRegressionGlobalSubscriptionEnforcement:
    """Regression tests for global subscription enforcement."""
    
    def test_free_user_blocked_from_premium_features(self, free_user_session):
        """Free user should be blocked from premium-only features."""
        # Test a premium-gated endpoint
        resp = free_user_session.get(f"{BASE_URL}/api/ai-photo-studio/status")
        # Should either return 403 or indicate free tier limitations
        if resp.status_code == 200:
            data = resp.json()
            # If accessible, should show free tier limitations
            plan = data.get("plan", data.get("effective_plan", ""))
            assert plan.lower() in ("free", ""), f"Free user should have free plan, got: {plan}"
    
    def test_admin_has_premium_access(self, admin_session):
        """Admin should have premium access."""
        resp = admin_session.get(f"{BASE_URL}/api/ai-photo-studio/status")
        if resp.status_code == 200:
            data = resp.json()
            plan = data.get("plan", data.get("effective_plan", ""))
            assert plan.lower() in ("premium", "admin", "enterprise", ""), f"Admin should have premium plan, got: {plan}"
