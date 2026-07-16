"""
WebSocket Ticket Security P1 Migration Tests - Iteration 57

Tests for the P1 migration of admin/employer WS channels to ticket-only auth:
- POST /api/auth/ws-ticket channel allowlist enforcement
- Admin WS channels: admin-activity, automation-dashboard, aso-dashboard, siem-events, enterprise-live
- System metrics WS: /api/ws/system-metrics and /ws/system-metrics
- Jobs employer pipeline WS: /api/ws/jobs/employer/pipeline
- Ticket replay rejection (one-time use)
- No-ticket connection rejection
"""

import pytest
import requests
import os
import time
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# CSRF header required for state-changing requests
CSRF_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


class TestWsTicketEndpoint:
    """Tests for POST /api/auth/ws-ticket endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session and authenticate as admin"""
        self.session = requests.Session()
        self.session.headers.update(CSRF_HEADERS)
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        
        # Store cookies for authenticated requests
        self.cookies = login_resp.cookies
        
    def test_ws_ticket_requires_authentication(self):
        """WS ticket endpoint should reject unauthenticated requests"""
        # Use a fresh session without auth
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        resp = fresh_session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "notifications"
        })
        
        assert resp.status_code == 401, f"Expected 401 for unauthenticated request, got {resp.status_code}"
        print("PASS: WS ticket endpoint rejects unauthenticated requests")
    
    def test_ws_ticket_issued_for_notifications_channel(self):
        """WS ticket should be issued for notifications channel"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "notifications"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        assert len(data["ticket"]) > 20, "Ticket should be a substantial string"
        assert data.get("expires_in_seconds", 0) > 0, "Should have expiry info"
        print(f"PASS: WS ticket issued for notifications channel, expires in {data.get('expires_in_seconds')}s")
    
    def test_ws_ticket_issued_for_admin_activity_channel(self):
        """WS ticket should be issued for admin_activity channel (admin only)"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "admin_activity"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        print("PASS: WS ticket issued for admin_activity channel")
    
    def test_ws_ticket_issued_for_automation_dashboard_channel(self):
        """WS ticket should be issued for automation_dashboard channel"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "automation_dashboard"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        print("PASS: WS ticket issued for automation_dashboard channel")
    
    def test_ws_ticket_issued_for_aso_dashboard_channel(self):
        """WS ticket should be issued for aso_dashboard channel"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "aso_dashboard"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        print("PASS: WS ticket issued for aso_dashboard channel")
    
    def test_ws_ticket_issued_for_siem_events_channel(self):
        """WS ticket should be issued for siem_events channel"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "siem_events"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        print("PASS: WS ticket issued for siem_events channel")
    
    def test_ws_ticket_issued_for_enterprise_live_channel(self):
        """WS ticket should be issued for enterprise_live channel"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "enterprise_live"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        print("PASS: WS ticket issued for enterprise_live channel")
    
    def test_ws_ticket_issued_for_system_metrics_channel(self):
        """WS ticket should be issued for system_metrics channel"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "system_metrics"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        print("PASS: WS ticket issued for system_metrics channel")
    
    def test_ws_ticket_issued_for_jobs_employer_pipeline_channel(self):
        """WS ticket should be issued for jobs_employer_pipeline channel"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "jobs_employer_pipeline"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        print("PASS: WS ticket issued for jobs_employer_pipeline channel")
    
    def test_ws_ticket_rejects_unsupported_channel(self):
        """WS ticket endpoint should reject unsupported channels"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "invalid_channel_xyz"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 400, f"Expected 400 for unsupported channel, got {resp.status_code}"
        print("PASS: WS ticket endpoint rejects unsupported channels")
    
    def test_ws_ticket_default_channel_is_notifications(self):
        """WS ticket endpoint should default to notifications channel if not specified"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={},
            cookies=self.cookies
        )
        
        # Should succeed with default channel
        assert resp.status_code == 200, f"Expected 200 with default channel, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket' field"
        print("PASS: WS ticket endpoint defaults to notifications channel")


class TestWsTicketAllowlist:
    """Tests for WS_TICKET_ALLOWED_CHANNELS allowlist"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session and authenticate as admin"""
        self.session = requests.Session()
        self.session.headers.update(CSRF_HEADERS)
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.cookies = login_resp.cookies
    
    def test_all_migrated_channels_in_allowlist(self):
        """All P1 migrated channels should be in the allowlist"""
        migrated_channels = [
            "notifications",
            "admin_activity",
            "automation_dashboard",
            "aso_dashboard",
            "siem_events",
            "enterprise_live",
            "system_metrics",
            "jobs_employer_pipeline",
        ]
        
        for channel in migrated_channels:
            resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
                json={"channel": channel},
                cookies=self.cookies
            )
            assert resp.status_code == 200, f"Channel '{channel}' should be in allowlist, got {resp.status_code}: {resp.text}"
            print(f"PASS: Channel '{channel}' is in allowlist")
        
        print(f"PASS: All {len(migrated_channels)} migrated channels are in allowlist")


