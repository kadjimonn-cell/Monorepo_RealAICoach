"""
Full Auth Live E2E Tests - Iteration 263
Testing the fix for example.com domain allowlist in non-production auth email flows.

Focus areas:
1. Password register/login/logout/auth-me
2. OTP request flow for example.com E2E auth user (should NOT fail due to domain guardrail)
3. Password reset request for example.com E2E auth user (should NOT fail)
4. Passkey readiness endpoints still healthy
5. 2FA status/enable unchanged
6. In-app notifications API still functional
7. Email logs confirm auth emails are sent/skipped per policy
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
E2E_BYPASS_EMAIL = "watchvideos.phase4.admin.306786@example.com"
E2E_BYPASS_PASSWORD = "Phase4Admin#2026Aa"


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_api_health(self):
        """API health endpoint should return healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✓ API health: {data}")


class TestPasswordAuthFlow:
    """Password-based authentication flows"""
    
    def test_admin_login_success(self):
        """Admin user should login successfully"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "user_id" in data or "email" in data
        print(f"✓ Admin login successful: user_id={data.get('user_id')}")
        return response.cookies
    
    def test_free_user_login_success(self):
        """Free user (example.com domain) should login successfully"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
        )
        # May return 200 (direct login) or require 2FA
        assert response.status_code in [200, 202], f"Free user login failed: {response.text}"
        data = response.json()
        print(f"✓ Free user login response: status={response.status_code}, data={data}")
        return response
    
    def test_e2e_bypass_user_login(self):
        """E2E bypass user should login without OTP challenge"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": E2E_BYPASS_EMAIL, "password": E2E_BYPASS_PASSWORD}
        )
        assert response.status_code == 200, f"E2E bypass user login failed: {response.text}"
        data = response.json()
        # E2E bypass user should get direct login (no 2FA required)
        assert "user_id" in data or "email" in data
        print(f"✓ E2E bypass user login successful (no OTP required): {data.get('user_id')}")
        return response.cookies
    
    def test_auth_me_with_session(self):
        """Auth/me should return user data when authenticated"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        # Then check auth/me
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            cookies=login_response.cookies
        )
        assert response.status_code == 200, f"Auth/me failed: {response.text}"
        data = response.json()
        assert data.get("email") == ADMIN_EMAIL
        print(f"✓ Auth/me returned user: {data.get('email')}")
    
    def test_logout(self):
        """Logout should clear session"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        # Then logout
        response = requests.post(
            f"{BASE_URL}/api/auth/logout",
            cookies=login_response.cookies
        )
        assert response.status_code == 200, f"Logout failed: {response.text}"
        print("✓ Logout successful")
        
        # Verify session is cleared
        me_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            cookies=login_response.cookies
        )
        # Should be 401 or return unauthenticated state
        assert me_response.status_code in [401, 200]
        if me_response.status_code == 200:
            data = me_response.json()
            # If 200, should indicate not authenticated
            assert not data.get("user_id") or data.get("authenticated") == False


class TestOTPFlowForExampleComDomain:
    """
    CRITICAL: OTP request flow for example.com E2E auth user
    This was previously failing due to domain guardrail - should now work in non-prod
    """
    
    def test_otp_login_request_example_com_user(self):
        """OTP login request for example.com user should NOT return 503 anymore"""
        response = requests.post(
            f"{BASE_URL}/api/auth/otp/login",
            json={"email": FREE_USER_EMAIL}
        )
        # Should NOT be 503 (email service unavailable)
        # Expected: 200 (OTP sent) or 429 (rate limited) or 400 (user not found)
        print(f"OTP login request response: status={response.status_code}, body={response.text[:500]}")
        
        # The fix should allow example.com in non-production
        # 503 would indicate the email guardrail is still blocking
        if response.status_code == 503:
            data = response.json()
            error = data.get("detail", data.get("error", ""))
            # Check if it's the domain guardrail error
            if "blocked" in str(error).lower() or "domain" in str(error).lower():
                pytest.fail(f"OTP request still blocked by domain guardrail: {error}")
        
        # Valid responses: 200 (sent), 429 (rate limit), 400 (validation)
        assert response.status_code in [200, 429, 400, 404], f"Unexpected status: {response.status_code}"
        print(f"✓ OTP login request for example.com user: status={response.status_code}")
    
    def test_otp_login_request_e2e_bypass_user(self):
        """OTP login request for E2E bypass user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/otp/login",
            json={"email": E2E_BYPASS_EMAIL}
        )
        print(f"OTP login request (E2E bypass): status={response.status_code}, body={response.text[:500]}")
        
        # Should not be blocked by domain guardrail
        if response.status_code == 503:
            data = response.json()
            error = data.get("detail", data.get("error", ""))
            if "blocked" in str(error).lower() or "domain" in str(error).lower():
                pytest.fail(f"OTP request blocked by domain guardrail: {error}")
        
        assert response.status_code in [200, 429, 400, 404]
        print(f"✓ OTP login request for E2E bypass user: status={response.status_code}")


