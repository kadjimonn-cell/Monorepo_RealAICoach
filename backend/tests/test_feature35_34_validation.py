"""
Feature 35+34 Validation Tests
Tests for:
1. Dry Run → Apply confirmation modal in admin reliability (backfill-false-positives)
2. RBAC drift monitor + gate health badge panels
3. No regressions in /integrations and /book-meeting
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session with authentication"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    
    return session


@pytest.fixture(scope="module")
def free_user_session():
    """Get free user session with authentication"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Free user login failed: {response.status_code}")
    
    return session


class TestBackendHealth:
    """Basic health checks"""
    
    def test_health_endpoint(self):
        """Test /api/health returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health endpoint returns healthy")


class TestBackfillFalsePositivesEndpoints:
    """Tests for backfill-false-positives endpoints (Feature 34 P2 Task 2)"""
    
    def test_backfill_preview_get_endpoint(self, admin_session):
        """Test GET /api/admin/platform-health/preview-browser-e2e/backfill-false-positives"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives",
            params={"limit": 10, "window_days": 30, "profile": "standard"}
        )
        assert response.status_code == 200
        data = response.json()
        # Verify response structure
        assert "success" in data or "scanned_count" in data or "candidates" in data
        print(f"✓ Backfill preview GET endpoint works - scanned: {data.get('scanned_count', 'N/A')}")
    
    def test_backfill_simulator_endpoint(self, admin_session):
        """Test GET /api/admin/platform-health/preview-browser-e2e/backfill-false-positives/simulator"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives/simulator",
            params={"limit": 20, "window_days": 30}
        )
        assert response.status_code == 200
        data = response.json()
        # Verify simulation response structure
        assert "simulation" in data or "profiles" in data or "success" in data
        print("✓ Backfill simulator endpoint works")
    
    def test_backfill_dry_run_post(self, admin_session):
        """Test POST /api/admin/platform-health/preview-browser-e2e/backfill-false-positives with dry_run=true"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives",
            params={"limit": 10, "window_days": 30, "profile": "standard", "dry_run": "true"}
        )
        assert response.status_code == 200
        data = response.json()
        # Verify dry run response
        assert data.get("dry_run") == True or "updated_count" in data
        print(f"✓ Backfill dry run POST works - dry_run: {data.get('dry_run', 'N/A')}")
    
    def test_backfill_apply_post(self, admin_session):
        """Test POST /api/admin/platform-health/preview-browser-e2e/backfill-false-positives with dry_run=false"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives",
            params={"limit": 5, "window_days": 30, "profile": "standard", "dry_run": "false"}
        )
        assert response.status_code == 200
        data = response.json()
        # Verify apply response
        assert "updated_count" in data or "success" in data
        print(f"✓ Backfill apply POST works - updated: {data.get('updated_count', 'N/A')}")


class TestRBACDriftMonitorEndpoints:
    """Tests for RBAC drift monitor + gate health badge panels"""
    
    def test_rbac_drift_monitor_endpoint(self, admin_session):
        """Test GET /api/admin/platform-health/rbac-drift-monitor"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/platform-health/rbac-drift-monitor",
            params={"limit": 100}
        )
        assert response.status_code == 200
        data = response.json()
        # Verify RBAC drift monitor response structure
        assert "status" in data or "scanned_routes" in data or "uncovered_route_count" in data
        print(f"✓ RBAC drift monitor endpoint works - status: {data.get('status', 'N/A')}")
    
    def test_rbac_gate_health_endpoint(self, admin_session):
        """Test GET /api/admin/platform-health/rbac-gate-health"""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/rbac-gate-health")
        assert response.status_code == 200
        data = response.json()
        # Verify RBAC gate health response structure
        assert "status" in data or "health_score" in data or "block_rate" in data
        print(f"✓ RBAC gate health endpoint works - status: {data.get('status', 'N/A')}, score: {data.get('health_score', 'N/A')}")


