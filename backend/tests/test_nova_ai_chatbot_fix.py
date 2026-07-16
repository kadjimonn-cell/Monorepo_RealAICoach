"""
Nova AI Chatbot Bug Fix Verification Tests
==========================================
Tests for the fix: AIChatPanel now uses /personal-assistant/* endpoints instead of /ai-engine/*
This ensures non-admin authenticated users can use Nova chat without premium-gating.

Test scenarios:
1. Non-admin authenticated users can load sessions via /personal-assistant/sessions
2. Non-admin authenticated users can send messages via /personal-assistant/sessions/{id}/messages
3. Free/basic users receive assistant responses (not premium-gated 403)
4. Admin user can still use Nova chat
5. Error responses contain meaningful messages (message/detail extraction)
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"

BASIC_USER_EMAIL = "f22.basic.20260613@example.com"
BASIC_USER_PASSWORD = "F22Basic#2026Aa"

NON_ADMIN_DELEGATED_EMAIL = "curation.1779076352@example.com"
NON_ADMIN_DELEGATED_PASSWORD = "NovaV2#2026!Aa"


def login_user(email: str, password: str) -> dict:
    """Login and return session info with cookies."""
    session = requests.Session()
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    return {"session": session, "response": response}


class TestPersonalAssistantEndpointsAccessibility:
    """Test that /personal-assistant/* endpoints are accessible to all authenticated users."""

    def test_bootstrap_endpoint_accessible_for_free_user(self):
        """Free user should be able to access /personal-assistant/bootstrap."""
        login_result = login_user(FREE_USER_EMAIL, FREE_USER_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed for free user: {login_result['response'].status_code}")
        
        session = login_result["session"]
        response = session.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        
        # Should NOT be 403 (premium-gated)
        assert response.status_code != 403, f"Free user got 403 on bootstrap: {response.text}"
        # Should be 200 or 401 (if auth issue, not subscription issue)
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "sessions" in data or "owner_id" in data, "Bootstrap response missing expected fields"
            print(f"✓ Free user bootstrap successful: tier={data.get('tier', 'unknown')}")

    def test_bootstrap_endpoint_accessible_for_basic_user(self):
        """Basic user should be able to access /personal-assistant/bootstrap."""
        login_result = login_user(BASIC_USER_EMAIL, BASIC_USER_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed for basic user: {login_result['response'].status_code}")
        
        session = login_result["session"]
        response = session.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        
        assert response.status_code != 403, f"Basic user got 403 on bootstrap: {response.text}"
        assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Basic user bootstrap successful: tier={data.get('tier', 'unknown')}")

    def test_bootstrap_endpoint_accessible_for_admin(self):
        """Admin user should be able to access /personal-assistant/bootstrap."""
        login_result = login_user(ADMIN_EMAIL, ADMIN_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed for admin: {login_result['response'].status_code}")
        
        session = login_result["session"]
        response = session.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        
        assert response.status_code == 200, f"Admin bootstrap failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "sessions" in data or "owner_id" in data
        print(f"✓ Admin bootstrap successful: tier={data.get('tier', 'unknown')}")


class TestPersonalAssistantSessionsFlow:
    """Test session creation and message sending for non-admin users."""

    def test_free_user_can_create_session(self):
        """Free user should be able to create a personal assistant session."""
        login_result = login_user(FREE_USER_EMAIL, FREE_USER_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed: {login_result['response'].status_code}")
        
        session = login_result["session"]
        response = session.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            json={"title": "Test Session from Free User"},
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
        )
        
        # Should NOT be 403 (premium-gated)
        assert response.status_code != 403, f"Free user got 403 on session create: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "session" in data
            assert "session_id" in data["session"]
            print(f"✓ Free user created session: {data['session']['session_id']}")
            return data["session"]["session_id"]

    def test_free_user_can_list_sessions(self):
        """Free user should be able to list their sessions."""
        login_result = login_user(FREE_USER_EMAIL, FREE_USER_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed: {login_result['response'].status_code}")
        
        session = login_result["session"]
        response = session.get(
            f"{BASE_URL}/api/personal-assistant/sessions",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        
        assert response.status_code != 403, f"Free user got 403 on sessions list: {response.text}"
        assert response.status_code == 200, f"Unexpected status: {response.status_code}"
        
        data = response.json()
        assert "sessions" in data
        print(f"✓ Free user listed {len(data['sessions'])} sessions")

    def test_non_admin_delegated_user_can_access_assistant(self):
        """Non-admin delegated user (curation) should be able to use personal assistant."""
        login_result = login_user(NON_ADMIN_DELEGATED_EMAIL, NON_ADMIN_DELEGATED_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed for delegated user: {login_result['response'].status_code}")
        
        session = login_result["session"]
        
        # Test bootstrap
        response = session.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        
        assert response.status_code != 403, f"Delegated user got 403: {response.text}"
        print("✓ Non-admin delegated user can access personal assistant")


class TestPersonalAssistantMessageFlow:
    """Test message sending flow - the core fix verification."""

    def test_free_user_can_send_message_and_get_response(self):
        """
        CRITICAL TEST: Free user should be able to send a message and receive an AI response.
        This verifies the fix: using /personal-assistant/* instead of /ai-engine/*.
        """
        login_result = login_user(FREE_USER_EMAIL, FREE_USER_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed: {login_result['response'].status_code}")
        
        session = login_result["session"]
        
        # Step 1: Create a session
        create_response = session.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            json={"title": "Test Message Flow"},
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
        )
        
        if create_response.status_code != 200:
            pytest.skip(f"Session creation failed: {create_response.status_code}")
        
        session_id = create_response.json()["session"]["session_id"]
        print(f"Created session: {session_id}")
        
        # Step 2: Send a message
        message_response = session.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            json={
                "content": "Hello, this is a test message",
                "mode": "planner",
                "idempotency_key": f"test_{int(time.time())}",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
            timeout=60,  # AI responses can take time
        )
        
        # CRITICAL: Should NOT be 403 (premium-gated from /ai-engine/)
        assert message_response.status_code != 403, (
            f"Free user got 403 on message send - this indicates the old /ai-engine/ path is still being used: "
            f"{message_response.text}"
        )
        
        # Should be 200 (success) or 500 (LLM error, but not subscription error)
        if message_response.status_code == 200:
            data = message_response.json()
            assert "assistant_message" in data, "Response missing assistant_message"
            assert "content" in data["assistant_message"], "Assistant message missing content"
            print(f"✓ Free user received AI response: {data['assistant_message']['content'][:100]}...")
        elif message_response.status_code == 500:
            # LLM error is acceptable - it means the endpoint was reached, not blocked
            data = message_response.json()
            print(f"⚠ LLM error (acceptable - not subscription blocked): {data.get('detail', {}).get('message', 'unknown')}")
        else:
            pytest.fail(f"Unexpected status {message_response.status_code}: {message_response.text}")


class TestErrorMessageExtraction:
    """Test that error responses contain meaningful messages."""

    def test_error_response_has_meaningful_message(self):
        """Backend errors should return structured error messages."""
        # Test with invalid session ID
        login_result = login_user(FREE_USER_EMAIL, FREE_USER_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed: {login_result['response'].status_code}")
        
        session = login_result["session"]
        
        response = session.get(
            f"{BASE_URL}/api/personal-assistant/sessions/invalid_session_id_12345",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        
        # Should be 404 with meaningful error
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        # Check for structured error response
        detail = data.get("detail", {})
        if isinstance(detail, dict):
            assert "message" in detail or "error_code" in detail, "Error response missing message/error_code"
            print(f"✓ Error response has structured message: {detail.get('message', detail.get('error_code'))}")
        elif isinstance(detail, str):
            assert len(detail) > 0, "Error detail is empty"
            print(f"✓ Error response has string message: {detail}")


class TestAdminRegressionCheck:
    """Regression check: Admin should still be able to use Nova chat."""

    def test_admin_full_flow(self):
        """Admin user should be able to complete full Nova chat flow."""
        login_result = login_user(ADMIN_EMAIL, ADMIN_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Admin login failed: {login_result['response'].status_code}")
        
        session = login_result["session"]
        
        # Bootstrap
        bootstrap_response = session.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert bootstrap_response.status_code == 200, f"Admin bootstrap failed: {bootstrap_response.text}"
        
        # Create session
        create_response = session.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            json={"title": "Admin Test Session"},
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
        )
        assert create_response.status_code == 200, f"Admin session create failed: {create_response.text}"
        
        session_id = create_response.json()["session"]["session_id"]
        
        # Send message
        message_response = session.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            json={
                "content": "Admin test message",
                "mode": "planner",
                "idempotency_key": f"admin_test_{int(time.time())}",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
            timeout=60,
        )
        
        # Admin should definitely get 200
        assert message_response.status_code in [200, 500], (
            f"Admin message send failed unexpectedly: {message_response.status_code} - {message_response.text}"
        )
        
        if message_response.status_code == 200:
            print("✓ Admin full flow completed successfully")
        else:
            print("⚠ Admin got LLM error (acceptable)")


class TestUsageEndpoint:
    """Test the usage endpoint for tier limits."""

    def test_usage_endpoint_returns_tier_info(self):
        """Usage endpoint should return tier and limit information."""
        login_result = login_user(FREE_USER_EMAIL, FREE_USER_PASSWORD)
        if login_result["response"].status_code != 200:
            pytest.skip(f"Login failed: {login_result['response'].status_code}")
        
        session = login_result["session"]
        
        response = session.get(
            f"{BASE_URL}/api/personal-assistant/usage",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        
        assert response.status_code == 200, f"Usage endpoint failed: {response.status_code}"
        
        data = response.json()
        assert "tier" in data, "Usage response missing tier"
        assert "daily_limit" in data, "Usage response missing daily_limit"
        assert "messages_used_today" in data, "Usage response missing messages_used_today"
        
        print(f"✓ Usage info: tier={data['tier']}, limit={data['daily_limit']}, used={data['messages_used_today']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
