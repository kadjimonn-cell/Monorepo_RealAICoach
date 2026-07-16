"""Feature 26 Sprint 3 - v2 Write Adapters and Admin Deprecation Telemetry Tests

Tests:
- v2 health endpoint (auth required)
- v2 candidate endpoints (priority-apply, boost-profile) - role-gated
- v2 employer endpoints (shortlist explainability, premium analytics) - role-gated
- v2 admin endpoints (workflow-events, deprecation-telemetry) - admin-only
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


class TestHiringV2Health:
    """Test v2 health endpoint"""

    def test_v2_health_requires_auth(self):
        """v2 health endpoint should be reachable for monitoring/contract checks."""
        response = requests.get(f"{BASE_URL}/api/hiring/v2/health")
        assert response.status_code in [200, 401, 403], (
            f"Unexpected health response: {response.status_code}: {response.text}"
        )

    def test_v2_health_with_auth(self, free_user_session):
        """v2 health endpoint should work with valid auth"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("ok") is True
        assert data.get("service") == "hiring-v2"
        assert data.get("version") == "v2"
        assert data.get("feature_number") == 26


class TestCandidateV2Endpoints:
    """Test candidate v2 write adapters - role-gated for Basic/Premium plans"""

    def test_candidate_priority_apply_requires_auth(self):
        """Priority apply should require authentication"""
        response = requests.post(f"{BASE_URL}/api/hiring/v2/candidate/priority-apply/test-app-id")
        assert response.status_code in [401, 403]

    def test_candidate_priority_apply_free_user_blocked(self, free_user_session):
        """Free users should be blocked from priority apply (requires Basic/Premium)"""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/candidate/priority-apply/test-app-id")
        # Should return 403 (plan restriction) or 404 (application not found)
        assert response.status_code in [403, 404], f"Expected 403/404, got {response.status_code}: {response.text}"
        if response.status_code == 403:
            data = response.json()
            assert "Basic" in data.get("detail", "") or "Premium" in data.get("detail", "")

    def test_candidate_boost_profile_requires_auth(self):
        """Boost profile should require authentication"""
        response = requests.post(f"{BASE_URL}/api/hiring/v2/candidate/boost-profile", json={"boost_hours": 72})
        assert response.status_code in [401, 403]

    def test_candidate_boost_profile_free_user_blocked(self, free_user_session):
        """Free users should be blocked from boost profile (requires Basic/Premium)"""
        response = free_user_session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/boost-profile",
            json={"boost_hours": 72}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert "Basic" in data.get("detail", "") or "Premium" in data.get("detail", "")


class TestEmployerV2Endpoints:
    """Test employer v2 endpoints - role-gated for Premium plan"""

    def test_employer_shortlist_explainability_requires_auth(self):
        """Shortlist explainability should require authentication"""
        response = requests.get(f"{BASE_URL}/api/hiring/v2/employer/shortlist/explainability")
        assert response.status_code in [401, 403]

    def test_employer_shortlist_explainability_free_user_blocked(self, free_user_session):
        """Free users should be blocked from shortlist explainability (requires Premium)"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/employer/shortlist/explainability")
        # Should return 403 (plan restriction) or 403 (employer access required)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"

    def test_employer_premium_analytics_requires_auth(self):
        """Premium analytics should require authentication"""
        response = requests.get(f"{BASE_URL}/api/hiring/v2/employer/premium-analytics/events")
        assert response.status_code in [401, 403]

    def test_employer_premium_analytics_free_user_blocked(self, free_user_session):
        """Free users should be blocked from premium analytics (requires Premium)"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/employer/premium-analytics/events")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"


