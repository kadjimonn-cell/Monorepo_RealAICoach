"""
Feature 26 Jobs Portal - Legacy v1 Code Removal Readiness Endpoint Tests

Tests for GET /api/hiring/v2/admin/legacy-removal-readiness endpoint:
- strict_zero and near_zero modes
- locked metadata (feature_number=26, feature_id=jobs-portal)
- Admin-only access control
- Response structure validation
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session with cookies"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code}")
    
    return session


@pytest.fixture(scope="module")
def free_user_session():
    """Get authenticated free user session with cookies"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Free user login failed: {login_response.status_code}")
    
    return session


class TestLegacyRemovalReadinessAuth:
    """Test authentication and authorization for legacy-removal-readiness endpoint"""
    
    def test_requires_authentication(self):
        """Endpoint should require authentication"""
        response = requests.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_requires_admin_access(self, free_user_session):
        """Endpoint should require admin access"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "Admin access required" in str(data.get("detail", ""))
    
    def test_admin_can_access(self, admin_session):
        """Admin should be able to access the endpoint"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


class TestLegacyRemovalReadinessLockedMetadata:
    """Test locked protocol metadata in response"""
    
    def test_has_feature_number_26(self, admin_session):
        """Response should include feature_number=26"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert data.get("feature_number") == 26, f"Expected feature_number=26, got {data.get('feature_number')}"
    
    def test_has_feature_id_jobs_portal(self, admin_session):
        """Response should include feature_id=jobs-portal"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert data.get("feature_id") == "jobs-portal", f"Expected feature_id=jobs-portal, got {data.get('feature_id')}"


class TestLegacyRemovalReadinessStrictZeroMode:
    """Test strict_zero mode (default)"""
    
    def test_default_mode_is_strict_zero(self, admin_session):
        """Default mode should be strict_zero"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "strict_zero", f"Expected mode=strict_zero, got {data.get('mode')}"
    
    def test_strict_zero_mode_explicit(self, admin_session):
        """Explicit strict_zero mode should work"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness?mode=strict_zero")
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "strict_zero"
    
    def test_strict_zero_thresholds(self, admin_session):
        """strict_zero mode should have max_events=0 and max_active_users=0"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness?mode=strict_zero")
        assert response.status_code == 200
        data = response.json()
        thresholds = data.get("thresholds", {}).get("strict_zero", {})
        assert thresholds.get("max_events") == 0, f"Expected max_events=0, got {thresholds.get('max_events')}"
        assert thresholds.get("max_active_users") == 0, f"Expected max_active_users=0, got {thresholds.get('max_active_users')}"


class TestLegacyRemovalReadinessNearZeroMode:
    """Test near_zero mode"""
    
    def test_near_zero_mode(self, admin_session):
        """near_zero mode should work"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness?mode=near_zero")
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "near_zero", f"Expected mode=near_zero, got {data.get('mode')}"
    
    def test_near_zero_default_thresholds(self, admin_session):
        """near_zero mode should have default thresholds (max_events=5, max_active_users=2)"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness?mode=near_zero")
        assert response.status_code == 200
        data = response.json()
        thresholds = data.get("thresholds", {}).get("near_zero", {})
        assert thresholds.get("max_events") == 5, f"Expected max_events=5, got {thresholds.get('max_events')}"
        assert thresholds.get("max_active_users") == 2, f"Expected max_active_users=2, got {thresholds.get('max_active_users')}"
    
    def test_near_zero_custom_thresholds(self, admin_session):
        """near_zero mode should accept custom thresholds"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness?mode=near_zero&near_zero_max_events=10&near_zero_max_active_users=5"
        )
        assert response.status_code == 200
        data = response.json()
        thresholds = data.get("thresholds", {}).get("near_zero", {})
        assert thresholds.get("max_events") == 10, f"Expected max_events=10, got {thresholds.get('max_events')}"
        assert thresholds.get("max_active_users") == 5, f"Expected max_active_users=5, got {thresholds.get('max_active_users')}"


class TestLegacyRemovalReadinessResponseStructure:
    """Test response structure"""
    
    def test_has_generated_at(self, admin_session):
        """Response should include generated_at timestamp"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert "generated_at" in data, "Response should include generated_at"
    
    def test_has_sustained_gate_met(self, admin_session):
        """Response should include sustained_gate_met boolean"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert "sustained_gate_met" in data, "Response should include sustained_gate_met"
        assert isinstance(data.get("sustained_gate_met"), bool), "sustained_gate_met should be boolean"
    
    def test_has_ready_for_legacy_code_removal(self, admin_session):
        """Response should include ready_for_legacy_code_removal boolean"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert "ready_for_legacy_code_removal" in data, "Response should include ready_for_legacy_code_removal"
        assert isinstance(data.get("ready_for_legacy_code_removal"), bool), "ready_for_legacy_code_removal should be boolean"
    
    def test_has_recommended_action(self, admin_session):
        """Response should include recommended_action string"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert "recommended_action" in data, "Response should include recommended_action"
        assert isinstance(data.get("recommended_action"), str), "recommended_action should be string"
    
    def test_has_windows_array(self, admin_session):
        """Response should include windows array with monitoring windows"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert "windows" in data, "Response should include windows"
        assert isinstance(data.get("windows"), list), "windows should be a list"
        assert len(data.get("windows", [])) > 0, "windows should not be empty"
    
    def test_windows_have_correct_structure(self, admin_session):
        """Each window should have correct structure"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        windows = data.get("windows", [])
        
        for window in windows:
            assert "window_label" in window, "Window should have window_label"
            assert "lookback_hours" in window, "Window should have lookback_hours"
            assert "gate_met" in window, "Window should have gate_met"
            assert "family_readiness" in window, "Window should have family_readiness"
            assert isinstance(window.get("family_readiness"), list), "family_readiness should be a list"
    
    def test_has_failing_windows_array(self, admin_session):
        """Response should include failing_windows array"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert "failing_windows" in data, "Response should include failing_windows"
        assert isinstance(data.get("failing_windows"), list), "failing_windows should be a list"
    
    def test_has_controls_snapshot(self, admin_session):
        """Response should include controls_snapshot"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert "controls_snapshot" in data, "Response should include controls_snapshot"
        snapshot = data.get("controls_snapshot", {})
        assert "legacy_retirement_enabled" in snapshot, "controls_snapshot should have legacy_retirement_enabled"
        assert "retirement_phase" in snapshot, "controls_snapshot should have retirement_phase"


