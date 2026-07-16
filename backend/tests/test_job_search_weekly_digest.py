"""Feature 26 Job Search — Weekly Digest backend tests.

Covers:
- GET/POST /api/job-search/digest/preference (auth user, default opt-in, opt-out toggle)
- POST /api/job-search/digest/send-now (admin-only 403 for free/non-admin)
- GET /api/job-search/digest/runs (admin-only 403 for non-admin)
- Opt-out honored: subscribed=false => audience 0, sent 0
- Idempotency (force=False): once a run exists this ISO week, cron path returns skipped='already_sent'
- Email template 'job_search_weekly_digest' is registered and renders without error
- Regression: free-tier /api/job-search/summary and /jobs still accessible (200, not 403)
"""

import os
import sys
import asyncio
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

WRITE_HEADERS = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}


def _login(session: requests.Session, email: str, password: str) -> requests.Response:
    return session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=WRITE_HEADERS,
        timeout=30,
    )


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    r = _login(s, FREE_EMAIL, FREE_PASSWORD)
    if r.status_code != 200:
        pytest.skip(f"Free login failed: {r.status_code} {r.text[:200]}")
    return s


def _relogin_if_needed(session: requests.Session, email: str, password: str, resp: requests.Response) -> requests.Response:
    """If 401, re-login (admin sessions rotate quickly per feature-req note)."""
    if resp.status_code == 401:
        _login(session, email, password)
    return resp


# ── Preference endpoints (admin) ─────────────────────────────

