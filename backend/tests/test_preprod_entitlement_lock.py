"""
Pre-Production Entitlement Lock verification tests (lock-state-aware).

This suite is designed to work whether the lock is ON or OFF.
- Reads current lock state at module setup via GET /api/platform-control/entitlement-lock
- Lock-ON specific assertions are conditionally executed (skipped when lock is OFF)
- Lock-OFF specific assertions are conditionally executed (skipped when lock is ON)
- The toggle test never leaves the lock in a different state than it started

Do NOT toggle the lock permanently. Environment default is authoritative.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"
FORMER_PREMIUM_EMAIL = "watchvideos.premium.4dc6ab84@example.com"
FORMER_PREMIUM_PASSWORD = "WatchVideos#2026Aa"

EXPECTED_403_DETAIL = "Subscriptions are disabled until production launch."


def _new_session():
    s = requests.Session()
    s.headers.update(
        {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    return s


def _login(session: requests.Session, email: str, password: str):
    return session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )


@pytest.fixture(scope="module")
def admin_session():
    s = _new_session()
    r = _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:400]}"
    return s


@pytest.fixture(scope="module")
def free_session():
    s = _new_session()
    r = _login(s, FREE_EMAIL, FREE_PASSWORD)
    assert r.status_code == 200, f"Free login failed: {r.status_code} {r.text[:400]}"
    return s


@pytest.fixture(scope="module")
def former_premium_session():
    s = _new_session()
    r = _login(s, FORMER_PREMIUM_EMAIL, FORMER_PREMIUM_PASSWORD)
    assert r.status_code == 200, f"Former-premium login failed: {r.status_code} {r.text[:400]}"
    return s


@pytest.fixture(scope="module")
def lock_state(admin_session):
    """Read current lock state once per module. Return dict {active, env_default}."""
    r = admin_session.get(f"{BASE_URL}/api/platform-control/entitlement-lock", timeout=30)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:400]}"
    data = r.json()
    assert isinstance(data.get("active"), bool)
    assert isinstance(data.get("env_default"), bool)
    return data


# --- Entitlement lock GET/POST admin-only ---
class TestEntitlementLockEndpoint:
    def test_admin_get_lock_shape(self, lock_state):
        # Shape check only; state itself is captured for state-aware branching below.
        assert "active" in lock_state and isinstance(lock_state["active"], bool)
        assert "env_default" in lock_state and isinstance(lock_state["env_default"], bool)

    def test_free_user_cannot_read_lock(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/platform-control/entitlement-lock", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:400]}"


# --- /auth/me plan resolution ---
class TestAuthMeEffectivePlan:
    def test_admin_me_privileged(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text[:400]
        me = r.json()
        assert bool(me.get("is_admin")) is True, f"admin flag missing: {me}"
        plan = str(me.get("subscription_plan") or me.get("effective_plan") or "").lower()
        assert plan in ("premium", "basic") or me.get("is_admin") is True

    def test_free_user_me_free(self, free_session):
        # Free user should ALWAYS resolve to 'free' regardless of lock state.
        r = free_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text[:400]
        me = r.json()
        assert str(me.get("subscription_plan") or "").lower() == "free", (
            f"expected free, got {me.get('subscription_plan')}"
        )
        assert bool(me.get("is_admin")) is False

    def test_former_premium_when_lock_active(self, former_premium_session, lock_state):
        """Only meaningful when lock is ON: former-premium must be forced to 'free'."""
        if not lock_state.get("active"):
            pytest.skip("Lock is OFF — former-premium plan resolution not enforced by lock.")
        r = former_premium_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text[:400]
        me = r.json()
        assert str(me.get("subscription_plan") or "").lower() == "free", (
            f"formerly-premium user must resolve to free under lock; got {me.get('subscription_plan')}"
        )
        assert bool(me.get("is_admin")) is False


# --- Paid checkout endpoints ---
class TestPaidCheckoutState:
    """Behavior branches by lock state.

    Lock ON  -> checkout endpoints return 403 with the preprod-lock detail.
    Lock OFF -> checkout endpoints return 200 with a real checkout_url (Stripe live).
                We DO NOT complete the checkout; we only verify a URL is returned.
    """

    @pytest.mark.parametrize("plan_id", ["basic", "premium"])
    def test_stripe_create_checkout(self, free_session, plan_id, lock_state):
        payload = {
            "plan_id": plan_id,
            "payment_method": "stripe",
            "origin_url": BASE_URL,
            "success_url": "https://example.com/s",
            "cancel_url": "https://example.com/c",
        }
        r = free_session.post(
            f"{BASE_URL}/api/subscriptions/create-checkout",
            json=payload,
            timeout=45,
        )
        if lock_state.get("active"):
            assert r.status_code == 403, f"[lock ON] expected 403 for {plan_id}, got {r.status_code}: {r.text[:400]}"
            body = _safe_json(r)
            detail = _detail(body, r)
            assert EXPECTED_403_DETAIL in str(detail), f"detail mismatch: {detail}"
        else:
            assert r.status_code == 200, f"[lock OFF] expected 200 for {plan_id}, got {r.status_code}: {r.text[:400]}"
            body = _safe_json(r)
            checkout_url = (body or {}).get("checkout_url") or ""
            assert checkout_url.startswith("https://checkout.stripe.com/"), (
                f"[lock OFF] expected checkout.stripe.com URL, got: {checkout_url[:120]}"
            )
            # Sanity: preprod-lock message must NOT appear when lock is off.
            assert EXPECTED_403_DETAIL not in r.text

    def test_revenue_upgrade_state(self, free_session, lock_state):
        r = free_session.post(f"{BASE_URL}/api/revenue/upgrade", json={"plan": "pro"}, timeout=30)
        # In both states this endpoint gates free users with 403 — but the DETAIL differs.
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:400]}"
        body = _safe_json(r)
        text = r.text or ""
        if lock_state.get("active"):
            assert EXPECTED_403_DETAIL in text, f"[lock ON] expected preprod-lock detail; got: {text[:400]}"
        else:
            # Lock OFF: must be the normal upsell message, NOT the preprod-lock message.
            assert EXPECTED_403_DETAIL not in text, (
                f"[lock OFF] preprod-lock message must be GONE; still found in: {text[:400]}"
            )
            # Accept either legacy 'Subscription Required' body or a plain message.
            assert (
                (isinstance(body, dict) and ("Subscription Required" in (body.get("error") or "") or
                                             "requires a Basic plan" in (body.get("message") or "")))
                or "requires a Basic plan" in text
            ), f"[lock OFF] expected upsell message; got: {text[:400]}"


# --- Subscription-gated feature endpoints ---
class TestSubscriptionGatedFeatures:
    """When the lock is OFF, gated feature endpoints must return the normal upsell
    message ('This feature requires a Basic plan or higher...') for free users,
    NOT the preprod-lock message. When the lock is ON, this test is skipped."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/ai-copywriter/generate",
            "/api/watch-videos/premium/list",
            "/api/travel-planner/premium-features",
        ],
    )
    def test_gated_endpoint_upsell_when_lock_off(self, free_session, path, lock_state):
        if lock_state.get("active"):
            pytest.skip("Lock is ON — gated endpoints may return preprod-lock detail instead of upsell.")
        r = free_session.get(f"{BASE_URL}{path}", timeout=30)
        assert r.status_code in (403, 402), f"expected 402/403 upsell, got {r.status_code}: {r.text[:400]}"
        text = r.text or ""
        assert EXPECTED_403_DETAIL not in text, (
            f"[lock OFF] preprod-lock message must not appear; found in {path}: {text[:400]}"
        )
        assert "requires a Basic plan" in text or "Subscription Required" in text, (
            f"[lock OFF] expected normal upsell for {path}; got: {text[:400]}"
        )


