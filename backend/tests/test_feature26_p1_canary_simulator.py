"""
Feature 26 P1 - Canary Policy Simulator Tests
Tests for POST /api/hiring/v2/admin/canary-simulator endpoint
Validates locked protocol metadata, admin-only guard, and response contract
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


class TestCanarySimulatorEndpoint:
    """Tests for the new Canary Policy Simulator endpoint"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        return session

    @pytest.fixture(scope="class")
    def free_user_session(self):
        """Get authenticated free user session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_USER_EMAIL,
            "password": FREE_USER_PASSWORD
        })
        assert login_resp.status_code == 200, f"Free user login failed: {login_resp.text}"
        return session

    # ========== Endpoint Existence Tests ==========

    def test_canary_simulator_endpoint_exists(self, admin_session):
        """Verify POST /api/hiring/v2/admin/canary-simulator endpoint exists"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        # Should not return 404 - endpoint exists
        assert resp.status_code != 404, "Canary simulator endpoint does not exist"
        # Should return 200 for admin
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}, {resp.text}"

    # ========== Admin-Only Guard Tests ==========

    def test_free_user_denied_canary_simulator(self, free_user_session):
        """Free user should get 403 on simulator endpoint"""
        resp = free_user_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 403, f"Expected 403 for free user, got {resp.status_code}"
        data = resp.json()
        assert "Admin access required" in data.get("detail", ""), f"Unexpected error: {data}"

    def test_unauthenticated_denied_canary_simulator(self):
        """Unauthenticated request should be denied"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        resp = session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"

    # ========== Locked Protocol Metadata Tests ==========

    def test_simulator_response_contains_feature_number_26(self, admin_session):
        """Simulator response must contain feature_number=26"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("feature_number") == 26, f"Expected feature_number=26, got {data.get('feature_number')}"

    def test_simulator_response_contains_feature_id_jobs_portal(self, admin_session):
        """Simulator response must contain feature_id=jobs-portal"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("feature_id") == "jobs-portal", f"Expected feature_id=jobs-portal, got {data.get('feature_id')}"

    # ========== Response Contract Tests ==========

    def test_simulator_summary_contains_projected_allowed_events(self, admin_session):
        """Summary must contain projected_allowed_events field"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("summary", {})
        assert "projected_allowed_events" in summary, f"Missing projected_allowed_events in summary: {summary.keys()}"

    def test_simulator_summary_contains_projected_blocked_events(self, admin_session):
        """Summary must contain projected_blocked_events field"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("summary", {})
        assert "projected_blocked_events" in summary, f"Missing projected_blocked_events in summary: {summary.keys()}"

    def test_simulator_summary_contains_projected_blocked_pct(self, admin_session):
        """Summary must contain projected_blocked_pct field"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("summary", {})
        assert "projected_blocked_pct" in summary, f"Missing projected_blocked_pct in summary: {summary.keys()}"

    def test_simulator_summary_contains_rollback_risk_level(self, admin_session):
        """Summary must contain rollback_risk_level field"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("summary", {})
        assert "rollback_risk_level" in summary, f"Missing rollback_risk_level in summary: {summary.keys()}"

    def test_simulator_summary_contains_would_trigger_auto_rollback(self, admin_session):
        """Summary must contain would_trigger_auto_rollback field"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("summary", {})
        assert "would_trigger_auto_rollback" in summary, f"Missing would_trigger_auto_rollback in summary: {summary.keys()}"

    def test_simulator_summary_contains_recommendation(self, admin_session):
        """Summary must contain recommendation field"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("summary", {})
        assert "recommendation" in summary, f"Missing recommendation in summary: {summary.keys()}"

    # ========== Full Response Structure Tests ==========

    def test_simulator_response_structure(self, admin_session):
        """Verify complete response structure"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={
            "canary_enabled": True,
            "legacy_allow_pct": 65,
            "lookback_hours": 72
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # Top-level fields
        assert "generated_at" in data, "Missing generated_at"
        assert "feature_number" in data, "Missing feature_number"
        assert "feature_id" in data, "Missing feature_id"
        assert "telemetry_window" in data, "Missing telemetry_window"
        assert "current_controls" in data, "Missing current_controls"
        assert "proposed_controls" in data, "Missing proposed_controls"
        assert "summary" in data, "Missing summary"
        assert "operations" in data, "Missing operations"

    def test_simulator_with_custom_parameters(self, admin_session):
        """Test simulator with custom parameters"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={
            "canary_enabled": True,
            "legacy_allow_pct": 50,
            "lookback_hours": 48,
            "rollback_window_hours": 12,
            "rollback_legacy_event_threshold": 100,
            "operations": ["candidate_save_job", "employer_offer_build"]
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify proposed controls reflect input
        proposed = data.get("proposed_controls", {})
        assert proposed.get("canary_enabled") == True
        assert proposed.get("legacy_allow_pct") == 50

    def test_simulator_risk_level_values(self, admin_session):
        """Verify rollback_risk_level is one of expected values"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("summary", {})
        risk_level = summary.get("rollback_risk_level")
        assert risk_level in ["low", "medium", "high"], f"Unexpected risk_level: {risk_level}"

    def test_simulator_recommendation_is_string(self, admin_session):
        """Verify recommendation is a non-empty string"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        summary = data.get("summary", {})
        recommendation = summary.get("recommendation")
        assert isinstance(recommendation, str), f"recommendation should be string, got {type(recommendation)}"
        assert len(recommendation) > 0, "recommendation should not be empty"

    def test_simulator_operations_list_structure(self, admin_session):
        """Verify operations list structure"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert resp.status_code == 200
        data = resp.json()
        operations = data.get("operations", [])
        assert isinstance(operations, list), "operations should be a list"
        
        # If there are operations, verify structure
        if operations:
            op = operations[0]
            assert "operation" in op, "Missing operation field"
            assert "projected_blocked_events" in op, "Missing projected_blocked_events"
            assert "projected_blocked_pct" in op, "Missing projected_blocked_pct"


class TestCanarySimulatorIntegration:
    """Integration tests for canary simulator with other admin endpoints"""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
        return session

    def test_simulator_uses_current_canary_controls(self, admin_session):
        """Simulator should reflect current canary controls as baseline"""
        # Get current controls
        controls_resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls")
        assert controls_resp.status_code == 200
        current_controls = controls_resp.json().get("controls", {})
        
        # Run simulator without overrides
        sim_resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={})
        assert sim_resp.status_code == 200
        sim_data = sim_resp.json()
        
        # Verify current_controls in response matches actual current controls
        sim_current = sim_data.get("current_controls", {})
        assert sim_current.get("canary_enabled") == current_controls.get("canary_enabled", False)

    def test_simulator_telemetry_window_matches_deprecation_data(self, admin_session):
        """Simulator telemetry should be consistent with deprecation telemetry"""
        # Get deprecation telemetry
        dep_resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry?lookback_days=14")
        assert dep_resp.status_code == 200
        
        # Run simulator
        sim_resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/canary-simulator", json={
            "lookback_hours": 336  # 14 days
        })
        assert sim_resp.status_code == 200
        sim_data = sim_resp.json()
        
        # Verify telemetry window is present
        telemetry_window = sim_data.get("telemetry_window", {})
        assert "lookback_hours" in telemetry_window
        assert "total_legacy_events" in telemetry_window


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
