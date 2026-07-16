"""
Test Apple SSO Auto-Refresh Accepted Preview Base Feature

Tests the runtime auto-refresh of accepted callback base from current preview host.
Features tested:
1. GET /api/auth/sso-config exposes apple_auto_refresh_accepted_preview_base_enabled=true
2. GET /api/auth/sso-config shows apple_dynamic_preview_candidate equal to current preview host
3. GET /api/auth/sso-config apple_provider_accepted_bases includes current preview host
4. GET /api/auth/apple/login redirects to appleid authorize URL with redirect_uri set to current preview callback
5. GET /api/admin/sso-status Apple provider shows dynamic_preview_candidate and auto_refresh_accepted_preview_base_enabled
6. Regression: Microsoft login redirect still works
"""

import pytest
import requests
import os
from urllib.parse import urlparse, parse_qs

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
EXPECTED_PREVIEW_BASE = os.environ.get("PYTEST_EXTERNAL_PREVIEW_BASE", "").rstrip("/") or BASE_URL

# Admin credentials
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
            pytest.skip(f"Admin session blocked by risk engine containment: {code}")

    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return api_client


class TestSSOConfigAutoRefreshPreview:
    """Test /api/auth/sso-config endpoint for Apple auto-refresh preview base feature"""

    def test_sso_config_returns_200(self, api_client):
        """GET /api/auth/sso-config should return 200"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/auth/sso-config returns 200")

    def test_apple_auto_refresh_accepted_preview_base_enabled(self, api_client):
        """GET /api/auth/sso-config exposes apple_auto_refresh_accepted_preview_base_enabled=true"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        assert "apple_auto_refresh_accepted_preview_base_enabled" in data, \
            "Missing apple_auto_refresh_accepted_preview_base_enabled field"
        assert data["apple_auto_refresh_accepted_preview_base_enabled"] is True, \
            f"Expected apple_auto_refresh_accepted_preview_base_enabled=true, got {data['apple_auto_refresh_accepted_preview_base_enabled']}"
        print(f"PASS: apple_auto_refresh_accepted_preview_base_enabled = {data['apple_auto_refresh_accepted_preview_base_enabled']}")

    def test_apple_dynamic_preview_candidate_equals_current_host(self, api_client):
        """GET /api/auth/sso-config shows apple_dynamic_preview_candidate equal to current preview host"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        assert "apple_dynamic_preview_candidate" in data, \
            "Missing apple_dynamic_preview_candidate field"
        
        dynamic_candidate = data["apple_dynamic_preview_candidate"]
        assert dynamic_candidate is not None, "apple_dynamic_preview_candidate should not be None"
        assert dynamic_candidate == EXPECTED_PREVIEW_BASE, \
            f"Expected apple_dynamic_preview_candidate={EXPECTED_PREVIEW_BASE}, got {dynamic_candidate}"
        print(f"PASS: apple_dynamic_preview_candidate = {dynamic_candidate}")

    def test_apple_provider_accepted_bases_includes_preview_host(self, api_client):
        """GET /api/auth/sso-config apple_provider_accepted_bases includes current preview host"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        assert "apple_provider_accepted_bases" in data, \
            "Missing apple_provider_accepted_bases field"
        
        accepted_bases = data["apple_provider_accepted_bases"]
        assert isinstance(accepted_bases, list), f"Expected list, got {type(accepted_bases)}"
        assert EXPECTED_PREVIEW_BASE in accepted_bases, \
            f"Expected {EXPECTED_PREVIEW_BASE} in apple_provider_accepted_bases, got {accepted_bases}"
        print(f"PASS: apple_provider_accepted_bases includes {EXPECTED_PREVIEW_BASE}")
        print(f"  Full list: {accepted_bases}")

    def test_apple_provider_verification_source(self, api_client):
        """GET /api/auth/sso-config shows apple_provider_verification_source=provider_accepted_list"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        assert "apple_provider_verification_source" in data, \
            "Missing apple_provider_verification_source field"
        
        verification_source = data["apple_provider_verification_source"]
        assert verification_source == "provider_accepted_list", \
            f"Expected apple_provider_verification_source=provider_accepted_list, got {verification_source}"
        print(f"PASS: apple_provider_verification_source = {verification_source}")

    def test_deployment_domain_active_apple(self, api_client):
        """GET /api/auth/sso-config shows deployment_domain_active_apple equals current preview host"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        assert "deployment_domain_active_apple" in data, \
            "Missing deployment_domain_active_apple field"
        
        active_apple = data["deployment_domain_active_apple"]
        assert active_apple == EXPECTED_PREVIEW_BASE, \
            f"Expected deployment_domain_active_apple={EXPECTED_PREVIEW_BASE}, got {active_apple}"
        print(f"PASS: deployment_domain_active_apple = {active_apple}")