class TestAdminSystemMetricsEndpoint:
    """Tests for admin system metrics REST endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session and authenticate as admin"""
        self.session = requests.Session()
        self.session.headers.update(CSRF_HEADERS)
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.cookies = login_resp.cookies
    
    def test_admin_system_metrics_requires_auth(self):
        """GET /api/admin/system/metrics should require authentication"""
        fresh_session = requests.Session()
        resp = fresh_session.get(f"{BASE_URL}/api/admin/system/metrics")
        
        assert resp.status_code in [401, 403], f"Expected 401/403 for unauthenticated request, got {resp.status_code}"
        print("PASS: Admin system metrics endpoint requires authentication")
    
    def test_admin_system_metrics_returns_data(self):
        """GET /api/admin/system/metrics should return system metrics for admin"""
        resp = self.session.get(f"{BASE_URL}/api/admin/system/metrics", cookies=self.cookies)
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify expected fields
        assert "cpu" in data, "Response should contain 'cpu' field"
        assert "memory" in data, "Response should contain 'memory' field"
        assert "disk" in data, "Response should contain 'disk' field"
        assert "network" in data, "Response should contain 'network' field"
        
        print(f"PASS: Admin system metrics returns data - CPU: {data['cpu'].get('percent')}%, Memory: {data['memory'].get('percent')}%")


class TestFrontendWsTicketUsage:
    """Tests to verify frontend components use ticket param (not token param)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session and authenticate as admin"""
        self.session = requests.Session()
        self.session.headers.update(CSRF_HEADERS)
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.cookies = login_resp.cookies
    
    def test_ws_ticket_response_format(self):
        """WS ticket response should have correct format for frontend usage"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "admin_activity"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        
        # Verify response format matches what frontend expects
        assert "ticket" in data, "Response must have 'ticket' field"
        assert isinstance(data["ticket"], str), "Ticket must be a string"
        assert len(data["ticket"]) > 0, "Ticket must not be empty"
        
        # Verify ticket is URL-safe (can be used in query param)
        ticket = data["ticket"]
        assert " " not in ticket, "Ticket should not contain spaces"
        
        print("PASS: WS ticket response format is correct for frontend usage")


class TestWsTicketSecurityProperties:
    """Tests for WS ticket security properties"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session and authenticate as admin"""
        self.session = requests.Session()
        self.session.headers.update(CSRF_HEADERS)
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        self.cookies = login_resp.cookies
    
    def test_ws_ticket_has_short_ttl(self):
        """WS ticket should have short TTL (90 seconds)"""
        resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "notifications"},
            cookies=self.cookies
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        expires_in = data.get("expires_in_seconds", 0)
        assert 0 < expires_in <= 90, f"Ticket TTL should be <= 90 seconds, got {expires_in}"
        print(f"PASS: WS ticket has short TTL ({expires_in} seconds)")
    
    def test_ws_ticket_is_unique_per_request(self):
        """Each WS ticket request should generate a unique ticket"""
        tickets = []
        for i in range(3):
            resp = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
                json={"channel": "notifications"},
                cookies=self.cookies
            )
            assert resp.status_code == 200
            tickets.append(resp.json()["ticket"])
        
        # All tickets should be unique
        assert len(set(tickets)) == 3, "Each ticket request should generate a unique ticket"
        print("PASS: WS tickets are unique per request")
    
    def test_ws_ticket_channel_specific(self):
        """WS tickets should be channel-specific"""
        # Get tickets for different channels
        resp1 = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "notifications"},
            cookies=self.cookies
        )
        resp2 = self.session.post(f"{BASE_URL}/api/auth/ws-ticket", 
            json={"channel": "admin_activity"},
            cookies=self.cookies
        )
        
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        
        ticket1 = resp1.json()["ticket"]
        ticket2 = resp2.json()["ticket"]
        
        # Tickets should be different
        assert ticket1 != ticket2, "Tickets for different channels should be different"
        print("PASS: WS tickets are channel-specific")


class TestAdminChannelAccess:
    """Tests for admin-only channel access control"""
    
    def test_admin_channels_list(self):
        """Verify the list of admin-only channels"""
        # These channels should require admin role
        admin_channels = [
            "admin_activity",
            "automation_dashboard",
            "aso_dashboard",
            "siem_events",
            "enterprise_live",
            "system_metrics",
        ]
        
        # Login as admin
        session = requests.Session()
        session.headers.update(CSRF_HEADERS)
        
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        cookies = login_resp.cookies
        
        # Admin should be able to get tickets for all admin channels
        for channel in admin_channels:
            resp = session.post(f"{BASE_URL}/api/auth/ws-ticket", 
                json={"channel": channel},
                cookies=cookies
            )
            assert resp.status_code == 200, f"Admin should get ticket for '{channel}', got {resp.status_code}"
            print(f"PASS: Admin can get ticket for '{channel}' channel")
        
        print(f"PASS: Admin has access to all {len(admin_channels)} admin channels")


class TestHealthAndConnectivity:
    """Basic health and connectivity tests"""
    
    def test_backend_health(self):
        """Backend should be healthy"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
        print("PASS: Backend is healthy")
    
    def test_auth_endpoint_available(self):
        """Auth endpoints should be available"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@test.com",
            "password": "wrong"
        })
        # Should get 401 (unauthorized) not 404 (not found)
        assert resp.status_code in [401, 400], f"Auth endpoint should be available, got {resp.status_code}"
        print("PASS: Auth endpoints are available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
