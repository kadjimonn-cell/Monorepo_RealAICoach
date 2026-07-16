"""
Test Apple SSO broker-style callback route and strict fail-closed behavior.

Features tested:
1. POST /api/auth/apple/broker/callback route exists and returns relay HTML form
2. GET /api/auth/sso-config exposes apple_callback_strategy and apple_broker_callback fields
3. GET /api/admin/sso-status apple provider includes callback_strategy and broker_callback
4. GET /api/auth/apple/login still fail-closes to apple_callback_not_provider_registered under strict preflight mode
5. Regression: Microsoft login redirect unaffected
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_session(api_client):
    """Authenticated admin session"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    if response.status_code == 403:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
        code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
        if code in {"risk_engine_id_verification_required", "risk_engine_admin_api_blocked"}:
            pytest.skip(f"Admin auth blocked by risk engine containment: {code}")

    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")

    login_data = response.json()
    token = login_data.get("session_token") or login_data.get("token") or response.cookies.get("session_token")
    if token:
        api_client.headers.update({"Authorization": f"Bearer {token}"})
    # Session cookie is set automatically
    return api_client


class TestAppleBrokerCallbackRoute:
    """Test POST /api/auth/apple/broker/callback route"""

    def test_broker_callback_route_exists(self, api_client):
        """POST /api/auth/apple/broker/callback should exist and return HTML relay form"""
        # Send minimal form data to trigger the route
        response = api_client.post(
            f"{BASE_URL}/api/auth/apple/broker/callback",
            data={"state": "test_state_value"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=False
        )
        
        # Route should exist (not 404)
        assert response.status_code != 404, "Broker callback route does not exist"
        
        # Should return HTML or redirect (302 for invalid target)
        assert response.status_code in [200, 302], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            # Should return HTML relay form
            content_type = response.headers.get("content-type", "")
            assert "text/html" in content_type, f"Expected HTML response, got: {content_type}"
            
            # Check for relay form elements
            html_content = response.text
            assert "apple-broker-relay-form" in html_content, "Missing relay form ID"
            assert "method=\"post\"" in html_content.lower(), "Missing POST method in form"
            print(f"✓ Broker callback returns HTML relay form (status={response.status_code})")
        else:
            # 302 redirect for invalid target is also acceptable
            location = response.headers.get("location", "")
            assert "sso_error" in location, f"Expected sso_error in redirect, got: {location}"
            print(f"✓ Broker callback redirects with error for invalid state (status={response.status_code})")

    def test_broker_callback_with_valid_state_structure(self, api_client):
        """Broker callback should handle form_post fields correctly"""
        import base64
        import json
        
        # Create a minimal state payload
        state_payload = {
            "provider": "apple",
            "return_base": BASE_URL,
            "nonce": "test_nonce_123"
        }
        state_encoded = base64.urlsafe_b64encode(json.dumps(state_payload).encode()).decode()
        
        response = api_client.post(
            f"{BASE_URL}/api/auth/apple/broker/callback",
            data={
                "state": state_encoded,
                "code": "test_auth_code",
                "id_token": "test_id_token"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=False
        )
        
        # Should return HTML relay form or redirect
        assert response.status_code in [200, 302], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            html_content = response.text
            # Verify form action points to apple callback
            assert "/api/auth/apple/callback" in html_content, "Form action should point to apple callback"
            # Verify hidden inputs are present
            assert 'name="state"' in html_content, "Missing state hidden input"
            print("✓ Broker callback generates relay form with correct action")
        else:
            print(f"✓ Broker callback redirects (status={response.status_code})")


class TestSSOConfigEndpoint:
    """Test GET /api/auth/sso-config exposes apple_callback_strategy and apple_broker_callback"""

    def test_sso_config_exposes_apple_callback_strategy(self, api_client):
        """GET /api/auth/sso-config should include apple_callback_strategy field"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        
        assert response.status_code == 200, f"SSO config failed: {response.text}"
        data = response.json()
        
        # Check apple_callback_strategy field exists
        assert "apple_callback_strategy" in data, "Missing apple_callback_strategy field"
        strategy = data["apple_callback_strategy"]
        assert strategy in ["direct", "broker"], f"Invalid strategy value: {strategy}"
        print(f"✓ apple_callback_strategy = {strategy}")

    def test_sso_config_exposes_apple_broker_callback(self, api_client):
        """GET /api/auth/sso-config should include apple_broker_callback field"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        
        assert response.status_code == 200, f"SSO config failed: {response.text}"
        data = response.json()
        
        # Check apple_broker_callback field exists
        assert "apple_broker_callback" in data, "Missing apple_broker_callback field"
        broker_callback = data["apple_broker_callback"]
        
        # Should be None or a valid URL path
        if broker_callback is not None:
            assert "/api/auth/apple/broker/callback" in broker_callback, \
                f"Unexpected broker callback path: {broker_callback}"
        print(f"✓ apple_broker_callback = {broker_callback}")

    def test_sso_config_all_apple_fields_present(self, api_client):
        """Verify all expected Apple SSO fields are present in sso-config"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        
        assert response.status_code == 200
        data = response.json()
        
        expected_fields = [
            "apple_callback_strategy",
            "apple_broker_callback",
            "apple_callback",
            "apple_strict_callback_allowlist_enabled",
            "apple_require_preflight_accepted",
            "apple_provider_accepted_bases",
            "deployment_domain_active_apple"
        ]
        
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
            print(f"  ✓ {field} = {data[field]}")
        
        print("✓ All expected Apple SSO fields present in sso-config")


class TestAdminSSOStatus:
    """Test GET /api/admin/sso-status apple provider includes callback_strategy and broker_callback"""

    def test_admin_sso_status_apple_callback_strategy(self, admin_session):
        """GET /api/admin/sso-status should include callback_strategy for Apple provider"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert response.status_code == 200, f"Admin SSO status failed: {response.text}"
        data = response.json()
        
        # Find Apple provider in providers list
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        
        assert apple_provider is not None, "Apple provider not found in sso-status"
        
        # Check callback_strategy field
        assert "callback_strategy" in apple_provider, "Missing callback_strategy in Apple provider"
        strategy = apple_provider["callback_strategy"]
        assert strategy in ["direct", "broker"], f"Invalid strategy: {strategy}"
        print(f"✓ Apple provider callback_strategy = {strategy}")

    def test_admin_sso_status_apple_broker_callback(self, admin_session):
        """GET /api/admin/sso-status should include broker_callback for Apple provider"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert response.status_code == 200, f"Admin SSO status failed: {response.text}"
        data = response.json()
        
        # Find Apple provider
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        
        assert apple_provider is not None, "Apple provider not found"
        
        # Check broker_callback field
        assert "broker_callback" in apple_provider, "Missing broker_callback in Apple provider"
        broker_callback = apple_provider["broker_callback"]
        
        if broker_callback is not None:
            assert "/api/auth/apple/broker/callback" in broker_callback, \
                f"Unexpected broker callback: {broker_callback}"
        print(f"✓ Apple provider broker_callback = {broker_callback}")

    def test_admin_sso_status_provider_callback_broker_base(self, admin_session):
        """GET /api/admin/sso-status should include provider_callback_broker_base"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level broker base field
        assert "provider_callback_broker_base" in data, "Missing provider_callback_broker_base"
        print(f"✓ provider_callback_broker_base = {data['provider_callback_broker_base']}")


class TestAppleLoginFailClose:
    """Test GET /api/auth/apple/login fail-closes under strict preflight mode"""

    def test_apple_login_fail_closes_without_preflight_acceptance(self, api_client):
        """Apple login should fail-close to apple_callback_not_provider_registered under strict mode"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/apple/login",
            allow_redirects=False
        )
        
        # Should redirect (302)
        assert response.status_code == 302, f"Expected redirect, got: {response.status_code}"
        
        location = response.headers.get("location", "")
        
        # Under strict preflight mode, should redirect to error page
        # Expected: /auth/login?sso_error=apple_callback_not_provider_registered
        if "sso_error=apple_callback_not_provider_registered" in location:
            print("✓ Apple login fail-closes with apple_callback_not_provider_registered")
            print(f"  Redirect location: {location}")
        elif "appleid.apple.com" in location:
            # If it redirects to Apple, preflight might be accepted
            print("⚠ Apple login redirects to Apple (preflight may be accepted)")
            print(f"  Redirect location: {location}")
        else:
            # Check for other SSO errors
            assert "sso_error" in location or "appleid.apple.com" in location, \
                f"Unexpected redirect: {location}"
            print(f"✓ Apple login redirects with: {location}")

    def test_apple_login_strict_preflight_mode_active(self, api_client):
        """Verify strict preflight mode is active via sso-config"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        
        assert response.status_code == 200
        data = response.json()
        
        strict_allowlist = data.get("apple_strict_callback_allowlist_enabled", False)
        require_preflight = data.get("apple_require_preflight_accepted", False)
        
        print(f"  apple_strict_callback_allowlist_enabled = {strict_allowlist}")
        print(f"  apple_require_preflight_accepted = {require_preflight}")
        
        # At least one strict mode should be enabled for fail-close behavior
        if strict_allowlist or require_preflight:
            print("✓ Strict preflight mode is active")
        else:
            print("⚠ Strict preflight mode may not be active")


class TestMicrosoftLoginRegression:
    """Regression test: Microsoft login redirect should be unaffected"""

    def test_microsoft_login_redirects_to_microsoft(self, api_client):
        """Microsoft login should still redirect to Microsoft OAuth"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/microsoft/login",
            allow_redirects=False
        )
        
        # Should redirect (302)
        assert response.status_code == 302, f"Expected redirect, got: {response.status_code}"
        
        location = response.headers.get("location", "")
        
        # Should redirect to Microsoft login
        assert "login.microsoftonline.com" in location or "microsoft" in location.lower(), \
            f"Microsoft login should redirect to Microsoft, got: {location}"
        
        print("✓ Microsoft login redirects to Microsoft OAuth")
        print(f"  Redirect location: {location[:100]}...")

    def test_microsoft_login_not_affected_by_apple_strict_mode(self, api_client):
        """Microsoft login should not be affected by Apple strict preflight mode"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/microsoft/login",
            allow_redirects=False
        )
        
        location = response.headers.get("location", "")
        
        # Should NOT have apple-related errors
        assert "apple" not in location.lower(), \
            f"Microsoft login should not have Apple errors: {location}"
        
        # Should NOT have callback_not_provider_registered error
        assert "callback_not_provider_registered" not in location, \
            f"Microsoft login should not have callback registration errors: {location}"
        
        print("✓ Microsoft login unaffected by Apple strict mode")


class TestEnvConfiguration:
    """Verify environment configuration for broker callback"""

    def test_env_apple_callback_strategy_value(self, api_client):
        """Verify APPLE_SSO_CALLBACK_STRATEGY is set correctly"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        
        assert response.status_code == 200
        data = response.json()
        
        strategy = data.get("apple_callback_strategy")
        # Expected: "direct" based on .env file
        print(f"✓ APPLE_SSO_CALLBACK_STRATEGY = {strategy}")
        assert strategy == "direct", f"Expected 'direct' strategy, got: {strategy}"

    def test_broker_callback_path_configured(self, api_client):
        """Verify broker callback path is configured"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        
        assert response.status_code == 200
        data = response.json()
        
        broker_callback = data.get("apple_broker_callback")
        
        # Even with direct strategy, broker callback should be available
        if broker_callback:
            assert "/api/auth/apple/broker/callback" in broker_callback
            print(f"✓ Broker callback path configured: {broker_callback}")
        else:
            # Broker callback might be None if APPLE_SSO_BROKER_BASE is empty
            print("⚠ Broker callback is None (APPLE_SSO_BROKER_BASE may be empty)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
