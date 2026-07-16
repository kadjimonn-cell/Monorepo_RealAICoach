"""Iteration 801 regression: /api/home/activity-feed safety, dedupe, localization.

Backend contract for the rebuilt Home 'Activity Pulse' section:
  * Every returned item must belong to the allowlisted safe types.
  * No item title/message may leak internal-ops / admin phrases.
  * No type may appear more than 2 times (dedupe cap).
  * Items must expose enriched fields {type,title,message,time,category,icon,route}.
  * lang=fr must localize known default titles (e.g., 'Session IA Terminée').

Auth uses the cookie-jar flow (session cookie is required by the middleware —
Bearer token flow is NOT sufficient for /api/home/activity-feed).
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required")

EMAIL = "p1.free.1779113329@example.com"
PASSWORD = "P1Free#2026!Aa"

SAFE_TYPES = {
    "badge_earned", "achievement", "goal_milestone", "insight",
    "learning_hub_update", "language_guidance",
    "ai", "coaching", "session_completed", "agenda_reminder",
    "welcome", "feature_release", "drip_day1",
    # 'system' is also served as a default filler for platform updates.
    "system",
}

BANNED_PHRASES = [
    "integrity engine",
    "growth integrity",
    "journey regression",
    "admin alert",
    "webhook",
    "guardrail",
    "autofix",
]


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def authed_session():
    """Login with cookie jar so downstream calls carry the session cookie."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"auth/login failed with {r.status_code}: {r.text[:200]}")
    # Attach Bearer as belt-and-suspenders; middleware primarily reads cookie.
    token = None
    try:
        data = r.json()
        token = (
            data.get("access_token")
            or data.get("token")
            or (data.get("data") or {}).get("access_token")
        )
    except Exception:
        pass
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ── Activity feed contract ─────────────────────────────────────────────────────

class TestActivityFeedSafety:
    """Security allowlist + dedupe cap + shape assertions for the pulse feed."""

    def test_activity_feed_returns_200_and_feed_list(self, authed_session):
        r = authed_session.get(f"{BASE_URL}/api/home/activity-feed", timeout=30)
        assert r.status_code == 200, f"unexpected status={r.status_code} body={r.text[:300]}"
        payload = r.json()
        assert "feed" in payload, f"missing 'feed' key: {payload}"
        assert isinstance(payload["feed"], list), "feed must be a list"
        assert len(payload["feed"]) > 0, "feed must not be empty (defaults should fill in)"

    def test_activity_feed_all_types_in_safe_allowlist(self, authed_session):
        r = authed_session.get(f"{BASE_URL}/api/home/activity-feed", timeout=30)
        assert r.status_code == 200
        for item in r.json().get("feed", []):
            assert item.get("type") in SAFE_TYPES, (
                f"UNSAFE type leaked into activity feed: {item.get('type')} · item={item}"
            )

    def test_activity_feed_no_internal_ops_phrases(self, authed_session):
        r = authed_session.get(f"{BASE_URL}/api/home/activity-feed", timeout=30)
        assert r.status_code == 200
        for item in r.json().get("feed", []):
            haystack = f"{item.get('title','')} {item.get('message','')}".lower()
            for phrase in BANNED_PHRASES:
                assert phrase not in haystack, (
                    f"BANNED phrase '{phrase}' leaked into activity feed item: {item}"
                )

    def test_activity_feed_dedupe_cap_two_per_type(self, authed_session):
        r = authed_session.get(f"{BASE_URL}/api/home/activity-feed", timeout=30)
        assert r.status_code == 200
        counts = {}
        for item in r.json().get("feed", []):
            t = item.get("type")
            counts[t] = counts.get(t, 0) + 1
        for t, c in counts.items():
            assert c <= 2, f"dedupe cap violated for type='{t}' count={c} counts={counts}"

    def test_activity_feed_items_have_enriched_fields(self, authed_session):
        r = authed_session.get(f"{BASE_URL}/api/home/activity-feed", timeout=30)
        assert r.status_code == 200
        required = {"type", "title", "message", "time", "category", "icon", "route"}
        for item in r.json().get("feed", []):
            missing = required - set(item.keys())
            assert not missing, f"item missing required fields {missing}: {item}"
            # time should be an ISO 8601-ish string
            assert isinstance(item["time"], str) and len(item["time"]) >= 10, (
                f"invalid time: {item['time']}"
            )
            # route should start with a slash so tap-to-navigate works
            assert str(item["route"]).startswith("/"), f"bad route: {item['route']}"


# ── Localization (fr) ──────────────────────────────────────────────────────────

class TestActivityFeedLocalization:
    """Ensures default localized strings surface when ?lang=fr is requested."""

    def test_activity_feed_fr_localizes_known_defaults(self, authed_session):
        r = authed_session.get(
            f"{BASE_URL}/api/home/activity-feed",
            params={"lang": "fr"},
            timeout=30,
        )
        assert r.status_code == 200
        titles = [str(x.get("title", "")) for x in r.json().get("feed", [])]
        joined = " | ".join(titles)
        # At least one of the known localized default titles must appear.
        expected_any = [
            "Session IA Terminée",
            "Jalon d'Objectif",
            "Mise à Jour Plateforme",
            "Coach Disponible",
            "Insight Hebdomadaire",
        ]
        assert any(exp in joined for exp in expected_any), (
            f"no French localized default titles found. titles={titles}"
        )


# ── Unauthenticated behavior sanity ────────────────────────────────────────────

class TestActivityFeedUnauthenticated:
    def test_activity_feed_without_auth_still_safe(self):
        """Even if endpoint is reachable unauthenticated, no unsafe leak."""
        r = requests.get(f"{BASE_URL}/api/home/activity-feed", timeout=30)
        # Should be either 200 (defaults) or 401 (locked). Both are acceptable —
        # what MUST hold is no banned phrase leaks when it does return data.
        assert r.status_code in (200, 401), f"unexpected status={r.status_code}"
        if r.status_code == 200:
            for item in r.json().get("feed", []):
                assert item.get("type") in SAFE_TYPES
                blob = f"{item.get('title','')} {item.get('message','')}".lower()
                for phrase in BANNED_PHRASES:
                    assert phrase not in blob, f"unauth feed leaked '{phrase}': {item}"