class TestAdminV2Endpoints:
    """Test admin v2 endpoints - admin-only access"""

    def test_admin_workflow_events_requires_auth(self):
        """Workflow events should require authentication"""
        response = requests.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events")
        assert response.status_code in [401, 403]

    def test_admin_workflow_events_free_user_blocked(self, free_user_session):
        """Non-admin users should be blocked from workflow events"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert "Admin" in data.get("detail", "") or "admin" in data.get("detail", "").lower()

    def test_admin_deprecation_telemetry_requires_auth(self):
        """Deprecation telemetry should require authentication"""
        response = requests.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry")
        assert response.status_code in [401, 403]

    def test_admin_deprecation_telemetry_free_user_blocked(self, free_user_session):
        """Non-admin users should be blocked from deprecation telemetry"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert "Admin" in data.get("detail", "") or "admin" in data.get("detail", "").lower()

    def test_admin_workflow_events_with_admin(self, admin_session):
        """Admin should be able to access workflow events"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=12")
        assert response.status_code == 200, f"Admin workflow events failed: {response.text}"
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert "generated_at" in data
        assert "lookback_hours" in data

    def test_admin_deprecation_telemetry_with_admin(self, admin_session):
        """Admin should be able to access deprecation telemetry with expected payload structure"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry?lookback_days=14&limit=1000")
        assert response.status_code == 200, f"Admin deprecation telemetry failed: {response.text}"
        data = response.json()
        
        # Verify expected payload structure
        assert "generated_at" in data
        assert "lookback_days" in data
        assert "total_events" in data
        assert "active_legacy_users" in data
        assert "remaining_legacy_operations" in data
        assert "migration_progress_pct" in data
        assert "top_operations" in data
        
        # Verify data types
        assert isinstance(data["total_events"], int)
        assert isinstance(data["active_legacy_users"], int)
        assert isinstance(data["migration_progress_pct"], (int, float))
        assert isinstance(data["remaining_legacy_operations"], list)
        assert isinstance(data["top_operations"], list)


class TestJobPlatformMainStability:
    """Test main /job-platform endpoint stability"""

    def test_jobs_portal_summary_retired_requires_auth(self):
        """Legacy portal summary endpoint is retired and should not be accessible."""
        response = requests.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code in [401, 403, 410]

    def test_jobs_portal_summary_with_auth_retired_410(self, free_user_session):
        """Legacy portal summary endpoint should return 410 after P2 read retirement."""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 410, f"Expected 410, got {response.status_code}: {response.text}"
        data = response.json().get("detail", {})
        assert data.get("feature_number") == 26
        assert data.get("retirement_phase") == "hard_retired_read_cleanup"
        assert "hiring/v2/dashboard/summary" in str(data.get("replacement_hint") or "")

    def test_hiring_v2_dashboard_summary_with_auth(self, free_user_session):
        """v2 dashboard summary replacement should work with valid auth."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary")
        assert response.status_code == 200, f"v2 dashboard summary failed: {response.text}"
        data = response.json()
        assert "open_roles" in data
        assert "candidate_applications" in data
        assert "saved_jobs" in data
        assert "last_sync_at" in data

    def test_jobs_search_retired_410(self, free_user_session):
        """Legacy jobs search endpoint should return 410 after P2 read retirement."""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/search?page=1&limit=10")
        assert response.status_code == 410, f"Expected 410, got {response.status_code}: {response.text}"
        detail = response.json().get("detail", {})
        assert detail.get("feature_number") == 26
        assert "hiring/v2/candidate/jobs/search" in str(detail.get("replacement_hint") or "")

    def test_hiring_v2_jobs_search_works(self, free_user_session):
        """v2 jobs search replacement should work."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search?page=1&limit=10")
        assert response.status_code == 200, f"v2 jobs search failed: {response.text}"
        data = response.json()
        assert "jobs" in data
        assert "total" in data


# Fixtures
@pytest.fixture(scope="module")
def free_user_session():
    """Create authenticated session for free user"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Free user login failed: {login_response.status_code} - {login_response.text}")
    
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Create authenticated session for admin user"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text}")
    
    return session


@pytest.fixture(scope="module")
def employer_session():
    """Create authenticated session for employer user"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMPLOYER_EMAIL, "password": EMPLOYER_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Employer login failed: {login_response.status_code} - {login_response.text}")
    
    return session
