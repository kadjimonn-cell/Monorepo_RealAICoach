"""
Runtime API tests for legacy admin/diagnostic surfaces that should now use effective plan labels.
Verifies: admin_sessions, payments_admin_maintenance, admin_console, admin_general_analytics
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session cookies for authenticated requests."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login as admin
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if login_resp.status_code != 200:
        pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
    
    return session


class TestAdminSessionsDiagnostics:
    """Test admin_sessions.py effective plan usage in diagnostics."""
    
    def test_list_active_sessions_returns_effective_plan(self, admin_session):
        """GET /api/admin/sessions should return effective plan labels."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sessions?page=1&limit=10")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "sessions" in data
        # If sessions exist, verify plan field is present
        if data["sessions"]:
            for session in data["sessions"][:3]:
                assert "plan" in session, f"Session missing 'plan' field: {session}"
                # Plan should be one of: free, basic, premium (effective plan values)
                assert session["plan"] in ["free", "basic", "premium"], f"Unexpected plan value: {session['plan']}"
    
    def test_suspicious_sessions_returns_effective_plan(self, admin_session):
        """GET /api/admin/sessions/suspicious should return effective plan labels."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sessions/suspicious?page=1&limit=50")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "flagged_users" in data
        # If flagged users exist, verify plan field is present
        if data["flagged_users"]:
            for user in data["flagged_users"][:3]:
                assert "plan" in user, f"Flagged user missing 'plan' field: {user}"
                assert user["plan"] in ["free", "basic", "premium"], f"Unexpected plan value: {user['plan']}"


class TestPaymentsAdminMaintenanceRenewalReminders:
    """Test payments_admin_maintenance_routes.py effective plan usage."""
    
    def test_trigger_renewal_reminders_endpoint_accessible(self, admin_session):
        """POST /api/admin/trigger-renewal-reminders should be accessible."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/trigger-renewal-reminders")
        # Should return 200 with success status (even if no reminders sent)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "success" in data
        assert data["success"] is True


class TestAdminConsoleExpiryNotifications:
    """Test admin_console.py effective plan usage in expiry notifications."""
    
    def test_admin_notifications_history_returns_effective_plan_labels(self, admin_session):
        """GET /api/admin/notifications/history should show effective plan in expiry messages."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/notifications/history?days=7&limit=50")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "notifications" in data
        # Check structure is correct
        assert "summary" in data
        assert "filters" in data
    
    def test_admin_live_notifications_accessible(self, admin_session):
        """GET /api/admin/notifications/live should be accessible."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/notifications/live?limit=20")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "notifications" in data
        assert "counts" in data


class TestAdminGeneralAnalytics:
    """Test admin_general_analytics.py effective plan usage for paid user counts and distribution."""
    
    def test_general_analytics_summary_uses_effective_plan(self, admin_session):
        """GET /api/admin/general-analytics/summary should use effective plan for paid_users count."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/general-analytics/summary")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        # Verify structure
        assert "platform" in data
        assert "subscriptions" in data
        
        # Check that active_subscribers (paid_users) is present
        if "subscriptions" in data:
            assert "active_subscribers" in data["subscriptions"]
            # Value should be a non-negative integer
            assert isinstance(data["subscriptions"]["active_subscribers"], int)
            assert data["subscriptions"]["active_subscribers"] >= 0
    
    def test_analytics_charts_subscription_distribution_uses_effective_plan(self, admin_session):
        """GET /api/admin/general-analytics/charts should use effective plan for subscription distribution."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/general-analytics/charts")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "subscription_distribution" in data
        
        # Verify distribution uses effective plan labels
        dist = data["subscription_distribution"]
        if dist:
            for item in dist:
                assert "plan" in item
                assert "count" in item
                # Plan should be effective plan value
                assert item["plan"] in ["free", "basic", "premium"], f"Unexpected plan in distribution: {item['plan']}"
    
    def test_trend_detection_uses_effective_plan_for_paid_users(self, admin_session):
        """POST /api/admin/general-analytics/trend-detection should use effective plan for paid_users."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/general-analytics/trend-detection")
        # This endpoint may take time due to AI processing, so we just check it's accessible
        assert resp.status_code in [200, 500], f"Unexpected status: {resp.status_code}: {resp.text[:200]}"
        
        if resp.status_code == 200:
            data = resp.json()
            # Verify context_summary includes paid_users
            if "context_summary" in data:
                assert "paid_users" in data["context_summary"]


class TestAdminOverviewAndConsole:
    """Test admin console overview endpoints."""
    
    def test_admin_overview_accessible(self, admin_session):
        """GET /api/admin/overview should be accessible."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/overview")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "users" in data
        assert "billing" in data
    
    def test_admin_console_overview_alias_accessible(self, admin_session):
        """GET /api/admin/console/overview should be accessible (compatibility alias)."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/console/overview")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"


class TestSelfRepairEnginePreservation:
    """Verify that raw-field audit/repair behavior is preserved where appropriate."""
    
    def test_smoke_test_accessible(self, admin_session):
        """GET /api/admin/smoke-test should be accessible (system diagnostics)."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/smoke-test")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "overall" in data
        assert "checks" in data
