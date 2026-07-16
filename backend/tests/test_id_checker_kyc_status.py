"""
Backend regression for ID Checker /kyc/status endpoint.
Verifies GET /api/id-checker/kyc/status returns 200 for a logged-in
free user and includes id_checker.timeline with a milestones array.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": FREE_EMAIL, "password": FREE_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    assert "session_token" in s.cookies, "session_token cookie not set after login"
    return s


class TestIdCheckerKycStatus:
    def test_kyc_status_unauthenticated_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/id-checker/kyc/status", timeout=30)
        assert r.status_code in (401, 403), f"Expected auth required, got {r.status_code}"

    def test_kyc_status_returns_200_for_free_user(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/id-checker/kyc/status", timeout=30)
        assert r.status_code == 200
        d = r.json()
        # Top-level keys
        for k in ("kyc", "entitlements", "id_checker"):
            assert k in d, f"missing top-level key: {k}"

    def test_kyc_status_contains_timeline_with_milestones(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/id-checker/kyc/status", timeout=30)
        assert r.status_code == 200
        d = r.json()
        tl = d.get("id_checker", {}).get("timeline")
        assert isinstance(tl, dict), f"id_checker.timeline missing/not-dict: {type(tl).__name__}"
        # Required timeline keys
        for k in ("milestones", "eta_message", "owner_label", "current_handoff"):
            assert k in tl, f"timeline missing key: {k}"
        ms = tl["milestones"]
        assert isinstance(ms, list) and len(ms) > 0, "milestones must be non-empty list"
        first = ms[0]
        for k in ("state", "label", "status"):
            assert k in first, f"milestone missing key: {k}"

    def test_kyc_status_free_user_default_state(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/id-checker/kyc/status", timeout=30)
        d = r.json()
        tl = d["id_checker"]["timeline"]
        states = [m["state"] for m in tl["milestones"]]
        # Free user who has not submitted should include NOT_SUBMITTED milestone
        assert "NOT_SUBMITTED" in states, f"expected NOT_SUBMITTED in milestone states, got {states}"
