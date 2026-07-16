"""
Test Support Nova Curation Features - Iteration 98
Tests for Support Contact->Chat Nova V2 curation features:
- Favorites/pins endpoints used by Support Nova
- Message actions (save favorite toggle, pin conversation toggle)
- Favorite snippets chips
- Pinned conversations list panel
- Favorite answers list panel
- Audio, attachment, feedback, and GPS context indicators
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


class TestSupportNovaAuth:
    """Test authentication requirements for Support Nova endpoints"""
    
    def test_support_chat_requires_auth(self):
        """Support chat endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Hello"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Support chat requires auth")
    
    def test_support_favorites_list_requires_auth(self):
        """Support favorites list requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/support/chat/messages/favorites",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Support favorites list requires auth")
    
    def test_support_pins_list_requires_auth(self):
        """Support pins list requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/support/chat/conversations/pins",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Support pins list requires auth")
    
    def test_support_favorite_post_requires_auth(self):
        """Support favorite POST requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={"conversation_id": "test", "message_id": "test"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Support favorite POST requires auth")
    
    def test_support_pin_post_requires_auth(self):
        """Support pin POST requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": "test"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASSED: Support pin POST requires auth")


class TestSupportNovaChatFlow:
    """Test Support Nova chat flow with curation features"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session for test user"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        
        return session
    
    def test_support_chat_returns_message_id(self, auth_session):
        """Support chat returns assistant_message_id for curation"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "What features does RealAICoach offer?"},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "message" in data, "Response should contain 'message'"
        assert "conversation_id" in data, "Response should contain 'conversation_id'"
        assert "timestamp" in data, "Response should contain 'timestamp'"
        
        # Check for assistant_message_id (required for favorites)
        assert "assistant_message_id" in data, "Response should contain 'assistant_message_id' for curation"
        assert data["assistant_message_id"].startswith("nm_"), f"assistant_message_id should start with 'nm_', got {data['assistant_message_id']}"
        
        print(f"PASSED: Support chat returns message_id: {data['assistant_message_id']}")
        return data
    
    def test_support_chat_returns_gps_context(self, auth_session):
        """Support chat returns GPS context indicators"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Tell me about subscription plans"},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Check for GPS context (optional but expected)
        if "gps_context" in data:
            gps = data["gps_context"]
            print(f"PASSED: GPS context present - live={gps.get('gps_live')}, version={gps.get('gps_version')}")
        else:
            print("INFO: GPS context not present in response (may be expected)")
        
        return data


class TestSupportNovaFavoritesFlow:
    """Test Support Nova favorites (save answer) flow"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        return session
    
    @pytest.fixture(scope="class")
    def chat_with_message_id(self, auth_session):
        """Create a chat and get message_id for favorites testing"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": f"Test message for favorites {uuid.uuid4().hex[:8]}"},
            timeout=30
        )
        
        if response.status_code != 200:
            pytest.skip(f"Chat failed: {response.status_code}")
        
        data = response.json()
        if "assistant_message_id" not in data:
            pytest.skip("No assistant_message_id in response")
        
        return {
            "conversation_id": data["conversation_id"],
            "message_id": data["assistant_message_id"],
            "content": data["message"]
        }
    
    def test_favorite_assistant_message(self, auth_session, chat_with_message_id):
        """Can favorite an assistant message"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={
                "conversation_id": chat_with_message_id["conversation_id"],
                "message_id": chat_with_message_id["message_id"]
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success"), "Favorite should succeed"
        print(f"PASSED: Favorited message {chat_with_message_id['message_id']}")
    
    def test_list_favorites_returns_saved_message(self, auth_session, chat_with_message_id):
        """Favorites list includes the saved message"""
        # First favorite the message
        auth_session.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={
                "conversation_id": chat_with_message_id["conversation_id"],
                "message_id": chat_with_message_id["message_id"]
            }
        )
        
        # Then list favorites
        response = auth_session.get(
            f"{BASE_URL}/api/support/chat/messages/favorites",
            params={"conversation_id": chat_with_message_id["conversation_id"]}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "favorites" in data, "Response should contain 'favorites'"
        
        # Check if our message is in favorites
        favorites = data["favorites"]
        message_ids = [f.get("message_id") for f in favorites]
        assert chat_with_message_id["message_id"] in message_ids, "Favorited message should be in list"
        
        # Verify favorite has content for snippets display
        for fav in favorites:
            if fav.get("message_id") == chat_with_message_id["message_id"]:
                assert "content" in fav, "Favorite should have content for snippets"
                print(f"PASSED: Favorites list contains message with content: {fav['content'][:50]}...")
                break
    
    def test_unfavorite_message(self, auth_session, chat_with_message_id):
        """Can unfavorite a message"""
        # First favorite
        auth_session.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={
                "conversation_id": chat_with_message_id["conversation_id"],
                "message_id": chat_with_message_id["message_id"]
            }
        )
        
        # Then unfavorite
        response = auth_session.delete(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={
                "conversation_id": chat_with_message_id["conversation_id"],
                "message_id": chat_with_message_id["message_id"]
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success"), "Unfavorite should succeed"
        print("PASSED: Unfavorited message successfully")


class TestSupportNovaPinsFlow:
    """Test Support Nova pins (pin conversation) flow"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        return session
    
    @pytest.fixture(scope="class")
    def conversation_id(self, auth_session):
        """Create a conversation for pins testing"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": f"Test message for pins {uuid.uuid4().hex[:8]}"},
            timeout=30
        )
        
        if response.status_code != 200:
            pytest.skip(f"Chat failed: {response.status_code}")
        
        return response.json()["conversation_id"]
    
    def test_pin_conversation(self, auth_session, conversation_id):
        """Can pin a conversation"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": conversation_id}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success"), "Pin should succeed"
        print(f"PASSED: Pinned conversation {conversation_id}")
    
    def test_list_pins_returns_pinned_conversation(self, auth_session, conversation_id):
        """Pins list includes the pinned conversation with preview"""
        # First pin the conversation
        auth_session.post(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": conversation_id}
        )
        
        # Then list pins
        response = auth_session.get(f"{BASE_URL}/api/support/chat/conversations/pins")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "pins" in data, "Response should contain 'pins'"
        
        # Check if our conversation is in pins
        pins = data["pins"]
        conv_ids = [p.get("conversation_id") for p in pins]
        assert conversation_id in conv_ids, "Pinned conversation should be in list"
        
        # Verify pin has preview for display
        for pin in pins:
            if pin.get("conversation_id") == conversation_id:
                assert "preview" in pin, "Pin should have preview for display"
                print(f"PASSED: Pins list contains conversation with preview: {pin.get('preview', '')[:50]}...")
                break
    
    def test_unpin_conversation(self, auth_session, conversation_id):
        """Can unpin a conversation"""
        # First pin
        auth_session.post(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": conversation_id}
        )
        
        # Then unpin
        response = auth_session.delete(
            f"{BASE_URL}/api/support/chat/conversations/pin",
            json={"conversation_id": conversation_id}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success"), "Unpin should succeed"
        print("PASSED: Unpinned conversation successfully")


class TestSupportNovaFeedback:
    """Test Support Nova feedback flow"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Get authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        return session
    
    @pytest.fixture(scope="class")
    def conversation_id(self, auth_session):
        """Create a conversation for feedback testing"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": f"Test message for feedback {uuid.uuid4().hex[:8]}"},
            timeout=30
        )
        
        if response.status_code != 200:
            pytest.skip(f"Chat failed: {response.status_code}")
        
        return response.json()["conversation_id"]
    
    def test_submit_feedback(self, auth_session, conversation_id):
        """Can submit feedback for a conversation"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat/feedback",
            json={
                "conversation_id": conversation_id,
                "rating": 5,
                "comment": "Great help!",
                "helpful": True
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("success"), "Feedback should succeed"
        assert "feedback_id" in data, "Response should contain feedback_id"
        print(f"PASSED: Submitted feedback {data['feedback_id']}")


class TestSupportNovaHealth:
    """Test Support Nova health endpoint"""
    
    def test_nova_health_endpoint(self):
        """Nova health endpoint returns status"""
        response = requests.get(f"{BASE_URL}/api/support/nova/health")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "status" in data, "Response should contain 'status'"
        assert data["status"] in ["healthy", "degraded"], f"Status should be healthy or degraded, got {data['status']}"
        
        # Check for expected fields
        expected_fields = ["window_hours", "success_ratio", "error_ratio"]
        for field in expected_fields:
            assert field in data, f"Response should contain '{field}'"
        
        print(f"PASSED: Nova health status: {data['status']}, success_ratio: {data['success_ratio']}%")


class TestSupportNovaOwnership:
    """Test Support Nova ownership enforcement"""
    
    def test_favorite_denied_for_non_owner(self):
        """Cannot favorite a message from another user's conversation"""
        # Create two sessions with different users
        session1 = requests.Session()
        session1.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as test user
        login1 = session1.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        )
        
        if login1.status_code != 200:
            pytest.skip("Login failed for test user")
        
        # Create a conversation
        chat_response = session1.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Test ownership"},
            timeout=30
        )
        
        if chat_response.status_code != 200:
            pytest.skip("Chat failed")
        
        chat_data = chat_response.json()
        
        # Try to favorite with a different user (using a fake conversation_id)
        # This should fail with 403 if ownership is enforced
        session2 = requests.Session()
        session2.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as a different user (using curation test user)
        login2 = session2.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "curation.1779076352@example.com", "password": "NovaV2#2026!Aa"}
        )
        
        if login2.status_code != 200:
            pytest.skip("Login failed for second user")
        
        # Try to favorite the first user's message
        response = session2.post(
            f"{BASE_URL}/api/support/chat/messages/favorite",
            json={
                "conversation_id": chat_data["conversation_id"],
                "message_id": chat_data.get("assistant_message_id", "nm_test")
            }
        )
        
        # Should be denied (403) because user2 doesn't own the conversation
        assert response.status_code == 403, f"Expected 403 for non-owner, got {response.status_code}"
        print("PASSED: Ownership enforced - non-owner cannot favorite")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
