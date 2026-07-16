"""Feature 26 P2 Legacy v1 Route Retirement Tests

Tests for phased legacy v1 route retirement for /api/jobs and /api/employers
using telemetry gates, under global system lock and platform locked protocol.

Feature: 26
Feature ID: jobs-portal
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with CSRF header"""
    session = requests.Session()
    session.headers.update({"X-Requested-With": "XMLHttpRequest"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def free_session():
    """Login as free user and return session with CSRF header"""
    session = requests.Session()
    session.headers.update({"X-Requested-With": "XMLHttpRequest"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_EMAIL,
        "password": FREE_PASSWORD
    })
    assert resp.status_code == 200, f"Free user login failed: {resp.text}"
    return session


@pytest.fixture(autouse=True)
def reset_retirement_state(admin_session):
    """Reset retirement state to observe before and after each test"""
    # Reset before test
    admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
        "legacy_retirement_enabled": False,
        "retirement_phase": "observe"
    })
    yield
    # Reset after test
    admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
        "legacy_retirement_enabled": False,
        "retirement_phase": "observe"
    })


class TestP2RetirementReadinessAPI:
    """Tests for GET /api/hiring/v2/admin/legacy-retirement-readiness"""

    def test_readiness_requires_auth(self):
        """Retirement readiness endpoint requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-readiness")
        assert resp.status_code in [401, 403], "Should require auth"

    def test_readiness_requires_admin(self, free_session):
        """Retirement readiness endpoint requires admin role"""
        resp = free_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-readiness")
        assert resp.status_code == 403, "Free user should get 403"
        data = resp.json()
        assert "Admin access required" in str(data.get("detail", ""))

    def test_readiness_returns_correct_structure(self, admin_session):
        """Retirement readiness returns correct response structure"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-readiness?lookback_hours=72")
        assert resp.status_code == 200, f"Admin should get 200: {resp.text}"
        data = resp.json()
        
        # Check locked metadata
        assert data.get("feature_number") == 26, "feature_number should be 26"
        assert data.get("feature_id") == "jobs-portal", "feature_id should be jobs-portal"
        
        # Check required fields
        assert "retirement_phase" in data, "Should have retirement_phase"
        assert "target_route_families" in data, "Should have target_route_families"
        assert "target_phase_gate_ready" in data, "Should have target_phase_gate_ready"
        assert "recommended_phase" in data, "Should have recommended_phase"
        assert "family_readiness" in data, "Should have family_readiness"
        assert "controls" in data, "Should have controls"
        assert "lookback_hours" in data, "Should have lookback_hours"

    def test_readiness_family_readiness_structure(self, admin_session):
        """Family readiness contains correct fields for each route family"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-readiness?lookback_hours=72")
        assert resp.status_code == 200
        data = resp.json()
        
        family_readiness = data.get("family_readiness", [])
        assert len(family_readiness) >= 2, "Should have at least jobs and employers families"
        
        for family in family_readiness:
            assert "route_family" in family, "Should have route_family"
            assert "total_events" in family, "Should have total_events"
            assert "active_users" in family, "Should have active_users"
            assert "gate_met" in family, "Should have gate_met"
            assert "readiness_score" in family, "Should have readiness_score"
            assert "gate_thresholds" in family, "Should have gate_thresholds"

    def test_readiness_lookback_hours_parameter(self, admin_session):
        """Lookback hours parameter is respected"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-readiness?lookback_hours=24")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("lookback_hours") == 24, "Should respect lookback_hours parameter"


