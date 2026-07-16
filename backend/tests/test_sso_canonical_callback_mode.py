"""
Test Suite: SSO Canonical Provider Callback Mode (Iteration 104)

Tests the canonical permanent auth path (A+A): Microsoft auto-alignment + Apple canonical callback strategy.
Validates that SSO callbacks use the canonical domain (https://realaicoach.app) instead of preview host.

Features tested:
1. GET /api/auth/sso-config - canonical provider callback mode with active microsoft/apple base
2. GET /api/auth/microsoft/init - returns callback and auth_url redirect_uri on canonical domain
3. GET /api/auth/apple/init - returns callback on canonical domain
4. POST /api/auth/admin/sso-validate-e2e - returns passed=true with strict callbacks
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
CANONICAL_DOMAIN = "https://realaicoach.app"

# Test credentials from test_credentials.md
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
    """Authenticated admin session with CSRF header"""
    # Add CSRF header for POST requests
    api_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        # Session cookie is set automatically
        return api_client
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


class TestSSOConfigDiagnostic:
    """Tests for GET /api/auth/sso-config endpoint"""
    
    def test_sso_config_returns_200(self, api_client):
        """SSO config endpoint should return 200"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ SSO config endpoint returns 200")
    
    def test_sso_config_has_canonical_provider_callback_mode(self, api_client):
        """SSO config should report canonical_provider_callback_mode"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        assert "canonical_provider_callback_mode" in data, "Missing canonical_provider_callback_mode field"
        print(f"✓ canonical_provider_callback_mode = {data['canonical_provider_callback_mode']}")
    
    def test_sso_config_microsoft_active_base_is_canonical(self, api_client):
        """Microsoft active base should be the canonical domain"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        ms_active_base = data.get("deployment_domain_active_microsoft", "")
        assert ms_active_base == CANONICAL_DOMAIN, \
            f"Expected Microsoft active base '{CANONICAL_DOMAIN}', got '{ms_active_base}'"
        print(f"✓ Microsoft active base = {ms_active_base}")
    
    def test_sso_config_apple_active_base_is_canonical(self, api_client):
        """Apple active base should be the canonical domain"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        apple_active_base = data.get("deployment_domain_active_apple", "")
        assert apple_active_base == CANONICAL_DOMAIN, \
            f"Expected Apple active base '{CANONICAL_DOMAIN}', got '{apple_active_base}'"
        print(f"✓ Apple active base = {apple_active_base}")
    
    def test_sso_config_microsoft_callback_uses_canonical(self, api_client):
        """Microsoft callback should use canonical domain"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        ms_callback = data.get("microsoft_callback", "")
        expected_callback = f"{CANONICAL_DOMAIN}/api/auth/microsoft/callback"
        assert ms_callback == expected_callback, \
            f"Expected Microsoft callback '{expected_callback}', got '{ms_callback}'"
        print(f"✓ Microsoft callback = {ms_callback}")
    
    def test_sso_config_apple_callback_uses_canonical(self, api_client):
        """Apple callback should use canonical domain"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        apple_callback = data.get("apple_callback", "")
        expected_callback = f"{CANONICAL_DOMAIN}/api/auth/apple/callback"
        assert apple_callback == expected_callback, \
            f"Expected Apple callback '{expected_callback}', got '{apple_callback}'"
        print(f"✓ Apple callback = {apple_callback}")
    
    def test_sso_config_provider_redirect_resolution_mode(self, api_client):
        """Provider redirect resolution mode should be canonical_first"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        mode = data.get("provider_redirect_resolution_mode", "")
        assert mode == "canonical_first", \
            f"Expected provider_redirect_resolution_mode 'canonical_first', got '{mode}'"
        print(f"✓ provider_redirect_resolution_mode = {mode}")
    
    def test_sso_config_registered_uri_sync_mode(self, api_client):
        """Registered URI sync mode should be preserve"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        mode = data.get("registered_uri_sync_mode", "")
        assert mode == "preserve", \
            f"Expected registered_uri_sync_mode 'preserve', got '{mode}'"
        print(f"✓ registered_uri_sync_mode = {mode}")
    
    def test_sso_config_registered_redirect_fallback_disabled(self, api_client):
        """Registered redirect fallback should be disabled"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        fallback = data.get("registered_redirect_fallback_enabled", True)
        assert fallback is False, \
            f"Expected registered_redirect_fallback_enabled False, got {fallback}"
        print(f"✓ registered_redirect_fallback_enabled = {fallback}")


