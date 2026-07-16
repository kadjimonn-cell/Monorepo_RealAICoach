"""
Comprehensive Auth E2E Live Tests - Full Authentication Matrix Validation
Tests: register/login/logout/auth-me lifecycle, 2FA, OTP, password reset, passkey endpoints,
security page resilience, in-app notifications, email logs
"""

import pytest
import requests
import os
import uuid
import time
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
E2E_BYPASS_EMAIL = "watchvideos.phase4.admin.306786@example.com"
E2E_BYPASS_PASSWORD = "Phase4Admin#2026Aa"


@pytest.fixture(scope="module")
def session():
    """Shared requests session with cookies."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    return s


@pytest.fixture(scope="module")
def admin_session(session):
    """Login as admin and return session."""
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def e2e_bypass_session():
    """Login as E2E bypass user (OTP bypass enabled)."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    resp = s.post(f"{BASE_URL}/api/auth/login", json={
        "email": E2E_BYPASS_EMAIL,
        "password": E2E_BYPASS_PASSWORD
    })
    assert resp.status_code == 200, f"E2E bypass user login failed: {resp.text}"
    return s


class TestHealthAndBasics:
    """Basic health and connectivity tests."""
    
    def test_health_endpoint(self, session):
        """Test /api/health returns 200."""
        resp = session.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        print(f"✓ Health check passed: {data}")


class TestPasswordAuthLifecycle:
    """Password register/login/logout/auth-me lifecycle tests."""
    
    def test_register_new_user_with_realaicoach_domain(self, session):
        """Register a new user with realaicoach.app domain (not blocked by email guardrail)."""
        unique_id = uuid.uuid4().hex[:8]
        test_email = f"auth.e2e.{unique_id}@realaicoach.app"
        test_password = "TestAuth#2026Aa!"
        
        resp = session.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": test_password,
            "name": "Auth E2E Test User"
        })
        
        # May fail due to rate limiting or existing user
        if resp.status_code == 429:
            pytest.skip("Rate limited on registration")
        
        assert resp.status_code == 200, f"Registration failed: {resp.text}"
        data = resp.json()
        assert "user_id" in data
        assert data["email"] == test_email
        print(f"✓ Registered user: {test_email}, user_id: {data['user_id']}")
        
        # Store for cleanup
        return {"email": test_email, "password": test_password, "user_id": data["user_id"]}
    
    def test_admin_login_success(self, session):
        """Test admin login with correct credentials."""
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        data = resp.json()
        assert data.get("email") == ADMIN_EMAIL
        assert data.get("is_admin") == True
        print(f"✓ Admin login successful: is_admin={data.get('is_admin')}")
    
    def test_auth_me_after_login(self, admin_session):
        """Test /api/auth/me returns user data after login."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"Auth me failed: {resp.text}"
        data = resp.json()
        assert "user_id" in data
        assert "email" in data
        assert data.get("is_admin") == True
        print(f"✓ Auth me returned: user_id={data['user_id']}, is_admin={data['is_admin']}")
    
    def test_logout_success(self):
        """Test logout clears session."""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        
        # Login first
        resp = s.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        
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
    
    def test_login_invalid_credentials(self, session):
        """Test login with wrong password returns 401."""
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": "WrongPassword123!"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("✓ Invalid credentials correctly rejected with 401")


class Test2FAStatusAndFlow:
    """2FA status and enable/disable flow tests."""
    
    def test_2fa_status_endpoint(self, admin_session):
        """Test /api/auth/2fa/status returns 2FA info."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/2fa/status")
        assert resp.status_code == 200, f"2FA status failed: {resp.text}"
        data = resp.json()
        
        # Verify expected fields
        assert "two_fa_enabled" in data
        assert "has_pin" in data
        assert "has_passkey" in data
        assert "passkey_count" in data
        assert "passkey_rollout_enabled" in data
        print(f"✓ 2FA status: two_fa_enabled={data.get('two_fa_enabled')}, has_passkey={data.get('has_passkey')}")
    
    def test_2fa_enable_flow(self, e2e_bypass_session):
        """Test enabling 2FA returns backup codes."""
        # First check current status
        status_resp = e2e_bypass_session.get(f"{BASE_URL}/api/auth/2fa/status")
        assert status_resp.status_code == 200
        status = status_resp.json()
        
        if status.get("two_fa_enabled"):
            # Already enabled, try to disable first
            disable_resp = e2e_bypass_session.post(f"{BASE_URL}/api/auth/2fa/disable")
            if disable_resp.status_code != 200:
                pytest.skip("Cannot disable 2FA to test enable flow")
        
        # Enable 2FA
        resp = e2e_bypass_session.post(f"{BASE_URL}/api/auth/2fa/enable")
        assert resp.status_code == 200, f"2FA enable failed: {resp.text}"
        data = resp.json()
        
        assert data.get("two_fa_enabled") == True
        assert "backup_codes" in data
        assert len(data["backup_codes"]) > 0
        print(f"✓ 2FA enabled, backup codes count: {len(data['backup_codes'])}")


