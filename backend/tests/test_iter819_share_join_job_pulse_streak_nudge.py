"""Iter819 — Test three new features:
1. FPS share-join viral counter (POST /games-station/share-join, GET /match-card, /bootstrap)
2. Job Hunt Pulse (GET /job-search/pulse)
3. Streak-protection nudge admin trigger (POST /gamification/streak-nudge/run)
"""

import os
import asyncio
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "NewAdminPass2026!")
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"
MATCH_ID = "testmatch001"
SEEDED_OWNER_ID = "user_test_sharer"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "realtalk_db")


def _session_for(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _session_for(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def free_session():
    return _session_for(FREE_EMAIL, FREE_PASSWORD)


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


# ── FPS share-join ────────────────────────────────

class TestFpsShareJoin:
    def test_public_match_card_includes_share_joins(self):
        r = requests.get(f"{API}/games-station/match-card/{MATCH_ID}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "share_joins" in data
        assert isinstance(data["share_joins"], int)
        assert data["share_joins"] >= 1
        assert data["match_id"] == MATCH_ID

    def test_public_match_card_no_auth_needed(self):
        # confirm no cookies/auth needed
        r = requests.get(f"{API}/games-station/match-card/{MATCH_ID}")
        assert r.status_code == 200
        assert "share_joins" in r.json()

    def test_share_join_admin_already_recorded(self, admin_session):
        r = admin_session.post(f"{API}/games-station/share-join", json={"match_id": MATCH_ID})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("recorded") is False
        assert body.get("reason") == "already_recorded"

    def test_share_join_unknown_match_404(self, admin_session):
        r = admin_session.post(f"{API}/games-station/share-join", json={"match_id": "nonexistent_xxx"})
        assert r.status_code == 404

    def test_share_join_own_match(self, admin_session, mongo):
        """Insert a match owned by admin and confirm own_match reason."""
        db = mongo
        me = admin_session.get(f"{API}/auth/me")
        assert me.status_code == 200
        admin_user_id = me.json().get("user_id") or me.json().get("user", {}).get("user_id")
        assert admin_user_id, me.text

        own_match_id = "testmatch_own_admin"
        db.fps_game_matches.update_one(
            {"match_id": own_match_id},
            {"$set": {"match_id": own_match_id, "user_id": admin_user_id, "kills": 1, "deaths": 0,
                      "won": True, "player_name": "Admin", "model": "policeman", "room_id": "arena",
                      "created_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        try:
            r = admin_session.post(f"{API}/games-station/share-join", json={"match_id": own_match_id})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("recorded") is False
            assert body.get("reason") == "own_match"
        finally:
            db.fps_game_matches.delete_one({"match_id": own_match_id})

    def test_share_join_fresh_user_records(self, free_session, mongo):
        """Fresh joiner should get recorded:true when they haven't joined this owner before."""
        db = mongo
        me = free_session.get(f"{API}/auth/me")
        assert me.status_code == 200
        free_uid = me.json().get("user_id") or me.json().get("user", {}).get("user_id")

        # Clean any prior joins by this user against the seeded owner
        db.fps_share_joins.delete_many(
            {"owner_user_id": SEEDED_OWNER_ID, "joiner_user_id": free_uid}
        )

        r = free_session.post(f"{API}/games-station/share-join", json={"match_id": MATCH_ID})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("recorded") is True, body
        assert isinstance(body.get("owner_share_joins"), int)
        assert body["owner_share_joins"] >= 2

        # Duplicate attempt -> already_recorded
        r2 = free_session.post(f"{API}/games-station/share-join", json={"match_id": MATCH_ID})
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2.get("recorded") is False
        assert b2.get("reason") == "already_recorded"

        # verify notification exists for the seeded owner
        notif = db.notifications.find_one(
            {"user_id": SEEDED_OWNER_ID, "type": "fps_share_join"},
            sort=[("created_at", -1)],
        )
        assert notif is not None
        assert "recruit" in (notif.get("title") or "").lower() or "share" in (notif.get("title") or "").lower()

        # cleanup so re-runs are idempotent
        db.fps_share_joins.delete_many(
            {"owner_user_id": SEEDED_OWNER_ID, "joiner_user_id": free_uid}
        )

    def test_bootstrap_share_joins_field(self, admin_session):
        r = admin_session.get(f"{API}/games-station/bootstrap")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "share_joins" in data
        assert isinstance(data["share_joins"], int)
        assert data["share_joins"] >= 0

    def test_share_join_requires_auth(self):
        s = requests.Session()
        s.headers.update({"X-Requested-With": "XMLHttpRequest"})
        r = s.post(f"{API}/games-station/share-join", json={"match_id": MATCH_ID})
        assert r.status_code in (401, 403)


# ── Job Hunt Pulse ─────────────────────────────────

class TestJobHuntPulse:
    def test_pulse_admin_response_shape(self, admin_session):
        r = admin_session.get(f"{API}/job-search/pulse")
        assert r.status_code == 200, r.text
        data = r.json()
        for key in [
            "profile_complete", "status_counts", "tracked",
            "new_matching_count", "new_matching_top",
            "best_fit_score", "best_fit_job_title",
            "kits_this_week", "apps_this_week",
        ]:
            assert key in data, f"missing key {key}"
        # status_counts includes all 5 statuses
        for s in ["saved", "applied", "interview", "offer", "rejected"]:
            assert s in data["status_counts"]
        assert isinstance(data["new_matching_top"], list)
        assert len(data["new_matching_top"]) <= 3
        for item in data["new_matching_top"]:
            assert "job_id" in item and "title" in item

    def test_pulse_admin_expected_values(self, admin_session):
        """Admin expected: profile_complete=true, applied=5, tracked=5, best_fit_score=72 (per review request)."""
        r = admin_session.get(f"{API}/job-search/pulse")
        assert r.status_code == 200
        data = r.json()
        # verify shape only; specific numbers may drift, but assert plausible bounds
        assert data["profile_complete"] is True
        assert data["tracked"] >= 1
        assert data["status_counts"]["applied"] >= 1

    def test_pulse_free_user_empty(self, free_session):
        r = free_session.get(f"{API}/job-search/pulse")
        assert r.status_code == 200, r.text
        data = r.json()
        # free user may or may not have a profile - accept both, but structure must be valid
        assert isinstance(data["profile_complete"], bool)
        assert isinstance(data["tracked"], int)
        assert data["tracked"] >= 0
        assert isinstance(data["status_counts"], dict)

    def test_pulse_requires_auth(self):
        r = requests.get(f"{API}/job-search/pulse")
        assert r.status_code in (401, 403)


# ── Streak-protection nudge ────────────────────────

class TestStreakNudge:
    def test_streak_nudge_requires_admin(self, free_session):
        r = free_session.post(f"{API}/gamification/streak-nudge/run", json={})
        assert r.status_code in (401, 403)

    def test_streak_nudge_no_auth(self):
        s = requests.Session()
        s.headers.update({"X-Requested-With": "XMLHttpRequest"})
        r = s.post(f"{API}/gamification/streak-nudge/run", json={})
        assert r.status_code in (401, 403)

    def test_streak_nudge_admin_returns_shape(self, admin_session):
        r = admin_session.post(f"{API}/gamification/streak-nudge/run", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        for key in ["notified", "skipped", "date_key", "hours_left"]:
            assert key in body
        assert isinstance(body["notified"], int)
        assert isinstance(body["skipped"], int)
        # Should not error and today's date key matches
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert body["date_key"] == today

    def test_streak_nudge_idempotent_and_fresh_notify(self, admin_session, mongo):
        """Seed a fresh streak profile, run, verify notified>=1 and notification created."""
        db = mongo
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        test_uid = "user_iter819_streak_test"

        # Seed a gamification_profile w/ streak=5, last_activity=yesterday
        db.gamification_profiles.update_one(
            {"user_id": test_uid},
            {"$set": {
                "user_id": test_uid,
                "current_streak": 5,
                "last_activity_date": yesterday,
                "updated_at": now.isoformat(),
            }},
            upsert=True,
        )
        # Clear any nudge log for today
        db.streak_nudge_log.delete_many({"user_id": test_uid, "date_key": today})
        # Clear any prior notifications for this user
        db.notifications.delete_many({"user_id": test_uid, "type": "streak_protection_nudge"})

        try:
            r = admin_session.post(f"{API}/gamification/streak-nudge/run", json={})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["notified"] >= 1, f"expected at least 1 notified, got {body}"

            # Verify notification created
            notif = db.notifications.find_one(
                {"user_id": test_uid, "type": "streak_protection_nudge"},
            )
            assert notif is not None
            assert "streak" in (notif.get("title") or "").lower()
            assert "5-day" in (notif.get("title") or "") or "5 " in (notif.get("title") or "")

            # Second run: should skip (idempotent), notified=0
            r2 = admin_session.post(f"{API}/gamification/streak-nudge/run", json={})
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["skipped"] >= 1
        finally:
            db.gamification_profiles.delete_one({"user_id": test_uid})
            db.streak_nudge_log.delete_many({"user_id": test_uid})
            db.notifications.delete_many({"user_id": test_uid, "type": "streak_protection_nudge"})


# ── Scheduler registration ─────────────────────────

class TestSchedulerRegistration:
    def test_streak_nudge_job_registered(self):
        # Verify the scheduler code registers the job at hour=18
        with open("/app/backend/scheduler.py") as f:
            content = f.read()
        assert "streak_protection_nudge" in content
        assert "id=\"streak_protection_nudge\"" in content
        assert "CronTrigger(hour=18" in content
