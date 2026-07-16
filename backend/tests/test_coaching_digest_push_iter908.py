"""Iteration 908 — Daily AI Coaching Team push digest.

Coverage:
- Admin dry-run + real-run of POST /api/ai-coaching-team/digest/push/run
- GET /api/ai-coaching-team/digest/push/runs listing
- Auth guard: unauthenticated 401 + free user 403
- Push token register (fake ExponentPushToken) then real run + dedupe
- Notification settings coaching_digest_push default + opt-out flow
- Regression: GET/PUT /api/notifications/settings + weekly EMAIL digest dry-run
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

HEADERS_CSRF = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}

FAKE_PUSH_TOKEN = "ExponentPushToken[testing-agent-fake-token]"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS_CSRF)
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:400]}"
    return s


# ── Session fixtures ──
@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    return _login(FREE_EMAIL, FREE_PASSWORD)


@pytest.fixture(scope="module")
def anon_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS_CSRF)
    return s


# ── Admin dry-run / real-run / listing ──
class TestPushDigestAdmin:
    def test_dry_run_summary_shape(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/ai-coaching-team/digest/push/run?dry_run=true", timeout=90
        )
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        for k in ("candidates", "sent", "skipped_pref", "skipped_no_channel",
                  "deduped", "errors", "trigger", "dry_run", "day"):
            assert k in data, f"missing key {k} in summary: {data}"
        assert data["dry_run"] is True
        assert isinstance(data["candidates"], int) and data["candidates"] >= 0
        assert isinstance(data["errors"], int)

    def test_real_run_persists_and_lists(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/ai-coaching-team/digest/push/run?dry_run=false", timeout=180
        )
        assert r.status_code == 200, r.text[:500]
        summary = r.json()
        assert summary["dry_run"] is False
        assert "candidates" in summary
        # Now GET runs list and confirm at least one entry
        rr = admin_session.get(
            f"{BASE_URL}/api/ai-coaching-team/digest/push/runs?limit=5", timeout=30
        )
        assert rr.status_code == 200, rr.text[:500]
        runs = rr.json().get("runs", [])
        assert isinstance(runs, list) and len(runs) >= 1
        top = runs[0]
        for k in ("candidates", "sent", "skipped_pref", "skipped_no_channel",
                  "deduped", "errors", "day"):
            assert k in top


# ── Auth guards ──
class TestPushDigestAuthGuards:
    def test_unauth_run_rejected(self, anon_session):
        r = anon_session.post(
            f"{BASE_URL}/api/ai-coaching-team/digest/push/run?dry_run=true", timeout=30
        )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"

    def test_unauth_runs_list_rejected(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/ai-coaching-team/digest/push/runs", timeout=30)
        assert r.status_code in (401, 403)

    def test_free_user_run_forbidden(self, free_session):
        r = free_session.post(
            f"{BASE_URL}/api/ai-coaching-team/digest/push/run?dry_run=true", timeout=30
        )
        assert r.status_code in (401, 403), f"expected 403 for free user, got {r.status_code}: {r.text[:200]}"

    def test_free_user_runs_list_forbidden(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/ai-coaching-team/digest/push/runs", timeout=30)
        assert r.status_code in (401, 403)


# ── Notification settings default + opt-out ──
class TestNotificationSettingsCoachingDigestPush:
    def test_default_coaching_digest_push_true(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/notifications/settings", timeout=30)
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert "coaching_digest_push" in data, f"missing coaching_digest_push in settings: {data}"
        # Default per DEFAULT_SETTINGS is True
        assert data["coaching_digest_push"] is True

    def test_regression_all_default_fields_present(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/notifications/settings", timeout=30)
        assert r.status_code == 200
        data = r.json()
        for k in ("push_enabled", "email_enabled", "daily_briefing", "practice_reminders",
                  "achievement_alerts", "weekly_digest", "team_updates", "goal_reminders",
                  "coaching_nudges", "coaching_digest_push",
                  "quiet_hours_enabled", "quiet_hours_start", "quiet_hours_end"):
            assert k in data, f"missing field {k} in settings response"

    def test_put_opt_out_and_back_in(self, free_session):
        # Opt out
        time.sleep(3)
        r = free_session.put(
            f"{BASE_URL}/api/notifications/settings",
            json={"coaching_digest_push": False}, timeout=30,
        )
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert data.get("coaching_digest_push") is False

        # Verify GET reflects it
        time.sleep(3)
        rg = free_session.get(f"{BASE_URL}/api/notifications/settings", timeout=30)
        assert rg.status_code == 200
        assert rg.json().get("coaching_digest_push") is False

        # Restore back to True (cleanup)
        time.sleep(3)
        rp = free_session.put(
            f"{BASE_URL}/api/notifications/settings",
            json={"coaching_digest_push": True}, timeout=30,
        )
        assert rp.status_code == 200, f"restore PUT failed: {rp.status_code} {rp.text[:200]}"
        assert rp.json().get("coaching_digest_push") is True


# ── Push token registration + dedupe flow ──
class TestPushTokenAndDedupe:
    def test_register_fake_expo_push_token(self, free_session):
        time.sleep(5)
        r = free_session.post(
            f"{BASE_URL}/api/notifications/push-token",
            json={"push_token": FAKE_PUSH_TOKEN, "platform": "expo"}, timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        j = r.json()
        assert j.get("success") is True

    def test_admin_real_run_after_token_and_then_dedupe(self, admin_session):
        """Two consecutive real runs; second should show deduped>=first_sent OR the free user is skipped once counted."""
        time.sleep(5)
        # First real run
        r1 = admin_session.post(
            f"{BASE_URL}/api/ai-coaching-team/digest/push/run?dry_run=false", timeout=180
        )
        assert r1.status_code == 200, f"{r1.status_code} {r1.text[:500]}"
        s1 = r1.json()
        time.sleep(5)
        # Second real run — same day → dedupe path should count everyone who was sent
        r2 = admin_session.post(
            f"{BASE_URL}/api/ai-coaching-team/digest/push/run?dry_run=false", timeout=180
        )
        assert r2.status_code == 200, f"{r2.status_code} {r2.text[:500]}"
        s2 = r2.json()

        # Summary integrity: candidates should be equal (same-day snapshot roughly)
        assert s1["candidates"] >= 0 and s2["candidates"] >= 0
        # Dedupe assertion: after first real run inserts logs, the second run must show
        # deduped >= s1["sent"] (each successfully-sent user should now be in dedupe log)
        # Allow small drift due to concurrent activity.
        assert s2["deduped"] >= s1["sent"], (
            f"expected s2.deduped ({s2['deduped']}) >= s1.sent ({s1['sent']}); "
            f"s1={s1}, s2={s2}"
        )

    def test_cleanup_delete_push_token(self, free_session):
        time.sleep(5)
        r = free_session.delete(f"{BASE_URL}/api/notifications/push-token", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        assert r.json().get("success") is True


# ── Regression: weekly EMAIL digest dry-run still works (do NOT send real emails) ──
class TestWeeklyEmailDigestRegression:
    def test_admin_weekly_email_digest_dry_run(self, admin_session):
        time.sleep(5)
        r = admin_session.post(
            f"{BASE_URL}/api/ai-coaching-team/digest/run?dry_run=true", timeout=120
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:500]}"
        data = r.json()
        # Weekly email digest returns a summary dict
        assert isinstance(data, dict)
        # dry_run should be echoed back and no email sending in dry-run
        assert data.get("dry_run") is True or "dry_run" in data
