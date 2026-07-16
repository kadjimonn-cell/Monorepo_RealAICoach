"""
Nova AI Assistant - Favorites & Pins Backend Tests
Tests for: /api/support/chat/messages/favorite, /api/support/chat/conversations/pin
All endpoints require authentication and enforce conversation ownership.
Features: assistant_message_id in responses, favorite/unfavorite, pin/unpin, list favorites/pins
"""

import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
TEST_USER_EMAIL = "nova.v2.1779074133@example.com"
TEST_USER_PASSWORD = "NovaV2#2026!Aa"


class TestNovaFavoritesPinsAuthRequired:
    """Verify favorites/pins endpoints require authentication"""

    def test_favorite_post_requires_auth(self):
        """POST /api/support/chat/messages/favorite should return 401 without auth"""
        response = requests.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={"conversation_id": "test", "message_id": "test"},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: POST /api/support/chat/messages/favorite requires authentication")

    def test_favorite_delete_requires_auth(self):
        """DELETE /api/support/chat/messages/favorite should return 401 without auth"""
        response = requests.delete(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={"conversation_id": "test", "message_id": "test"},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: DELETE /api/support/chat/messages/favorite requires authentication")

    def test_favorites_list_requires_auth(self):
        """GET /api/support/chat/messages/favorites should return 401 without auth"""
        response = requests.get(
            f"{BASE_URL}/api/support/chat/messages/favorites",
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: GET /api/support/chat/messages/favorites requires authentication")

    def test_pin_post_requires_auth(self):
        """POST /api/support/chat/conversations/pin should return 401 without auth"""
        response = requests.post(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": "test"},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: POST /api/support/chat/conversations/pin requires authentication")

    def test_pin_delete_requires_auth(self):
        """DELETE /api/support/chat/conversations/pin should return 401 without auth"""
        response = requests.delete(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": "test"},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: DELETE /api/support/chat/conversations/pin requires authentication")

    def test_pins_list_requires_auth(self):
        """GET /api/support/chat/conversations/pins should return 401 without auth"""
        response = requests.get(
            f"{BASE_URL}/api/support/chat/conversations/pins",
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: GET /api/support/chat/conversations/pins requires authentication")


class TestNovaAssistantMessageId:
    """Test that assistant_message_id is returned in chat responses"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Login and get authenticated session"""
        session = requests.Session()
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        # Register (may already exist)
        session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD, "name": "Nova Test User"},
            timeout=15
        )
        
        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            timeout=15
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        
        return session

    def test_chat_returns_assistant_message_id(self, auth_session):
        """POST /api/support/chat should return assistant_message_id"""
        conversation_id = f"test-msgid-{uuid.uuid4().hex[:8]}"
        
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Hello Nova, test message", "conversation_id": conversation_id},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "assistant_message_id" in data, "Response should contain 'assistant_message_id'"
        assert data["assistant_message_id"].startswith("nm_"), f"assistant_message_id should start with 'nm_', got {data['assistant_message_id']}"
        
        print(f"PASS: Chat returns assistant_message_id: {data['assistant_message_id']}")
        return {"conversation_id": conversation_id, "assistant_message_id": data["assistant_message_id"]}

    def test_attachment_returns_assistant_message_id(self, auth_session):
        """POST /api/support/chat/attachment should return assistant_message_id"""
        conversation_id = f"test-attach-msgid-{uuid.uuid4().hex[:8]}"
        
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat/attachment",
            data={"conversation_id": conversation_id, "message": "Analyze this"},
            files={"file": ("test.txt", b"Test content for analysis", "text/plain")},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "assistant_message_id" in data, "Attachment response should contain 'assistant_message_id'"
        assert data["assistant_message_id"].startswith("nm_"), "assistant_message_id should start with 'nm_'"
        
        print(f"PASS: Attachment returns assistant_message_id: {data['assistant_message_id']}")


class TestNovaFavoritesFlow:
    """Test favorites CRUD operations"""

    @pytest.fixture(scope="class")
    def auth_session_with_message(self):
        """Login and create a conversation with assistant message"""
        session = requests.Session()
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        # Register/login
        session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD, "name": "Nova Test User"},
            timeout=15
        )
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            timeout=15
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        # Create a conversation with assistant message
        conversation_id = f"test-fav-{uuid.uuid4().hex[:8]}"
        chat_response = session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Hello Nova, give me a helpful tip", "conversation_id": conversation_id},
            timeout=30
        )
        
        if chat_response.status_code != 200:
            pytest.skip(f"Chat failed: {chat_response.status_code}")
        
        chat_data = chat_response.json()
        assistant_message_id = chat_data.get("assistant_message_id")
        
        if not assistant_message_id:
            pytest.skip("No assistant_message_id in chat response")
        
        return {
            "session": session,
            "conversation_id": conversation_id,
            "assistant_message_id": assistant_message_id
        }

    def test_favorite_assistant_message(self, auth_session_with_message):
        """POST /api/support/chat/messages/favorite should favorite an assistant message"""
        session = auth_session_with_message["session"]
        conversation_id = auth_session_with_message["conversation_id"]
        message_id = auth_session_with_message["assistant_message_id"]
        
        response = session.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={"conversation_id": conversation_id, "message_id": message_id},
            timeout=15
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("success"), "Favorite should succeed"
        assert "favorite" in data, "Response should contain 'favorite' object"
        
        favorite = data["favorite"]
        assert favorite.get("message_id") == message_id, "Favorite should have correct message_id"
        assert favorite.get("conversation_id") == conversation_id, "Favorite should have correct conversation_id"
        
        print(f"PASS: Favorited message: {message_id}")

    def test_list_favorites(self, auth_session_with_message):
        """GET /api/support/chat/messages/favorites should list user's favorites"""
        session = auth_session_with_message["session"]
        conversation_id = auth_session_with_message["conversation_id"]
        
        response = session.get(
            f"{BASE_URL}/api/support/chat/messages/favorites?conversation_id={conversation_id}",
            timeout=15
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "favorites" in data, "Response should contain 'favorites' list"
        assert isinstance(data["favorites"], list), "favorites should be a list"
        assert len(data["favorites"]) >= 1, "Should have at least 1 favorite"
        
        print(f"PASS: Listed {len(data['favorites'])} favorites")

    def test_unfavorite_message(self, auth_session_with_message):
        """DELETE /api/support/chat/messages/favorite should unfavorite a message"""
        session = auth_session_with_message["session"]
        conversation_id = auth_session_with_message["conversation_id"]
        message_id = auth_session_with_message["assistant_message_id"]
        
        response = session.delete(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={"conversation_id": conversation_id, "message_id": message_id},
            timeout=15
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("success"), "Unfavorite should succeed"
        
        print(f"PASS: Unfavorited message: {message_id}")

    def test_favorite_user_message_rejected(self, auth_session_with_message):
        """POST /api/support/chat/messages/favorite should reject user messages"""
        session = auth_session_with_message["session"]
        conversation_id = auth_session_with_message["conversation_id"]
        
        # Try to favorite a non-existent or user message
        response = session.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={"conversation_id": conversation_id, "message_id": "fake_user_message_id"},
            timeout=15
        )
        
        # Should return 404 because the message doesn't exist or isn't an assistant message
        assert response.status_code == 404, f"Expected 404 for invalid message, got {response.status_code}"
        
        print("PASS: Invalid/user message favorite correctly rejected")


class TestNovaPinsFlow:
    """Test conversation pins CRUD operations"""

    @pytest.fixture(scope="class")
    def auth_session_with_conversation(self):
        """Login and create a conversation"""
        session = requests.Session()
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        # Register/login
        session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD, "name": "Nova Test User"},
            timeout=15
        )
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            timeout=15
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        # Create a conversation
        conversation_id = f"test-pin-{uuid.uuid4().hex[:8]}"
        chat_response = session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Hello Nova, this is a conversation to pin", "conversation_id": conversation_id},
            timeout=30
        )
        
        if chat_response.status_code != 200:
            pytest.skip(f"Chat failed: {chat_response.status_code}")
        
        return {"session": session, "conversation_id": conversation_id}

    def test_pin_conversation(self, auth_session_with_conversation):
        """POST /api/support/chat/conversations/pin should pin a conversation"""
        session = auth_session_with_conversation["session"]
        conversation_id = auth_session_with_conversation["conversation_id"]
        
        response = session.post(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": conversation_id},
            timeout=15
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("success"), "Pin should succeed"
        
        print(f"PASS: Pinned conversation: {conversation_id}")

    def test_list_pins(self, auth_session_with_conversation):
        """GET /api/support/chat/conversations/pins should list user's pinned conversations"""
        session = auth_session_with_conversation["session"]
        
        response = session.get(
            f"{BASE_URL}/api/support/chat/conversations/pins",
            timeout=15
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "pins" in data, "Response should contain 'pins' list"
        assert isinstance(data["pins"], list), "pins should be a list"
        assert len(data["pins"]) >= 1, "Should have at least 1 pin"
        
        # Verify pin structure
        pin = data["pins"][0]
        assert "conversation_id" in pin, "Pin should have conversation_id"
        assert "preview" in pin, "Pin should have preview"
        
        print(f"PASS: Listed {len(data['pins'])} pinned conversations")

    def test_unpin_conversation(self, auth_session_with_conversation):
        """DELETE /api/support/chat/conversations/pin should unpin a conversation"""
        session = auth_session_with_conversation["session"]
        conversation_id = auth_session_with_conversation["conversation_id"]
        
        response = session.delete(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": conversation_id},
            timeout=15
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("success"), "Unpin should succeed"
        
        print(f"PASS: Unpinned conversation: {conversation_id}")


class TestNovaFavoritesPinsOwnership:
    """Test ownership enforcement for favorites and pins"""

    @pytest.fixture(scope="class")
    def two_users_with_conversation(self):
        """Create two users, one with a conversation"""
        sessions = {}
        
        # Create owner user
        owner_email = f"owner.{int(time.time())}@example.com"
        owner_session = requests.Session()
        owner_session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        owner_session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": owner_email, "password": "NovaV2#2026!Aa", "name": "Owner User"},
            timeout=15
        )
        
        login_resp = owner_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": owner_email, "password": "NovaV2#2026!Aa"},
            timeout=15
        )
        
        if login_resp.status_code != 200:
            pytest.skip("Could not create owner user")
        
        # Create conversation
        conversation_id = f"ownership-test-{uuid.uuid4().hex[:8]}"
        chat_resp = owner_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Owner's conversation", "conversation_id": conversation_id},
            timeout=30
        )
        
        if chat_resp.status_code != 200:
            pytest.skip("Could not create conversation")
        
        assistant_message_id = chat_resp.json().get("assistant_message_id")
        
        sessions["owner"] = owner_session
        
        # Create other user
        other_email = f"other.{int(time.time())}@example.com"
        other_session = requests.Session()
        other_session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        other_session.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": other_email, "password": "NovaV2#2026!Aa", "name": "Other User"},
            timeout=15
        )
        
        login_resp = other_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": other_email, "password": "NovaV2#2026!Aa"},
            timeout=15
        )
        
        if login_resp.status_code != 200:
            pytest.skip("Could not create other user")
        
        sessions["other"] = other_session
        
        return {
            "sessions": sessions,
            "conversation_id": conversation_id,
            "assistant_message_id": assistant_message_id
        }

    def test_favorite_denied_for_non_owner(self, two_users_with_conversation):
        """POST /api/support/chat/messages/favorite should deny non-owner"""
        other_session = two_users_with_conversation["sessions"]["other"]
        conversation_id = two_users_with_conversation["conversation_id"]
        message_id = two_users_with_conversation["assistant_message_id"]
        
        response = other_session.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={"conversation_id": conversation_id, "message_id": message_id},
            timeout=15
        )
        
        assert response.status_code == 403, f"Expected 403 for non-owner, got {response.status_code}"
        
        print("PASS: Favorite denied for non-owner")

    def test_pin_denied_for_non_owner(self, two_users_with_conversation):
        """POST /api/support/chat/conversations/pin should deny non-owner"""
        other_session = two_users_with_conversation["sessions"]["other"]
        conversation_id = two_users_with_conversation["conversation_id"]
        
        response = other_session.post(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": conversation_id},
            timeout=15
        )
        
        assert response.status_code == 403, f"Expected 403 for non-owner, got {response.status_code}"
        
        print("PASS: Pin denied for non-owner")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
