"""
Test Payment Trust Assurance API - Static vs Live mode based on user role
Tests the audience-mode split: static/public for non-admin, live/admin for admin users
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
REGULAR_USER_EMAIL = "ui.test.new.1779211745@example.com"
REGULAR_USER_PASSWORD = "UiTestNew#2026Aa!"


class TestPaymentTrustAssuranceAPI:
    """Tests for GET /api/payments/trust/assurance endpoint"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated session for admin user"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")
        return session

    @pytest.fixture(scope="class")
    def regular_user_session(self):
        """Get authenticated session for regular (non-admin) user"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": REGULAR_USER_EMAIL,
            "password": REGULAR_USER_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Regular user login failed: {response.status_code} - {response.text[:200]}")
        return session

    @pytest.fixture(scope="class")
    def unauthenticated_session(self):
        """Get unauthenticated session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session

    # ==================== Non-Admin User Tests ====================

    def test_non_admin_gets_static_mode(self, regular_user_session):
        """Non-admin authenticated user should get mode_effective=static"""
        response = regular_user_session.get(f"{BASE_URL}/api/payments/trust/assurance")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        assert data.get("mode_effective") == "static", f"Expected mode_effective=static, got {data.get('mode_effective')}"
        assert data.get("audience") == "public", f"Expected audience=public, got {data.get('audience')}"
        assert not data.get("viewer_is_admin"), f"Expected viewer_is_admin=False, got {data.get('viewer_is_admin')}"
        assert data.get("data_source") == "policy", f"Expected data_source=policy, got {data.get('data_source')}"
        print("PASS: Non-admin user gets mode_effective=static, audience=public")

    def test_non_admin_cannot_force_live_mode_via_query_params(self, regular_user_session):
        """Non-admin user cannot force live mode by passing mode=live query param"""
        # Try to force live mode via query param
        response = regular_user_session.get(f"{BASE_URL}/api/payments/trust/assurance?mode=live")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Should still be static regardless of query param
        assert data.get("mode_effective") == "static", f"Non-admin should not be able to force live mode, got {data.get('mode_effective')}"
        assert not data.get("viewer_is_admin"), "viewer_is_admin should be False"
        print("PASS: Non-admin cannot force live mode via query params")

    def test_non_admin_with_provider_param(self, regular_user_session):
        """Non-admin user with provider param should still get static mode"""
        response = regular_user_session.get(f"{BASE_URL}/api/payments/trust/assurance?provider=stripe&context=checkout")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("mode_effective") == "static"
        assert data.get("provider") == "stripe"
        assert data.get("context") == "checkout"
        print("PASS: Non-admin with provider=stripe gets static mode")

    # ==================== Admin User Tests ====================

    def test_admin_gets_live_mode(self, admin_session):
        """Admin user should get mode_effective=live"""
        response = admin_session.get(f"{BASE_URL}/api/payments/trust/assurance")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        assert data.get("mode_effective") == "live", f"Expected mode_effective=live, got {data.get('mode_effective')}"
        assert data.get("audience") == "admin", f"Expected audience=admin, got {data.get('audience')}"
        assert data.get("viewer_is_admin"), f"Expected viewer_is_admin=True, got {data.get('viewer_is_admin')}"
        assert data.get("data_source") == "runtime", f"Expected data_source=runtime, got {data.get('data_source')}"
        print("PASS: Admin user gets mode_effective=live, audience=admin")

    def test_admin_with_provider_param(self, admin_session):
        """Admin user with provider param should get live mode"""
        response = admin_session.get(f"{BASE_URL}/api/payments/trust/assurance?provider=paypal&context=billing")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("mode_effective") == "live"
        assert data.get("provider") == "paypal"
        assert data.get("context") == "billing"
        assert data.get("viewer_is_admin")
        print("PASS: Admin with provider=paypal gets live mode")

    def test_admin_with_all_providers(self, admin_session):
        """Admin user requesting all providers should get live mode"""
        response = admin_session.get(f"{BASE_URL}/api/payments/trust/assurance?provider=all")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("mode_effective") == "live"
        assert data.get("provider") == "all"
        # provider_status should be a list for 'all' provider
        provider_status = data.get("provider_status")
        assert isinstance(provider_status, list), "Expected provider_status to be list for provider=all"
        print("PASS: Admin with provider=all gets live mode with provider list")

    # ==================== Unauthenticated User Tests ====================

    def test_unauthenticated_requires_auth(self, unauthenticated_session):
        """Unauthenticated user should get 401 (endpoint requires authentication)"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/payments/trust/assurance")
        # Endpoint requires authentication to determine user role
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got {response.status_code}"
        print("PASS: Unauthenticated user gets 401 (auth required)")

    # ==================== Response Structure Tests ====================

    def test_response_contains_required_fields(self, regular_user_session):
        """Response should contain all required fields"""
        response = regular_user_session.get(f"{BASE_URL}/api/payments/trust/assurance")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = [
            "provider", "provider_label", "context", "checked_at",
            "overall_status", "warnings", "settings", "signals",
            "messages", "connection", "provider_status", "mode_effective",
            "data_source", "compliance_indicators", "audience", "viewer_is_admin"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print("PASS: Response contains all required fields")

    def test_signals_structure(self, regular_user_session):
        """Signals array should have proper structure"""
        response = regular_user_session.get(f"{BASE_URL}/api/payments/trust/assurance")
        assert response.status_code == 200
        
        data = response.json()
        signals = data.get("signals", [])
        assert isinstance(signals, list), "signals should be a list"
        assert len(signals) > 0, "signals should not be empty"
        
        # Check signal structure
        for signal in signals:
            assert "id" in signal, "signal should have id"
            assert "label" in signal, "signal should have label"
            assert "status" in signal, "signal should have status"
            assert "message" in signal, "signal should have message"
        print("PASS: Signals have proper structure")

    def test_static_mode_has_verified_status(self, regular_user_session):
        """Static mode should have overall_status=verified (no warnings)"""
        response = regular_user_session.get(f"{BASE_URL}/api/payments/trust/assurance")
        assert response.status_code == 200
        
        data = response.json()
        # In static mode, overall_status should be verified (policy assurance)
        assert data.get("overall_status") == "verified", f"Expected overall_status=verified in static mode, got {data.get('overall_status')}"
        # Warnings should be empty in static mode
        warnings = data.get("warnings", [])
        assert len(warnings) == 0, f"Expected no warnings in static mode, got {warnings}"
        print("PASS: Static mode has verified status with no warnings")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
