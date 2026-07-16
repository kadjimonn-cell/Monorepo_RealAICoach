"""Iter816 FPS viral engagement loop backend verification.

Validates:
- GET /api/home/badges returns total=8 including fps_first_blood & fps_arena_legend
- GET /api/gamification/activity-feed returns FPS badge_earned events
- GET /api/home/activity-feed includes 'FPS Streak Milestone' entry when present
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "NewAdminPass2026!")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return s


class TestHomeBadgesTotalEight:
    def test_badges_total_is_eight_with_fps_ids(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/home/badges", timeout=30)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        assert "badges" in data and isinstance(data["badges"], list)
        assert data.get("total") == 8, f"Expected total=8, got {data.get('total')}"
        assert len(data["badges"]) == 8
        badge_ids = [b["id"] for b in data["badges"]]
        assert "fps_first_blood" in badge_ids
        assert "fps_arena_legend" in badge_ids

    def test_fps_first_blood_earned_for_admin(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/home/badges", timeout=30)
        assert r.status_code == 200
        badges = {b["id"]: b for b in r.json()["badges"]}
        fb = badges["fps_first_blood"]
        assert fb["threshold"] == 1
        assert "progress" in fb and "earned" in fb
        # Admin already scored kills in prior E2E — expect earned=true
        assert fb["earned"] is True, f"Expected admin fps_first_blood earned=True, got {fb}"

    def test_fps_arena_legend_has_progress(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/home/badges", timeout=30)
        badges = {b["id"]: b for b in r.json()["badges"]}
        al = badges["fps_arena_legend"]
        assert al["threshold"] == 5
        assert isinstance(al["progress"], int)
        assert 0 <= al["progress"] <= 5


class TestTodayPulseBadgesTotalBump:
    def test_today_pulse_reports_badges_total_eight(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/home/today-pulse", timeout=30)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        assert data.get("badges_total") == 8, f"Expected badges_total=8, got {data.get('badges_total')}"


class TestGamificationActivityFeed:
    def test_activity_feed_returns_ok(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/gamification/activity-feed", timeout=30)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_feed_contains_fps_badge_earned(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/gamification/activity-feed", timeout=30)
        assert r.status_code == 200
        data = r.json()
        events = data if isinstance(data, list) else data.get("items") or data.get("activities") or data.get("feed") or []
        # Look for at least one badge_earned event referencing an fps_ badge
        fps_badge_labels = {"First Blood", "Double Kill", "Killing Spree", "Rampage", "Unstoppable", "Arena Veteran"}
        fps_badge_events = [
            e for e in events
            if isinstance(e, dict) and (
                e.get("badge_name") in fps_badge_labels or
                "fps_" in str(e.get("badge_id", "")) or
                e.get("badge_name") in fps_badge_labels
            )
        ]
        assert len(fps_badge_events) >= 1, f"No FPS badge_earned events found in feed sample: {str(events)[:1000]}"


class TestHomeActivityFeedFpsStreak:
    def test_home_activity_feed_returns_ok(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/home/activity-feed", timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_home_activity_feed_may_contain_fps_streak_milestone(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/home/activity-feed", timeout=30)
        data = r.json()
        events = data if isinstance(data, list) else data.get("items") or data.get("activities") or data.get("feed") or []
        streak_events = [
            e for e in events
            if isinstance(e, dict) and (
                "FPS Streak" in str(e.get("title", "")) or
                "kill streak" in str(e.get("message", "")).lower() or
                "🏆" in str(e.get("message", ""))
            )
        ]
        assert len(streak_events) >= 1, f"No FPS Streak Milestone entry in feed: {str(events)[:800]}"
        e = streak_events[0]
        assert e.get("category") == "milestones"
        assert e.get("icon") == "trophy"
