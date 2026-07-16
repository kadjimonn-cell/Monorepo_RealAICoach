"""
Test Email Suppression for Non-Production Risk Templates - Iteration 264

Tests the new behavior that suppresses only noisy risk templates (risk_engine_status_v7)
in non-production for test-domain recipients (example.com), while ensuring OTP/reset
templates still send correctly.

Features tested:
1. risk_engine_status_v7 email template suppressed for example.com recipients in non-production
2. OTP auth email template still sends for example.com recipients
3. Password reset flow still sends for example.com recipients
4. No regression in auth login/otp/reset flows
"""

import pytest
import requests
import os
import sys

# Add backend to path for direct module testing
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestEmailSuppressionModule:
    """Direct module-level tests for email suppression logic."""
    
    def test_nonprod_suppressed_templates_default(self):
        """Test that default suppressed templates include risk_engine_status_v7."""
        from utils.email_service import _nonprod_suppressed_email_templates
        
        suppressed = _nonprod_suppressed_email_templates()
        assert "risk_engine_status_v7" in suppressed, \
            f"risk_engine_status_v7 should be in suppressed templates, got: {suppressed}"
        print(f"PASS: Default suppressed templates: {suppressed}")
    
    def test_is_non_production_runtime_detection(self):
        """Test that preview environment is detected as non-production."""
        from utils.email_service import _is_non_production_runtime
        
        # In preview.emergentagent.com, this should return True
        result = _is_non_production_runtime()
        print(f"INFO: _is_non_production_runtime() = {result}")
        # This should be True in preview environment
        assert result is True, "Preview environment should be detected as non-production"
        print("PASS: Non-production runtime correctly detected")
    
    def test_auth_email_test_domain_allowlist(self):
        """Test that example.com is in the auth email test domain allowlist."""
        from utils.email_service import _auth_email_test_domain_allowlist
        
        allowlist = _auth_email_test_domain_allowlist()
        assert "example.com" in allowlist, \
            f"example.com should be in allowlist, got: {allowlist}"
        print(f"PASS: Auth email test domain allowlist: {allowlist}")
    
    def test_should_suppress_risk_template_for_example_com(self):
        """Test that risk_engine_status_v7 is suppressed for example.com in non-prod."""
        from utils.email_service import _should_suppress_nonprod_template_for_test_domain
        
        # Should suppress risk_engine_status_v7 for example.com
        result = _should_suppress_nonprod_template_for_test_domain(
            template_key="risk_engine_status_v7",
            recipient_email="test@example.com"
        )
        assert result is True, \
            f"risk_engine_status_v7 should be suppressed for example.com, got: {result}"
        print("PASS: risk_engine_status_v7 correctly suppressed for example.com")
    
    def test_should_not_suppress_otp_template_for_example_com(self):
        """Test that OTP template is NOT suppressed for example.com."""
        from utils.email_service import _should_suppress_nonprod_template_for_test_domain
        
        # OTP templates should NOT be suppressed
        otp_templates = ["otp_verification", "auth_otp", "login_otp", "verification_code"]
        
        for template in otp_templates:
            result = _should_suppress_nonprod_template_for_test_domain(
                template_key=template,
                recipient_email="test@example.com"
            )
            assert result is False, \
                f"{template} should NOT be suppressed for example.com, got: {result}"
            print(f"PASS: {template} correctly NOT suppressed for example.com")
    
    def test_should_not_suppress_password_reset_template_for_example_com(self):
        """Test that password reset template is NOT suppressed for example.com."""
        from utils.email_service import _should_suppress_nonprod_template_for_test_domain
        
        # Password reset templates should NOT be suppressed
        reset_templates = ["password_reset", "reset_password", "password_reset_request"]
        
        for template in reset_templates:
            result = _should_suppress_nonprod_template_for_test_domain(
                template_key=template,
                recipient_email="test@example.com"
            )
            assert result is False, \
                f"{template} should NOT be suppressed for example.com, got: {result}"
            print(f"PASS: {template} correctly NOT suppressed for example.com")
    
    def test_should_not_suppress_for_real_domain(self):
        """Test that risk template is NOT suppressed for real domains."""
        from utils.email_service import _should_suppress_nonprod_template_for_test_domain
        
        # Real domains should never be suppressed
        real_domains = ["user@gmail.com", "user@realaicoach.app", "user@company.org"]
        
        for email in real_domains:
            result = _should_suppress_nonprod_template_for_test_domain(
                template_key="risk_engine_status_v7",
                recipient_email=email
            )
            assert result is False, \
                f"risk_engine_status_v7 should NOT be suppressed for {email}, got: {result}"
            print(f"PASS: risk_engine_status_v7 correctly NOT suppressed for {email}")
    
    def test_should_not_suppress_non_risk_templates(self):
        """Test that non-risk templates are NOT suppressed even for example.com."""
        from utils.email_service import _should_suppress_nonprod_template_for_test_domain
        
        # Non-risk templates should NOT be suppressed
        non_risk_templates = [
            "welcome_email",
            "login_alert",
            "user_notification_alert",
            "payment_confirmation",
            "subscription_update"
        ]
        
        for template in non_risk_templates:
            result = _should_suppress_nonprod_template_for_test_domain(
                template_key=template,
                recipient_email="test@example.com"
            )
            assert result is False, \
                f"{template} should NOT be suppressed for example.com, got: {result}"
            print(f"PASS: {template} correctly NOT suppressed for example.com")


