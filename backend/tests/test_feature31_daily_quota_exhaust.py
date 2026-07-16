"""Free-tier daily quota exhaustion test for AI Coaching Team.

Sends messages until 429 DAILY_LIMIT_REACHED. Uses one-word prompts to save LLM
budget. Skips if the user has already been reset / has a burdensome start point.
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASS = "P1Free#2026!Aa"
CSRF = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(CSRF)
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": FREE_EMAIL, "password": FREE_PASS}, timeout=30)
    assert r.status_code == 200
    return s


def test_daily_quota_reaches_429(free_session):
    status = free_session.get(f"{BASE_URL}/api/ai-coaching-team/status", timeout=15).json()
    remaining = status["remaining_today"]
    assert status["daily_limit"] == 5

    # create a session
    r = free_session.post(
        f"{BASE_URL}/api/ai-coaching-team/sessions",
        json={"coach_key": "career_coach"}, timeout=20,
    )
    assert r.status_code == 200
    sid = r.json()["session_id"]

    # Send up to `remaining` messages (each should succeed)
    saw_429 = False
    attempts = 0
    max_attempts = remaining + 2  # +2 safety net to bump into 429
    while attempts < max_attempts:
        r = free_session.post(
            f"{BASE_URL}/api/ai-coaching-team/sessions/{sid}/message",
            json={"message": "tip?"}, timeout=90,
        )
        attempts += 1
        if r.status_code == 429:
            detail = r.json().get("detail", {})
            assert detail.get("code") == "DAILY_LIMIT_REACHED"
            assert detail.get("upgrade_route") == "/subscription/plans"
            saw_429 = True
            break
        assert r.status_code == 200, f"unexpected {r.status_code}: {r.text[:200]}"

    assert saw_429, f"Never hit 429 after {attempts} attempts (remaining_before={remaining})"

    # cleanup
    free_session.delete(f"{BASE_URL}/api/ai-coaching-team/sessions/{sid}", timeout=15)
