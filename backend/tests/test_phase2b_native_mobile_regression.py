"""
Phase 2B backend regression tests: native mobile SSO endpoints, voice-message
audio_format field, push token register/delete, native bearer session flow,
and coaching regression (LLM path).

Scope: BACKEND ONLY. No frontend interaction. Real Google/Apple provider tokens
are NOT exercised — we only assert 400/401 branches (garbage token paths).
"""

import os
import time

import pytest
import requests


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://full-stack-migrate-1.preview.emergentagent.com",
).rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


# --- Shared fixtures ---------------------------------------------------------


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def native_session(http):
    """Login as admin in native/mobile mode → session_token in JSON body."""
    r = http.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Client-Platform": "mobile"},
    )
    assert r.status_code == 200, f"native login failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body.get("session_token"), "native login must return session_token in body"
    return {
        "token": body["session_token"],
        "user_id": body.get("user_id"),
        "email": body.get("email"),
        "is_admin": body.get("is_admin"),
        "roles": body.get("roles"),
    }


@pytest.fixture(scope="module")
def native_headers(native_session):
    return {
        "Authorization": f"Bearer {native_session['token']}",
        "X-Client-Platform": "mobile",
        "Content-Type": "application/json",
    }


# --- 1. Health ---------------------------------------------------------------


def test_health(http):
    r = http.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "healthy"
    assert body.get("service") == "RealAICoach API"


# --- 2. Web cookie login: no session_token in body ---------------------------


def test_login_web_cookie_no_body_token(http):
    r = requests.post(  # fresh session — don't pollute module session with cookie
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "session_token" not in body, f"web login must NOT expose session_token in body; got {list(body.keys())}"
    # httpOnly cookie must be set
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert "session_token=" in set_cookie
    assert "httponly" in set_cookie
    assert body.get("email") == ADMIN_EMAIL
    assert body.get("is_admin") is True


# --- 3. Native login: session_token in body ---------------------------------


def test_login_native_bearer_returns_body_token(native_session):
    assert native_session["token"].count(".") == 2  # JWT shape
    assert native_session["email"] == ADMIN_EMAIL
    assert native_session["is_admin"] is True
    assert "admin" in (native_session["roles"] or [])


# --- 4. /auth/sso-config/native is public + correct shape --------------------


def test_native_sso_config_public_shape(http):
    # No auth, no cookie → still 200
    r = requests.get(f"{BASE_URL}/api/auth/sso-config/native")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("google_ios_client_id") is not None, "google_ios_client_id must be non-null"
    assert isinstance(body["google_ios_client_id"], str)
    assert body["google_ios_client_id"].endswith(".apps.googleusercontent.com")
    assert body.get("google_android_client_id") is None, "google_android_client_id must be null (env not set)"
    assert body.get("apple_native_enabled") is True
    assert body.get("apple_bundle_id") == "com.realaicoach.app"


# --- 5. Google native SSO error branches ------------------------------------


def test_google_native_missing_id_token_400(http):
    r = requests.post(f"{BASE_URL}/api/auth/google/native", json={})
    assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:200]}"
    assert "id_token required" in r.text


def test_google_native_garbage_token_401(http):
    r = requests.post(
        f"{BASE_URL}/api/auth/google/native",
        json={"id_token": "not-a-real-google-token"},
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text[:200]}"
    assert "Invalid Google token" in r.text


# --- 6. Apple native SSO error branches -------------------------------------


def test_apple_native_missing_identity_token_400(http):
    r = requests.post(f"{BASE_URL}/api/auth/apple/native", json={})
    assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:200]}"
    assert "identity_token required" in r.text


def test_apple_native_garbage_token_401(http):
    r = requests.post(
        f"{BASE_URL}/api/auth/apple/native",
        json={"identity_token": "not-a-real-apple-jwt"},
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text[:200]}"
    assert "Invalid Apple identity token" in r.text


