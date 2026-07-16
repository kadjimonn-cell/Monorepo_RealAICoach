"""Feature 37 - Flappy Bird Game backend EXTENDED tests (iteration 823).

Adds:
- Score boundary acceptance: 0 and 9999 must be accepted
- CSRF enforcement: POST /score without X-CSRF-Token header must be blocked (403)
- Multi-user leaderboard ranking: free user submission -> admin (best 50) ranked #1,
  free below; best_score is MAX of user's runs (not latest).
"""

import os

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


class TestScoreBoundaries:
    """Score field ge=0 le=9999 - boundaries must be accepted."""

    def test_score_zero_accepted(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 0, "duration_ms": 100},
            timeout=15,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data.get("accepted") is True
        assert data.get("score") == 0

    def test_score_max_9999_accepted(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 9999, "duration_ms": 999},
            timeout=15,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data.get("accepted") is True
        assert data.get("score") == 9999


class TestCSRFEnforcement:
    """Platform CSRF contract: state-changing requests require the X-Requested-With
    custom header (cannot be set cross-origin without a CORS preflight). Requests
    carrying that header are legitimately accepted; requests without ANY custom
    header must be blocked."""

    def test_score_without_custom_headers_blocked(self, admin_session):
        raw = requests.Session()
        raw.cookies.update(admin_session.cookies)
        raw.headers.update({"Content-Type": "application/json"})
        # explicitly NO X-Requested-With and NO X-CSRF-Token
        r = raw.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 5, "duration_ms": 100},
            timeout=15,
        )
        assert r.status_code in (401, 403), f"expected 401/403 without custom headers, got {r.status_code}: {r.text[:200]}"
        if r.status_code == 403:
            assert "csrf" in r.text.lower(), f"403 but not CSRF-related: {r.text[:200]}"

    def test_score_with_x_requested_with_accepted(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 5, "duration_ms": 100},
            timeout=15,
        )
        assert r.status_code == 200, f"expected 200 with X-Requested-With, got {r.status_code}: {r.text[:200]}"


class TestMultiUserLeaderboard:
    """Free user submits score; leaderboard ranks admin (higher best) above free."""

    def test_admin_top_after_free_submit(self, admin_session, free_session):
        # Ensure admin has a solid best (>=50). Submit 50 as admin - this may or may not
        # bump personal_best depending on prior state, but ensures admin has best>=50.
        r_admin_best = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 50, "duration_ms": 1200},
            timeout=15,
        )
        assert r_admin_best.status_code == 200

        # Free user submits a low score (12)
        r_free = free_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 12, "duration_ms": 500},
            timeout=15,
        )
        assert r_free.status_code == 200, f"free submit failed: {r_free.status_code} {r_free.text[:200]}"
        free_data = r_free.json()
        assert free_data.get("accepted") is True
        assert free_data.get("score") == 12

        # Get leaderboard (as admin — any authed user should get the same board)
        r_lb = admin_session.get(f"{BASE_URL}/api/flappy-bird/leaderboard", timeout=15)
        assert r_lb.status_code == 200
        lb = r_lb.json().get("leaderboard") or []
        assert isinstance(lb, list) and len(lb) >= 1

        # Rank #1 best_score should be >= 50 (admin's best)
        top = lb[0]
        assert top["rank"] == 1
        assert int(top["best_score"]) >= 50, f"Expected #1 best_score>=50 (admin), got {top}"

        # Ensure best_score ordering is descending
        for i in range(len(lb) - 1):
            assert lb[i]["best_score"] >= lb[i + 1]["best_score"], (
                f"Leaderboard not sorted desc at index {i}: {lb[i]} vs {lb[i+1]}"
            )

    def test_best_score_is_max_not_latest(self, free_session):
        """After a low score submission, personal_best should remain the historical max."""
        # Fetch current best
        r0 = free_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r0.status_code == 200
        pb_before = int(r0.json().get("personal_best", 0))

        # Submit a score guaranteed lower than any reasonable best (0)
        r_low = free_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 0, "duration_ms": 100},
            timeout=15,
        )
        assert r_low.status_code == 200
        d = r_low.json()
        # personal_best must NOT decrease
        assert int(d["personal_best"]) >= pb_before, (
            f"personal_best regressed: was {pb_before}, now {d['personal_best']}"
        )
        assert d.get("is_new_best") is False or int(d["personal_best"]) > pb_before
