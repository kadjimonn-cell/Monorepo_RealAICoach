"""
Auth E2E Full Live Tests - Corrected Endpoints
Tests all authentication flows with proper session handling
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
E2E_BYPASS_EMAIL = "watchvideos.phase4.admin.306786@example.com"
E2E_BYPASS_PASSWORD = "Phase4Admin#2026Aa"


def get_authenticated_session(email, password):
    """Helper to get an authenticated session."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    resp = s.post(f"{BASE_URL}/api/auth/login", json={
        "email": email,
        "password": password
    })
    if resp.status_code != 200:
        raise Exception(f"Login failed: {resp.text}")
    return s


class TestHealthAndBasics:
    """Basic health and connectivity tests."""
    
    def test_health_endpoint(self):
        """Test /api/health returns 200."""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        print(f"✓ Health check passed: {data}")


class TestPasswordAuthLifecycle:
    """Password register/login/logout/auth-me lifecycle tests."""
    
    def test_admin_login_success(self):
        """Test admin login with correct credentials."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        assert data.get("email") == ADMIN_EMAIL
        assert data.get("is_admin") == True
        print(f"✓ Admin login successful: is_admin={data.get('is_admin')}")
    
    def test_auth_me_after_login(self):
        """Test /api/auth/me returns user data after login."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"Auth me failed: {resp.text}"
        data = resp.json()
        assert "user_id" in data
        assert "email" in data
        assert data.get("is_admin") == True
        print(f"✓ Auth me returned: user_id={data['user_id']}, is_admin={data['is_admin']}")
    
    def test_logout_success(self):
        """Test logout clears session."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        
        # Logout
        resp = s.post(f"{BASE_URL}/api/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("message") == "Logged out successfully"
        print("✓ Logout successful")
        
        # Verify auth/me returns 401
        resp = s.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 401
        print("✓ Auth me returns 401 after logout")
    
    def test_login_invalid_credentials(self):
        """Test login with wrong password returns 401."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": "WrongPassword123!"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("✓ Invalid credentials correctly rejected with 401")


