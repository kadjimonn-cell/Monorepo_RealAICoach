"""
Feature 26 Jobs Portal Sprint 1 - Guardrails & Lifecycle Validation Tests

Tests:
1. POST /api/jobs/apply - legacy write route is hard-retired with 410 for authenticated users
2. POST /api/jobs/applicants/{job_id}/{application_id}/status - legacy write route is hard-retired with 410 for authenticated users
3. GET /api/jobs/portal-summary - stable and unchanged for frontend
4. GET /api/jobs/saved - returns both keys (saved_jobs and jobs) for compatibility
5. No regressions on /job-platform route from Sprint 0
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def free_user_session(api_client):
    """Authenticate as free-tier user and return session with cookies"""
    login_response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
    )
    if login_response.status_code != 200:
        pytest.skip(f"Free user login failed: {login_response.status_code} - {login_response.text}")
    return api_client


class TestJobsApplyFreeUser:
    """Test POST /api/jobs/apply is hard-retired in legacy namespace"""

    def test_apply_endpoint_requires_auth(self, api_client):
        """Apply endpoint still requires auth before legacy retirement response"""
        fresh_session = requests.Session()
        response = fresh_session.post(
            f"{BASE_URL}/api/jobs/apply",
            json={"job_id": "test_job_123", "cover_letter": "Test cover letter"},
        )
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got {response.status_code}"
        print("PASS: /api/jobs/apply requires authentication")

    def test_free_user_gets_410_for_legacy_apply_endpoint(self, free_user_session):
        """Authenticated free user should get 410 on legacy apply endpoint."""
        apply_response = free_user_session.post(
            f"{BASE_URL}/api/jobs/apply",
            json={"job_id": f"legacy_job_{uuid.uuid4().hex[:8]}", "cover_letter": "Legacy route retirement check"},
        )
        assert apply_response.status_code == 410, f"Expected 410, got {apply_response.status_code}"
        detail = apply_response.json().get("detail", {})
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: Free user gets 410 on legacy /api/jobs/apply")


class TestApplicationStatusTransitionGuardrails:
    """Test POST /api/jobs/applicants/{job_id}/{application_id}/status is legacy-retired"""

    def test_status_update_returns_410_for_legacy_route(self, free_user_session):
        """Legacy status update endpoint returns 410 for authenticated users."""
        response = free_user_session.post(
            f"{BASE_URL}/api/jobs/applicants/test_job/test_app/status",
            json={"status": "viewed"},
        )
        assert response.status_code == 410, f"Expected 410, got {response.status_code}"
        detail = response.json().get("detail", {})
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: Legacy status update endpoint returns 410")

    def test_invalid_status_payload_still_returns_410_before_validation(self, free_user_session):
        """Legacy retirement should trigger before status validation."""
        response = free_user_session.post(
            f"{BASE_URL}/api/jobs/applicants/test_job/test_app/status",
            json={"status": "invalid_status_xyz"},
        )
        assert response.status_code == 410, f"Expected 410, got {response.status_code}"
        print("PASS: Legacy retirement wins before payload validation")


class TestPortalSummaryStability:
    """Test GET /api/jobs/portal-summary remains stable and unchanged for frontend"""

    def test_portal_summary_requires_auth(self, api_client):
        """Portal summary endpoint should require authentication"""
        fresh_session = requests.Session()
        response = fresh_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got {response.status_code}"
        print("PASS: /api/jobs/portal-summary requires authentication")

    def test_portal_summary_returns_canonical_fields(self, free_user_session):
        """Portal summary should return all canonical fields for frontend"""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200, f"Portal summary failed: {response.status_code}"
        
        data = response.json()
        
        # Check canonical top-level fields
        canonical_fields = [
            "open_roles",
            "candidate_applications",
            "interview_applications",
            "offer_applications",
            "saved_jobs",
            "employer_jobs",
            "last_sync_at",
            "candidate",
            "employer",
        ]
        
        for field in canonical_fields:
            assert field in data, f"Missing canonical field: {field}"
        
        # Verify numeric fields are integers or null
        numeric_fields = ["open_roles", "candidate_applications", "interview_applications", "offer_applications", "saved_jobs"]
        for field in numeric_fields:
            value = data.get(field)
            assert value is None or isinstance(value, int), f"Field {field} should be int or null, got {type(value)}"
        
        # Verify nested structures exist
        assert "candidate" in data and isinstance(data["candidate"], dict), "candidate section should be dict"
        assert "employer" in data and isinstance(data["employer"], dict), "employer section should be dict"
        
        # Verify candidate section has expected keys
        candidate_section = data["candidate"]
        assert "analytics" in candidate_section, "candidate.analytics missing"
        assert "applications" in candidate_section, "candidate.applications missing"
        assert "saved" in candidate_section, "candidate.saved missing"
        
        # Verify employer section has expected keys
        employer_section = data["employer"]
        assert "has_employer_access" in employer_section, "employer.has_employer_access missing"
        
        print("PASS: Portal summary returns all canonical fields with correct structure")
        print(f"  - open_roles: {data.get('open_roles')}")
        print(f"  - candidate_applications: {data.get('candidate_applications')}")
        print(f"  - saved_jobs: {data.get('saved_jobs')}")
        print(f"  - employer_jobs: {data.get('employer_jobs')}")

    def test_portal_summary_last_sync_at_is_iso_format(self, free_user_session):
        """last_sync_at should be ISO format timestamp"""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200
        
        data = response.json()
        last_sync = data.get("last_sync_at")
        assert last_sync is not None, "last_sync_at should not be null"
        assert "T" in last_sync, "last_sync_at should be ISO format with T separator"
        print(f"PASS: last_sync_at is ISO format: {last_sync}")


class TestSavedJobsCompatibility:
    """Test GET /api/jobs/saved returns both keys (saved_jobs and jobs) for compatibility"""

    def test_saved_jobs_requires_auth(self, api_client):
        """Saved jobs endpoint should require authentication"""
        fresh_session = requests.Session()
        response = fresh_session.get(f"{BASE_URL}/api/jobs/saved")
        assert response.status_code == 401, f"Expected 401 for unauthenticated, got {response.status_code}"
        print("PASS: /api/jobs/saved requires authentication")

    def test_saved_jobs_returns_both_keys(self, free_user_session):
        """Saved jobs should return both 'saved_jobs' and 'jobs' keys for backwards compatibility"""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/saved")
        assert response.status_code == 200, f"Saved jobs failed: {response.status_code}"
        
        data = response.json()
        
        # Both keys should be present for compatibility
        assert "saved_jobs" in data, "Missing 'saved_jobs' key for backwards compatibility"
        assert "jobs" in data, "Missing 'jobs' key for backwards compatibility"
        assert "total" in data, "Missing 'total' key"
        
        # Both should be lists
        assert isinstance(data["saved_jobs"], list), "saved_jobs should be a list"
        assert isinstance(data["jobs"], list), "jobs should be a list"
        
        # Both should have same content
        assert data["saved_jobs"] == data["jobs"], "saved_jobs and jobs should have identical content"
        
        print("PASS: /api/jobs/saved returns both keys (saved_jobs and jobs)")
        print(f"  - saved_jobs count: {len(data['saved_jobs'])}")
        print(f"  - jobs count: {len(data['jobs'])}")
        print(f"  - total: {data.get('total')}")


class TestTransitionValidationLogic:
    """Test validate_application_transition helper function behavior via code inspection"""

    def test_transition_guard_exists_in_jobs_shared(self):
        """Verify validate_application_transition function exists in jobs_shared.py"""
        from pathlib import Path
        source = Path("/app/backend/routes/jobs_shared.py").read_text(encoding="utf-8")
        
        assert "def validate_application_transition(" in source, "validate_application_transition function missing"
        assert "terminal_status" in source, "terminal_status check missing"
        assert "reverse_transition" in source, "reverse_transition check missing"
        assert "hired_requires_interview_or_offer" in source, "hired_requires_interview_or_offer check missing"
        
        print("PASS: validate_application_transition function exists with expected guards")

    def test_status_update_uses_transition_guard(self):
        """Verify update_application_status endpoint uses transition guard"""
        from pathlib import Path
        source = Path("/app/backend/routes/jobs.py").read_text(encoding="utf-8")
        
        assert "validate_application_transition(" in source, "validate_application_transition not called"
        assert "Invalid application status transition" in source, "Error message missing"
        assert "status_code=409" in source, "409 status code missing"
        
        print("PASS: update_application_status uses transition guard with 409 error")

    def test_apply_uses_hiring_plan_guard(self):
        """Verify apply endpoint uses require_hiring_plan guard"""
        from pathlib import Path
        source = Path("/app/backend/routes/jobs.py").read_text(encoding="utf-8")
        
        assert 'require_hiring_plan(request, min_plan="free")' in source, "require_hiring_plan guard missing from apply"
        assert "candidate_application_submitted" in source, "workflow event logging missing"
        
        print("PASS: apply endpoint uses require_hiring_plan guard with min_plan='free'")


class TestWorkflowEventInstrumentation:
    """Test workflow event instrumentation is in place"""

    def test_record_hiring_workflow_event_exists(self):
        """Verify record_hiring_workflow_event function exists"""
        from pathlib import Path
        source = Path("/app/backend/routes/jobs_shared.py").read_text(encoding="utf-8")
        
        assert "async def record_hiring_workflow_event(" in source, "record_hiring_workflow_event function missing"
        assert "hiring_workflow_events" in source, "hiring_workflow_events collection reference missing"
        assert "event_type" in source, "event_type parameter missing"
        
        print("PASS: record_hiring_workflow_event function exists with expected structure")

    def test_apply_logs_workflow_event(self):
        """Verify apply endpoint logs workflow event"""
        from pathlib import Path
        source = Path("/app/backend/routes/jobs.py").read_text(encoding="utf-8")
        
        assert "record_hiring_workflow_event" in source, "record_hiring_workflow_event not called"
        assert "candidate_application_submitted" in source, "candidate_application_submitted event type missing"
        
        print("PASS: apply endpoint logs candidate_application_submitted workflow event")


class TestJobPlatformRouteNoRegression:
    """Test /job-platform route has no regressions from Sprint 0"""

    def test_jobs_search_endpoint_works(self, free_user_session):
        """Jobs search endpoint should work"""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/search?limit=5")
        assert response.status_code == 200, f"Jobs search failed: {response.status_code}"
        
        data = response.json()
        assert "jobs" in data, "Missing 'jobs' key"
        assert "total" in data, "Missing 'total' key"
        
        print(f"PASS: Jobs search works - found {data.get('total', 0)} total jobs")

    def test_my_applications_endpoint_works(self, free_user_session):
        """My applications endpoint should work"""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/my-applications")
        assert response.status_code == 200, f"My applications failed: {response.status_code}"
        
        data = response.json()
        assert "applications" in data, "Missing 'applications' key"
        assert "total" in data, "Missing 'total' key"
        
        print(f"PASS: My applications works - found {data.get('total', 0)} applications")

    def test_analytics_endpoint_works(self, free_user_session):
        """Analytics endpoint should work"""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/analytics")
        assert response.status_code == 200, f"Analytics failed: {response.status_code}"
        
        data = response.json()
        assert "total_applications" in data, "Missing 'total_applications' key"
        assert "status_breakdown" in data, "Missing 'status_breakdown' key"
        
        print(f"PASS: Analytics works - total_applications: {data.get('total_applications', 0)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
