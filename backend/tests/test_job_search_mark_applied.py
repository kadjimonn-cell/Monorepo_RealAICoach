"""Feature 26 - POST /api/job-search/applications/mark-applied (funnel loop-closer).

Contract:
- Idempotent create-or-advance for tracker
- untracked open job  -> creates application at status='applied', returns changed:true
- 'saved'             -> advances to 'applied', appends history ['saved','applied'], changed:true
- 'applied'/'interview'/'offer' -> no-op, changed:false, never downgrades
- Nonexistent job_id  -> 404
- Unauthenticated     -> 401/403
"""

import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
WRITE_HEADERS = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}
MARK = f"{BASE_URL}/api/job-search/applications/mark-applied"
APPS = f"{BASE_URL}/api/job-search/applications"


def _login(session: requests.Session, email: str, password: str) -> bool:
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=WRITE_HEADERS,
        timeout=30,
    )
    return r.status_code == 200


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    if not _login(s, ADMIN_EMAIL, ADMIN_PASSWORD):
        pytest.skip("Admin login failed (possibly rate-limited)")
    return s


@pytest.fixture(scope="module")
def open_jobs(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/job-search/jobs?q=engineer", timeout=20)
    assert r.status_code == 200, r.text
    jobs = r.json().get("jobs", [])
    if len(jobs) < 2:
        pytest.skip("need at least 2 open jobs")
    return jobs


def _delete_if_tracked(session, job_id):
    """Delete existing tracker entry for job_id, if any."""
    r = session.get(APPS, timeout=20)
    if r.status_code != 200:
        return
    for app in r.json().get("applications", []):
        if app.get("job_id") == job_id:
            aid = app.get("application_id")
            session.delete(f"{APPS}/{aid}", headers=WRITE_HEADERS, timeout=15)


def _find_app(session, job_id):
    r = session.get(APPS, timeout=20)
    if r.status_code != 200:
        return None
    for app in r.json().get("applications", []):
        if app.get("job_id") == job_id:
            return app
    return None


# -------------------- Auth guards --------------------

class TestAuthGuards:
    def test_unauthenticated_returns_401_or_403(self):
        r = requests.post(MARK, json={"job_id": "job_senior-backend-engineer"},
                          headers=WRITE_HEADERS, timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}: {r.text[:200]}"

    def test_nonexistent_job_returns_404(self, admin_session):
        r = admin_session.post(
            MARK,
            json={"job_id": f"job_definitely_not_real_{uuid.uuid4().hex[:8]}"},
            headers=WRITE_HEADERS,
            timeout=20,
        )
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:200]}"


# -------------------- Untracked -> Applied --------------------

class TestUntrackedToApplied:
    def test_creates_as_applied_when_untracked(self, admin_session, open_jobs):
        # Pick a job likely untracked; delete existing tracker first if any
        job_id = open_jobs[0]["job_id"]
        _delete_if_tracked(admin_session, job_id)
        time.sleep(0.3)

        r = admin_session.post(MARK, json={"job_id": job_id},
                               headers=WRITE_HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        assert body.get("status") == "applied"
        assert body.get("changed") is True, f"expected changed:true for fresh create, got {body}"

        # Verify persisted with GET
        app = _find_app(admin_session, job_id)
        assert app is not None, "app not found after mark-applied"
        assert app.get("status") == "applied"
        history = app.get("history") or []
        assert any(h.get("status") == "applied" for h in history)


# -------------------- Saved -> Applied (advance + history) --------------------

class TestSavedToApplied:
    def test_advances_saved_to_applied_with_history(self, admin_session, open_jobs):
        job_id = open_jobs[1]["job_id"]
        # Reset then create as 'saved'
        _delete_if_tracked(admin_session, job_id)
        time.sleep(0.3)

        r = admin_session.post(
            APPS,
            json={"job_id": job_id, "status": "saved", "notes": "TEST_saved"},
            headers=WRITE_HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, r.text

        # Now mark applied
        m = admin_session.post(MARK, json={"job_id": job_id},
                               headers=WRITE_HEADERS, timeout=20)
        assert m.status_code == 200, m.text
        body = m.json()
        assert body.get("changed") is True
        assert body.get("status") == "applied"

        # Verify history advance
        app = _find_app(admin_session, job_id)
        assert app is not None
        assert app.get("status") == "applied"
        statuses = [h.get("status") for h in (app.get("history") or [])]
        assert statuses[:2] == ["saved", "applied"], f"expected history to start ['saved','applied'], got {statuses}"


# -------------------- Already Applied -> No-op (idempotent) --------------------

class TestAlreadyAppliedNoOp:
    def test_already_applied_returns_changed_false(self, admin_session, open_jobs):
        job_id = open_jobs[0]["job_id"]  # was marked applied above
        # Ensure it's applied
        app = _find_app(admin_session, job_id)
        if not app or app.get("status") != "applied":
            # bootstrap
            admin_session.post(MARK, json={"job_id": job_id},
                               headers=WRITE_HEADERS, timeout=20)

        r = admin_session.post(MARK, json={"job_id": job_id},
                               headers=WRITE_HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("changed") is False
        assert body.get("status") == "applied"

    def test_interview_status_not_downgraded(self, admin_session, open_jobs):
        job_id = open_jobs[1]["job_id"]
        # Advance the saved->applied one further to 'interview' via PATCH
        app = _find_app(admin_session, job_id)
        if not app:
            pytest.skip("prerequisite app missing")
        aid = app["application_id"]
        p = admin_session.patch(
            f"{APPS}/{aid}",
            json={"status": "interview"},
            headers=WRITE_HEADERS,
            timeout=20,
        )
        assert p.status_code == 200, p.text

        r = admin_session.post(MARK, json={"job_id": job_id},
                               headers=WRITE_HEADERS, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("changed") is False
        assert body.get("status") == "interview", f"must NOT downgrade, got {body}"

        # Verify DB still reflects 'interview'
        app2 = _find_app(admin_session, job_id)
        assert app2.get("status") == "interview"


# -------------------- Cleanup --------------------

def test_cleanup(admin_session, open_jobs):
    """Restore admin state to two 'applied' apps as noted in review request."""
    for j in open_jobs[:2]:
        app = _find_app(admin_session, j["job_id"])
        if app and app.get("status") != "applied":
            admin_session.patch(
                f"{APPS}/{app['application_id']}",
                json={"status": "applied"},
                headers=WRITE_HEADERS,
                timeout=15,
            )
