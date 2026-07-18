"""
Iteration 11 — Web regression suite for the mobile/native enablement change.

Web behaviour MUST be unchanged. We verify:
  1. GET /api/health -> 200
  2. POST /api/auth/login (admin) sets httpOnly session_token cookie
  3. GET /api/auth/me works with cookie
  4. GET /api/admin/scaling/status returns 200 for admin (regression)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://full-stack-migrate-1.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


# -------------------- health --------------------
def test_api_health_returns_200():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15, verify=False)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "healthy"
    assert body.get("service") == "RealAICoach API"


# -------------------- admin login (cookie) --------------------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.verify = False
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return s


def test_admin_login_sets_httponly_cookie(admin_session):
    # Session must carry a session_token cookie after login
    cookies = admin_session.cookies
    assert "session_token" in cookies.keys(), f"missing session_token cookie; got {list(cookies.keys())}"
    # httpOnly flag is set server-side; we can only confirm via raw response headers.
    # Re-issue login through a fresh session to inspect Set-Cookie.
    fresh = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
        timeout=30,
        verify=False,
    )
    set_cookie = fresh.headers.get("set-cookie", "") or fresh.headers.get("Set-Cookie", "")
    assert "session_token" in set_cookie, set_cookie
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower(), set_cookie


def test_admin_login_returns_admin_role(admin_session):
    # /api/auth/login response body contains user info
    r = admin_session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
        timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("email") == ADMIN_EMAIL
    assert body.get("is_admin") is True
    assert "admin" in body.get("roles", [])


# -------------------- authenticated endpoints via cookie --------------------
def test_auth_me_with_cookie(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("email") == ADMIN_EMAIL
    assert body.get("is_admin") is True


def test_admin_scaling_status_with_cookie(admin_session):
    # Regression from iter-10 circuit-breaker work
    r = admin_session.get(f"{BASE_URL}/api/admin/scaling/status", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "llm_circuit_breaker" in body
    assert body["llm_circuit_breaker"].get("paused") in (False, True)  # field present
    assert "instances" in body
    assert "metrics" in body


# -------------------- unauthenticated regression --------------------
def test_admin_scaling_status_anon_forbidden():
    r = requests.get(f"{BASE_URL}/api/admin/scaling/status", timeout=15, verify=False)
    assert r.status_code in (401, 403), r.text


# -------------------- native manifest sanity (localhost:3001) --------------------
def test_native_manifest_via_proxy():
    # Direct pod check — proxy at :3001 forwards to Metro on :3000.
    try:
        r = requests.get(
            "http://localhost:3001/",
            headers={"expo-platform": "android", "Accept": "application/expo+json,application/json"},
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        pytest.skip(f"metro-proxy unreachable inside pod: {e}")

    assert r.status_code == 200, r.text[:500]
    body = r.json()
    assert body.get("runtimeVersion", "").startswith("exposdk:")
    expo_client = body.get("extra", {}).get("expoClient", {})
    assert expo_client.get("name") == "RealAICoach", expo_client
    assert expo_client.get("slug") == "realaicoach"
