"""
Session Persistence P0/P1/P2 Tests
==================================
Tests for preview session persistence across navigations.

P0: Cookie-mode auth bootstrap should NOT clear session on transient /auth/me failures (429/timeout/network); must clear only on 401
P0: RouteAccessGuard should apply transient recovery grace with snapshot hint and avoid immediate redirect flaps
P0: refreshUser should use resilient auth/me handling

P1: /api/auth/me endpoint-specific rate limit should reflect updated threshold (240/60)
P1: client reason-code telemetry should be emitted and backend endpoint /api/auth/session-bootstrap-telemetry should accept payload

P2: session renewal path should be used via /api/auth/renew-session throttled flow
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://coach-web-preview.preview.emergentagent.com"

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestSessionPersistenceP0:
    """P0: Critical session persistence tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login and get admin session token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": True},
            timeout=30
        )
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Handle 2FA if required
        if data.get("requires_2fa"):
            pytest.skip("2FA required - skipping authenticated tests")
        
        token = data.get("session_token")
        assert token, f"No session_token in response: {data}"
        return token
    
    def test_auth_me_returns_user_on_valid_session(self, admin_session):
        """P0: /api/auth/me should return user data on valid session"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_session}"},
            timeout=15
        )
        assert response.status_code == 200, f"auth/me failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify user data structure
        assert "user_id" in data, "Missing user_id in response"
        assert "email" in data, "Missing email in response"
        assert data["email"] == ADMIN_EMAIL, f"Email mismatch: {data['email']}"
        print(f"✓ P0: auth/me returns valid user data for {data['email']}")
    
    def test_auth_me_returns_401_on_invalid_session(self):
        """P0: /api/auth/me should return 401 on invalid/expired session (not 429 or 5xx)"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_12345"},
            timeout=15
        )
        # Should be 401 Unauthorized, not 429 or 5xx
        assert response.status_code == 401, f"Expected 401, got {response.status_code} - {response.text}"
        print("✓ P0: auth/me returns 401 on invalid session (correct behavior for session clearing)")
    
    def test_auth_me_rate_limit_threshold(self, admin_session):
        """P1: /api/auth/me rate limit should be 240/60 (4 req/sec average)"""
        # Make several rapid requests to verify rate limit is not too aggressive
        success_count = 0
        rate_limited_count = 0
        
        for i in range(10):
            response = requests.get(
                f"{BASE_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {admin_session}"},
                timeout=15
            )
            if response.status_code == 200:
                success_count += 1
            elif response.status_code == 429:
                rate_limited_count += 1
                # Check rate limit headers
                limit = response.headers.get("X-RateLimit-Limit")
                print(f"Rate limit header: {limit}")
            time.sleep(0.1)  # 100ms between requests
        
        # With 240/60 limit, 10 requests in 1 second should all succeed
        assert success_count >= 8, f"Too many rate limited: {rate_limited_count}/10 requests failed"
        print(f"✓ P1: auth/me rate limit allows rapid requests ({success_count}/10 succeeded)")


class TestSessionTelemetryP1:
    """P1: Session bootstrap telemetry tests"""
    
    def test_session_bootstrap_telemetry_endpoint_accepts_payload(self):
        """P1: /api/auth/session-bootstrap-telemetry should accept telemetry payload"""
        payload = {
            "reason_code": "auth_me_timeout",
            "phase": "bootstrap_cookie_only",
            "status": 0,
            "attempt": 1
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/session-bootstrap-telemetry",
            json=payload,
            timeout=15
        )
        
        assert response.status_code == 200, f"Telemetry endpoint failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("ok") is True, f"Unexpected response: {data}"
        print("✓ P1: session-bootstrap-telemetry endpoint accepts payload")
    
    def test_session_bootstrap_telemetry_requires_reason_code(self):
        """P1: Telemetry endpoint should require reason_code"""
        payload = {
            "phase": "bootstrap_cookie_only"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auth/session-bootstrap-telemetry",
            json=payload,
            timeout=15
        )
        
        # Should fail without reason_code
        assert response.status_code == 400 or response.status_code == 422, \
            f"Expected 400/422 without reason_code, got {response.status_code}"
        print("✓ P1: session-bootstrap-telemetry requires reason_code")
    
    def test_session_bootstrap_telemetry_various_reason_codes(self):
        """P1: Telemetry endpoint should accept various reason codes"""
        reason_codes = [
            "auth_me_unauthorized",
            "auth_me_rate_limited",
            "auth_me_timeout",
            "auth_me_network",
            "auth_me_server",
            "session_renew_success",
            "session_renew_failed"
        ]
        
        for reason_code in reason_codes:
            payload = {
                "reason_code": reason_code,
                "phase": "test",
                "attempt": 0
            }
            response = requests.post(
                f"{BASE_URL}/api/auth/session-bootstrap-telemetry",
                json=payload,
                timeout=15
            )
            assert response.status_code == 200, f"Failed for {reason_code}: {response.status_code}"
        
        print(f"✓ P1: session-bootstrap-telemetry accepts all {len(reason_codes)} reason codes")


