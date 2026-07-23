"""
Phase 3 backend-only regression (iteration 14).

Scope: verify that Phase 3 (frontend-only native IAP client, universal-links
static assets, ADMIN_PASSWORD_ENFORCE_SYNC=true env change + backend restart)
did NOT regress any backend surface, and contract-verify the IAP endpoints
consumed by the new expo-iap native client.

Zero backend code changes are expected in this phase, so this is a pure
regression sweep.

Backend endpoints exercised:
- GET  /api/health
- POST /api/auth/login  (web-cookie mode AND native-bearer mode)
- GET  /api/iap/products             (no auth)
- POST /api/iap/apple/verify         (auth; bogus payload → structured error)
- POST /api/iap/google/verify        (auth; bogus payload → structured error)
- GET  /api/iap/status               (auth)
- GET  /api/auth/sso-config/native   (public, Phase 2B regression)
- POST /api/auth/google/native       (garbage id_token → 401)
- POST /api/auth/apple/native        (garbage identity_token → 401)
- POST /api/notifications/push-token (register)
- DELETE /api/notifications/push-token
- GET  /api/scenarios                (bearer)

Real Apple/Google receipts cannot be exercised here — bogus payloads are
expected to fail at the provider-auth stage with a structured 4xx/5xx error
(NOT 422 Pydantic validation), which is what proves the contract shape.
"""

import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set in the environment"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

EXPECTED_PRODUCTS = {
    "com.realaicoach.basic.monthly",
    "com.realaicoach.basic.yearly",
    "com.realaicoach.premium.monthly",
    "com.realaicoach.premium.yearly",
}


# --- Shared fixtures --------------------------------------------------------


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def native_session(http):
    """Native/mobile login → session_token in JSON body."""
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
        "roles": body.get("roles", []),
    }


@pytest.fixture(scope="module")
def native_headers(native_session):
    return {
        "Authorization": f"Bearer {native_session['token']}",
        "X-Client-Platform": "mobile",
        "Content-Type": "application/json",
    }


# --- 1. Health --------------------------------------------------------------


def test_health(http):
    r = http.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("status") == "healthy"
    assert body.get("init") == "complete"
    assert body.get("service") == "RealAICoach API"


# --- 2. Auth: web-cookie mode (no token in body) ----------------------------


def test_login_web_cookie_mode():
    """Web mode: no X-Client-Platform header → cookie only, no body token.

    This confirms ADMIN_PASSWORD_ENFORCE_SYNC=true restart still leaves admin
    creds working AND that web-mode behavior is unchanged.
    """
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("email") == ADMIN_EMAIL
    assert body.get("is_admin") is True
    # No bearer token in body when platform != mobile
    assert "session_token" not in body or body.get("session_token") in (None, "")
    # httpOnly cookie was set
    set_cookie = r.headers.get("set-cookie", "")
    assert "session_token" in set_cookie.lower()
    assert "httponly" in set_cookie.lower()


# --- 3. Auth: native-bearer mode (token in body) ----------------------------


def test_login_native_bearer_mode(native_session):
    assert native_session["token"], "native session_token missing"
    # JWT-shape (3 dot-separated segments)
    assert native_session["token"].count(".") == 2, "session_token not JWT-shaped"
    assert native_session["email"] == ADMIN_EMAIL
    assert native_session["is_admin"] is True


# --- 4. IAP products: public, 4 known products ------------------------------


def test_iap_products_public_shape(http):
    """GET /api/iap/products — endpoint is designed to work without auth
    (get_current_user returns None gracefully). Returns list of product IDs.
    """
    r = http.get(f"{BASE_URL}/api/iap/products")
    assert r.status_code == 200, r.text[:300]
    payload = r.json()
    # Contract may return {"products": [...]} — locate the list of product IDs
    products_raw = payload.get("products") if isinstance(payload, dict) else payload
    assert isinstance(products_raw, list), f"products key must be a list: {type(products_raw)}"

    product_ids = set()
    for entry in products_raw:
        if isinstance(entry, str):
            product_ids.add(entry)
        elif isinstance(entry, dict):
            pid = entry.get("product_id") or entry.get("id") or entry.get("sku")
            if pid:
                product_ids.add(pid)

    missing = EXPECTED_PRODUCTS - product_ids
    assert not missing, (
        f"Missing expected IAP product IDs: {missing}. "
        f"Found: {sorted(product_ids)}"
    )


