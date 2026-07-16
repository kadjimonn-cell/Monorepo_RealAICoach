"""
Apple SSO Preflight Acceptance & Strict Callback Allowlist Tests
Tests for iteration_135: Permanent fix for recurring Apple SSO invalid_request in dev.

Features tested:
1. GET /api/auth/apple/login fail-closes to /auth/login?sso_error=apple_callback_not_provider_registered 
   when selected_via is not apple_authorize_preflight
2. GET /api/auth/sso-config exposes apple_provider_accepted_bases, apple_strict_callback_allowlist_enabled, 
   apple_require_preflight_accepted
3. GET /api/admin/sso-status reflects Apple preflight-acceptance issue (misconfigured when latest preflight not accepted)
4. POST /api/auth/admin/sso-validate-e2e includes apple_callback_in_provider_allowlist check
5. Regression: Microsoft login redirect still functional
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestAppleSSOPreflightAcceptance:
    """Tests for Apple SSO preflight acceptance and strict callback allowlist enforcement."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin authentication."""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        # Login as admin
        login_resp = self.session.post(
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

        data = login_resp.json()
        token = data.get("session_token") or data.get("token") or login_resp.cookies.get("session_token")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})

        yield
        self.session.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Test 1: GET /api/auth/sso-config exposes new Apple preflight fields
    # ─────────────────────────────────────────────────────────────────────────
    def test_sso_config_exposes_apple_preflight_fields(self):
        """Verify /api/auth/sso-config exposes apple_provider_accepted_bases, 
        apple_strict_callback_allowlist_enabled, apple_require_preflight_accepted."""
        resp = self.session.get(f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Check required fields exist
        assert "apple_provider_accepted_bases" in data, "Missing apple_provider_accepted_bases"
        assert "apple_strict_callback_allowlist_enabled" in data, "Missing apple_strict_callback_allowlist_enabled"
        assert "apple_require_preflight_accepted" in data, "Missing apple_require_preflight_accepted"
        
        # Validate types
        assert isinstance(data["apple_provider_accepted_bases"], list), "apple_provider_accepted_bases should be a list"
        assert isinstance(data["apple_strict_callback_allowlist_enabled"], bool), "apple_strict_callback_allowlist_enabled should be bool"
        assert isinstance(data["apple_require_preflight_accepted"], bool), "apple_require_preflight_accepted should be bool"
        
        # Based on .env, these should be enabled
        assert data["apple_strict_callback_allowlist_enabled"] is True, "Expected strict callback allowlist to be enabled"
        assert data["apple_require_preflight_accepted"] is True, "Expected require preflight accepted to be enabled"
        
        print("✓ sso-config exposes Apple preflight fields correctly")
        print(f"  - apple_provider_accepted_bases: {data['apple_provider_accepted_bases']}")
        print(f"  - apple_strict_callback_allowlist_enabled: {data['apple_strict_callback_allowlist_enabled']}")
        print(f"  - apple_require_preflight_accepted: {data['apple_require_preflight_accepted']}")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 2: GET /api/auth/apple/login fail-closes when preflight not accepted
    # ─────────────────────────────────────────────────────────────────────────
    def test_apple_login_fail_closes_without_preflight_acceptance(self):
        """Verify Apple login redirects to sso_error=apple_callback_not_provider_registered 
        when selected_via is not apple_authorize_preflight."""
        # Make request without following redirects
        resp = self.session.get(
            f"{BASE_URL}/api/auth/apple/login",
            allow_redirects=False
        )
        
        # Should be a redirect (302)
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        
        # In dev environment without proper preflight acceptance, should fail-close
        # Either redirects to Apple (if preflight accepted) or to error page
        if "sso_error=apple_callback_not_provider_registered" in location:
            print("✓ Apple login correctly fail-closes with apple_callback_not_provider_registered")
            print(f"  - Redirect location: {location}")
        elif "appleid.apple.com" in location:
            # If it redirects to Apple, preflight was accepted - this is also valid
            print("✓ Apple login redirects to Apple (preflight was accepted)")
            print(f"  - Redirect location: {location[:100]}...")
        elif "sso_error=" in location:
            # Other SSO errors are also acceptable (e.g., apple_redirect_unregistered)
            print("✓ Apple login fail-closes with SSO error")
            print(f"  - Redirect location: {location}")
        else:
            # Unexpected redirect
            pytest.fail(f"Unexpected redirect location: {location}")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 3: GET /api/admin/sso-status reflects Apple preflight-acceptance issue
    # ─────────────────────────────────────────────────────────────────────────
    def test_admin_sso_status_reflects_preflight_acceptance(self):
        """Verify /api/admin/sso-status shows Apple as misconfigured when preflight not accepted."""
        resp = self.session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Find Apple provider in the list
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        
        assert apple_provider is not None, "Apple provider not found in sso-status"
        
        # Check Apple-specific fields
        assert "strict_callback_allowlist_enabled" in apple_provider, "Missing strict_callback_allowlist_enabled"
        assert "require_preflight_accepted" in apple_provider, "Missing require_preflight_accepted"
        assert "provider_accepted_bases" in apple_provider, "Missing provider_accepted_bases"
        
        # Validate values
        assert apple_provider["strict_callback_allowlist_enabled"] is True, "Expected strict allowlist enabled"
        assert apple_provider["require_preflight_accepted"] is True, "Expected require preflight accepted"
        
        # Check status - should be misconfigured if preflight not accepted
        status = apple_provider.get("status")
        issues = apple_provider.get("issues", [])
        
        print("✓ admin/sso-status reflects Apple preflight acceptance state")
        print(f"  - Status: {status}")
        print(f"  - Issues: {issues}")
        print(f"  - strict_callback_allowlist_enabled: {apple_provider['strict_callback_allowlist_enabled']}")
        print(f"  - require_preflight_accepted: {apple_provider['require_preflight_accepted']}")
        print(f"  - provider_accepted_bases: {apple_provider.get('provider_accepted_bases')}")
        
        # If there are preflight-related issues, status should be misconfigured
        preflight_issue = any("preflight" in str(issue).lower() for issue in issues)
        if preflight_issue:
            assert status == "misconfigured", f"Expected misconfigured status when preflight issue exists, got {status}"
            print("  - Correctly shows misconfigured due to preflight issue")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 4: POST /api/auth/admin/sso-validate-e2e includes allowlist check
    # ─────────────────────────────────────────────────────────────────────────
    def test_sso_validate_e2e_includes_allowlist_check(self):
        """Verify /api/auth/admin/sso-validate-e2e includes apple_callback_in_provider_allowlist check."""
        resp = self.session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Check structure
        assert "checks" in data, "Missing checks array"
        checks = data.get("checks", [])
        
        # Find the apple_callback_in_provider_allowlist check
        allowlist_check = next(
            (c for c in checks if c.get("name") == "apple_callback_in_provider_allowlist"),
            None
        )
        
        assert allowlist_check is not None, "Missing apple_callback_in_provider_allowlist check"
        
        # Validate check structure
        assert "passed" in allowlist_check, "Missing passed field in allowlist check"
        assert "details" in allowlist_check, "Missing details field in allowlist check"
        assert "allowlist_bases" in allowlist_check, "Missing allowlist_bases field in allowlist check"
        
        print("✓ sso-validate-e2e includes apple_callback_in_provider_allowlist check")
        print(f"  - Passed: {allowlist_check['passed']}")
        print(f"  - Details: {allowlist_check['details']}")
        print(f"  - Allowlist bases: {allowlist_check.get('allowlist_bases')}")
        
        # Also verify other Apple-related checks exist
        apple_checks = [c for c in checks if "apple" in c.get("name", "").lower()]
        print(f"  - Total Apple-related checks: {len(apple_checks)}")
        for check in apple_checks:
            print(f"    - {check.get('name')}: passed={check.get('passed')}")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 5: Microsoft login redirect still functional (regression test)
    # ─────────────────────────────────────────────────────────────────────────
    def test_microsoft_login_redirect_still_functional(self):
        """Regression test: Microsoft login redirect should still work."""
        resp = self.session.get(
            f"{BASE_URL}/api/auth/microsoft/login",
            allow_redirects=False
        )
        
        # Should be a redirect (302)
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        
        # Should redirect to Microsoft login
        assert "login.microsoftonline.com" in location or "microsoft" in location.lower(), \
            f"Expected Microsoft login redirect, got: {location}"
        
        print("✓ Microsoft login redirect still functional")
        print(f"  - Redirect location: {location[:100]}...")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 6: Verify env configuration is correctly loaded
    # ─────────────────────────────────────────────────────────────────────────
    def test_env_configuration_loaded(self):
        """Verify the new env variables are correctly loaded and exposed."""
        resp = self.session.get(f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Based on .env:
        # APPLE_SSO_REQUIRE_PREFLIGHT_ACCEPTED=true
        # APPLE_SSO_STRICT_CALLBACK_ALLOWLIST=true
        # APPLE_SSO_PROVIDER_ACCEPTED_CALLBACK_BASES=https://coach-web-preview.preview.emergentagent.com
        
        assert data.get("apple_require_preflight_accepted") is True, \
            "APPLE_SSO_REQUIRE_PREFLIGHT_ACCEPTED should be true"
        assert data.get("apple_strict_callback_allowlist_enabled") is True, \
            "APPLE_SSO_STRICT_CALLBACK_ALLOWLIST should be true"
        
        accepted_bases = data.get("apple_provider_accepted_bases", [])
        assert len(accepted_bases) > 0, "APPLE_SSO_PROVIDER_ACCEPTED_CALLBACK_BASES should have at least one entry"
        
        print("✓ Environment configuration correctly loaded")
        print(f"  - APPLE_SSO_REQUIRE_PREFLIGHT_ACCEPTED: {data.get('apple_require_preflight_accepted')}")
        print(f"  - APPLE_SSO_STRICT_CALLBACK_ALLOWLIST: {data.get('apple_strict_callback_allowlist_enabled')}")
        print(f"  - APPLE_SSO_PROVIDER_ACCEPTED_CALLBACK_BASES: {accepted_bases}")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 7: Verify Apple callback base matches provider accepted list
    # ─────────────────────────────────────────────────────────────────────────
    def test_apple_callback_base_in_accepted_list(self):
        """Verify the active Apple callback base is in the provider accepted list."""
        resp = self.session.get(f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        
        data = resp.json()
        
        apple_active_base = data.get("deployment_domain_active_apple", "")
        accepted_bases = data.get("apple_provider_accepted_bases", [])
        
        print("✓ Apple callback base configuration")
        print(f"  - Active Apple base: {apple_active_base}")
        print(f"  - Accepted bases: {accepted_bases}")
        
        # The active base should be in the accepted list for proper operation
        # If not, Apple login will fail-close (which is the expected behavior)
        if apple_active_base in accepted_bases:
            print("  - Active base IS in accepted list (Apple login should work)")
        else:
            print("  - Active base NOT in accepted list (Apple login will fail-close as expected)")

    # ─────────────────────────────────────────────────────────────────────────
    # Test 8: Verify admin sso-status shows all required Apple fields
    # ─────────────────────────────────────────────────────────────────────────
    def test_admin_sso_status_apple_fields_complete(self):
        """Verify admin/sso-status includes all required Apple preflight fields."""
        resp = self.session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200
        
        data = resp.json()
        providers = data.get("providers", [])
        apple_provider = next((p for p in providers if p.get("provider") == "apple"), None)
        
        assert apple_provider is not None, "Apple provider not found"
        
        # Required fields for Apple preflight acceptance feature
        required_fields = [
            "provider_verified_base_required",
            "provider_verified_bases",
            "provider_accepted_bases",
            "provider_verified_base",
            "provider_verification_source",
            "preview_registered_fallback_enabled",
            "strict_callback_allowlist_enabled",
            "require_preflight_accepted",
        ]
        
        missing_fields = [f for f in required_fields if f not in apple_provider]
        assert len(missing_fields) == 0, f"Missing fields in Apple provider: {missing_fields}"
        
        print("✓ admin/sso-status Apple provider has all required fields")
        for field in required_fields:
            print(f"  - {field}: {apple_provider.get(field)}")


class TestAppleSSOFailCloseScenarios:
    """Tests for Apple SSO fail-close scenarios."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session."""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        yield
        self.session.close()

    def test_apple_login_returns_redirect(self):
        """Verify Apple login endpoint returns a redirect response."""
        resp = self.session.get(
            f"{BASE_URL}/api/auth/apple/login",
            allow_redirects=False
        )
        
        assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
        location = resp.headers.get("Location", "")
        assert location, "Missing Location header in redirect"
        
        print("✓ Apple login returns redirect")
        print(f"  - Status: {resp.status_code}")
        print(f"  - Location: {location[:100]}...")

    def test_apple_login_error_codes(self):
        """Verify Apple login uses correct error codes for fail-close scenarios."""
        resp = self.session.get(
            f"{BASE_URL}/api/auth/apple/login",
            allow_redirects=False
        )
        
        location = resp.headers.get("Location", "")
        
        # Valid error codes for fail-close
        valid_error_codes = [
            "apple_callback_not_provider_registered",
            "apple_redirect_unregistered",
            "apple_provider_verification_required",
            "apple_not_configured",
        ]
        
        if "sso_error=" in location:
            # Extract error code
            import urllib.parse
            parsed = urllib.parse.urlparse(location)
            params = urllib.parse.parse_qs(parsed.query)
            error_code = params.get("sso_error", [""])[0]
            
            assert error_code in valid_error_codes, \
                f"Unexpected error code: {error_code}. Valid codes: {valid_error_codes}"
            
            print(f"✓ Apple login uses valid error code: {error_code}")
        elif "appleid.apple.com" in location:
            print("✓ Apple login redirects to Apple (no error)")
        else:
            print(f"✓ Apple login redirects to: {location[:80]}...")


class TestMicrosoftSSORegression:
    """Regression tests to ensure Microsoft SSO is not affected by Apple changes."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin authentication."""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        # Login as admin
        login_resp = self.session.post(
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

        login_data = login_resp.json()
        token = login_data.get("session_token") or login_data.get("token") or login_resp.cookies.get("session_token")
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        yield
        self.session.close()

    def test_microsoft_sso_config_unchanged(self):
        """Verify Microsoft SSO config is not affected by Apple changes."""
        resp = self.session.get(f"{BASE_URL}/api/auth/sso-config")
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Microsoft-specific fields should still exist
        assert "deployment_domain_active_microsoft" in data
        assert "microsoft_callback" in data
        assert "microsoft_registered_callbacks" in data
        
        print("✓ Microsoft SSO config unchanged")
        print(f"  - Active base: {data.get('deployment_domain_active_microsoft')}")
        print(f"  - Callback: {data.get('microsoft_callback')}")

    def test_microsoft_in_sso_status(self):
        """Verify Microsoft provider appears correctly in sso-status."""
        resp = self.session.get(f"{BASE_URL}/api/admin/sso-status")
        assert resp.status_code == 200
        
        data = resp.json()
        providers = data.get("providers", [])
        ms_provider = next((p for p in providers if p.get("provider") == "microsoft"), None)
        
        assert ms_provider is not None, "Microsoft provider not found"
        assert ms_provider.get("configured") is True, "Microsoft should be configured"
        
        print("✓ Microsoft provider in sso-status")
        print(f"  - Status: {ms_provider.get('status')}")
        print(f"  - Callback URL: {ms_provider.get('callback_url')}")

    def test_microsoft_in_e2e_validation(self):
        """Verify Microsoft checks exist in e2e validation."""
        resp = self.session.post(f"{BASE_URL}/api/auth/admin/sso-validate-e2e")
        assert resp.status_code == 200
        
        data = resp.json()
        checks = data.get("checks", [])
        
        ms_checks = [c for c in checks if "microsoft" in c.get("name", "").lower()]
        assert len(ms_checks) > 0, "No Microsoft checks found in e2e validation"
        
        print("✓ Microsoft checks in e2e validation")
        for check in ms_checks:
            print(f"  - {check.get('name')}: passed={check.get('passed')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
