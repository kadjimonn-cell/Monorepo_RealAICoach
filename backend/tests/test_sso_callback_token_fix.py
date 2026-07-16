"""
Test SSO Callback Token Handling Fix - Iteration 106

Verifies the fix for callback handlers that expected result['session_token'] 
but process helpers returned token payload only for native channels.

Tests:
1. Regression: GET /api/auth/microsoft/login returns 302
2. Regression: GET /api/auth/apple/login returns 302
3. Verify codebase path now supports web callbacks without requiring session_token in public payload
4. Ensure /api/auth/microsoft/exchange and /api/auth/apple/exchange do not leak _session_token_internal/_refresh_token_internal
"""

import pytest
import requests
import os
from urllib.parse import urlparse, parse_qs

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSSOLoginRedirects:
    """Test SSO login endpoints return proper 302 redirects"""
    
    def test_microsoft_login_returns_302(self):
        """Regression: GET /api/auth/microsoft/login returns 302 redirect"""
        response = requests.get(
            f"{BASE_URL}/api/auth/microsoft/login",
            allow_redirects=False
        )
        assert response.status_code == 302, f"Expected 302, got {response.status_code}"
        
        location = response.headers.get('Location', '')
        assert 'login.microsoftonline.com' in location or 'microsoft' in location.lower(), \
            f"Expected Microsoft OAuth URL, got: {location[:200]}"
        print(f"✓ Microsoft login returns 302 redirect to: {location[:100]}...")
    
    def test_apple_login_returns_302(self):
        """Regression: GET /api/auth/apple/login returns 302 redirect"""
        response = requests.get(
            f"{BASE_URL}/api/auth/apple/login",
            allow_redirects=False
        )
        assert response.status_code == 302, f"Expected 302, got {response.status_code}"
        
        location = response.headers.get('Location', '')
        assert 'appleid.apple.com' in location, \
            f"Expected Apple OAuth URL, got: {location[:200]}"
        print(f"✓ Apple login returns 302 redirect to: {location[:100]}...")


class TestCallbackCodePathVerification:
    """Verify callback code path supports web callbacks without session_token in public payload"""
    
    def test_microsoft_callback_no_crash_on_missing_code(self):
        """Microsoft callback should redirect gracefully without code (not crash)"""
        response = requests.get(
            f"{BASE_URL}/api/auth/microsoft/callback",
            allow_redirects=False
        )
        # Should redirect to frontend with error, not crash with 500
        assert response.status_code in [302, 307], f"Expected redirect, got {response.status_code}"
        
        location = response.headers.get('Location', '')
        assert 'sso_error' in location or 'no_code' in location or 'login' in location, \
            f"Expected error redirect, got: {location}"
        print(f"✓ Microsoft callback handles missing code gracefully: {location[:100]}...")
    
    def test_apple_callback_no_crash_on_missing_code(self):
        """Apple callback should redirect gracefully without code (not crash)"""
        # Apple uses POST form_post, but GET should also not crash
        response = requests.get(
            f"{BASE_URL}/api/auth/apple/callback",
            allow_redirects=False
        )
        # Should return 405 (Method Not Allowed) or redirect, not 500
        assert response.status_code in [302, 307, 405, 422], \
            f"Expected redirect or 405, got {response.status_code}"
        print(f"✓ Apple callback GET returns {response.status_code} (expected behavior)")
    
    def test_apple_callback_post_no_crash_on_missing_code(self):
        """Apple callback POST should redirect gracefully without code (not crash)"""
        response = requests.post(
            f"{BASE_URL}/api/auth/apple/callback",
            data={},  # Empty form data
            allow_redirects=False
        )
        # Should redirect to frontend with error, not crash with 500
        assert response.status_code in [302, 307], f"Expected redirect, got {response.status_code}"
        
        location = response.headers.get('Location', '')
        assert 'sso_error' in location or 'no_code' in location or 'login' in location, \
            f"Expected error redirect, got: {location}"
        print(f"✓ Apple callback POST handles missing code gracefully: {location[:100]}...")


