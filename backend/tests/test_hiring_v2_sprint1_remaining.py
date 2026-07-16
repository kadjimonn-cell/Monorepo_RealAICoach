"""Feature 26 Sprint 1 Remaining - Hiring v2 Endpoints Testing

Tests for:
- GET /api/hiring/v2/health returns 200
- GET /api/hiring/v2/dashboard/summary returns 200 for free user
- GET /api/hiring/v2/candidate/jobs/search returns 200 for free user
- GET /api/hiring/v2/admin/workflow-events enforces admin-only access (free=403, admin=200)
- GET /api/hiring/v2/employer/kpi-header and /employer/offers enforce employer gating
- No regressions in /api/jobs/portal-summary and /api/jobs/saved
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

# Test credentials
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def free_user_session():
    """Login as free user and return session with cookies."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
    )
    assert response.status_code == 200, f"Free user login failed: {response.text}"
    data = response.json()
    assert data.get("is_admin") is False, "Expected non-admin user"
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin user and return session with cookies."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    assert data.get("is_admin") is True, "Expected admin user"
    return session


class TestHiringV2Health:
    """Test /api/hiring/v2/health endpoint."""

    def test_health_returns_200(self, free_user_session):
        """GET /api/hiring/v2/health returns 200 for free user."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("ok") is True
        assert data.get("service") == "hiring-v2"
        assert data.get("version") == "v2"
        assert data.get("feature_id") == "jobs-portal"
        assert data.get("feature_number") == 26


class TestHiringV2DashboardSummary:
    """Test /api/hiring/v2/dashboard/summary endpoint."""

    def test_dashboard_summary_returns_200_for_free_user(self, free_user_session):
        """GET /api/hiring/v2/dashboard/summary returns 200 for free user."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify canonical fields exist
        assert "open_roles" in data
        assert "candidate_applications" in data
        assert "interview_applications" in data
        assert "offer_applications" in data
        assert "saved_jobs" in data
        assert "employer_jobs" in data
        assert "last_sync_at" in data
        assert "candidate" in data
        assert "employer" in data


class TestHiringV2CandidateJobsSearch:
    """Test /api/hiring/v2/candidate/jobs/search endpoint."""

    def test_candidate_jobs_search_returns_200_for_free_user(self, free_user_session):
        """GET /api/hiring/v2/candidate/jobs/search returns 200 for free user."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data


class TestHiringV2AdminWorkflowEvents:
    """Test /api/hiring/v2/admin/workflow-events endpoint access control."""

    def test_admin_workflow_events_returns_403_for_free_user(self, free_user_session):
        """GET /api/hiring/v2/admin/workflow-events returns 403 for free user (admin-only)."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail") == "Admin access required"

    def test_admin_workflow_events_returns_200_for_admin(self, admin_session):
        """GET /api/hiring/v2/admin/workflow-events returns 200 for admin user."""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "generated_at" in data
        assert "lookback_hours" in data
        assert "filters" in data
        assert "include_metadata" in data
        assert "total" in data
        assert "events" in data


class TestHiringV2EmployerGating:
    """Test employer-gated endpoints enforce access control."""

    def test_employer_kpi_header_returns_403_for_free_user(self, free_user_session):
        """GET /api/hiring/v2/employer/kpi-header returns 403 for free user (employer-gated)."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/employer/kpi-header")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail") == "Approved employer access required"

    def test_employer_offers_returns_403_for_free_user(self, free_user_session):
        """GET /api/hiring/v2/employer/offers returns 403 for free user (employer-gated)."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/employer/offers")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail") == "Approved employer access required"

    def test_employer_kpi_header_returns_403_for_admin_without_employer_approval(self, admin_session):
        """GET /api/hiring/v2/employer/kpi-header returns 403 for admin without employer approval.
        
        Note: Admin users don't automatically have employer access - they need an approved
        employer application with post_job permission. This is by design.
        """
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/employer/kpi-header")
        # Admin without employer approval should get 403
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"


class TestJobsPortalRegressions:
    """Test no regressions in /api/jobs/portal-summary and /api/jobs/saved."""

    def test_jobs_portal_summary_returns_200(self, free_user_session):
        """GET /api/jobs/portal-summary returns 200 with all canonical fields."""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify canonical fields
        assert "open_roles" in data
        assert "candidate_applications" in data
        assert "interview_applications" in data
        assert "offer_applications" in data
        assert "saved_jobs" in data
        assert "employer_jobs" in data
        assert "last_sync_at" in data
        assert "candidate" in data
        assert "employer" in data

    def test_jobs_saved_returns_200_with_backwards_compatible_keys(self, free_user_session):
        """GET /api/jobs/saved returns 200 with both saved_jobs and jobs keys."""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/saved")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Verify backwards compatible keys
        assert "saved_jobs" in data, "Missing 'saved_jobs' key for backwards compatibility"
        assert "jobs" in data, "Missing 'jobs' key"
        assert "total" in data, "Missing 'total' key"


class TestHiringV2FreePatternAccess:
    """Verify /api/hiring/v2/ is in FREE_PATTERNS for free user access."""

    def test_hiring_v2_in_free_patterns(self):
        """Verify /api/hiring/v2/ pattern is in FREE_PATTERNS in access_control_engine.py."""
        from pathlib import Path
        source = Path("/app/backend/utils/access_control_engine.py").read_text(encoding="utf-8")
        assert 'r"^/api/hiring/v2/"' in source, "Missing /api/hiring/v2/ in FREE_PATTERNS"


class TestUseJobsPortalSummaryHook:
    """Verify useJobsPortalSummary hook exists and has correct structure."""

    def test_hook_file_exists(self):
        """Verify useJobsPortalSummary.ts hook file exists."""
        from pathlib import Path
        hook_path = Path("/app/frontend/src/hooks/useJobsPortalSummary.ts")
        assert hook_path.exists(), "useJobsPortalSummary.ts hook file not found"

    def test_hook_exports_correct_types(self):
        """Verify hook exports JobsPortalSummaryState type and useJobsPortalSummary function."""
        from pathlib import Path
        source = Path("/app/frontend/src/hooks/useJobsPortalSummary.ts").read_text(encoding="utf-8")
        assert "export type JobsPortalSummaryState" in source, "Missing JobsPortalSummaryState export"
        assert "export const useJobsPortalSummary" in source, "Missing useJobsPortalSummary export"
        assert "openRoles" in source, "Missing openRoles field"
        assert "candidateApplications" in source, "Missing candidateApplications field"
        assert "interviewApplications" in source, "Missing interviewApplications field"
        assert "offerApplications" in source, "Missing offerApplications field"
        assert "savedJobs" in source, "Missing savedJobs field"
        assert "employerJobs" in source, "Missing employerJobs field"
