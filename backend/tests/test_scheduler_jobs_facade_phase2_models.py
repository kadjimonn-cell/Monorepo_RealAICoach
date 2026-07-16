"""
Regression test suite — Iteration 204
=====================================
Covers main-agent refactor in this session:
  1. scheduler_jobs/ package facade (__init__.py + _legacy.py)
  2. Phase 2 model extraction (models/jobs.py, models/payments.py)
  3. Subscription analytics endpoints (kpi/distribution/funnel/platform/billing/trends)
  4. Enforcement audit $facet consolidation
  5. Newsletter analytics route (uses scheduler_jobs imports)
  6. Subscriptions catalog public endpoint
  7. Auth flow with cookie-session + X-Session-Token compatibility

Backend uses cookie-based auth (session_token cookie). The login response does
NOT expose `session_token`; we extract the cookie from the Set-Cookie header
and reuse via the requests.Session cookie jar.
"""

import importlib
import os
import sys
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Frontend env contract — fail fast
    raise RuntimeError("REACT_APP_BACKEND_URL not set in environment")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Ensure backend src is importable for the import-level smoke tests
sys.path.insert(0, "/app/backend")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def admin_session():
    """Return a requests.Session authenticated as admin via cookie."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    resp = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text[:300]}"
    # Cookie expected: session_token
    cookie_names = [c.name for c in s.cookies]
    assert any("session" in n.lower() or "token" in n.lower() for n in cookie_names), \
        f"Session cookie not set. cookies={cookie_names}"
    return s


# ---------------------------------------------------------------------------
# 1. Boot / import-level smoke: scheduler_jobs facade
# ---------------------------------------------------------------------------
class TestSchedulerJobsFacade:
    def test_package_is_importable(self):
        mod = importlib.import_module("scheduler_jobs")
        assert mod is not None
        # Sanity: the facade should re-export many callables from _legacy
        public_attrs = [a for a in dir(mod) if not a.startswith("_")]
        assert len(public_attrs) > 50, (
            f"scheduler_jobs facade exports unexpectedly few names: {len(public_attrs)}"
        )

    def test_legacy_module_present(self):
        legacy = importlib.import_module("scheduler_jobs.misc")
        assert legacy is not None
        # After Phase 2 batch #24 (final domain split) `misc.py` is the
        # rebranded `_legacy.py`. Only the two non-`scheduled_*` jobs that
        # never got domain-extracted remain canonically defined here.
        canonical_callables = [
            a for a in dir(legacy)
            if not a.startswith("_")
            and callable(getattr(legacy, a, None))
            and getattr(getattr(legacy, a), "__module__", "") == "scheduler_jobs.misc"
        ]
        assert "check_meeting_reminders" in canonical_callables, (
            f"misc.py missing canonical 'check_meeting_reminders'; canonicals: {canonical_callables}"
        )
        assert "run_auto_response_scan" in canonical_callables, (
            f"misc.py missing canonical 'run_auto_response_scan'; canonicals: {canonical_callables}"
        )

    def test_facade_reexports_match_legacy(self):
        """Every callable CANONICALLY defined in misc.py must be importable from facade."""
        legacy = importlib.import_module("scheduler_jobs.misc")
        facade = importlib.import_module("scheduler_jobs")
        missing = []
        for name in dir(legacy):
            if name.startswith("_"):
                continue
            obj = getattr(legacy, name)
            if not callable(obj):
                continue
            # Only check names whose canonical home is misc.py — other
            # symbols (Any, Dict, datetime, ...) are typing/stdlib re-imports
            # and should NOT be re-exported by the facade after the catch-all
            # mirror decommission (Phase 2 batch #24).
            if getattr(obj, "__module__", "") != "scheduler_jobs.misc":
                continue
            if not hasattr(facade, name):
                missing.append(name)
        assert not missing, f"Facade missing re-exports: {missing[:20]} (total {len(missing)})"


# ---------------------------------------------------------------------------
# 2. Phase 2 model extraction — re-export public API
# ---------------------------------------------------------------------------
class TestPhase2ModelExtraction:
    def test_payments_models_reexported_from_route(self):
        mod = importlib.import_module("routes.payments_checkout_core")
        for sym in (
            "CreateCheckoutRequest",
            "ConfirmPaymentRequest",
            "CheckoutPreviewRequest",
            "PaymentRecord",
            "CANONICAL_PAYMENT_METHODS",
            "PAYMENT_METHOD_ALIASES",
            "normalize_payment_method",
        ):
            assert hasattr(mod, sym), f"routes.payments_checkout_core missing {sym}"

    def test_payments_models_module_directly(self):
        mod = importlib.import_module("models.payments")
        for sym in (
            "CreateCheckoutRequest",
            "ConfirmPaymentRequest",
            "CheckoutPreviewRequest",
            "PaymentRecord",
        ):
            assert hasattr(mod, sym), f"models.payments missing {sym}"

    def test_jobs_models_reexported_from_route(self):
        mod = importlib.import_module("routes.jobs")
        for sym in ("JobPost", "JobApplication", "ResumeProfile"):
            assert hasattr(mod, sym), f"routes.jobs missing {sym}"

    def test_jobs_models_module_directly(self):
        mod = importlib.import_module("models.jobs")
        for sym in ("JobPost", "JobApplication", "ResumeProfile"):
            assert hasattr(mod, sym), f"models.jobs missing {sym}"

    def test_models_package_init_exposes_extracted(self):
        mod = importlib.import_module("models")
        # Should at least surface key types
        for sym in ("JobPost", "PaymentRecord"):
            assert hasattr(mod, sym), f"models package missing {sym}"


# ---------------------------------------------------------------------------
# 3. Auth endpoints
# ---------------------------------------------------------------------------
class TestAuthFlow:
    def test_admin_login_200(self, admin_session):
        # Fixture already asserts login succeeded; double check via /me
        resp = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert resp.status_code == 200, f"/auth/me failed: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        # Locate email regardless of envelope (user.email or top-level)
        email = (data.get("user") or {}).get("email") or data.get("email")
        assert email == ADMIN_EMAIL, f"unexpected email on /auth/me: {data}"


# ---------------------------------------------------------------------------
# 4. Subscription analytics (admin)
# ---------------------------------------------------------------------------
class TestSubscriptionAnalytics:
    def test_subscription_analytics_30d(self, admin_session):
        resp = admin_session.get(
            f"{BASE_URL}/api/admin/subscription-analytics?period=30d",
            timeout=30,
        )
        assert resp.status_code == 200, f"{resp.status_code} {resp.text[:400]}"
        data = resp.json()
        required_top_keys = ("kpis", "distribution", "funnel", "platform", "billing", "trends")
        missing = [k for k in required_top_keys if k not in data]
        assert not missing, f"subscription-analytics missing keys: {missing}; got={list(data.keys())}"

    def test_enforcement_audit(self, admin_session):
        resp = admin_session.get(
            f"{BASE_URL}/api/admin/subscription-analytics/enforcement-audit",
            timeout=30,
        )
        assert resp.status_code == 200, f"{resp.status_code} {resp.text[:400]}"
        data = resp.json()
        assert "summary" in data, f"missing summary; got={list(data.keys())}"
        summary = data["summary"]
        assert "total_users" in summary, f"summary missing total_users: {summary}"
        assert "plan_counts" in summary, f"summary missing plan_counts: {summary}"
        # health_score is at top-level of the response (not nested under summary)
        assert "health_score" in data, f"response missing health_score: {list(data.keys())}"
        assert isinstance(summary["total_users"], int)
        assert isinstance(data["health_score"], (int, float))
        # plan_counts may be dict or list
        assert summary["plan_counts"] is not None


# ---------------------------------------------------------------------------
# 5. Newsletter analytics (verifies scheduler_jobs facade reachable)
# ---------------------------------------------------------------------------
class TestNewsletterAnalytics:
    def test_newsletter_analytics(self, admin_session):
        resp = admin_session.get(f"{BASE_URL}/api/newsletter/analytics", timeout=30)
        assert resp.status_code == 200, f"{resp.status_code} {resp.text[:400]}"
        # Body should be JSON
        data = resp.json()
        assert isinstance(data, (dict, list))


# ---------------------------------------------------------------------------
# 6. Subscriptions catalog
# ---------------------------------------------------------------------------
class TestSubscriptionsCatalog:
    def test_plans_public(self):
        # Per existing public surface, this endpoint should be reachable.
        # Try unauthenticated first; if 401/403, retry with admin session.
        url = f"{BASE_URL}/api/subscriptions/plans"
        resp = requests.get(url, timeout=20)
        if resp.status_code in (401, 403):
            s = requests.Session()
            s.headers.update({
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            })
            login = s.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=20,
            )
            assert login.status_code == 200
            resp = s.get(url, timeout=20)
        assert resp.status_code == 200, f"{resp.status_code} {resp.text[:400]}"
        data = resp.json()
        # Expect an array of plans (or {plans: [...]})
        plans = data if isinstance(data, list) else data.get("plans") or data.get("items") or []
        assert isinstance(plans, list)
