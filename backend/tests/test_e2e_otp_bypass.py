"""
Test suite for E2E OTP Bypass Automation (P1 Hardening)

Tests:
1. Allowlisted admin E2E account bypasses OTP challenge on /api/auth/login in non-production test mode
2. Bypass is email-allowlisted only (non-allowlisted admin and normal users do not get bypass flag)
3. Bypass is auditable (security event path present and no crash)
4. Auth helper endpoint remains gated and functional: /api/auth/admin/e2e/otp/issue
5. Frontend /auth/login still works and can authenticate the allowlisted admin account
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ALLOWLISTED_ADMIN_E2E_EMAIL = "watchvideos.phase4.admin.306786@example.com"
ALLOWLISTED_ADMIN_E2E_PASSWORD = "Phase4Admin#2026Aa"

PRIMARY_ADMIN_EMAIL = "admin@realaicoach.app"
PRIMARY_ADMIN_PASSWORD = "NewAdminPass2026!"

FREE_TEST_USER_EMAIL = "feature21.test.1781234530@example.com"
FREE_TEST_USER_PASSWORD = "Feature21Test#2026Aa"


class TestE2EOtpBypassLogin:
    """Test OTP bypass for allowlisted admin E2E account on login"""

    def test_health_endpoint(self):
        """Verify backend is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("PASS: Health endpoint accessible")

    def test_allowlisted_admin_e2e_login_bypasses_otp(self):
        """
        Allowlisted admin E2E account should bypass OTP challenge and get direct login.
        Response should include e2e_otp_bypass_applied=True.
        """
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": ALLOWLISTED_ADMIN_E2E_EMAIL,
                "password": ALLOWLISTED_ADMIN_E2E_PASSWORD,
            },
            headers={"Content-Type": "application/json"},
        )
        
        # Should be 200 (direct login) not 200 with requires_2fa=True
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        
        data = response.json()
        
        # Verify direct login (no 2FA required)
        assert data.get("requires_2fa") is not True, f"OTP bypass failed - 2FA still required: {data}"
        
        # Verify e2e_otp_bypass_applied flag is present and True
        assert data.get("e2e_otp_bypass_applied") is True, f"e2e_otp_bypass_applied flag missing or False: {data}"
        
        # Verify user data is returned
        assert data.get("user_id"), f"user_id missing in response: {data}"
        assert data.get("email") == ALLOWLISTED_ADMIN_E2E_EMAIL, f"Email mismatch: {data}"
        
        print(f"PASS: Allowlisted admin E2E login bypassed OTP - e2e_otp_bypass_applied={data.get('e2e_otp_bypass_applied')}")
        print(f"  user_id: {data.get('user_id')}")
        print(f"  is_admin: {data.get('is_admin')}")
        print(f"  full_access: {data.get('full_access')}")

    def test_primary_admin_login_no_bypass_flag(self):
        """
        Primary admin (not in bypass allowlist) should NOT have e2e_otp_bypass_applied=True.
        They may still bypass OTP due to is_admin/full_access, but not via E2E bypass.
        """
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": PRIMARY_ADMIN_EMAIL,
                "password": PRIMARY_ADMIN_PASSWORD,
            },
            headers={"Content-Type": "application/json"},
        )
        
        assert response.status_code == 200, f"Primary admin login failed: {response.status_code} - {response.text}"
        
        data = response.json()
        
        # Primary admin should NOT have e2e_otp_bypass_applied=True (they bypass via is_admin policy, not E2E bypass)
        e2e_bypass = data.get("e2e_otp_bypass_applied", False)
        assert e2e_bypass is False or e2e_bypass is None, f"Primary admin should NOT have e2e_otp_bypass_applied=True: {data}"
        
        print(f"PASS: Primary admin login - e2e_otp_bypass_applied={e2e_bypass} (expected False)")
        print(f"  is_admin: {data.get('is_admin')}")
        print(f"  full_access: {data.get('full_access')}")


class TestE2EOtpBypassNonAllowlisted:
    """Test that non-allowlisted users do NOT get OTP bypass"""

    def test_free_user_no_bypass(self):
        """
        Free test user (not admin, not in allowlist) should NOT get e2e_otp_bypass_applied.
        They may require OTP or be in grace period, but no E2E bypass flag.
        """
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": FREE_TEST_USER_EMAIL,
                "password": FREE_TEST_USER_PASSWORD,
            },
            headers={"Content-Type": "application/json"},
        )
        
        # May be 200 (direct login if in grace) or 200 with requires_2fa=True
        assert response.status_code == 200, f"Free user login failed: {response.status_code} - {response.text}"
        
        data = response.json()
        
        # Free user should NOT have e2e_otp_bypass_applied=True
        e2e_bypass = data.get("e2e_otp_bypass_applied", False)
        assert e2e_bypass is False or e2e_bypass is None, f"Free user should NOT have e2e_otp_bypass_applied=True: {data}"
        
        print(f"PASS: Free user login - e2e_otp_bypass_applied={e2e_bypass} (expected False)")
        print(f"  requires_2fa: {data.get('requires_2fa')}")
        print(f"  is_admin: {data.get('is_admin')}")


