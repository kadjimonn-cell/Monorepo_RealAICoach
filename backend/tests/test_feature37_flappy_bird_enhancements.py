"""Feature 37 - Flappy Bird Game ENHANCEMENTS tests (iteration 838).

Validates the new gameplay/platform/social flows added by main agent:
- Medal system (bronze @>=10, silver @>=25, gold @>=50, diamond @>=100, none <10)
- XP: per-run cap (30), daily cap (100), daily challenge bonus (+20)
- Daily challenge: deterministic 5/10/15 target rotation, completion + streak
- Weekly leaderboard scope + my_weekly_rank
- Difficulty acceptance (easy/classic/hard) + invalid falls back to classic
- Bootstrap shape covers difficulties, xp, daily_challenge, weekly_leaderboard
"""

from __future__ import annotations

import os
from datetime import date

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://coach-web-preview.preview.emergentagent.com",
).rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text[:200]}")
    csrf = s.cookies.get("csrf_token")
    if csrf:
        s.headers.update({"X-CSRF-Token": csrf})
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE_EMAIL, FREE_PASSWORD)


def _expected_daily_target() -> int:
    ordinal = date.today().toordinal()
    return 5 + (ordinal % 3) * 5  # 5, 10, or 15


# ---------- Bootstrap shape (extended) ----------
class TestBootstrapExtendedShape:
    def test_bootstrap_returns_new_fields(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r.status_code == 200, r.text[:200]
        data = r.json()

        # Existing baseline
        assert data["feature_id"] == "flappy-bird"
        assert data["max_score"] == 9999

        # New fields
        assert data.get("difficulties") == ["easy", "classic", "hard"]

        best_by_difficulty = data.get("best_by_difficulty")
        assert isinstance(best_by_difficulty, dict)
        for diff in ("easy", "classic", "hard"):
            assert diff in best_by_difficulty
            assert isinstance(best_by_difficulty[diff], int)

        # daily_challenge
        dc = data.get("daily_challenge")
        assert isinstance(dc, dict)
        assert dc.get("target") == _expected_daily_target()
        assert isinstance(dc.get("completed_today"), bool)
        assert isinstance(dc.get("streak"), int) and dc["streak"] >= 0

        # xp
        xp = data.get("xp")
        assert isinstance(xp, dict)
        assert xp.get("daily_cap") == 100
        assert xp.get("per_run_cap") == 30
        assert isinstance(xp.get("earned_today"), int) and xp["earned_today"] >= 0

        # weekly leaderboard + rank
        assert isinstance(data.get("weekly_leaderboard"), list)
        assert isinstance(data.get("my_weekly_rank"), dict)
        assert "rank" in data["my_weekly_rank"]
        assert "week_key" in data


# ---------- Medal system ----------
class TestMedals:
    @pytest.mark.parametrize("score,expected", [
        (0, "none"),
        (9, "none"),
        (10, "bronze"),
        (24, "bronze"),
        (25, "silver"),
        (49, "silver"),
        (50, "gold"),
        (99, "gold"),
        (100, "diamond"),
        (500, "diamond"),
    ])
    def test_medal_for_score(self, admin_session, score, expected):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": score, "duration_ms": 200, "difficulty": "classic"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("medal") == expected, f"score={score}: {r.json()}"


# ---------- Difficulty handling ----------
class TestDifficulty:
    def test_hard_difficulty_accepted_and_returned(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 3, "duration_ms": 200, "difficulty": "hard"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("difficulty") == "hard"

    def test_easy_difficulty_accepted_and_returned(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 3, "duration_ms": 200, "difficulty": "easy"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("difficulty") == "easy"

    def test_invalid_difficulty_falls_back_to_classic(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 2, "duration_ms": 200, "difficulty": "extreme"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("difficulty") == "classic"

    def test_best_by_difficulty_updates_independently(self, admin_session):
        # Submit an easy score high enough to bump easy-best
        r0 = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        prev_easy = int(r0.json()["best_by_difficulty"]["easy"])
        target = min(9999, max(prev_easy + 5, 20))
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": target, "duration_ms": 400, "difficulty": "easy"},
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["best_by_difficulty"]["easy"] >= target


# ---------- XP caps ----------
class TestXpCaps:
    def test_xp_capped_per_run_at_30(self, free_session):
        # Fetch xp_today for free user
        r0 = free_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r0.status_code == 200
        xp_today = int(r0.json()["xp"]["earned_today"])
        # Submit a score >30
        r = free_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 55, "duration_ms": 500, "difficulty": "classic"},
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        # xp_awarded is min(score, 30) + daily_challenge_bonus(20 if completed_now) capped by daily cap remaining
        base_award = min(55, 30, max(0, 100 - xp_today))
        # Plus optional +20 if this run completed the challenge for the first time today
        assert d["xp_awarded"] <= base_award + 20
        assert d["xp_awarded"] <= 30 + 20  # absolute ceiling per single run

    def test_xp_respects_daily_cap_100(self, admin_session):
        # Rapidly submit multiple 30-XP-eligible scores; total xp_earned_today must never exceed 100
        for _ in range(6):
            r = admin_session.post(
                f"{BASE_URL}/api/flappy-bird/score",
                json={"score": 35, "duration_ms": 300, "difficulty": "classic"},
                timeout=15,
            )
            assert r.status_code == 200
        r_boot = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r_boot.status_code == 200
        earned = int(r_boot.json()["xp"]["earned_today"])
        assert earned <= 100, f"XP daily cap exceeded: earned_today={earned}"


# ---------- Daily challenge ----------
class TestDailyChallenge:
    def test_target_is_5_10_or_15(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r.status_code == 200
        target = r.json()["daily_challenge"]["target"]
        assert target in (5, 10, 15)
        assert target == _expected_daily_target()

    def test_completed_today_reflected(self, admin_session):
        # By the time other tests have run submitting scores, admin's daily challenge
        # should be marked completed_today=True (target<=15 easily hit).
        r = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r.status_code == 200
        dc = r.json()["daily_challenge"]
        # target likely completed by earlier medal/xp tests. If not, submit >=target once.
        if not dc["completed_today"]:
            admin_session.post(
                f"{BASE_URL}/api/flappy-bird/score",
                json={"score": max(dc["target"], 15), "duration_ms": 500, "difficulty": "classic"},
                timeout=15,
            )
            r2 = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
            dc = r2.json()["daily_challenge"]
        assert dc["completed_today"] is True
        assert dc["streak"] >= 1


# ---------- Weekly leaderboard ----------
class TestWeeklyLeaderboard:
    def test_weekly_scope_returns_current_week_only(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/flappy-bird/leaderboard?scope=weekly",
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("scope") == "weekly"
        assert isinstance(data.get("leaderboard"), list)

    def test_alltime_scope_default(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/flappy-bird/leaderboard?scope=all_time",
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("scope") == "all_time"

    def test_invalid_scope_falls_back(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/flappy-bird/leaderboard?scope=lifetime",
            timeout=15,
        )
        assert r.status_code == 200
        # Router coerces unknown scopes to all_time
        assert r.json().get("scope") == "all_time"

    def test_score_response_includes_weekly_leaderboard_and_rank(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 8, "duration_ms": 200, "difficulty": "classic"},
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("weekly_leaderboard"), list)
        assert isinstance(d.get("my_weekly_rank"), dict)
        assert "rank" in d["my_weekly_rank"]


# ---------- Score response shape (all new keys) ----------
class TestScoreResponseShape:
    def test_score_response_contains_all_new_keys(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 12, "duration_ms": 400, "difficulty": "classic"},
            timeout=15,
        )
        assert r.status_code == 200
        d = r.json()
        required = {
            "accepted", "score", "difficulty", "medal",
            "is_new_best", "is_new_difficulty_best",
            "xp_awarded", "daily_challenge_completed_now",
            "personal_best", "games_played", "best_by_difficulty",
            "leaderboard", "weekly_leaderboard",
            "my_rank", "my_weekly_rank",
            "daily_challenge", "xp",
        }
        missing = required - set(d.keys())
        assert not missing, f"score response missing keys: {missing}"
        # Medal correctness for 12
        assert d["medal"] == "bronze"