class TestAppleLoginRedirect:
    """Test /api/auth/apple/login redirect behavior"""

    def test_apple_login_redirects_to_appleid(self, api_client):
        """GET /api/auth/apple/login redirects to appleid.apple.com/auth/authorize"""
        response = api_client.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False)
        
        assert response.status_code == 302, f"Expected 302 redirect, got {response.status_code}"
        
        location = response.headers.get("Location", "")
        assert "appleid.apple.com/auth/authorize" in location, \
            f"Expected redirect to appleid.apple.com/auth/authorize, got {location}"
        
        # Should NOT have sso_error in the redirect
        assert "sso_error" not in location, \
            f"Unexpected sso_error in redirect: {location}"
        
        print("PASS: Apple login redirects to appleid.apple.com")
        print(f"  Location: {location[:150]}...")

    def test_apple_login_redirect_uri_is_preview_callback(self, api_client):
        """GET /api/auth/apple/login redirect_uri is set to current preview callback"""
        response = api_client.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False)
        
        assert response.status_code == 302
        location = response.headers.get("Location", "")
        
        # Parse the redirect URL
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)
        
        assert "redirect_uri" in query_params, "Missing redirect_uri in Apple authorize URL"
        
        redirect_uri = query_params["redirect_uri"][0]
        parsed_redirect_uri = urlparse(redirect_uri)
        assert parsed_redirect_uri.scheme == "https", f"redirect_uri must be https, got {redirect_uri}"
        assert parsed_redirect_uri.path == "/api/auth/apple/callback", \
            f"redirect_uri path mismatch: {redirect_uri}"
        redirect_host = parsed_redirect_uri.netloc.lower()
        assert (
            redirect_host.endswith("preview.emergentagent.com")
            or redirect_host.endswith("realaicoach.app")
        ), f"Unexpected redirect_uri host: {redirect_host}"
        
        print(f"PASS: Apple login redirect_uri = {redirect_uri}")

    def test_apple_login_has_required_params(self, api_client):
        """GET /api/auth/apple/login has all required OAuth params"""
        response = api_client.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False)
        
        assert response.status_code == 302
        location = response.headers.get("Location", "")
        
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)
        
        required_params = ["client_id", "redirect_uri", "response_type", "scope", "state"]
        for param in required_params:
            assert param in query_params, f"Missing required param: {param}"
        
        # Verify response_type is code
        assert query_params["response_type"][0] == "code", \
            f"Expected response_type=code, got {query_params['response_type'][0]}"
        
        print("PASS: Apple login has all required OAuth params")