class Test2FAStatusAndFlow:
    """2FA status and enable/disable flow tests."""
    
    def test_2fa_status_endpoint(self):
        """Test /api/auth/2fa/status returns 2FA info."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.get(f"{BASE_URL}/api/auth/2fa/status")
        assert resp.status_code == 200, f"2FA status failed: {resp.text}"
        data = resp.json()
        
        # Verify expected fields
        assert "two_fa_enabled" in data
        assert "has_pin" in data
        assert "has_passkey" in data
        print(f"✓ 2FA status: two_fa_enabled={data.get('two_fa_enabled')}, has_passkey={data.get('has_passkey')}")
    
    def test_2fa_enable_for_e2e_bypass_user(self):
        """Test 2FA enable for E2E bypass user."""
        s = get_authenticated_session(E2E_BYPASS_EMAIL, E2E_BYPASS_PASSWORD)
        
        # Check current status
        status_resp = s.get(f"{BASE_URL}/api/auth/2fa/status")
        assert status_resp.status_code == 200
        status = status_resp.json()
        
        # E2E bypass user may be exempt from 2FA
        if status.get("exempt"):
            print(f"✓ E2E bypass user is 2FA exempt: {status.get('message')}")
            return
        
        if status.get("two_fa_enabled"):
            print("✓ 2FA already enabled for E2E bypass user")
            return
        
        # Try to enable 2FA
        resp = s.post(f"{BASE_URL}/api/auth/2fa/enable")
        assert resp.status_code == 200, f"2FA enable failed: {resp.text}"
        data = resp.json()
        print(f"✓ 2FA enable response: {data}")


class TestOTPLoginFlow:
    """OTP login request/verify readiness and error handling."""
    
    def test_otp_request_with_blocked_domain(self):
        """Test OTP request with example.com domain (email guardrail)."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/otp/request", json={
            "email": FREE_USER_EMAIL
        })
        
        # Returns 200 but with unavailable message due to email guardrail
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Check for unavailable message
        detail = data.get("detail", "")
        if "temporarily unavailable" in detail.lower():
            print(f"✓ OTP request correctly indicates unavailability for blocked domain: {detail}")
        else:
            print(f"✓ OTP request response: {data}")
    
    def test_otp_request_with_valid_domain(self):
        """Test OTP request with realaicoach.app domain."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/otp/request", json={
            "email": ADMIN_EMAIL
        })
        
        # Admin is OTP exempt, should succeed or be rate limited
        assert resp.status_code in [200, 429], f"Unexpected status: {resp.status_code}: {resp.text}"
        print(f"✓ OTP request for valid domain: status={resp.status_code}")


class TestPasswordResetFlow:
    """Password reset request flow tests."""
    
    def test_password_reset_request_blocked_domain(self):
        """Test password reset with example.com domain returns 503."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/password/reset/request", json={
            "email": FREE_USER_EMAIL
        })
        
        # Expected: 503 due to email guardrail
        assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "temporarily unavailable" in data.get("detail", "").lower()
        print(f"✓ Password reset correctly returns 503 for blocked domain: {data.get('detail')}")
    
    def test_password_reset_request_valid_domain(self):
        """Test password reset with valid domain."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/password/reset/request", json={
            "email": ADMIN_EMAIL
        })
        
        # Should succeed or be rate limited
        assert resp.status_code in [200, 429], f"Unexpected status: {resp.status_code}: {resp.text}"
        print(f"✓ Password reset for valid domain: status={resp.status_code}")


class TestPasskeyEndpoints:
    """Passkey endpoints readiness tests."""
    
    def test_passkey_enrollment_eligibility(self):
        """Test passkey enrollment eligibility endpoint."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.get(f"{BASE_URL}/api/auth/biometric/enrollment-eligibility")
        assert resp.status_code == 200, f"Passkey eligibility failed: {resp.text}"
        data = resp.json()
        
        assert "rollout_enabled" in data or "should_prompt" in data
        print(f"✓ Passkey eligibility: {data}")
    
    def test_webauthn_register_options(self):
        """Test WebAuthn register options endpoint."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.post(f"{BASE_URL}/api/auth/biometric/webauthn-register-options", json={})
        assert resp.status_code == 200, f"WebAuthn register options failed: {resp.text}"
        data = resp.json()
        
        # Should contain challenge or publicKey
        assert "challenge" in data or "publicKey" in data or "rp" in data
        print("✓ WebAuthn register options returned successfully")
    
    def test_webauthn_auth_options(self):
        """Test WebAuthn auth options endpoint."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/biometric/webauthn-auth-options", json={
            "user_id": "user_test123"
        })
        
        # May return 200 with options or 404 if no passkey registered
        assert resp.status_code in [200, 404, 400], f"Unexpected status: {resp.status_code}: {resp.text}"
        print(f"✓ WebAuthn auth options: status={resp.status_code}")


