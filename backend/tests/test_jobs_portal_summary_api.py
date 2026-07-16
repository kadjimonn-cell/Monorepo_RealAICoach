"""
Feature 26 Jobs Portal - Sprint 0 Stabilization Tests
Tests the canonical /api/jobs/portal-summary endpoint and related job platform APIs.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
TEST_USER_EMAIL = "p1.free.1779113329@example.com"
TEST_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def authenticated_session():
    """Create authenticated session for testing."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Authentication failed: {login_response.status_code}")
    
    return session


class TestJobsPortalSummaryEndpoint:
    """Tests for the canonical /api/jobs/portal-summary endpoint."""
    
    def test_portal_summary_requires_auth(self):
        """Verify endpoint requires authentication."""
        response = requests.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_portal_summary_returns_200_when_authenticated(self, authenticated_session):
        """Verify endpoint returns 200 for authenticated users."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_portal_summary_has_canonical_fields(self, authenticated_session):
        """Verify response contains all canonical fields from Sprint 0 contract."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200
        
        data = response.json()
        
        # Top-level canonical fields
        required_fields = [
            "open_roles",
            "candidate_applications",
            "interview_applications",
            "offer_applications",
            "saved_jobs",
            "employer_jobs",
            "last_sync_at",
            "candidate",
            "employer"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
    
    def test_portal_summary_candidate_section_structure(self, authenticated_session):
        """Verify candidate section has expected nested structure."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200
        
        data = response.json()
        candidate = data.get("candidate", {})
        
        # Candidate section should have analytics, applications, saved
        assert "analytics" in candidate, "Missing candidate.analytics"
        assert "applications" in candidate, "Missing candidate.applications"
        assert "saved" in candidate, "Missing candidate.saved"
        
        # Analytics should have expected fields
        analytics = candidate.get("analytics", {})
        analytics_fields = ["total_applications", "status_breakdown", "response_rate", "interview_rate"]
        for field in analytics_fields:
            assert field in analytics, f"Missing candidate.analytics.{field}"
    
    def test_portal_summary_employer_section_structure(self, authenticated_session):
        """Verify employer section has expected structure."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200
        
        data = response.json()
        employer = data.get("employer", {})
        
        # Employer section should have access flag and optional data
        assert "has_employer_access" in employer, "Missing employer.has_employer_access"
        assert "kpi_header" in employer, "Missing employer.kpi_header"
        assert "pipeline" in employer, "Missing employer.pipeline"
        assert "error" in employer, "Missing employer.error"
    
    def test_portal_summary_numeric_fields_are_integers_or_null(self, authenticated_session):
        """Verify numeric fields are proper integers or null."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200
        
        data = response.json()
        
        numeric_fields = [
            "open_roles",
            "candidate_applications",
            "interview_applications",
            "offer_applications",
            "saved_jobs"
        ]
        
        for field in numeric_fields:
            value = data.get(field)
            assert value is None or isinstance(value, int), f"{field} should be int or null, got {type(value)}"
    
    def test_portal_summary_last_sync_at_is_iso_timestamp(self, authenticated_session):
        """Verify last_sync_at is a valid ISO timestamp."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200
        
        data = response.json()
        last_sync = data.get("last_sync_at")
        
        assert last_sync is not None, "last_sync_at should not be null"
        assert isinstance(last_sync, str), "last_sync_at should be a string"
        # Basic ISO format check
        assert "T" in last_sync, "last_sync_at should be ISO format with T separator"


class TestJobsSearchEndpoint:
    """Tests for /api/jobs/search endpoint."""
    
    def test_jobs_search_returns_200(self, authenticated_session):
        """Verify jobs search endpoint works."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/search")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_jobs_search_has_expected_structure(self, authenticated_session):
        """Verify search response has expected fields."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/search")
        assert response.status_code == 200
        
        data = response.json()
        assert "jobs" in data, "Missing jobs field"
        assert "total" in data, "Missing total field"
        # Note: page/pages fields are optional in current implementation


class TestJobsMyApplicationsEndpoint:
    """Tests for /api/jobs/my-applications endpoint."""
    
    def test_my_applications_requires_auth(self):
        """Verify endpoint requires authentication."""
        response = requests.get(f"{BASE_URL}/api/jobs/my-applications")
        assert response.status_code in [401, 403]
    
    def test_my_applications_returns_200_when_authenticated(self, authenticated_session):
        """Verify endpoint returns 200 for authenticated users."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/my-applications")
        assert response.status_code == 200
    
    def test_my_applications_has_expected_structure(self, authenticated_session):
        """Verify response has expected fields."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/my-applications")
        assert response.status_code == 200
        
        data = response.json()
        assert "applications" in data, "Missing applications field"
        assert "total" in data, "Missing total field"
        assert "stats" in data, "Missing stats field"


class TestJobsSavedEndpoint:
    """Tests for /api/jobs/saved endpoint."""
    
    def test_saved_jobs_requires_auth(self):
        """Verify endpoint requires authentication."""
        response = requests.get(f"{BASE_URL}/api/jobs/saved")
        assert response.status_code in [401, 403]
    
    def test_saved_jobs_returns_200_when_authenticated(self, authenticated_session):
        """Verify endpoint returns 200 for authenticated users."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/saved")
        assert response.status_code == 200
    
    def test_saved_jobs_has_expected_structure(self, authenticated_session):
        """Verify response has expected fields."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/saved")
        assert response.status_code == 200
        
        data = response.json()
        # API returns 'jobs' key for saved jobs list
        assert "jobs" in data or "saved_jobs" in data, "Missing jobs/saved_jobs field"


class TestJobsAnalyticsEndpoint:
    """Tests for /api/jobs/analytics endpoint."""
    
    def test_analytics_requires_auth(self):
        """Verify endpoint requires authentication."""
        response = requests.get(f"{BASE_URL}/api/jobs/analytics")
        assert response.status_code in [401, 403]
    
    def test_analytics_returns_200_when_authenticated(self, authenticated_session):
        """Verify endpoint returns 200 for authenticated users."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/analytics")
        assert response.status_code == 200
    
    def test_analytics_has_expected_structure(self, authenticated_session):
        """Verify response has expected fields."""
        response = authenticated_session.get(f"{BASE_URL}/api/jobs/analytics")
        assert response.status_code == 200
        
        data = response.json()
        expected_fields = [
            "total_applications",
            "status_breakdown",
            "response_rate",
            "interview_rate",
            "saved_jobs",
            "profile_complete"
        ]
        
        for field in expected_fields:
            assert field in data, f"Missing {field} field"


class TestNoSilentFallbackDependency:
    """Verify frontend doesn't silently depend on /employers/my-jobs."""
    
    def test_frontend_code_does_not_reference_employers_my_jobs(self):
        """Verify job-platform.tsx doesn't reference /employers/my-jobs."""
        from pathlib import Path
        source = Path("/app/frontend/app/job-platform.tsx").read_text(encoding="utf-8")
        
        # Should NOT contain reference to /employers/my-jobs
        assert "/employers/my-jobs" not in source, "Frontend should not reference /employers/my-jobs"
        
        # Should contain reference to canonical /jobs/portal-summary
        assert "/jobs/portal-summary" in source, "Frontend should use /jobs/portal-summary"
