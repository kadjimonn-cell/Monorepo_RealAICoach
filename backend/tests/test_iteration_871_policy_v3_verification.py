"""Iteration 871 — Subscription Access Control Policy 2026-06.v3 verification.

Explicit verification of BACKEND 1..6 criteria from the review request:
  1. Free user limited access to previously blocked feature API READS (no 403)
  2. Free session exposes canonical_feature_policy with 37 entries
  3. Daily action meter enforces free quota with correct error contract
  4. Basic almost_unlimited / Premium full_unlimited profile + limits
  5. Security regression (admin surfaces still 403 for free; admin login works)
  6. Self-enforced quotas intact (coaching team GET open; policy marks them -1)
"""

import os
import sys
import time

import pytest
import requests

sys.path.insert(0, "/app/backend")

from utils.access_control_engine import SUBSCRIPTION_ACCESS_POLICY_VERSION  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

FREE = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
BASIC = {"email": "f22.basic.20260613@example.com", "password": "F22Basic#2026Aa"}
PREMIUM = {"email": "f22.premium.20260613@example.com", "password": "F22Premium#2026Aa"}
ADMIN = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}

# BACKEND 1 — endpoints listed in the review request
BACKEND1_READS = [
    "/api/writing-studio/documents",
    "/api/personal-assistant/tasks",
    "/api/research-navigator/projects",
    "/api/money-strategy-hub/overview",
    "/api/travel-planner-pro/trips",
    "/api/relationship-coach/sessions",
    "/api/video-studio/projects",
    "/api/ai-photo-studio/projects",
    "/api/ai-enterprise/dashboard",
    "/api/bill-generator/bills",
    "/api/word-forge/dashboard",
    "/api/audio-studio/v2/bootstrap",
    "/api/podcasts/v2/bootstrap",
    "/api/sports/v2/bootstrap",
    "/api/ai-briefing/today",
    "/api/calendar/status",
    "/api/content/library",
    "/api/integrations/available",
]

ADMIN_BLOCK_ENDPOINTS = [
    "/api/admin/employees",
    "/api/admin/subscription-analytics",
    "/api/reports/x",
    "/api/audio-studio/v2/admin/catalog",
    "/api/sports/v2/admin/conversion-dashboard",
]


