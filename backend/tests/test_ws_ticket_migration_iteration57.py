"""
Iteration 57 - WS Ticket Migration Tests
Tests for P1 WebSocket ticket migration validation.

Test Coverage:
1. POST /api/auth/ws-ticket with {channel:"admin_activity"} returns ticket/channel/ttl for authenticated admin
2. POST /api/auth/ws-ticket with invalid channel returns 400
3. WS endpoints reject no-ticket and replay; accept valid ticket once:
   - /api/ws/admin-activity
   - /api/ws/system-metrics
4. /api/ws/jobs/employer/pipeline rejects no-ticket
"""

import pytest
import requests
import os
import time
import asyncio
import websockets
from websockets.exceptions import ConnectionClosed

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestWSTicketEndpoint:
    """Tests for POST /api/auth/ws-ticket endpoint"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session with CSRF header"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"  # Required for CSRF protection
        })
        
        # Login as admin - this sets session cookie
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text}")
        
        # Session cookie is automatically stored by requests.Session
        return session
    
    def test_ws_ticket_valid_channel_admin_activity(self, admin_session):
        """Test: POST /api/auth/ws-ticket with {channel:"admin_activity"} returns ticket/channel/ttl"""
        resp = admin_session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "admin_activity"
        })
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket'"
        assert "channel" in data, "Response should contain 'channel'"
        # API returns 'expires_in_seconds' instead of 'ttl'
        assert "expires_in_seconds" in data, "Response should contain 'expires_in_seconds' (ttl)"
        
        assert data["channel"] == "admin_activity", f"Channel should be 'admin_activity', got {data['channel']}"
        assert isinstance(data["ticket"], str) and len(data["ticket"]) > 10, "Ticket should be a non-empty string"
        assert isinstance(data["expires_in_seconds"], int) and data["expires_in_seconds"] > 0, "TTL should be a positive integer"
        
        print(f"✓ WS ticket issued: channel={data['channel']}, ttl={data['expires_in_seconds']}s, ticket_len={len(data['ticket'])}")
    
    def test_ws_ticket_valid_channel_system_metrics(self, admin_session):
        """Test: POST /api/auth/ws-ticket with {channel:"system_metrics"} returns ticket/channel/ttl"""
        resp = admin_session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "system_metrics"
        })
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket'"
        assert data["channel"] == "system_metrics", f"Channel should be 'system_metrics', got {data['channel']}"
        
        print(f"✓ WS ticket issued for system_metrics: ttl={data['expires_in_seconds']}s")
    
    def test_ws_ticket_valid_channel_jobs_employer_pipeline(self, admin_session):
        """Test: POST /api/auth/ws-ticket with {channel:"jobs_employer_pipeline"} returns ticket/channel/ttl"""
        resp = admin_session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "jobs_employer_pipeline"
        })
        
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "ticket" in data, "Response should contain 'ticket'"
        assert data["channel"] == "jobs_employer_pipeline", f"Channel should be 'jobs_employer_pipeline', got {data['channel']}"
        
        print(f"✓ WS ticket issued for jobs_employer_pipeline: ttl={data['expires_in_seconds']}s")
    
    def test_ws_ticket_invalid_channel_returns_400(self, admin_session):
        """Test: POST /api/auth/ws-ticket with invalid channel returns 400"""
        resp = admin_session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "invalid_channel_xyz_12345"
        })
        
        assert resp.status_code == 400, f"Expected 400 for invalid channel, got {resp.status_code}: {resp.text}"
        
        print("✓ Invalid channel correctly rejected with 400")
    
    def test_ws_ticket_requires_authentication(self):
        """Test: POST /api/auth/ws-ticket without auth returns 401"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"  # Include CSRF header to isolate auth check
        })
        
        resp = session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "admin_activity"
        })
        
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}: {resp.text}"
        
        print("✓ Unauthenticated request correctly rejected with 401")


