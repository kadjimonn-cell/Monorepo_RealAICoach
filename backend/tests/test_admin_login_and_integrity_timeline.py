"""
Backend API tests for:
1. Admin UI login contract - verify admin can authenticate and access admin routes
2. Referral integrity incident timeline - verify new endpoint returns valid payload shape
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

E2E_BYPASS_HEADERS = {
    "X-E2E-Test-Bypass": "playwright-e2e",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}


class TestAdminLoginContract:
    """Admin UI login contract tests"""

    @pytest.fixture(scope="class")
    def session(self):
        """Create a requests session for the test class"""
        s = requests.Session()
        s.headers.update(E2E_BYPASS_HEADERS)
        return s

    def test_login_endpoint_exists(self, session):
        """Verify login endpoint is accessible"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        # Should return 401 for invalid credentials, not 404
        assert response.status_code in [401, 403, 429], f"Expected 401/403/429, got {response.status_code}"
        print(f"✓ Login endpoint exists and returns {response.status_code} for invalid credentials")

    def test_admin_login_success(self, session):
        """Admin can login with valid credentials"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        assert response.status_code in [200, 201], f"Admin login failed with status {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure - may have user info or token
        assert "user" in data or "token" in data or "email" in data, f"Unexpected response structure: {data.keys()}"
        
        # Store cookies for subsequent requests
        print(f"✓ Admin login successful, response keys: {list(data.keys())}")

    def test_admin_session_valid_after_login(self, session):
        """After login, /api/auth/me returns 200 with admin info"""
        # First login
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code in [200, 201], f"Login failed: {login_response.status_code}"
        
        # Check session
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, f"Session check failed: {me_response.status_code}"
        
        data = me_response.json()
        assert "email" in data or "user" in data, "Missing user info in /me response"
        
        # Verify admin status
        user_data = data.get("user", data)
        is_admin = user_data.get("is_admin", False) or user_data.get("role") == "admin"
        assert is_admin, f"User is not admin: {user_data}"
        print(f"✓ Admin session valid, is_admin={is_admin}")

    def test_admin_can_access_admin_analytics(self, session):
        """Admin can access admin-only referral analytics endpoint"""
        # Login first
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code in [200, 201]
        
        # Access admin endpoint
        analytics_response = session.get(f"{BASE_URL}/api/referrals/admin/analytics")
        assert analytics_response.status_code == 200, f"Admin analytics access failed: {analytics_response.status_code}"
        
        data = analytics_response.json()
        # Verify expected fields exist
        expected_fields = ["total_referrers", "total_clicks", "total_signups"]
        for field in expected_fields:
            assert field in data, f"Missing field '{field}' in analytics response"
        
        print(f"✓ Admin can access analytics, total_referrers={data.get('total_referrers')}")


class TestIntegrityIncidentTimeline:
    """Referral integrity incident timeline endpoint tests"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Create an authenticated admin session"""
        s = requests.Session()
        s.headers.update(E2E_BYPASS_HEADERS)
        
        # Login as admin
        login_response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code in [200, 201], f"Admin login failed: {login_response.status_code}"
        return s

    def test_integrity_incident_timeline_endpoint_exists(self, admin_session):
        """Verify the new integrity incident timeline endpoint exists"""
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-incident-timeline?limit=8")
        assert response.status_code == 200, f"Endpoint returned {response.status_code}: {response.text}"
        print("✓ Integrity incident timeline endpoint exists and returns 200")

    def test_integrity_incident_timeline_payload_shape(self, admin_session):
        """Verify the response has the expected payload shape"""
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-incident-timeline?limit=8")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify top-level structure
        assert "timeline" in data, f"Missing 'timeline' field in response: {data.keys()}"
        assert "count" in data, f"Missing 'count' field in response: {data.keys()}"
        assert "generated_at" in data, f"Missing 'generated_at' field in response: {data.keys()}"
        
        # Verify timeline is a list
        assert isinstance(data["timeline"], list), f"'timeline' should be a list, got {type(data['timeline'])}"
        
        # Verify count matches timeline length
        assert data["count"] == len(data["timeline"]), f"Count mismatch: {data['count']} vs {len(data['timeline'])}"
        
        print(f"✓ Payload shape valid: timeline={len(data['timeline'])} items, count={data['count']}")

    def test_integrity_incident_timeline_empty_state_valid(self, admin_session):
        """Empty timeline is a valid state (no incidents generated yet)"""
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-incident-timeline?limit=8")
        assert response.status_code == 200
        
        data = response.json()
        timeline = data.get("timeline", [])
        
        # Empty state is valid
        if len(timeline) == 0:
            assert data["count"] == 0, "Count should be 0 for empty timeline"
            print("✓ Empty timeline state is valid (no incidents yet)")
        else:
            print(f"✓ Timeline has {len(timeline)} incidents")

    def test_integrity_incident_timeline_item_structure(self, admin_session):
        """If incidents exist, verify each item has expected structure"""
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-incident-timeline?limit=8")
        assert response.status_code == 200
        
        data = response.json()
        timeline = data.get("timeline", [])
        
        if len(timeline) == 0:
            print("✓ No incidents to validate structure (empty state)")
            return
        
        # Validate first incident structure
        incident = timeline[0]
        expected_fields = [
            "incident_id", "alert_id", "title", "status", "severity",
            "message", "signals", "created_at", "affected_events_count",
            "impacted_referrers_count", "summary", "events"
        ]
        
        for field in expected_fields:
            assert field in incident, f"Missing field '{field}' in incident: {incident.keys()}"
        
        # Validate summary structure
        summary = incident.get("summary", {})
        assert "subscribed_count" in summary, "Missing subscribed_count in summary"
        assert "pending_count" in summary, "Missing pending_count in summary"
        assert "commission_at_risk" in summary, "Missing commission_at_risk in summary"
        
        # Validate events is a list
        events = incident.get("events", [])
        assert isinstance(events, list), f"'events' should be a list, got {type(events)}"
        
        print(f"✓ Incident structure valid: {incident.get('title')}, events={len(events)}")

    def test_integrity_incident_timeline_event_structure(self, admin_session):
        """If incidents have linked events, verify event structure"""
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-incident-timeline?limit=8")
        assert response.status_code == 200
        
        data = response.json()
        timeline = data.get("timeline", [])
        
        # Find an incident with events
        incident_with_events = None
        for incident in timeline:
            if len(incident.get("events", [])) > 0:
                incident_with_events = incident
                break
        
        if incident_with_events is None:
            print("✓ No incidents with linked events to validate (empty state)")
            return
        
        # Validate event structure
        event = incident_with_events["events"][0]
        expected_event_fields = [
            "referral_id", "referrer_id", "referred_user_id",
            "status", "plan", "commission_earned", "created_at"
        ]
        
        for field in expected_event_fields:
            assert field in event, f"Missing field '{field}' in event: {event.keys()}"
        
        print(f"✓ Event structure valid: referral_id={event.get('referral_id')}")

    def test_integrity_incident_timeline_limit_parameter(self, admin_session):
        """Verify limit parameter is respected"""
        # Request with limit=2
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-incident-timeline?limit=2")
        assert response.status_code == 200
        
        data = response.json()
        timeline = data.get("timeline", [])
        
        # Should not exceed limit
        assert len(timeline) <= 2, f"Timeline exceeded limit: {len(timeline)} > 2"
        print(f"✓ Limit parameter respected: returned {len(timeline)} items (limit=2)")

    def test_integrity_incident_timeline_requires_admin(self):
        """Verify endpoint requires admin authentication"""
        # Create unauthenticated session
        s = requests.Session()
        s.headers.update(E2E_BYPASS_HEADERS)
        
        response = s.get(f"{BASE_URL}/api/referrals/admin/integrity-incident-timeline?limit=8")
        
        # Should return 401 or 403 for unauthenticated request
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"✓ Endpoint requires authentication (returned {response.status_code})")


