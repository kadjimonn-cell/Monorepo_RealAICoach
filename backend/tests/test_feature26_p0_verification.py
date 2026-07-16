"""
Feature 26 Jobs Portal P0 Verification Tests
Tests locked protocol contract, free user access matrix, employer v2 reads, and admin controls.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
EMPLOYER_EMAIL = "e2e.employer.feature26@realaicoach.app"
EMPLOYER_PASSWORD = "E2EEmployer#Feature26!2026"


def get_session_with_auth(email: str, password: str) -> tuple[requests.Session, bool]:
    """Login and return authenticated session."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",  # Required for CSRF bypass on cookie-auth
    })
    
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password}
    )
    
    if login_resp.status_code == 200:
        return session, True
    return session, False


class TestLockedProtocolContract:
    """Test /api/hiring/v2/health aligns to feature_number=26 and feature_id=jobs-portal"""
    
    def test_hiring_v2_health_returns_correct_feature_metadata(self):
        """Verify health endpoint returns correct feature_number=26 and feature_id=jobs-portal"""
        session, logged_in = get_session_with_auth(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert logged_in, "Admin login failed"
        
        resp = session.get(f"{BASE_URL}/api/hiring/v2/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert data.get("ok") is True, "Health check should return ok=True"
        assert data.get("feature_number") == 26, f"Expected feature_number=26, got {data.get('feature_number')}"
        assert data.get("feature_id") == "jobs-portal", f"Expected feature_id=jobs-portal, got {data.get('feature_id')}"
        assert data.get("version") == "v2", f"Expected version=v2, got {data.get('version')}"
        assert data.get("service") == "hiring-v2", f"Expected service=hiring-v2, got {data.get('service')}"
        print("PASS: Health endpoint returns correct locked protocol: feature_number=26, feature_id=jobs-portal")


class TestFreeUserAccessMatrix:
    """Test free user access: dashboard summary and candidate search allowed, admin endpoints denied"""
    
    @pytest.fixture(autouse=True)
    def setup_free_session(self):
        """Setup authenticated free user session"""
        self.session, self.logged_in = get_session_with_auth(FREE_USER_EMAIL, FREE_USER_PASSWORD)
        if not self.logged_in:
            pytest.skip("Free user login failed - skipping free user tests")
    
    def test_free_user_can_access_dashboard_summary(self):
        """Free user should be able to access /api/hiring/v2/dashboard/summary"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary")
        assert resp.status_code == 200, f"Expected 200 for dashboard summary, got {resp.status_code}"
        
        data = resp.json()
        # Verify response structure
        assert "open_roles" in data or "candidate" in data, "Dashboard summary should contain hiring data"
        print("PASS: Free user can access dashboard summary")
    
    def test_free_user_can_access_candidate_search(self):
        """Free user should be able to access /api/hiring/v2/candidate/jobs/search"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search")
        assert resp.status_code == 200, f"Expected 200 for candidate search, got {resp.status_code}"
        
        data = resp.json()
        assert "jobs" in data, "Search response should contain jobs array"
        assert "total" in data, "Search response should contain total count"
        print("PASS: Free user can access candidate job search")
    
    def test_free_user_denied_admin_workflow_events(self):
        """Free user should be denied access to /api/hiring/v2/admin/workflow-events"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=5")
        assert resp.status_code == 403, f"Expected 403 for admin endpoint, got {resp.status_code}"
        
        data = resp.json()
        assert "Admin access required" in str(data.get("detail", "")), "Should return admin access required message"
        print("PASS: Free user correctly denied access to admin workflow-events")
    
    def test_free_user_denied_admin_deprecation_telemetry(self):
        """Free user should be denied access to /api/hiring/v2/admin/deprecation-telemetry"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry")
        assert resp.status_code == 403, f"Expected 403 for admin endpoint, got {resp.status_code}"
        print("PASS: Free user correctly denied access to admin deprecation-telemetry")
    
    def test_free_user_denied_admin_canary_controls(self):
        """Free user should be denied access to /api/hiring/v2/admin/canary-controls"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls")
        assert resp.status_code == 403, f"Expected 403 for admin endpoint, got {resp.status_code}"
        print("PASS: Free user correctly denied access to admin canary-controls")
    
    def test_free_user_denied_admin_premium_conversion_cohorts(self):
        """Free user should be denied access to /api/hiring/v2/admin/premium-conversion-cohorts"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/premium-conversion-cohorts")
        assert resp.status_code == 403, f"Expected 403 for admin endpoint, got {resp.status_code}"
        print("PASS: Free user correctly denied access to admin premium-conversion-cohorts")
    
    def test_free_user_denied_boost_profile_premium_feature(self):
        """Free user should be denied access to premium boost-profile feature"""
        resp = self.session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/boost-profile",
            json={"boost_hours": 72}
        )
        assert resp.status_code == 403, f"Expected 403 for premium feature, got {resp.status_code}"
        
        data = resp.json()
        assert "Basic and Premium plans" in str(data.get("detail", "")), "Should indicate plan requirement"
        print("PASS: Free user correctly denied access to premium boost-profile feature")