class TestAuthFlowsNoRegression:
    """Test that auth flows still work correctly after the suppression change."""
    
    @pytest.fixture
    def api_client(self):
        """Shared requests session."""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        return session
    
    def test_health_check(self, api_client):
        """Verify backend is healthy."""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("PASS: Backend health check")
    
    def test_password_login_admin(self, api_client):
        """Test admin password login still works."""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@realaicoach.app",
                "password": "NewAdminPass2026!"
            }
        )
        assert response.status_code == 200, \
            f"Admin login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "user_id" in data or "user" in data, f"Missing user data in response: {data}"
        print("PASS: Admin password login works")
    
    def test_password_login_free_user_example_com(self, api_client):
        """Test free user (example.com) password login still works."""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "p1.free.1779113329@example.com",
                "password": "P1Free#2026!Aa"
            }
        )
        assert response.status_code == 200, \
            f"Free user login failed: {response.status_code} - {response.text}"
        print("PASS: Free user (example.com) password login works")
    
    def test_otp_request_for_example_com_user(self, api_client):
        """Test OTP request for example.com user still sends email."""
        response = api_client.post(
            f"{BASE_URL}/api/auth/otp/request",
            json={
                "email": "p1.free.1779113329@example.com"
            }
        )
        # Should return 200 with OTP sent message (not suppressed)
        assert response.status_code == 200, \
            f"OTP request failed: {response.status_code} - {response.text}"
        data = response.json()
        # Check that OTP was sent (not suppressed)
        assert "otp" in str(data).lower() or "sent" in str(data).lower() or "success" in str(data).lower(), \
            f"OTP should be sent for example.com user, got: {data}"
        print(f"PASS: OTP request for example.com user works - Response: {data}")
    
    def test_password_reset_for_example_com_user(self, api_client):
        """Test password reset for example.com user still sends email."""
        response = api_client.post(
            f"{BASE_URL}/api/auth/password/reset/request",
            json={
                "email": "p1.free.1779113329@example.com"
            }
        )
        # Should return 200 with reset email sent (not suppressed)
        assert response.status_code == 200, \
            f"Password reset request failed: {response.status_code} - {response.text}"
        data = response.json()
        # Check that reset email was sent (not suppressed)
        assert "sent" in str(data).lower() or "success" in str(data).lower() or "email" in str(data).lower(), \
            f"Password reset email should be sent for example.com user, got: {data}"
        print(f"PASS: Password reset for example.com user works - Response: {data}")
    
    def test_auth_me_after_login(self, api_client):
        """Test /auth/me endpoint after login."""
        # First login
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@realaicoach.app",
                "password": "NewAdminPass2026!"
            }
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.status_code}"
        
        # Then check /auth/me
        me_response = api_client.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200, \
            f"/auth/me failed: {me_response.status_code} - {me_response.text}"
        data = me_response.json()
        assert "email" in data or "user" in data, f"Missing user data in /auth/me: {data}"
        print("PASS: /auth/me endpoint works after login")


class TestRiskTemplateSuppressionIntegration:
    """Integration tests to verify risk template suppression behavior."""
    
    def test_risk_template_suppression_in_send_email_guard(self):
        """Test that send_email guard correctly suppresses risk_engine_status_v7."""
        from utils.email_service import (
            _should_suppress_nonprod_template_for_test_domain,
            _is_non_production_runtime,
            _nonprod_suppressed_email_templates,
            _auth_email_test_domain_allowlist
        )
        
        # Verify all components work together
        is_nonprod = _is_non_production_runtime()
        suppressed_templates = _nonprod_suppressed_email_templates()
        test_domains = _auth_email_test_domain_allowlist()
        
        print(f"INFO: is_non_production_runtime = {is_nonprod}")
        print(f"INFO: suppressed_templates = {suppressed_templates}")
        print(f"INFO: test_domains = {test_domains}")
        
        # Test the full suppression logic
        test_cases = [
            # (template_key, recipient_email, expected_suppressed)
            ("risk_engine_status_v7", "test@example.com", True),
            ("risk_engine_status_v7", "user@gmail.com", False),
            ("otp_verification", "test@example.com", False),
            ("password_reset", "test@example.com", False),
            ("login_alert", "test@example.com", False),
        ]
        
        for template_key, recipient_email, expected in test_cases:
            result = _should_suppress_nonprod_template_for_test_domain(template_key, recipient_email)
            assert result == expected, \
                f"Template {template_key} for {recipient_email}: expected {expected}, got {result}"
            status = "suppressed" if result else "allowed"
            print(f"PASS: {template_key} for {recipient_email} is {status} (expected: {expected})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
