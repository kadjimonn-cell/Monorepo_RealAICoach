"""End-to-end backend test for Smart Weekly Digest (iteration 864).

Covers the per-user 'Smart Weekly Digest' feature added in this iteration:
- send-email self/admin flow with force=true
- ISO-week idempotency (mongo weekly_digest_sends doc + skipped reason)
- authorization matrix (cross-user 403, self OK, unauth send-all 401, free send-all 403)
- opt-out respected (email_enabled=false → skipped:digest_email_disabled)
- template catalog preview (light + dark) with V7 chrome markers
- legacy digest endpoints still 200
- scheduler wiring (job registered) + module import
"""
import os
import subprocess
import requests
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
BACKEND_ENV = "/app/backend/.env"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PW = "NewAdminPass2026!"
ADMIN_USER_ID = "user_4b5a68d2f7c6"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PW = "P1Free#2026!Aa"

XRW = {"X-Requested-With": "XMLHttpRequest"}


def _read_env(path=BACKEND_ENV):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


@pytest.fixture(scope="session")
def mongo_client():
    env = _read_env()
    client = AsyncIOMotorClient(env["MONGO_URL"])
    return client[env["DB_NAME"]]


def _login(email, password):
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=XRW,
        timeout=30,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s, r.json()


@pytest.fixture(scope="session")
def admin_session():
    s, body = _login(ADMIN_EMAIL, ADMIN_PW)
    return s, body


@pytest.fixture(scope="session")
def free_session():
    s, body = _login(FREE_EMAIL, FREE_PW)
    return s, body


