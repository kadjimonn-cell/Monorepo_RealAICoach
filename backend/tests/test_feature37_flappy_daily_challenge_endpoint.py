"""Tests for the new GET /api/flappy-bird/daily-challenge home-dashboard endpoint.

Covers:
- Shape/types of the response
- Unauthenticated 401
- Regression on bootstrap + leaderboard endpoints
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")

ADMIN = ("admin@realaicoach.app", "NewAdminPass2026!")
FREE = ("p1.free.1779113329@example.com", "P1Free#2026!Aa")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_client() -> requests.Session:
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def free_client() -> requests.Session:
    return _login(*FREE)


class TestDailyChallengeEndpoint:
    def test_unauthenticated_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/flappy-bird/daily-challenge", timeout=15)
        assert r.status_code == 401

    def test_admin_shape_and_values(self, admin_client: requests.Session):
        r = admin_client.get(f"{BASE_URL}/api/flappy-bird/daily-challenge", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # exact key set
        assert set(data.keys()) == {"target", "completed_today", "streak", "personal_best"}
        # types
        assert isinstance(data["target"], int)
        assert isinstance(data["completed_today"], bool)
        assert isinstance(data["streak"], int)
        assert isinstance(data["personal_best"], int)
        # values per PRD
        assert data["target"] in (5, 10, 15)
        assert data["completed_today"] is True
        assert data["streak"] >= 1
        assert data["personal_best"] == 9999

    def test_free_user_shape(self, free_client: requests.Session):
        r = free_client.get(f"{BASE_URL}/api/flappy-bird/daily-challenge", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) == {"target", "completed_today", "streak", "personal_best"}
        assert data["target"] in (5, 10, 15)
        assert isinstance(data["completed_today"], bool)
        assert data["streak"] >= 0
        assert data["personal_best"] >= 0

    def test_target_matches_bootstrap(self, admin_client: requests.Session):
        # Regression: target from lightweight endpoint should equal bootstrap's daily_challenge.target
        light = admin_client.get(f"{BASE_URL}/api/flappy-bird/daily-challenge", timeout=15).json()
        boot = admin_client.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15).json()
        assert boot["daily_challenge"]["target"] == light["target"]
        assert boot["daily_challenge"]["completed_today"] == light["completed_today"]
        assert boot["daily_challenge"]["streak"] == light["streak"]
        assert boot["personal_best"] == light["personal_best"]


class TestFlappyRegression:
    def test_bootstrap_ok(self, admin_client: requests.Session):
        r = admin_client.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for key in ("feature_id", "title", "personal_best", "games_played",
                    "best_by_difficulty", "leaderboard", "weekly_leaderboard",
                    "my_rank", "my_weekly_rank", "daily_challenge", "xp",
                    "max_score", "difficulties", "week_key"):
            assert key in d, f"missing key {key}"

    def test_leaderboard_ok(self, admin_client: requests.Session):
        r = admin_client.get(f"{BASE_URL}/api/flappy-bird/leaderboard", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["scope"] == "all_time"
        assert isinstance(d["leaderboard"], list)

    def test_leaderboard_weekly(self, admin_client: requests.Session):
        r = admin_client.get(f"{BASE_URL}/api/flappy-bird/leaderboard?scope=weekly", timeout=15)
        assert r.status_code == 200
        assert r.json()["scope"] == "weekly"
