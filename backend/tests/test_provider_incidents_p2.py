"""
P2 Provider Incidents API Tests - Iteration 112
Tests for provider incidents drilldown, canary status, and run-now functionality
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
CURATION_EMAIL = "curation.1779076352@example.com"
CURATION_PASSWORD = "NovaV2#2026!Aa"


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session with auth cookies"""
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
    assert login_resp.status_code == 200, f"Admin login failed: {login_resp.status_code} - {login_resp.text}"
    return session


@pytest.fixture(scope="module")
def curation_session():
    """Get curation user session with auth cookies"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login as curation user
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": CURATION_EMAIL,
        "password": CURATION_PASSWORD
    })
    assert login_resp.status_code == 200, f"Curation user login failed: {login_resp.status_code} - {login_resp.text}"
    return session


class TestProviderIncidentsDrilldown:
    """Tests for /admin/payment-analytics/provider-incidents/drilldown endpoint"""
    
    def test_drilldown_default_params(self, admin_session):
        """Test drilldown with default parameters"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/drilldown")
        assert resp.status_code == 200, f"Drilldown failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        # Verify response structure
        assert "generated_at" in data
        assert "window_hours" in data
        assert "provider_filter" in data
        assert "summary" in data
        assert "provider_rollup" in data
        assert "incident_timeline" in data
        assert "webhook_retry_queue" in data
        
        # Verify summary structure
        summary = data["summary"]
        assert "total_incidents" in summary
        assert "providers_impacted" in summary
        assert "critical_incidents" in summary
        assert "high_incidents" in summary
        
        print(f"✓ Drilldown returned {summary['total_incidents']} incidents, {summary['providers_impacted']} providers impacted")
    
    def test_drilldown_with_hours_filter(self, admin_session):
        """Test drilldown with different hours filter"""
        for hours in [24, 72, 168]:
            resp = admin_session.get(f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/drilldown?hours={hours}")
            assert resp.status_code == 200, f"Drilldown with hours={hours} failed: {resp.status_code}"
            
            data = resp.json()
            assert data["window_hours"] == hours
            print(f"✓ Drilldown with hours={hours} returned successfully")
    
    def test_drilldown_with_provider_filter(self, admin_session):
        """Test drilldown with provider filter"""
        # Test with 'all' provider
        resp = admin_session.get(f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/drilldown?provider=all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_filter"] == "all"
        
        # Test with specific provider
        resp = admin_session.get(f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/drilldown?provider=stripe")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_filter"] == "stripe"
        print("✓ Provider filter works correctly")
    
    def test_drilldown_requires_admin(self, curation_session):
        """Test that drilldown requires admin access"""
        resp = curation_session.get(f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/drilldown")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Drilldown correctly requires admin access")


class TestProviderIncidentsCanaryStatus:
    """Tests for /admin/payment-analytics/provider-incidents/canary-status endpoint"""
    
    def test_canary_status_returns_jobs(self, admin_session):
        """Test canary status returns job list"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-status")
        assert resp.status_code == 200, f"Canary status failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        # Verify response structure
        assert "generated_at" in data
        assert "summary" in data
        assert "jobs" in data
        
        # Verify summary structure
        summary = data["summary"]
        assert "healthy" in summary
        assert "warning" in summary
        assert "critical" in summary
        
        # Verify jobs list
        jobs = data["jobs"]
        assert isinstance(jobs, list)
        
        # Check for expected canary jobs
        job_ids = [job.get("job_id") for job in jobs]
        expected_jobs = [
            "critical_journey_monitor",
            "admin_routes_sentinel",
            "platform_e2e_regression_gate",
            "growth_integrity_monitor"
        ]
        
        for expected in expected_jobs:
            assert expected in job_ids, f"Expected job {expected} not found in canary status"
        
        print(f"✓ Canary status returned {len(jobs)} jobs, summary: healthy={summary['healthy']}, warning={summary['warning']}, critical={summary['critical']}")
    
    def test_canary_status_job_structure(self, admin_session):
        """Test that each canary job has required fields"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-status")
        assert resp.status_code == 200
        
        data = resp.json()
        jobs = data["jobs"]
        
        for job in jobs:
            assert "job_id" in job
            assert "label" in job
            assert "status" in job
            assert "health" in job
            assert "last_run" in job
            print(f"  - Job: {job['job_id']} | Health: {job['health']} | Status: {job['status']}")
        
        print(f"✓ All {len(jobs)} jobs have required structure")
    
    def test_canary_status_requires_admin(self, curation_session):
        """Test that canary status requires admin access"""
        resp = curation_session.get(f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-status")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Canary status correctly requires admin access")


class TestProviderIncidentsCanaryRunNow:
    """Tests for /admin/payment-analytics/provider-incidents/canary-run-now endpoint"""
    
    def test_run_now_supported_canary(self, admin_session):
        """Test run-now for supported canary IDs"""
        supported_canaries = [
            "critical_journey_monitor",
            "platform_e2e_regression_gate",
            "growth_integrity_monitor"
        ]
        
        for canary_id in supported_canaries:
            resp = admin_session.post(
                f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-run-now",
                json={"canary_id": canary_id}
            )
            # Should return 200 for supported canaries
            assert resp.status_code == 200, f"Run-now for {canary_id} failed: {resp.status_code} - {resp.text}"
            
            data = resp.json()
            assert data.get("ok")
            assert data.get("canary_id") == canary_id
            assert "started_at" in data
            assert "finished_at" in data
            print(f"✓ Run-now for {canary_id} completed successfully")
    
    def test_run_now_unsupported_canary(self, admin_session):
        """Test run-now for unsupported canary ID returns 400"""
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-run-now",
            json={"canary_id": "unsupported_canary_id"}
        )
        assert resp.status_code == 400, f"Expected 400 for unsupported canary, got {resp.status_code}"
        print("✓ Run-now correctly rejects unsupported canary IDs")
    
    def test_run_now_empty_canary_id(self, admin_session):
        """Test run-now with empty canary_id returns 400"""
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-run-now",
            json={"canary_id": ""}
        )
        assert resp.status_code == 400, f"Expected 400 for empty canary_id, got {resp.status_code}"
        print("✓ Run-now correctly rejects empty canary_id")
    
    def test_run_now_requires_admin(self, curation_session):
        """Test that run-now requires admin access"""
        resp = curation_session.post(
            f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-run-now",
            json={"canary_id": "critical_journey_monitor"}
        )
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Run-now correctly requires admin access")


class TestNovaCurationHubAPIs:
    """Tests for Nova curation hub related APIs (pins and favorites)"""
    
    def test_get_pins(self, curation_session):
        """Test getting pinned conversations"""
        resp = curation_session.get(f"{BASE_URL}/api/support/chat/conversations/pins?limit=60")
        assert resp.status_code == 200, f"Get pins failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "pins" in data
        assert isinstance(data["pins"], list)
        print(f"✓ Get pins returned {len(data['pins'])} pinned conversations")
    
    def test_get_favorites(self, curation_session):
        """Test getting favorite messages"""
        resp = curation_session.get(f"{BASE_URL}/api/support/chat/messages/favorites?limit=100")
        assert resp.status_code == 200, f"Get favorites failed: {resp.status_code} - {resp.text}"
        
        data = resp.json()
        assert "favorites" in data
        assert isinstance(data["favorites"], list)
        print(f"✓ Get favorites returned {len(data['favorites'])} favorite messages")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
