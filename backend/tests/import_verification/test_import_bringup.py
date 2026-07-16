"""
Import verification tests for RealAICoach backend bring-up.
Tests: health, register/login (fresh user), admin login, /api/openapi.json access, /api/auth/me
Auth mechanism: httpOnly `session_token` cookie set by POST /api/auth/login
"""
import os
import random
import string
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback: read from frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _rand(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


@pytest.fixture(scope="module")
def anon_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def fresh_user_creds():
    return {
        "email": f"importtest+{_rand()}@example.com",
        "password": "TestPass2026!",
        "name": "Import Tester",
    }


# --- Health ---
def test_health(anon_session):
    r = anon_session.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "healthy"


# --- Auth register + login (fresh user) ---
def test_register_new_user(anon_session, fresh_user_creds):
    r = anon_session.post(
        f"{BASE_URL}/api/auth/register",
        json=fresh_user_creds,
        timeout=30,
    )
    # 200/201 success; 409/400 if pre-exists (unlikely)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text[:400]}"


def test_login_new_user_sets_cookie(fresh_user_creds):
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": fresh_user_creds["email"], "password": fresh_user_creds["password"]},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:400]}"
    # Session cookie set
    cookies = {c.name: c.value for c in s.cookies}
    assert "session_token" in cookies, f"No session_token cookie; got: {list(cookies.keys())}"
    # auth/me works
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert me.status_code == 200, f"/auth/me failed: {me.status_code} {me.text[:300]}"
    body = me.json()
    assert isinstance(body, dict)
    # email should be present somewhere
    email_val = body.get("email") or (body.get("user") or {}).get("email")
    assert email_val == fresh_user_creds["email"], f"email mismatch: {body}"


# --- Admin login ---
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:400]}"
    assert any(c.name == "session_token" for c in s.cookies), "no session_token for admin"
    return s


def test_admin_login_and_me(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    email_val = body.get("email") or (body.get("user") or {}).get("email")
    assert email_val == ADMIN_EMAIL


# --- openapi.json admin-gated ---
def test_openapi_requires_admin_401_anon(anon_session):
    r = anon_session.get(f"{BASE_URL}/api/openapi.json", timeout=15, allow_redirects=False)
    # Should be denied for anon (401 or 403)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:300]}"


def test_openapi_admin_200(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/openapi.json", timeout=30)
    assert r.status_code == 200, f"admin openapi failed: {r.status_code} {r.text[:400]}"
    body = r.json()
    assert "openapi" in body or "paths" in body


# --- One admin-authenticated endpoint ---
def test_admin_endpoint_accessible(admin_session):
    # Try a common admin endpoint. If not present, test simply asserts we can hit /api/auth/me twice.
    r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200
    body = r.json()
    roles = body.get("roles") or (body.get("user") or {}).get("roles") or []
    # admin should have admin role per test_credentials
    assert "admin" in roles or body.get("is_admin") is True or (body.get("user") or {}).get("is_admin") is True, \
        f"admin flag not found in /auth/me: {body}"
