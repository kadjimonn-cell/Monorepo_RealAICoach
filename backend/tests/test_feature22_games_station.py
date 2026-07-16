"""Feature 22 — FPS Game backend contract tests.

Validates the FPS Game replacement of Games Station:
- Bootstrap contract (feature_id stays canonical 'games-station', title 'FPS Game')
- Plan/quota snapshot shape
- Rooms join-or-create flow (repo login-panel behaviour)
- Leaderboard + profile + match history endpoints
Run: python -m pytest /app/backend/tests/test_feature22_fps_game.py -v
"""

import os

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_CREDS = {"email": "admin@realaicoach.app", "password": os.environ.get("TEST_ADMIN_PASSWORD", "")}


def _load_admin_password() -> str:
    if ADMIN_CREDS["password"]:
        return ADMIN_CREDS["password"]
    try:
        content = open("/app/memory/test_credentials.md").read()
        for i, line in enumerate(content.splitlines()):
            if "admin@realaicoach.app" in line:
                # inline `email / password` or `email password` style
                tail = line.split("admin@realaicoach.app", 1)[1]
                tokens = [p.strip("`*") for p in tail.replace("|", " ").replace("/", " ").split() if p.strip("`*")]
                if tokens:
                    return tokens[0]
                # `- Email: ...` followed by `- Password: ...` style
                for nxt in content.splitlines()[i + 1:i + 3]:
                    if "password" in nxt.lower() and ":" in nxt:
                        return nxt.split(":", 1)[1].strip().strip("`*")
    except Exception:
        pass
    return ""


@pytest.fixture(scope="module")
def auth_headers():
    password = _load_admin_password()
    assert password, "Admin password not found in env or /app/memory/test_credentials.md"
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_CREDS["email"], "password": password}, timeout=30)
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text[:200]}"
    data = resp.json()
    token = (
        data.get("session_token")
        or data.get("token")
        or data.get("access_token")
        or resp.cookies.get("session_token")
    )
    assert token, "No token in login response"
    return {"Authorization": f"Bearer {token}"}


class TestFpsBootstrapContract:
    def test_bootstrap_returns_canonical_feature_id_and_fps_title(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/games-station/bootstrap", headers=auth_headers, timeout=30)
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()
        assert data["feature_id"] == "games-station"
        assert data["title"] == "FPS Game"

    def test_bootstrap_has_plan_and_quota(self, auth_headers):
        data = requests.get(f"{BASE_URL}/api/games-station/bootstrap", headers=auth_headers, timeout=30).json()
        assert "plan" in data
        assert "quota" in data
        quota = data["quota"]
        for key in ("daily_gameplay_limit", "daily_plays_used", "daily_plays_remaining", "leaderboard_visibility"):
            assert key in quota, f"quota missing {key}"

    def test_bootstrap_exposes_repo_player_models(self, auth_headers):
        data = requests.get(f"{BASE_URL}/api/games-station/bootstrap", headers=auth_headers, timeout=30).json()
        assert sorted(data["player_models"]) == ["policeman", "robotx", "roboty"]
        assert data["max_hp"] == 100
        assert data["hit_damage"] == 10
        assert data["max_players_per_room"] == 8

    def test_bootstrap_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/api/games-station/bootstrap", timeout=30)
        assert resp.status_code in (401, 403)


class TestFpsRoomsFlow:
    def test_join_or_create_room(self, auth_headers):
        resp = requests.post(
            f"{BASE_URL}/api/games-station/rooms/join",
            headers=auth_headers,
            json={"room_name": "pytest-arena", "player_name": "PyTester", "model": "robotx"},
            timeout=30,
        )
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()
        assert data["room_id"] == "pytest-arena"
        assert data["ws_path"].startswith("/api/ws/fps/pytest-arena/")
        assert data["model"] == "robotx"
        assert data["player_name"] == "PyTester"

    def test_join_room_rejects_empty_name(self, auth_headers):
        resp = requests.post(
            f"{BASE_URL}/api/games-station/rooms/join",
            headers=auth_headers,
            json={"room_name": "***", "player_name": "PyTester", "model": "policeman"},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_invalid_model_falls_back_to_policeman(self, auth_headers):
        resp = requests.post(
            f"{BASE_URL}/api/games-station/rooms/join",
            headers=auth_headers,
            json={"room_name": "pytest-arena-2", "player_name": "PyTester", "model": "not-a-model"},
            timeout=30,
        )
        assert resp.status_code == 200
        assert resp.json()["model"] == "policeman"

    def test_rooms_listing(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/games-station/rooms", headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        assert "rooms" in resp.json()


class TestFpsStatsEndpoints:
    def test_leaderboard(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/games-station/leaderboard", headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        assert isinstance(resp.json()["leaderboard"], list)

    def test_profile(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/games-station/profile", headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        profile = resp.json()["profile"]
        for key in ("user_id", "kills", "deaths", "matches_played", "preferred_model"):
            assert key in profile

    def test_match_history(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/games-station/match-history", headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        assert isinstance(resp.json()["matches"], list)


class TestFeatureRegistryMigration:
    def test_registry_reports_fps_game_title(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/features/registry", headers=auth_headers, timeout=30)
        if resp.status_code != 200:
            pytest.skip("registry endpoint unavailable")
        rows = resp.json() if isinstance(resp.json(), list) else resp.json().get("features", [])
        entry = next((f for f in rows if f.get("feature_id") == "games-station"), None)
        if entry is None:
            pytest.skip("games-station entry not exposed by this endpoint")
        assert entry.get("title") == "FPS Game"
        assert entry.get("route") == "/features/fps-game"