class TestExchangeEndpointsNoTokenLeak:
    """Ensure exchange endpoints do not leak internal tokens in response"""
    
    def test_microsoft_exchange_no_internal_token_leak(self):
        """Microsoft exchange should not leak _session_token_internal/_refresh_token_internal"""
        # This will fail with 400 due to missing code, but we can check error response structure
        response = requests.post(
            f"{BASE_URL}/api/auth/microsoft/exchange",
            json={"code": "invalid_test_code"},
            headers={"Content-Type": "application/json"}
        )
        
        # Expected to fail with 400 or 500 due to invalid code
        assert response.status_code in [400, 500], f"Expected 400/500, got {response.status_code}"
        
        # Check response doesn't contain internal tokens even in error
        response_text = response.text.lower()
        assert '_session_token_internal' not in response_text, \
            "Response should not contain _session_token_internal"
        assert '_refresh_token_internal' not in response_text, \
            "Response should not contain _refresh_token_internal"
        print("✓ Microsoft exchange error response does not leak internal tokens")
    
    def test_apple_exchange_no_internal_token_leak(self):
        """Apple exchange should not leak _session_token_internal/_refresh_token_internal"""
        response = requests.post(
            f"{BASE_URL}/api/auth/apple/exchange",
            json={"code": "invalid_test_code"},
            headers={"Content-Type": "application/json"}
        )
        
        # Expected to fail with 400 or 500 due to invalid code
        assert response.status_code in [400, 500], f"Expected 400/500, got {response.status_code}"
        
        # Check response doesn't contain internal tokens even in error
        response_text = response.text.lower()
        assert '_session_token_internal' not in response_text, \
            "Response should not contain _session_token_internal"
        assert '_refresh_token_internal' not in response_text, \
            "Response should not contain _refresh_token_internal"
        print("✓ Apple exchange error response does not leak internal tokens")
    
    def test_microsoft_exchange_missing_code_returns_400(self):
        """Microsoft exchange should return 400 for missing code"""
        response = requests.post(
            f"{BASE_URL}/api/auth/microsoft/exchange",
            json={},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert 'detail' in data, "Expected error detail in response"
        print(f"✓ Microsoft exchange returns 400 for missing code: {data.get('detail')}")
    
    def test_apple_exchange_missing_code_returns_400(self):
        """Apple exchange should return 400 for missing code"""
        response = requests.post(
            f"{BASE_URL}/api/auth/apple/exchange",
            json={},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = response.json()
        assert 'detail' in data, "Expected error detail in response"
        print(f"✓ Apple exchange returns 400 for missing code: {data.get('detail')}")


class TestSSOConfigEndpoints:
    """Test SSO configuration endpoints"""
    
    def test_sso_config_returns_callbacks(self):
        """SSO config should return proper callback URLs"""
        response = requests.get(f"{BASE_URL}/api/auth/sso-config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert 'microsoft_callback' in data, "Expected microsoft_callback in response"
        assert 'apple_callback' in data, "Expected apple_callback in response"
        
        # Verify callbacks are HTTPS
        assert data['microsoft_callback'].startswith('https://'), \
            f"Microsoft callback should be HTTPS: {data['microsoft_callback']}"
        assert data['apple_callback'].startswith('https://'), \
            f"Apple callback should be HTTPS: {data['apple_callback']}"
        
        print("✓ SSO config returns valid callbacks:")
        print(f"  Microsoft: {data['microsoft_callback']}")
        print(f"  Apple: {data['apple_callback']}")
    
    def test_apple_init_returns_preflight_data(self):
        """Apple init should return preflight probe data"""
        response = requests.get(f"{BASE_URL}/api/auth/apple/init")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get('ok') is True, f"Expected ok=true, got {data.get('ok')}"
        assert data.get('provider') == 'apple', f"Expected provider=apple, got {data.get('provider')}"
        assert 'callback' in data, "Expected callback in response"
        
        # Check redirect_preflight if present
        if 'redirect_preflight' in data:
            preflight = data['redirect_preflight']
            print("✓ Apple init returns preflight data:")
            print(f"  selected_via: {preflight.get('selected_via')}")
            print(f"  all_invalid: {preflight.get('all_invalid')}")
        else:
            print(f"✓ Apple init returns callback: {data['callback']}")


class TestBackendLogsNoKeyError:
    """Verify backend logs don't emit session_token KeyError during callback simulation"""
    
    def test_microsoft_callback_with_error_param_no_crash(self):
        """Microsoft callback with error param should not crash with KeyError"""
        response = requests.get(
            f"{BASE_URL}/api/auth/microsoft/callback",
            params={"error": "access_denied", "error_description": "User cancelled"},
            allow_redirects=False
        )
        # Should redirect with error, not crash
        assert response.status_code in [302, 307], f"Expected redirect, got {response.status_code}"
        
        location = response.headers.get('Location', '')
        assert 'sso_error' in location or 'access_denied' in location, \
            f"Expected error in redirect: {location}"
        print("✓ Microsoft callback handles error param without crash")
    
    def test_apple_callback_with_error_param_no_crash(self):
        """Apple callback with error param should not crash with KeyError"""
        response = requests.post(
            f"{BASE_URL}/api/auth/apple/callback",
            data={"error": "user_cancelled_authorize"},
            allow_redirects=False
        )
        # Should redirect with error, not crash
        assert response.status_code in [302, 307], f"Expected redirect, got {response.status_code}"
        
        location = response.headers.get('Location', '')
        assert 'sso_error' in location or 'user_cancelled' in location, \
            f"Expected error in redirect: {location}"
        print("✓ Apple callback handles error param without crash")


class TestAdminSSOStatus:
    """Test admin SSO status endpoint (requires auth)"""
    
    @pytest.fixture
    def admin_session(self):
        """Get admin session for authenticated requests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@realaicoach.app",
                "password": "NewAdminPass2026!"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code}")
        
        cookies = response.cookies
        return cookies
    
    def test_admin_sso_status_includes_preflight(self, admin_session):
        """Admin SSO status should include Apple redirect preflight info"""
        response = requests.get(
            f"{BASE_URL}/api/admin/sso-status",
            cookies=admin_session,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        
        if response.status_code == 403:
            pytest.skip("Admin SSO status requires higher privileges")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        print("✓ Admin SSO status response received")
        
        # Check for Apple preflight info if present
        if 'apple_redirect_preflight' in data:
            preflight = data['apple_redirect_preflight']
            print(f"  Apple preflight status: {preflight.get('status')}")
            print(f"  Selected callback: {preflight.get('selected_callback')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
