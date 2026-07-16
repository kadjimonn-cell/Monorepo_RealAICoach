"""Personal AI Assistant v2 API Tests — Enterprise assistant workspace APIs."""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')
FALLBACK_USER_ID = f"user_test_pai_{int(time.time())}"

HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


class TestPersonalAssistantBootstrap:
    """Bootstrap endpoint tests — loads workspace state."""

    def test_bootstrap_returns_200_with_guest_id(self):
        """Bootstrap should return 200 with valid fallback_user_id."""
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={"fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "owner_id" in data
        assert "sessions" in data
        assert "actions" in data
        assert "memory_notes" in data
        assert "modes" in data
        assert "stats" in data
        
        # Verify modes list
        assert data["modes"] == ["planner", "executor", "coach", "critic"]
        
        # Verify stats structure
        assert "sessions_count" in data["stats"]
        assert "pending_actions" in data["stats"]
        assert "memory_count" in data["stats"]

    def test_bootstrap_requires_fallback_user_id(self):
        """Bootstrap should return 401 without fallback_user_id."""
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            timeout=15
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error_code"] == "assistant_auth_required"

    def test_bootstrap_rejects_invalid_guest_id_format(self):
        """Bootstrap should reject invalid fallback_user_id format."""
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={"fallback_user_id": "invalid"},
            timeout=15
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert data["detail"]["error_code"] == "assistant_invalid_guest_id"


class TestPersonalAssistantSessions:
    """Session CRUD tests."""

    def test_create_session_success(self):
        """Create session should return 200 with session object."""
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=HEADERS,
            json={"title": "Test Session Create", "fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "session" in data
        session = data["session"]
        
        assert "session_id" in session
        assert session["session_id"].startswith("pas_")
        assert session["title"] == "Test Session Create"
        assert session["owner_id"] == f"guest:{FALLBACK_USER_ID}"
        assert session["last_mode"] == "planner"
        assert session["message_count"] == 0

    def test_list_sessions_success(self):
        """List sessions should return sessions array."""
        # First create a session
        requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=HEADERS,
            json={"title": "List Test Session", "fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        
        # Then list sessions
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/sessions",
            params={"fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)
        assert len(data["sessions"]) >= 1

    def test_get_session_by_id(self):
        """Get session by ID should return session with messages."""
        # Create a session first
        create_response = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=HEADERS,
            json={"title": "Get Test Session", "fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        session_id = create_response.json()["session"]["session_id"]
        
        # Get the session
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}",
            params={"fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "session" in data
        assert "messages" in data
        assert data["session"]["session_id"] == session_id

    def test_get_nonexistent_session_returns_404(self):
        """Get nonexistent session should return 404."""
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/sessions/pas_nonexistent123",
            params={"fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestPersonalAssistantMessages:
    """Message sending tests."""

    @pytest.fixture
    def session_id(self):
        """Create a session for message tests."""
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=HEADERS,
            json={"title": "Message Test Session", "fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        return response.json()["session"]["session_id"]

    def test_send_message_success(self, session_id):
        """Send message should return user and assistant messages."""
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            headers=HEADERS,
            json={
                "content": "Help me plan my day",
                "mode": "planner",
                "fallback_user_id": FALLBACK_USER_ID,
                "idempotency_key": f"test_{int(time.time())}"
            },
            timeout=60  # LLM calls can take time
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user_message" in data
        assert "assistant_message" in data
        
        user_msg = data["user_message"]
        assert user_msg["role"] == "user"
        assert user_msg["content"] == "Help me plan my day"
        
        assistant_msg = data["assistant_message"]
        assert assistant_msg["role"] == "assistant"
        assert len(assistant_msg["content"]) > 0
        assert "quality" in assistant_msg

    def test_send_message_to_nonexistent_session_returns_404(self):
        """Send message to nonexistent session should return 404."""
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions/pas_nonexistent123/messages",
            headers=HEADERS,
            json={
                "content": "Test message",
                "mode": "planner",
                "fallback_user_id": FALLBACK_USER_ID
            },
            timeout=15
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    def test_send_message_with_different_modes(self, session_id):
        """Send message with different modes should work."""
        modes = ["planner", "executor", "coach", "critic"]
        
        for mode in modes:
            response = requests.post(
                f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
                headers=HEADERS,
                json={
                    "content": f"Test {mode} mode",
                    "mode": mode,
                    "fallback_user_id": FALLBACK_USER_ID,
                    "idempotency_key": f"test_{mode}_{int(time.time())}"
                },
                timeout=60
            )
            assert response.status_code == 200, f"Mode {mode} failed: {response.status_code}: {response.text}"
            
            data = response.json()
            assert data["assistant_message"]["mode"] == mode


class TestPersonalAssistantActions:
    """Action tracker tests."""

    def test_create_action_success(self):
        """Create action should return action object."""
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/actions",
            headers=HEADERS,
            json={
                "title": "Test Action Item",
                "due_hint": "today",
                "fallback_user_id": FALLBACK_USER_ID
            },
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "action" in data
        action = data["action"]
        
        assert "action_id" in action
        assert action["action_id"].startswith("act_")
        assert action["title"] == "Test Action Item"
        assert action["due_hint"] == "today"
        assert action["done"] is False

    def test_list_actions_success(self):
        """List actions should return actions array."""
        # Create an action first
        requests.post(
            f"{BASE_URL}/api/personal-assistant/actions",
            headers=HEADERS,
            json={
                "title": "List Test Action",
                "fallback_user_id": FALLBACK_USER_ID
            },
            timeout=15
        )
        
        # List actions
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/actions",
            params={"fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "actions" in data
        assert isinstance(data["actions"], list)
        assert len(data["actions"]) >= 1

    def test_toggle_action_done_status(self):
        """Toggle action done status should update action."""
        # Create an action
        create_response = requests.post(
            f"{BASE_URL}/api/personal-assistant/actions",
            headers=HEADERS,
            json={
                "title": "Toggle Test Action",
                "fallback_user_id": FALLBACK_USER_ID
            },
            timeout=15
        )
        action_id = create_response.json()["action"]["action_id"]
        
        # Toggle to done
        response = requests.patch(
            f"{BASE_URL}/api/personal-assistant/actions/{action_id}",
            headers=HEADERS,
            json={"done": True, "fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["action"]["done"] is True
        
        # Toggle back to not done
        response = requests.patch(
            f"{BASE_URL}/api/personal-assistant/actions/{action_id}",
            headers=HEADERS,
            json={"done": False, "fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 200
        assert response.json()["action"]["done"] is False

    def test_toggle_nonexistent_action_returns_404(self):
        """Toggle nonexistent action should return 404."""
        response = requests.patch(
            f"{BASE_URL}/api/personal-assistant/actions/act_nonexistent123",
            headers=HEADERS,
            json={"done": True, "fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestPersonalAssistantMemory:
    """Memory notes tests."""

    def test_add_memory_note_success(self):
        """Add memory note should return note object."""
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/memory",
            headers=HEADERS,
            json={
                "note": "I prefer concise responses",
                "fallback_user_id": FALLBACK_USER_ID
            },
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "note" in data
        note = data["note"]
        
        assert "note_id" in note
        assert note["note_id"].startswith("mem_")
        assert note["note"] == "I prefer concise responses"

    def test_memory_notes_appear_in_bootstrap(self):
        """Memory notes should appear in bootstrap response."""
        # Add a memory note
        requests.post(
            f"{BASE_URL}/api/personal-assistant/memory",
            headers=HEADERS,
            json={
                "note": "Bootstrap test memory note",
                "fallback_user_id": FALLBACK_USER_ID
            },
            timeout=15
        )
        
        # Check bootstrap
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={"fallback_user_id": FALLBACK_USER_ID},
            timeout=15
        )
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["memory_notes"]) >= 1
        notes = [n["note"] for n in data["memory_notes"]]
        assert "Bootstrap test memory note" in notes


class TestPersonalAssistantDailyBrief:
    """Daily brief generation tests."""

    def test_generate_daily_brief_success(self):
        """Generate daily brief should return brief content."""
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/daily-brief",
            headers=HEADERS,
            params={"fallback_user_id": FALLBACK_USER_ID},
            timeout=60  # LLM calls can take time
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "daily_brief" in data
        brief = data["daily_brief"]
        
        assert "brief_id" in brief
        assert brief["brief_id"].startswith("brief_")
        assert "content" in brief
        assert len(brief["content"]) > 0


class TestPersonalAssistantPublicAccess:
    """Verify personal assistant is in public API contract."""

    def test_personal_assistant_in_public_prefixes(self):
        """Personal assistant should be accessible without auth via fallback_user_id."""
        # This test verifies the endpoint is publicly accessible
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={"fallback_user_id": "user_public_test_12345678"},
            timeout=15
        )
        # Should not return 403 (forbidden) - should be 200 or 401 (if no fallback_user_id)
        assert response.status_code == 200, f"Expected 200 for public access, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
