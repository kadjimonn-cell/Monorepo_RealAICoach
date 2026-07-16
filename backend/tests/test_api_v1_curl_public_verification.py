"""Iteration 841 — Additional curl-style verification of the Web-First / Multi-Platform
API v1 architecture over the PUBLIC preview URL (ingress path).

This complements test_api_v1_multiplatform_architecture.py which hits the ASGI app
via TestClient. Here we ensure that the middleware behaves identically when the
request actually goes through the Kubernetes ingress + reverse proxy at
REACT_APP_BACKEND_URL, since that is what real web/mobile clients will use.
"""

from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read frontend/.env directly if env not exported
    with open("/app/frontend/.env", "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

CSRF_HEADER = {"X-Requested-With": "XMLHttpRequest"}
NATIVE_HEADER = {"X-Client-Platform": "ios", **CSRF_HEADER}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# Health parity — /api/health vs /api/v1/health
# ---------------------------------------------------------------------------
class TestHealthParity:
    def test_legacy_health(self, session):
        r = session.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200, r.text
        assert "x-api-version" not in {k.lower() for k in r.headers.keys()}

    def test_v1_health(self, session):
        r = session.get(f"{BASE_URL}/api/v1/health", timeout=15)
        assert r.status_code == 200, r.text
        # header MUST be present on versioned responses
        assert r.headers.get("x-api-version") == "1" or r.headers.get("X-API-Version") == "1"


# ---------------------------------------------------------------------------
# Public bootstrap contract
# ---------------------------------------------------------------------------
class TestClientBootstrapPublic:
    def test_versioned_bootstrap(self, session):
        r = session.get(f"{BASE_URL}/api/v1/client/bootstrap", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["api_version"] == "v1"
        assert data["theming"]["app_theme_contract"] == "v2-light-dark"
        assert data["theming"]["email_theme_contract"] == "v7-light-dark"
        assert data["auth"]["native_token_header"] == "X-Client-Platform"
        assert data["auth"]["refresh_tokens_supported"] is True
        assert data["auth"]["mfa_supported"] is True
        assert "google" in data["auth"]["oauth_providers"]
        # docs sub-map
        assert data["docs"]["openapi_url"] == "/api/v1/openapi.json"
        # header
        assert r.headers.get("x-api-version") == "1" or r.headers.get("X-API-Version") == "1"

    def test_legacy_bootstrap_alias(self, session):
        r = session.get(f"{BASE_URL}/api/client/bootstrap", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["api_version"] == "v1"
        # legacy path must NOT include the version header
        assert "x-api-version" not in {k.lower() for k in r.headers.keys()}

    def test_bootstrap_echoes_native_platform(self, session):
        r = session.get(
            f"{BASE_URL}/api/v1/client/bootstrap",
            headers={"X-Client-Platform": "android"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["client_platform"] == "android"


# ---------------------------------------------------------------------------
# Auth gate & docs
# ---------------------------------------------------------------------------
class TestAuthGate:
    def test_openapi_requires_auth(self, session):
        r = session.get(f"{BASE_URL}/api/v1/openapi.json", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_docs_requires_auth(self, session):
        r = session.get(f"{BASE_URL}/api/v1/docs", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_admin_users_versioned_requires_auth(self, session):
        r = session.get(f"{BASE_URL}/api/v1/admin/users", timeout=15)
        assert r.status_code in (401, 403), r.status_code


# ---------------------------------------------------------------------------
# Native auth channel
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_native_bearer(session):
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=NATIVE_HEADER,
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"admin native login failed: {r.status_code} {r.text[:200]}")
    body = r.json()
    token = body.get("session_token") or body.get("access_token") or body.get("token")
    if not token:
        pytest.skip(f"native login body missing session_token: keys={list(body.keys())}")
    return token


class TestNativeAuthChannel:
    def test_native_login_returns_tokens_in_body(self, session):
        r = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers=NATIVE_HEADER,
            timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        # At minimum a session/access token must exist in body for native
        assert (
            "session_token" in body or "access_token" in body or "token" in body
        ), f"no bearer token in body; keys={list(body.keys())}"

    def test_web_login_does_not_leak_tokens_in_body(self, session):
        r = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers=CSRF_HEADER,  # no X-Client-Platform
            timeout=20,
        )
        # web login should succeed and rely on cookies; body must not carry raw tokens
        if r.status_code != 200:
            pytest.skip(f"web login unexpected status: {r.status_code}")
        body = r.json()
        # Accept absence of both — cookies-only mode
        assert "session_token" not in body and "access_token" not in body, (
            f"web login leaked tokens in body: keys={list(body.keys())}"
        )

    def test_bearer_token_grants_me(self, session, admin_native_bearer):
        r = requests.get(
            f"{BASE_URL}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {admin_native_bearer}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        me = r.json()
        assert (me.get("email") or "").lower() == ADMIN_EMAIL.lower()

    def test_admin_openapi_with_bearer(self, session, admin_native_bearer):
        r = requests.get(
            f"{BASE_URL}/api/v1/openapi.json",
            headers={"Authorization": f"Bearer {admin_native_bearer}"},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:200]
        schema = r.json()
        assert schema.get("openapi", "").startswith("3."), f"not OpenAPI 3: {schema.get('openapi')}"
        assert "paths" in schema and isinstance(schema["paths"], dict)


# ---------------------------------------------------------------------------
# Backward compat — legacy routes still fine
# ---------------------------------------------------------------------------
class TestBackwardCompat:
    def test_features_registry(self, session):
        r = session.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert r.status_code == 200, r.text[:200]

    def test_i18n_languages(self, session):
        r = session.get(f"{BASE_URL}/api/i18n/languages", timeout=15)
        assert r.status_code == 200, r.text[:200]

    def test_flappy_bird_gate_parity(self, session):
        r_legacy = session.get(f"{BASE_URL}/api/flappy-bird/daily-challenge", timeout=15)
        r_v1 = session.get(f"{BASE_URL}/api/v1/flappy-bird/daily-challenge", timeout=15)
        # Both should exhibit the same auth behavior (either both public or both gated)
        assert r_legacy.status_code == r_v1.status_code, (
            f"legacy={r_legacy.status_code} v1={r_v1.status_code}"
        )