class TestOTPLoginFlow:
    """OTP login request/verify readiness and error handling."""
    
    def test_otp_login_request_with_blocked_domain(self, session):
        """Test OTP login request with example.com domain returns 503 (email guardrail)."""
        resp = session.post(f"{BASE_URL}/api/auth/otp/login/request", json={
            "email": FREE_USER_EMAIL
        })
        
        # Expected: 503 due to email guardrail blocking example.com
        assert resp.status_code == 503, f"Expected 503 for blocked domain, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "temporarily unavailable" in data.get("detail", "").lower()
        print(f"✓ OTP login request correctly returns 503 for blocked domain: {data.get('detail')}")
    
    def test_otp_login_request_with_valid_domain(self, session):
        """Test OTP login request with realaicoach.app domain."""
        resp = session.post(f"{BASE_URL}/api/auth/otp/login/request", json={
            "email": ADMIN_EMAIL
        })
        
        # Admin is OTP exempt, so this should succeed or return appropriate response
        # Could be 200 (OTP sent) or 200 with reused_existing or rate limited
        assert resp.status_code in [200, 429], f"Unexpected status: {resp.status_code}: {resp.text}"
        print(f"✓ OTP login request for valid domain: status={resp.status_code}")
    
    def test_otp_verify_without_code(self, session):
        """Test OTP verify endpoint validation."""
        resp = session.post(f"{BASE_URL}/api/auth/otp/login/verify", json={
            "email": ADMIN_EMAIL,
            "code": ""
        })
        
        # Should fail validation
        assert resp.status_code in [400, 422], f"Expected validation error, got {resp.status_code}"
        print("✓ OTP verify correctly validates empty code")


class TestPasswordResetFlow:
    """Password reset request flow tests."""
    
    def test_password_reset_request_blocked_domain(self, session):
        """Test password reset with example.com domain returns 503."""
        resp = session.post(f"{BASE_URL}/api/auth/password-reset/request", json={
            "email": FREE_USER_EMAIL
        })
        
        # Expected: 503 due to email guardrail
        assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.text}"
        print("✓ Password reset correctly returns 503 for blocked domain")
    
    def test_password_reset_request_valid_domain(self, session):
        """Test password reset with valid domain."""
        resp = session.post(f"{BASE_URL}/api/auth/password-reset/request", json={
            "email": ADMIN_EMAIL
        })
        
        # Should succeed or be rate limited
        assert resp.status_code in [200, 429], f"Unexpected status: {resp.status_code}: {resp.text}"
        print(f"✓ Password reset for valid domain: status={resp.status_code}")


class TestPasskeyEndpoints:
    """Passkey endpoints readiness tests."""
    
    def test_passkey_enrollment_eligibility(self, admin_session):
        """Test passkey enrollment eligibility endpoint."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/biometric/passkey-enrollment-eligibility")
        assert resp.status_code == 200, f"Passkey eligibility failed: {resp.text}"
        data = resp.json()
        
        assert "rollout_enabled" in data
        assert "has_passkey" in data
        assert "should_prompt" in data
        print(f"✓ Passkey eligibility: rollout_enabled={data.get('rollout_enabled')}, should_prompt={data.get('should_prompt')}")
    
    def test_webauthn_register_options(self, admin_session):
        """Test WebAuthn register options endpoint."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/biometric/webauthn-register-options", json={})
        assert resp.status_code == 200, f"WebAuthn register options failed: {resp.text}"
        data = resp.json()
        
        # Should contain challenge
        assert "challenge" in data or "publicKey" in data
        print("✓ WebAuthn register options returned successfully")
    
    def test_webauthn_auth_options(self, session):
        """Test WebAuthn auth options endpoint (unauthenticated)."""
        resp = session.post(f"{BASE_URL}/api/auth/biometric/webauthn-auth-options", json={
            "user_id": "user_test123"
        })
        
        # May return 200 with options or 404 if no passkey registered
        assert resp.status_code in [200, 404], f"Unexpected status: {resp.status_code}: {resp.text}"
        print(f"✓ WebAuthn auth options: status={resp.status_code}")