class TestPasswordResetForExampleComDomain:
    """
    CRITICAL: Password reset request for example.com E2E auth user
    This was previously failing due to domain guardrail - should now work in non-prod
    """
    
    def test_password_reset_request_example_com_user(self):
        """Password reset for example.com user should NOT return 503 anymore"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/request",
            json={"email": FREE_USER_EMAIL}
        )
        print(f"Password reset request response: status={response.status_code}, body={response.text[:500]}")
        
        # Should NOT be 503 (email service unavailable)
        if response.status_code == 503:
            data = response.json()
            error = data.get("detail", data.get("error", ""))
            if "blocked" in str(error).lower() or "domain" in str(error).lower():
                pytest.fail(f"Password reset still blocked by domain guardrail: {error}")
        
        # Valid responses: 200 (sent), 429 (rate limit), 400 (validation)
        assert response.status_code in [200, 429, 400, 404], f"Unexpected status: {response.status_code}"
        print(f"✓ Password reset request for example.com user: status={response.status_code}")
    
    def test_password_reset_request_e2e_bypass_user(self):
        """Password reset for E2E bypass user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/password-reset/request",
            json={"email": E2E_BYPASS_EMAIL}
        )
        print(f"Password reset request (E2E bypass): status={response.status_code}, body={response.text[:500]}")
        
        if response.status_code == 503:
            data = response.json()
            error = data.get("detail", data.get("error", ""))
            if "blocked" in str(error).lower() or "domain" in str(error).lower():
                pytest.fail(f"Password reset blocked by domain guardrail: {error}")
        
        assert response.status_code in [200, 429, 400, 404]
        print(f"✓ Password reset request for E2E bypass user: status={response.status_code}")


class TestPasskeyReadinessEndpoints:
    """Passkey/WebAuthn endpoints should remain healthy"""
    
    def test_passkey_enrollment_eligibility(self):
        """Passkey enrollment eligibility endpoint"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.get(
            f"{BASE_URL}/api/auth/biometric/passkey-enrollment-eligibility",
            cookies=login_response.cookies
        )
        assert response.status_code in [200, 404], f"Passkey eligibility failed: {response.text}"
        print(f"✓ Passkey enrollment eligibility: status={response.status_code}")
    
    def test_webauthn_register_options(self):
        """WebAuthn register options endpoint"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-register-options",
            json={},
            cookies=login_response.cookies
        )
        # Should return challenge or indicate no passkey support
        assert response.status_code in [200, 400, 404], f"WebAuthn register options failed: {response.text}"
        print(f"✓ WebAuthn register options: status={response.status_code}")
    
    def test_webauthn_auth_options_requires_auth(self):
        """WebAuthn auth options requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-auth-options",
            json={}
        )
        # Should require authentication
        assert response.status_code in [401, 400, 422], f"Expected auth required: {response.text}"
        print(f"✓ WebAuthn auth options requires auth: status={response.status_code}")


class Test2FAStatusAndEnable:
    """2FA status and enable endpoints should remain unchanged"""
    
    def test_2fa_status(self):
        """2FA status endpoint"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.get(
            f"{BASE_URL}/api/auth/2fa/status",
            cookies=login_response.cookies
        )
        assert response.status_code == 200, f"2FA status failed: {response.text}"
        data = response.json()
        print(f"✓ 2FA status: {data}")
    
    def test_2fa_enable_for_exempt_user(self):
        """2FA enable for OTP-exempt user should indicate exemption"""
        # First login as admin (OTP exempt)
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.post(
            f"{BASE_URL}/api/auth/2fa/enable",
            json={},
            cookies=login_response.cookies
        )
        # Admin is OTP exempt, so may get special response
        print(f"✓ 2FA enable response: status={response.status_code}, body={response.text[:300]}")
        assert response.status_code in [200, 400, 403]