# ── 1. Smart digest send (self, admin, force=true) ──
class TestSmartDigestSend:
    def test_admin_self_send_force(self, admin_session):
        s, body = admin_session
        r = s.post(
            f"{BASE_URL}/api/weekly-digest/send-email/{ADMIN_USER_ID}?force=true",
            headers=XRW, timeout=60,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("success") is True
        assert "week_key" in data and data["week_key"].startswith("2026-W")
        digest = data.get("digest") or {}
        for key in [
            "user_name", "smart_tip", "streak_days", "longest_streak", "active_day_map",
            "day_labels", "sessions", "active_days", "xp_earned", "total_xp",
            "highlights", "week_label",
        ]:
            assert key in digest, f"missing digest key {key}"
        assert isinstance(digest["smart_tip"], str) and len(digest["smart_tip"]) > 0
        assert isinstance(digest["active_day_map"], list) and len(digest["active_day_map"]) == 7
        assert all(isinstance(b, bool) for b in digest["active_day_map"])
        assert isinstance(digest["day_labels"], list) and len(digest["day_labels"]) == 7

    def test_idempotent_without_force(self, admin_session):
        s, _ = admin_session
        r = s.post(
            f"{BASE_URL}/api/weekly-digest/send-email/{ADMIN_USER_ID}",
            headers=XRW, timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("skipped") is True
        assert data.get("reason") == "already_sent_this_week"

    @pytest.mark.asyncio
    async def test_weekly_digest_sends_doc_exists(self, mongo_client):
        # Compute current ISO week key
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isocalendar()
        wk = f"{now[0]}-W{now[1]:02d}"
        doc = await mongo_client.weekly_digest_sends.find_one(
            {"user_id": ADMIN_USER_ID, "week_key": wk}, {"_id": 0}
        )
        assert doc is not None, f"expected weekly_digest_sends doc for {ADMIN_USER_ID}/{wk}"
        assert doc["user_id"] == ADMIN_USER_ID
        assert doc["week_key"] == wk
        assert "sent_at" in doc


# ── 2. Authorization matrix ──
class TestAuthorization:
    def test_free_cannot_send_admin_digest(self, free_session):
        s, _ = free_session
        r = s.post(
            f"{BASE_URL}/api/weekly-digest/send-email/{ADMIN_USER_ID}?force=true",
            headers=XRW, timeout=30,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"

    def test_free_can_send_own_digest(self, free_session):
        s, body = free_session
        free_uid = (body.get("user") or {}).get("user_id") or body.get("user_id")
        assert free_uid, f"could not extract user_id from free login body: {body}"
        r = s.post(
            f"{BASE_URL}/api/weekly-digest/send-email/{free_uid}",
            headers=XRW, timeout=60,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # success or skipped both acceptable
        assert (data.get("success") is True) or (data.get("skipped") is True)

    def test_unauth_send_all_401(self):
        r = requests.post(f"{BASE_URL}/api/weekly-digest/send-all", headers=XRW, timeout=15)
        assert r.status_code == 401, f"expected 401 got {r.status_code}"

    def test_free_send_all_403(self, free_session):
        s, _ = free_session
        r = s.post(f"{BASE_URL}/api/weekly-digest/send-all", headers=XRW, timeout=15)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"


# ── 3. Opt-out respected ──
class TestOptOut:
    def test_disable_and_skip(self, free_session):
        s, body = free_session
        free_uid = (body.get("user") or {}).get("user_id") or body.get("user_id")
        # Disable
        r = s.put(
            f"{BASE_URL}/api/weekly-digest/preferences",
            json={"user_id": free_uid, "email_enabled": False},
            headers=XRW, timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        # Send with force → should skip due to opt-out
        r = s.post(
            f"{BASE_URL}/api/weekly-digest/send-email/{free_uid}?force=true",
            headers=XRW, timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("skipped") is True
        assert data.get("reason") == "digest_email_disabled"
        # Restore
        r = s.put(
            f"{BASE_URL}/api/weekly-digest/preferences",
            json={"user_id": free_uid, "email_enabled": True},
            headers=XRW, timeout=15,
        )
        assert r.status_code == 200


# ── 4. Preview template (light + dark) ──
class TestPreview:
    REQUIRED_MARKERS = [
        "email-header-wordmark",
        "email-header-trust",
        "DAY STREAK",
        "Coaching Sessions",
        "Your Coach",
        "Keep Your Streak Alive",
        "em-footer-chip",
        'data-global-footer-version="gef_v2026_06_pro_chrome_redesign"',
    ]

    def _fetch(self, admin_session, theme):
        s, _ = admin_session
        r = s.get(
            f"{BASE_URL}/api/email-notifications/preview/smart_weekly_digest?theme={theme}",
            timeout=30,
        )
        assert r.status_code == 200, f"{theme} preview {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body.get("template_type") == "smart_weekly_digest"
        assert body.get("theme") == theme
        assert body.get("footer_version") == "gef_v2026_06_pro_chrome_redesign"
        return body.get("html", "")

    def test_preview_light(self, admin_session):
        html = self._fetch(admin_session, "light")
        for marker in self.REQUIRED_MARKERS:
            assert marker in html, f"light preview missing marker: {marker}"
        assert "data-theme-light" in html

    def test_preview_dark(self, admin_session):
        html = self._fetch(admin_session, "dark")
        for marker in self.REQUIRED_MARKERS:
            assert marker in html, f"dark preview missing marker: {marker}"
        assert "data-theme-dark" in html


# ── 5. Legacy digest endpoints still work ──
class TestLegacyEndpoints:
    def test_get_preferences(self, admin_session):
        s, _ = admin_session
        r = s.get(f"{BASE_URL}/api/weekly-digest/preferences/{ADMIN_USER_ID}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("user_id") == ADMIN_USER_ID

    def test_get_history(self, admin_session):
        s, _ = admin_session
        r = s.get(f"{BASE_URL}/api/weekly-digest/history/{ADMIN_USER_ID}", timeout=15)
        assert r.status_code == 200
        assert "digests" in r.json()


# ── 6. Scheduler wiring + import ──
class TestSchedulerWiring:
    def test_scheduler_registers_job(self):
        with open("/app/backend/scheduler.py") as f:
            content = f.read()
        assert 'id="smart_weekly_digest_dispatch"' in content
        assert "CronTrigger(day_of_week='mon', hour=8" in content

    def test_scheduler_jobs_import(self):
        r = subprocess.run(
            ["python3", "-c", "from scheduler_jobs import scheduled_smart_weekly_digest; print('ok')"],
            cwd="/app/backend",
            capture_output=True, text=True, timeout=20,
            env={**os.environ, "PYTHONPATH": "/app/backend"},
        )
        assert r.returncode == 0, f"import failed: {r.stderr}"
        assert "ok" in r.stdout
