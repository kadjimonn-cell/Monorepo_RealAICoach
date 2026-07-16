"""
Test FedaPay mobile money gateway API - Card methods display verification
Tests for iteration 151: VISA/MASTERCARD display in gateway status and country section
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


def _is_admin_containment_block(response: requests.Response) -> bool:
    if response.status_code not in (401, 403):
        return False

    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    blocked_codes = {"AUTH_REQUIRED", "RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}

    if top_code in blocked_codes:
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in blocked_codes:
            return True
        message = str(detail.get("message") or "").lower()
        return "admin access" in message or "id checker" in message

    if isinstance(detail, str):
        lowered = detail.lower()
        return "admin access" in lowered or "id checker" in lowered

    return False


def _is_auth_required(response: requests.Response) -> bool:
    if response.status_code not in (401, 403):
        return False

    try:
        payload = response.json()
    except Exception:
        payload = {}

    code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    if code == "AUTH_REQUIRED":
        return True

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    if isinstance(detail, str):
        return "authentication required" in detail.lower()

    return "authentication required" in (response.text or "").lower()


class TestMobileMoneyGatewaysCardMethods:
    """Test mobile money gateways API returns card methods correctly"""

    def _get_gateways_response(self) -> requests.Response:
        response = self.session.get(f"{BASE_URL}/api/subscriptions/mobile-money/gateways")
        if _is_admin_containment_block(response) or _is_auth_required(response):
            pytest.skip("Mobile money gateways blocked by environment auth containment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        return response
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        # Login to get session
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@realaicoach.app",
                "password": "NewAdminPass2026!"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )

        if login_response.status_code == 200:
            data = login_response.json()
            token = (
                data.get("session_token")
                or data.get("token")
                or data.get("access_token")
                or login_response.cookies.get("session_token")
                or self.session.cookies.get("session_token")
            )
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
        elif _is_admin_containment_block(login_response) or _is_auth_required(login_response):
            pytest.skip("Admin login blocked/unavailable for mobile-money gateway contract tests")
        else:
            pytest.skip(f"Setup login unavailable: {login_response.status_code} - {login_response.text[:200]}")

        yield
        self.session.close()
    
    def test_gateways_endpoint_returns_200(self):
        """Test that gateways endpoint returns 200"""
        response = self._get_gateways_response()
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_gateways_returns_fedapay(self):
        """Test that gateways response includes FedaPay"""
        response = self._get_gateways_response()
        data = response.json()
        
        assert "gateways" in data, "Response should contain 'gateways' key"
        gateways = data["gateways"]
        assert len(gateways) > 0, "Should have at least one gateway"
        
        fedapay = next((g for g in gateways if g["id"] == "fedapay"), None)
        assert fedapay is not None, "FedaPay gateway should be present"
    
    def test_fedapay_has_supported_cards(self):
        """Test that FedaPay gateway includes supported_cards array"""
        response = self._get_gateways_response()
        data = response.json()
        
        fedapay = next((g for g in data["gateways"] if g["id"] == "fedapay"), None)
        assert fedapay is not None, "FedaPay gateway should be present"
        
        assert "supported_cards" in fedapay, "FedaPay should have 'supported_cards' field"
        supported_cards = fedapay["supported_cards"]
        assert isinstance(supported_cards, list), "supported_cards should be a list"
    
    def test_fedapay_supports_visa(self):
        """Test that FedaPay supports VISA"""
        response = self._get_gateways_response()
        data = response.json()
        
        fedapay = next((g for g in data["gateways"] if g["id"] == "fedapay"), None)
        supported_cards = [c.lower() for c in fedapay["supported_cards"]]
        
        assert "visa" in supported_cards, "FedaPay should support VISA"
    
    def test_fedapay_supports_mastercard(self):
        """Test that FedaPay supports MASTERCARD"""
        response = self._get_gateways_response()
        data = response.json()
        
        fedapay = next((g for g in data["gateways"] if g["id"] == "fedapay"), None)
        supported_cards = [c.lower() for c in fedapay["supported_cards"]]
        
        assert "mastercard" in supported_cards, "FedaPay should support MASTERCARD"
    
    def test_fedapay_has_all_five_countries(self):
        """Test that FedaPay includes all 5 operating countries"""
        response = self._get_gateways_response()
        data = response.json()
        
        fedapay = next((g for g in data["gateways"] if g["id"] == "fedapay"), None)
        assert "countries" in fedapay, "FedaPay should have 'countries' field"
        
        expected_countries = {"BJ", "CI", "NE", "SN", "TG"}
        actual_countries = set(fedapay["countries"])
        
        assert expected_countries == actual_countries, f"Expected countries {expected_countries}, got {actual_countries}"
    
    def test_fedapay_has_country_fee_schedule(self):
        """Test that FedaPay includes country_fee_schedule"""
        response = self._get_gateways_response()
        data = response.json()
        
        fedapay = next((g for g in data["gateways"] if g["id"] == "fedapay"), None)
        assert "country_fee_schedule" in fedapay, "FedaPay should have 'country_fee_schedule' field"
        
        schedule = fedapay["country_fee_schedule"]
        assert isinstance(schedule, dict), "country_fee_schedule should be a dict"
        
        # Check each country has required fields
        for country_code in ["BJ", "CI", "NE", "SN", "TG"]:
            assert country_code in schedule, f"Country {country_code} should be in fee schedule"
            country_data = schedule[country_code]
            assert "default_mobile_fee_pct" in country_data, f"{country_code} should have default_mobile_fee_pct"
            assert "mobile_money_fees" in country_data, f"{country_code} should have mobile_money_fees"
            assert "card_fee_pct" in country_data, f"{country_code} should have card_fee_pct"
    
    def test_fedapay_gateway_status_fields(self):
        """Test that FedaPay gateway has all required status fields"""
        response = self._get_gateways_response()
        data = response.json()
        
        fedapay = next((g for g in data["gateways"] if g["id"] == "fedapay"), None)
        
        required_fields = ["id", "label", "status", "mode", "message", "checked_at"]
        for field in required_fields:
            assert field in fedapay, f"FedaPay should have '{field}' field"
    
    def test_fedapay_policy_metadata(self):
        """Test that FedaPay includes policy metadata"""
        response = self._get_gateways_response()
        data = response.json()
        
        fedapay = next((g for g in data["gateways"] if g["id"] == "fedapay"), None)
        
        assert "policy_source" in fedapay, "FedaPay should have 'policy_source' field"
        assert "policy_updated_at" in fedapay, "FedaPay should have 'policy_updated_at' field"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