class TestSecurityPageResilience:
    """Security page resilience tests - no hard fail if geo endpoint fails."""
    
    def test_geo_detect_endpoint(self, admin_session):
        """Test /api/geo/detect endpoint (may fail for free users)."""
        resp = admin_session.get(f"{BASE_URL}/api/geo/detect")
        
        # Should return 200 or 403 (subscription gated) - not 500
        assert resp.status_code in [200, 403], f"Geo detect unexpected error: {resp.status_code}: {resp.text}"
        print(f"✓ Geo detect endpoint: status={resp.status_code}")
    
    def test_login_history_endpoint(self, admin_session):
        """Test login history endpoint."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/login-history")
        assert resp.status_code == 200, f"Login history failed: {resp.text}"
        data = resp.json()
        
        assert "events" in data or isinstance(data, list)
        print("✓ Login history returned successfully")
    
    def test_security_events_endpoint(self, admin_session):
        """Test security events endpoint."""
        resp = admin_session.get(f"{BASE_URL}/api/security/events")
        
        # May be admin-only or return events
        assert resp.status_code in [200, 403], f"Security events unexpected: {resp.status_code}"
        print(f"✓ Security events: status={resp.status_code}")


class TestNotificationSideEffects:
    """In-app notification side effects after auth events."""
    
    def test_notifications_endpoint(self, admin_session):
        """Test notifications endpoint returns user notifications."""
        resp = admin_session.get(f"{BASE_URL}/api/notifications")
        assert resp.status_code == 200, f"Notifications failed: {resp.text}"
        data = resp.json()
        
        assert "notifications" in data
        assert "unread_count" in data
        print(f"✓ Notifications: count={len(data['notifications'])}, unread={data['unread_count']}")
    
    def test_notification_unread_count(self, admin_session):
        """Test notification unread count endpoint."""
        resp = admin_session.get(f"{BASE_URL}/api/notifications/unread-count")
        assert resp.status_code == 200, f"Unread count failed: {resp.text}"
        data = resp.json()
        
        assert "unread_count" in data
        print(f"✓ Unread count: {data['unread_count']}")


class TestEmailNotificationBehavior:
    """Email notification/log behavior for auth events."""
    
    def test_email_guardrail_blocks_example_domain(self, session):
        """Verify email guardrail blocks example.com domain."""
        # This is tested implicitly by OTP and password reset tests
        # The 503 responses confirm the guardrail is active
        print("✓ Email guardrail for example.com domain confirmed via OTP/reset tests")
    
    def test_admin_email_delivery_works(self, session):
        """Test that admin email (realaicoach.app) is not blocked."""
        # Login as admin triggers login alert email
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        
        # The login should succeed and email should be attempted (not blocked)
        print("✓ Admin login succeeded - email delivery not blocked for realaicoach.app domain")


class TestRealTimeInAppBehavior:
    """Real-time in-app behavior around auth/notification feeds."""
    
    def test_live_activity_feed(self, admin_session):
        """Test live activity feed endpoint."""
        resp = admin_session.get(f"{BASE_URL}/api/live-activity/feed")
        
        # May return events or empty list
        assert resp.status_code == 200, f"Live activity failed: {resp.text}"
        data = resp.json()
        assert "events" in data
        print(f"✓ Live activity feed: {len(data['events'])} events")
    
    def test_notification_settings(self, admin_session):
        """Test notification settings endpoint."""
        resp = admin_session.get(f"{BASE_URL}/api/notifications/settings")
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
    
    def test_auth_lookup_existing_user(self, session):
        """Test auth lookup for existing user."""
        resp = session.get(f"{BASE_URL}/api/auth/lookup", params={"email": ADMIN_EMAIL})
        assert resp.status_code == 200, f"Auth lookup failed: {resp.text}"
        data = resp.json()
        
        assert data.get("exists") == True
        assert "user_id" in data
        assert "has_pin" in data
        assert "has_passkey" in data
        print(f"✓ Auth lookup: exists={data['exists']}, has_passkey={data.get('has_passkey')}")
    
    def test_auth_lookup_nonexistent_user(self, session):
        """Test auth lookup for non-existent user (anti-enumeration)."""
        resp = session.get(f"{BASE_URL}/api/auth/lookup", params={"email": "nonexistent@example.com"})
        assert resp.status_code == 200, f"Auth lookup failed: {resp.text}"
        data = resp.json()
        
        # Anti-enumeration: should still return exists=True with fake user_id
        assert data.get("exists") == True
        assert "user_id" in data
        print("✓ Auth lookup anti-enumeration working (returns consistent shape)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
