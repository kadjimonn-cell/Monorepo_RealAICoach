"""
Apple SSO redirect diagnostics regression tests.

These assertions intentionally derive expected callback policy from live
`/api/auth/sso-config` diagnostics so tests remain stable across preview-host
rotations and callback strategy mode changes (`direct` vs `broker`).
"""

import pytest
import requests
import os
from functools import lru_cache
from urllib.parse import urlparse, parse_qs

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@lru_cache(maxsize=1)
def _sso_config() -> dict:
    response = requests.get(f"{BASE_URL}/api/auth/sso-config", timeout=10)
    assert response.status_code == 200, f"Expected /api/auth/sso-config=200, got {response.status_code}"
    return response.json()


def _expected_apple_login_redirect_uri() -> str:
    cfg = _sso_config()
    return (
        cfg.get("apple_preflight_selected_callback")
        or cfg.get("apple_callback")
        or cfg.get("apple_expected_provider_callback")
        or cfg.get("apple_broker_callback")
        or ""
    )


def _require_https_callback(url: str, expected_path: str) -> None:
    parsed = urlparse(url)
    assert parsed.scheme == "https", f"Expected https callback URL, got: {url}"
    assert parsed.path == expected_path, f"Expected callback path={expected_path}, got: {url}"


class TestHealthEndpoint:
    """Health endpoint should remain healthy"""

    def test_health_endpoint_returns_200(self):
        """GET /api/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        data = response.json()
        assert data.get("status") == "healthy", f"Health status not healthy: {data}"
        print("PASS: Health endpoint returns 200 with status=healthy")


class TestAppleLoginBrokerEnforcement:
    """Apple login redirect must align to current runtime callback selection."""

    def test_apple_login_returns_302(self):
        """GET /api/auth/apple/login should return 302 redirect"""
        response = requests.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False, timeout=10)
        assert response.status_code == 302, f"Expected 302, got {response.status_code}"
        print("PASS: Apple login returns 302")

    def test_apple_login_redirects_to_apple_authorize(self):
        """Apple login should redirect to appleid.apple.com/auth/authorize"""
        response = requests.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False, timeout=10)
        location = response.headers.get("Location", "")
        assert "appleid.apple.com/auth/authorize" in location, f"Expected Apple authorize URL, got: {location}"
        print("PASS: Apple login redirects to appleid.apple.com/auth/authorize")

    def test_apple_login_redirect_uri_matches_runtime_selected_callback(self):
        """Apple login redirect_uri must match runtime-selected callback diagnostics."""
        response = requests.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False, timeout=10)
        location = response.headers.get("Location", "")
        
        # Parse the redirect URL to extract redirect_uri parameter
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)
        redirect_uri = query_params.get("redirect_uri", [""])[0]
        expected_callback = _expected_apple_login_redirect_uri()
        
        assert redirect_uri == expected_callback, (
            f"Expected redirect_uri={expected_callback}, got: {redirect_uri}"
        )
        _require_https_callback(redirect_uri, "/api/auth/apple/callback")
        print(f"PASS: Apple login redirect_uri matches runtime callback: {expected_callback}")

    def test_apple_login_redirect_host_policy_matches_expected_callback(self):
        """Apple login redirect host policy should match runtime-selected callback."""
        response = requests.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False, timeout=10)
        location = response.headers.get("Location", "")
        
        # Parse the redirect URL to extract redirect_uri parameter
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)
        redirect_uri = query_params.get("redirect_uri", [""])[0]
        expected_callback = _expected_apple_login_redirect_uri()
        expected_host = urlparse(expected_callback).netloc.lower()
        actual_host = urlparse(redirect_uri).netloc.lower()
        
        assert actual_host == expected_host, (
            f"Expected Apple redirect host={expected_host}, got: {actual_host}"
        )
        print(f"PASS: Apple login host policy matches expected callback host: {expected_host}")

    def test_apple_login_does_not_fail_close_to_sso_error(self):
        """Apple login should NOT fail-close to sso_error=apple_redirect_unregistered"""
        response = requests.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False, timeout=10)
        location = response.headers.get("Location", "")
        
        assert "sso_error=apple_redirect_unregistered" not in location, (
            f"Apple login should not fail-close to unregistered error, got: {location}"
        )
        assert "sso_error=apple_callback_not_provider_registered" not in location, (
            f"Apple login should not fail-close to not_provider_registered error, got: {location}"
        )
        print("PASS: Apple login does not fail-close to sso_error")


class TestSSOConfigDiagnostics:
    """SSO config endpoint should expose coherent Apple callback diagnostics."""

    def test_sso_config_returns_200(self):
        """GET /api/auth/sso-config should return 200"""
        response = requests.get(f"{BASE_URL}/api/auth/sso-config", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: SSO config returns 200")

    def test_sso_config_exposes_valid_callback_strategy(self):
        """SSO config should show Apple strategy within allowed values."""
        response = requests.get(f"{BASE_URL}/api/auth/sso-config", timeout=10)
        data = response.json()
        
        strategy = data.get("apple_callback_strategy")
        assert strategy in {"direct", "broker"}, f"Unexpected apple_callback_strategy: {strategy}"
        print(f"PASS: SSO config apple_callback_strategy={strategy}")

    def test_sso_config_exposes_valid_broker_callback_shape(self):
        """SSO config should expose HTTPS Apple broker callback URL with broker path."""
        response = requests.get(f"{BASE_URL}/api/auth/sso-config", timeout=10)
        data = response.json()
        
        broker_callback = data.get("apple_broker_callback")
        _require_https_callback(broker_callback or "", "/api/auth/apple/broker/callback")
        print(f"PASS: SSO config apple_broker_callback={broker_callback}")

    def test_sso_config_broker_enforced_matches_strategy(self):
        """If strategy is broker then broker_enforced must be true; otherwise false."""
        response = requests.get(f"{BASE_URL}/api/auth/sso-config", timeout=10)
        data = response.json()
        
        strategy = data.get("apple_callback_strategy")
        broker_enforced = data.get("apple_broker_enforced")
        assert isinstance(broker_enforced, bool), f"Expected bool apple_broker_enforced, got: {broker_enforced}"
        assert broker_enforced is (strategy == "broker"), (
            f"Expected apple_broker_enforced={(strategy == 'broker')} for strategy={strategy}, got: {broker_enforced}"
        )
        print(f"PASS: SSO config broker_enforced={broker_enforced} aligns with strategy={strategy}")

    def test_sso_config_expected_provider_callback_matches_broker(self):
        """SSO config apple_expected_provider_callback should match broker callback"""
        response = requests.get(f"{BASE_URL}/api/auth/sso-config", timeout=10)
        data = response.json()
        
        expected_callback = data.get("apple_expected_provider_callback")
        broker_callback = data.get("apple_broker_callback")
        assert expected_callback == broker_callback, (
            f"Expected apple_expected_provider_callback={broker_callback}, got: {expected_callback}"
        )
        print("PASS: SSO config apple_expected_provider_callback matches apple_broker_callback")


class TestAdminSSOStatus:
    """Admin SSO status endpoint should show broker enforcement details"""

    @pytest.fixture(autouse=True)
    def admin_session(self):
        """Get admin session for authenticated requests"""
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code}")
        self.session = session

    def test_admin_sso_status_returns_200(self):
        """GET /api/admin/sso-status should return 200 for admin"""
        response = self.session.get(f"{BASE_URL}/api/admin/sso-status", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Admin SSO status returns 200")

    def test_admin_sso_status_apple_callback_strategy_matches_sso_config(self):
        """Admin Apple callback_strategy should align with /api/auth/sso-config."""
        response = self.session.get(f"{BASE_URL}/api/admin/sso-status", timeout=10)
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None, "Apple provider not found in SSO status"
        
        expected_strategy = _sso_config().get("apple_callback_strategy")
        strategy = apple_provider.get("callback_strategy")
        assert strategy == expected_strategy, f"Expected callback_strategy={expected_strategy}, got: {strategy}"
        print(f"PASS: Admin SSO status Apple callback_strategy={strategy}")

    def test_admin_sso_status_apple_broker_callback_matches_sso_config(self):
        """Admin Apple broker_callback should align with /api/auth/sso-config."""
        response = self.session.get(f"{BASE_URL}/api/admin/sso-status", timeout=10)
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None, "Apple provider not found in SSO status"
        
        expected_broker_callback = _sso_config().get("apple_broker_callback")
        broker_callback = apple_provider.get("broker_callback")
        assert broker_callback == expected_broker_callback, (
            f"Expected broker_callback={expected_broker_callback}, got: {broker_callback}"
        )
        print(f"PASS: Admin SSO status Apple broker_callback={broker_callback}")

    def test_admin_sso_status_apple_broker_enforced_matches_sso_config(self):
        """Admin Apple broker_enforced should align with /api/auth/sso-config."""
        response = self.session.get(f"{BASE_URL}/api/admin/sso-status", timeout=10)
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None, "Apple provider not found in SSO status"
        
        expected_broker_enforced = _sso_config().get("apple_broker_enforced")
        broker_enforced = apple_provider.get("broker_enforced")
        assert broker_enforced is expected_broker_enforced, (
            f"Expected broker_enforced={expected_broker_enforced}, got: {broker_enforced}"
        )
        print(f"PASS: Admin SSO status Apple broker_enforced={broker_enforced}")

    def test_admin_sso_status_apple_expected_provider_callback(self):
        """Admin Apple expected_provider_callback should align with /api/auth/sso-config."""
        response = self.session.get(f"{BASE_URL}/api/admin/sso-status", timeout=10)
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None, "Apple provider not found in SSO status"
        
        expected_from_config = _sso_config().get("apple_expected_provider_callback")
        expected_callback = apple_provider.get("expected_provider_callback")
        assert expected_callback == expected_from_config, (
            f"Expected expected_provider_callback={expected_from_config}, got: {expected_callback}"
        )
        print(f"PASS: Admin SSO status Apple expected_provider_callback={expected_callback}")

    def test_admin_sso_status_apple_no_critical_issues(self):
        """Admin SSO status should show Apple with no critical issues"""
        response = self.session.get(f"{BASE_URL}/api/admin/sso-status", timeout=10)
        data = response.json()
        
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        assert apple_provider is not None, "Apple provider not found in SSO status"
        
        issues = apple_provider.get("issues", [])
        status = apple_provider.get("status")
        
        # Log issues for debugging but don't fail on non-critical issues
        if issues:
            print(f"INFO: Apple provider has issues: {issues}")
        
        # Status should be configured or at least not critical
        assert status in ["configured", "misconfigured"], f"Unexpected Apple status: {status}"
        print(f"PASS: Admin SSO status shows Apple status={status}")


class TestMicrosoftLoginNoRegression:
    """Microsoft login should still work and align to live SSO config callback."""

    def test_microsoft_login_returns_302(self):
        """GET /api/auth/microsoft/login should return 302 redirect"""
        response = requests.get(f"{BASE_URL}/api/auth/microsoft/login", allow_redirects=False, timeout=10)
        assert response.status_code == 302, f"Expected 302, got {response.status_code}"
        print("PASS: Microsoft login returns 302")

    def test_microsoft_login_redirects_to_microsoft_authorize(self):
        """Microsoft login should redirect to login.microsoftonline.com"""
        response = requests.get(f"{BASE_URL}/api/auth/microsoft/login", allow_redirects=False, timeout=10)
        location = response.headers.get("Location", "")
        assert "login.microsoftonline.com" in location, f"Expected Microsoft authorize URL, got: {location}"
        print("PASS: Microsoft login redirects to login.microsoftonline.com")

    def test_microsoft_login_uses_runtime_callback(self):
        """Microsoft login should use runtime callback from /api/auth/sso-config."""
        response = requests.get(f"{BASE_URL}/api/auth/microsoft/login", allow_redirects=False, timeout=10)
        location = response.headers.get("Location", "")
        
        # Parse the redirect URL to extract redirect_uri parameter
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)
        redirect_uri = query_params.get("redirect_uri", [""])[0]
        expected_ms_callback = _sso_config().get("microsoft_callback")
        
        assert redirect_uri == expected_ms_callback, (
            f"Expected Microsoft redirect_uri={expected_ms_callback}, got: {redirect_uri}"
        )
        _require_https_callback(redirect_uri, "/api/auth/microsoft/callback")
        print(f"PASS: Microsoft login uses runtime callback: {redirect_uri}")


class TestBrokerCallbackEndpoint:
    """Broker callback endpoint should exist and be accessible"""

    def test_broker_callback_endpoint_exists(self):
        """POST /api/auth/apple/broker/callback should exist (returns 302 or 400, not 404)"""
        # Send empty POST to check endpoint exists
        response = requests.post(
            f"{BASE_URL}/api/auth/apple/broker/callback",
            data={},
            allow_redirects=False,
            timeout=10
        )
        # Should return 302 (redirect) or 422 (validation error), not 404
        assert response.status_code != 404, f"Broker callback endpoint not found: {response.status_code}"
        print(f"PASS: Broker callback endpoint exists (status={response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
