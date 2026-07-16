"""
GTEC C5 Incident Lifecycle Timeline API Tests
----------------------------------------------
Tests for the new /api/admin/gtec-scan-v2/incidents/lifecycle-timeline endpoint
and regression tests for existing release certificate/drill APIs.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


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


def _skip_if_admin_blocked(response: requests.Response, context: str) -> None:
    if _is_risk_engine_admin_blocked(response):
        pytest.skip(f"{context} blocked by risk engine containment")


def _admin_get(path_with_query: str, auth_headers: dict, context: str) -> requests.Response:
    response = requests.get(f"{BASE_URL}{path_with_query}", headers=auth_headers)
    _skip_if_admin_blocked(response, context)
    return response


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")
    data = response.json()
    token = data.get("session_token") or data.get("token") or response.cookies.get("session_token")
    if not token:
        pytest.skip("Admin token unavailable in login JSON/cookies")
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for admin requests"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


class TestIncidentLifecycleTimeline:
    """Tests for /api/admin/gtec-scan-v2/incidents/lifecycle-timeline endpoint"""

    def test_lifecycle_timeline_returns_200(self, auth_headers):
        """Verify endpoint returns 200 OK"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/incidents/lifecycle-timeline",
            auth_headers,
            "incident lifecycle timeline",
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_lifecycle_timeline_response_structure(self, auth_headers):
        """Verify response has correct top-level structure"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/incidents/lifecycle-timeline",
            auth_headers,
            "incident lifecycle timeline",
        )
        assert response.status_code == 200
        data = response.json()
        
        # Top-level fields
        assert "items" in data, "Missing 'items' field"
        assert "count" in data, "Missing 'count' field"
        assert "generated_at" in data, "Missing 'generated_at' field"
        
        # items should be a list
        assert isinstance(data["items"], list), "'items' should be a list"
        # count should match items length
        assert data["count"] == len(data["items"]), "count should match items length"

    def test_lifecycle_timeline_item_structure(self, auth_headers):
        """Verify each item has required fields per API contract"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/incidents/lifecycle-timeline?limit=5",
            auth_headers,
            "incident lifecycle timeline limit=5",
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data["items"]) == 0:
            pytest.skip("No incidents in timeline to verify structure")
        
        item = data["items"][0]
        
        # Required fields per contract
        required_fields = [
            "incident_id",
            "incident_key",
            "label",
            "severity",
            "status",
            "containment",
            "clean_rescan_streak",
            "policy",
            "pending_verification_started_at",
            "pending_verification_deadline",
            "resolution_reason",
            "task_id",
            "internal_task_id",
            "updated_at",
            "events"
        ]
        
        for field in required_fields:
            assert field in item, f"Missing required field: {field}"

    def test_lifecycle_timeline_policy_structure(self, auth_headers):
        """Verify policy object has correct structure"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/incidents/lifecycle-timeline?limit=5",
            auth_headers,
            "incident lifecycle timeline policy structure",
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data["items"]) == 0:
            pytest.skip("No incidents in timeline to verify policy structure")
        
        item = data["items"][0]
        policy = item.get("policy", {})
        
        # Policy should have auto-close configuration
        assert "consecutive_clean_rescans_required" in policy, "Missing consecutive_clean_rescans_required in policy"
        assert "pending_verification_hours" in policy, "Missing pending_verification_hours in policy"

    def test_lifecycle_timeline_events_structure(self, auth_headers):
        """Verify events array has correct structure"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/incidents/lifecycle-timeline?limit=5",
            auth_headers,
            "incident lifecycle timeline events structure",
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data["items"]) == 0:
            pytest.skip("No incidents in timeline to verify events structure")
        
        item = data["items"][0]
        events = item.get("events", [])
        
        assert isinstance(events, list), "events should be a list"
        
        if len(events) > 0:
            event = events[0]
            assert "kind" in event, "Event missing 'kind' field"
            assert "at" in event, "Event missing 'at' field"

    def test_lifecycle_timeline_limit_parameter(self, auth_headers):
        """Verify limit parameter works correctly"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/incidents/lifecycle-timeline?limit=3",
            auth_headers,
            "incident lifecycle timeline limit=3",
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should return at most 3 items
        assert len(data["items"]) <= 3, f"Expected at most 3 items, got {len(data['items'])}"

    def test_lifecycle_timeline_requires_auth(self):
        """Verify endpoint requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/incidents/lifecycle-timeline"
        )
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"


class TestReleaseCertificateRegression:
    """Regression tests for /api/admin/gtec-scan-v2/release-certificate endpoint"""

    def test_release_certificate_returns_200(self, auth_headers):
        """Verify release certificate endpoint still works"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/release-certificate",
            auth_headers,
            "release certificate",
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_release_certificate_structure(self, auth_headers):
        """Verify release certificate has required fields"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/release-certificate",
            auth_headers,
            "release certificate structure",
        )
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "certificate_id" in data, "Missing certificate_id"
        assert "trust_score_percent" in data, "Missing trust_score_percent"
        assert "checks" in data, "Missing checks"
        
        # Verify checks structure
        checks = data.get("checks", {})
        expected_checks = [
            "theme_v2",
            "email_v7_darkmode",
            "i18n_missing_open",
            "pipeline_enforcement",
            "db_security_hardening",
            "white_screen_sentry",
            "responsive_viewport_matrix"
        ]
        
        for check in expected_checks:
            assert check in checks, f"Missing check: {check}"


class TestGoNoGoDrillRegression:
    """Regression tests for /api/admin/gtec-scan-v2/pipeline/go-no-go-drill/latest endpoint"""

    def test_go_no_go_drill_latest_returns_200(self, auth_headers):
        """Verify go-no-go drill latest endpoint still works"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/pipeline/go-no-go-drill/latest",
            auth_headers,
            "go-no-go drill latest",
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_go_no_go_drill_structure(self, auth_headers):
        """Verify go-no-go drill response structure"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/pipeline/go-no-go-drill/latest",
            auth_headers,
            "go-no-go drill structure",
        )
        assert response.status_code == 200
        data = response.json()
        
        # Top-level fields
        assert "drill" in data, "Missing 'drill' field"
        assert "generated_at" in data, "Missing 'generated_at' field"
        
        drill = data.get("drill")
        if drill:
            # Drill should have decision and validation
            assert "decision" in drill, "Missing 'decision' in drill"
            assert "validation" in drill, "Missing 'validation' in drill"


class TestIncidentsEndpointRegression:
    """Regression tests for /api/admin/gtec-scan-v2/incidents endpoint"""

    def test_incidents_returns_200(self, auth_headers):
        """Verify incidents endpoint still works"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/incidents",
            auth_headers,
            "incidents endpoint",
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_incidents_structure(self, auth_headers):
        """Verify incidents response structure"""
        response = _admin_get(
            "/api/admin/gtec-scan-v2/incidents",
            auth_headers,
            "incidents structure",
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "items" in data, "Missing 'items' field"
        assert "count" in data, "Missing 'count' field"
        assert "status_filter" in data, "Missing 'status_filter' field"
