"""Platform Subscription Access Control Policy 2026-06.v3 — 37-feature free-limited lock.

Policy:
  Free    -> Limited access to ALL 37 canonical features (daily action meters)
  Basic   -> Almost unlimited
  Premium -> Full unlimited
Auto-enforced via the AI-driven entitlement system (middleware meter).
"""

import os
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

from utils.access_control_engine import (  # noqa: E402
    BASIC_PATTERNS,
    CANONICAL_FEATURE_METERS,
    FEATURE_DEFAULT_DAILY_ACTIONS,
    SUBSCRIPTION_ACCESS_POLICY_VERSION,
    UI_TIER_ROUTES,
    build_canonical_feature_policy,
    get_feature_daily_action_limit,
    get_required_level,
    resolve_feature_meter,
)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
BASIC_USER = {"email": "f22.basic.20260613@example.com", "password": "F22Basic#2026Aa"}
PREMIUM_USER = {"email": "f22.premium.20260613@example.com", "password": "F22Premium#2026Aa"}

# Representative read endpoint per previously hard-blocked feature API surface.
PREVIOUSLY_BLOCKED_READS = [
    "/api/writing-studio/documents",
    "/api/personal-assistant/tasks",
    "/api/research-navigator/projects",
    "/api/decision-coach/decisions",
    "/api/money-strategy-hub/overview",
    "/api/smart-shopping-advisor/wishlists",
    "/api/travel-planner-pro/trips",
    "/api/relationship-coach/sessions",
    "/api/mobility-assistant/vehicles",
    "/api/video-studio/projects",
    "/api/ai-photo-studio/projects",
    "/api/ai-speech-studio/projects",
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


def _session(creds: dict) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited during login")
    assert r.status_code == 200, f"login failed {creds['email']}: {r.status_code} {r.text[:200]}"
    return s


# ── Offline policy contract (locked) ──

def test_policy_covers_all_37_canonical_features():
    numbers = sorted(m["feature_number"] for m in CANONICAL_FEATURE_METERS)
    assert numbers == list(range(1, 38)), f"Meter map must cover features 1..37, got {numbers}"


def test_no_canonical_feature_is_hard_blocked_at_basic():
    assert BASIC_PATTERNS == [], "POLICY v3: no canonical feature may be hard-blocked at Basic"


def test_default_daily_action_quota_matrix():
    assert FEATURE_DEFAULT_DAILY_ACTIONS == {"free": 5, "basic": 200, "premium": -1}


def test_all_canonical_feature_apis_resolve_to_free_level():
    for meter in CANONICAL_FEATURE_METERS:
        for prefix in meter["prefixes"]:
            probe = prefix if prefix.endswith("/") else prefix + "/"
            level = get_required_level(probe + "probe")
            assert level <= 0, f"{meter['feature_key']} ({probe}) requires level {level}, expected free (0) or public"


def test_premium_always_unlimited_and_basic_capped():
    for meter in CANONICAL_FEATURE_METERS:
        assert get_feature_daily_action_limit(meter, "premium") == -1
        basic_limit = get_feature_daily_action_limit(meter, "basic")
        assert basic_limit == -1 or basic_limit >= 100, f"{meter['feature_key']} basic limit too low: {basic_limit}"
        free_limit = get_feature_daily_action_limit(meter, "free")
        if not meter.get("self_enforced"):
            assert free_limit > 0, f"{meter['feature_key']} free limit must be positive, got {free_limit}"


def test_resolve_feature_meter_ordering_daily_meditation_before_travel_visa():
    assert resolve_feature_meter("/api/travel-visa/daily-meditation/checkin")["feature_key"] == "daily-meditation"
    assert resolve_feature_meter("/api/travel-visa/requirements/x")["feature_key"] == "travel-visa"


def test_admin_media_subroutes_stay_gated():
    assert get_required_level("/api/audio-studio/v2/admin/catalog") >= 1
    assert get_required_level("/api/podcasts/v2/admin/catalog") >= 1
    assert get_required_level("/api/sports/v2/admin/catalog") >= 1


def test_ui_tier_routes_open_feature_pages_for_free():
    free_prefixes = UI_TIER_ROUTES["free_feature_prefixes"]
    assert len(free_prefixes) >= 30
    assert UI_TIER_ROUTES["basic_authenticated_ui_prefixes"] == []
    limited = UI_TIER_ROUTES["free_limited_ui_prefixes"]
    for route in ["/features/bill-generator", "/features/ai-enterprise", "/features/ai-automations"]:
        assert route not in limited, f"{route} must not be UI-locked for free users"
    assert "/content-studio" in limited and "/workspace" in limited


def test_canonical_policy_builder_matrix():
    free_policy = build_canonical_feature_policy("free")
    basic_policy = build_canonical_feature_policy("basic")
    premium_policy = build_canonical_feature_policy("premium")
    assert len(free_policy) == len(basic_policy) == len(premium_policy) == 37
    assert free_policy["business-operations-copilot"]["daily_action_limit"] == 5
    assert basic_policy["business-operations-copilot"]["daily_action_limit"] == 200
    assert premium_policy["business-operations-copilot"]["daily_action_limit"] == -1
    for entry in free_policy.values():
        assert entry["read_access"] == "unlimited"


# ── Live enforcement (runtime) ──

def test_free_user_session_exposes_policy():
    s = _session(FREE_USER)
    res = s.get(f"{BASE_URL}/api/access-control/session", timeout=30)
    assert res.status_code == 200
    body = res.json()
    assert body.get("subscription_access_profile") == "limited"
    assert body.get("subscription_policy_version") == SUBSCRIPTION_ACCESS_POLICY_VERSION
    policy = (body.get("feature_entitlements") or {}).get("canonical_feature_policy") or {}
    assert len(policy) == 37


def test_free_user_can_read_all_previously_blocked_feature_apis():
    s = _session(FREE_USER)
    failures = []
    for ep in PREVIOUSLY_BLOCKED_READS:
        r = s.get(f"{BASE_URL}{ep}", timeout=30)
        if r.status_code == 403:
            failures.append(f"{ep} -> 403 ({r.text[:120]})")
    assert not failures, "Free user still hard-blocked:\n" + "\n".join(failures)


def test_basic_and_premium_users_can_read_feature_apis():
    for creds in (BASIC_USER, PREMIUM_USER):
        s = _session(creds)
        for ep in ["/api/bill-generator/bills", "/api/ai-briefing/today", "/api/content/library"]:
            r = s.get(f"{BASE_URL}{ep}", timeout=30)
            assert r.status_code != 403, f"{creds['email']} blocked on {ep}: {r.status_code}"


def test_free_user_daily_meter_returns_429_after_quota():
    s = _session(FREE_USER)
    codes = []
    for _ in range(7):
        r = s.post(f"{BASE_URL}/api/ai-enterprise/meter-probe-test", json={}, timeout=30)
        codes.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in codes, f"Expected 429 after free quota, got {codes}"
    last = s.post(f"{BASE_URL}/api/ai-enterprise/meter-probe-test", json={}, timeout=30)
    assert last.status_code == 429
    body = last.json()
    assert body.get("error_code") == "feature_daily_limit_reached"
    assert body.get("required_plan") == "basic"
    assert body.get("upgrade_url") == "/subscription/plans"


def test_free_user_reads_never_metered():
    s = _session(FREE_USER)
    for _ in range(8):
        r = s.get(f"{BASE_URL}/api/ai-briefing/today", timeout=30)
        assert r.status_code == 200, f"Free reads must stay open, got {r.status_code}"


def test_free_user_still_blocked_from_admin_and_premium_surfaces():
    s = _session(FREE_USER)
    for ep in ["/api/admin/employees", "/api/admin/subscription-analytics", "/api/reports/x", "/api/audio-studio/v2/admin/catalog"]:
        r = s.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 403, f"{ep} must remain blocked for free users, got {r.status_code}"


# ── Quota pill support: feature meter status endpoint + UI route mapping ──

def test_canonical_policy_includes_ui_routes():
    from utils.access_control_engine import CANONICAL_FEATURE_UI_ROUTES
    assert len(CANONICAL_FEATURE_UI_ROUTES) == 37
    policy = build_canonical_feature_policy("free")
    for feature_key, entry in policy.items():
        assert entry.get("ui_routes"), f"{feature_key} missing ui_routes"


def test_feature_meter_status_endpoint_free_user():
    s = _session(FREE_USER)
    r = s.get(f"{BASE_URL}/api/access-control/feature-meter/video-creator-studio", timeout=30)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["feature_key"] == "video-creator-studio"
    assert body["plan"] == "free"
    assert body["limit"] == 5
    assert 0 <= body["used"] <= body["limit"]
    assert body["remaining"] == max(0, body["limit"] - body["used"])
    assert body["policy_version"] == SUBSCRIPTION_ACCESS_POLICY_VERSION


def test_feature_meter_status_endpoint_premium_unlimited():
    s = _session(PREMIUM_USER)
    r = s.get(f"{BASE_URL}/api/access-control/feature-meter/video-creator-studio", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == -1 and body["remaining"] == -1


def test_feature_meter_status_endpoint_unknown_feature_404():
    s = _session(FREE_USER)
    r = s.get(f"{BASE_URL}/api/access-control/feature-meter/not-a-feature", timeout=30)
    assert r.status_code == 404
