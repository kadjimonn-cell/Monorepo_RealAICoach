"""
SSO Redirect Controls - Checkpoint B Testing
Tests for new SSO redirect control features:
- GET /api/auth/sso-config exposes provider_redirect_resolution_mode, registered_redirect_fallback_enabled, registered_uri_sync_mode
- POST /api/auth/admin/sso-validate-e2e returns 200 and passed=true
- POST /api/auth/admin/sso-provider-registration/align returns structured result
- GET /api/admin/sso-status includes provider redirect control fields
- SSO callback init endpoints respond: /api/auth/microsoft/init and /api/auth/apple/init
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def retry_request(method, url, max_retries=3, **kwargs):
    """Retry request on transient 502 errors."""
    for attempt in range(max_retries):
        resp = method(url, **kwargs)
        if resp.status_code != 502:
            return resp
        if attempt < max_retries - 1:
            time.sleep(2)
    return resp


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    # Add CSRF header for POST requests
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login as admin
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if login_resp.status_code != 200:
        pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
    
    return session


class TestSSOConfigEndpoint:
    """Tests for GET /api/auth/sso-config endpoint."""
    
    def test_sso_config_returns_200(self):
        """SSO config endpoint should return 200."""
        resp = retry_request(requests.get, f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    
    def test_sso_config_has_provider_redirect_resolution_mode(self):
        """SSO config should expose provider_redirect_resolution_mode field."""
        resp = retry_request(requests.get, f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "provider_redirect_resolution_mode" in data, \
            f"Missing provider_redirect_resolution_mode in response: {list(data.keys())}"
        
        # Should be one of the valid modes
        mode = data["provider_redirect_resolution_mode"]
        assert mode in ["canonical_first", "registered_first"], \
            f"Invalid mode: {mode}"
    
    def test_sso_config_has_registered_redirect_fallback_enabled(self):
        """SSO config should expose registered_redirect_fallback_enabled field."""
        resp = retry_request(requests.get, f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "registered_redirect_fallback_enabled" in data, \
            f"Missing registered_redirect_fallback_enabled in response: {list(data.keys())}"
        
        # Should be a boolean
        assert isinstance(data["registered_redirect_fallback_enabled"], bool), \
            f"Expected boolean, got {type(data['registered_redirect_fallback_enabled'])}"
    
    def test_sso_config_has_registered_uri_sync_mode(self):
        """SSO config should expose registered_uri_sync_mode field."""
        resp = retry_request(requests.get, f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "registered_uri_sync_mode" in data, \
            f"Missing registered_uri_sync_mode in response: {list(data.keys())}"
        
        # Should be a string (preserve or rewrite_to_current)
        mode = data["registered_uri_sync_mode"]
        assert isinstance(mode, str), f"Expected string, got {type(mode)}"
        assert mode in ["preserve", "rewrite_to_current"], \
            f"Unexpected sync mode: {mode}"
    
    def test_sso_config_has_deployment_domain_fields(self):
        """SSO config should have deployment domain fields."""
        resp = retry_request(requests.get, f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        data = resp.json()
        
        required_fields = [
            "deployment_domain_active",
            "deployment_domain_active_microsoft",
            "deployment_domain_active_apple",
            "microsoft_callback",
            "apple_callback",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestSSOValidateE2E:
    """Tests for POST /api/auth/admin/sso-validate-e2e endpoint."""
    
    def test_sso_validate_e2e_requires_admin(self):
        """SSO validate E2E should require admin authentication."""
        resp = requests.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        # Should return 401 or 403 without auth
        assert resp.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {resp.status_code}"
    
    def test_sso_validate_e2e_returns_200_with_admin(self, admin_session):
        """SSO validate E2E should return 200 with admin auth."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    
    def test_sso_validate_e2e_has_passed_field(self, admin_session):
        """SSO validate E2E should return passed field."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "passed" in data, f"Missing 'passed' field in response: {list(data.keys())}"
        assert isinstance(data["passed"], bool), f"Expected boolean, got {type(data['passed'])}"
    
    def test_sso_validate_e2e_has_checks_array(self, admin_session):
        """SSO validate E2E should return checks array."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "checks" in data, "Missing 'checks' field in response"
        assert isinstance(data["checks"], list), f"Expected list, got {type(data['checks'])}"
        
        # Each check should have name, passed, details
        for check in data["checks"]:
            assert "name" in check, f"Check missing 'name': {check}"
            assert "passed" in check, f"Check missing 'passed': {check}"
    
    def test_sso_validate_e2e_passed_is_true(self, admin_session):
        """SSO validate E2E should return passed=true after Checkpoint B changes."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert resp.status_code == 200
        data = resp.json()
        
        # After Checkpoint B implementation, validation should pass
        assert data.get("passed") is True, \
            f"Expected passed=true, got {data.get('passed')}. Checks: {data.get('checks', [])}"


class TestSSOProviderRegistrationAlign:
    """Tests for POST /api/auth/admin/sso-provider-registration/align endpoint."""
    
    def test_sso_provider_registration_align_requires_admin(self):
        """SSO provider registration align should require admin authentication."""
        resp = requests.post(f"{BASE_URL}/api/auth/admin/sso-provider-registration/align")
        assert resp.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {resp.status_code}"
    
    def test_sso_provider_registration_align_returns_200(self, admin_session):
        """SSO provider registration align should return 200 with admin auth."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-provider-registration/align")
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    
    def test_sso_provider_registration_align_has_structured_result(self, admin_session):
        """SSO provider registration align should return structured result."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-provider-registration/align")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should have ok field
        assert "ok" in data, f"Missing 'ok' field: {list(data.keys())}"
        
        # Should have active_base fields
        assert "active_base" in data, "Missing 'active_base' field"
        
        # Should have microsoft and apple sections
        assert "microsoft" in data, "Missing 'microsoft' section"
        assert "apple" in data, "Missing 'apple' section"
    
    def test_sso_provider_registration_align_microsoft_structure(self, admin_session):
        """Microsoft section should have expected structure."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-provider-registration/align")
        assert resp.status_code == 200
        data = resp.json()
        
        ms = data.get("microsoft", {})
        assert "attempted" in ms, f"Missing 'attempted' in microsoft: {ms.keys()}"
        assert "aligned" in ms, f"Missing 'aligned' in microsoft: {ms.keys()}"
        assert "required_callbacks" in ms, f"Missing 'required_callbacks' in microsoft: {ms.keys()}"
    
    def test_sso_provider_registration_align_apple_structure(self, admin_session):
        """Apple section should have expected structure."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-provider-registration/align")
        assert resp.status_code == 200
        data = resp.json()
        
        apple = data.get("apple", {})
        assert "attempted" in apple, f"Missing 'attempted' in apple: {apple.keys()}"
        assert "manual_required" in apple, f"Missing 'manual_required' in apple: {apple.keys()}"
        assert "required_callbacks" in apple, f"Missing 'required_callbacks' in apple: {apple.keys()}"


class TestAdminSSOStatus:
    """Tests for GET /api/admin/sso-status endpoint."""
    
    def test_admin_sso_status_returns_200(self, admin_session):
        """Admin SSO status should return 200."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200, \
            f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    
    def test_admin_sso_status_has_provider_redirect_resolution_mode(self, admin_session):
        """Admin SSO status should include provider_redirect_resolution_mode."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "provider_redirect_resolution_mode" in data, \
            f"Missing provider_redirect_resolution_mode: {list(data.keys())}"
    
    def test_admin_sso_status_has_registered_redirect_fallback_enabled(self, admin_session):
        """Admin SSO status should include registered_redirect_fallback_enabled."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "registered_redirect_fallback_enabled" in data, \
            f"Missing registered_redirect_fallback_enabled: {list(data.keys())}"
    
    def test_admin_sso_status_has_registered_uri_sync_mode(self, admin_session):
        """Admin SSO status should include registered_uri_sync_mode."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "registered_uri_sync_mode" in data, \
            f"Missing registered_uri_sync_mode: {list(data.keys())}"
    
    def test_admin_sso_status_has_provider_registration_alignment(self, admin_session):
        """Admin SSO status should include provider_registration_alignment trigger info."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "provider_registration_alignment" in data, \
            f"Missing provider_registration_alignment: {list(data.keys())}"
    
    def test_admin_sso_status_has_providers_array(self, admin_session):
        """Admin SSO status should include providers array."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "providers" in data, f"Missing providers: {list(data.keys())}"
        assert isinstance(data["providers"], list), f"Expected list, got {type(data['providers'])}"
        
        # Should have at least Google, Microsoft, Apple
        provider_names = [p.get("provider") for p in data["providers"]]
        assert "microsoft" in provider_names, f"Missing microsoft provider: {provider_names}"
        assert "apple" in provider_names, f"Missing apple provider: {provider_names}"


class TestSSOCallbackInitEndpoints:
    """Tests for SSO callback init endpoints."""
    
    def test_microsoft_init_responds(self):
        """Microsoft init endpoint should respond (redirect or error, not 500)."""
        resp = retry_request(
            requests.get,
            f"{BASE_URL}/api/auth/microsoft/init",
            allow_redirects=False
        )
        # Should be a redirect (302/307) or a client error (400/401), not a server error
        assert resp.status_code < 500, \
            f"Microsoft init returned server error: {resp.status_code}: {resp.text[:300]}"
        
        # Typically returns 302 redirect to Microsoft login
        # or 400 if missing parameters
        assert resp.status_code in [200, 302, 307, 400, 401, 403], \
            f"Unexpected status: {resp.status_code}"
    
    def test_apple_init_responds(self):
        """Apple init endpoint should respond (redirect or error, not 500)."""
        resp = retry_request(
            requests.get,
            f"{BASE_URL}/api/auth/apple/init",
            allow_redirects=False
        )
        # Should be a redirect (302/307) or a client error (400/401), not a server error
        assert resp.status_code < 500, \
            f"Apple init returned server error: {resp.status_code}: {resp.text[:300]}"
        
        # Typically returns 302 redirect to Apple login
        # or 400 if missing parameters
        assert resp.status_code in [200, 302, 307, 400, 401, 403], \
            f"Unexpected status: {resp.status_code}"


class TestEnvConfigValues:
    """Tests to verify env config values are correctly exposed."""
    
    def test_sso_registered_uri_sync_mode_is_preserve(self):
        """SSO_REGISTERED_URI_SYNC_MODE should be 'preserve' per .env."""
        resp = retry_request(requests.get, f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        data = resp.json()
        
        # Per backend/.env: SSO_REGISTERED_URI_SYNC_MODE=preserve
        assert data.get("registered_uri_sync_mode") == "preserve", \
            f"Expected 'preserve', got {data.get('registered_uri_sync_mode')}"
    
    def test_sso_provider_redirect_resolution_mode_is_canonical_first(self):
        """SSO_PROVIDER_REDIRECT_RESOLUTION_MODE should be 'canonical_first' per .env."""
        resp = retry_request(requests.get, f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        data = resp.json()
        
        # Per backend/.env: SSO_PROVIDER_REDIRECT_RESOLUTION_MODE=canonical_first
        assert data.get("provider_redirect_resolution_mode") == "canonical_first", \
            f"Expected 'canonical_first', got {data.get('provider_redirect_resolution_mode')}"
    
    def test_sso_allow_registered_redirect_uri_as_active_base_is_false(self):
        """SSO_ALLOW_REGISTERED_REDIRECT_URI_AS_ACTIVE_BASE should be false per .env."""
        resp = retry_request(requests.get, f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        data = resp.json()
        
        # Per backend/.env: SSO_ALLOW_REGISTERED_REDIRECT_URI_AS_ACTIVE_BASE=false
        assert data.get("registered_redirect_fallback_enabled") is False, \
            f"Expected False, got {data.get('registered_redirect_fallback_enabled')}"


class TestSchedulerJobRegistration:
    """Tests to verify scheduler job is registered."""
    
    def test_system_status_shows_scheduler_healthy(self, admin_session):
        """System status should show scheduler is healthy."""
        resp = admin_session.get(f"{BASE_URL}/api/system/status")
        assert resp.status_code == 200
        data = resp.json()
        
        checks = data.get("checks", {})
        scheduler = checks.get("scheduler", {})
        
        # Scheduler should be healthy or degraded (not error)
        assert scheduler.get("status") in ["healthy", "degraded"], \
            f"Scheduler status: {scheduler}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