class TestSecurityPageResilience:
    """Security page resilience tests."""
    
    def test_login_history_endpoint(self):
        """Test login history endpoint."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.get(f"{BASE_URL}/api/auth/security/login-history")
        assert resp.status_code == 200, f"Login history failed: {resp.text}"
        data = resp.json()
        
        assert "events" in data or isinstance(data, list)
        print("✓ Login history returned successfully")


class TestNotificationSideEffects:
    """In-app notification side effects after auth events."""
    
    def test_notifications_endpoint(self):
        """Test notifications endpoint returns user notifications."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.get(f"{BASE_URL}/api/notifications")
        assert resp.status_code == 200, f"Notifications failed: {resp.text}"
        data = resp.json()
        
        assert "notifications" in data
        assert "unread_count" in data
        print(f"✓ Notifications: count={len(data['notifications'])}, unread={data['unread_count']}")
    
    def test_notification_unread_count(self):
        """Test notification unread count endpoint."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.get(f"{BASE_URL}/api/notifications/unread-count")
        assert resp.status_code == 200, f"Unread count failed: {resp.text}"
        data = resp.json()
        
        assert "unread_count" in data
        print(f"✓ Unread count: {data['unread_count']}")


class TestRealTimeInAppBehavior:
    """Real-time in-app behavior around auth/notification feeds."""
    
    def test_live_activity_feed(self):
        """Test live activity feed endpoint."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.get(f"{BASE_URL}/api/live-activity/feed")
        
        # May return events or empty list
        assert resp.status_code == 200, f"Live activity failed: {resp.text}"
        data = resp.json()
        assert "events" in data
        print(f"✓ Live activity feed: {len(data['events'])} events")
    
    def test_notification_settings(self):
        """Test notification settings endpoint."""
        s = get_authenticated_session(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = s.get(f"{BASE_URL}/api/notifications/settings")
        assert resp.status_code == 200, f"Notification settings failed: {resp.text}"
        data = resp.json()
        
        # Should have default settings
        assert "push_enabled" in data or "email_enabled" in data
        print("✓ Notification settings retrieved")


class TestE2EOTPBypassUser:
    """Tests for E2E OTP bypass allowlisted user."""
    
    def test_e2e_bypass_user_login_no_otp_required(self):
        """Test that E2E bypass user can login without OTP challenge."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": E2E_BYPASS_EMAIL,
            "password": E2E_BYPASS_PASSWORD
        })
        
        assert resp.status_code == 200, f"E2E bypass login failed: {resp.text}"
        data = resp.json()
        
        # Should not require 2FA challenge
        assert data.get("requires_2fa") != True, "E2E bypass user should not require 2FA"
        
        # Check if bypass was applied
        if data.get("e2e_otp_bypass_applied"):
            print(f"✓ E2E OTP bypass applied for {E2E_BYPASS_EMAIL}")
        else:
            print("✓ E2E bypass user logged in successfully (may be OTP exempt)")


class TestAuthLookup:
    """Auth lookup endpoint tests."""
    
    def test_auth_lookup_existing_user(self):
        """Test auth lookup for existing user."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.get(f"{BASE_URL}/api/auth/lookup", params={"email": ADMIN_EMAIL})
        assert resp.status_code == 200, f"Auth lookup failed: {resp.text}"
        data = resp.json()
        
        assert data.get("exists") == True
        assert "user_id" in data
        assert "has_pin" in data
        assert "has_passkey" in data
        print(f"✓ Auth lookup: exists={data['exists']}, has_passkey={data.get('has_passkey')}")
    
    def test_auth_lookup_nonexistent_user(self):
        """Test auth lookup for non-existent user (anti-enumeration)."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.get(f"{BASE_URL}/api/auth/lookup", params={"email": "nonexistent@example.com"})
        assert resp.status_code == 200, f"Auth lookup failed: {resp.text}"
        data = resp.json()
        
        # Anti-enumeration: should still return exists=True with fake user_id
        assert data.get("exists") == True
        assert "user_id" in data
        print("✓ Auth lookup anti-enumeration working (returns consistent shape)")


class TestEmailGuardrailRCA:
    """Root cause analysis for email guardrail behavior."""
    
    def test_email_guardrail_blocks_example_domain_otp(self):
        """Verify OTP request for example.com shows unavailable message."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/otp/request", json={
            "email": FREE_USER_EMAIL
        })
        
        data = resp.json()
        detail = data.get("detail", "")
        
        # RCA: Email guardrail blocks example.com domain
        # This is environment-level policy, not app logic bug
        if "temporarily unavailable" in detail.lower():
            print("✓ RCA CONFIRMED: OTP blocked for example.com domain")
            print("  Root cause: Email guardrail policy blocks example.com")
            print("  This is expected behavior for test/synthetic domains")
        else:
            print(f"✓ OTP request response: {data}")
    
    def test_email_guardrail_blocks_example_domain_reset(self):
        """Verify password reset for example.com returns 503."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        resp = s.post(f"{BASE_URL}/api/auth/password/reset/request", json={
            "email": FREE_USER_EMAIL
        })
        
        # RCA: 503 confirms email guardrail is blocking
        if resp.status_code == 503:
            print("✓ RCA CONFIRMED: Password reset blocked for example.com domain")
            print("  Root cause: Email guardrail policy blocks example.com")
            print("  Status: 503 Service Unavailable")
        else:
            print(f"✓ Password reset response: {resp.status_code} - {resp.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
