"""
Comprehensive E2E Auth verification for /auth/login page.
Tests every login method and supporting backend endpoint.

Ref request: full E2E verify (Password, OTP, QR, PIN, Passkey, SSO, Remember Me, Register, Forgot Password).
Web is cookie-based (WEB_COOKIE_ONLY_AUTH=true). CSRF: X-Requested-With: XMLHttpRequest required unless endpoint is in CSRF_EXEMPT_PREFIXES.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update(CSRF_HEADERS)
    return s


# ---------------- Backend health ----------------
def test_health_backend_reachable(client):
    r = client.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code in (200, 404), f"Backend reachability: {r.status_code}"


# ---------------- Password login (admin) ----------------
def test_login_admin_password_success(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": False,
    }, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    # Some deployments return {user:{...}} or the user directly. Just check identifying field:
    assert "user" in data or "email" in data or "id" in data or "session_token" in data
    # cookie is set
    sess_cookie = [c for c in client.cookies if "session" in c.name.lower() or "sid" in c.name.lower()]
    assert sess_cookie, f"No session cookie set. Cookies: {list(client.cookies.keys())}"


def test_login_admin_auth_me_returns_user(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": False,
    }, timeout=15)
    assert r.status_code == 200
    me = client.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert me.status_code == 200, f"/auth/me failed: {me.status_code} {me.text[:200]}"
    body = me.json()
    email = body.get("email") or (body.get("user") or {}).get("email")
    assert email == ADMIN_EMAIL


def test_logout_clears_session(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": False,
    }, timeout=15)
    assert r.status_code == 200
    lo = client.post(f"{BASE_URL}/api/auth/logout", timeout=15)
    assert lo.status_code in (200, 204), f"logout: {lo.status_code} {lo.text[:200]}"
    me = client.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert me.status_code == 401, f"/auth/me post-logout should 401, got {me.status_code}"


# ---------------- Login failure paths ----------------
def test_login_wrong_password_returns_401(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": "definitely_wrong_pw!!!", "remember_me": False,
    }, timeout=15)
    assert r.status_code in (400, 401), f"Wrong password should reject: {r.status_code}"


def test_login_nonexistent_email(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json={
        "email": f"nobody_{uuid.uuid4().hex[:8]}@example.com", "password": "somepass", "remember_me": False,
    }, timeout=15)
    assert r.status_code in (400, 401, 404), f"Non-existent email: {r.status_code}"


# ---------------- Free user login ----------------
def test_login_free_user_success(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_EMAIL, "password": FREE_PASSWORD, "remember_me": False,
    }, timeout=15)
    assert r.status_code == 200, f"Free user login failed: {r.status_code} {r.text[:300]}"


# ---------------- Lookup ----------------
def test_lookup_admin_exists_true(client):
    r = client.get(f"{BASE_URL}/api/auth/lookup", params={"email": ADMIN_EMAIL}, timeout=15)
    assert r.status_code == 200, f"lookup: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("exists") is True, f"exists field: {data}"


def test_lookup_nonexistent_email(client):
    r = client.get(f"{BASE_URL}/api/auth/lookup", params={"email": f"nobody_{uuid.uuid4().hex[:8]}@example.com"}, timeout=15)
    # Anti-enumeration: endpoint may return exists=true for unknown emails to avoid leaking user existence.
    # Just verify it responds 200 with an "exists" field.
    assert r.status_code == 200
    assert "exists" in r.json()


# ---------------- QR ----------------
def test_qr_generate_returns_session_and_url(client):
    r = client.post(f"{BASE_URL}/api/auth/qr/generate", json={}, timeout=15)
    assert r.status_code == 200, f"qr/generate: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert "session_id" in data, f"no session_id: {data}"
    # qr_url may be called different things but should exist
    assert "qr_url" in data or "url" in data or "qr_code" in data or "qr_data" in data, f"missing qr url field: {list(data.keys())}"


# ---------------- Biometric PIN (pre-login) ----------------
def test_verify_pin_public_no_pin_set(client):
    # Try without cookie/session — should be reachable (public endpoint)
    fresh = requests.Session()
    fresh.headers.update(CSRF_HEADERS)
    # Need a user_id — get via lookup? Lookup returns user id maybe
    look = fresh.get(f"{BASE_URL}/api/auth/lookup", params={"email": ADMIN_EMAIL}, timeout=15)
    assert look.status_code == 200
    user_id = look.json().get("user_id") or look.json().get("id")
    if not user_id:
        pytest.skip(f"lookup didn't return user_id: {look.json()}")
    r = fresh.post(f"{BASE_URL}/api/auth/biometric/verify-pin", json={"user_id": user_id, "pin": "0000"}, timeout=15)
    # Admin has no PIN → 404, or wrong pin → 401. Not 403 or 401 AUTH_REQUIRED
    assert r.status_code in (401, 404), f"verify-pin should be reachable: {r.status_code} {r.text[:200]}"
    body = r.text.lower()
    assert "auth_required" not in body, f"middleware blocked verify-pin: {r.text[:200]}"


def test_verify_pin_no_csrf_header_still_works(client):
    fresh = requests.Session()
    fresh.headers.update({"Content-Type": "application/json"})  # NO X-Requested-With
    r = fresh.post(f"{BASE_URL}/api/auth/biometric/verify-pin", json={"user_id": "nonexistent_user", "pin": "1234"}, timeout=15)
    assert r.status_code in (400, 401, 404), f"verify-pin CSRF-exempt but got {r.status_code} {r.text[:200]}"


# ---------------- Passkey / WebAuthn (pre-login) ----------------
def test_has_passkey_public(client):
    fresh = requests.Session()
    fresh.headers.update(CSRF_HEADERS)
    # Endpoint requires user_id. Get it via lookup first.
    look = fresh.get(f"{BASE_URL}/api/auth/lookup", params={"email": ADMIN_EMAIL}, timeout=15)
    user_id = look.json().get("user_id") or look.json().get("id")
    if not user_id:
        pytest.skip("lookup did not return user_id")
    r = fresh.get(f"{BASE_URL}/api/auth/biometric/has-passkey", params={"user_id": user_id}, timeout=15)
    assert r.status_code == 200, f"has-passkey: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert "has_passkey" in data or "enrolled" in data or "exists" in data


def test_webauthn_auth_options_public(client):
    fresh = requests.Session()
    fresh.headers.update(CSRF_HEADERS)
    r = fresh.post(f"{BASE_URL}/api/auth/biometric/webauthn-auth-options", json={"email": ADMIN_EMAIL}, timeout=15)
    # Public endpoint. Admin may not have passkeys → 400/404 acceptable, but not 401 AUTH_REQUIRED
    assert r.status_code in (200, 400, 404), f"webauthn-auth-options: {r.status_code} {r.text[:200]}"
    assert "auth_required" not in r.text.lower()


# ---------------- Register ----------------
def test_register_new_user_succeeds(client):
    email = f"test_e2e_{int(time.time())}_{uuid.uuid4().hex[:6]}@example.com"
    r = client.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "TestE2E#2026!Aa", "name": "E2E Test User",
    }, timeout=20)
    assert r.status_code in (200, 201), f"register: {r.status_code} {r.text[:300]}"
    data = r.json()
    # Should have some form of user id
    assert data.get("user_id") or data.get("id") or (data.get("user") or {}).get("id"), f"no user_id: {data}"


def test_register_duplicate_email_rejected(client):
    r = client.post(f"{BASE_URL}/api/auth/register", json={
        "email": ADMIN_EMAIL, "password": "SomePass#2026!Aa", "name": "Duplicate Admin",
    }, timeout=15)
    assert r.status_code in (400, 409, 422), f"duplicate register: {r.status_code} {r.text[:200]}"


# ---------------- Password reset ----------------
def test_password_reset_request_valid_email(client):
    r = client.post(f"{BASE_URL}/api/auth/password/reset/request", json={"email": ADMIN_EMAIL}, timeout=15)
    # Usually 200 with generic success (to prevent user enumeration)
    assert r.status_code in (200, 202), f"password reset request: {r.status_code} {r.text[:200]}"


# ---------------- Remember Me cookie Max-Age ----------------
def test_remember_me_true_sets_30_day_cookie(client):
    fresh = requests.Session()
    fresh.headers.update(CSRF_HEADERS)
    r = fresh.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": True,
    }, timeout=15)
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "max-age=2592000" in set_cookie.lower() or "max-age=2592000" in set_cookie, f"expected 30-day Max-Age (2592000) in Set-Cookie: {set_cookie}"


def test_remember_me_false_sets_5h_cookie(client):
    fresh = requests.Session()
    fresh.headers.update(CSRF_HEADERS)
    r = fresh.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": False,
    }, timeout=15)
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "max-age=18000" in set_cookie.lower(), f"expected 5-hour Max-Age (18000) in Set-Cookie: {set_cookie}"


# ---------------- Renew session ----------------
def test_renew_session_with_valid_cookie(client):
    r = client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "remember_me": False,
    }, timeout=15)
    assert r.status_code == 200
    renew = client.post(f"{BASE_URL}/api/auth/renew-session", json={}, timeout=15)
    assert renew.status_code in (200, 204), f"renew-session: {renew.status_code} {renew.text[:200]}"
