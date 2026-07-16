"""
Nova AI Assistant v2 Backend Tests
Tests for: /api/support/chat, /api/support/chat/attachment, /api/support/chat/audio, 
           /api/support/chat/feedback, /api/support/chat/history
All endpoints require authentication and enforce conversation ownership.
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


class TestNovaAuthRequired:
    """Verify all Nova endpoints require authentication"""

    def test_chat_requires_auth(self):
        """POST /api/support/chat should return 401 without auth"""
        response = requests.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Hello Nova"},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /api/support/chat requires authentication")

    def test_attachment_requires_auth(self):
        """POST /api/support/chat/attachment should return 401 without auth"""
        response = requests.post(
            f"{BASE_URL}/api/support/chat/attachment",
            data={"conversation_id": "test", "message": "test"},
            files={"file": ("test.txt", b"test content", "text/plain")},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /api/support/chat/attachment requires authentication")

    def test_audio_requires_auth(self):
        """POST /api/support/chat/audio should return 401 without auth"""
        # Create a minimal audio-like blob
        response = requests.post(
            f"{BASE_URL}/api/support/chat/audio",
            data={"conversation_id": "test"},
            files={"audio": ("test.webm", b"x" * 200, "audio/webm")},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /api/support/chat/audio requires authentication")

    def test_feedback_requires_auth(self):
        """POST /api/support/chat/feedback should return 401 without auth"""
        response = requests.post(
            f"{BASE_URL}/api/support/chat/feedback",
            json={"conversation_id": "test", "rating": 5, "comment": "Great"},
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /api/support/chat/feedback requires authentication")

    def test_history_requires_auth(self):
        """GET /api/support/chat/history should return 401 without auth"""
        response = requests.get(
            f"{BASE_URL}/api/support/chat/history?conversation_id=test",
            timeout=10
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /api/support/chat/history requires authentication")


class TestNovaHealthEndpoint:
    """Test Nova health endpoint (public)"""

    def test_nova_health_returns_status(self):
        """GET /api/support/nova/health should return health status"""
        response = requests.get(f"{BASE_URL}/api/support/nova/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "status" in data, "Response should contain 'status' field"
        assert data["status"] in ["healthy", "degraded"], f"Status should be healthy or degraded, got {data['status']}"
        print(f"✓ Nova health status: {data['status']}")


class TestNovaAuthenticatedFlow:
    """Test Nova endpoints with authenticated user"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Login and get authenticated session"""
        session = requests.Session()
        # Add CSRF header for all requests
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        # First, try to register the test user (may already exist)
        register_response = session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "name": "Nova Test User"
            },
            timeout=15
        )
        print(f"Register response: {register_response.status_code}")
        
        # Now login
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            },
            timeout=15
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        
        data = login_response.json()
        user_id = data.get("user", {}).get("user_id") or data.get("user_id")
        print(f"✓ Logged in as user: {user_id}")
        
        return {"session": session, "user_id": user_id}

    def test_chat_send_receive(self, auth_session):
        """POST /api/support/chat should send message and receive response with gps_context"""
        session = auth_session["session"]
        conversation_id = f"test-nova-{uuid.uuid4().hex[:8]}"
        
        response = session.post(
            f"{BASE_URL}/api/support/chat",
            json={
                "message": "Hello Nova, what features does this platform have?",
                "conversation_id": conversation_id
            },
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "message" in data, "Response should contain 'message'"
        assert "conversation_id" in data, "Response should contain 'conversation_id'"
        assert "timestamp" in data, "Response should contain 'timestamp'"
        assert "gps_context" in data, "Response should contain 'gps_context'"
        
        # Verify gps_context structure
        gps = data["gps_context"]
        assert "gps_source" in gps, "gps_context should contain 'gps_source'"
        assert "gps_live" in gps, "gps_context should contain 'gps_live'"
        assert "gps_version" in gps, "gps_context should contain 'gps_version'"
        
        print(f"✓ Chat response received with GPS context: gps_live={gps.get('gps_live')}, source={gps.get('gps_source')}")
        
        # Store conversation_id for later tests
        auth_session["conversation_id"] = data["conversation_id"]
        return data

    def test_chat_history_owner_access(self, auth_session):
        """GET /api/support/chat/history should return history for conversation owner"""
        session = auth_session["session"]
        conversation_id = auth_session.get("conversation_id")
        
        if not conversation_id:
            pytest.skip("No conversation_id from previous test")
        
        response = session.get(
            f"{BASE_URL}/api/support/chat/history?conversation_id={conversation_id}",
            timeout=15
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "conversation_id" in data, "Response should contain 'conversation_id'"
        assert "messages" in data, "Response should contain 'messages'"
        assert isinstance(data["messages"], list), "messages should be a list"
        
        # Should have at least 2 messages (user + assistant)
        assert len(data["messages"]) >= 2, f"Expected at least 2 messages, got {len(data['messages'])}"
        
        print(f"✓ Chat history retrieved: {len(data['messages'])} messages")

    def test_feedback_submission(self, auth_session):
        """POST /api/support/chat/feedback should submit feedback for conversation owner"""
        session = auth_session["session"]
        conversation_id = auth_session.get("conversation_id")
        
        if not conversation_id:
            pytest.skip("No conversation_id from previous test")
        
        response = session.post(
            f"{BASE_URL}/api/support/chat/feedback",
            json={
                "conversation_id": conversation_id,
                "rating": 5,
                "comment": "Great response from Nova!",
                "helpful": True
            },
            timeout=15
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("success"), "Feedback submission should succeed"
        assert "feedback_id" in data, "Response should contain 'feedback_id'"
        
        print(f"✓ Feedback submitted: {data.get('feedback_id')}")

    def test_attachment_upload_text(self, auth_session):
        """POST /api/support/chat/attachment should handle text file upload"""
        session = auth_session["session"]
        conversation_id = f"test-attach-{uuid.uuid4().hex[:8]}"
        
        test_content = b"This is a test document for Nova to analyze."
        
        response = session.post(
            f"{BASE_URL}/api/support/chat/attachment",
            data={
                "conversation_id": conversation_id,
                "message": "Please analyze this document"
            },
            files={"file": ("test_doc.txt", test_content, "text/plain")},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "message" in data, "Response should contain 'message'"
        assert "conversation_id" in data, "Response should contain 'conversation_id'"
        assert "gps_context" in data, "Response should contain 'gps_context'"
        assert "attachment" in data, "Response should contain 'attachment'"
        
        attachment = data["attachment"]
        assert "file_id" in attachment, "Attachment should have file_id"
        assert "url" in attachment, "Attachment should have url"
        
        print(f"✓ Attachment uploaded: {attachment.get('file_id')}")

    def test_attachment_invalid_type_rejected(self, auth_session):
        """POST /api/support/chat/attachment should reject unsupported file types"""
        session = auth_session["session"]
        
        response = session.post(
            f"{BASE_URL}/api/support/chat/attachment",
            data={"conversation_id": "test", "message": "test"},
            files={"file": ("test.exe", b"fake executable", "application/x-msdownload")},
            timeout=15
        )
        
        assert response.status_code == 400, f"Expected 400 for invalid file type, got {response.status_code}"
        print("✓ Invalid file type correctly rejected")


class TestNovaConversationOwnership:
    """Test conversation ownership enforcement"""

    @pytest.fixture(scope="class")
    def two_users(self):
        """Create two authenticated sessions"""
        sessions = {}
        
        for i, suffix in enumerate(["owner", "other"]):
            email = f"nova.test.{suffix}.{uuid.uuid4().hex[:6]}@example.com"
            password = "TestPass#2026!Aa"
            
            session = requests.Session()
            # Add CSRF header for all requests
            session.headers.update({"X-Requested-With": "XMLHttpRequest"})
            
            # Register
            session.post(
                f"{BASE_URL}/api/auth/register",
                json={"email": email, "password": password, "name": f"Test User {suffix}"},
                timeout=15
            )
            
            # Login
            login_resp = session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": password},
                timeout=15
            )
            
            if login_resp.status_code != 200:
                pytest.skip(f"Could not create test user {suffix}")
            
            sessions[suffix] = session
            print(f"✓ Created test user: {suffix}")
        
        return sessions

    def test_history_denied_for_non_owner(self, two_users):
        """GET /api/support/chat/history should deny access to non-owner"""
        owner_session = two_users["owner"]
        other_session = two_users["other"]
        
        # Owner creates a conversation
        conv_id = f"ownership-test-{uuid.uuid4().hex[:8]}"
        owner_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Hello from owner", "conversation_id": conv_id},
            timeout=30
        )
        
        # Other user tries to access history
        response = other_session.get(
            f"{BASE_URL}/api/support/chat/history?conversation_id={conv_id}",
            timeout=15
        )
        
        assert response.status_code == 403, f"Expected 403 for non-owner, got {response.status_code}"
        print("✓ History access denied for non-owner")

    def test_feedback_denied_for_non_owner(self, two_users):
        """POST /api/support/chat/feedback should deny access to non-owner"""
        owner_session = two_users["owner"]
        other_session = two_users["other"]
        
        # Owner creates a conversation
        conv_id = f"feedback-test-{uuid.uuid4().hex[:8]}"
        owner_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "Hello from owner", "conversation_id": conv_id},
            timeout=30
        )
        
        # Other user tries to submit feedback
        response = other_session.post(
            f"{BASE_URL}/api/support/chat/feedback",
            json={"conversation_id": conv_id, "rating": 5, "comment": "Hacking attempt"},
            timeout=15
        )
        
        assert response.status_code == 403, f"Expected 403 for non-owner, got {response.status_code}"
        print("✓ Feedback submission denied for non-owner")


class TestNovaGPSContext:
    """Test GPS context in Nova responses"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        """Login and get authenticated session"""
        session = requests.Session()
        # Add CSRF header for all requests
        session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        
        # Register/login test user
        session.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "name": "Nova Test User"
            },
            timeout=15
        )
        
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            timeout=15
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        return session

    def test_gps_context_structure(self, auth_session):
        """Verify gps_context has all required fields"""
        response = auth_session.post(
            f"{BASE_URL}/api/support/chat",
            json={"message": "What is the platform status?"},
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        gps = data.get("gps_context", {})
        
        required_fields = ["gps_source", "gps_live", "gps_version", "gps_updated_at", "gps_freshness_sec", "gps_counts", "gps_failed_checks"]
        for field in required_fields:
            assert field in gps, f"gps_context missing required field: {field}"
        
        # Verify gps_counts structure
        counts = gps.get("gps_counts", {})
        assert "features" in counts, "gps_counts should have 'features'"
        assert "plans" in counts, "gps_counts should have 'plans'"
        
        print(f"✓ GPS context complete: live={gps['gps_live']}, version={gps['gps_version']}, source={gps['gps_source']}")
        print(f"  Counts: features={counts.get('features')}, plans={counts.get('plans')}, faq={counts.get('faq')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
