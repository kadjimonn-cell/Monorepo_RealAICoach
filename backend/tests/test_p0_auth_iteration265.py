"""
P0 Auth Validation Tests - Iteration 265
=========================================
Tests P0 auth flows per locked protocol:
- Session persistence (login + /auth/me)
- Passkey/fingerprint readiness chain
- OTP request flow for example.com test domain
- Password reset request flow for example.com test domain
- Admin auth login + /auth/me
- No regression for core auth flows
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


class TestP0SessionPersistence:
    """P0: Session persistence - POST /api/auth/login then GET /api/auth/me remains authenticated"""

    def test_admin_login_and_session_persistence(self):
        """Admin login should return 200 and /auth/me should return user data with same session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"  # CSRF header
        })

        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        login_data = login_response.json()
        assert "user_id" in login_data, f"Missing user_id in login response: {login_data}"
        print(f"PASS: Admin login successful, user_id={login_data.get('user_id')}")

        # Verify session persistence with /auth/me
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, f"/auth/me failed: {me_response.text}"
        me_data = me_response.json()
        assert me_data.get("user_id") == login_data.get("user_id"), "Session user_id mismatch"
        assert me_data.get("email") == ADMIN_EMAIL, f"Email mismatch: {me_data.get('email')}"
        print(f"PASS: Session persistence verified, email={me_data.get('email')}")

    def test_free_user_login_and_session_persistence(self):
        """Free user (example.com) login should work and session should persist"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })

        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
        )
        # May return 200 (direct login) or 202 (OTP required)
        assert login_response.status_code in [200, 202], f"Free user login failed: {login_response.text}"
        login_data = login_response.json()
        print(f"PASS: Free user login response status={login_response.status_code}")

        if login_response.status_code == 200:
            # Direct login - verify session
            me_response = session.get(f"{BASE_URL}/api/auth/me")
            assert me_response.status_code == 200, f"/auth/me failed: {me_response.text}"
            me_data = me_response.json()
            assert me_data.get("email") == FREE_USER_EMAIL, f"Email mismatch: {me_data.get('email')}"
            print("PASS: Free user session persistence verified")
        else:
            # OTP required - this is expected behavior
            assert "otp_required" in login_data or "requires_otp" in login_data or login_data.get("status") == "otp_required", \
                f"Expected OTP required response: {login_data}"
            print("PASS: Free user login requires OTP (expected security behavior)")


class TestP0PasskeyReadinessChain:
    """P0: Passkey/fingerprint readiness chain endpoints"""

    @pytest.fixture(autouse=True)
    def setup_admin_session(self):
        """Setup authenticated admin session for passkey tests"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        self.user_id = login_response.json().get("user_id")

    def test_2fa_status_endpoint(self):
        """GET /api/auth/2fa/status should return 2FA configuration"""
        response = self.session.get(f"{BASE_URL}/api/auth/2fa/status")
        assert response.status_code == 200, f"2FA status failed: {response.text}"
        data = response.json()
        # Should have 2FA status fields
        assert "otp_enabled" in data or "has_passkey" in data or "biometric_enabled" in data, \
            f"Missing 2FA status fields: {data}"
        print(f"PASS: 2FA status endpoint working, data={data}")

    def test_geo_detect_endpoint(self):
        """GET /api/geo/detect should return geo detection (soft-fail fallback)"""
        response = self.session.get(f"{BASE_URL}/api/geo/detect")
        # Should return 200 even if geo detection fails (soft-fail)
        assert response.status_code == 200, f"Geo detect failed: {response.text}"
        data = response.json()
        assert "detected_country" in data, f"Missing detected_country: {data}"
        print(f"PASS: Geo detect endpoint working, country={data.get('detected_country')}")

    def test_webauthn_register_options_endpoint(self):
        """POST /api/auth/biometric/webauthn-register-options should return registration options"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-register-options",
            json={}
        )
        # Should return 200 with registration options or 400 if already registered
        assert response.status_code in [200, 400], f"WebAuthn register options failed: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert "challenge_id" in data or "options" in data or "publicKey" in data, \
                f"Missing WebAuthn options: {data}"
            print("PASS: WebAuthn register options endpoint working")
        else:
            print("PASS: WebAuthn register options returned 400 (may already have passkey)")

    def test_webauthn_credentials_list_endpoint(self):
        """GET /api/auth/biometric/webauthn/credentials should return credentials list"""
        response = self.session.get(f"{BASE_URL}/api/auth/biometric/webauthn/credentials")
        assert response.status_code == 200, f"WebAuthn credentials list failed: {response.text}"
        data = response.json()
        # Should return list (may be empty)
        assert "credentials" in data or isinstance(data, list), f"Unexpected response: {data}"
        print("PASS: WebAuthn credentials list endpoint working")


class TestP0OTPRequestFlow:
    """P0: OTP request flow for allowlisted non-production test domain example.com"""

    def test_otp_request_with_csrf_header(self):
        """POST /api/auth/otp/request with X-Requested-With header should return 200"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"  # Required CSRF header
        })

        response = session.post(
            f"{BASE_URL}/api/auth/otp/request",
            json={"email": FREE_USER_EMAIL}
        )
        # Should return 200 with OTP sent confirmation
        assert response.status_code == 200, f"OTP request failed: {response.text}"
        data = response.json()
        # Should indicate OTP was sent or success
        assert data.get("success") or "sent" in str(data).lower() or "otp" in str(data).lower(), \
            f"Unexpected OTP response: {data}"
        print("PASS: OTP request for example.com user successful")

    def test_otp_request_without_csrf_header_returns_403(self):
        """POST /api/auth/otp/request without X-Requested-With should return 403 (expected security)"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json"
            # No X-Requested-With header
        })

        response = session.post(
            f"{BASE_URL}/api/auth/otp/request",
            json={"email": FREE_USER_EMAIL}
        )
        # Should return 403 due to CSRF protection
        assert response.status_code == 403, f"Expected 403 without CSRF header, got {response.status_code}: {response.text}"
        print("PASS: OTP request without CSRF header correctly returns 403")


class TestP0PasswordResetFlow:
    """P0: Password reset request flow for allowlisted non-production test domain example.com"""

    def test_password_reset_request_with_csrf_header(self):
        """POST /api/auth/password/reset/request with X-Requested-With header should return 200"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })

        response = session.post(
            f"{BASE_URL}/api/auth/password/reset/request",
            json={"email": FREE_USER_EMAIL}
        )
        # Should return 200 with reset email sent confirmation
        assert response.status_code == 200, f"Password reset request failed: {response.text}"
        data = response.json()
        # Should indicate email was sent or success
        assert data.get("success") or "sent" in str(data).lower() or "email" in str(data).lower(), \
            f"Unexpected password reset response: {data}"
        print("PASS: Password reset request for example.com user successful")


