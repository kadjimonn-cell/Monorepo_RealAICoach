"""Tests for Anthropic Claude models integration in the Personal AI Assistant chat.

Covers:
- GET /api/personal-assistant/models — returns default and 3 models
- POST /api/personal-assistant/sessions and send messages with claude-sonnet-4-6 / claude-haiku-4-5
- Invalid & omitted model fields fallback to gpt-4o
- Message history projection includes model_label on assistant messages
"""
import os
import pytest
import requests

BASE_URL = "http://localhost:8001"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    r = s.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_EMAIL,
        "password": FREE_PASSWORD,
    }, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    return s


# ----- GET /models -----
class TestChatModelsCatalog:
    def test_models_endpoint(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/personal-assistant/models", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["default"] == "gpt-4o"
        keys = {m["key"] for m in data["models"]}
        assert keys == {"gpt-4o", "claude-sonnet-4-6", "claude-haiku-4-5"}
        by_key = {m["key"]: m for m in data["models"]}
        assert by_key["claude-sonnet-4-6"]["provider"] == "anthropic"
        assert by_key["claude-sonnet-4-6"]["label"] == "Claude Sonnet 4.6"
        assert by_key["claude-haiku-4-5"]["provider"] == "anthropic"
        assert by_key["claude-haiku-4-5"]["label"] == "Claude Haiku 4.5"
        assert by_key["gpt-4o"]["provider"] == "openai"
        for m in data["models"]:
            assert "description" in m and m["description"]


# ----- Send message with each model -----
@pytest.fixture(scope="module")
def session_id(auth_session):
    r = auth_session.post(f"{BASE_URL}/api/personal-assistant/sessions", json={
        "title": "TEST_claude_models_session",
    }, timeout=15)
    assert r.status_code == 200, r.text[:200]
    sid = r.json()["session"]["session_id"]
    yield sid
    # cleanup best-effort (delete endpoint uses different collection, but ignore failures)
    try:
        auth_session.delete(f"{BASE_URL}/api/personal-assistant/sessions/{sid}", timeout=10)
    except Exception:
        pass


class TestSendMessageModels:
    def test_send_with_claude_sonnet(self, auth_session, session_id):
        r = auth_session.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            json={
                "content": "Reply with exactly: SONNET OK",
                "mode": "planner",
                "model": "claude-sonnet-4-6",
            },
            timeout=90,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        am = r.json()["assistant_message"]
        assert am["model"] == "claude-sonnet-4-6"
        assert am["model_label"] == "Claude Sonnet 4.6"
        assert am["provider"] == "anthropic"
        assert isinstance(am["content"], str) and len(am["content"]) > 0

    def test_send_with_claude_haiku(self, auth_session, session_id):
        r = auth_session.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            json={
                "content": "Reply with exactly: HAIKU OK",
                "mode": "planner",
                "model": "claude-haiku-4-5",
            },
            timeout=90,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        am = r.json()["assistant_message"]
        assert am["model"] == "claude-haiku-4-5"
        assert am["model_label"] == "Claude Haiku 4.5"
        assert am["provider"] == "anthropic"
        assert isinstance(am["content"], str) and len(am["content"]) > 0

    def test_invalid_model_falls_back_to_gpt4o(self, auth_session, session_id):
        r = auth_session.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            json={
                "content": "One-word reply: ok",
                "mode": "planner",
                "model": "bogus-x",
            },
            timeout=90,
        )
        assert r.status_code == 200, r.text[:400]
        am = r.json()["assistant_message"]
        assert am["model"] == "gpt-4o"
        assert am["provider"] == "openai"

    def test_omitted_model_defaults_to_gpt4o(self, auth_session, session_id):
        r = auth_session.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            json={
                "content": "One-word reply: yes",
                "mode": "planner",
            },
            timeout=90,
        )
        assert r.status_code == 200, r.text[:400]
        am = r.json()["assistant_message"]
        assert am["model"] == "gpt-4o"
        assert am["model_label"] == "GPT-4o"


# ----- Message history includes model_label -----
class TestMessageHistoryProjection:
    def test_history_includes_model_label(self, auth_session, session_id):
        r = auth_session.get(f"{BASE_URL}/api/personal-assistant/sessions/{session_id}", timeout=15)
        assert r.status_code == 200, r.text[:300]
        messages = r.json()["messages"]
        # There should be at least one assistant message w/ model_label
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        assert len(assistant_msgs) >= 1
        labels = {m.get("model_label") for m in assistant_msgs}
        assert any(lbl in {"Claude Sonnet 4.6", "Claude Haiku 4.5", "GPT-4o"} for lbl in labels)
