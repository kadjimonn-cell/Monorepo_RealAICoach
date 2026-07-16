"""Live E2E backend tests for platform subscription access control.

Verifies with the ACTUAL preview backend that:
 - Paid API families require authentication (401/403 unauthenticated)
 - Free users get subscription_required for basic-tier families
 - Basic users can access basic-tier families
 - Basic users are blocked from premium-only families
 - Admin users can access everything

Uses REACT_APP_BACKEND_URL and real seeded test users.
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
BASIC_USER = {"email": "f21.basic.1781338672@example.com", "password": "F21Basic#2026Aa"}
ADMIN_USER = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}

# Basic-tier paid/auth families
BASIC_TIER_PATHS = [
    "/api/personal-assistant/bootstrap",
    "/api/ai-enterprise/bootstrap",
    "/api/writing-studio/bootstrap",
]

# Premium-only path used for gating check
PREMIUM_ONLY_PATH = "/api/workspace/bootstrap"


def _login(email: str, password: str) -> requests.Session:
    """Login and return an authenticated requests.Session with cookies set."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email} status={r.status_code} body={r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE_USER["email"], FREE_USER["password"])


@pytest.fixture(scope="module")
def basic_session():
    return _login(BASIC_USER["email"], BASIC_USER["password"])


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_USER["email"], ADMIN_USER["password"])


# ---------------- Unauthenticated ----------------

@pytest.mark.parametrize("path", BASIC_TIER_PATHS + [PREMIUM_ONLY_PATH])
def test_unauthenticated_blocked(path):
    """Unauthenticated calls to paid families must be rejected (not public)."""
    r = requests.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code in (401, 403), f"{path} unauthenticated -> {r.status_code} {r.text[:200]}"


# ---------------- Free user ----------------

@pytest.mark.parametrize("path", BASIC_TIER_PATHS)
def test_free_user_blocked_from_basic_tier(free_session, path):
    """Free user must be blocked with subscription_required from basic-tier features."""
    r = free_session.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code in (402, 403), f"{path} FREE -> {r.status_code} body={r.text[:300]}"
    # If body is JSON, verify subscription_required reason (never auth_required)
    try:
        body = r.json()
        body.get("reason") or body.get("detail", {}).get("reason") if isinstance(body, dict) else None
        # Compose full string for lax check
        text = str(body).lower()
        assert "subscription" in text or "plan" in text or "upgrade" in text, (
            f"{path} FREE expected subscription-related reason, got: {body}"
        )
        assert "auth_required" not in text and "login_required" not in text, (
            f"{path} FREE returned auth-required reason (should be subscription): {body}"
        )
    except ValueError:
        pass


# ---------------- Basic user ----------------

@pytest.mark.parametrize("path", BASIC_TIER_PATHS)
def test_basic_user_allowed_basic_tier(basic_session, path):
    """Basic user must be able to access basic-tier features."""
    r = basic_session.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} BASIC -> {r.status_code} body={r.text[:300]}"


def test_basic_user_blocked_from_premium(basic_session):
    """Basic user must be blocked from premium-only /api/workspace/bootstrap."""
    r = basic_session.get(f"{BASE_URL}{PREMIUM_ONLY_PATH}", timeout=30)
    assert r.status_code in (402, 403), (
        f"{PREMIUM_ONLY_PATH} BASIC -> {r.status_code} body={r.text[:300]}"
    )
    text = r.text.lower()
    assert "subscription" in text or "premium" in text or "plan" in text, (
        f"BASIC premium block should mention subscription/premium: {r.text[:300]}"
    )


# ---------------- Admin user ----------------

@pytest.mark.parametrize("path", BASIC_TIER_PATHS)
def test_admin_user_allowed_everywhere(admin_session, path):
    """Admin (=premium effective) must access all endpoints."""
    r = admin_session.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} ADMIN -> {r.status_code} body={r.text[:300]}"


def test_admin_bypasses_premium_gate(admin_session):
    """Admin must bypass premium subscription gating for the premium-only pattern.

    The endpoint may return 200 or 404 (route not implemented), but must NOT be
    403 subscription_required — that would mean gating incorrectly blocked admin.
    """
    r = admin_session.get(f"{BASE_URL}{PREMIUM_ONLY_PATH}", timeout=30)
    assert r.status_code not in (402, 403), (
        f"Admin should bypass premium gate for {PREMIUM_ONLY_PATH}, got {r.status_code}: {r.text[:300]}"
    )


# ---------------- Session / plan resolution ----------------

def test_access_control_session_free(free_session):
    r = free_session.get(f"{BASE_URL}/api/access-control/session", timeout=30)
    assert r.status_code == 200, r.text[:300]


def test_access_control_session_basic(basic_session):
    r = basic_session.get(f"{BASE_URL}/api/access-control/session", timeout=30)
    assert r.status_code == 200, r.text[:300]


def test_access_control_session_admin(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/access-control/session", timeout=30)
    assert r.status_code == 200, r.text[:300]


def test_subscription_status_endpoint_basic(basic_session):
    r = basic_session.get(f"{BASE_URL}/api/subscriptions/status", timeout=30)
    assert r.status_code == 200, r.text[:300]