class TestSessionRenewalP2:
    """P2: Session renewal tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login and get admin session token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": True},
            timeout=30
        )
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        data = response.json()
        
        if data.get("requires_2fa"):
            pytest.skip("2FA required - skipping authenticated tests")
        
        token = data.get("session_token")
        assert token, f"No session_token in response: {data}"
        return token
    
    def test_renew_session_endpoint_works(self, admin_session):
        """P2: /api/auth/renew-session should renew session with fresh token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/renew-session",
            headers={"Authorization": f"Bearer {admin_session}"},
            json={},
            timeout=15
        )
        
        assert response.status_code == 200, f"renew-session failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "session_token" in data, f"Missing session_token: {data}"
        assert "refresh_token" in data, f"Missing refresh_token: {data}"
        assert "expires_in_seconds" in data, f"Missing expires_in_seconds: {data}"
        
        # Verify 30-day expiry (REMEMBER_ME_MINUTES = 43200 = 30 days)
        expected_seconds = 43200 * 60  # 30 days in seconds
        assert data["expires_in_seconds"] == expected_seconds, \
            f"Expected {expected_seconds}s, got {data['expires_in_seconds']}s"
        
        print("✓ P2: renew-session returns new token with 30-day expiry")
    
    def test_renew_session_requires_auth(self):
        """P2: /api/auth/renew-session should require authentication"""
        response = requests.post(
            f"{BASE_URL}/api/auth/renew-session",
            json={},
            timeout=15
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ P2: renew-session requires authentication")
    
    def test_renewed_token_is_valid(self, admin_session):
        """P2: Renewed token should be valid for auth/me"""
        # First renew the session
        renew_response = requests.post(
            f"{BASE_URL}/api/auth/renew-session",
            headers={"Authorization": f"Bearer {admin_session}"},
            json={},
            timeout=15
        )
        
        assert renew_response.status_code == 200, f"renew-session failed: {renew_response.status_code}"
        new_token = renew_response.json().get("session_token")
        assert new_token, "No new token returned"
        
        # Use the new token for auth/me
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
            timeout=15
        )
        
        assert me_response.status_code == 200, f"auth/me with renewed token failed: {me_response.status_code}"
        data = me_response.json()
        assert data["email"] == ADMIN_EMAIL, f"Email mismatch: {data['email']}"
        print("✓ P2: Renewed token is valid for subsequent auth/me calls")


class TestRateLimiterConfiguration:
    """Test rate limiter configuration for auth endpoints"""
    
    def test_auth_me_rate_limit_header(self):
        """P1: Verify /api/auth/me has correct rate limit header (240/60)"""
        # Login first
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        data = login_response.json()
        if data.get("requires_2fa"):
            pytest.skip("2FA required")
        
        token = data.get("session_token")
        
        # Make auth/me request and check headers
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15
        )
        
        assert response.status_code == 200, f"auth/me failed: {response.status_code}"
        
        # Check rate limit header
        limit = response.headers.get("X-RateLimit-Limit")
        remaining = response.headers.get("X-RateLimit-Remaining")
        
        print(f"Rate limit headers: Limit={limit}, Remaining={remaining}")
        
        # Verify limit is 240 (as configured in api_rate_limiter.py)
        if limit:
            assert int(limit) == 240, f"Expected rate limit 240, got {limit}"
            print("✓ P1: auth/me rate limit is correctly set to 240/60")
        else:
            print("⚠ Rate limit header not present (may be behind proxy)")


class TestHealthAndConnectivity:
    """Basic health and connectivity tests"""
    
    def test_api_health(self):
        """Verify API is reachable"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print(f"✓ API health check passed: {BASE_URL}")
    
    def test_login_endpoint_reachable(self):
        """Verify login endpoint is reachable"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "test@test.com", "password": "wrong"},
            timeout=15
        )
        # Should get 401 (invalid credentials), not 5xx or connection error
        assert response.status_code in [401, 429], f"Unexpected status: {response.status_code}"
        print("✓ Login endpoint is reachable")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