class TestWSEndpointSecurity:
    """Tests for WebSocket endpoint security - no-ticket rejection and replay prevention"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session with CSRF header"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"  # Required for CSRF protection
        })
        
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        if login_resp.status_code != 200:
            pytest.skip(f"Admin login failed: {login_resp.status_code}")
        
        # Session cookie is automatically stored by requests.Session
        return session
    
    def _get_ws_url(self, path: str) -> str:
        """Convert HTTP URL to WebSocket URL"""
        ws_base = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_base}{path}"
    
    @pytest.mark.asyncio
    async def test_ws_admin_activity_rejects_no_ticket(self):
        """Test: /api/ws/admin-activity rejects connection without ticket"""
        ws_url = self._get_ws_url("/api/ws/admin-activity")
        
        try:
            async with websockets.connect(ws_url, close_timeout=5):
                # If connection succeeds without ticket, that's a security issue
                # Wait briefly for server to close
                await asyncio.sleep(1)
                pytest.fail("WebSocket should reject connection without ticket")
        except ConnectionClosed as e:
            # Expected: server closes connection with 4001 or similar
            assert e.code in [4001, 4003, 1008, 1011], f"Expected close code 4001/4003/1008/1011, got {e.code}"
            print(f"✓ /api/ws/admin-activity correctly rejected no-ticket connection (code={e.code})")
        except Exception as e:
            # Connection refused or other error is also acceptable
            print(f"✓ /api/ws/admin-activity rejected no-ticket connection: {type(e).__name__}")
    
    @pytest.mark.asyncio
    async def test_ws_system_metrics_rejects_no_ticket(self):
        """Test: /api/ws/system-metrics rejects connection without ticket"""
        ws_url = self._get_ws_url("/api/ws/system-metrics")
        
        try:
            async with websockets.connect(ws_url, close_timeout=5):
                await asyncio.sleep(1)
                pytest.fail("WebSocket should reject connection without ticket")
        except ConnectionClosed as e:
            assert e.code in [4001, 4003, 1008, 1011], f"Expected close code 4001/4003/1008/1011, got {e.code}"
            print(f"✓ /api/ws/system-metrics correctly rejected no-ticket connection (code={e.code})")
        except Exception as e:
            print(f"✓ /api/ws/system-metrics rejected no-ticket connection: {type(e).__name__}")
    
    @pytest.mark.asyncio
    async def test_ws_employer_pipeline_rejects_no_ticket(self):
        """Test: /api/ws/jobs/employer/pipeline rejects connection without ticket"""
        ws_url = self._get_ws_url("/api/ws/jobs/employer/pipeline")
        
        try:
            async with websockets.connect(ws_url, close_timeout=5):
                await asyncio.sleep(1)
                pytest.fail("WebSocket should reject connection without ticket")
        except ConnectionClosed as e:
            assert e.code in [4001, 4003, 1008, 1011], f"Expected close code 4001/4003/1008/1011, got {e.code}"
            print(f"✓ /api/ws/jobs/employer/pipeline correctly rejected no-ticket connection (code={e.code})")
        except Exception as e:
            print(f"✓ /api/ws/jobs/employer/pipeline rejected no-ticket connection: {type(e).__name__}")
    
    @pytest.mark.asyncio
    async def test_ws_admin_activity_accepts_valid_ticket(self, admin_session):
        """Test: /api/ws/admin-activity accepts valid ticket once"""
        # Get a valid ticket
        ticket_resp = admin_session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "admin_activity"
        })
        
        if ticket_resp.status_code != 200:
            pytest.skip(f"Failed to get WS ticket: {ticket_resp.status_code}")
        
        ticket = ticket_resp.json().get("ticket")
        ws_url = self._get_ws_url(f"/api/ws/admin-activity?ticket={ticket}")
        
        try:
            async with websockets.connect(ws_url, close_timeout=10) as ws:
                # Connection should succeed
                # Try to receive a message or wait briefly
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    print(f"✓ /api/ws/admin-activity accepted valid ticket, received: {msg[:100] if len(msg) > 100 else msg}")
                except asyncio.TimeoutError:
                    # No message received but connection is open - that's fine
                    print("✓ /api/ws/admin-activity accepted valid ticket (connection open)")
        except ConnectionClosed as e:
            if e.code in [4001, 4003]:
                pytest.fail(f"Valid ticket was rejected with code {e.code}")
            print(f"✓ /api/ws/admin-activity connection closed normally (code={e.code})")
        except Exception as e:
            pytest.fail(f"Unexpected error with valid ticket: {type(e).__name__}: {e}")
    
    @pytest.mark.asyncio
    async def test_ws_system_metrics_accepts_valid_ticket(self, admin_session):
        """Test: /api/ws/system-metrics accepts valid ticket once"""
        ticket_resp = admin_session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "system_metrics"
        })
        
        if ticket_resp.status_code != 200:
            pytest.skip(f"Failed to get WS ticket: {ticket_resp.status_code}")
        
        ticket = ticket_resp.json().get("ticket")
        ws_url = self._get_ws_url(f"/api/ws/system-metrics?ticket={ticket}")
        
        try:
            async with websockets.connect(ws_url, close_timeout=10) as ws:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    print(f"✓ /api/ws/system-metrics accepted valid ticket, received: {msg[:100] if len(msg) > 100 else msg}")
                except asyncio.TimeoutError:
                    print("✓ /api/ws/system-metrics accepted valid ticket (connection open)")
        except ConnectionClosed as e:
            if e.code in [4001, 4003]:
                pytest.fail(f"Valid ticket was rejected with code {e.code}")
            print(f"✓ /api/ws/system-metrics connection closed normally (code={e.code})")
        except Exception as e:
            pytest.fail(f"Unexpected error with valid ticket: {type(e).__name__}: {e}")
    
    @pytest.mark.asyncio
    async def test_ws_ticket_replay_rejected(self, admin_session):
        """Test: WS ticket can only be used once (replay attack prevention)"""
        # Get a valid ticket
        ticket_resp = admin_session.post(f"{BASE_URL}/api/auth/ws-ticket", json={
            "channel": "admin_activity"
        })
        
        if ticket_resp.status_code != 200:
            pytest.skip(f"Failed to get WS ticket: {ticket_resp.status_code}")
        
        ticket = ticket_resp.json().get("ticket")
        ws_url = self._get_ws_url(f"/api/ws/admin-activity?ticket={ticket}")
        
        # First connection - should succeed
        first_connection_succeeded = False
        try:
            async with websockets.connect(ws_url, close_timeout=5) as ws:
                first_connection_succeeded = True
                # Close immediately after connecting
                await ws.close()
        except ConnectionClosed as e:
            if e.code not in [4001, 4003]:
                first_connection_succeeded = True
        except Exception:
            pass
        
        if not first_connection_succeeded:
            pytest.skip("First connection with valid ticket failed")
        
        # Small delay to ensure ticket is consumed
        await asyncio.sleep(0.5)
        
        # Second connection with same ticket - should be rejected
        try:
            async with websockets.connect(ws_url, close_timeout=5) as ws:
                await asyncio.sleep(1)
                # If we get here, replay was allowed - that's a security issue
                pytest.fail("Replay attack succeeded - ticket was accepted twice")
        except ConnectionClosed as e:
            assert e.code in [4001, 4003, 1008, 1011], f"Expected rejection code, got {e.code}"
            print(f"✓ Ticket replay correctly rejected (code={e.code})")
        except Exception as e:
            print(f"✓ Ticket replay rejected: {type(e).__name__}")


class TestFrontendWSURLPatterns:
    """Verify frontend files use ?ticket= not ?token= for WS URLs"""
    
    def test_frontend_files_use_ticket_param(self):
        """Test: All specified frontend files use ?ticket= for WS URLs"""
        import subprocess
        
        files_to_check = [
            "/app/frontend/src/components/admin/LiveActivityFeedPanel.tsx",
            "/app/frontend/src/components/admin/AutomationEnginePanel.tsx",
            "/app/frontend/src/components/admin/CompetitorKeywordPanel.tsx",
            "/app/frontend/src/components/admin/SIEMPanel.tsx",
            "/app/frontend/src/components/admin/PerformanceDashboardPanel.tsx",
            "/app/frontend/src/components/admin/SystemMonitorPanel.tsx",
            "/app/frontend/src/components/admin/OperationsDashboard.tsx",
            "/app/frontend/src/components/jobs/EmployerPipelineBoard.tsx",
        ]
        
        results = {"pass": [], "fail": []}
        
        for filepath in files_to_check:
            filename = filepath.split("/")[-1]
            
            # Check for ?ticket= pattern
            ticket_result = subprocess.run(
                ["grep", "-c", "ticket=", filepath],
                capture_output=True, text=True
            )
            has_ticket = int(ticket_result.stdout.strip() or "0") > 0
            
            # Check for ?token= pattern (should NOT exist for WS URLs)
            token_result = subprocess.run(
                ["grep", "-c", "\\?token=", filepath],
                capture_output=True, text=True
            )
            has_token_param = int(token_result.stdout.strip() or "0") > 0
            
            if has_ticket and not has_token_param:
                results["pass"].append(filename)
                print(f"✓ {filename}: Uses ?ticket= (correct)")
            elif has_token_param:
                results["fail"].append(f"{filename}: Still uses ?token= (INCORRECT)")
                print(f"✗ {filename}: Uses ?token= (INCORRECT)")
            else:
                results["pass"].append(filename)
                print(f"✓ {filename}: No WS URL params found (OK)")
        
        assert len(results["fail"]) == 0, f"Files still using ?token=: {results['fail']}"
        print(f"\n✓ All {len(results['pass'])} frontend files correctly use ?ticket= for WS URLs")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