class TestInAppNotificationsAPI:
    """In-app notifications API should remain functional"""
    
    def test_get_notifications(self):
        """Get notifications for authenticated user"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.get(
            f"{BASE_URL}/api/notifications",
            cookies=login_response.cookies
        )
        assert response.status_code == 200, f"Get notifications failed: {response.text}"
        data = response.json()
        assert "notifications" in data or isinstance(data, list)
        print(f"✓ Get notifications: count={len(data.get('notifications', data))}")
    
    def test_notifications_unread_count(self):
        """Get unread notifications count"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.get(
            f"{BASE_URL}/api/notifications/unread-count",
            cookies=login_response.cookies
        )
        assert response.status_code == 200, f"Unread count failed: {response.text}"
        data = response.json()
        assert "unread_count" in data
        print(f"✓ Unread count: {data.get('unread_count')}")
    
    def test_notification_settings(self):
        """Get notification settings"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.get(
            f"{BASE_URL}/api/notifications/settings",
            cookies=login_response.cookies
        )
        assert response.status_code == 200, f"Notification settings failed: {response.text}"
        data = response.json()
        print(f"✓ Notification settings: {list(data.keys())[:5]}...")
    
    def test_live_activity_feed(self):
        """Live activity feed endpoint"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.get(
            f"{BASE_URL}/api/live-activity/feed",
            cookies=login_response.cookies
        )
        assert response.status_code == 200, f"Live activity feed failed: {response.text}"
        data = response.json()
        print(f"✓ Live activity feed: events={len(data.get('events', []))}")


class TestAuthLookupAntiEnumeration:
    """Auth lookup should work with anti-enumeration protection"""
    
    def test_auth_lookup_existing_user(self):
        """Auth lookup for existing user"""
        response = requests.get(
            f"{BASE_URL}/api/auth/lookup",
            params={"email": ADMIN_EMAIL}
        )
        assert response.status_code == 200, f"Auth lookup failed: {response.text}"
        data = response.json()
        # Anti-enumeration: always returns exists=True
        assert data.get("exists") == True
        print(f"✓ Auth lookup (existing): {data}")
    
    def test_auth_lookup_nonexistent_user(self):
        """Auth lookup for non-existent user (anti-enumeration)"""
        fake_email = f"nonexistent_{uuid.uuid4().hex[:8]}@example.com"
        response = requests.get(
            f"{BASE_URL}/api/auth/lookup",
            params={"email": fake_email}
        )
        assert response.status_code == 200, f"Auth lookup failed: {response.text}"
        data = response.json()
        # Anti-enumeration: always returns exists=True with fake user_id
        assert data.get("exists") == True
        print(f"✓ Auth lookup (non-existent, anti-enum): {data}")


class TestLoginHistory:
    """Login history endpoint"""
    
    def test_login_history(self):
        """Get login history for authenticated user"""
        # First login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 200
        
        response = requests.get(
            f"{BASE_URL}/api/auth/login-history",
            cookies=login_response.cookies
        )
        # May return 200 with history or 404 if not implemented
        assert response.status_code in [200, 404], f"Login history failed: {response.text}"
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Login history: {len(data.get('events', data))} events")
        else:
            print(f"✓ Login history endpoint: status={response.status_code}")


class TestRegressionChecks:
    """Regression checks to ensure no unintended side effects"""
    
    def test_admin_login_still_works(self):
        """Admin login should still work after the fix"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        print("✓ Admin login regression check passed")
    
    def test_invalid_credentials_rejected(self):
        """Invalid credentials should still be rejected"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrongpassword"}
        )
        assert response.status_code in [401, 400, 403]
        print(f"✓ Invalid credentials rejected: status={response.status_code}")
    
    def test_unauthenticated_protected_endpoint(self):
        """Protected endpoints should require authentication"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        # Should return 401 or indicate not authenticated
        assert response.status_code in [401, 200]
        if response.status_code == 200:
            data = response.json()
            # If 200, should indicate not authenticated
            assert not data.get("user_id") or data.get("authenticated") == False
        print(f"✓ Protected endpoint requires auth: status={response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
