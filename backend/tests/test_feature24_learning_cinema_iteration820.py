"""
Feature 24 Learning Hub — Cinematic Rebuild (iteration 820)
Tests:
- Public cover endpoint (no auth) returns 1280x720 JPEG w/ Cache-Control
- Two different course_ids return DIFFERENT covers (unique per-course)
- Unknown course_id returns generic 200 cover (not 500)
- Authenticated /courses payload includes cover_url per course
- Enroll on a fresh course triggers non-blocking kickoff email (db.email_sends)
- Re-enrolling existing enrollment does NOT emit duplicate kickoff email
- Regression: hub-dashboard, my-learning-center, admin integrity/status
"""
import os
import io
import time
import hashlib
import struct
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# ---------------- helpers -----------------

@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="session")
def public_session():
    s = requests.Session()
    return s


def _jpeg_dimensions(data: bytes):
    """Parse JPEG SOF marker to get width/height."""
    idx = 2  # skip SOI
    while idx < len(data):
        while data[idx] != 0xFF:
            idx += 1
        while data[idx] == 0xFF:
            idx += 1
        marker = data[idx]
        idx += 1
        if marker in (0xC0, 0xC1, 0xC2):  # SOF0/SOF1/SOF2
            # length(2) + precision(1) + height(2) + width(2)
            h = struct.unpack(">H", data[idx + 3:idx + 5])[0]
            w = struct.unpack(">H", data[idx + 5:idx + 7])[0]
            return w, h
        if marker in (0xD8, 0xD9):
            return None
        length = struct.unpack(">H", data[idx:idx + 2])[0]
        idx += length
    return None


# ---------------- Course cover endpoint (public) -----------------

class TestCoverEndpointPublic:
    def test_courses_list_has_cover_url(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        courses = data.get("courses") or data if isinstance(data, list) else data.get("courses", [])
        assert isinstance(courses, list) and len(courses) > 0, "No courses returned"
        # Store one for downstream tests
        pytest.first_course_id = courses[0]["course_id"]
        pytest.second_course_id = courses[1]["course_id"]
        pytest.courses_list = courses
        # Every course must have cover_url
        for c in courses:
            assert "cover_url" in c, f"Missing cover_url in course {c.get('course_id')}"
            assert c["cover_url"] == f"/api/ai-learn/course-cover/{c['course_id']}.jpg", c["cover_url"]
        # Should have ~48 courses
        assert len(courses) >= 40, f"Expected ~48 courses, got {len(courses)}"

    def test_cover_public_no_auth_returns_jpeg(self, public_session):
        cid = getattr(pytest, "first_course_id", None)
        assert cid, "first_course_id not set"
        r = public_session.get(f"{BASE_URL}/api/ai-learn/course-cover/{cid}.jpg", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:150]}"
        assert "image/jpeg" in r.headers.get("Content-Type", ""), r.headers.get("Content-Type")
        assert "Cache-Control" in r.headers, list(r.headers.keys())
        body = r.content
        assert body[:2] == b"\xff\xd8", "Not a JPEG (missing SOI)"
        dims = _jpeg_dimensions(body)
        assert dims == (1280, 720), f"Expected 1280x720, got {dims}"
        pytest.first_cover_hash = hashlib.sha256(body).hexdigest()
        pytest.first_cover_size = len(body)

    def test_cover_two_courses_are_unique(self, public_session):
        cid2 = getattr(pytest, "second_course_id", None)
        r = public_session.get(f"{BASE_URL}/api/ai-learn/course-cover/{cid2}.jpg", timeout=30)
        assert r.status_code == 200
        h2 = hashlib.sha256(r.content).hexdigest()
        s2 = len(r.content)
        assert h2 != getattr(pytest, "first_cover_hash", None), "Two different course covers hash identical"
        # size may or may not differ (hashes are the real check)
        print(f"Cover uniqueness ok: size1={pytest.first_cover_size} size2={s2}")

    def test_cover_unknown_id_returns_generic_200(self, public_session):
        r = public_session.get(f"{BASE_URL}/api/ai-learn/course-cover/course_unknown_zzz9999.jpg", timeout=30)
        assert r.status_code == 200, f"Unknown id status {r.status_code}"
        assert "image/jpeg" in r.headers.get("Content-Type", "")
        assert r.content[:2] == b"\xff\xd8"