class TestEmployerV2CriticalReads:
    """Test employer v2 critical reads: pipeline board and offers"""
    
    @pytest.fixture(autouse=True)
    def setup_employer_session(self):
        """Setup authenticated employer session"""
        self.session, self.logged_in = get_session_with_auth(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
        if not self.logged_in:
            pytest.skip("Employer login failed - skipping employer tests")
    
    def test_employer_can_access_pipeline_board(self):
        """Employer should be able to access /api/hiring/v2/employer/pipeline-board"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/employer/pipeline-board?limit=10")
        assert resp.status_code == 200, f"Expected 200 for pipeline board, got {resp.status_code}"
        
        data = resp.json()
        # Verify response structure
        assert "stages" in data, "Pipeline board should contain stages"
        assert "counts" in data, "Pipeline board should contain counts"
        assert "applications" in data, "Pipeline board should contain applications"
        print("PASS: Employer can access pipeline board")
    
    def test_employer_can_access_offers(self):
        """Employer should be able to access /api/hiring/v2/employer/offers"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/employer/offers?limit=10")
        assert resp.status_code == 200, f"Expected 200 for offers, got {resp.status_code}"
        
        data = resp.json()
        assert "offers" in data, "Offers response should contain offers array"
        assert "total" in data, "Offers response should contain total count"
        print("PASS: Employer can access offers endpoint")
    
    def test_employer_can_access_dashboard_summary(self):
        """Employer should be able to access /api/hiring/v2/dashboard/summary"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary")
        assert resp.status_code == 200, f"Expected 200 for dashboard summary, got {resp.status_code}"
        print("PASS: Employer can access dashboard summary")


class TestAdminV2ControlsObservability:
    """Test admin v2 controls: workflow events, deprecation telemetry, canary controls, premium cohorts"""
    
    @pytest.fixture(autouse=True)
    def setup_admin_session(self):
        """Setup authenticated admin session"""
        self.session, self.logged_in = get_session_with_auth(ADMIN_EMAIL, ADMIN_PASSWORD)
        if not self.logged_in:
            pytest.skip("Admin login failed - skipping admin tests")
    
    def test_admin_can_access_workflow_events(self):
        """Admin should be able to access /api/hiring/v2/admin/workflow-events"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=5")
        assert resp.status_code == 200, f"Expected 200 for workflow events, got {resp.status_code}"
        
        data = resp.json()
        assert "events" in data, "Workflow events should contain events array"
        assert "lookback_hours" in data, "Workflow events should contain lookback_hours"
        assert "generated_at" in data, "Workflow events should contain generated_at"
        print("PASS: Admin can access workflow events")
    
    def test_admin_can_access_deprecation_telemetry(self):
        """Admin should be able to access /api/hiring/v2/admin/deprecation-telemetry"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry?lookback_days=14&limit=200")
        assert resp.status_code == 200, f"Expected 200 for deprecation telemetry, got {resp.status_code}"
        
        data = resp.json()
        assert "total_events" in data, "Deprecation telemetry should contain total_events"
        assert "migration_progress_pct" in data, "Deprecation telemetry should contain migration_progress_pct"
        assert "active_legacy_users" in data, "Deprecation telemetry should contain active_legacy_users"
        assert "remaining_legacy_operations" in data, "Deprecation telemetry should contain remaining_legacy_operations"
        print(f"PASS: Admin can access deprecation telemetry - migration_progress_pct={data.get('migration_progress_pct')}")
    
    def test_admin_can_access_canary_controls_get(self):
        """Admin should be able to GET /api/hiring/v2/admin/canary-controls"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls")
        assert resp.status_code == 200, f"Expected 200 for canary controls GET, got {resp.status_code}"
        
        data = resp.json()
        assert "controls" in data, "Canary controls should contain controls object"
        assert "defaults" in data, "Canary controls should contain defaults object"
        
        controls = data.get("controls", {})
        assert "canary_enabled" in controls, "Controls should contain canary_enabled"
        assert "legacy_allow_pct" in controls, "Controls should contain legacy_allow_pct"
        assert "auto_rollback_enabled" in controls, "Controls should contain auto_rollback_enabled"
        assert "rollback_window_hours" in controls, "Controls should contain rollback_window_hours"
        assert "rollback_legacy_event_threshold" in controls, "Controls should contain rollback_legacy_event_threshold"
        print(f"PASS: Admin can access canary controls GET - canary_enabled={controls.get('canary_enabled')}, legacy_allow_pct={controls.get('legacy_allow_pct')}")
    
    def test_admin_can_access_premium_conversion_cohorts(self):
        """Admin should be able to access /api/hiring/v2/admin/premium-conversion-cohorts"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/premium-conversion-cohorts?lookback_days=30")
        assert resp.status_code == 200, f"Expected 200 for premium conversion cohorts, got {resp.status_code}"
        
        data = resp.json()
        assert "activation_users" in data, "Premium cohorts should contain activation_users"
        assert "repeat_users" in data, "Premium cohorts should contain repeat_users"
        assert "repeat_rate_pct" in data, "Premium cohorts should contain repeat_rate_pct"
        assert "churn_signal_pct" in data, "Premium cohorts should contain churn_signal_pct"
        assert "events_by_plan" in data, "Premium cohorts should contain events_by_plan"
        print(f"PASS: Admin can access premium conversion cohorts - repeat_rate_pct={data.get('repeat_rate_pct')}")
    
    def test_admin_can_post_canary_controls(self):
        """Admin should be able to POST /api/hiring/v2/admin/canary-controls"""
        # First get current controls
        get_resp = self.session.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls")
        assert get_resp.status_code == 200
        current = get_resp.json().get("controls", {})
        
        # POST with same values (no actual change, just verify endpoint works)
        post_resp = self.session.post(
            f"{BASE_URL}/api/hiring/v2/admin/canary-controls",
            json={
                "canary_enabled": current.get("canary_enabled", False),
                "legacy_allow_pct": current.get("legacy_allow_pct", 100),
                "auto_rollback_enabled": current.get("auto_rollback_enabled", True),
            }
        )
        assert post_resp.status_code == 200, f"Expected 200 for canary controls POST, got {post_resp.status_code}"
        
        data = post_resp.json()
        assert data.get("success") is True, "POST should return success=True"
        assert "controls" in data, "POST response should contain controls"
        print("PASS: Admin can POST canary controls")


class TestV2EndpointExistence:
    """Verify all v2 endpoints exist and respond appropriately"""
    
    @pytest.fixture(autouse=True)
    def setup_admin_session(self):
        """Setup authenticated admin session for endpoint checks"""
        self.session, self.logged_in = get_session_with_auth(ADMIN_EMAIL, ADMIN_PASSWORD)
        if not self.logged_in:
            pytest.skip("Admin login failed - skipping endpoint existence tests")
    
    def test_v2_candidate_applications_endpoint_exists(self):
        """Verify /api/hiring/v2/candidate/applications endpoint exists"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/candidate/applications")
        assert resp.status_code in [200, 401, 403], f"Endpoint should exist, got {resp.status_code}"
        print(f"PASS: v2 candidate applications endpoint exists (status={resp.status_code})")
    
    def test_v2_candidate_saved_jobs_endpoint_exists(self):
        """Verify /api/hiring/v2/candidate/saved-jobs endpoint exists"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/candidate/saved-jobs")
        assert resp.status_code in [200, 401, 403], f"Endpoint should exist, got {resp.status_code}"
        print(f"PASS: v2 candidate saved-jobs endpoint exists (status={resp.status_code})")
    
    def test_v2_candidate_analytics_endpoint_exists(self):
        """Verify /api/hiring/v2/candidate/analytics endpoint exists"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/candidate/analytics")
        assert resp.status_code in [200, 401, 403], f"Endpoint should exist, got {resp.status_code}"
        print(f"PASS: v2 candidate analytics endpoint exists (status={resp.status_code})")
    
    def test_v2_candidate_recommendations_endpoint_exists(self):
        """Verify /api/hiring/v2/candidate/recommendations endpoint exists"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/candidate/recommendations")
        assert resp.status_code in [200, 401, 403], f"Endpoint should exist, got {resp.status_code}"
        print(f"PASS: v2 candidate recommendations endpoint exists (status={resp.status_code})")
    
    def test_v2_employer_kpi_header_endpoint_exists(self):
        """Verify /api/hiring/v2/employer/kpi-header endpoint exists"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/employer/kpi-header")
        assert resp.status_code in [200, 401, 403], f"Endpoint should exist, got {resp.status_code}"
        print(f"PASS: v2 employer kpi-header endpoint exists (status={resp.status_code})")
    
    def test_v2_employer_sla_alerts_endpoint_exists(self):
        """Verify /api/hiring/v2/employer/sla-alerts endpoint exists"""
        resp = self.session.get(f"{BASE_URL}/api/hiring/v2/employer/sla-alerts")
        assert resp.status_code in [200, 401, 403], f"Endpoint should exist, got {resp.status_code}"
        print(f"PASS: v2 employer sla-alerts endpoint exists (status={resp.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