class TestAdminRouteProtection:
    """Test admin route protection after login"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Create an authenticated admin session"""
        s = requests.Session()
        s.headers.update(E2E_BYPASS_HEADERS)
        
        login_response = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code in [200, 201]
        return s

    def test_admin_can_access_ops_health(self, admin_session):
        """Admin can access ops health endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/ops-health")
        assert response.status_code == 200, f"Ops health access failed: {response.status_code}"
        
        data = response.json()
        assert "funnel" in data or "flags" in data, f"Unexpected ops health response: {data.keys()}"
        print("✓ Admin can access ops health endpoint")

    def test_admin_can_access_integrity_alerts(self, admin_session):
        """Admin can access integrity alerts endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts?status=open&page=1&page_size=10")
        assert response.status_code == 200, f"Integrity alerts access failed: {response.status_code}"
        
        data = response.json()
        # Should have data or alerts field
        assert "data" in data or "alerts" in data or "total_count" in data, f"Unexpected response: {data.keys()}"
        print("✓ Admin can access integrity alerts endpoint")

    def test_admin_can_access_integrity_trends(self, admin_session):
        """Admin can access integrity trends endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/referrals/admin/integrity-trends?days=90")
        assert response.status_code == 200, f"Integrity trends access failed: {response.status_code}"
        
        data = response.json()
        assert "windows" in data or "points" in data, f"Unexpected trends response: {data.keys()}"
        print("✓ Admin can access integrity trends endpoint")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
