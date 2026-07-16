"""Feature 37 - Flappy Bird Streak Saver Email Tests (iteration 840).

Validates:
- Template catalog registration for flappy_streak_saver_v7
- Builder output (subject, HTML CTA link, streak/target values)
- Candidate selection (find_at_risk_users): yesterday-complete + today-missing users
- Streak math (_streak_for): consecutive-day walk-back, gap handling
- Send + per-user-per-day dedupe via flappy_streak_saver_log
- Admin endpoint 401/403 guardrails
- Admin endpoint success shape {at_risk_count, emails_sent, day_key}
- Scheduler registration (source-code verification)

Uses asyncio.run() + a fresh Motor client per test to avoid pytest-asyncio
event-loop cross-contamination with the module-level Motor client in routes.db.
Synthetic docs are tagged with SYNTHETIC_TAG and cleaned in each test.
"""

import os
import sys
import re
import uuid
import asyncio
import pytest
import requests
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

BACKEND_DIR = "/app/backend"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

LOCAL_URL = "http://localhost:8001"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

SYNTHETIC_TAG = "synthetic_test_iter840"


def _day_key_offset(offset: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=offset)).isoformat()


def _run(coro_factory):
    """Run an async scenario with a fresh Motor client bound to a fresh loop.
    coro_factory: async fn taking (db) and returning result."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import routes.db as db_module

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=loop)
        fresh_db = client[os.environ["DB_NAME"]]
        original_db = db_module.db
        db_module.db = fresh_db

        # Also patch any module that has already bound `db` at import time
        patched_modules = []
        for mod_name in ("services.flappy_streak_saver", "routes.flappy_bird"):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, "db"):
                patched_modules.append((mod, mod.db))
                mod.db = fresh_db

        try:
            return loop.run_until_complete(coro_factory(fresh_db))
        finally:
            db_module.db = original_db
            for mod, orig in patched_modules:
                mod.db = orig
            client.close()
    finally:
        loop.close()
        asyncio.set_event_loop(None)


async def _register_user(db, user_id, email):
    await db.users.insert_one({
        "user_id": user_id,
        "email": email,
        "name": f"Synth {user_id[:6]}",
        SYNTHETIC_TAG: True,
    })


async def _add_daily(db, user_id, day_key, score=15, target=10):
    await db.flappy_bird_daily.insert_one({
        "user_id": user_id,
        "day_key": day_key,
        "score": score,
        "target": target,
        "created_at": datetime.now(timezone.utc).isoformat(),
        SYNTHETIC_TAG: True,
    })


async def _cleanup(db):
    await db.users.delete_many({SYNTHETIC_TAG: True})
    await db.flappy_bird_daily.delete_many({SYNTHETIC_TAG: True})
    await db.flappy_streak_saver_log.delete_many({SYNTHETIC_TAG: True})


# ── Template Catalog ─────────────────────────────────────

class TestTemplateRegistration:
    def test_template_key_registered(self):
        from utils.email_templates import TEMPLATE_CATALOG
        assert "flappy_streak_saver_v7" in TEMPLATE_CATALOG
        entry = TEMPLATE_CATALOG["flappy_streak_saver_v7"]
        assert entry["category"] == "Engagement"
        assert callable(entry["builder"])

    def test_builder_output_contains_streak_target_and_cta(self):
        from utils.email_templates import TEMPLATE_CATALOG
        builder = TEMPLATE_CATALOG["flappy_streak_saver_v7"]["builder"]
        tpl = builder(user_name="Alex", streak=3, target=12, personal_best=25)
        assert "3-day" in tpl.subject
        assert "expires at midnight" in tpl.subject.lower()
        assert "/features/flappy-bird" in tpl.html
        assert "3" in tpl.html
        assert "12" in tpl.html
        assert "25" in tpl.html

    def test_builder_singular_day_label(self):
        from utils.email_templates import TEMPLATE_CATALOG
        builder = TEMPLATE_CATALOG["flappy_streak_saver_v7"]["builder"]
        tpl = builder(user_name="Sam", streak=1, target=10, personal_best=0)
        assert "1-day" in tpl.subject


# ── Scheduler Registration ───────────────────────────────

class TestSchedulerRegistration:
    def test_scheduler_source_contains_streak_saver_cron(self):
        with open("/app/backend/scheduler.py", "r") as fh:
            src = fh.read()
        assert "flappy_streak_saver" in src
        pat = re.compile(
            r"scheduler\.add_job\(\s*scheduled_flappy_streak_saver\s*,\s*"
            r"CronTrigger\(hour=17,\s*minute=0\)\s*,\s*id=\"flappy_streak_saver\"",
            re.DOTALL,
        )
        assert pat.search(src), "Cron hour=17 id=flappy_streak_saver not found in scheduler.py"


# ── Candidate Selection ──────────────────────────────────

class TestCandidateSelection:
    def test_yesterday_only_user_is_at_risk(self):
        uid = f"synth_atrisk_{uuid.uuid4().hex[:8]}"

        async def scenario(db):
            from services.flappy_streak_saver import find_at_risk_users
            try:
                await _register_user(db, uid, f"{uid}@example.com")
                await _add_daily(db, uid, _day_key_offset(1))
                at_risk = await find_at_risk_users()
                return any(c["user_id"] == uid for c in at_risk), len(at_risk)
            finally:
                await _cleanup(db)

        found, total = _run(scenario)
        assert found, f"Expected {uid} in at_risk list (total {total})"

    def test_user_done_today_excluded(self):
        uid = f"synth_done_{uuid.uuid4().hex[:8]}"

        async def scenario(db):
            from services.flappy_streak_saver import find_at_risk_users
            try:
                await _register_user(db, uid, f"{uid}@example.com")
                await _add_daily(db, uid, _day_key_offset(1))
                await _add_daily(db, uid, _day_key_offset(0))
                at_risk = await find_at_risk_users()
                return any(c["user_id"] == uid for c in at_risk)
            finally:
                await _cleanup(db)

        assert _run(scenario) is False

    def test_user_without_yesterday_excluded(self):
        uid = f"synth_noy_{uuid.uuid4().hex[:8]}"

        async def scenario(db):
            from services.flappy_streak_saver import find_at_risk_users
            try:
                await _register_user(db, uid, f"{uid}@example.com")
                await _add_daily(db, uid, _day_key_offset(3))
                at_risk = await find_at_risk_users()
                return any(c["user_id"] == uid for c in at_risk)
            finally:
                await _cleanup(db)

        assert _run(scenario) is False


# ── Streak Math ──────────────────────────────────────────

class TestStreakMath:
    def test_streak_walks_back_consecutive_days(self):
        uid = f"synth_s3_{uuid.uuid4().hex[:8]}"

        async def scenario(db):
            from services.flappy_streak_saver import _streak_for
            try:
                await _register_user(db, uid, f"{uid}@example.com")
                for off in (1, 2, 3):
                    await _add_daily(db, uid, _day_key_offset(off))
                return await _streak_for(uid)
            finally:
                await _cleanup(db)

        assert _run(scenario) == 3

    def test_streak_stops_at_gap(self):
        uid = f"synth_gap_{uuid.uuid4().hex[:8]}"

        async def scenario(db):
            from services.flappy_streak_saver import _streak_for
            try:
                await _register_user(db, uid, f"{uid}@example.com")
                await _add_daily(db, uid, _day_key_offset(1))
                await _add_daily(db, uid, _day_key_offset(3))
                return await _streak_for(uid)
            finally:
                await _cleanup(db)

        assert _run(scenario) == 1

    def test_streak_zero_when_no_yesterday(self):
        uid = f"synth_z_{uuid.uuid4().hex[:8]}"

        async def scenario(db):
            from services.flappy_streak_saver import _streak_for
            try:
                await _register_user(db, uid, f"{uid}@example.com")
                await _add_daily(db, uid, _day_key_offset(2))
                return await _streak_for(uid)
            finally:
                await _cleanup(db)

        assert _run(scenario) == 0


# ── Send + Dedupe (mocked email transport) ───────────────

class TestSendAndDedupe:
    def test_send_writes_log_and_dedupes(self):
        uid = f"synth_send_{uuid.uuid4().hex[:8]}"
        email = f"{uid}@example.com"

        async def scenario(db):
            import services.flappy_streak_saver as svc
            try:
                await _register_user(db, uid, email)
                await _add_daily(db, uid, _day_key_offset(1))

                mock_send = AsyncMock(return_value={"success": True, "message_id": "mock-123"})
                with patch("utils.email_service.send_catalog_template", mock_send):
                    await svc.send_streak_saver_reminders()

                recipients_1 = [c.kwargs.get("recipient_email") for c in mock_send.call_args_list]
                first_hit = email in recipients_1

                today = _day_key_offset(0)
                log = await db.flappy_streak_saver_log.find_one(
                    {"user_id": uid, "day_key": today}, {"_id": 0}
                )

                # Tag for cleanup - real code doesn't tag it
                if log:
                    await db.flappy_streak_saver_log.update_one(
                        {"user_id": uid, "day_key": today},
                        {"$set": {SYNTHETIC_TAG: True}},
                    )

                # Second run - MUST dedupe
                mock_send2 = AsyncMock(return_value={"success": True})
                with patch("utils.email_service.send_catalog_template", mock_send2):
                    await svc.send_streak_saver_reminders()

                recipients_2 = [c.kwargs.get("recipient_email") for c in mock_send2.call_args_list]
                second_hit = email in recipients_2

                return {"first_hit": first_hit, "second_hit": second_hit, "log": log}
            finally:
                await _cleanup(db)

        result = _run(scenario)
        assert result["first_hit"] is True, "First run should have sent to our synthetic user"
        assert result["log"] is not None, "Log record must be persisted"
        assert result["log"]["email"] == email
        assert result["log"]["success"] is True
        assert result["log"]["streak"] == 1
        assert result["log"]["target"] > 0
        assert result["second_hit"] is False, "Dedupe FAILED - re-sent to same user on 2nd run"


# ── HTTP Admin Endpoint ──────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    resp = s.post(
        f"{LOCAL_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} {resp.text[:200]}")
    csrf = s.cookies.get("csrf_token")
    if csrf:
        s.headers.update({"X-CSRF-Token": csrf})
    return s


@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    resp = s.post(
        f"{LOCAL_URL}/api/auth/login",
        json={"email": FREE_EMAIL, "password": FREE_PASSWORD},
        timeout=30,
    )
    if resp.status_code != 200:
        pytest.skip(f"Free user login failed: {resp.status_code} {resp.text[:200]}")
    csrf = s.cookies.get("csrf_token")
    if csrf:
        s.headers.update({"X-CSRF-Token": csrf})
    return s


class TestAdminEndpointGuardrails:
    URL = f"{LOCAL_URL}/api/flappy-bird/admin/streak-saver-run"

    def test_anonymous_denied(self):
        r = requests.post(self.URL, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
        assert r.status_code in (401, 403), f"Expected 401/403 for anon, got {r.status_code}"

    def test_non_admin_denied(self, free_session):
        r = free_session.post(self.URL, timeout=15)
        assert r.status_code in (401, 403), \
            f"Expected 401/403 for free user, got {r.status_code}: {r.text[:200]}"


class TestAdminEndpointHappyPath:
    def test_admin_run_returns_shape(self, admin_session):
        r = admin_session.post(
            f"{LOCAL_URL}/api/flappy-bird/admin/streak-saver-run",
            timeout=60,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
        data = r.json()
        assert {"at_risk_count", "emails_sent", "day_key"}.issubset(data.keys()), \
            f"Missing keys in {data}"
        assert isinstance(data["at_risk_count"], int)
        assert isinstance(data["emails_sent"], int)
        assert data["day_key"] == _day_key_offset(0)
        assert data["emails_sent"] <= data["at_risk_count"] + 1
