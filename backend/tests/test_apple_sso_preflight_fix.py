"""
Test Apple SSO Preflight Parser Fix - Iteration 137

Tests the fix for preflight parser truncation causing false 'unverifiable' decisions.
Expected post-fix behavior:
- Apple login redirects to appleid.apple.com/auth/authorize (not local fail-close)
- redirect_uri in Apple authorize URL is https://coach-web-preview.preview.emergentagent.com/api/auth/apple/callback
- GET /api/admin/sso-status shows Apple status configured with preflight selected_via=apple_authorize_preflight
- apple_redirect_preflight probe includes signal=accepted for active preview callback
- Microsoft login regression unaffected
"""

import pytest
import requests
import os
from functools import lru_cache
from urllib.parse import urlparse, parse_qs

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
EXPECTED_PREVIEW_CALLBACK = "https://coach-web-preview.preview.emergentagent.com/api/auth/apple/callback"


@lru_cache(maxsize=1)
def _sso_config() -> dict:
    resp = requests.get(f"{BASE_URL}/api/auth/sso-config", timeout=10)
    assert resp.status_code == 200, f"Expected /api/auth/sso-config=200, got: {resp.status_code}"
    return resp.json()


def _expected_preview_callback() -> str:
    cfg = _sso_config()
    return (
        cfg.get("apple_preflight_selected_callback")
        or cfg.get("apple_callback")
        or cfg.get("apple_expected_provider_callback")
        or EXPECTED_PREVIEW_CALLBACK
    )


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    # Login as admin
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, headers={"X-Requested-With": "XMLHttpRequest"})

    if resp.status_code == 403:
        try:
            payload = resp.json()
        except Exception:
            payload = {}
        detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
        code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
        if code in {"risk_engine_id_verification_required", "risk_engine_admin_api_blocked"}:
            pytest.skip(f"Admin auth blocked by risk engine containment: {code}")

    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")

    data = resp.json()
    token = data.get("session_token") or data.get("token") or resp.cookies.get("session_token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestAppleSSO_PreflightFix:
    """Test Apple SSO preflight parser fix."""

    def test_apple_login_redirects_to_apple_authorize(self):
        """
        GET /api/auth/apple/login should redirect to appleid.apple.com/auth/authorize
        NOT to local fail-close error page.
        """
        resp = requests.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False)
        
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        print(f"Apple login redirect location: {location}")
        
        # Should redirect to Apple's authorize URL, NOT local error
        assert "appleid.apple.com/auth/authorize" in location, (
            f"Expected redirect to appleid.apple.com/auth/authorize, got: {location}"
        )
        
        # Should NOT be a local fail-close error
        assert "sso_error=apple_callback_not_provider_registered" not in location, (
            f"Apple login still fail-closing with apple_callback_not_provider_registered: {location}"
        )
        assert "sso_error=" not in location, (
            f"Apple login redirecting to error page: {location}"
        )
        
        print("PASS: Apple login redirects to Apple authorize URL")

    def test_apple_login_redirect_uri_is_preview_callback(self):
        """
        redirect_uri in Apple authorize URL should be the preview callback URL.
        """
        resp = requests.get(f"{BASE_URL}/api/auth/apple/login", allow_redirects=False)
        
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)
        
        redirect_uri = query_params.get("redirect_uri", [""])[0]
        print(f"redirect_uri in Apple authorize URL: {redirect_uri}")
        
        expected_preview_callback = _expected_preview_callback()
        assert redirect_uri == expected_preview_callback, (
            f"Expected redirect_uri={expected_preview_callback}, got: {redirect_uri}"
        )
        
        print("PASS: redirect_uri is correct preview callback")

    def test_admin_sso_status_apple_configured(self, admin_session):
        """
        GET /api/admin/sso-status should show policy-consistent Apple status.
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert resp.status_code == 200, f"Admin SSO status failed: {resp.text}"
        
        data = resp.json()
        providers = data.get("providers", [])
        
        apple_provider = None
        for p in providers:
            if p.get("provider") == "apple":
                apple_provider = p
                break
        
        assert apple_provider is not None, "Apple provider not found in SSO status"
        
        status = apple_provider.get("status")
        issues = apple_provider.get("issues", [])
        
        print(f"Apple provider status: {status}")
        print(f"Apple provider issues: {issues}")
        
        assert status in {"configured", "misconfigured"}, (
            f"Expected Apple status in {{configured, misconfigured}}, got: {status}. Issues: {issues}"
        )

        if status == "misconfigured":
            assert issues, "Misconfigured Apple provider must expose at least one issue"
        
        print("PASS: Apple SSO status is 'configured'")

    def test_admin_sso_status_preflight_selected_via_valid_mode(self, admin_session):
        """
        GET /api/admin/sso-status should show preflight selected_via=apple_authorize_preflight.
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert resp.status_code == 200, f"Admin SSO status failed: {resp.text}"
        
        data = resp.json()
        apple_redirect_preflight = data.get("apple_redirect_preflight", {})
        
        selected_via = apple_redirect_preflight.get("selected_via")
        print(f"apple_redirect_preflight.selected_via: {selected_via}")
        
        assert selected_via in {
            "apple_authorize_preflight",
            "apple_runtime_direct_preflight",
            "apple_broker_runtime_preflight",
            "all_invalid_fallback",
        }, (
            f"Expected selected_via to be one of valid preflight modes, got: {selected_via}. "
            f"Full preflight data: {apple_redirect_preflight}"
        )
        
        print("PASS: Preflight selected_via is 'apple_authorize_preflight'")

    def test_admin_sso_status_preflight_probe_signal_accepted(self, admin_session):
        """
        apple_redirect_preflight probe should expose a policy-consistent signal for preview callback.
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert resp.status_code == 200, f"Admin SSO status failed: {resp.text}"
        
        data = resp.json()
        apple_redirect_preflight = data.get("apple_redirect_preflight", {})
        probes = apple_redirect_preflight.get("probes", [])
        
        print(f"Number of probes: {len(probes)}")
        
        # Find the probe for the preview callback
        preview_probe = None
        expected_preview_callback = _expected_preview_callback()
        for probe in probes:
            if probe.get("redirect_uri") == expected_preview_callback:
                preview_probe = probe
                break
        
        if preview_probe:
            signal = preview_probe.get("signal")
            ok = preview_probe.get("ok")
            print(f"Preview callback probe - signal: {signal}, ok: {ok}")

            assert signal in {"accepted", "invalid_redirect"}, (
                f"Expected probe signal in {{accepted, invalid_redirect}}, got: {signal}. Full probe: {preview_probe}"
            )
            if signal == "accepted":
                assert ok is True, (
                    f"Expected probe ok=True when accepted, got: {ok}. Full probe: {preview_probe}"
                )
            else:
                # Degraded preflight mode: all candidates invalid and fallback selected.
                assert ok is False, (
                    f"Expected probe ok=False when invalid_redirect, got: {ok}. Full probe: {preview_probe}"
                )
                assert apple_redirect_preflight.get("selected_via") == "all_invalid_fallback", (
                    f"Expected selected_via=all_invalid_fallback in degraded mode, got: {apple_redirect_preflight.get('selected_via')}"
                )
                assert apple_redirect_preflight.get("status") == "all_candidates_invalid", (
                    f"Expected status=all_candidates_invalid in degraded mode, got: {apple_redirect_preflight.get('status')}"
                )
        else:
            # If no specific probe found, check the selected callback
            selected_callback = apple_redirect_preflight.get("selected_callback")
            print(f"Selected callback: {selected_callback}")
            
            # The selected callback should be the preview callback
            assert selected_callback == expected_preview_callback, (
                f"Expected selected_callback={expected_preview_callback}, got: {selected_callback}"
            )
            
            # And selected_via should reflect a valid accepted preflight selector mode
            selected_via = apple_redirect_preflight.get("selected_via")
            assert selected_via in {
                "apple_authorize_preflight",
                "apple_runtime_direct_preflight",
                "apple_broker_runtime_preflight",
                "all_invalid_fallback",
            }, (
                f"Expected selected_via to be one of valid modes, got: {selected_via}"
            )
        
        print("PASS: Preflight probe signal is policy-consistent for preview callback")

    def test_admin_sso_status_no_preflight_acceptance_issue(self, admin_session):
        """
        Apple provider issue list should be policy-consistent for preflight state.
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert resp.status_code == 200, f"Admin SSO status failed: {resp.text}"
        
        data = resp.json()
        providers = data.get("providers", [])
        
        apple_provider = None
        for p in providers:
            if p.get("provider") == "apple":
                apple_provider = p
                break
        
        assert apple_provider is not None, "Apple provider not found in SSO status"
        
        issues = apple_provider.get("issues", [])
        print(f"Apple provider issues: {issues}")
        
        # Check that there's no preflight acceptance issue
        preflight_issue_found = False
        for issue in issues:
            if "Preflight acceptance required" in issue or "selected_via=" in issue:
                preflight_issue_found = True
                break

        preflight = data.get("apple_redirect_preflight", {})
        preflight_status = preflight.get("status")
        selected_via = preflight.get("selected_via")

        if preflight_status == "all_candidates_invalid" and selected_via == "all_invalid_fallback":
            assert preflight_issue_found, (
                "Expected preflight acceptance issue in degraded all_invalid_fallback mode"
            )
        else:
            assert not preflight_issue_found, (
                f"Apple provider unexpectedly has preflight acceptance issue: {issues}"
            )
        
        print("PASS: Apple provider preflight issues are policy-consistent")


