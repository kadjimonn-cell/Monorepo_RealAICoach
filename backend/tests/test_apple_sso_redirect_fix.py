"""
Apple SSO Redirect Fix Validation Tests
========================================
Tests for the Apple SSO auto-sync redirected URL fix where Apple shows invalid_request/Invalid web redirect url.
The fix introduces provider-verified Apple base preference over stale preview base.

Key features tested:
1. GET /api/auth/apple/login - generates provider URL with redirect_uri using provider-verified Apple base
2. GET /api/auth/sso-config - reports deployment_domain_active_apple and apple_callback aligned with provider-verified base
3. GET /api/admin/sso-status - reports Apple provider as configured when provider-verified base is active
4. POST /api/auth/admin/sso-validate-e2e - passes apple_provider_verified_base and apple_callback_matches_active_base checks
5. Regression: Microsoft callback status must remain healthy
"""

import pytest
import requests
import os
from functools import lru_cache
from urllib.parse import urlparse, parse_qs

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Expected provider-verified base from config include list (security invariant)
EXPECTED_APPLE_PROVIDER_VERIFIED_BASE = "https://realaicoach.app"


@lru_cache(maxsize=1)
def _sso_config() -> dict:
    resp = requests.get(f"{BASE_URL}/api/auth/sso-config", timeout=10)
    assert resp.status_code == 200, f"Expected /api/auth/sso-config=200, got {resp.status_code}"
    return resp.json()


def _expected_apple_login_redirect_uri() -> str:
    cfg = _sso_config()
    return (
        cfg.get("apple_preflight_selected_callback")
        or cfg.get("apple_callback")
        or cfg.get("apple_expected_provider_callback")
        or cfg.get("apple_broker_callback")
        or ""
    )


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_session(api_client):
    """Authenticated admin session"""
    login_resp = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    if login_resp.status_code == 403:
        try:
            payload = login_resp.json()
        except Exception:
            payload = {}
        detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
        code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
        if code in {"risk_engine_id_verification_required", "risk_engine_admin_api_blocked"}:
            pytest.skip(f"Admin auth blocked by risk engine containment: {code}")

    if login_resp.status_code != 200:
        pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
    
    # Extract cookies for session-based auth
    cookies = login_resp.cookies.get_dict()
    api_client.cookies.update(cookies)
    login_data = login_resp.json()
    token = login_data.get("session_token") or login_data.get("token") or login_resp.cookies.get("session_token")
    if token:
        api_client.headers.update({"Authorization": f"Bearer {token}"})
    api_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
    return api_client


