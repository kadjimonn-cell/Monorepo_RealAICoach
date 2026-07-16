"""Personal AI Assistant v2 - Backend API Tests

Tests all core endpoints:
- Bootstrap (GET /personal-assistant/bootstrap)
- Sessions CRUD (POST/GET /personal-assistant/sessions)
- Messages (POST /personal-assistant/sessions/{id}/messages)
- Actions (POST/PATCH/GET /personal-assistant/actions)
- Memory (POST /personal-assistant/memory)
- Daily Brief (POST /personal-assistant/daily-brief)
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)

# Required headers for CSRF protection on POST/PATCH requests
CSRF_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


def generate_guest_id(purpose: str = "test") -> str:
    """Generate a valid guest user ID for testing."""
    return f"user_{purpose}_{uuid.uuid4().hex[:16]}"


class TestPersonalAssistantBootstrap:
    """Bootstrap endpoint tests"""

    def test_bootstrap_returns_200_with_guest_id(self):
        guest_id = generate_guest_id("bootstrap")
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={"fallback_user_id": guest_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert "owner_id" in data
        assert "sessions" in data
        assert "actions" in data
        assert "memory_notes" in data
        assert "modes" in data
        assert "stats" in data
        assert data["owner_id"] == f"guest:{guest_id}"
        assert isinstance(data["modes"], list)
        assert "planner" in data["modes"]

    def test_bootstrap_requires_auth_or_fallback_id(self):
        response = requests.get(f"{BASE_URL}/api/personal-assistant/bootstrap")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error_code"] == "assistant_auth_required"

    def test_bootstrap_rejects_invalid_guest_id_format(self):
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={"fallback_user_id": "invalid-format"}
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error_code"] == "assistant_invalid_guest_id"


class TestPersonalAssistantSessions:
    """Session CRUD tests"""

    def test_create_session_success(self):
        guest_id = generate_guest_id("session_create")
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=CSRF_HEADERS,
            json={
                "title": "Test Session for API Validation",
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "session" in data
        session = data["session"]
        assert "session_id" in session
        assert session["session_id"].startswith("pas_")
        assert session["title"] == "Test Session for API Validation"
        assert session["owner_id"] == f"guest:{guest_id}"
        assert session["message_count"] == 0
        assert session["last_mode"] == "planner"

    def test_list_sessions_success(self):
        guest_id = generate_guest_id("session_list")
        # Create a session first
        requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=CSRF_HEADERS,
            json={"title": "List Test Session", "fallback_user_id": guest_id}
        )
        # List sessions
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/sessions",
            params={"fallback_user_id": guest_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert len(data["sessions"]) >= 1

    def test_get_session_success(self):
        guest_id = generate_guest_id("session_get")
        # Create session
        create_resp = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=CSRF_HEADERS,
            json={"title": "Get Test Session", "fallback_user_id": guest_id}
        )
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session"]["session_id"]
        
        # Get session
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}",
            params={"fallback_user_id": guest_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert "session" in data
        assert "messages" in data
        assert data["session"]["session_id"] == session_id

    def test_get_session_not_found(self):
        guest_id = generate_guest_id("session_notfound")
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/sessions/pas_nonexistent123",
            params={"fallback_user_id": guest_id}
        )
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_code"] == "assistant_session_not_found"


class TestPersonalAssistantMessages:
    """Message send tests - skipped due to AI response time"""

    @pytest.mark.skip(reason="AI response generation takes too long for CI")
    def test_send_message_success(self):
        guest_id = generate_guest_id("message_send")
        # Create session
        create_resp = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=CSRF_HEADERS,
            json={"title": "Message Test Session", "fallback_user_id": guest_id}
        )
        session_id = create_resp.json()["session"]["session_id"]
        
        # Send message
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            headers=CSRF_HEADERS,
            json={
                "content": "Help me plan my day",
                "mode": "planner",
                "fallback_user_id": guest_id,
                "idempotency_key": f"{session_id}:test123"
            },
            timeout=60  # AI response may take time
        )
        assert response.status_code == 200
        data = response.json()
        assert "user_message" in data
        assert "assistant_message" in data
        assert data["user_message"]["role"] == "user"
        assert data["assistant_message"]["role"] == "assistant"
        assert "quality" in data["assistant_message"]
        assert "content" in data["assistant_message"]

    def test_send_message_to_nonexistent_session(self):
        guest_id = generate_guest_id("message_nosession")
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions/pas_nonexistent123/messages",
            headers=CSRF_HEADERS,
            json={
                "content": "Test message",
                "mode": "planner",
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_code"] == "assistant_session_not_found"


class TestPersonalAssistantActions:
    """Action tracker tests"""

    def test_create_action_success(self):
        guest_id = generate_guest_id("action_create")
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/actions",
            headers=CSRF_HEADERS,
            json={
                "title": "Complete API testing",
                "due_hint": "Today",
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "action" in data
        action = data["action"]
        assert action["action_id"].startswith("act_")
        assert action["title"] == "Complete API testing"
        assert action["due_hint"] == "Today"
        assert action["done"] is False

    def test_toggle_action_success(self):
        guest_id = generate_guest_id("action_toggle")
        # Create action
        create_resp = requests.post(
            f"{BASE_URL}/api/personal-assistant/actions",
            headers=CSRF_HEADERS,
            json={"title": "Toggle Test Action", "fallback_user_id": guest_id}
        )
        assert create_resp.status_code == 200
        action_id = create_resp.json()["action"]["action_id"]
        
        # Toggle to done
        response = requests.patch(
            f"{BASE_URL}/api/personal-assistant/actions/{action_id}",
            headers=CSRF_HEADERS,
            json={"done": True, "fallback_user_id": guest_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["action"]["done"] is True
        
        # Toggle back to not done
        response = requests.patch(
            f"{BASE_URL}/api/personal-assistant/actions/{action_id}",
            headers=CSRF_HEADERS,
            json={"done": False, "fallback_user_id": guest_id}
        )
        assert response.status_code == 200
        assert response.json()["action"]["done"] is False

    def test_list_actions_success(self):
        guest_id = generate_guest_id("action_list")
        # Create action
        requests.post(
            f"{BASE_URL}/api/personal-assistant/actions",
            headers=CSRF_HEADERS,
            json={"title": "List Test Action", "fallback_user_id": guest_id}
        )
        # List actions
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/actions",
            params={"fallback_user_id": guest_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert "actions" in data
        assert len(data["actions"]) >= 1

    def test_toggle_nonexistent_action(self):
        guest_id = generate_guest_id("action_notfound")
        response = requests.patch(
            f"{BASE_URL}/api/personal-assistant/actions/act_nonexistent123",
            headers=CSRF_HEADERS,
            json={"done": True, "fallback_user_id": guest_id}
        )
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error_code"] == "assistant_action_not_found"


class TestPersonalAssistantMemory:
    """Memory notes tests"""

    def test_add_memory_note_success(self):
        guest_id = generate_guest_id("memory_add")
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/memory",
            headers=CSRF_HEADERS,
            json={
                "note": "Prefer concise responses with action items",
                "fallback_user_id": guest_id
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "note" in data
        note = data["note"]
        assert note["note_id"].startswith("mem_")
        assert note["note"] == "Prefer concise responses with action items"
        assert "created_at" in note


class TestPersonalAssistantDailyBrief:
    """Daily brief generation tests - skipped due to AI response time"""

    @pytest.mark.skip(reason="AI response generation takes too long for CI")
    def test_generate_daily_brief_success(self):
        guest_id = generate_guest_id("brief_gen")
        # Create some context first
        requests.post(
            f"{BASE_URL}/api/personal-assistant/actions",
            headers=CSRF_HEADERS,
            json={"title": "Review project status", "fallback_user_id": guest_id}
        )
        
        # Generate brief
        response = requests.post(
            f"{BASE_URL}/api/personal-assistant/daily-brief",
            headers=CSRF_HEADERS,
            params={"fallback_user_id": guest_id},
            timeout=60  # AI response may take time
        )
        assert response.status_code == 200
        data = response.json()
        assert "daily_brief" in data
        brief = data["daily_brief"]
        assert brief["brief_id"].startswith("brief_")
        assert "content" in brief
        assert len(brief["content"]) > 0


class TestPersonalAssistantOwnerIsolation:
    """Owner isolation tests"""

    def test_session_owner_isolation(self):
        guest_id_1 = generate_guest_id("owner1")
        guest_id_2 = generate_guest_id("owner2")
        
        # Create session for user 1
        create_resp = requests.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers=CSRF_HEADERS,
            json={"title": "User 1 Session", "fallback_user_id": guest_id_1}
        )
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session"]["session_id"]
        
        # User 2 should not be able to access user 1's session
        response = requests.get(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}",
            params={"fallback_user_id": guest_id_2}
        )
        assert response.status_code == 404

    def test_action_owner_isolation(self):
        guest_id_1 = generate_guest_id("actionowner1")
        guest_id_2 = generate_guest_id("actionowner2")
        
        # Create action for user 1
        create_resp = requests.post(
            f"{BASE_URL}/api/personal-assistant/actions",
            headers=CSRF_HEADERS,
            json={"title": "User 1 Action", "fallback_user_id": guest_id_1}
        )
        assert create_resp.status_code == 200
        action_id = create_resp.json()["action"]["action_id"]
        
        # User 2 should not be able to toggle user 1's action
        response = requests.patch(
            f"{BASE_URL}/api/personal-assistant/actions/{action_id}",
            headers=CSRF_HEADERS,
            json={"done": True, "fallback_user_id": guest_id_2}
        )
        assert response.status_code == 404


class TestPersonalAssistantPublicAPIContract:
    """Public API contract verification"""

    def test_personal_assistant_in_public_prefixes(self):
        from pathlib import Path
        contract_path = Path('/app/backend/utils/public_api_contract.py')
        source = contract_path.read_text()
        assert '"/api/personal-assistant/"' in source


class TestPersonalAssistantAccessControl:
    """Access control engine verification"""

    def test_personal_assistant_in_free_patterns(self):
        from pathlib import Path
        ace_path = Path('/app/backend/utils/access_control_engine.py')
        source = ace_path.read_text()
        assert 'r"^/api/personal-assistant/"' in source
