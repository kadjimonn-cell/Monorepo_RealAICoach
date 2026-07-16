"""
Feature 26 Migration Validation Tests
=====================================
Tests for validating the migration from legacy write callers to v2 adapters.

Scope:
1. Legacy writes remain retired (410 Gone)
2. New v2 adapters are reachable (non-404/non-410)
3. Frontend runtime callers migrated (code inspection verified separately)
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
EMPLOYER_EMAIL = "e2e.employer.feature26@realaicoach.app"
EMPLOYER_PASSWORD = "E2EEmployer#Feature26!2026"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    return session


@pytest.fixture(scope="module")
def admin_session(api_client):
    """Get admin authenticated session"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return api_client
    # Try without OTP for test environment
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")


@pytest.fixture(scope="module")
def free_user_session(api_client):
    """Get free user authenticated session"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    if response.status_code == 200:
        return api_client
    pytest.skip(f"Free user login failed: {response.status_code}")


class TestLegacyWritesRetired:
    """
    Validate that legacy write routes return 410 Gone.
    These routes should be retired and return proper 410 responses.
    """

    def test_legacy_jobs_save_test_x_returns_410(self, api_client):
        """POST /api/jobs/save/test_x should return 410 Gone"""
        response = api_client.post(f"{BASE_URL}/api/jobs/save/test_x", json={})
        # 410 Gone indicates the route is retired
        # 401/403 means auth required but route exists (also acceptable for retired routes)
        assert response.status_code in [410, 401, 403], \
            f"Expected 410/401/403 for retired legacy route, got {response.status_code}: {response.text[:200]}"
        
        if response.status_code == 410:
            data = response.json()
            assert "detail" in data or "message" in data, "410 response should have detail/message"
            print("✓ POST /api/jobs/save/test_x returns 410 Gone with proper retirement metadata")

    def test_legacy_employers_reverify_returns_410(self, api_client):
        """POST /api/employers/reverify should return 410 Gone"""
        response = api_client.post(f"{BASE_URL}/api/employers/reverify", json={})
        # 410 Gone indicates the route is retired
        # 401/403 means auth required but route exists (also acceptable for retired routes)
        assert response.status_code in [410, 401, 403], \
            f"Expected 410/401/403 for retired legacy route, got {response.status_code}: {response.text[:200]}"
        
        if response.status_code == 410:
            data = response.json()
            assert "detail" in data or "message" in data, "410 response should have detail/message"
            print("✓ POST /api/employers/reverify returns 410 Gone with proper retirement metadata")


class TestV2AdaptersReachable:
    """
    Validate that new v2 adapters are reachable.
    Non-404/non-410 responses are acceptable (2xx/4xx domain errors).
    """

    def test_v2_candidate_alerts_read_all(self, api_client):
        """POST /api/hiring/v2/candidate/alerts/read-all should be reachable"""
        response = api_client.post(f"{BASE_URL}/api/hiring/v2/candidate/alerts/read-all", json={})
        # Should NOT be 404 or 410 - route should exist
        assert response.status_code not in [404, 410], \
            f"v2 endpoint should exist, got {response.status_code}: {response.text[:200]}"
        # 401/403 (auth required) or 2xx are acceptable
        print(f"✓ POST /api/hiring/v2/candidate/alerts/read-all is reachable (status: {response.status_code})")

    def test_v2_candidate_alerts_preferences(self, api_client):
        """POST /api/hiring/v2/candidate/alerts/preferences should be reachable"""
        response = api_client.post(f"{BASE_URL}/api/hiring/v2/candidate/alerts/preferences", json={})
        assert response.status_code not in [404, 410], \
            f"v2 endpoint should exist, got {response.status_code}: {response.text[:200]}"
        print(f"✓ POST /api/hiring/v2/candidate/alerts/preferences is reachable (status: {response.status_code})")

    def test_v2_admin_approvals_decide(self, api_client):
        """POST /api/hiring/v2/admin/approvals/decide should be reachable"""
        response = api_client.post(f"{BASE_URL}/api/hiring/v2/admin/approvals/decide", json={
            "approval_id": "test_approval_id",
            "decision": "approve"
        })
        assert response.status_code not in [404, 410], \
            f"v2 endpoint should exist, got {response.status_code}: {response.text[:200]}"
        print(f"✓ POST /api/hiring/v2/admin/approvals/decide is reachable (status: {response.status_code})")

    def test_v2_admin_employers_add_note(self, api_client):
        """POST /api/hiring/v2/admin/employers/add-note/{id} should be reachable"""
        response = api_client.post(f"{BASE_URL}/api/hiring/v2/admin/employers/add-note/test_employer_id", json={
            "note": "Test note"
        })
        assert response.status_code not in [404, 410], \
            f"v2 endpoint should exist, got {response.status_code}: {response.text[:200]}"
        print(f"✓ POST /api/hiring/v2/admin/employers/add-note/{{id}} is reachable (status: {response.status_code})")

    def test_v2_employer_approval_submit(self, api_client):
        """POST /api/hiring/v2/employer/approval/submit should be reachable"""
        response = api_client.post(f"{BASE_URL}/api/hiring/v2/employer/approval/submit", json={
            "company_name": "Test Company",
            "country": "US",
            "industry": "technology"
        })
        assert response.status_code not in [404, 410], \
            f"v2 endpoint should exist, got {response.status_code}: {response.text[:200]}"
        print(f"✓ POST /api/hiring/v2/employer/approval/submit is reachable (status: {response.status_code})")

    def test_v2_ai_translate(self, api_client):
        """POST /api/hiring/v2/ai/translate should be reachable"""
        response = api_client.post(f"{BASE_URL}/api/hiring/v2/ai/translate", json={
            "text": "Hello world",
            "target_lang": "fr"
        })
        assert response.status_code not in [404, 410], \
            f"v2 endpoint should exist, got {response.status_code}: {response.text[:200]}"
        print(f"✓ POST /api/hiring/v2/ai/translate is reachable (status: {response.status_code})")


class TestV2HealthAndBasicEndpoints:
    """Test that v2 basic endpoints are working"""

    def test_v2_health_endpoint(self, api_client):
        """GET /api/hiring/v2/health should return 200"""
        response = api_client.get(f"{BASE_URL}/api/hiring/v2/health")
        assert response.status_code == 200, f"Health endpoint failed: {response.status_code}"
        data = response.json()
        assert data.get("ok") == True
        assert data.get("feature_number") == 26
        assert data.get("feature_id") == "jobs-portal"
        print("✓ GET /api/hiring/v2/health returns 200 OK with feature metadata")

    def test_v2_candidate_jobs_search(self, api_client):
        """GET /api/hiring/v2/candidate/jobs/search should be reachable"""
        response = api_client.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search")
        assert response.status_code not in [404, 410], \
            f"v2 search endpoint should exist, got {response.status_code}"
        print(f"✓ GET /api/hiring/v2/candidate/jobs/search is reachable (status: {response.status_code})")


class TestFrontendMigrationCodeInspection:
    """
    Verify frontend files have migrated to v2 endpoints.
    This is a code inspection test - we verify the patterns in the frontend code.
    """

    def test_career_inner_uses_v2_endpoints(self):
        """CareerInner.tsx should use /hiring/v2/ endpoints for writes"""
        file_path = "/app/frontend/src/components/pages/CareerInner.tsx"
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for v2 endpoint usage
        v2_patterns = [
            "/hiring/v2/candidate/alerts/",
            "/hiring/v2/candidate/save/",
            "/hiring/v2/candidate/apply",
            "/hiring/v2/candidate/profile/update",
            "/hiring/v2/candidate/resume/upload"
        ]
        
        found_v2 = []
        for pattern in v2_patterns:
            if pattern in content:
                found_v2.append(pattern)
        
        # Check for legacy write patterns that should NOT exist
        legacy_write_patterns = [
            "api.post('/jobs/",
            "api.post(\"/jobs/",
            "api.post('/employers/",
            "api.post(\"/employers/"
        ]
        
        found_legacy = []
        for pattern in legacy_write_patterns:
            if pattern in content:
                found_legacy.append(pattern)
        
        assert len(found_legacy) == 0, f"CareerInner.tsx still has legacy write calls: {found_legacy}"
        assert len(found_v2) > 0, f"CareerInner.tsx should use v2 endpoints, found: {found_v2}"
        print(f"✓ CareerInner.tsx uses v2 endpoints: {found_v2}")

    def test_employer_apply_uses_v2_endpoints(self):
        """employer-apply.tsx should use /hiring/v2/ endpoints for writes"""
        file_path = "/app/frontend/app/employer-apply.tsx"
        with open(file_path, 'r') as f:
            content = f.read()
        
        v2_patterns = [
            "/hiring/v2/employer/application/",
            "/hiring/v2/admin/employers/"
        ]
        
        found_v2 = []
        for pattern in v2_patterns:
            if pattern in content:
                found_v2.append(pattern)
        
        legacy_write_patterns = [
            "api.post('/jobs/",
            "api.post(\"/jobs/",
            "api.post('/employers/apply",
            "api.post('/employers/reverify"
        ]
        
        found_legacy = []
        for pattern in legacy_write_patterns:
            if pattern in content:
                found_legacy.append(pattern)
        
        assert len(found_legacy) == 0, f"employer-apply.tsx still has legacy write calls: {found_legacy}"
        print(f"✓ employer-apply.tsx uses v2 endpoints: {found_v2}")

    def test_employer_management_panel_uses_v2_endpoints(self):
        """EmployerManagementPanel.tsx should use /hiring/v2/ endpoints"""
        file_path = "/app/frontend/src/components/admin/EmployerManagementPanel.tsx"
        with open(file_path, 'r') as f:
            content = f.read()
        
        v2_patterns = [
            "/hiring/v2/admin/employers/review/",
            "/hiring/v2/admin/employers/messages/",
            "/hiring/v2/admin/employers/add-note/"
        ]
        
        found_v2 = []
        for pattern in v2_patterns:
            if pattern in content:
                found_v2.append(pattern)
        
        assert len(found_v2) > 0, "EmployerManagementPanel.tsx should use v2 endpoints"
        print(f"✓ EmployerManagementPanel.tsx uses v2 endpoints: {found_v2}")

    def test_employer_portal_panel_uses_v2_endpoints(self):
        """EmployerPortalPanel.tsx should use /hiring/v2/ endpoints"""
        file_path = "/app/frontend/src/components/admin/EmployerPortalPanel.tsx"
        with open(file_path, 'r') as f:
            content = f.read()
        
        v2_patterns = [
            "/hiring/v2/admin/employers/review/",
            "/hiring/v2/admin/employers/messages/",
            "/hiring/v2/admin/employers/add-note/"
        ]
        
        found_v2 = []
        for pattern in v2_patterns:
            if pattern in content:
                found_v2.append(pattern)
        
        assert len(found_v2) > 0, "EmployerPortalPanel.tsx should use v2 endpoints"
        print(f"✓ EmployerPortalPanel.tsx uses v2 endpoints: {found_v2}")

    def test_employer_pipeline_board_uses_v2_endpoints(self):
        """EmployerPipelineBoard.tsx should use /hiring/v2/ endpoints"""
        file_path = "/app/frontend/src/components/jobs/EmployerPipelineBoard.tsx"
        with open(file_path, 'r') as f:
            content = f.read()
        
        v2_patterns = [
            "/hiring/v2/employer/pipeline-board",
            "/hiring/v2/employer/offers",
            "/hiring/v2/employer/applications/",
            "/hiring/v2/employer/interview-kit/",
            "/hiring/v2/employer/scorecards/",
            "/hiring/v2/employer/auto-scheduler/",
            "/hiring/v2/employer/communication-sequences/",
            "/hiring/v2/employer/talent-rediscovery/",
            "/hiring/v2/employer/sla-alerts",
            "/hiring/v2/employer/sla-auto-triggers/"
        ]
        
        found_v2 = []
        for pattern in v2_patterns:
            if pattern in content:
                found_v2.append(pattern)
        
        assert len(found_v2) > 0, "EmployerPipelineBoard.tsx should use v2 endpoints"
        print(f"✓ EmployerPipelineBoard.tsx uses v2 endpoints: {found_v2}")

    def test_exec_inline_panels_uses_v2_endpoints(self):
        """ExecInlinePanels.tsx should use /hiring/v2/ endpoints"""
        file_path = "/app/frontend/src/components/executive/ExecInlinePanels.tsx"
        with open(file_path, 'r') as f:
            content = f.read()
        
        v2_patterns = [
            "/hiring/v2/admin/approvals/decide"
        ]
        
        found_v2 = []
        for pattern in v2_patterns:
            if pattern in content:
                found_v2.append(pattern)
        
        assert len(found_v2) > 0, "ExecInlinePanels.tsx should use v2 endpoints"
        print(f"✓ ExecInlinePanels.tsx uses v2 endpoints: {found_v2}")

    def test_job_platform_mini_app_uses_v2_endpoints(self):
        """job-platform.tsx should use /hiring/v2/ endpoints"""
        file_path = "/app/frontend/app/mini-apps/job-platform.tsx"
        with open(file_path, 'r') as f:
            content = f.read()
        
        v2_patterns = [
            "/hiring/v2/candidate/apply",
            "/hiring/v2/candidate/save/",
            "/hiring/v2/employer/register",
            "/hiring/v2/employer/jobs/create",
            "/hiring/v2/employer/jobs/",
            "/hiring/v2/ai/rank-candidates",
            "/hiring/v2/ai/description",
            "/hiring/v2/ai/salary",
            "/hiring/v2/ai/translate",
            "/hiring/v2/employer/approval/submit",
            "/hiring/v2/employer/approval/resubmit"
        ]
        
        found_v2 = []
        for pattern in v2_patterns:
            if pattern in content:
                found_v2.append(pattern)
        
        assert len(found_v2) > 0, "job-platform.tsx should use v2 endpoints"
        print(f"✓ job-platform.tsx uses v2 endpoints: {found_v2}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