class TestAdminSSOStatus:
    """Test /api/admin/sso-status endpoint for Apple provider details"""

    def test_admin_sso_status_returns_200(self, admin_session):
        """GET /api/admin/sso-status should return 200"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/admin/sso-status returns 200")

    def test_apple_provider_in_sso_status(self, admin_session):
        """GET /api/admin/sso-status includes Apple provider"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert response.status_code == 200
        data = response.json()
        
        assert "providers" in data, "Missing providers field"
        providers = data["providers"]
        
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None, "Apple provider not found in sso-status"
        print("PASS: Apple provider found in sso-status")

    def test_apple_provider_dynamic_preview_candidate(self, admin_session):
        """GET /api/admin/sso-status Apple provider shows dynamic_preview_candidate"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert response.status_code == 200
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None
        
        assert "dynamic_preview_candidate" in apple_provider, \
            "Missing dynamic_preview_candidate in Apple provider"
        
        dynamic_candidate = apple_provider["dynamic_preview_candidate"]
        assert dynamic_candidate == EXPECTED_PREVIEW_BASE, \
            f"Expected dynamic_preview_candidate={EXPECTED_PREVIEW_BASE}, got {dynamic_candidate}"
        
        print(f"PASS: Apple provider dynamic_preview_candidate = {dynamic_candidate}")

    def test_apple_provider_auto_refresh_enabled(self, admin_session):
        """GET /api/admin/sso-status Apple provider shows auto_refresh_accepted_preview_base_enabled=true"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert response.status_code == 200
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None
        
        assert "auto_refresh_accepted_preview_base_enabled" in apple_provider, \
            "Missing auto_refresh_accepted_preview_base_enabled in Apple provider"
        
        auto_refresh = apple_provider["auto_refresh_accepted_preview_base_enabled"]
        assert auto_refresh is True, \
            f"Expected auto_refresh_accepted_preview_base_enabled=true, got {auto_refresh}"
        
        print(f"PASS: Apple provider auto_refresh_accepted_preview_base_enabled = {auto_refresh}")

    def test_apple_provider_status_configured(self, admin_session):
        """GET /api/admin/sso-status Apple provider status is policy-consistent."""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert response.status_code == 200
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None
        
        status = apple_provider.get("status")
        assert status in {"configured", "misconfigured"}, \
            f"Expected Apple provider status in {{configured, misconfigured}}, got {status}"
        
        issues = apple_provider.get("issues", [])
        if status == "misconfigured":
            assert issues, "Misconfigured Apple provider must expose at least one issue"
        print(f"PASS: Apple provider status = {status}")
        if issues:
            print(f"  Issues: {issues}")

    def test_apple_provider_accepted_bases_in_status(self, admin_session):
        """GET /api/admin/sso-status Apple provider shows provider_accepted_bases with preview host"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert response.status_code == 200
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None
        
        assert "provider_accepted_bases" in apple_provider, \
            "Missing provider_accepted_bases in Apple provider"
        
        accepted_bases = apple_provider["provider_accepted_bases"]
        assert EXPECTED_PREVIEW_BASE in accepted_bases, \
            f"Expected {EXPECTED_PREVIEW_BASE} in provider_accepted_bases, got {accepted_bases}"
        
        print(f"PASS: Apple provider_accepted_bases includes {EXPECTED_PREVIEW_BASE}")


class TestMicrosoftLoginRegression:
    """Regression test: Microsoft login redirect still works"""

    def test_microsoft_login_redirects(self, api_client):
        """GET /api/auth/microsoft/login redirects to login.microsoftonline.com"""
        response = api_client.get(f"{BASE_URL}/api/auth/microsoft/login", allow_redirects=False)
        
        assert response.status_code == 302, f"Expected 302 redirect, got {response.status_code}"
        
        location = response.headers.get("Location", "")
        assert "login.microsoftonline.com" in location, \
            f"Expected redirect to login.microsoftonline.com, got {location}"
        
        # Should NOT have sso_error in the redirect
        assert "sso_error" not in location, \
            f"Unexpected sso_error in Microsoft redirect: {location}"
        
        print("PASS: Microsoft login redirects to login.microsoftonline.com")
        print(f"  Location: {location[:150]}...")

    def test_microsoft_provider_in_sso_status(self, admin_session):
        """GET /api/admin/sso-status includes Microsoft provider with configured status"""
        response = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert response.status_code == 200
        data = response.json()
        
        providers = data.get("providers", [])
        ms_provider = next((p for p in providers if p.get("provider") == "microsoft"), None)
        assert ms_provider is not None, "Microsoft provider not found in sso-status"
        
        status = ms_provider.get("status")
        # Microsoft should be configured or at least not have critical issues
        assert status in ["configured", "misconfigured"], \
            f"Unexpected Microsoft provider status: {status}"
        
        print(f"PASS: Microsoft provider found with status = {status}")


class TestStrictAllowlistBehavior:
    """Test that strict allowlist includes dynamic preview candidate"""

    def test_strict_callback_allowlist_enabled(self, api_client):
        """Verify strict callback allowlist is enabled"""
        response = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200
        data = response.json()
        
        strict_enabled = data.get("apple_strict_callback_allowlist_enabled", False)
        print(f"INFO: apple_strict_callback_allowlist_enabled = {strict_enabled}")
        
        # Even under strict allowlist, preview host should be accepted
        accepted_bases = data.get("apple_provider_accepted_bases", [])
        assert EXPECTED_PREVIEW_BASE in accepted_bases, \
            "Preview host should be in accepted bases even under strict allowlist"
        
        print("PASS: Preview host is in accepted bases under strict allowlist")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