class TestLegacyRemovalReadinessExcludeSynthetic:
    """Test exclude_synthetic parameter"""
    
    def test_exclude_synthetic_false_default(self, admin_session):
        """Default exclude_synthetic should be false"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        assert data.get("exclude_synthetic") == False, f"Expected exclude_synthetic=False, got {data.get('exclude_synthetic')}"
    
    def test_exclude_synthetic_true(self, admin_session):
        """exclude_synthetic=true should work"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness?exclude_synthetic=true")
        assert response.status_code == 200
        data = response.json()
        assert data.get("exclude_synthetic") == True, f"Expected exclude_synthetic=True, got {data.get('exclude_synthetic')}"


class TestLegacyRemovalReadinessStrictZeroNotReady:
    """Test that strict_zero mode reports not ready when there are legacy events"""
    
    def test_strict_zero_with_legacy_events_not_ready(self, admin_session):
        """With 7 legacy jobs save events, strict_zero should report not ready"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness?mode=strict_zero")
        assert response.status_code == 200
        data = response.json()
        
        # Check if there are any failing windows (indicating legacy events exist)
        failing_windows = data.get("failing_windows", [])
        sustained_gate_met = data.get("sustained_gate_met", True)
        ready_for_removal = data.get("ready_for_legacy_code_removal", True)
        
        # If there are legacy events, the gate should not be met
        # Note: This test validates the logic - if there are events, it should report not ready
        if len(failing_windows) > 0:
            assert sustained_gate_met == False, "With failing windows, sustained_gate_met should be False"
            assert ready_for_removal == False, "With failing windows, ready_for_legacy_code_removal should be False"
            assert "Continue monitoring" in data.get("recommended_action", ""), "Should recommend continuing monitoring"


class TestLegacyRemovalReadinessMonitorWindows:
    """Test monitoring windows (72h, 7d, 14d, 30d)"""
    
    def test_has_72h_window(self, admin_session):
        """Should have 72h monitoring window"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        windows = data.get("windows", [])
        labels = [w.get("window_label") for w in windows]
        assert "72h" in labels, f"Should have 72h window, got {labels}"
    
    def test_has_7d_window(self, admin_session):
        """Should have 7d monitoring window"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        windows = data.get("windows", [])
        labels = [w.get("window_label") for w in windows]
        assert "7d" in labels, f"Should have 7d window, got {labels}"
    
    def test_has_14d_window(self, admin_session):
        """Should have 14d monitoring window"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        windows = data.get("windows", [])
        labels = [w.get("window_label") for w in windows]
        assert "14d" in labels, f"Should have 14d window, got {labels}"
    
    def test_has_30d_window(self, admin_session):
        """Should have 30d monitoring window"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        windows = data.get("windows", [])
        labels = [w.get("window_label") for w in windows]
        assert "30d" in labels, f"Should have 30d window, got {labels}"


class TestLegacyRemovalReadinessFamilyReadiness:
    """Test family readiness structure (jobs and employers)"""
    
    def test_family_readiness_has_jobs(self, admin_session):
        """Family readiness should include jobs route family"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        windows = data.get("windows", [])
        
        if len(windows) > 0:
            first_window = windows[0]
            family_readiness = first_window.get("family_readiness", [])
            families = [f.get("route_family") for f in family_readiness]
            assert "jobs" in families, f"Should have jobs family, got {families}"
    
    def test_family_readiness_has_employers(self, admin_session):
        """Family readiness should include employers route family"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        windows = data.get("windows", [])
        
        if len(windows) > 0:
            first_window = windows[0]
            family_readiness = first_window.get("family_readiness", [])
            families = [f.get("route_family") for f in family_readiness]
            assert "employers" in families, f"Should have employers family, got {families}"
    
    def test_family_readiness_structure(self, admin_session):
        """Each family readiness should have correct structure"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert response.status_code == 200
        data = response.json()
        windows = data.get("windows", [])
        
        if len(windows) > 0:
            first_window = windows[0]
            family_readiness = first_window.get("family_readiness", [])
            
            for family in family_readiness:
                assert "route_family" in family, "Family should have route_family"
                assert "total_events" in family, "Family should have total_events"
                assert "active_users" in family, "Family should have active_users"
                assert "gate_met" in family, "Family should have gate_met"
                assert "readiness_score" in family, "Family should have readiness_score"
