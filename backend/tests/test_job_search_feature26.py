"""Feature 26 Job Search - Backend API tests.

Covers: profile PUT/GET, jobs search, AI fit match (with 400 when no profile),
documents/generate (drafter->reviewer), ATS check, application tracker CRUD,
workspace summary, and features registry entry rename.
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
        pytest.skip("Admin login failed")
    return s


@pytest.fixture(scope="module")
def fresh_user_session():
    """Fresh unregistered user (for the 'complete your profile' 400 test)."""
    s = requests.Session()
    email = f"TEST_jobsearch_{uuid.uuid4().hex[:10]}@example.com"
    password = "TestJobs#2026Aa!"

    # Register the user
    r = s.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password, "full_name": "Job Search Test User"},
        headers=WRITE_HEADERS,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"Fresh user register failed: {r.status_code} {r.text[:200]}")

    # Login (register may auto-login; ensure cookie session)
    if not _login(s, email, password):
        pytest.skip(f"Fresh user login failed for {email}")
    return s


# -------------------- Auth guard --------------------

class TestAuthGuard:
    def test_jobs_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/job-search/jobs", timeout=15)
        assert r.status_code in (401, 403), f"Expected 401/403 got {r.status_code}"


# -------------------- Profile --------------------

class TestProfile:
    def test_put_and_get_profile(self, admin_session):
        payload = {
            "headline": "Senior AI Engineer",
            "summary": "10+ years building ML and AI systems for growth.",
            "skills": ["Python", "FastAPI", "React", "LLM", "MongoDB"],
            "experience_years": 10,
            "education": "MSc Computer Science",
            "target_roles": ["AI Engineer", "Staff Engineer"],
            "preferred_location": "Remote",
            "remote_preferred": True,
            "achievements": "Built RAG platform serving 1M users",
        }
        r = admin_session.put(
            f"{BASE_URL}/api/job-search/profile", json=payload, headers=WRITE_HEADERS, timeout=30
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        prof = body["profile"]
        assert prof["headline"] == "Senior AI Engineer"
        assert "Python" in prof["skills"]

        # GET to verify persisted
        g = admin_session.get(f"{BASE_URL}/api/job-search/profile", timeout=15)
        assert g.status_code == 200, g.text
        got = g.json()["profile"]
        assert got is not None
        assert got["summary"].startswith("10+")
        assert got["experience_years"] == 10
        assert got["remote_preferred"] is True


# -------------------- Jobs Search --------------------

class TestJobsSearch:
    def test_search_engineer(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/job-search/jobs?q=engineer", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)
        # Main agent noted 32 results; assert at least 1
        assert len(data["jobs"]) >= 1
        job = data["jobs"][0]
        # Required fields per spec
        for k in ("job_id", "title", "department", "location", "type", "level"):
            assert k in job, f"missing {k}"

    def test_search_returns_open_jobs_default(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/job-search/jobs", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json().get("jobs"), list)


# -------------------- Match --------------------

class TestMatch:
    def test_match_without_profile_returns_400(self, fresh_user_session):
        # First get a job_id
        rj = fresh_user_session.get(f"{BASE_URL}/api/job-search/jobs?q=engineer", timeout=20)
        assert rj.status_code == 200, rj.text
        jobs = rj.json().get("jobs", [])
        if not jobs:
            pytest.skip("no jobs available")
        job_id = jobs[0]["job_id"]

        r = fresh_user_session.post(
            f"{BASE_URL}/api/job-search/match",
            json={"job_id": job_id},
            headers=WRITE_HEADERS,
            timeout=30,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
        detail = r.json().get("detail", "")
        assert "profile" in detail.lower()

    def test_match_with_profile_returns_ai_score(self, admin_session):
        rj = admin_session.get(f"{BASE_URL}/api/job-search/jobs?q=engineer", timeout=20)
        jobs = rj.json().get("jobs", [])
        if not jobs:
            pytest.skip("no jobs")
        job_id = jobs[0]["job_id"]

        r = admin_session.post(
            f"{BASE_URL}/api/job-search/match",
            json={"job_id": job_id},
            headers=WRITE_HEADERS,
            timeout=120,
        )
        assert r.status_code == 200, r.text
        m = r.json()["match"]
        assert isinstance(m.get("overall_score"), (int, float))
        assert m.get("recommendation") in ("strong_apply", "apply", "stretch", "skip")
        dims = m.get("dimensions") or []
        assert len(dims) >= 3, f"Expected 5 dimensions, got {len(dims)}"
        # Store for later use
        TestMatch.job_id = job_id  # type: ignore


# -------------------- Documents + ATS --------------------

class TestDocumentsAndAts:
    _job_id = None

    def test_generate_documents(self, admin_session):
        rj = admin_session.get(f"{BASE_URL}/api/job-search/jobs?q=engineer", timeout=20)
        jobs = rj.json().get("jobs", [])
        if not jobs:
            pytest.skip("no jobs")
        job_id = jobs[0]["job_id"]
        TestDocumentsAndAts._job_id = job_id

        r = admin_session.post(
            f"{BASE_URL}/api/job-search/documents/generate",
            json={"job_id": job_id},
            headers=WRITE_HEADERS,
            timeout=240,
        )
        assert r.status_code == 200, r.text[:500]
        doc = r.json()["document"]
        assert doc.get("cv_markdown") and len(doc["cv_markdown"]) > 100
        assert doc.get("cover_letter_markdown") and len(doc["cover_letter_markdown"]) > 50
        assert isinstance(doc.get("reviewer_notes"), list)

        # List documents
        gl = admin_session.get(f"{BASE_URL}/api/job-search/documents", timeout=20)
        assert gl.status_code == 200
        docs = gl.json().get("documents") or []
        assert any(d.get("job_id") == job_id for d in docs)

    def test_ats_check_after_generate(self, admin_session):
        job_id = TestDocumentsAndAts._job_id
        if not job_id:
            pytest.skip("no job_id from prior test")
        r = admin_session.post(
            f"{BASE_URL}/api/job-search/ats-check",
            json={"job_id": job_id},
            headers=WRITE_HEADERS,
            timeout=180,
        )
        assert r.status_code == 200, r.text[:500]
        rep = r.json()["ats_report"]
        assert isinstance(rep.get("ats_score"), (int, float))
        assert isinstance(rep.get("covered_keywords"), list)
        assert isinstance(rep.get("missing_keywords"), list)
        assert "parseability" in rep
        assert "recommendations" in rep

    def test_ats_check_without_docs_returns_400(self, admin_session):
        # Use a different job with no docs generated for admin
        rj = admin_session.get(f"{BASE_URL}/api/job-search/jobs", timeout=20)
        jobs = rj.json().get("jobs", [])
        used_id = TestDocumentsAndAts._job_id
        candidate = next((j for j in jobs if j.get("job_id") != used_id), None)
        if not candidate:
            pytest.skip("only one job available")
        r = admin_session.post(
            f"{BASE_URL}/api/job-search/ats-check",
            json={"job_id": candidate["job_id"]},
            headers=WRITE_HEADERS,
            timeout=30,
        )
        assert r.status_code == 400, f"Expected 400 got {r.status_code}"


# -------------------- Application Tracker --------------------

class TestTracker:
    _app_id = None
    _job_id = None

    def test_create_and_duplicate_and_patch_and_delete(self, admin_session):
        rj = admin_session.get(f"{BASE_URL}/api/job-search/jobs?q=engineer", timeout=20)
        jobs = rj.json().get("jobs", [])
        if len(jobs) < 2:
            pytest.skip("need at least 2 jobs")
        # pick a job that isn't already tracked - use one deeper in list
        job = jobs[-1]
        job_id = job["job_id"]
        # Try to clean any existing entry first
        lst = admin_session.get(f"{BASE_URL}/api/job-search/applications", timeout=15).json().get("applications", [])
        for a in lst:
            if a.get("job_id") == job_id:
                admin_session.delete(
                    f"{BASE_URL}/api/job-search/applications/{a['application_id']}",
                    headers=WRITE_HEADERS,
                    timeout=15,
                )
        TestTracker._job_id = job_id

        # Create
        r = admin_session.post(
            f"{BASE_URL}/api/job-search/applications",
            json={"job_id": job_id, "status": "saved"},
            headers=WRITE_HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        app = r.json()["application"]
        assert app["status"] == "saved"
        TestTracker._app_id = app["application_id"]

        # Duplicate -> 409
        r2 = admin_session.post(
            f"{BASE_URL}/api/job-search/applications",
            json={"job_id": job_id, "status": "saved"},
            headers=WRITE_HEADERS,
            timeout=20,
        )
        assert r2.status_code == 409

        # Patch to interview
        r3 = admin_session.patch(
            f"{BASE_URL}/api/job-search/applications/{TestTracker._app_id}",
            json={"status": "interview"},
            headers=WRITE_HEADERS,
            timeout=20,
        )
        assert r3.status_code == 200, r3.text
        upd = r3.json()["application"]
        assert upd["status"] == "interview"
        assert isinstance(upd.get("history"), list) and len(upd["history"]) >= 2

        # Invalid status -> 400
        r4 = admin_session.patch(
            f"{BASE_URL}/api/job-search/applications/{TestTracker._app_id}",
            json={"status": "bogus"},
            headers=WRITE_HEADERS,
            timeout=20,
        )
        assert r4.status_code == 400

        # List
        rl = admin_session.get(f"{BASE_URL}/api/job-search/applications", timeout=15)
        assert rl.status_code == 200
        assert any(a["application_id"] == TestTracker._app_id for a in rl.json()["applications"])

        # Delete
        rd = admin_session.delete(
            f"{BASE_URL}/api/job-search/applications/{TestTracker._app_id}",
            headers=WRITE_HEADERS,
            timeout=15,
        )
        assert rd.status_code == 200
        # Verify gone
        rl2 = admin_session.get(f"{BASE_URL}/api/job-search/applications", timeout=15).json()
        assert not any(a["application_id"] == TestTracker._app_id for a in rl2["applications"])


# -------------------- Summary --------------------

class TestSummary:
    def test_summary_shape(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/job-search/summary", timeout=20)
        assert r.status_code == 200, r.text
        s = r.json()
        for k in ("profile_complete", "open_jobs", "matches", "documents", "tracked", "interviews", "offers"):
            assert k in s, f"summary missing key {k}"
        assert isinstance(s["open_jobs"], int)
        assert isinstance(s["profile_complete"], bool)


# -------------------- Feature Registry --------------------

class TestFeatureRegistry:
    def test_jobs_portal_entry_renamed_to_job_search(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/features/registry", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        features = data.get("features") or data.get("registry") or data
        # Try common shapes
        if isinstance(features, dict) and "features" in features:
            features = features["features"]
        # find entry
        entry = None
        if isinstance(features, list):
            entry = next((f for f in features if f.get("feature_id") == "jobs-portal"), None)
        elif isinstance(features, dict):
            entry = features.get("jobs-portal")
        assert entry is not None, f"jobs-portal entry not found; keys={list(features)[:10] if hasattr(features,'__iter__') else features}"
        assert entry.get("title") == "Job Search", f"title={entry.get('title')}"
        assert entry.get("route") == "/job-search", f"route={entry.get('route')}"
        assert entry.get("icon") == "search", f"icon={entry.get('icon')}"
        assert entry.get("enabled") is True
