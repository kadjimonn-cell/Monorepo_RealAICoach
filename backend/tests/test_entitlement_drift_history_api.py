"""
Entitlement Drift History API Tests
Tests for GET /api/admin/code-health/entitlement-drift/history endpoint
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
NON_ADMIN_EMAIL = "feature21.test.1781234530@example.com"
NON_ADMIN_PASSWORD = "Feature21Test#2026Aa"


class TestEntitlementDriftHistoryAPI:
    """Tests for entitlement drift audit history endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _admin_login(self):
        """Login as admin and return session with cookies"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return self.session

    def _non_admin_login(self):
        """Login as non-admin user and return session with cookies"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": NON_ADMIN_EMAIL, "password": NON_ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Non-admin login failed: {response.text}"
        return self.session

    def test_anonymous_access_blocked(self):
        """Anonymous users should be blocked with 401/403"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=7"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "admin" in data["detail"].lower() or "auth" in data["detail"].lower()

    def test_non_admin_access_blocked(self):
        """Non-admin authenticated users should be blocked with 403"""
        self._non_admin_login()
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=7"
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "admin" in data["detail"].lower()

    def test_admin_access_allowed(self):
        """Admin users should have access to the endpoint"""
        self._admin_login()
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=7"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_response_structure(self):
        """Response should have correct structure with latest, history, status_breakdown"""
        self._admin_login()
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=7"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level keys
        assert "latest" in data, "Missing 'latest' key"
        assert "history" in data, "Missing 'history' key"
        assert "total" in data, "Missing 'total' key"
        assert "status_breakdown" in data, "Missing 'status_breakdown' key"
        assert "attention_count" in data, "Missing 'attention_count' key"
        
        # Check status_breakdown structure
        breakdown = data["status_breakdown"]
        assert "pass" in breakdown
        assert "warning" in breakdown
        assert "fail" in breakdown

    def test_no_mongo_id_leakage(self):
        """Response should not contain MongoDB _id field"""
        self._admin_login()
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=7"
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check latest doesn't have _id
        if data.get("latest"):
            assert "_id" not in data["latest"], "MongoDB _id leaked in latest"
        
        # Check history items don't have _id
        for item in data.get("history", []):
            assert "_id" not in item, "MongoDB _id leaked in history item"

    def test_history_row_fields(self):
        """Each history row should have expected sanitized fields"""
        self._admin_login()
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=7"
        )
        assert response.status_code == 200
        data = response.json()
        
        expected_fields = [
            "generated_at", "trigger", "status", "severity", "title", "summary",
            "baseline_established", "raw_scan_status", "files_scanned",
            "finding_count", "high_risk_count", "medium_risk_count",
            "new_finding_count", "new_high_risk_count", "new_medium_risk_count",
            "baseline_previous_finding_count", "alert_dispatched",
            "preview_source", "preview_findings"
        ]
        
        for item in data.get("history", []):
            for field in expected_fields:
                assert field in item, f"Missing field '{field}' in history row"

    def test_preview_findings_structure(self):
        """Preview findings should have correct structure"""
        self._admin_login()
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=7"
        )
        assert response.status_code == 200
        data = response.json()
        
        for item in data.get("history", []):
            findings = item.get("preview_findings", [])
            for finding in findings:
                assert "path" in finding, "Missing 'path' in preview finding"
                assert "line" in finding, "Missing 'line' in preview finding"
                assert "pattern" in finding, "Missing 'pattern' in preview finding"
                assert "severity" in finding, "Missing 'severity' in preview finding"
                # snippet is optional but should be present if available
                assert "_id" not in finding, "MongoDB _id leaked in preview finding"

    def test_limit_parameter(self):
        """Limit parameter should cap results"""
        self._admin_login()
        
        # Test with limit=3
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=3"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("history", [])) <= 3, "Limit not respected"

    def test_limit_max_cap(self):
        """Limit should be capped at ENTITLEMENT_DRIFT_MAX_HISTORY (30)"""
        self._admin_login()
        
        # Test with limit=100 (should be capped to 30)
        response = self.session.get(
            f"{BASE_URL}/api/admin/code-health/entitlement-drift/history?limit=100"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("history", [])) <= 30, "Max limit not enforced"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