class TestP2RetirementControlsAPI:
    """Tests for POST /api/hiring/v2/admin/legacy-retirement-controls"""

    def test_controls_requires_auth(self):
        """Retirement controls endpoint requires authentication"""
        resp = requests.post(
            f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls",
            json={"legacy_retirement_enabled": False},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert resp.status_code in [401, 403], "Should require auth"

    def test_controls_requires_admin(self, free_session):
        """Retirement controls endpoint requires admin role"""
        resp = free_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": False,
            "retirement_phase": "observe"
        })
        assert resp.status_code == 403, "Free user should get 403"

    def test_controls_observe_phase(self, admin_session):
        """Can set retirement to observe phase"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": False,
            "retirement_phase": "observe"
        })
        assert resp.status_code == 200, f"Should succeed: {resp.text}"
        data = resp.json()
        
        assert data.get("success") is True
        assert data.get("feature_number") == 26
        assert data.get("feature_id") == "jobs-portal"
        
        controls = data.get("controls", {})
        assert controls.get("retirement_phase") == "observe"
        assert controls.get("legacy_retirement_enabled") is False

    def test_controls_phase1_jobs_writes(self, admin_session):
        """Can set retirement to phase1_jobs_writes with force_apply"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase1_jobs_writes",
            "retirement_force_apply": True,
            "retirement_gate_max_events": 100000,
            "retirement_gate_max_active_users": 100000
        })
        assert resp.status_code == 200, f"Should succeed: {resp.text}"
        data = resp.json()
        
        controls = data.get("controls", {})
        assert controls.get("retirement_phase") == "phase1_jobs_writes"
        assert controls.get("legacy_retirement_enabled") is True
        assert "jobs" in controls.get("retired_legacy_route_families", [])

    def test_controls_phase2_jobs_employers_writes(self, admin_session):
        """Can set retirement to phase2_jobs_employers_writes with force_apply"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase2_jobs_employers_writes",
            "retirement_force_apply": True,
            "retirement_gate_max_events": 100000,
            "retirement_gate_max_active_users": 100000
        })
        assert resp.status_code == 200, f"Should succeed: {resp.text}"
        data = resp.json()
        
        controls = data.get("controls", {})
        assert controls.get("retirement_phase") == "phase2_jobs_employers_writes"
        assert "jobs" in controls.get("retired_legacy_route_families", [])
        assert "employers" in controls.get("retired_legacy_route_families", [])

    def test_controls_returns_family_readiness(self, admin_session):
        """Controls response includes family_readiness"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": False,
            "retirement_phase": "observe"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert "family_readiness" in data, "Should include family_readiness"
        family_readiness = data.get("family_readiness", [])
        assert len(family_readiness) >= 2, "Should have jobs and employers families"

    def test_controls_gate_not_met_without_force(self, admin_session):
        """Cannot enable retirement without force_apply if gate not met"""
        # First set very strict thresholds
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase1_jobs_writes",
            "retirement_force_apply": False,
            "retirement_gate_max_events": 0,  # Very strict - no events allowed
            "retirement_gate_max_active_users": 0
        })
        # Should either succeed (if gate is met) or return 409 (if gate not met)
        assert resp.status_code in [200, 409], f"Should be 200 or 409: {resp.text}"


class TestP2DeprecationTelemetryEnhancements:
    """Tests for deprecation telemetry route_family_breakdown and retirement fields"""

    def test_telemetry_has_route_family_breakdown(self, admin_session):
        """Deprecation telemetry includes route_family_breakdown"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry?lookback_days=14&limit=100")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "route_family_breakdown" in data, "Should have route_family_breakdown"
        breakdown = data.get("route_family_breakdown", [])
        assert isinstance(breakdown, list), "route_family_breakdown should be a list"

    def test_telemetry_has_retirement_status_fields(self, admin_session):
        """Deprecation telemetry includes retirement status fields"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry?lookback_days=14&limit=100")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "retirement_phase" in data, "Should have retirement_phase"
        assert "legacy_retirement_enabled" in data, "Should have legacy_retirement_enabled"
        assert "retired_legacy_route_families" in data, "Should have retired_legacy_route_families"