class TestP0AdminAuthNoRegression:
    """P0: No regression for admin auth login + /api/auth/me"""

    def test_admin_full_auth_flow(self):
        """Admin should be able to login, access /auth/me, and logout"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })

        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.text}"
        login_data = login_response.json()
        assert login_data.get("is_admin") or login_data.get("role") == "admin", \
            f"Admin flag not set: {login_data}"
        print("PASS: Admin login successful with admin privileges")

        # Verify /auth/me
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, f"/auth/me failed: {me_response.text}"
        me_data = me_response.json()
        assert me_data.get("email") == ADMIN_EMAIL, f"Email mismatch: {me_data}"
        assert me_data.get("is_admin") or me_data.get("role") == "admin", \
            f"Admin flag not in /auth/me: {me_data}"
        print("PASS: Admin /auth/me returns correct data")

        # Logout
        logout_response = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200, f"Logout failed: {logout_response.text}"
        print("PASS: Admin logout successful")

        # Verify session is invalidated
        me_after_logout = session.get(f"{BASE_URL}/api/auth/me")
        assert me_after_logout.status_code == 401, f"Session should be invalidated after logout: {me_after_logout.status_code}"
        print("PASS: Session correctly invalidated after logout")


class TestP0CSRFMiddlewareBehavior:
    """P0: CSRF middleware behavior verification"""

    def test_login_exempt_from_csrf(self):
        """Login endpoint should be exempt from CSRF (no X-Requested-With needed)"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json"
            # No X-Requested-With header
        })

        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        # Login should work without CSRF header (exempt)
        assert response.status_code == 200, f"Login should be CSRF exempt: {response.text}"
        print("PASS: Login endpoint is CSRF exempt")

    def test_otp_request_requires_csrf(self):
        """OTP request should require CSRF header"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json"
            # No X-Requested-With header
        })

        response = session.post(
            f"{BASE_URL}/api/auth/otp/request",
            json={"email": FREE_USER_EMAIL}
        )
        # Should return 403 without CSRF header
        assert response.status_code == 403, f"OTP request should require CSRF: {response.status_code}"
        print("PASS: OTP request correctly requires CSRF header")


class TestP0HealthCheck:
    """P0: Basic health check to ensure API is accessible"""

    def test_health_endpoint(self):
        """Health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("PASS: Health endpoint accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
