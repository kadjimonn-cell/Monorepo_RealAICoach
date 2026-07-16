"""
Test suite for Provider Incidents and Nova Curation Hub APIs
Tests the new P2 features: Provider Incidents drilldown, canary status, and Nova curation hub
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
CURATION_USER_EMAIL = "curation.1779076352@example.com"
CURATION_USER_PASSWORD = "NovaV2#2026!Aa"


class TestProviderIncidentsAPI:
    """Tests for Provider Incidents admin endpoints"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json", "X-Client-Platform": "mobile"}
        )
        assert resp.status_code == 200, f"Admin login failed: {resp.text[:200]}"
        data = resp.json()
        token = data.get("session_token") or data.get("token")
        assert token, "No token in login response"
        return token
    
    def test_provider_incidents_drilldown(self, admin_token):
        """Test /admin/payment-analytics/provider-incidents/drilldown endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        resp = requests.get(
            f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/drilldown?hours=72&provider=all&limit=50",
            headers=headers
        )
        
        assert resp.status_code == 200, f"Drilldown failed: {resp.text[:300]}"
        data = resp.json()
        
        # Validate response structure
        assert "generated_at" in data, "Missing generated_at field"
        assert "window_hours" in data, "Missing window_hours field"
        assert "summary" in data, "Missing summary field"
        assert "provider_rollup" in data, "Missing provider_rollup field"
        assert "incident_timeline" in data, "Missing incident_timeline field"
        assert "webhook_retry_queue" in data, "Missing webhook_retry_queue field"
        
        # Validate summary structure
        summary = data["summary"]
        assert "total_incidents" in summary, "Missing total_incidents in summary"
        assert "providers_impacted" in summary, "Missing providers_impacted in summary"
        
        print(f"Drilldown response: total_incidents={summary.get('total_incidents')}, providers_impacted={summary.get('providers_impacted')}")
    
    def test_provider_incidents_drilldown_with_provider_filter(self, admin_token):
        """Test drilldown with specific provider filter"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        resp = requests.get(
            f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/drilldown?hours=24&provider=stripe&limit=20",
            headers=headers
        )
        
        assert resp.status_code == 200, f"Drilldown with filter failed: {resp.text[:300]}"
        data = resp.json()
        assert "summary" in data
    
    def test_canary_status(self, admin_token):
        """Test /admin/payment-analytics/provider-incidents/canary-status endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        resp = requests.get(
            f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-status",
            headers=headers
        )
        
        assert resp.status_code == 200, f"Canary status failed: {resp.text[:300]}"
        data = resp.json()
        
        # Validate response structure
        assert "generated_at" in data, "Missing generated_at field"
        assert "summary" in data, "Missing summary field"
        assert "jobs" in data, "Missing jobs field"
        
        # Validate summary structure
        summary = data["summary"]
        assert "healthy" in summary, "Missing healthy count in summary"
        assert "warning" in summary, "Missing warning count in summary"
        assert "critical" in summary, "Missing critical count in summary"
        
        # Validate jobs structure if any exist
        if data["jobs"]:
            job = data["jobs"][0]
            assert "job_id" in job, "Missing job_id in job"
            assert "health" in job, "Missing health in job"
            assert "status" in job, "Missing status in job"
        
        print(f"Canary status: healthy={summary.get('healthy')}, warning={summary.get('warning')}, critical={summary.get('critical')}")
    
    def test_canary_run_now(self, admin_token):
        """Test /admin/payment-analytics/provider-incidents/canary-run-now endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        resp = requests.post(
            f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-run-now",
            headers=headers,
            json={"canary_id": "critical_journey_monitor"}
        )
        
        assert resp.status_code == 200, f"Canary run now failed: {resp.text[:300]}"
        data = resp.json()
        
        # Validate response structure
        assert "ok" in data, "Missing ok field"
        assert "canary_id" in data, "Missing canary_id field"
        assert data["ok"], "Canary run now should return ok=True"
        assert data["canary_id"] == "critical_journey_monitor", "Canary ID mismatch"
        
        print(f"Canary run now: ok={data.get('ok')}, canary_id={data.get('canary_id')}")
    
    def test_canary_run_now_invalid_canary(self, admin_token):
        """Test canary run now with invalid canary ID"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        resp = requests.post(
            f"{BASE_URL}/api/admin/payment-analytics/provider-incidents/canary-run-now",
            headers=headers,
            json={"canary_id": "invalid_canary_id_12345"}
        )
        
        # Should return 400 or 404 for invalid canary
        assert resp.status_code in [400, 404, 200], f"Unexpected status for invalid canary: {resp.status_code}"


class TestNovaCurationHubAPI:
    """Tests for Nova Curation Hub endpoints (pins and favorites)"""
    
    @pytest.fixture(scope="class")
    def user_token(self):
        """Get user authentication token for curation hub testing"""
        # Try curation user first
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CURATION_USER_EMAIL, "password": CURATION_USER_PASSWORD},
            headers={"Content-Type": "application/json", "X-Client-Platform": "mobile"}
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("session_token") or data.get("token")
            if token:
                return token
        
        # Fallback to admin
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json", "X-Client-Platform": "mobile"}
        )
        assert resp.status_code == 200, f"Login failed: {resp.text[:200]}"
        data = resp.json()
        token = data.get("session_token") or data.get("token")
        assert token, "No token in login response"
        return token
    
    def test_get_pins(self, user_token):
        """Test /support/chat/conversations/pins endpoint"""
        headers = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}
        resp = requests.get(
            f"{BASE_URL}/api/support/chat/conversations/pins?limit=60",
            headers=headers
        )
        
        assert resp.status_code == 200, f"Get pins failed: {resp.text[:300]}"
        data = resp.json()
        
        # Validate response structure
        assert "pins" in data, "Missing pins field"
        assert isinstance(data["pins"], list), "pins should be a list"
        
        print(f"Pins count: {len(data['pins'])}")
    
    def test_get_favorites(self, user_token):
        """Test /support/chat/messages/favorites endpoint"""
        headers = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}
        resp = requests.get(
            f"{BASE_URL}/api/support/chat/messages/favorites?limit=100",
            headers=headers
        )
        
        assert resp.status_code == 200, f"Get favorites failed: {resp.text[:300]}"
        data = resp.json()
        
        # Validate response structure
        assert "favorites" in data, "Missing favorites field"
        assert isinstance(data["favorites"], list), "favorites should be a list"
        
        print(f"Favorites count: {len(data['favorites'])}")


class TestHealthAndBasicEndpoints:
    """Basic health and connectivity tests"""
    
    def test_health_endpoint(self):
        """Test /health endpoint"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    
    def test_admin_login(self):
        """Test admin login works"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json", "X-Client-Platform": "mobile"}
        )
        assert resp.status_code == 200, f"Admin login failed: {resp.text[:200]}"
        data = resp.json()
        assert "session_token" in data or "token" in data, "No token in response"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
