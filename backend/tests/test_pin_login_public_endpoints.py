"""Verification tests for the P0 PIN Login fix.

Verifies that POST /api/auth/biometric/verify-pin is:
1. Public (no AUTH_REQUIRED without session)
2. CSRF-exempt (works without X-Requested-With header)
3. Returns proper HTTP statuses (404 no PIN, 404 non-existent user)

Regression:
- webauthn-auth-options remains public
- webauthn-register-options still requires auth (401 AUTH_REQUIRED)
- Password login for admin still works
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
VERIFY_PIN_URL = f"{BASE_URL}/api/auth/biometric/verify-pin"
LOOKUP_URL = f"{BASE_URL}/api/auth/lookup"
LOGIN_URL = f"{BASE_URL}/api/auth/login"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_user_id() -> str:
    """Resolve the admin user_id via /auth/lookup (public endpoint)."""
    r = requests.get(LOOKUP_URL, params={"email": ADMIN_EMAIL}, timeout=15)
    assert r.status_code == 200, f"lookup returned {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("exists") is True
    uid = data.get("user_id")
    assert uid, "admin user_id missing from lookup"
    return uid


# ── verify-pin public access (P0 fix) ──

class TestVerifyPinPublicAccess:
    def test_verify_pin_no_auth_no_csrf_returns_404_no_pin(self, admin_user_id):
        """P0: Without session cookie AND without X-Requested-With header,
        endpoint should be reachable and return 404 'No PIN set' (admin has no PIN)."""
        r = requests.post(
            VERIFY_PIN_URL,
            json={"user_id": admin_user_id, "pin": "0000"},
            timeout=15,
        )
        # MUST NOT be 401 AUTH_REQUIRED or 403 CSRF
        assert r.status_code not in (401, 403), (
            f"verify-pin blocked by middleware (status={r.status_code}, body={r.text[:200]})"
        )
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"
        detail = r.json().get("detail", "")
        assert "PIN" in detail or "pin" in detail, f"unexpected detail: {detail}"

    def test_verify_pin_with_xrw_header_still_works(self, admin_user_id):
        """Sanity: X-Requested-With header does not break the flow either."""
        r = requests.post(
            VERIFY_PIN_URL,
            json={"user_id": admin_user_id, "pin": "0000"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code not in (401, 403)
        assert r.status_code == 404

    def test_verify_pin_nonexistent_user_returns_404(self):
        """Bogus user_id → 404 (No PIN set → because pin lookup returns None)."""
        r = requests.post(
            VERIFY_PIN_URL,
            json={"user_id": "user_does_not_exist_zzz", "pin": "1234"},
            timeout=15,
        )
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"


# ── Regression: other public/private endpoints unchanged ──

class TestRegressionPasskeyEndpoints:
    def test_webauthn_auth_options_still_public(self, admin_user_id):
        """POST /api/auth/biometric/webauthn-auth-options must remain public."""
        url = f"{BASE_URL}/api/auth/biometric/webauthn-auth-options"
        r = requests.post(url, json={"user_id": admin_user_id}, timeout=15)
        # Should NOT return AUTH_REQUIRED (401 from middleware). Admin has no
        # passkey enrolled, so 404 (no credential) is expected.
        assert r.status_code != 401 or "AUTH_REQUIRED" not in r.text
        assert r.status_code in (200, 404), f"unexpected status {r.status_code}: {r.text[:200]}"

    def test_webauthn_register_options_still_requires_auth(self):
        """POST /api/auth/biometric/webauthn-register-options MUST still require auth."""
        url = f"{BASE_URL}/api/auth/biometric/webauthn-register-options"
        r = requests.post(url, json={}, timeout=15)
        assert r.status_code == 401, (
            f"webauthn-register-options should require auth, got {r.status_code}: {r.text[:200]}"
        )
        # Middleware AUTH_REQUIRED code
        body = r.text
        assert "AUTH_REQUIRED" in body or "authentication" in body.lower() or "unauthorized" in body.lower()


class TestRegressionPasswordLogin:
    def test_admin_password_login_works(self):
        """Admin password login regression."""
        r = requests.post(
            LOGIN_URL,
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=20,
        )
        assert r.status_code in (200, 202), f"admin login failed: {r.status_code} {r.text[:300]}"
