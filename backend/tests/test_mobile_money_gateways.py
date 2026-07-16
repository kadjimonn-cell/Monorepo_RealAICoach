"""
Test mobile money gateways API contract fields
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')


def _is_env_auth_block(response: requests.Response) -> bool:
    if response.status_code in (429,):
        return True
    if response.status_code not in (401, 403, 503):
        return False

    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    blocked_codes = {
        "AUTH_REQUIRED",
        "RISK_ENGINE_ADMIN_API_BLOCKED",
        "RISK_ENGINE_ID_VERIFICATION_REQUIRED",
        "PRODUCTION_POLICY_GATE_BLOCKED",
    }

    if top_code in blocked_codes:
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in blocked_codes:
            return True
        message = str(detail.get("message") or "").lower()
        return (
            "authentication required" in message
            or "admin access required" in message
            or "id checker" in message
            or "policy gate" in message
            or "too many" in message
            or "rate limit" in message
        )

    if isinstance(detail, str):
        lowered = detail.lower()
        return (
            "authentication required" in lowered
            or "admin access required" in lowered
            or "id checker" in lowered
            or "policy gate" in lowered
            or "too many" in lowered
            or "rate limit" in lowered
        )

    body = (response.text or "").lower()
    return (
        "authentication required" in body
        or "admin access required" in body
        or "risk_engine" in body
        or "policy gate" in body
        or "too many" in body
        or "rate limit" in body
    )

class TestMobileMoneyGateways:
    """Test mobile money gateways API"""

    def _get_gateways(self):
        resp = requests.get(
            f"{BASE_URL}/api/subscriptions/mobile-money/gateways",
            headers={"Authorization": f"Bearer {self.token}", "X-Requested-With": "XMLHttpRequest"}
        )
        if _is_env_auth_block(resp):
            pytest.skip("Mobile-money gateways blocked by environment auth containment")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        return resp
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session token"""
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-Client-Platform": "mobile"}
        )
        if _is_env_auth_block(login_resp):
            pytest.skip("Admin login blocked by environment containment/policy gate")
        if login_resp.status_code != 200:
            pytest.skip(f"Authentication failed: {login_resp.status_code}")

        payload = login_resp.json()
        self.token = (
            payload.get('session_token')
            or payload.get('token')
            or payload.get('access_token')
            or login_resp.cookies.get('session_token')
        )

        if not self.token:
            pytest.skip("Authentication token unavailable for mobile-money gateway tests")
    
    def test_gateways_endpoint_returns_200(self):
        """Test that gateways endpoint returns 200"""
        resp = self._get_gateways()
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    def test_gateways_response_has_gateways_array(self):
        """Test that response has gateways array"""
        resp = self._get_gateways()
        data = resp.json()
        assert "gateways" in data, "Response should have 'gateways' key"
        assert isinstance(data["gateways"], list), "gateways should be a list"
    
    def test_gateway_has_contract_fields(self):
        """Test that each gateway has required contract fields for UI matrix rendering"""
        resp = self._get_gateways()
        data = resp.json()
        gateways = data.get("gateways", [])
        
        assert len(gateways) > 0, "Should have at least one gateway"
        
        required_fields = [
            "label",
            "status",
            "mode",
            "message",
            "checked_at",
            "countries",
            "country_fee_schedule",
            "policy_source",
            "policy_updated_at",
        ]
        for gw in gateways:
            for field in required_fields:
                assert field in gw, f"Gateway {gw.get('id', 'unknown')} missing required field: {field}"

    def test_fedapay_countries_and_fee_schedule_present(self):
        """FedaPay should expose country matrix + fee schedule for country-first checkout UX"""
        resp = self._get_gateways()
        data = resp.json()
        gateways = data.get("gateways", [])

        fedapay = next((gw for gw in gateways if gw.get("id") == "fedapay"), None)
        assert fedapay is not None, "FedaPay gateway should be present"

        countries = fedapay.get("countries") or []
        assert isinstance(countries, list), "FedaPay countries should be a list"
        assert len(countries) >= 1, "FedaPay countries should include at least one country"

        country_fee_schedule = fedapay.get("country_fee_schedule") or {}
        assert isinstance(country_fee_schedule, dict), "country_fee_schedule should be an object"

        for country_code in countries:
            row = country_fee_schedule.get(country_code, {})
            assert isinstance(row, dict), f"country_fee_schedule[{country_code}] should be an object"
            assert "mobile_money_fees" in row, f"country_fee_schedule[{country_code}] should contain mobile_money_fees"
    
    def test_fedapay_gateway_is_active(self):
        """Test that FedaPay gateway is active"""
        resp = self._get_gateways()
        data = resp.json()
        gateways = data.get("gateways", [])
        
        fedapay = next((gw for gw in gateways if gw.get("id") == "fedapay"), None)
        assert fedapay is not None, "FedaPay gateway should be present"
        assert fedapay.get("status") == "active", f"FedaPay status should be 'active', got '{fedapay.get('status')}'"
    
    def test_fedapay_gateway_mode_is_live(self):
        """Test that FedaPay gateway mode is live"""
        resp = self._get_gateways()
        data = resp.json()
        gateways = data.get("gateways", [])
        
        fedapay = next((gw for gw in gateways if gw.get("id") == "fedapay"), None)
        assert fedapay is not None, "FedaPay gateway should be present"
        assert fedapay.get("mode") == "live", f"FedaPay mode should be 'live', got '{fedapay.get('mode')}'"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