# --- 5. IAP apple/verify: bogus payload → structured non-422 error ----------


def test_iap_apple_verify_bogus_contract_shape(native_headers):
    """Bogus payload must pass Pydantic validation (not 422) and be rejected
    at the provider-auth stage with a structured 4xx/5xx error mentioning
    Apple.
    """
    r = requests.post(
        f"{BASE_URL}/api/iap/apple/verify",
        json={"transaction_id": "123456", "receipt_data": "bogus"},
        headers=native_headers,
    )
    assert r.status_code != 422, f"contract shape rejected: {r.status_code} {r.text[:300]}"
    assert 400 <= r.status_code < 600, r.status_code
    # Not authenticated would be 401 — we sent Bearer, so ensure not the auth wall
    assert r.status_code != 401, "should be past auth (bearer session valid)"
    body = r.text.lower()
    # Structured error message from Apple verification path (or a 5xx from provider auth stage)
    assert "apple" in body or "receipt" in body or "invalid" in body or "authentic" in body, (
        f"expected structured Apple error, got: {r.text[:400]}"
    )


# --- 6. IAP google/verify: bogus payload → structured non-422 error ---------


def test_iap_google_verify_bogus_contract_shape(native_headers):
    r = requests.post(
        f"{BASE_URL}/api/iap/google/verify",
        json={"purchase_token": "bogus", "product_id": "com.realaicoach.basic.monthly"},
        headers=native_headers,
    )
    assert r.status_code != 422, f"contract shape rejected: {r.status_code} {r.text[:300]}"
    assert 400 <= r.status_code < 600, r.status_code
    assert r.status_code != 401, "should be past auth (bearer session valid)"
    body = r.text.lower()
    # Structured google-side failure keywords
    assert (
        "google" in body
        or "invalid" in body
        or "purchase" in body
        or "grant" in body
        or "auth" in body
    ), f"expected structured Google error, got: {r.text[:400]}"


# --- 7. IAP status: authed shape --------------------------------------------


def test_iap_status_authed(native_headers):
    r = requests.get(f"{BASE_URL}/api/iap/status", headers=native_headers)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # Contract fields
    assert "plan" in body
    assert "status" in body
    assert "auto_renewing" in body
    assert isinstance(body.get("plan"), str)
    assert isinstance(body.get("status"), str)


# --- 8. Phase 2B regression: /api/auth/sso-config/native --------------------


def test_sso_config_native_public(http):
    r = http.get(f"{BASE_URL}/api/auth/sso-config/native")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("google_ios_client_id"), "google_ios_client_id must be non-null"
    assert body["google_ios_client_id"].endswith(".apps.googleusercontent.com")


# --- 9. Phase 2B regression: /api/auth/google/native garbage token → 401 ----


def test_google_native_garbage_token_returns_401(http):
    r = http.post(
        f"{BASE_URL}/api/auth/google/native",
        json={"id_token": "not-a-real-google-token"},
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    assert r.status_code != 500


# --- 10. Phase 2B regression: /api/auth/apple/native garbage token → 401 ----


def test_apple_native_garbage_token_returns_401(http):
    r = http.post(
        f"{BASE_URL}/api/auth/apple/native",
        json={"identity_token": "not-a-real-apple-jwt"},
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"
    assert r.status_code != 500


# --- 11. Push token register + delete lifecycle -----------------------------


def test_push_token_register_then_delete(native_headers):
    reg = requests.post(
        f"{BASE_URL}/api/notifications/push-token",
        json={"push_token": "ExponentPushToken[t2]"},
        headers=native_headers,
    )
    assert reg.status_code == 200, reg.text[:300]
    assert reg.json().get("success") is True

    dele = requests.delete(
        f"{BASE_URL}/api/notifications/push-token",
        headers=native_headers,
    )
    assert dele.status_code == 200, dele.text[:300]
    assert dele.json().get("success") is True


# --- 12. Scenarios: coaching content intact --------------------------------


def test_scenarios_bearer_list(native_headers):
    r = requests.get(f"{BASE_URL}/api/scenarios", headers=native_headers)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # Endpoint may return either a list directly or {"scenarios": [...]}
    scenarios = body if isinstance(body, list) else body.get("scenarios", body.get("items", []))
    assert isinstance(scenarios, list) and len(scenarios) > 0, (
        f"expected non-empty scenarios list, got: {str(body)[:400]}"
    )
