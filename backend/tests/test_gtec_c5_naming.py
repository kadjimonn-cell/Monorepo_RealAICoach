"""
Test GTEC C5 naming update verification.
Validates that GTEC naming has been updated from GTEC Scan v2/GTEC v2 to GTEC C5.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_risk_engine_admin_blocked(response: requests.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        return False
    detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
    return code in {"risk_engine_admin_api_blocked", "risk_engine_id_verification_required"}


def _skip_if_admin_blocked(response: requests.Response, context: str):
    if _is_risk_engine_admin_blocked(response):
        pytest.skip(f"{context} blocked by risk engine containment")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    data = response.json()
    token = data.get("session_token") or data.get("token") or response.cookies.get("session_token")
    if not token:
        pytest.skip("Admin token missing in login JSON/cookies")
    return token


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth token."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }


class TestGtecC5NamingBackend:
    """Backend API tests for GTEC C5 naming."""

    def test_directive_endpoint_returns_gtec_c5_system_name(self, admin_headers):
        """Verify /api/admin/gtec-scan-v2/directive returns system_name=GTEC C5."""
        response = requests.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/directive",
            headers=admin_headers
        )
        _skip_if_admin_blocked(response, "gtec-c5 directive")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify system_name is GTEC C5
        assert "system_name" in data, "Response should contain system_name field"
        assert data["system_name"] == "GTEC C5", f"Expected 'GTEC C5', got '{data['system_name']}'"
        
        # Verify other expected fields
        assert "directive_text" in data, "Response should contain directive_text"
        assert "always_active" in data, "Response should contain always_active"
        assert data["always_active"] is True, "always_active should be True"
        assert "non_disableable" in data, "Response should contain non_disableable"
        assert data["non_disableable"] is True, "non_disableable should be True"
        
        print(f"✓ Directive endpoint returns system_name: {data['system_name']}")

    def test_policy_effective_endpoint_returns_autonomous_mode(self, admin_headers):
        """Verify /api/admin/gtec-scan-v2/policy/effective returns autonomous_only mode."""
        response = requests.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective",
            headers=admin_headers
        )
        _skip_if_admin_blocked(response, "gtec-c5 policy effective")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify autonomous mode
        assert data.get("mode") == "autonomous_only", f"Expected mode 'autonomous_only', got '{data.get('mode')}'"
        assert data.get("manual_input_allowed") is False, "manual_input_allowed should be False"
        assert data.get("policy_locked") is True, "policy_locked should be True"
        
        print(f"✓ Policy effective endpoint returns mode: {data.get('mode')}")

    def test_schedule_endpoint_returns_valid_schedule(self, admin_headers):
        """Verify /api/admin/gtec-scan-v2/schedule returns valid schedule data."""
        response = requests.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/schedule",
            headers=admin_headers
        )
        _skip_if_admin_blocked(response, "gtec-c5 schedule")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify schedule fields exist
        assert "enabled" in data, "Response should contain enabled field"
        assert "interval_hours" in data, "Response should contain interval_hours field"
        
        print(f"✓ Schedule endpoint returns enabled: {data.get('enabled')}, interval_hours: {data.get('interval_hours')}")

    def test_latest_endpoint_returns_valid_response(self, admin_headers):
        """Verify /api/admin/gtec-scan-v2/latest returns valid response."""
        response = requests.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/latest",
            headers=admin_headers
        )
        _skip_if_admin_blocked(response, "gtec-c5 latest")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Response should have report field (may be null if no scans yet)
        assert "report" in data, "Response should contain report field"
        
        print(f"✓ Latest endpoint returns valid response, report present: {data.get('report') is not None}")

    def test_history_endpoint_returns_valid_response(self, admin_headers):
        """Verify /api/admin/gtec-scan-v2/history returns valid response."""
        response = requests.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/history",
            headers=admin_headers
        )
        _skip_if_admin_blocked(response, "gtec-c5 history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Response should have items and count fields
        assert "items" in data, "Response should contain items field"
        assert "count" in data, "Response should contain count field"
        assert isinstance(data["items"], list), "items should be a list"
        
        print(f"✓ History endpoint returns {data.get('count')} items")


class TestGtecC5NamingNoV2Strings:
    """Verify no remaining v2 naming strings in API response metadata fields (not directive text content)."""

    def test_directive_system_name_is_gtec_c5(self, admin_headers):
        """Verify directive response system_name field is 'GTEC C5' (not checking directive_text content)."""
        response = requests.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/directive",
            headers=admin_headers
        )
        _skip_if_admin_blocked(response, "gtec-c5 directive naming")
        assert response.status_code == 200
        data = response.json()
        
        # Check system_name field specifically (not the directive_text which is a policy document)
        assert data.get("system_name") == "GTEC C5", f"system_name should be 'GTEC C5', got '{data.get('system_name')}'"
        
        # Note: directive_text is a policy document and may contain historical references
        # The key is that the system_name field is updated to GTEC C5
        
        print(f"✓ Directive system_name is correctly set to: {data.get('system_name')}")

    def test_policy_response_no_v2_strings(self, admin_headers):
        """Verify policy response doesn't contain 'GTEC v2' or 'GTEC Scan v2' strings."""
        response = requests.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective",
            headers=admin_headers
        )
        _skip_if_admin_blocked(response, "gtec-c5 policy naming")
        assert response.status_code == 200
        response_text = response.text.lower()
        
        # Check for old naming patterns in policy metadata
        assert "gtec v2" not in response_text, "Response should not contain 'GTEC v2'"
        assert "gtec scan v2" not in response_text, "Response should not contain 'GTEC Scan v2'"
        
        print("✓ Policy response contains no v2 naming strings")