def _login(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    if r.status_code == 429:
        pytest.skip(f"Rate limited during login for {creds['email']}")
    assert r.status_code == 200, f"login failed {creds['email']}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE)


@pytest.fixture(scope="module")
def basic_session():
    return _login(BASIC)


@pytest.fixture(scope="module")
def premium_session():
    return _login(PREMIUM)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


# ── BACKEND 1 ────────────────────────────────────────────────────────────

class TestBackend1FreeUserReadAccess:
    """Free user GETs on previously-blocked APIs must NOT return 403."""

    def test_free_user_reads_not_forbidden(self, free_session):
        failures = []
        for ep in BACKEND1_READS:
            r = free_session.get(f"{BASE_URL}{ep}", timeout=30)
            if r.status_code == 403:
                failures.append(f"{ep} -> 403 ({r.text[:120]})")
        assert not failures, "Free user still hard-blocked on:\n" + "\n".join(failures)

    def test_free_user_reads_status_codes_acceptable(self, free_session):
        """Verify accepted codes (200 / 404 / 405) per review contract."""
        summary = {}
        for ep in BACKEND1_READS:
            r = free_session.get(f"{BASE_URL}{ep}", timeout=30)
            summary[ep] = r.status_code
        bad = {k: v for k, v in summary.items() if v not in (200, 201, 204, 404, 405)}
        # 401 sometimes surfaces if cookie session dropped; treat as failure
        assert not bad, f"Unexpected status codes: {bad}"


# ── BACKEND 2 ────────────────────────────────────────────────────────────

class TestBackend2SessionPolicyContract:

    def test_free_session_shape(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("subscription_access_profile") == "limited"
        assert body.get("subscription_policy_version") == "2026-06.v3.free-limited-37"
        assert body.get("subscription_policy_version") == SUBSCRIPTION_ACCESS_POLICY_VERSION
        entitlements = body.get("feature_entitlements") or {}
        policy = entitlements.get("canonical_feature_policy") or {}
        assert len(policy) == 37, f"expected 37 canonical features, got {len(policy)}"
        for key, entry in policy.items():
            assert "daily_action_limit" in entry, f"{key} missing daily_action_limit"
            assert entry.get("read_access") == "unlimited", f"{key} read_access != unlimited"


# ── BACKEND 3 ────────────────────────────────────────────────────────────

class TestBackend3DailyMeter:

    def test_free_user_post_meter_returns_429_with_contract(self):
        # Fresh session to isolate meter usage
        s = _login(FREE)
        codes = []
        last_body = None
        for i in range(8):
            r = s.post(f"{BASE_URL}/api/ai-enterprise/any-probe-path", json={}, timeout=30)
            codes.append(r.status_code)
            if r.status_code == 429:
                try:
                    last_body = r.json()
                except Exception:
                    last_body = None
                break
        assert 429 in codes, f"expected 429 within 8 POSTs, got {codes}"
        assert last_body is not None
        assert last_body.get("error_code") == "feature_daily_limit_reached"
        assert last_body.get("required_plan") == "basic"
        assert last_body.get("upgrade_url") == "/subscription/plans"

    def test_free_user_gets_never_metered(self):
        s = _login(FREE)
        for _ in range(8):
            r = s.get(f"{BASE_URL}/api/ai-briefing/today", timeout=30)
            assert r.status_code == 200, f"GET should never be metered: {r.status_code}"


# ── BACKEND 4 ────────────────────────────────────────────────────────────

class TestBackend4BasicPremiumProfiles:

    def test_basic_profile_and_limits(self, basic_session):
        r = basic_session.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("subscription_access_profile") == "almost_unlimited"
        policy = (body.get("feature_entitlements") or {}).get("canonical_feature_policy") or {}
        assert policy["business-operations-copilot"]["daily_action_limit"] == 200

    def test_premium_profile_and_limits(self, premium_session):
        r = premium_session.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("subscription_access_profile") == "full_unlimited"
        policy = (body.get("feature_entitlements") or {}).get("canonical_feature_policy") or {}
        assert policy["business-operations-copilot"]["daily_action_limit"] == -1


# ── BACKEND 5 ────────────────────────────────────────────────────────────

class TestBackend5SecurityRegression:

    def test_free_still_blocked_on_admin_surfaces(self, free_session):
        failures = []
        for ep in ADMIN_BLOCK_ENDPOINTS:
            r = free_session.get(f"{BASE_URL}{ep}", timeout=30)
            if r.status_code != 403:
                failures.append(f"{ep} -> {r.status_code} (expected 403)")
        assert not failures, "Admin surfaces leaked to free user:\n" + "\n".join(failures)

    def test_admin_login_works_and_admin_can_access_admin_endpoints(self, admin_session):
        # e.g., admin employees endpoint should NOT be 403 for admin
        r = admin_session.get(f"{BASE_URL}/api/admin/employees", timeout=30)
        assert r.status_code != 403, f"admin blocked from /api/admin/employees: {r.status_code}"
        # Session confirms admin
        s = admin_session.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        assert s.status_code == 200
        body = s.json()
        assert body.get("is_admin") is True or body.get("actor_type") == "admin"


# ── BACKEND 6 ────────────────────────────────────────────────────────────

class TestBackend6SelfEnforcedFeatures:

    def test_free_user_coaching_team_get_open(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/ai-coaching-team/coaches", timeout=30)
        assert r.status_code == 200, f"coaching team coaches list should be open: {r.status_code}"

    def test_self_enforced_features_have_neg1_in_canonical_policy(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        assert r.status_code == 200
        policy = (r.json().get("feature_entitlements") or {}).get("canonical_feature_policy") or {}
        for key in ("lexicon-intelligence-hub", "bill-generator", "ai-coaching-team"):
            entry = policy.get(key)
            assert entry is not None, f"{key} missing"
            assert entry.get("self_enforced") is True, f"{key} should be marked self_enforced"
            assert entry.get("daily_action_limit") == -1, f"{key} canonical limit should be -1 (self-enforced), got {entry.get('daily_action_limit')}"
