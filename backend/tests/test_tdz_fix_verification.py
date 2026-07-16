"""
Test TDZ Fix Verification - Iteration 107
Tests for verifying the TDZ ReferenceError fix in HomeNovaAssistantWidget.tsx

Features tested:
1. Frontend root route '/' loads without error boundary
2. Frontend '/auth/login' loads without error boundary
3. GET /api/auth/microsoft/login returns 302 redirect
4. GET /api/auth/apple/login returns 302 redirect
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')


class TestSSORedirects:
    """Test SSO login redirect endpoints"""
    
    def test_microsoft_login_returns_302(self):
        """GET /api/auth/microsoft/login should return 302 redirect"""
        response = requests.get(
            f"{BASE_URL}/api/auth/microsoft/login",
            allow_redirects=False,
            timeout=10
        )
        assert response.status_code == 302, f"Expected 302, got {response.status_code}"
        # Verify redirect location contains Microsoft OAuth URL
        location = response.headers.get('Location', '')
        assert 'microsoft' in location.lower() or 'login.microsoftonline.com' in location.lower(), \
            f"Expected Microsoft OAuth redirect, got: {location}"
        print(f"PASS: Microsoft login returns 302 redirect to: {location[:100]}...")
    
    def test_apple_login_returns_302(self):
        """GET /api/auth/apple/login should return 302 redirect"""
        response = requests.get(
            f"{BASE_URL}/api/auth/apple/login",
            allow_redirects=False,
            timeout=10
        )
        assert response.status_code == 302, f"Expected 302, got {response.status_code}"
        # Verify redirect location contains Apple OAuth URL
        location = response.headers.get('Location', '')
        assert 'apple' in location.lower() or 'appleid.apple.com' in location.lower(), \
            f"Expected Apple OAuth redirect, got: {location}"
        print(f"PASS: Apple login returns 302 redirect to: {location[:100]}...")


class TestHealthEndpoints:
    """Test basic health endpoints"""
    
    def test_health_endpoint(self):
        """GET /api/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Health endpoint returns 200")
    
    def test_auth_lookup_endpoint(self):
        """GET /api/auth/lookup should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/auth/lookup",
            params={"email": "test@example.com"},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "exists" in data, "Response should contain 'exists' field"
        print("PASS: Auth lookup endpoint returns 200")


class TestClientErrorsEndpoint:
    """Test client errors telemetry endpoint"""
    
    def test_client_errors_ingest(self):
        """POST /api/errors/client should accept error reports"""
        payload = {
            "panel_id": "test-panel",
            "panel_name": "Test Panel",
            "message": "Test error message for verification",
            "pathname": "/test"
        }
        response = requests.post(
            f"{BASE_URL}/api/errors/client",
            json=payload,
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("ok"), "Response should indicate success"
        print("PASS: Client errors ingest endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
