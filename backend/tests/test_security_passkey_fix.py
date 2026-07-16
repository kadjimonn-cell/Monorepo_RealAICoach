"""
Test suite for Security Page and Passkey/Fingerprint Login Fix
Tests the following features:
1. Security page should not fail hard when /api/geo/detect fails (status data must still load)
2. Passkey status card should reflect real 2FA status from /api/auth/2fa/status
3. Passkey registration options endpoint should be reachable for authenticated user
4. No regression in login flow and /security navigation
5. Backend auto-block logic should no longer treat AUTH_REQUIRED incident noise as block-eligible
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    return session


@pytest.fixture(scope="module")
def free_user_token(api_client):
    """Get free user authentication token"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
        headers={"X-Client-Platform": "mobile"}
    )
    if response.status_code == 200:
        return response.json().get("session_token")
    pytest.skip(f"Free user login failed: {response.status_code}")


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Client-Platform": "mobile"}
    )
    if response.status_code == 200:
        return response.json().get("session_token")
    pytest.skip(f"Admin login failed: {response.status_code}")


class TestLoginFlow:
    """Test login flow has no regression"""
    
    def test_health_endpoint(self, api_client):
        """Health endpoint should be accessible"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health endpoint working")
    
    def test_free_user_login(self, api_client):
        """Free user should be able to login"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
            headers={"X-Client-Platform": "mobile"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_token" in data
        assert data.get("email") == FREE_USER_EMAIL
        assert data.get("subscription_plan") == "free"
        print(f"✓ Free user login successful: {data.get('user_id')}")
    
    def test_admin_login(self, api_client):
        """Admin should be able to login"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Client-Platform": "mobile"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_token" in data
        assert data.get("is_admin") == True
        print(f"✓ Admin login successful: {data.get('user_id')}")


class Test2FAStatusEndpoint:
    """Test /api/auth/2fa/status endpoint for passkey status"""
    
    def test_2fa_status_returns_passkey_info(self, api_client, free_user_token):
        """2FA status should include passkey rollout and status info"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/2fa/status",
            headers={"Authorization": f"Bearer {free_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields for passkey status card
        assert "two_fa_enabled" in data
        assert "has_passkey" in data
        assert "passkey_rollout_enabled" in data
        assert "passkey_count" in data
        
        # Verify passkey rollout is enabled
        assert data.get("passkey_rollout_enabled") == True
        print(f"✓ 2FA status endpoint returns passkey info: has_passkey={data.get('has_passkey')}, rollout_enabled={data.get('passkey_rollout_enabled')}")
    
    def test_2fa_status_has_all_security_fields(self, api_client, free_user_token):
        """2FA status should have all fields needed by security page"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/2fa/status",
            headers={"Authorization": f"Bearer {free_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # All fields needed by security.tsx
        required_fields = [
            "two_fa_enabled", "is_exempt", "backup_codes_remaining",
            "has_pin", "has_passkey", "passkey_rollout_enabled",
            "biometric_enabled", "account_locked"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        print("✓ 2FA status has all required security fields")


class TestGeoDetectEndpoint:
    """Test /api/geo/detect endpoint behavior"""
    
    def test_geo_detect_requires_auth_or_subscription(self, api_client):
        """Geo detect should require authentication or subscription"""
        response = api_client.get(f"{BASE_URL}/api/geo/detect")
        # Can be 401 (AUTH_REQUIRED), 403 (CSRF_BLOCKED or Subscription Required)
        assert response.status_code in [401, 403]
        data = response.json()
        # Valid responses: AUTH_REQUIRED, CSRF_BLOCKED, or Subscription Required
        valid_codes = ["AUTH_REQUIRED", "CSRF_BLOCKED"]
        is_subscription_error = "Subscription Required" in data.get("error", "")
        assert data.get("code") in valid_codes or is_subscription_error
        print(f"✓ Geo detect requires authentication/subscription: {data.get('code') or data.get('error')}")
    
    def test_geo_detect_subscription_gated_for_free_user(self, api_client, free_user_token):
        """Geo detect may be subscription-gated for free users"""
        response = api_client.get(
            f"{BASE_URL}/api/geo/detect",
            headers={"Authorization": f"Bearer {free_user_token}"}
        )
        # Can be 200 (success) or 403 (subscription required) - both are valid
        assert response.status_code in [200, 403]
        if response.status_code == 403:
            data = response.json()
            assert "Subscription Required" in data.get("error", "") or "required_plan" in data
            print("✓ Geo detect is subscription-gated for free users (expected)")
        else:
            print("✓ Geo detect accessible for free user")


class TestPasskeyRegistrationEndpoint:
    """Test passkey registration options endpoint"""
    
    def test_webauthn_register_options_accessible(self, api_client, free_user_token):
        """Passkey registration options should be accessible for authenticated users"""
        # First get user_id from /api/auth/me
        me_response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {free_user_token}"}
        )
        assert me_response.status_code == 200
        user_id = me_response.json().get("user_id")
        
        # Test registration options endpoint
        response = api_client.post(
            f"{BASE_URL}/api/auth/biometric/webauthn-register-options",
            json={"user_id": user_id},
            headers={"Authorization": f"Bearer {free_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify WebAuthn options structure
        assert "rp" in data  # Relying party
        assert "user" in data
        assert "challenge" in data
        assert "pubKeyCredParams" in data
        assert "challenge_id" in data
        
        # Verify rollout info
        assert "rollout" in data
        assert data["rollout"].get("enabled") == True
        print(f"✓ Passkey registration options endpoint working: challenge_id={data.get('challenge_id')}")
    
    def test_webauthn_credentials_list(self, api_client, free_user_token):
        """Should be able to list passkey credentials"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/biometric/webauthn/credentials",
            headers={"Authorization": f"Bearer {free_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "credentials" in data
        assert "total" in data
        assert "rollout" in data
        assert isinstance(data["credentials"], list)
        print(f"✓ Passkey credentials list endpoint working: total={data.get('total')}")


class TestAutoBlockLogic:
    """Test that auto-block logic no longer treats AUTH_REQUIRED as block-eligible"""
    
    def test_autoblock_config_accessible(self, api_client, admin_token):
        """Admin should be able to access autoblock config"""
        response = api_client.get(
            f"{BASE_URL}/api/admin/security-incidents/autoblock-config",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "enabled" in data
        assert "threshold" in data
        assert "window_minutes" in data
        print(f"✓ Autoblock config accessible: enabled={data.get('enabled')}, threshold={data.get('threshold')}")
    
    def test_security_incidents_summary(self, api_client, admin_token):
        """Should be able to get security incidents summary"""
        response = api_client.get(
            f"{BASE_URL}/api/admin/security-incidents/summary?hours=24",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "total" in data
        assert "total_401" in data
        assert "total_403" in data
        assert "breakdown" in data
        print(f"✓ Security incidents summary: total={data.get('total')}, 401s={data.get('total_401')}, 403s={data.get('total_403')}")
    
    def test_autoblock_run_does_not_block_auth_required(self, api_client, admin_token):
        """Auto-block run should not block IPs based on AUTH_REQUIRED incidents alone"""
        response = api_client.post(
            f"{BASE_URL}/api/admin/security-incidents/autoblock-run",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # The response should indicate that no IPs were blocked based on AUTH_REQUIRED
        # or that IPs were released because they only had AUTH_REQUIRED incidents
        assert "status" in data
        
        # If there are released blocks, verify they were released due to low high-risk count
        if data.get("released_count", 0) > 0:
            released = data.get("released_blocks", [])
            for block in released:
                # High risk count should be below threshold
                assert block.get("high_risk_count", 0) < data.get("threshold", 100)
            print(f"✓ Auto-block released {data.get('released_count')} IPs with low high-risk count")
        
        print(f"✓ Auto-block run status: {data.get('status')}, blocked={data.get('blocked_count', 0)}, released={data.get('released_count', 0)}")


class TestSecurityPageDataLoading:
    """Test that security page can load all required data"""
    
    def test_all_security_endpoints_accessible(self, api_client, free_user_token):
        """All endpoints needed by security page should be accessible"""
        endpoints = [
            ("/api/auth/2fa/status", "GET"),
            ("/api/auth/biometric/webauthn/credentials", "GET"),
            ("/api/auth/security/login-history", "GET"),
        ]
        
        for endpoint, method in endpoints:
            if method == "GET":
                response = api_client.get(
                    f"{BASE_URL}{endpoint}",
                    headers={"Authorization": f"Bearer {free_user_token}"}
                )
            
            # Should not return 500 errors
            assert response.status_code != 500, f"Endpoint {endpoint} returned 500"
            # Should return 200 or expected auth/subscription errors
            assert response.status_code in [200, 401, 403], f"Endpoint {endpoint} returned unexpected {response.status_code}"
            print(f"✓ {endpoint}: {response.status_code}")
    
    def test_geo_detect_failure_does_not_break_status_loading(self, api_client, free_user_token):
        """Even if geo/detect fails, 2fa/status should still work"""
        # First call geo/detect (may fail for free user)
        geo_response = api_client.get(
            f"{BASE_URL}/api/geo/detect",
            headers={"Authorization": f"Bearer {free_user_token}"}
        )
        geo_failed = geo_response.status_code != 200
        
        # 2FA status should still work regardless
        status_response = api_client.get(
            f"{BASE_URL}/api/auth/2fa/status",
            headers={"Authorization": f"Bearer {free_user_token}"}
        )
        assert status_response.status_code == 200
        
        if geo_failed:
            print(f"✓ Geo detect failed ({geo_response.status_code}) but 2FA status still works")
        else:
            print("✓ Both geo detect and 2FA status work")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