class TestMicrosoftInit:
    """Tests for GET /api/auth/microsoft/init endpoint"""
    
    def test_microsoft_init_returns_200(self, api_client):
        """Microsoft init endpoint should return 200"""
        response = api_client.get(f"{BASE_URL}/api/auth/microsoft/init")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ Microsoft init endpoint returns 200")
    
    def test_microsoft_init_callback_uses_canonical(self, api_client):
        """Microsoft init callback should use canonical domain"""
        response = api_client.get(f"{BASE_URL}/api/auth/microsoft/init")
        assert response.status_code == 200
        data = response.json()
        
        callback = data.get("callback", "")
        expected_callback = f"{CANONICAL_DOMAIN}/api/auth/microsoft/callback"
        assert callback == expected_callback, \
            f"Expected callback '{expected_callback}', got '{callback}'"
        print(f"✓ Microsoft init callback = {callback}")
    
    def test_microsoft_init_auth_url_redirect_uri_uses_canonical(self, api_client):
        """Microsoft init auth_url should contain redirect_uri with canonical domain"""
        response = api_client.get(f"{BASE_URL}/api/auth/microsoft/init")
        assert response.status_code == 200
        data = response.json()
        
        auth_url = data.get("auth_url", "")
        expected_redirect_uri = f"{CANONICAL_DOMAIN}/api/auth/microsoft/callback"
        
        # URL-encoded version
        from urllib.parse import quote
        encoded_redirect = quote(expected_redirect_uri, safe='')
        
        assert expected_redirect_uri in auth_url or encoded_redirect in auth_url, \
            f"Expected auth_url to contain redirect_uri '{expected_redirect_uri}', got auth_url: {auth_url[:200]}..."
        print("✓ Microsoft init auth_url contains canonical redirect_uri")
    
    def test_microsoft_init_has_required_fields(self, api_client):
        """Microsoft init should return all required fields"""
        response = api_client.get(f"{BASE_URL}/api/auth/microsoft/init")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["ok", "provider", "frontend_base", "callback", "login_url", "auth_url"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        assert data["ok"] is True, "Expected ok=True"
        assert data["provider"] == "microsoft", "Expected provider=microsoft"
        print("✓ Microsoft init has all required fields")


class TestAppleInit:
    """Tests for GET /api/auth/apple/init endpoint"""
    
    def test_apple_init_returns_200(self, api_client):
        """Apple init endpoint should return 200"""
        response = api_client.get(f"{BASE_URL}/api/auth/apple/init")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ Apple init endpoint returns 200")
    
    def test_apple_init_callback_uses_canonical(self, api_client):
        """Apple init callback should use canonical domain"""
        response = api_client.get(f"{BASE_URL}/api/auth/apple/init")
        assert response.status_code == 200
        data = response.json()
        
        callback = data.get("callback", "")
        expected_callback = f"{CANONICAL_DOMAIN}/api/auth/apple/callback"
        assert callback == expected_callback, \
            f"Expected callback '{expected_callback}', got '{callback}'"
        print(f"✓ Apple init callback = {callback}")
    
    def test_apple_init_has_required_fields(self, api_client):
        """Apple init should return all required fields"""
        response = api_client.get(f"{BASE_URL}/api/auth/apple/init")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["ok", "provider", "frontend_base", "callback", "client_id", "authorize_url"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        assert data["ok"] is True, "Expected ok=True"
        assert data["provider"] == "apple", "Expected provider=apple"
        print("✓ Apple init has all required fields")


class TestSSOValidateE2E:
    """Tests for POST /api/auth/admin/sso-validate-e2e endpoint"""
    
    def test_sso_validate_e2e_requires_auth(self, api_client):
        """SSO validate E2E should require admin authentication"""
        response = api_client.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert response.status_code in [401, 403], \
            f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        print("✓ SSO validate E2E requires authentication")
    
    def test_sso_validate_e2e_returns_200_for_admin(self, admin_session):
        """SSO validate E2E should return 200 for admin"""
        response = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ SSO validate E2E returns 200 for admin")
    
    def test_sso_validate_e2e_returns_passed_true(self, admin_session):
        """SSO validate E2E should return passed=true with strict callbacks"""
        response = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert response.status_code == 200
        data = response.json()
        
        passed = data.get("passed", False)
        assert passed is True, f"Expected passed=True, got {passed}. Full response: {data}"
        print(f"✓ SSO validate E2E passed = {passed}")
    
    def test_sso_validate_e2e_has_checks_array(self, admin_session):
        """SSO validate E2E should return checks array"""
        response = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert response.status_code == 200
        data = response.json()
        
        checks = data.get("checks", [])
        assert isinstance(checks, list), f"Expected checks to be a list, got {type(checks)}"
        assert len(checks) > 0, "Expected at least one check"
        print(f"✓ SSO validate E2E has {len(checks)} checks")
    
    def test_sso_validate_e2e_all_checks_pass(self, admin_session):
        """All SSO validate E2E checks should pass"""
        response = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert response.status_code == 200
        data = response.json()
        
        checks = data.get("checks", [])
        failed_checks = [c for c in checks if not c.get("passed", False)]
        
        if failed_checks:
            for fc in failed_checks:
                print(f"  ✗ Failed check: {fc.get('name')} - {fc.get('details')}")
        
        assert len(failed_checks) == 0, \
            f"Expected all checks to pass, but {len(failed_checks)} failed: {failed_checks}"
        print(f"✓ All {len(checks)} SSO validate E2E checks passed")


class TestMicrosoftLoginRedirect:
    """Tests for GET /api/auth/microsoft/login endpoint (302 redirect)"""
    
    def test_microsoft_login_returns_302(self, api_client):
        """Microsoft login should return 302 redirect"""
        response = api_client.get(f"{BASE_URL}/api/auth/microsoft/login", allow_redirects=False)
        assert response.status_code == 302, f"Expected 302, got {response.status_code}"
        print("✓ Microsoft login returns 302 redirect")
    
    def test_microsoft_login_redirect_contains_canonical_callback(self, api_client):
        """Microsoft login redirect should contain canonical callback in redirect_uri"""
        response = api_client.get(f"{BASE_URL}/api/auth/microsoft/login", allow_redirects=False)
        assert response.status_code == 302
        
        location = response.headers.get("Location", "")
        expected_callback = f"{CANONICAL_DOMAIN}/api/auth/microsoft/callback"
        
        from urllib.parse import quote
        encoded_callback = quote(expected_callback, safe='')
        
        assert expected_callback in location or encoded_callback in location, \
            f"Expected redirect Location to contain '{expected_callback}', got: {location[:200]}..."
        print("✓ Microsoft login redirect contains canonical callback")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