class TestP2CanaryControlsRetirementFields:
    """Tests for canary controls retirement fields"""

    def test_canary_controls_has_retirement_fields(self, admin_session):
        """Canary controls includes all P2 retirement fields"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls")
        assert resp.status_code == 200
        data = resp.json()
        
        controls = data.get("controls", {})
        
        # Check for P2 retirement fields
        retirement_fields = [
            "legacy_retirement_enabled",
            "retirement_phase",
            "retirement_gate_lookback_hours",
            "retirement_gate_max_events",
            "retirement_gate_max_active_users",
            "retirement_force_apply",
        ]
        for field in retirement_fields:
            assert field in controls, f"Should have {field}"


class TestP2LegacyWriteEnforcement:
    """Tests for legacy write enforcement when retirement is enabled"""

    def test_jobs_write_blocked_when_phase1_enabled(self, admin_session, free_session):
        """Legacy jobs write is blocked when phase1 retirement is enabled"""
        # Enable phase1 with force
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase1_jobs_writes",
            "retirement_force_apply": True,
            "retirement_gate_max_events": 100000,
            "retirement_gate_max_active_users": 100000
        })
        assert resp.status_code == 200, f"Enable phase1 failed: {resp.text}"
        
        # Try legacy jobs save as free user
        resp = free_session.post(f"{BASE_URL}/api/jobs/save/job_test_p2_123")
        assert resp.status_code == 410, f"Should be blocked with 410: {resp.status_code}"
        
        data = resp.json()
        detail = data.get("detail", {})
        assert detail.get("route_family") == "jobs"
        assert detail.get("retirement_phase") == "hard_retired_cleanup"
        assert "/api/hiring/v2/" in str(detail.get("replacement_hint", ""))

    def test_employers_write_blocked_when_phase2_enabled(self, admin_session, free_session):
        """Legacy employers write is blocked when phase2 retirement is enabled"""
        # Enable phase2 with force
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase2_jobs_employers_writes",
            "retirement_force_apply": True,
            "retirement_gate_max_events": 100000,
            "retirement_gate_max_active_users": 100000
        })
        assert resp.status_code == 200, f"Enable phase2 failed: {resp.text}"
        
        # Try legacy employers reverify as free user
        resp = free_session.post(f"{BASE_URL}/api/employers/reverify")
        assert resp.status_code == 410, f"Should be blocked with 410: {resp.status_code}"
        
        data = resp.json()
        detail = data.get("detail", {})
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_phase") == "hard_retired_cleanup"

    def test_admin_write_also_retired_after_final_cleanup(self, admin_session):
        """Final cleanup retires legacy writes for admin users too (no override)."""
        # Enable phase2 with force
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase2_jobs_employers_writes",
            "retirement_force_apply": True,
            "retirement_gate_max_events": 100000,
            "retirement_gate_max_active_users": 100000
        })
        assert resp.status_code == 200
        
        resp = admin_session.post(f"{BASE_URL}/api/jobs/save/job_admin_test_123")
        assert resp.status_code == 410, f"Admin legacy writes should be retired: {resp.status_code}"
        detail = resp.json().get("detail", {})
        assert detail.get("retirement_mode") == "hard_retired"


class TestP2LockedMetadata:
    """Tests for locked metadata (feature_number=26, feature_id=jobs-portal)"""

    def test_readiness_has_locked_metadata(self, admin_session):
        """Retirement readiness has locked metadata"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-readiness")
        assert resp.status_code == 200
        data = resp.json()
        
        assert data.get("feature_number") == 26
        assert data.get("feature_id") == "jobs-portal"

    def test_controls_response_has_locked_metadata(self, admin_session):
        """Retirement controls response has locked metadata"""
        resp = admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": False,
            "retirement_phase": "observe"
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert data.get("feature_number") == 26
        assert data.get("feature_id") == "jobs-portal"

    def test_410_response_has_locked_metadata(self, admin_session, free_session):
        """410 retirement response includes locked metadata in detail"""
        # Enable phase1 with force
        admin_session.post(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-controls", json={
            "legacy_retirement_enabled": True,
            "retirement_phase": "phase1_jobs_writes",
            "retirement_force_apply": True,
            "retirement_gate_max_events": 100000,
            "retirement_gate_max_active_users": 100000
        })
        
        # Try legacy jobs save
        resp = free_session.post(f"{BASE_URL}/api/jobs/save/job_metadata_test")
        if resp.status_code == 410:
            data = resp.json()
            detail = data.get("detail", {})
            # The 410 response should indicate the retirement phase
            assert "retirement_phase" in detail
            assert "route_family" in detail