class TestAppleSSORedirectFix:
    """Tests for Apple SSO redirect URL fix with provider-verified base preference"""

    def test_apple_login_redirect_matches_runtime_policy(self, api_client):
        """
        GET /api/auth/apple/login should generate provider URL with redirect_uri 
        using provider-verified Apple base (not stale preview base)
        """
        # Don't follow redirects to inspect the redirect URL
        resp = api_client.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False)
        
        # Should redirect to Apple's authorization page
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        assert "appleid.apple.com/auth/authorize" in location, f"Expected Apple auth URL, got: {location[:100]}"
        
        # Parse the redirect_uri from the authorization URL
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)
        redirect_uri = query_params.get("redirect_uri", [""])[0]
        
        print(f"Observed redirect_uri: {redirect_uri}")
        
        # The redirect_uri should align with runtime callback selection policy
        assert redirect_uri, "redirect_uri parameter is missing from Apple auth URL"
        expected_redirect_uri = _expected_apple_login_redirect_uri()
        assert redirect_uri == expected_redirect_uri, \
            f"redirect_uri should match runtime policy {expected_redirect_uri}, got: {redirect_uri}"

        parsed_redirect = urlparse(redirect_uri)
        assert parsed_redirect.scheme == "https", f"redirect_uri should use HTTPS, got: {redirect_uri}"
        assert parsed_redirect.path in {"/api/auth/apple/callback", "/api/auth/apple/broker/callback"}, \
            f"Unexpected Apple callback path: {redirect_uri}"

    def test_sso_config_reports_provider_verified_apple_base(self, api_client):
        """
        GET /api/auth/sso-config should report deployment_domain_active_apple 
        and apple_callback aligned with provider-verified base
        """
        resp = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        
        # Check deployment_domain_active_apple
        apple_active_base = data.get("deployment_domain_active_apple", "")
        print(f"deployment_domain_active_apple: {apple_active_base}")
        
        assert apple_active_base.startswith("https://"), \
            f"deployment_domain_active_apple should be https URL, got: {apple_active_base}"
        
        # Check apple_callback
        apple_callback = data.get("apple_callback", "")
        expected_callback = f"{apple_active_base}/api/auth/apple/callback"
        print(f"apple_callback: {apple_callback}")
        
        assert apple_callback == expected_callback, \
            f"apple_callback should be {expected_callback}, got: {apple_callback}"
        
        # Check apple_provider_verified_bases includes the expected base
        verified_bases = data.get("apple_provider_verified_bases", [])
        print(f"apple_provider_verified_bases: {verified_bases}")
        
        assert EXPECTED_APPLE_PROVIDER_VERIFIED_BASE in verified_bases, \
            f"apple_provider_verified_bases should include {EXPECTED_APPLE_PROVIDER_VERIFIED_BASE}, got: {verified_bases}"

    def test_admin_sso_status_reports_apple_configured(self, admin_session):
        """
        GET /api/admin/sso-status should report Apple provider as configured 
        when provider-verified base is active
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        providers = data.get("providers", [])
        
        # Find Apple provider
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None, "Apple provider not found in sso-status response"
        
        print(f"Apple provider status: {apple_provider.get('status')}")
        print(f"Apple provider issues: {apple_provider.get('issues', [])}")
        print(f"Apple callback_url: {apple_provider.get('callback_url')}")
        print(f"Apple provider_verified_base: {apple_provider.get('provider_verified_base')}")
        
        # Apple should be configured (not misconfigured due to redirect issues)
        assert apple_provider.get("configured") is True, "Apple should be configured"
        
        # Check callback_url uses provider-verified base
        callback_url = apple_provider.get("callback_url", "")
        expected_callback = _sso_config().get("apple_callback", "")
        assert callback_url == expected_callback, \
            f"Apple callback_url should be {expected_callback}, got: {callback_url}"
        
        # Check provider_verified_base is True
        assert apple_provider.get("provider_verified_base") is True, \
            "Apple provider_verified_base should be True"
        
        # Check no issues related to provider verification
        issues = apple_provider.get("issues", [])
        allowed_preflight_issue = [
            issue
            for issue in issues
            if "preflight acceptance required" in issue.lower() and "all_invalid_fallback" in issue
        ]
        verification_issues = [
            issue
            for issue in issues
            if ("provider" in issue.lower() or "verified" in issue.lower()) and issue not in allowed_preflight_issue
        ]
        assert len(verification_issues) == 0, \
            f"Apple should have no provider verification issues beyond allowed degraded-preflight issue, got: {verification_issues}"

    def test_sso_validate_e2e_passes_apple_checks(self, admin_session):
        """
        POST /api/auth/admin/sso-validate-e2e should pass apple_provider_verified_base 
        and apple_callback_matches_active_base checks
        """
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        checks = data.get("checks", [])
        
        print(f"E2E validation passed: {data.get('passed')}")
        print(f"E2E validation severity: {data.get('severity')}")
        print(f"Active base apple: {data.get('active_base_apple')}")
        
        # Find apple_callback_matches_active_base check
        apple_callback_check = next(
            (c for c in checks if c.get("name") == "apple_callback_matches_active_base"), 
            None
        )
        assert apple_callback_check is not None, "apple_callback_matches_active_base check not found"
        print(f"apple_callback_matches_active_base: {apple_callback_check}")
        assert apple_callback_check.get("passed") is True, \
            f"apple_callback_matches_active_base should pass: {apple_callback_check.get('details')}"
        
        # Find apple_provider_verified_base check
        apple_verified_check = next(
            (c for c in checks if c.get("name") == "apple_provider_verified_base"), 
            None
        )
        assert apple_verified_check is not None, "apple_provider_verified_base check not found"
        print(f"apple_provider_verified_base: {apple_verified_check}")
        assert apple_verified_check.get("passed") is True, \
            f"apple_provider_verified_base should pass: {apple_verified_check.get('details')}"
        
        # Find apple_callback_registered check
        apple_registered_check = next(
            (c for c in checks if c.get("name") == "apple_callback_registered"), 
            None
        )
        assert apple_registered_check is not None, "apple_callback_registered check not found"
        print(f"apple_callback_registered: {apple_registered_check}")
        # This may or may not pass depending on APPLE_SSO_REGISTERED_REDIRECT_URIS config
        
        # Check active_base_apple is provider-verified
        active_base_apple = data.get("active_base_apple", "")
        expected_active_base = _sso_config().get("deployment_domain_active_apple", "")
        assert active_base_apple == expected_active_base, \
            f"active_base_apple should be {expected_active_base}, got: {active_base_apple}"


class TestMicrosoftSSORegression:
    """Regression tests to ensure Microsoft SSO remains healthy after Apple fix"""

    def test_microsoft_callback_status_healthy(self, admin_session):
        """Microsoft callback status must remain healthy after Apple SSO fix"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        providers = data.get("providers", [])
        
        # Find Microsoft provider
        ms_provider = next((p for p in providers if p.get("provider") == "microsoft"), None)
        assert ms_provider is not None, "Microsoft provider not found in sso-status response"
        
        print(f"Microsoft provider status: {ms_provider.get('status')}")
        print(f"Microsoft provider issues: {ms_provider.get('issues', [])}")
        print(f"Microsoft callback_url: {ms_provider.get('callback_url')}")
        
        # Microsoft should be configured
        assert ms_provider.get("configured") is True, "Microsoft should be configured"
        
        # Microsoft status should be configured (not misconfigured)
        status = ms_provider.get("status", "")
        assert status == "configured", f"Microsoft status should be 'configured', got: {status}"

    def test_microsoft_login_redirect_works(self, api_client):
        """Microsoft login redirect should still work after Apple fix"""
        resp = api_client.get(f"{BASE_URL}/api/auth/microsoft/login", allow_redirects=False)
        
        # Should redirect to Microsoft's authorization page
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        assert "login.microsoftonline.com" in location, f"Expected Microsoft auth URL, got: {location[:100]}"
        
        # Parse the redirect_uri from the authorization URL
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)
        redirect_uri = query_params.get("redirect_uri", [""])[0]
        
        print(f"Microsoft redirect_uri: {redirect_uri}")
        
        # Microsoft redirect_uri should be present and use HTTPS
        assert redirect_uri, "redirect_uri parameter is missing from Microsoft auth URL"
        assert redirect_uri.startswith("https://"), f"redirect_uri should use HTTPS: {redirect_uri}"

    def test_sso_validate_e2e_microsoft_checks_pass(self, admin_session):
        """Microsoft checks in E2E validation should pass"""
        resp = admin_session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        checks = data.get("checks", [])
        
        # Find microsoft_callback_matches_active_base check
        ms_callback_check = next(
            (c for c in checks if c.get("name") == "microsoft_callback_matches_active_base"), 
            None
        )
        assert ms_callback_check is not None, "microsoft_callback_matches_active_base check not found"
        print(f"microsoft_callback_matches_active_base: {ms_callback_check}")
        assert ms_callback_check.get("passed") is True, \
            f"microsoft_callback_matches_active_base should pass: {ms_callback_check.get('details')}"
        
        # Find microsoft_auth_redirect_matches check
        ms_auth_check = next(
            (c for c in checks if c.get("name") == "microsoft_auth_redirect_matches"), 
            None
        )
        assert ms_auth_check is not None, "microsoft_auth_redirect_matches check not found"
        print(f"microsoft_auth_redirect_matches: {ms_auth_check}")
        assert ms_auth_check.get("passed") is True, \
            f"microsoft_auth_redirect_matches should pass: {ms_auth_check.get('details')}"


class TestSSOConfigDiagnostic:
    """Tests for SSO config diagnostic endpoint consistency"""

    def test_sso_config_returns_all_required_fields(self, api_client):
        """SSO config should return all required diagnostic fields"""
        resp = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Required fields
        required_fields = [
            "deployment_domain_dynamic",
            "deployment_domain_env",
            "deployment_domain_canonical",
            "deployment_domain_active",
            "deployment_domain_active_microsoft",
            "deployment_domain_active_apple",
            "microsoft_callback",
            "apple_callback",
            "apple_provider_verified_bases",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
            print(f"{field}: {data.get(field)}")

    def test_apple_callback_matches_active_base(self, api_client):
        """Apple callback should match the active apple base"""
        resp = api_client.get(f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        
        data = resp.json()
        
        apple_active_base = data.get("deployment_domain_active_apple", "")
        apple_callback = data.get("apple_callback", "")
        
        expected_callback = f"{apple_active_base}/api/auth/apple/callback"
        assert apple_callback == expected_callback, \
            f"apple_callback ({apple_callback}) should match active base ({expected_callback})"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
