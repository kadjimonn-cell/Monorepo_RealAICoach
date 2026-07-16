"""End-to-end HTTP tests for Feature 31 replacement (AI Coaching Team).

Covers:
- Legacy retirement endpoints (410 payload for authed user)
- New API surface (/api/ai-coaching-team/*) - coach list, status, tier gating,
  chat flow with memory, session isolation between users, and daily quota.

NOTE:
- Uses cookie-session auth via /api/auth/login (session cookie set on session).
- CSRF: POST/PUT/DELETE include X-Requested-With: XMLHttpRequest.
- LLM calls kept short (single-word / one-line prompts) to control budget.
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASS = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASS = "NewAdminPass2026!"

CSRF = {"X-Requested-With": "XMLHttpRequest"}


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(CSRF)
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    return _login(FREE_EMAIL, FREE_PASS)


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASS)


# --- Retirement (410) ---------------------------------------------------------

class TestRetirement:
    def test_ai_solver_categories_returns_410(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/ai-solver/categories", timeout=15)
        assert r.status_code == 410, r.text[:300]
        detail = r.json().get("detail", {})
        assert detail.get("retired") is True
        assert detail.get("feature") == "ai-problem-solver"
        assert detail.get("replacement_feature") == "ai-coaching-team"
        assert detail.get("replacement_route") == "/ai-coaching-team"
        assert detail.get("replacement_api") == "/api/ai-coaching-team"

    def test_ai_problem_solver_sessions_get_returns_410(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/ai-problem-solver/sessions", timeout=15)
        assert r.status_code == 410, r.text[:300]
        assert r.json().get("detail", {}).get("retired") is True

    def test_ai_problem_solver_sessions_post_returns_410(self, free_session):
        r = free_session.post(
            f"{BASE_URL}/api/ai-problem-solver/sessions", json={"foo": "bar"}, timeout=15
        )
        assert r.status_code == 410, r.text[:300]
        assert r.json().get("detail", {}).get("replacement_api") == "/api/ai-coaching-team"


# --- Unauth guard -------------------------------------------------------------

def test_unauth_coaches_returns_401():
    r = requests.get(f"{BASE_URL}/api/ai-coaching-team/coaches", timeout=15)
    assert r.status_code == 401, r.text[:200]


# --- Free-tier surface --------------------------------------------------------

class TestFreeCoachesAndStatus:
    def test_coaches_free_user(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/ai-coaching-team/coaches", timeout=15)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert data.get("tier") == "free"
        assert data.get("all_coaches_unlocked") is False
        coaches = data.get("coaches") or []
        assert len(coaches) == 4, f"expected 4 coaches, got {len(coaches)}"
        keys = {c["coach_key"]: c for c in coaches}
        assert set(keys.keys()) == {"career_coach", "interview_coach", "resume_specialist", "negotiation_coach"}
        assert keys["career_coach"]["available"] is True
        for locked in ("interview_coach", "resume_specialist", "negotiation_coach"):
            assert keys[locked]["available"] is False, f"{locked} should be locked for free"

    def test_status_free_user(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/ai-coaching-team/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["tier"] == "free"
        assert data["daily_limit"] == 5
        assert data["all_coaches_unlocked"] is False
        assert isinstance(data["used_today"], int) and data["used_today"] >= 0
        assert data["remaining_today"] == max(0, 5 - data["used_today"])


# --- Tier gating --------------------------------------------------------------

class TestTierGating:
    def test_free_cannot_start_locked_coach(self, free_session):
        r = free_session.post(
            f"{BASE_URL}/api/ai-coaching-team/sessions",
            json={"coach_key": "negotiation_coach"}, timeout=15,
        )
        assert r.status_code == 402, r.text[:300]
        detail = r.json().get("detail", {})
        assert detail.get("code") == "COACH_LOCKED"
        assert detail.get("upgrade_route") == "/subscription/plans"

    def test_bogus_coach_returns_400(self, free_session):
        r = free_session.post(
            f"{BASE_URL}/api/ai-coaching-team/sessions",
            json={"coach_key": "bogus"}, timeout=15,
        )
        assert r.status_code == 400, r.text[:300]


# --- Chat flow / memory / isolation ------------------------------------------

class TestChatFlow:
    session_id = None  # class-level share

    def test_create_session_career_coach(self, free_session):
        r = free_session.post(
            f"{BASE_URL}/api/ai-coaching-team/sessions",
            json={"coach_key": "career_coach"}, timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["coach_key"] == "career_coach"
        assert data["session_id"]
        TestChatFlow.session_id = data["session_id"]

    def test_send_message_and_decrement(self, free_session):
        assert TestChatFlow.session_id, "session missing from prior test"
        # snapshot remaining before
        s_before = free_session.get(f"{BASE_URL}/api/ai-coaching-team/status", timeout=15).json()
        rem_before = s_before["remaining_today"]
        if rem_before == 0:
            pytest.skip("Daily quota already exhausted; cannot test message decrement")
        r = free_session.post(
            f"{BASE_URL}/api/ai-coaching-team/sessions/{TestChatFlow.session_id}/message",
            json={"message": "One tip for a junior PM interview?"}, timeout=90,
        )
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert isinstance(data.get("reply"), str) and len(data["reply"]) > 5
        assert data["remaining_today"] == max(0, rem_before - 1)

    def test_get_session_shows_messages(self, free_session):
        assert TestChatFlow.session_id
        r = free_session.get(
            f"{BASE_URL}/api/ai-coaching-team/sessions/{TestChatFlow.session_id}", timeout=15
        )
        assert r.status_code == 200
        data = r.json()
        msgs = data.get("messages") or []
        # Should have at least the first user + assistant pair
        assert len(msgs) >= 2, f"expected >=2 messages, got {len(msgs)}"
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_memory_recall_second_message(self, free_session):
        assert TestChatFlow.session_id
        s = free_session.get(f"{BASE_URL}/api/ai-coaching-team/status", timeout=15).json()
        if s["remaining_today"] == 0:
            pytest.skip("Daily quota exhausted before memory recall test")
        r = free_session.post(
            f"{BASE_URL}/api/ai-coaching-team/sessions/{TestChatFlow.session_id}/message",
            json={"message": "What did I just ask you?"}, timeout=90,
        )
        assert r.status_code == 200, r.text[:300]
        reply = (r.json().get("reply") or "").lower()
        # Loose signal: mentions interview / pm / tip / junior — anything recall-like
        assert any(k in reply for k in ("interview", "pm", "junior", "tip", "you asked", "product manager"))

    def test_session_lists_and_isolation(self, free_session, admin_session):
        assert TestChatFlow.session_id
        r = free_session.get(f"{BASE_URL}/api/ai-coaching-team/sessions", timeout=15)
        assert r.status_code == 200
        ids = [s["session_id"] for s in (r.json().get("sessions") or [])]
        assert TestChatFlow.session_id in ids

        # Admin cannot fetch the free user's session — must 404
        r2 = admin_session.get(
            f"{BASE_URL}/api/ai-coaching-team/sessions/{TestChatFlow.session_id}", timeout=15
        )
        assert r2.status_code == 404, r2.text[:200]

    def test_delete_session(self, free_session):
        assert TestChatFlow.session_id
        r = free_session.delete(
            f"{BASE_URL}/api/ai-coaching-team/sessions/{TestChatFlow.session_id}", timeout=15
        )
        assert r.status_code == 200
        assert r.json().get("deleted") is True
        r2 = free_session.get(
            f"{BASE_URL}/api/ai-coaching-team/sessions/{TestChatFlow.session_id}", timeout=15
        )
        assert r2.status_code == 404


# --- Admin/premium ------------------------------------------------------------

class TestAdminPremium:
    def test_admin_coaches_all_available(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/ai-coaching-team/coaches", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["all_coaches_unlocked"] is True
        assert data["tier"] == "premium"
        for c in data["coaches"]:
            assert c["available"] is True, f"{c['coach_key']} should be available for admin"

    def test_admin_status_unlimited(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/ai-coaching-team/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["daily_limit"] == -1
        assert data["remaining_today"] == -1
        assert data["all_coaches_unlocked"] is True