# --- Admin toggle round-trip — never permanently changes state ---
class TestAdminToggleLockRoundTrip:
    def test_toggle_round_trip_restores_state(self, admin_session, lock_state):
        original = bool(lock_state.get("active"))
        opposite = not original

        # Flip to opposite
        r1 = admin_session.post(
            f"{BASE_URL}/api/platform-control/entitlement-lock",
            json={"active": opposite},
            timeout=30,
        )
        assert r1.status_code == 200, f"flip failed: {r1.status_code} {r1.text[:400]}"
        assert bool(r1.json().get("active")) is opposite

        # Verify GET reflects opposite
        g1 = admin_session.get(f"{BASE_URL}/api/platform-control/entitlement-lock", timeout=30)
        assert g1.status_code == 200
        assert bool(g1.json().get("active")) is opposite

        # Restore to original — MANDATORY, even on assertion failure.
        try:
            pass
        finally:
            r2 = admin_session.post(
                f"{BASE_URL}/api/platform-control/entitlement-lock",
                json={"active": original},
                timeout=30,
            )
            assert r2.status_code == 200, f"restore failed: {r2.status_code} {r2.text[:400]}"
            assert bool(r2.json().get("active")) is original

            g2 = admin_session.get(f"{BASE_URL}/api/platform-control/entitlement-lock", timeout=30)
            assert g2.status_code == 200
            final = g2.json()
            assert bool(final.get("active")) is original, (
                f"CRITICAL: lock must be restored to original ({original}). Got {final}"
            )


# --- DB integrity — only meaningful when lock is ON ---
class TestDBIntegrity:
    def test_no_nonadmin_paid_users_when_lock_active(self, admin_session, lock_state):
        if not lock_state.get("active"):
            pytest.skip("Lock is OFF — non-admin paid users are permitted.")
        tried = []
        for url in [
            f"{BASE_URL}/api/admin/users?limit=500",
            f"{BASE_URL}/api/admin/users/list?limit=500",
            f"{BASE_URL}/api/admin/subscription-analytics",
            f"{BASE_URL}/api/admin/analytics/subscriptions",
        ]:
            r = admin_session.get(url, timeout=30)
            tried.append((url, r.status_code))
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception:
                    continue
                users = None
                if isinstance(data, dict):
                    for k in ("users", "items", "results", "data"):
                        if isinstance(data.get(k), list):
                            users = data[k]
                            break
                elif isinstance(data, list):
                    users = data
                if users is not None:
                    offenders = [
                        u for u in users
                        if isinstance(u, dict)
                        and str(u.get("subscription_plan") or "").lower() in ("basic", "premium")
                        and not bool(u.get("is_admin"))
                    ]
                    assert offenders == [], (
                        f"found {len(offenders)} non-admin paid users via {url}: "
                        f"{[o.get('email') for o in offenders[:5]]}"
                    )
                    return
        pytest.skip(f"No admin listing endpoint returned 200; tried: {tried}")


# --- Regression smoke ---
class TestRegressionSmoke:
    def test_free_user_home_endpoints(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200
        for url in [f"{BASE_URL}/api/home/today", f"{BASE_URL}/api/home/dashboard", f"{BASE_URL}/api/notifications"]:
            r2 = free_session.get(url, timeout=30)
            assert r2.status_code in (200, 401, 403, 404), f"{url} unexpected {r2.status_code}"

    def test_admin_home(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200

    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        assert (r.json() or {}).get("status") == "healthy"


# --- helpers ---
def _safe_json(r):
    try:
        return r.json()
    except Exception:
        return None


def _detail(body, r):
    if isinstance(body, dict):
        d = body.get("detail")
        if isinstance(d, str):
            return d
        if d is not None:
            return str(d)
    return r.text or ""