class TestReleaseGateSafeRolloutSimulator:
    """Tests for release-gate safe rollout simulator (Feature 34)"""
    
    def test_safe_rollout_simulator_endpoint(self, admin_session):
        """Test GET /api/admin/calendar/release-gate/safe-rollout-simulator"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/calendar/release-gate/safe-rollout-simulator",
            params={"sample_size": 20}
        )
        assert response.status_code == 200
        data = response.json()
        # Verify simulator response structure
        assert "active_profile" in data or "simulation" in data or "recommendation" in data
        print(f"✓ Safe rollout simulator endpoint works - active_profile: {data.get('active_profile', 'N/A')}")


class TestIntegrationsEndpoints:
    """Tests for /integrations endpoints (Feature 35)"""
    
    def test_integrations_available(self, admin_session):
        """Test GET /api/integrations/available"""
        response = admin_session.get(f"{BASE_URL}/api/integrations/available")
        assert response.status_code == 200
        data = response.json()
        assert "integrations" in data
        print(f"✓ Integrations available endpoint works - count: {len(data.get('integrations', []))}")
    
    def test_integrations_list(self, admin_session):
        """Test GET /api/integrations/"""
        response = admin_session.get(f"{BASE_URL}/api/integrations/")
        assert response.status_code == 200
        data = response.json()
        assert "integrations" in data
        print(f"✓ Integrations list endpoint works - connected: {len(data.get('integrations', []))}")
    
    def test_integrations_dashboard_stats(self, admin_session):
        """Test GET /api/integrations/dashboard/stats"""
        response = admin_session.get(f"{BASE_URL}/api/integrations/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        # Verify stats response structure
        assert "active_integrations" in data or "total_candidates" in data or "health_score" in data
        print(f"✓ Integrations dashboard stats endpoint works - active: {data.get('active_integrations', 'N/A')}")
    
    def test_admin_seed_cleanup_policy(self, admin_session):
        """Test GET /api/integrations/admin/test-mode-seed-policy"""
        response = admin_session.get(f"{BASE_URL}/api/integrations/admin/test-mode-seed-policy")
        assert response.status_code == 200
        data = response.json()
        # Verify policy response structure
        assert "policy" in data or "enabled" in data or "retention_hours" in data
        print("✓ Admin seed cleanup policy endpoint works")


class TestBookMeetingEndpoints:
    """Tests for /book-meeting related endpoints (calendar/agenda)"""
    
    def test_calendar_status(self, admin_session):
        """Test GET /api/calendar/status"""
        response = admin_session.get(f"{BASE_URL}/api/calendar/status")
        assert response.status_code == 200
        data = response.json()
        assert "google_connected" in data
        print(f"✓ Calendar status endpoint works - google_connected: {data.get('google_connected', 'N/A')}")
    
    def test_admin_calendar_reliability(self, admin_session):
        """Test GET /api/admin/calendar/reliability"""
        response = admin_session.get(f"{BASE_URL}/api/admin/calendar/reliability")
        assert response.status_code == 200
        data = response.json()
        # Verify reliability response structure
        assert "profile" in data or "summary" in data
        print(f"✓ Admin calendar reliability endpoint works - profile: {data.get('profile', 'N/A')}")


class TestNonAdminAccessControl:
    """Tests to verify non-admin users cannot access admin endpoints"""
    
    def test_non_admin_cannot_access_rbac_drift_monitor(self, free_user_session):
        """Test that non-admin users get 403 on RBAC drift monitor"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/platform-health/rbac-drift-monitor")
        assert response.status_code in [401, 403]
        print(f"✓ Non-admin blocked from RBAC drift monitor - status: {response.status_code}")
    
    def test_non_admin_cannot_access_rbac_gate_health(self, free_user_session):
        """Test that non-admin users get 403 on RBAC gate health"""
        response = free_user_session.get(f"{BASE_URL}/api/admin/platform-health/rbac-gate-health")
        assert response.status_code in [401, 403]
        print(f"✓ Non-admin blocked from RBAC gate health - status: {response.status_code}")
    
    def test_non_admin_cannot_access_backfill_endpoints(self, free_user_session):
        """Test that non-admin users get 403 on backfill endpoints"""
        response = free_user_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives"
        )
        assert response.status_code in [401, 403]
        print(f"✓ Non-admin blocked from backfill endpoints - status: {response.status_code}")
    
    def test_non_admin_cannot_access_seed_cleanup_policy(self, free_user_session):
        """Test that non-admin users get 403 on seed cleanup policy"""
        response = free_user_session.get(f"{BASE_URL}/api/integrations/admin/test-mode-seed-policy")
        assert response.status_code in [401, 403]
        print(f"✓ Non-admin blocked from seed cleanup policy - status: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
