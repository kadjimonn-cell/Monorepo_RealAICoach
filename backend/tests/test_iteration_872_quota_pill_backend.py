"""Iteration 872 — Backend contract for Floating Feature Quota Pill.

Verifies:
  BACKEND 1 — /api/access-control/feature-meter/{feature_key}
    * Free user on video-creator-studio: 200 + plan/limit/used/remaining/self_enforced/policy_version
    * Premium user: limit=-1, remaining=-1
    * Unknown key: 404
  BACKEND 2 — /api/access-control/session
    * feature_entitlements.canonical_feature_policy has 37 entries
    * Each entry has a non-empty ui_routes array
    * video-creator-studio maps to /features/ai-video
"""

import os
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

from utils.access_control_engine import SUBSCRIPTION_ACCESS_POLICY_VERSION  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
PREMIUM_USER = {"email": "f22.premium.20260613@example.com", "password": "F22Premium#2026Aa"}


def _login(creds: dict) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited during login")
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# BACKEND 1
class TestFeatureMeterEndpoint:
    def test_free_video_creator_studio_shape(self):
        s = _login(FREE_USER)
        r = s.get(f"{BASE_URL}/api/access-control/feature-meter/video-creator-studio", timeout=30)
        assert r.status_code == 200, r.text[:200]
        b = r.json()
        assert b["feature_key"] == "video-creator-studio"
        assert b["plan"] == "free"
        assert b["limit"] == 5
        assert isinstance(b["used"], int) and b["used"] >= 0
        assert b["remaining"] == max(0, b["limit"] - b["used"])
        assert b["self_enforced"] is False
        assert b["policy_version"] == SUBSCRIPTION_ACCESS_POLICY_VERSION
        assert b["policy_version"] == "2026-06.v3.free-limited-37"

    def test_unknown_feature_key_returns_404(self):
        s = _login(FREE_USER)
        r = s.get(f"{BASE_URL}/api/access-control/feature-meter/not-a-real-feature", timeout=30)
        assert r.status_code == 404

    def test_premium_returns_unlimited(self):
        s = _login(PREMIUM_USER)
        r = s.get(f"{BASE_URL}/api/access-control/feature-meter/video-creator-studio", timeout=30)
        assert r.status_code == 200
        b = r.json()
        assert b["limit"] == -1
        assert b["remaining"] == -1
        assert b["plan"] == "premium"


# BACKEND 2
class TestSessionUiRoutes:
    def test_free_session_policy_has_37_entries_with_ui_routes(self):
        s = _login(FREE_USER)
        r = s.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        assert r.status_code == 200
        body = r.json()
        policy = (body.get("feature_entitlements") or {}).get("canonical_feature_policy") or {}
        assert len(policy) == 37, f"expected 37 canonical features, got {len(policy)}"
        missing = []
        for key, entry in policy.items():
            routes = entry.get("ui_routes")
            if not routes or not isinstance(routes, list) or len(routes) == 0:
                missing.append(key)
        assert not missing, f"features missing ui_routes: {missing}"

    def test_video_creator_studio_maps_to_ai_video_route(self):
        s = _login(FREE_USER)
        r = s.get(f"{BASE_URL}/api/access-control/session", timeout=30)
        body = r.json()
        policy = body["feature_entitlements"]["canonical_feature_policy"]
        assert "video-creator-studio" in policy
        routes = policy["video-creator-studio"]["ui_routes"]
        assert "/features/ai-video" in routes, f"expected /features/ai-video in {routes}"