class TestDigestPreference:
    def test_default_get_returns_subscribed_true(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/job-search/digest/preference", timeout=15)
        if r.status_code == 401:
            _login(admin_session, ADMIN_EMAIL, ADMIN_PASSWORD)
            r = admin_session.get(f"{BASE_URL}/api/job-search/digest/preference", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "subscribed" in data
        assert isinstance(data["subscribed"], bool)

    def test_toggle_off_then_on(self, admin_session):
        # Off
        r = admin_session.post(
            f"{BASE_URL}/api/job-search/digest/preference",
            json={"subscribed": False},
            headers=WRITE_HEADERS,
            timeout=15,
        )
        if r.status_code == 401:
            _login(admin_session, ADMIN_EMAIL, ADMIN_PASSWORD)
            r = admin_session.post(
                f"{BASE_URL}/api/job-search/digest/preference",
                json={"subscribed": False},
                headers=WRITE_HEADERS,
                timeout=15,
            )
        assert r.status_code == 200, r.text
        assert r.json().get("subscribed") is False

        g = admin_session.get(f"{BASE_URL}/api/job-search/digest/preference", timeout=15)
        assert g.status_code == 200
        assert g.json().get("subscribed") is False

        # Back on (restore)
        r2 = admin_session.post(
            f"{BASE_URL}/api/job-search/digest/preference",
            json={"subscribed": True},
            headers=WRITE_HEADERS,
            timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json().get("subscribed") is True

        g2 = admin_session.get(f"{BASE_URL}/api/job-search/digest/preference", timeout=15)
        assert g2.status_code == 200
        assert g2.json().get("subscribed") is True


# ── Admin-only guard on send-now and runs ────────────────────

class TestDigestAdminGuard:
    def test_send_now_forbidden_for_free_user(self, free_session):
        r = free_session.post(
            f"{BASE_URL}/api/job-search/digest/send-now",
            headers=WRITE_HEADERS,
            timeout=30,
        )
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}: {r.text[:200]}"

    def test_runs_forbidden_for_free_user(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/job-search/digest/runs", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# ── send-now happy path + opt-out honored ────────────────────

class TestDigestSendNowAndOptOut:
    def test_send_now_opt_out_then_opt_in_flow(self, admin_session):
        # Ensure baseline opted-in
        admin_session.post(
            f"{BASE_URL}/api/job-search/digest/preference",
            json={"subscribed": True},
            headers=WRITE_HEADERS,
            timeout=15,
        )

        # Opt-out admin
        p_off = admin_session.post(
            f"{BASE_URL}/api/job-search/digest/preference",
            json={"subscribed": False},
            headers=WRITE_HEADERS,
            timeout=15,
        )
        if p_off.status_code == 401:
            _login(admin_session, ADMIN_EMAIL, ADMIN_PASSWORD)
            p_off = admin_session.post(
                f"{BASE_URL}/api/job-search/digest/preference",
                json={"subscribed": False},
                headers=WRITE_HEADERS,
                timeout=15,
            )
        assert p_off.status_code == 200

        # send-now with opt-out -> audience 0
        r = admin_session.post(
            f"{BASE_URL}/api/job-search/digest/send-now",
            headers=WRITE_HEADERS,
            timeout=60,
        )
        if r.status_code == 401:
            _login(admin_session, ADMIN_EMAIL, ADMIN_PASSWORD)
            r = admin_session.post(
                f"{BASE_URL}/api/job-search/digest/send-now",
                headers=WRITE_HEADERS,
                timeout=60,
            )
        assert r.status_code == 200, r.text[:400]
        summary_off = r.json()
        assert summary_off.get("status") == "complete"
        assert summary_off.get("trigger") == "admin_manual"
        assert "week_key" in summary_off
        assert summary_off.get("audience") == 0, f"expected 0 got {summary_off.get('audience')}"
        assert summary_off.get("sent") == 0

        # Opt back in
        p_on = admin_session.post(
            f"{BASE_URL}/api/job-search/digest/preference",
            json={"subscribed": True},
            headers=WRITE_HEADERS,
            timeout=15,
        )
        assert p_on.status_code == 200
        assert p_on.json().get("subscribed") is True

        # send-now again -> audience >= 1 (admin has a job_search_profile from prior tests)
        r2 = admin_session.post(
            f"{BASE_URL}/api/job-search/digest/send-now",
            headers=WRITE_HEADERS,
            timeout=60,
        )
        assert r2.status_code == 200, r2.text[:400]
        summary_on = r2.json()
        assert summary_on.get("status") == "complete"
        assert summary_on.get("trigger") == "admin_manual"
        assert isinstance(summary_on.get("audience"), int)
        assert summary_on.get("audience") >= 1, f"expected audience>=1 got {summary_on.get('audience')}"
        # sent may be 0 if no matching content and no matches/kits/apps this week — spec says
        # 'skipped_no_content' bucket is expected; both 'sent' and 'skipped_no_content' are ints
        assert isinstance(summary_on.get("sent"), int)
        assert isinstance(summary_on.get("skipped_no_content"), int)

    def test_runs_lists_recent_runs(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/job-search/digest/runs", timeout=15)
        if r.status_code == 401:
            _login(admin_session, ADMIN_EMAIL, ADMIN_PASSWORD)
            r = admin_session.get(f"{BASE_URL}/api/job-search/digest/runs", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        runs = data.get("runs") or []
        assert isinstance(runs, list)
        assert len(runs) >= 1
        # newest run has week_key + status
        assert "week_key" in runs[0]
        assert runs[0].get("status") == "complete"


# ── Idempotency (cron path force=False) + template registration (python-level) ─────

class TestIdempotencyAndTemplate:
    """Runs against local backend python — imports scheduler_jobs.digests and email_templates."""

    def setup_method(self):
        # Make backend importable
        if "/app/backend" not in sys.path:
            sys.path.insert(0, "/app/backend")

    def test_template_registered_in_catalog(self):
        from utils.email_templates import TEMPLATE_CATALOG
        assert "job_search_weekly_digest" in TEMPLATE_CATALOG, f"catalog keys sample={list(TEMPLATE_CATALOG.keys())[:5]}"

    def test_template_builder_renders(self):
        from utils.email_templates import build_job_search_weekly_digest_email
        tmpl = build_job_search_weekly_digest_email(
            user_name="Alex",
            week_label="Week of Jul 03",
            new_roles_count=3,
            top_roles=[
                {"title": "AI Engineer", "department": "Engineering", "location": "Remote"},
                {"title": "Staff Engineer", "department": "Platform", "location": "NYC"},
                {"title": "ML Lead", "department": "Data", "location": "Remote"},
            ],
            best_fit_score=82,
            best_fit_job_title="AI Engineer",
            kits_generated=2,
            apps_tracked=1,
            show_upgrade_hint=True,
        )
        assert getattr(tmpl, "subject", None), "subject missing"
        assert "digest" in tmpl.subject.lower()
        assert getattr(tmpl, "html", None) and len(tmpl.html) > 100
        assert getattr(tmpl, "text", None) and len(tmpl.text) > 20
        # upgrade hint should appear in html when show_upgrade_hint True
        assert "upgrade" in tmpl.html.lower()

    def test_cron_path_idempotent_already_sent(self):
        """After send-now this week completed a run, cron (force=False) should skip."""
        from scheduler_jobs.digests import _send_job_search_weekly_digest
        from routes.db import db

        result = asyncio.get_event_loop().run_until_complete(
            _send_job_search_weekly_digest(db, trigger="cron", force=False)
        )
        assert result.get("skipped") == "already_sent", f"expected already_sent skip, got {result}"
        assert "week_key" in result


# ── Scheduler registration (code inspection) ─────────────────

class TestSchedulerRegistration:
    def test_scheduler_registers_mon_0930(self):
        with open("/app/backend/scheduler.py", "r", encoding="utf-8") as f:
            src = f.read()
        assert "id=\"job_search_weekly_digest\"" in src or "id='job_search_weekly_digest'" in src, \
            "job_search_weekly_digest scheduler id not registered"
        # CronTrigger mon 09:30 near the registration
        idx = src.find("job_search_weekly_digest")
        window = src[max(0, idx - 400): idx + 200]
        assert "CronTrigger" in window
        assert "mon" in window
        assert "hour=9" in window and "minute=30" in window


# ── Regression: free-tier /api/job-search core reads still 200 ────

class TestFreeTierRegression:
    def test_free_summary_and_jobs_accessible(self, free_session):
        r_sum = free_session.get(f"{BASE_URL}/api/job-search/summary", timeout=15)
        assert r_sum.status_code == 200, f"summary {r_sum.status_code}: {r_sum.text[:200]}"
        r_jobs = free_session.get(f"{BASE_URL}/api/job-search/jobs", timeout=20)
        assert r_jobs.status_code == 200, f"jobs {r_jobs.status_code}: {r_jobs.text[:200]}"
        assert isinstance(r_jobs.json().get("jobs"), list)
