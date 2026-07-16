"""
Issue 8: Delayed or Incomplete API Integrations - API Endpoint Tests
Tests for:
- /api/admin/subscription-analytics (parallelized count queries)
- /api/admin/sessions/* (no to_list(5000) truncation)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
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


class TestSubscriptionAnalyticsEndpoint:
    """Tests for /api/admin/subscription-analytics endpoint after parallelization fix."""
    
    def test_subscription_analytics_returns_valid_schema(self, admin_session):
        """Verify subscription analytics endpoint returns valid schema after count parallelization."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/subscription-analytics")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        
        # Verify top-level keys exist
        assert "period" in data, "Missing 'period' key"
        assert "kpis" in data, "Missing 'kpis' key"
        assert "distribution" in data, "Missing 'distribution' key"
        assert "platform" in data, "Missing 'platform' key"
        assert "billing" in data, "Missing 'billing' key"
        assert "plan_catalog" in data, "Missing 'plan_catalog' key"
        assert "trends" in data, "Missing 'trends' key"
        assert "funnel" in data, "Missing 'funnel' key"
        
        # Verify KPIs structure
        kpis = data["kpis"]
        assert "mrr" in kpis, "Missing 'mrr' in kpis"
        assert "arr" in kpis, "Missing 'arr' in kpis"
        assert "churn_rate" in kpis, "Missing 'churn_rate' in kpis"
        assert "active_subs" in kpis, "Missing 'active_subs' in kpis"
        assert "total_users" in kpis, "Missing 'total_users' in kpis"
        
        # Verify distribution structure
        distribution = data["distribution"]
        assert "free" in distribution, "Missing 'free' in distribution"
        assert "basic" in distribution, "Missing 'basic' in distribution"
        assert "premium" in distribution, "Missing 'premium' in distribution"
        
        # Verify platform structure
        platform = data["platform"]
        assert "apple" in platform, "Missing 'apple' in platform"
        assert "google" in platform, "Missing 'google' in platform"
        assert "stripe" in platform, "Missing 'stripe' in platform"
        
        print(f"✓ Subscription analytics returned valid schema with {len(data['trends'])} trend entries")
    
    def test_subscription_analytics_with_period_param(self, admin_session):
        """Verify subscription analytics works with different period parameters."""
        for period in ["7d", "30d", "90d"]:
            resp = admin_session.get(f"{BASE_URL}/api/admin/subscription-analytics?period={period}")
            
            assert resp.status_code == 200, f"Failed for period={period}: {resp.status_code}"
            
            data = resp.json()
            assert data["period"] == period, f"Expected period={period}, got {data['period']}"
        
        print("✓ Subscription analytics works with all period parameters (7d, 30d, 90d)")
    
    def test_subscription_analytics_overview_alias(self, admin_session):
        """Verify /overview alias endpoint works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/subscription-analytics/overview")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert "kpis" in data, "Missing 'kpis' in overview response"
        
        print("✓ Subscription analytics /overview alias works correctly")


class TestAdminSessionsEndpoint:
    """Tests for /api/admin/sessions/* endpoints after to_list(5000) fix."""
    
    def test_sessions_list_returns_valid_schema(self, admin_session):
        """Verify sessions list endpoint returns valid schema."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sessions")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        
        # Verify pagination structure
        assert "sessions" in data, "Missing 'sessions' key"
        assert "total" in data, "Missing 'total' key"
        assert "page" in data, "Missing 'page' key"
        assert "pages" in data, "Missing 'pages' key"
        
        # Verify sessions is a list
        assert isinstance(data["sessions"], list), "sessions should be a list"
        
        print(f"✓ Sessions list returned {len(data['sessions'])} sessions, total: {data['total']}")
    
    def test_sessions_stats_returns_valid_schema(self, admin_session):
        """Verify sessions stats endpoint returns valid schema."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sessions/stats")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        
        assert "total_sessions" in data, "Missing 'total_sessions' key"
        assert "unique_users" in data, "Missing 'unique_users' key"
        assert "top_users" in data, "Missing 'top_users' key"
        
        print(f"✓ Sessions stats: {data['total_sessions']} total, {data['unique_users']} unique users")
    
    def test_sessions_suspicious_returns_valid_schema(self, admin_session):
        """Verify suspicious sessions endpoint returns valid schema (uses _collect_cursor_docs)."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sessions/suspicious")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        
        assert "total_flagged" in data, "Missing 'total_flagged' key"
        assert "risk_summary" in data, "Missing 'risk_summary' key"
        assert "flagged_users" in data, "Missing 'flagged_users' key"
        assert "scanned_sessions" in data, "Missing 'scanned_sessions' key"
        assert "scanned_users" in data, "Missing 'scanned_users' key"
        
        # Verify risk_summary structure
        risk_summary = data["risk_summary"]
        assert "critical" in risk_summary, "Missing 'critical' in risk_summary"
        assert "high" in risk_summary, "Missing 'high' in risk_summary"
        assert "medium" in risk_summary, "Missing 'medium' in risk_summary"
        assert "low" in risk_summary, "Missing 'low' in risk_summary"
        
        print(f"✓ Suspicious sessions: scanned {data['scanned_sessions']} sessions, {data['total_flagged']} flagged")
    
    def test_sessions_geo_summary_returns_valid_schema(self, admin_session):
        """Verify geo summary endpoint returns valid schema (uses _collect_cursor_docs)."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sessions/geo-summary")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        
        assert "markers" in data, "Missing 'markers' key"
        assert "total_sessions" in data, "Missing 'total_sessions' key"
        assert "geolocated" in data, "Missing 'geolocated' key"
        
        print(f"✓ Geo summary: {data['total_sessions']} total sessions, {data['geolocated']} geolocated")
    
    def test_sessions_anomalies_returns_valid_schema(self, admin_session):
        """Verify anomalies endpoint returns valid schema (uses _collect_cursor_docs)."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sessions/anomalies")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        
        assert "anomalies" in data, "Missing 'anomalies' key"
        assert "summary" in data, "Missing 'summary' key"
        assert "window_minutes" in data, "Missing 'window_minutes' key"
        
        print(f"✓ Anomalies: {len(data['anomalies'])} detected in {data['window_minutes']} min window")
    
    def test_sessions_security_overview_returns_valid_schema(self, admin_session):
        """Verify security overview endpoint returns valid schema (uses _collect_cursor_docs)."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sessions/security-overview")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        
        assert "threat_level" in data, "Missing 'threat_level' key"
        assert "threat_score" in data, "Missing 'threat_score' key"
        assert "sessions" in data, "Missing 'sessions' key"
        assert "anomalies" in data, "Missing 'anomalies' key"
        assert "blocked_ips" in data, "Missing 'blocked_ips' key"
        assert "auto_response" in data, "Missing 'auto_response' key"
        
        print(f"✓ Security overview: threat_level={data['threat_level']}, score={data['threat_score']}")


class TestEnforcementAuditEndpoint:
    """Tests for subscription enforcement audit endpoint."""
    
    def test_enforcement_audit_returns_valid_schema(self, admin_session):
        """Verify enforcement audit endpoint returns valid schema."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/subscription-analytics/enforcement-audit")
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        
        assert "health_score" in data, "Missing 'health_score' key"
        assert "summary" in data, "Missing 'summary' key"
        assert "route_enforcement_matrix" in data, "Missing 'route_enforcement_matrix' key"
        
        # Verify summary structure
        summary = data["summary"]
        assert "total_users" in summary, "Missing 'total_users' in summary"
        assert "plan_counts" in summary, "Missing 'plan_counts' in summary"
        
        print(f"✓ Enforcement audit: health_score={data['health_score']}, total_users={summary['total_users']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