# --- 7. /auth/me with native bearer -----------------------------------------


def test_auth_me_native_bearer(native_headers):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=native_headers)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("email") == ADMIN_EMAIL
    assert body.get("is_admin") is True


# --- 8. Scenarios list w/ native bearer -------------------------------------


@pytest.fixture(scope="module")
def scenarios(native_headers):
    r = requests.get(f"{BASE_URL}/api/scenarios", headers=native_headers)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    # Accept either list or {scenarios: [...]}
    if isinstance(data, dict) and "scenarios" in data:
        data = data["scenarios"]
    assert isinstance(data, list) and len(data) > 0, "expected non-empty scenarios list"
    return data


def test_scenarios_bearer_returns_list(scenarios):
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 1
    assert any(("id" in s) for s in scenarios)


# --- 9. Voice-message audio_format accepted (404 on nonexistent conv) -------


def test_voice_message_audio_format_accepted(native_headers):
    payload = {
        "conversation_id": "nonexistent",
        "user_id": "x",
        "audio_base64": "aGVsbG8=",
        "audio_format": "m4a",
    }
    r = requests.post(
        f"{BASE_URL}/api/conversations/voice-message",
        json=payload,
        headers=native_headers,
    )
    # Must NOT be 422 (that would mean audio_format field was rejected)
    assert r.status_code != 422, f"audio_format field rejected: {r.text[:300]}"
    assert r.status_code == 404, f"expected 404 Conversation not found, got {r.status_code} {r.text[:200]}"
    assert "Conversation not found" in r.text


# --- 10. Push token register + delete ---------------------------------------


def test_push_token_register_then_delete(native_headers):
    reg = requests.post(
        f"{BASE_URL}/api/notifications/push-token",
        json={"push_token": "ExponentPushToken[test123]"},
        headers=native_headers,
    )
    assert reg.status_code == 200, reg.text[:300]
    body = reg.json()
    assert body.get("success") is True

    delr = requests.delete(
        f"{BASE_URL}/api/notifications/push-token",
        headers=native_headers,
    )
    assert delr.status_code == 200, delr.text[:300]
    assert delr.json().get("success") is True


# --- 11. Coaching regression: start → message (LLM path) --------------------


def test_coaching_start_and_message(native_headers, scenarios, native_session):
    scenario_id = scenarios[0]["id"]
    start = requests.post(
        f"{BASE_URL}/api/conversations/start",
        json={"scenario_id": scenario_id, "user_id": native_session["user_id"]},
        headers=native_headers,
        timeout=60,
    )
    assert start.status_code == 200, f"start failed: {start.status_code} {start.text[:300]}"
    conv = start.json()
    conv_id = conv.get("id") or conv.get("conversation_id") or (conv.get("conversation") or {}).get("id")
    assert conv_id, f"no conversation id returned: {conv}"

    time.sleep(1)

    msg = requests.post(
        f"{BASE_URL}/api/conversations/message",
        json={
            "conversation_id": conv_id,
            "user_id": native_session["user_id"],
            "message": "Hi",
        },
        headers=native_headers,
        timeout=120,
    )
    body_txt = msg.text[:500]
    if msg.status_code != 200:
        # Explicit circuit-breaker call-out per review request
        if "scaling" in body_txt.lower() or "circuit" in body_txt.lower() or "paused" in body_txt.lower():
            pytest.skip(f"LLM circuit breaker paused (pre-existing runtime state): {body_txt}")
    assert msg.status_code == 200, f"message failed: {msg.status_code} {body_txt}"
    data = msg.json()
    # Structure per core_platform.py: assistant_message + feedback
    assert "assistant_message" in data or "message" in data, f"no assistant_message key: {list(data.keys())}"
    # Feedback presence (soft-check — allow missing if scenario type doesn't emit)
    assert "feedback" in data or data.get("assistant_message"), f"expected feedback in {list(data.keys())}"