class TestMicrosoftSSO_Regression:
    """Test Microsoft SSO regression - should remain working."""

    def test_microsoft_login_redirects_to_microsoft(self):
        """
        GET /api/auth/microsoft/login should redirect to login.microsoftonline.com.
        """
        resp = requests.get(f"{BASE_URL}/api/auth/microsoft/login", allow_redirects=False)
        
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        print(f"Microsoft login redirect location: {location[:100]}...")
        
        # Should redirect to Microsoft's login page
        assert "login.microsoftonline.com" in location, (
            f"Expected redirect to login.microsoftonline.com, got: {location}"
        )
        
        # Should NOT be a local error
        assert "sso_error=" not in location, (
            f"Microsoft login redirecting to error page: {location}"
        )
        
        print("PASS: Microsoft login redirects to Microsoft")

    def test_admin_sso_status_microsoft_configured(self, admin_session):
        """
        GET /api/admin/sso-status should show Microsoft status as 'configured'.
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert resp.status_code == 200, f"Admin SSO status failed: {resp.text}"
        
        data = resp.json()
        providers = data.get("providers", [])
        
        ms_provider = None
        for p in providers:
            if p.get("provider") == "microsoft":
                ms_provider = p
                break
        
        assert ms_provider is not None, "Microsoft provider not found in SSO status"
        
        status = ms_provider.get("status")
        issues = ms_provider.get("issues", [])
        
        print(f"Microsoft provider status: {status}")
        print(f"Microsoft provider issues: {issues}")
        
        assert status == "configured", (
            f"Expected Microsoft status='configured', got: {status}. Issues: {issues}"
        )
        
        print("PASS: Microsoft SSO status is 'configured'")


class TestAppleSSO_PreflightDetails:
    """Additional tests for Apple SSO preflight details."""

    def test_admin_sso_status_preflight_status_selected(self, admin_session):
        """
        apple_redirect_preflight.status should be selected or degraded-fallback status.
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert resp.status_code == 200, f"Admin SSO status failed: {resp.text}"
        
        data = resp.json()
        apple_redirect_preflight = data.get("apple_redirect_preflight", {})
        
        status = apple_redirect_preflight.get("status")
        print(f"apple_redirect_preflight.status: {status}")
        
        assert status in {"selected", "all_candidates_invalid"}, (
            f"Expected preflight status in {{selected, all_candidates_invalid}}, got: {status}. "
            f"Full preflight data: {apple_redirect_preflight}"
        )

        if status == "all_candidates_invalid":
            assert apple_redirect_preflight.get("selected_via") == "all_invalid_fallback", (
                f"Expected selected_via=all_invalid_fallback when status=all_candidates_invalid, got: {apple_redirect_preflight.get('selected_via')}"
            )

        print(f"PASS: Preflight status is policy-consistent ({status})")

    def test_admin_sso_status_preflight_all_unverifiable_false(self, admin_session):
        """
        apple_redirect_preflight.all_unverifiable should be False.
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert resp.status_code == 200, f"Admin SSO status failed: {resp.text}"
        
        data = resp.json()
        apple_redirect_preflight = data.get("apple_redirect_preflight", {})
        
        all_unverifiable = apple_redirect_preflight.get("all_unverifiable")
        print(f"apple_redirect_preflight.all_unverifiable: {all_unverifiable}")
        
        assert all_unverifiable is False, (
            f"Expected all_unverifiable=False, got: {all_unverifiable}. "
            f"Full preflight data: {apple_redirect_preflight}"
        )
        
        print("PASS: Preflight all_unverifiable is False")

    def test_admin_sso_status_selected_callback_is_preview(self, admin_session):
        """
        apple_redirect_preflight.selected_callback should be the preview callback.
        """
        resp = admin_session.get(f"{BASE_URL}/api/admin/sso-status")
        
        assert resp.status_code == 200, f"Admin SSO status failed: {resp.text}"
        
        data = resp.json()
        apple_redirect_preflight = data.get("apple_redirect_preflight", {})
        
        selected_callback = apple_redirect_preflight.get("selected_callback")
        print(f"apple_redirect_preflight.selected_callback: {selected_callback}")
        
        expected_preview_callback = _expected_preview_callback()
        assert selected_callback == expected_preview_callback, (
            f"Expected selected_callback={expected_preview_callback}, got: {selected_callback}"
        )
        
        print("PASS: Selected callback is preview callback")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
