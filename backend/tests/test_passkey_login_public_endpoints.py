"""Passkey/Fingerprint login public endpoint contract tests.

Verifies that pre-login passkey endpoints:
- Are accessible WITHOUT authentication (not gated by AUTH_REQUIRED middleware).
- CSRF-exempt for POSTs (no X-Requested-With required).
- Return meaningful business responses (not 401 auth errors) for anonymous callers.
- Registration endpoint still requires authentication (regression).
- /auth/lookup returns has_passkey field.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
DEFAULT_TIMEOUT = 30


@pytest.fixture(autouse=True)
def _throttle_between_tests():
    """Small delay between tests to avoid preview ingress throttling."""
    yield
    time.sleep(0.5)
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def anon_session():
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def admin_user_id(anon_session):
    # Look up admin user_id via /auth/lookup (public endpoint)
    r = anon_session.get(
        f"{BASE_URL}/api/auth/lookup",
        params={"email": ADMIN_EMAIL},
        timeout=30,
    )
    assert r.status_code == 200, f"Lookup failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("exists") is True
    uid = data.get("user_id")
    assert uid, "user_id missing in lookup response"
    return uid


# ── /auth/lookup returns has_passkey ────────────────────────────
class TestAuthLookupHasPasskey:
    def test_lookup_returns_has_passkey_field(self, anon_session):
        r = anon_session.get(
            f"{BASE_URL}/api/auth/lookup",
            params={"email": ADMIN_EMAIL},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "has_passkey" in data, f"has_passkey missing from lookup response: {list(data.keys())}"
        assert isinstance(data["has_passkey"], bool)
        assert data.get("exists") is True
        assert data.get("user_id")


# ── GET /auth/biometric/has-passkey (public, GET) ───────────────
class TestHasPasskeyEndpoint:
    def test_has_passkey_public_no_auth(self, anon_session, admin_user_id):
        """Should return 200 with has_passkey + passkey_count without any auth."""
        r = anon_session.get(
            f"{BASE_URL}/api/auth/biometric/has-passkey",
            params={"user_id": admin_user_id},
            timeout=30,
        )
        assert r.status_code == 200, f"Expected 200 public access, got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert "has_passkey" in data
        assert "passkey_count" in data
        assert isinstance(data["has_passkey"], bool)
        assert isinstance(data["passkey_count"], int)

    def test_has_passkey_missing_user_id(self, anon_session):
        """Missing user_id returns 400 (not 401 AUTH_REQUIRED)."""
        r = anon_session.get(
            f"{BASE_URL}/api/auth/biometric/has-passkey",
            timeout=30,
        )
        assert r.status_code == 400, f"Expected 400 for missing user_id, got {r.status_code}: {r.text[:200]}"
        body = r.json()
        # Should NOT be an AUTH_REQUIRED error
        assert body.get("code") != "AUTH_REQUIRED"


# ── POST /auth/biometric/webauthn-auth-options ─────────────────
class TestWebAuthnAuthOptions:
    def test_auth_options_no_auth_returns_business_response(self, anon_session, admin_user_id):
        """No cookies/auth + no X-Requested-With. Should NOT return 401 AUTH_REQUIRED or 403 CSRF_BLOCKED.
        Admin has no passkey enrolled -> expect 404 'No biometric credential registered'."""
        r = anon_session.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-auth-options",
            json={"user_id": admin_user_id},
            timeout=30,
        )
        assert r.status_code != 401, f"Endpoint incorrectly requires auth (401 AUTH_REQUIRED): {r.text[:200]}"
        assert r.status_code != 403, f"Endpoint incorrectly CSRF-blocked (403): {r.text[:200]}"
        # Admin has no passkey enrolled → expect 404
        # OR if some user has one enrolled → 200 with challenge
        assert r.status_code in (200, 404), f"Unexpected status {r.status_code}: {r.text[:200]}"
        body = r.json()
        if r.status_code == 404:
            assert "biometric credential" in str(body.get("detail", "")).lower() or "no biometric" in str(body).lower()

    def test_auth_options_missing_user_id(self, anon_session):
        """POST with empty body → 400 (validation) or 422, NOT 401/403."""
        r = anon_session.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-auth-options",
            json={},
            timeout=30,
        )
        assert r.status_code not in (401, 403), f"Should not be blocked by auth/CSRF: {r.status_code} {r.text[:200]}"
        assert r.status_code in (400, 422)

    def test_auth_options_csrf_exempt_no_xrw_header(self, anon_session, admin_user_id):
        """Explicit test: POST without X-Requested-With header still works (CSRF-exempt)."""
        # Bare POST — no headers
        r = requests.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-auth-options",
            json={"user_id": admin_user_id},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert r.status_code != 403 or "CSRF" not in r.text, f"CSRF blocked without X-Requested-With: {r.text[:200]}"
        assert r.status_code in (200, 404)


# ── POST /auth/biometric/webauthn-auth-complete ────────────────
class TestWebAuthnAuthComplete:
    def test_auth_complete_no_auth_not_401(self, anon_session):
        """Anonymous POST should NOT return 401 AUTH_REQUIRED. Empty body -> 400/422/500 (validation/error).
        The key assertion is that middleware auth is NOT blocking (not 401 AUTH_REQUIRED code)."""
        r = anon_session.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-auth-complete",
            json={},
            timeout=30,
        )
        assert r.status_code != 401, f"Endpoint incorrectly requires auth (401 AUTH_REQUIRED): {r.text[:200]}"
        assert r.status_code != 403, f"Endpoint incorrectly CSRF-blocked (403): {r.text[:200]}"
        # Endpoint is reachable — request went past middleware and hit route handler
        try:
            body = r.json()
            assert body.get("code") != "AUTH_REQUIRED"
        except ValueError:
            pass  # non-JSON response is fine — proves middleware passed

    def test_auth_complete_csrf_exempt(self):
        """POST without X-Requested-With header should not be CSRF-blocked."""
        r = requests.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-auth-complete",
            json={"user_id": "user_nonexistent1"},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        # Should not be blocked by CSRF middleware
        assert not (r.status_code == 403 and "CSRF" in r.text), f"CSRF-blocked unexpectedly: {r.text[:200]}"


# ── Regression: registration endpoint STILL requires auth ──────
class TestRegisterOptionsRequiresAuth:
    def test_webauthn_register_options_requires_auth(self, anon_session):
        """Registration is an authenticated action, MUST require auth (regression)."""
        r = anon_session.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-register-options",
            json={},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=30,
        )
        assert r.status_code == 401, f"Register endpoint MUST require auth, got {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert body.get("code") == "AUTH_REQUIRED"


# ── Regression: password login still works ─────────────────────
class TestPasswordLoginRegression:
    def test_admin_password_login(self):
        s = requests.Session()
        r = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            timeout=30,
        )
        assert r.status_code == 200, f"Admin password login failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        assert data.get("email") == ADMIN_EMAIL
        assert data.get("user_id")
