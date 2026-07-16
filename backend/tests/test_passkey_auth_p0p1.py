"""
P0/P1 Passkey/WebAuthn Auth Flow Tests
Tests for fingerprint/passkey enrollment eligibility and auth endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestAuthSanity:
    """P0: Backend auth sanity tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
    
    def test_login_endpoint_returns_200(self):
        """P0: /api/auth/login returns 200 with valid credentials"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "user_id" in data, "Response missing user_id"
        assert "email" in data, "Response missing email"
        print(f"PASS: Login returned 200, user_id={data.get('user_id')}")
    
    def test_me_endpoint_unauthenticated_returns_401(self):
        """P0: /api/auth/me returns 401 when unauthenticated"""
        fresh_session = requests.Session()
        response = fresh_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: /api/auth/me returns 401 for unauthenticated requests")
    
    def test_me_endpoint_authenticated_returns_200(self):
        """P0: /api/auth/me returns 200 when authenticated"""
        # Login first
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        # Now check /me
        me_resp = self.session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200, f"Expected 200, got {me_resp.status_code}: {me_resp.text}"
        data = me_resp.json()
        assert data.get("email") == ADMIN_EMAIL, f"Email mismatch: {data.get('email')}"
        print("PASS: /api/auth/me returns 200 with correct user data")


class TestPasskeyEnrollmentEligibility:
    """P0/P1: Passkey enrollment eligibility endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
    
    def test_enrollment_eligibility_unauthenticated_returns_401(self):
        """P0: /api/auth/biometric/enrollment-eligibility returns 401 when unauthenticated"""
        fresh_session = requests.Session()
        response = fresh_session.get(f"{BASE_URL}/api/auth/biometric/enrollment-eligibility")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: enrollment-eligibility returns 401 for unauthenticated requests")
    
    def test_enrollment_eligibility_authenticated_returns_200(self):
        """P0: /api/auth/biometric/enrollment-eligibility returns 200 when authenticated"""
        # Login first
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        # Check enrollment eligibility
        response = self.session.get(f"{BASE_URL}/api/auth/biometric/enrollment-eligibility")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "should_prompt" in data, "Response missing should_prompt field"
        assert "has_passkey" in data, "Response missing has_passkey field"
        assert "rollout_enabled" in data, "Response missing rollout_enabled field"
        assert "cooldown_elapsed" in data, "Response missing cooldown_elapsed field"
        
        print(f"PASS: enrollment-eligibility returns 200 with data: should_prompt={data.get('should_prompt')}, has_passkey={data.get('has_passkey')}")


class TestHasPasskeyEndpoint:
    """P1: has-passkey endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
    
    def test_has_passkey_with_valid_user_id(self):
        """P1: /api/auth/biometric/has-passkey returns correct response for valid user_id"""
        # First get a valid user_id via login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        user_id = login_resp.json().get("user_id")
        
        # Check has-passkey endpoint
        response = self.session.get(f"{BASE_URL}/api/auth/biometric/has-passkey?user_id={user_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "has_passkey" in data, "Response missing has_passkey field"
        assert isinstance(data["has_passkey"], bool), "has_passkey should be boolean"
        print(f"PASS: has-passkey returns 200 with has_passkey={data.get('has_passkey')}")
    
    def test_has_passkey_without_user_id_returns_error(self):
        """P1: /api/auth/biometric/has-passkey returns error without user_id"""
        response = self.session.get(f"{BASE_URL}/api/auth/biometric/has-passkey")
        # Should return 400, 401, or 422 for missing required parameter
        assert response.status_code in [400, 401, 422], f"Expected 400/401/422, got {response.status_code}"
        print(f"PASS: has-passkey returns {response.status_code} when user_id is missing")


class TestAuthLookupEndpoint:
    """P1: Auth lookup endpoint for passkey mode"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
    
    def test_auth_lookup_returns_user_info(self):
        """P1: /api/auth/lookup returns user info including passkey status"""
        response = self.session.get(f"{BASE_URL}/api/auth/lookup?email={ADMIN_EMAIL}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "exists" in data, "Response missing exists field"
        assert "user_id" in data, "Response missing user_id field"
        assert "has_passkey" in data, "Response missing has_passkey field"
        assert "has_pin" in data, "Response missing has_pin field"
        
        print(f"PASS: auth/lookup returns user info: exists={data.get('exists')}, has_passkey={data.get('has_passkey')}")


class TestEnrollmentDismiss:
    """P1: Enrollment dismiss endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
    
    def test_enrollment_dismiss_unauthenticated_returns_401(self):
        """P1: /api/auth/biometric/enrollment-dismiss returns 401 when unauthenticated"""
        fresh_session = requests.Session()
        response = fresh_session.post(f"{BASE_URL}/api/auth/biometric/enrollment-dismiss")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: enrollment-dismiss returns 401 for unauthenticated requests")
    
    def test_enrollment_dismiss_authenticated_returns_200(self):
        """P1: /api/auth/biometric/enrollment-dismiss returns 200 when authenticated"""
        # Login first
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        # Dismiss enrollment prompt
        response = self.session.post(f"{BASE_URL}/api/auth/biometric/enrollment-dismiss")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("success") == True, "Response should have success=True"
        assert "dismissed_at" in data, "Response missing dismissed_at field"
        print(f"PASS: enrollment-dismiss returns 200 with dismissed_at={data.get('dismissed_at')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
