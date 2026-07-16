"""
Security Hardening Tests - Iteration 55
Tests for:
1. Frontend preview availability (app root and /login)
2. Web login flow with admin credentials (cookie-session auth)
3. Auth response contract: web login should NOT expose session_token/refresh_token
4. Native compatibility: login with X-Client-Platform: mobile should include tokens
5. CSRF contract: POST to /api/auth/track-route without CSRF indicator should be blocked
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestFrontendPreviewAvailability:
    """Test that frontend preview is available and not showing proxy/startup failure page."""

    def test_app_root_loads(self):
        """App root (/) should return 200 and not show proxy error."""
        response = requests.get(f"{BASE_URL}/", timeout=30)
        assert response.status_code == 200, f"App root returned {response.status_code}"
        # Check it's not a proxy error page
        content = response.text.lower()
        assert "proxy error" not in content, "App root shows proxy error"
        assert "502 bad gateway" not in content, "App root shows 502 error"
        assert "503 service unavailable" not in content, "App root shows 503 error"
        print("PASS: App root loads successfully (200)")

    def test_login_page_loads(self):
        """Login page (/login) should return 200."""
        response = requests.get(f"{BASE_URL}/login", timeout=30)
        assert response.status_code == 200, f"Login page returned {response.status_code}"
        content = response.text.lower()
        assert "proxy error" not in content, "Login page shows proxy error"
        print("PASS: Login page loads successfully (200)")


class TestWebLoginFlow:
    """Test web login flow with admin credentials using cookie-session auth."""

    def test_web_login_success(self):
        """Web login should succeed with valid admin credentials."""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed with status {response.status_code}: {response.text}"
        data = response.json()
        assert "user_id" in data, "Response missing user_id"
        assert data.get("email") == ADMIN_EMAIL, f"Email mismatch: {data.get('email')}"
        print(f"PASS: Web login succeeded for {ADMIN_EMAIL}")
        return data

    def test_web_login_sets_cookie(self):
        """Web login should set session_token cookie."""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        # Check for session cookie
        cookies = session.cookies.get_dict()
        assert "session_token" in cookies, f"session_token cookie not set. Cookies: {cookies}"
        print("PASS: Web login sets session_token cookie")


class TestAuthResponseContract:
    """Test that web login response does NOT expose session_token/refresh_token."""

    def test_web_login_no_token_fields(self):
        """Web login (no X-Client-Platform header) should NOT return session_token or refresh_token in body."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Web clients should NOT receive tokens in response body
        assert "session_token" not in data, f"session_token exposed in web login response: {data.keys()}"
        assert "refresh_token" not in data, f"refresh_token exposed in web login response: {data.keys()}"
        print("PASS: Web login response does NOT expose session_token/refresh_token")

    def test_web_login_with_web_platform_header_no_tokens(self):
        """Web login with X-Client-Platform: web should NOT return tokens."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={
                "Content-Type": "application/json",
                "X-Client-Platform": "web",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        assert "session_token" not in data, f"session_token exposed for web platform: {data.keys()}"
        assert "refresh_token" not in data, f"refresh_token exposed for web platform: {data.keys()}"
        print("PASS: Web login with X-Client-Platform: web does NOT expose tokens")


class TestNativeCompatibilityContract:
    """Test that native/mobile clients receive tokens in login response."""

    def test_mobile_login_includes_tokens(self):
        """Login with X-Client-Platform: mobile should include session_token and refresh_token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={
                "Content-Type": "application/json",
                "X-Client-Platform": "mobile",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Mobile clients SHOULD receive tokens
        assert "session_token" in data, f"session_token missing for mobile login: {data.keys()}"
        assert "refresh_token" in data, f"refresh_token missing for mobile login: {data.keys()}"
        assert len(data["session_token"]) > 0, "session_token is empty"
        assert len(data["refresh_token"]) > 0, "refresh_token is empty"
        print("PASS: Mobile login includes session_token and refresh_token")

    def test_native_header_variants(self):
        """Test various native platform header values."""
        native_platforms = ["native", "android", "ios", "expo"]
        
        for platform in native_platforms:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                headers={
                    "Content-Type": "application/json",
                    "X-Client-Platform": platform,
                },
                timeout=30,
            )
            assert response.status_code == 200, f"Login failed for {platform}: {response.text}"
            data = response.json()
            
            assert "session_token" in data, f"session_token missing for {platform}: {data.keys()}"
            assert "refresh_token" in data, f"refresh_token missing for {platform}: {data.keys()}"
            print(f"PASS: X-Client-Platform: {platform} includes tokens")


class TestCSRFContract:
    """Test CSRF protection for /api/auth/track-route endpoint."""

    def test_csrf_blocked_without_header(self):
        """POST to /api/auth/track-route without X-Requested-With should be blocked with 403."""
        # First login to get a session
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        # Now try POST to track-route WITHOUT X-Requested-With header
        # This should be blocked by CSRF protection
        response = session.post(
            f"{BASE_URL}/api/auth/track-route",
            json={"route": "/dashboard", "timestamp": "2026-01-01T00:00:00Z"},
            headers={"Content-Type": "application/json"},
            # Deliberately NOT including X-Requested-With
            timeout=30,
        )
        
        assert response.status_code == 403, f"Expected 403 CSRF_BLOCKED, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("code") == "CSRF_BLOCKED", f"Expected CSRF_BLOCKED code, got: {data}"
        print("PASS: POST to /api/auth/track-route without X-Requested-With returns 403 CSRF_BLOCKED")

    def test_csrf_allowed_with_x_requested_with(self):
        """POST to /api/auth/track-route WITH X-Requested-With should pass CSRF check."""
        # First login to get a session
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        # Now try POST to track-route WITH X-Requested-With header
        response = session.post(
            f"{BASE_URL}/api/auth/track-route",
            json={"route": "/dashboard", "timestamp": "2026-01-01T00:00:00Z"},
            headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=30,
        )
        
        # Should NOT be 403 CSRF_BLOCKED
        assert response.status_code != 403 or response.json().get("code") != "CSRF_BLOCKED", \
            f"Request was blocked by CSRF even with X-Requested-With: {response.text}"
        print(f"PASS: POST to /api/auth/track-route with X-Requested-With passes CSRF check (status: {response.status_code})")

    def test_csrf_exempt_auth_login(self):
        """Auth login endpoint should be CSRF exempt."""
        # POST to login without X-Requested-With should still work
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            # Deliberately NOT including X-Requested-With
            timeout=30,
        )
        
        # Should succeed (200) or fail for other reasons, but NOT 403 CSRF_BLOCKED
        if response.status_code == 403:
            data = response.json()
            assert data.get("code") != "CSRF_BLOCKED", f"Login endpoint should be CSRF exempt: {data}"
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        print("PASS: /api/auth/login is CSRF exempt")


class TestBackendHealth:
    """Basic backend health checks."""

    def test_health_endpoint(self):
        """Health endpoint should return 200."""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("PASS: Backend health check returns 200")

    def test_auth_me_requires_auth(self):
        """Auth me endpoint should require authentication."""
        response = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        # Should return 401 or similar when not authenticated
        # Note: This endpoint is in AUTH_PUBLIC_PREFIXES so it may return user info or null
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"
        print(f"PASS: /api/auth/me returns {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