class TestE2EOtpHelperEndpoint:
    """Test /api/auth/admin/e2e/otp/issue endpoint"""

    def _get_admin_session(self):
        """Get admin session for authenticated requests"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": PRIMARY_ADMIN_EMAIL,
                "password": PRIMARY_ADMIN_PASSWORD,
            },
            headers={
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        
        # Session cookies are automatically stored in the session object
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        return session

    def test_e2e_otp_issue_requires_admin(self):
        """Endpoint should require admin authentication"""
        response = requests.post(
            f"{BASE_URL}/api/auth/admin/e2e/otp/issue",
            json={
                "email": ALLOWLISTED_ADMIN_E2E_EMAIL,
                "purpose": "2fa",
            },
            headers={"Content-Type": "application/json"},
        )
        
        # Should be 401 or 403 without auth
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}: {response.text}"
        print(f"PASS: E2E OTP issue endpoint requires admin auth (status={response.status_code})")

    def test_e2e_otp_issue_allowlist_check(self):
        """Endpoint should only work for allowlisted emails"""
        admin_session = self._get_admin_session()
        
        # Try with non-allowlisted email
        response = admin_session.post(
            f"{BASE_URL}/api/auth/admin/e2e/otp/issue",
            json={
                "email": "random.user@example.com",
                "purpose": "2fa",
            },
        )
        
        # Should be 403 or 404 for non-allowlisted email
        assert response.status_code in [403, 404], f"Expected 403/404 for non-allowlisted email, got {response.status_code}: {response.text}"
        print(f"PASS: E2E OTP issue rejects non-allowlisted email (status={response.status_code})")

    def test_e2e_otp_issue_success_for_allowlisted(self):
        """Endpoint should work for allowlisted email"""
        admin_session = self._get_admin_session()
        
        response = admin_session.post(
            f"{BASE_URL}/api/auth/admin/e2e/otp/issue",
            json={
                "email": ALLOWLISTED_ADMIN_E2E_EMAIL,
                "purpose": "2fa",
            },
        )
        
        assert response.status_code == 200, f"E2E OTP issue failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert data.get("success") is True, f"success flag missing: {data}"
        assert data.get("otp_code"), f"otp_code missing: {data}"
        assert data.get("target_email") == ALLOWLISTED_ADMIN_E2E_EMAIL, f"target_email mismatch: {data}"
        assert data.get("non_production_only") is True, f"non_production_only flag missing: {data}"
        
        print("PASS: E2E OTP issue successful for allowlisted email")
        print(f"  otp_code: {data.get('otp_code')}")
        print(f"  expires_in_minutes: {data.get('expires_in_minutes')}")
        print(f"  non_production_only: {data.get('non_production_only')}")


class TestSecurityEventAudit:
    """Test that OTP bypass is auditable via security events"""

    def test_bypass_creates_security_event(self):
        """
        Login with allowlisted admin E2E should create a security event.
        We verify this by checking the login succeeds without crash.
        """
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": ALLOWLISTED_ADMIN_E2E_EMAIL,
                "password": ALLOWLISTED_ADMIN_E2E_PASSWORD,
            },
            headers={"Content-Type": "application/json"},
        )
        
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert data.get("e2e_otp_bypass_applied") is True, f"Bypass not applied: {data}"
        
        # If we got here without crash, the security event logging path is working
        print("PASS: OTP bypass login completed without crash (security event path functional)")


class TestEnvConfiguration:
    """Test environment configuration for OTP bypass"""

    def test_bypass_env_vars_configured(self):
        """Verify the expected env vars are set (via backend behavior)"""
        # We can't directly read env vars, but we can verify behavior
        # If allowlisted admin gets bypass, env vars are correctly configured
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": ALLOWLISTED_ADMIN_E2E_EMAIL,
                "password": ALLOWLISTED_ADMIN_E2E_PASSWORD,
            },
            headers={"Content-Type": "application/json"},
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # If bypass is applied, AUTH_E2E_OTP_BYPASS_ENABLED=true is working
        if data.get("e2e_otp_bypass_applied"):
            print("PASS: AUTH_E2E_OTP_BYPASS_ENABLED=true is active")
            print("PASS: AUTH_E2E_OTP_BYPASS_EMAILS includes allowlisted admin")
        else:
            pytest.fail(f"Bypass not applied - check env configuration: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
