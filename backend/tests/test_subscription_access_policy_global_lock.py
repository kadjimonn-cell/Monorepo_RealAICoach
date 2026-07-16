"""Global subscription access policy lock tests.

Policy:
Free -> limited access
Basic -> almost unlimited
Premium -> full unlimited
"""

import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

USERS = {
    "free": ("p1.free.1779113329@example.com", "P1Free#2026!Aa"),
    "basic": ("f22.basic.20260613@example.com", "F22Basic#2026Aa"),
    "premium": ("f22.premium.20260613@example.com", "F22Premium#2026Aa"),
    "admin": ("admin@realaicoach.app", "NewAdminPass2026!"),
}


def _session(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


def test_access_control_session_profiles_match_policy():
    expected = {
        "free": "limited",
        "basic": "almost_unlimited",
        "premium": "full_unlimited",
        "admin": "full_unlimited",
    }
    for plan_key, (email, password) in USERS.items():
        s = _session(email, password)
        res = s.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        assert res.status_code == 200, f"session failed {plan_key}: {res.status_code} {res.text}"
        body = res.json()
        assert body.get("subscription_access_profile") == expected[plan_key]
        assert body.get("entitlement_engine") == "ai_driven_entitlements_v2"


def test_basic_plan_gets_almost_unlimited_entitlements_snapshot():
    s = _session(*USERS["basic"])
    res = s.get(f"{BASE_URL}/api/access-control/session", timeout=30)
    assert res.status_code == 200
    body = res.json()
    ent = body.get("feature_entitlements") or {}
    # Non-premium-exclusive numeric limits should be effectively unlimited
    assert ent.get("ai_conversations_daily") == -1
    assert ent.get("coaching_team_daily_messages") == -1
    assert ent.get("word_forge_generate_word_daily") == -1
    # Premium exclusive remains locked for basic
    assert ent.get("export_history") is False
    assert ent.get("dev_advanced_debug") is False


def test_free_plan_remains_limited_entitlements_snapshot():
    s = _session(*USERS["free"])
    res = s.get(f"{BASE_URL}/api/access-control/session", timeout=30)
    assert res.status_code == 200
    body = res.json()
    ent = body.get("feature_entitlements") or {}
    assert body.get("subscription_access_profile") == "limited"
    assert int(ent.get("ai_conversations_daily", 0)) == 3
