"""
Feature 36 Integrity Controls Visibility Fix - Verification Tests
Tests that admin referral analytics panel exposes integrity controls near top.
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


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login as admin
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
    return session


@pytest.fixture(scope="module")
def basic_session():
    """Get authenticated basic user session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login as basic user
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": BASIC_EMAIL,
        "password": BASIC_PASSWORD
    })
    assert login_resp.status_code == 200, f"Basic user login failed: {login_resp.text}"
    return session


class TestIntegrityAlertsEvaluate:
    """Test POST /api/referrals/admin/integrity-alerts/evaluate"""
    
    def test_evaluate_returns_success(self, admin_session):
        """Evaluate endpoint returns success with metrics and recommendation."""
        resp = admin_session.post(f"{BASE_URL}/api/referrals/admin/integrity-alerts/evaluate")
        assert resp.status_code == 200, f"Evaluate failed: {resp.text}"
        data = resp.json()
        assert "success" in data
        assert data["success"] is True
        # Should have metrics and recommendation
        assert "metrics" in data or "recommendation" in data or "alert_created" in data
        print(f"✓ Evaluate integrity alerts: {data}")
    
    def test_evaluate_requires_admin(self, basic_session):
        """Non-admin users should be blocked from evaluate endpoint."""
        resp = basic_session.post(f"{BASE_URL}/api/referrals/admin/integrity-alerts/evaluate")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Non-admin blocked from evaluate endpoint")


class TestIntegrityAlertsList:
    """Test GET /api/referrals/admin/integrity-alerts"""
    
    def test_list_alerts_returns_data(self, admin_session):
        """List alerts endpoint returns paginated data."""
        resp = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts?status=open&page=1&page_size=10")
        assert resp.status_code == 200, f"List alerts failed: {resp.text}"
        data = resp.json()
        # Should have data/alerts array and total_count
        assert "data" in data or "alerts" in data
        assert "total_count" in data
        print(f"✓ List integrity alerts: total_count={data.get('total_count', 0)}")
    
    def test_list_alerts_requires_admin(self, basic_session):
        """Non-admin users should be blocked from list alerts endpoint."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts?status=open&page=1&page_size=10")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Non-admin blocked from list alerts endpoint")


class TestIntegrityTrends:
    """Test GET /api/referrals/admin/integrity-trends"""
    
    def test_trends_returns_windows(self, admin_session):
        """Trends endpoint returns 7/30/90 day windows."""
        resp = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-trends?days=90")
        assert resp.status_code == 200, f"Trends failed: {resp.text}"
        data = resp.json()
        # Should have windows for 7, 30, 90 days
        assert "windows" in data
        windows = data["windows"]
        assert "7" in windows or 7 in windows
        assert "30" in windows or 30 in windows
        assert "90" in windows or 90 in windows
        # Should have points array
        assert "points" in data
        print(f"✓ Integrity trends: windows={list(windows.keys())}, points_count={len(data.get('points', []))}")
    
    def test_trends_requires_admin(self, basic_session):
        """Non-admin users should be blocked from trends endpoint."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/admin/integrity-trends?days=90")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Non-admin blocked from trends endpoint")


class TestFraudPolicyRecommendation:
    """Test GET /api/referrals/admin/fraud-policy/recommendation"""
    
    def test_recommendation_returns_profile(self, admin_session):
        """Recommendation endpoint returns active profile and recommendation."""
        resp = admin_session.get(f"{BASE_URL}/api/referrals/admin/fraud-policy/recommendation")
        assert resp.status_code == 200, f"Recommendation failed: {resp.text}"
        data = resp.json()
        # Should have active_profile and recommendation
        assert "active_profile" in data or "recommendation" in data
        print(f"✓ Fraud policy recommendation: {list(data.keys())}")
    
    def test_recommendation_requires_admin(self, basic_session):
        """Non-admin users should be blocked from recommendation endpoint."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/admin/fraud-policy/recommendation")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Non-admin blocked from recommendation endpoint")


class TestApplyRecommendedProfile:
    """Test POST /api/referrals/admin/fraud-policy/apply-recommendation"""
    
    def test_apply_returns_success(self, admin_session):
        """Apply recommendation endpoint returns success."""
        resp = admin_session.post(f"{BASE_URL}/api/referrals/admin/fraud-policy/apply-recommendation", json={})
        assert resp.status_code == 200, f"Apply recommendation failed: {resp.text}"
        data = resp.json()
        assert "success" in data
        assert data["success"] is True
        print(f"✓ Apply recommended profile: {data}")
    
    def test_apply_requires_admin(self, basic_session):
        """Non-admin users should be blocked from apply recommendation endpoint."""
        resp = basic_session.post(f"{BASE_URL}/api/referrals/admin/fraud-policy/apply-recommendation", json={})
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Non-admin blocked from apply recommendation endpoint")


class TestFraudScanWithIntegrity:
    """Test POST /api/referrals/admin/fraud-scan/run includes integrity payload"""
    
    def test_fraud_scan_includes_integrity(self, admin_session):
        """Fraud scan endpoint includes integrity_alert in response."""
        resp = admin_session.post(f"{BASE_URL}/api/referrals/admin/fraud-scan/run")
        assert resp.status_code == 200, f"Fraud scan failed: {resp.text}"
        data = resp.json()
        # Should include integrity_alert payload
        assert "integrity_alert" in data, f"Missing integrity_alert in fraud scan response: {list(data.keys())}"
        print(f"✓ Fraud scan includes integrity_alert: {data.get('integrity_alert', {}).get('success', 'N/A')}")


class TestReferralsUserWorkspaceRegression:
    """Regression tests for /referrals user workspace tabs"""
    
    def test_my_stats_endpoint(self, basic_session):
        """User can get their referral stats."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/my-stats")
        assert resp.status_code == 200, f"my-stats failed: {resp.text}"
        data = resp.json()
        assert "referral_code" in data
        assert "total_clicks" in data
        print(f"✓ my-stats: code={data.get('referral_code')}")
    
    def test_my_referrals_endpoint(self, basic_session):
        """User can get their referrals list."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/my-referrals")
        assert resp.status_code == 200, f"my-referrals failed: {resp.text}"
        data = resp.json()
        assert "referrals" in data
        print(f"✓ my-referrals: count={len(data.get('referrals', []))}")
    
    def test_my_credits_endpoint(self, basic_session):
        """User can get their credit balance."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/my-credits")
        assert resp.status_code == 200, f"my-credits failed: {resp.text}"
        data = resp.json()
        assert "balance" in data
        print(f"✓ my-credits: balance={data.get('balance')}")
    
    def test_public_leaderboard_endpoint(self, basic_session):
        """User can access public leaderboard."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/public-leaderboard")
        assert resp.status_code == 200, f"public-leaderboard failed: {resp.text}"
        data = resp.json()
        assert "leaderboard" in data
        print(f"✓ public-leaderboard: count={len(data.get('leaderboard', []))}")
    
    def test_my_milestones_endpoint(self, basic_session):
        """User can get their milestones."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/my-milestones")
        assert resp.status_code == 200, f"my-milestones failed: {resp.text}"
        data = resp.json()
        assert "milestones" in data or "achieved" in data
        print(f"✓ my-milestones: {list(data.keys())}")
    
    def test_my_challenges_endpoint(self, basic_session):
        """User can get their challenges."""
        resp = basic_session.get(f"{BASE_URL}/api/referrals/my-challenges")
        assert resp.status_code == 200, f"my-challenges failed: {resp.text}"
        data = resp.json()
        assert "challenges" in data or "active" in data
        print(f"✓ my-challenges: {list(data.keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