# ---------------- Enrollment kickoff email -----------------

class TestEnrollmentKickoffEmail:
    @pytest.mark.asyncio
    async def _find_kickoff_records(self, recipient, course_id=None):
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            db = client[DB_NAME]
            cursor = db.email_sends.find({
                "template_key": "learning_hub_enrollment_kickoff",
                "recipient": recipient,
            }).sort("sent_at", -1)
            return await cursor.to_list(length=100)
        finally:
            client.close()

    def _get_me(self, session):
        r = session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200, r.text[:200]
        return r.json()

    def _pick_unenrolled_course(self, session):
        r = session.get(f"{BASE_URL}/api/ai-learn/courses", timeout=30)
        assert r.status_code == 200
        courses = r.json().get("courses", [])
        for c in courses:
            if not c.get("enrolled"):
                return c
        # fallback
        return courses[-1]

    def test_enroll_triggers_kickoff_email_once(self, admin_session):
        me = self._get_me(admin_session)
        email = me.get("email") or me.get("user", {}).get("email") or ADMIN_EMAIL
        assert email, f"Cannot resolve email from /me: {me}"

        course = self._pick_unenrolled_course(admin_session)
        course_id = course["course_id"]
        was_enrolled = bool(course.get("enrolled"))
        print(f"Testing enrollment on course_id={course_id} already_enrolled={was_enrolled}")

        # capture kickoff count before
        loop = asyncio.new_event_loop()
        before = loop.run_until_complete(self._find_kickoff_records(email))
        before_ct = len(before)

        # enroll
        r = admin_session.post(f"{BASE_URL}/api/ai-learn/courses/{course_id}/enroll", json={}, timeout=30)
        assert r.status_code == 200, f"enroll status {r.status_code} body={r.text[:250]}"
        body = r.json()
        assert body.get("success") is True
        assert body.get("course_id") == course_id
        assert "enrolled_at" in body
        assert "plan" in body

        # allow non-blocking task to fire
        time.sleep(6.0)
        after = loop.run_until_complete(self._find_kickoff_records(email))
        after_ct = len(after)

        if not was_enrolled:
            assert after_ct == before_ct + 1, (
                f"Expected exactly 1 new kickoff email row (before={before_ct} after={after_ct}); "
                f"latest recipients: {[a.get('recipient') for a in after[:3]]}"
            )
            latest = after[0]  # sorted desc by sent_at
            subj = latest.get("subject", "")
            assert "enrolled" in subj.lower(), f"Unexpected subject: {subj}"
        else:
            assert after_ct == before_ct, f"Duplicate kickoff sent (before={before_ct} after={after_ct})"

        # Second enroll (idempotent) must NOT add another email
        r2 = admin_session.post(f"{BASE_URL}/api/ai-learn/courses/{course_id}/enroll", json={}, timeout=30)
        assert r2.status_code == 200
        time.sleep(6.0)
        again = loop.run_until_complete(self._find_kickoff_records(email))
        loop.close()
        assert len(again) == after_ct, (
            f"Re-enrollment produced duplicate kickoff email (after1={after_ct} after2={len(again)})"
        )


# ---------------- Regression endpoints -----------------

class TestLearningHubRegression:
    def test_hub_dashboard(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard", timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert isinstance(data, dict)

    def test_my_learning_center(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/ai-learn/my-learning-center", timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert isinstance(data, dict)

    def test_admin_integrity_status(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/ai-learn/admin/integrity/status", timeout=30)
        assert r.status_code == 200, r.text[:200]
