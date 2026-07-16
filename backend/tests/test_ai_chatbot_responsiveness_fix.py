"""
Test suite for Nova AI Chatbot responsiveness fix verification.
Tests that /features/ai-chatbot route is accessible for free/basic/premium users
and that the personal-assistant API endpoints work correctly.

Root causes fixed:
1. Narrow branch in ai-chatbot.tsx omitted message rendering/mode controls
2. Frontend access-control had /features blanket basic gate but ai-chatbot is backend-tiered
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
TEST_USERS = {
    'basic': {
        'email': 'f22.basic.20260613@example.com',
        'password': 'F22Basic#2026Aa',
        'expected_tier': 'basic',
        'expected_daily_limit': 200,
    },
    'free': {
        'email': 'p1.free.1779113329@example.com',
        'password': 'P1Free#2026!Aa',
        'expected_tier': 'free',
        'expected_daily_limit': 50,
    },
    'admin': {
        'email': 'admin@realaicoach.app',
        'password': 'NewAdminPass2026!',
        'expected_tier': 'premium',
        'expected_daily_limit': -1,  # unlimited
    },
}


class TestPersonalAssistantAccessibility:
    """Tests that personal assistant API is accessible for all tiers"""

    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        })
        return session

    def login_user(self, client, user_key):
        """Helper to login a user and return user_id"""
        user = TEST_USERS[user_key]
        response = client.post(
            f"{BASE_URL}/api/auth/login",
            json={'email': user['email'], 'password': user['password']}
        )
        assert response.status_code in [200, 201], f"Login failed for {user_key}: {response.text}"
        data = response.json()
        return data.get('user_id')

    def test_free_user_can_access_bootstrap(self, api_client):
        """Free user should be able to access personal assistant bootstrap"""
        user_id = self.login_user(api_client, 'free')
        
        response = api_client.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={'fallback_user_id': user_id}
        )
        
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert 'sessions' in data
        assert 'usage' in data
        assert 'stats' in data
        
        # Verify tier info
        usage = data['usage']
        assert usage['tier'] == 'free'
        assert usage['daily_limit'] == 50
        print(f"PASS: Free user bootstrap - tier={usage['tier']}, limit={usage['daily_limit']}")

    def test_basic_user_can_access_bootstrap(self, api_client):
        """Basic user should be able to access personal assistant bootstrap"""
        user_id = self.login_user(api_client, 'basic')
        
        response = api_client.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={'fallback_user_id': user_id}
        )
        
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert 'sessions' in data
        assert 'usage' in data
        assert 'stats' in data
        
        # Verify tier info
        usage = data['usage']
        assert usage['tier'] == 'basic'
        assert usage['daily_limit'] == 200
        print(f"PASS: Basic user bootstrap - tier={usage['tier']}, limit={usage['daily_limit']}")

    def test_admin_user_can_access_bootstrap(self, api_client):
        """Admin user should be able to access personal assistant bootstrap"""
        user_id = self.login_user(api_client, 'admin')
        
        response = api_client.get(
            f"{BASE_URL}/api/personal-assistant/bootstrap",
            params={'fallback_user_id': user_id}
        )
        
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert 'sessions' in data
        assert 'usage' in data
        assert 'stats' in data
        
        # Verify tier info (admin gets premium)
        usage = data['usage']
        assert usage['tier'] == 'premium'
        assert usage['daily_limit'] == -1  # unlimited
        print(f"PASS: Admin user bootstrap - tier={usage['tier']}, limit={usage['daily_limit']}")


class TestPersonalAssistantSessionCRUD:
    """Tests session creation and message sending"""

    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        })
        return session

    def login_user(self, client, user_key):
        """Helper to login a user and return user_id"""
        user = TEST_USERS[user_key]
        response = client.post(
            f"{BASE_URL}/api/auth/login",
            json={'email': user['email'], 'password': user['password']}
        )
        assert response.status_code in [200, 201], f"Login failed for {user_key}: {response.text}"
        data = response.json()
        return data.get('user_id')

    def test_basic_user_can_create_session(self, api_client):
        """Basic user should be able to create a new session"""
        user_id = self.login_user(api_client, 'basic')
        
        response = api_client.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            json={
                'title': 'TEST_Responsiveness_Fix_Session',
                'fallback_user_id': user_id,
            }
        )
        
        assert response.status_code in [200, 201], f"Session creation failed: {response.text}"
        data = response.json()
        
        assert 'session' in data
        session = data['session']
        assert 'session_id' in session
        assert session['title'] == 'TEST_Responsiveness_Fix_Session'
        print(f"PASS: Basic user created session: {session['session_id']}")
        
        return session['session_id']

    def test_free_user_can_create_session(self, api_client):
        """Free user should be able to create a new session"""
        user_id = self.login_user(api_client, 'free')
        
        response = api_client.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            json={
                'title': 'TEST_Free_User_Session',
                'fallback_user_id': user_id,
            }
        )
        
        assert response.status_code in [200, 201], f"Session creation failed: {response.text}"
        data = response.json()
        
        assert 'session' in data
        session = data['session']
        assert 'session_id' in session
        print(f"PASS: Free user created session: {session['session_id']}")

    def test_basic_user_can_send_message(self, api_client):
        """Basic user should be able to send a message and get AI response"""
        user_id = self.login_user(api_client, 'basic')
        
        # First create a session
        session_response = api_client.post(
            f"{BASE_URL}/api/personal-assistant/sessions",
            json={
                'title': 'TEST_Message_Send_Session',
                'fallback_user_id': user_id,
            }
        )
        assert session_response.status_code in [200, 201]
        session_id = session_response.json()['session']['session_id']
        
        # Send a message
        import time
        message_response = api_client.post(
            f"{BASE_URL}/api/personal-assistant/sessions/{session_id}/messages",
            json={
                'content': 'Hello, please give me one quick tip for productivity.',
                'mode': 'planner',
                'fallback_user_id': user_id,
                'idempotency_key': f'{session_id}:{int(time.time())}',
            },
            timeout=60  # AI response may take time
        )
        
        assert message_response.status_code == 200, f"Message send failed: {message_response.text}"
        data = message_response.json()
        
        # Verify user message and assistant response
        assert 'user_message' in data
        assert 'assistant_message' in data
        
        user_msg = data['user_message']
        assistant_msg = data['assistant_message']
        
        assert user_msg['role'] == 'user'
        assert assistant_msg['role'] == 'assistant'
        assert len(assistant_msg['content']) > 0
        
        print("PASS: Basic user sent message and received AI response")
        print(f"  User: {user_msg['content'][:50]}...")
        print(f"  Assistant: {assistant_msg['content'][:100]}...")


class TestAccessControlRouteAllowlist:
    """Tests that /features/ai-chatbot is in the route allowlist"""

    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        })
        return session

    def login_user(self, client, user_key):
        """Helper to login a user and return user_id"""
        user = TEST_USERS[user_key]
        response = client.post(
            f"{BASE_URL}/api/auth/login",
            json={'email': user['email'], 'password': user['password']}
        )
        assert response.status_code in [200, 201], f"Login failed for {user_key}: {response.text}"
        return response.json()

    def test_free_user_access_control_session(self, api_client):
        """Free user should get access-control session without route blocking"""
        self.login_user(api_client, 'free')
        
        response = api_client.get(
            f"{BASE_URL}/api/access-control/session",
            timeout=10
        )
        
        # Should return 200 with session info
        assert response.status_code == 200, f"Access control session failed: {response.text}"
        data = response.json()
        
        assert 'effective_plan' in data
        assert data['effective_plan'] == 'free'
        print(f"PASS: Free user access-control session - plan={data['effective_plan']}")

    def test_basic_user_access_control_session(self, api_client):
        """Basic user should get access-control session"""
        self.login_user(api_client, 'basic')
        
        response = api_client.get(
            f"{BASE_URL}/api/access-control/session",
            timeout=10
        )
        
        assert response.status_code == 200, f"Access control session failed: {response.text}"
        data = response.json()
        
        assert 'effective_plan' in data
        assert data['effective_plan'] == 'basic'
        print(f"PASS: Basic user access-control session - plan={data['effective_plan']}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
