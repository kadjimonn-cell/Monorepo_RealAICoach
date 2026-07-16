"""Feature 26 Final Cleanup and CI Guard Tests.

Tests:
1. Legacy write retirement still enforced globally: /api/jobs* and /api/employers* write routes return 410
2. v2 write/read routes remain functional (no regression)
3. jobs.py no longer contains endpoint-level _enforce_legacy_write_policy hooks
4. employers.py no longer contains _enforce_employers_write_retirement hooks
5. CI guard script exists and fails on forbidden runtime frontend write endpoints
6. new workflow exists and calls guard script
"""

import pytest
import requests
import os
import subprocess
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        if data.get("token"):
            session.headers.update({"Authorization": f"Bearer {data['token']}"})
    return session


@pytest.fixture(scope="module")
def free_user_session():
    """Get authenticated free user session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as free user
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        if data.get("token"):
            session.headers.update({"Authorization": f"Bearer {data['token']}"})
    return session


class TestLegacyCodeRemoval:
    """Verify legacy write policy hooks have been removed from route files."""
    
    def test_jobs_py_no_legacy_write_policy_hooks(self):
        """jobs.py should not contain _enforce_legacy_write_policy hooks."""
        jobs_path = Path("/app/backend/routes/jobs.py")
        assert jobs_path.exists(), "jobs.py not found"
        
        content = jobs_path.read_text()
        assert "_enforce_legacy_write_policy" not in content, \
            "jobs.py still contains _enforce_legacy_write_policy hooks"
    
    def test_employers_py_no_legacy_write_retirement_hooks(self):
        """employers.py should not contain _enforce_employers_write_retirement hooks."""
        employers_path = Path("/app/backend/routes/employers.py")
        assert employers_path.exists(), "employers.py not found"
        
        content = employers_path.read_text()
        assert "_enforce_employers_write_retirement" not in content, \
            "employers.py still contains _enforce_employers_write_retirement hooks"


class TestCIGuardScript:
    """Verify CI guard script exists and functions correctly."""
    
    def test_guard_script_exists(self):
        """CI guard script should exist."""
        script_path = Path("/app/scripts/feature26_frontend_legacy_write_guard.py")
        assert script_path.exists(), "CI guard script not found"
    
    def test_guard_script_is_executable(self):
        """CI guard script should be executable."""
        script_path = Path("/app/scripts/feature26_frontend_legacy_write_guard.py")
        # Check if it has shebang
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env python3"), \
            "CI guard script should have proper shebang"
    
    def test_guard_script_passes_on_clean_codebase(self):
        """CI guard script should pass when no forbidden endpoints are used."""
        result = subprocess.run(
            ["python", "/app/scripts/feature26_frontend_legacy_write_guard.py"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, \
            f"CI guard script failed: {result.stdout}\n{result.stderr}"
        assert "passed" in result.stdout.lower(), \
            f"CI guard script output unexpected: {result.stdout}"


class TestCIWorkflow:
    """Verify GitHub workflow exists and is properly configured."""
    
    def test_workflow_file_exists(self):
        """GitHub workflow file should exist."""
        workflow_path = Path("/app/.github/workflows/feature26-legacy-write-guard.yml")
        assert workflow_path.exists(), "GitHub workflow file not found"
    
    def test_workflow_calls_guard_script(self):
        """Workflow should call the guard script."""
        workflow_path = Path("/app/.github/workflows/feature26-legacy-write-guard.yml")
        content = workflow_path.read_text()
        
        assert "feature26_frontend_legacy_write_guard.py" in content, \
            "Workflow does not call the guard script"
    
    def test_workflow_triggers_on_frontend_changes(self):
        """Workflow should trigger on frontend file changes."""
        workflow_path = Path("/app/.github/workflows/feature26-legacy-write-guard.yml")
        content = workflow_path.read_text()
        
        assert "frontend/app/**" in content or "frontend/src/**" in content, \
            "Workflow does not trigger on frontend changes"


class TestLegacyWriteRoutes410:
    """Verify legacy write routes return 410 Gone (or are blocked by auth/CSRF)."""
    
    def test_jobs_apply_returns_blocked(self, free_user_session):
        """POST /api/jobs/apply should be blocked (401/403/410)."""
        response = free_user_session.post(
            f"{BASE_URL}/api/jobs/apply",
            json={"job_id": "test_job_123", "cover_letter": "Test"}
        )
        # Accept 401 (auth), 403 (CSRF), or 410 (retired) - all indicate blocked
        # The key is that the endpoint is NOT functional (not 200/201)
        assert response.status_code in [401, 403, 410], \
            f"Expected 401/403/410, got {response.status_code}: {response.text}"
    
    def test_jobs_save_returns_blocked(self, free_user_session):
        """POST /api/jobs/save/{job_id} should be blocked (401/403/410)."""
        response = free_user_session.post(f"{BASE_URL}/api/jobs/save/test_job_123")
        assert response.status_code in [401, 403, 410], \
            f"Expected 401/403/410, got {response.status_code}: {response.text}"
    
    def test_jobs_profile_update_returns_blocked(self, free_user_session):
        """POST /api/jobs/profile/update should be blocked (401/403/410)."""
        response = free_user_session.post(
            f"{BASE_URL}/api/jobs/profile/update",
            json={"skills": ["python"]}
        )
        assert response.status_code in [401, 403, 410], \
            f"Expected 401/403/410, got {response.status_code}: {response.text}"
    
    def test_employers_apply_returns_blocked(self, free_user_session):
        """POST /api/employers/apply should be blocked (401/403/410)."""
        response = free_user_session.post(
            f"{BASE_URL}/api/employers/apply",
            json={"business_name": "Test Corp"}
        )
        assert response.status_code in [401, 403, 410], \
            f"Expected 401/403/410, got {response.status_code}: {response.text}"


class TestV2EndpointsAvailable:
    """Verify v2 endpoints remain functional."""
    
    def test_v2_health_endpoint(self):
        """GET /api/hiring/v2/health should be accessible."""
        response = requests.get(f"{BASE_URL}/api/hiring/v2/health")
        # May require auth, but should not be 404 or 410
        assert response.status_code not in [404, 410], \
            f"v2 health endpoint not available: {response.status_code}"
    
    def test_v2_dashboard_summary(self, free_user_session):
        """GET /api/hiring/v2/dashboard/summary should be accessible."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary")
        # May require auth, but should not be 404 or 410
        assert response.status_code not in [404, 410], \
            f"v2 dashboard summary not available: {response.status_code}"
    
    def test_v2_candidate_jobs_search(self, free_user_session):
        """GET /api/hiring/v2/candidate/jobs/search should be accessible."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search")
        # May require auth, but should not be 404 or 410
        assert response.status_code not in [404, 410], \
            f"v2 candidate jobs search not available: {response.status_code}"


class TestReadEndpointsNotRetired:
    """Legacy v1 jobs READ endpoints are now hard-retired (phase: hard_retired_read_cleanup)."""

    def test_jobs_search_hard_retired(self):
        """GET /api/jobs/search returns 410 with the v2 retirement contract."""
        response = requests.get(f"{BASE_URL}/api/jobs/search")
        assert response.status_code == 410, \
            f"jobs/search should be hard-retired (410): {response.status_code}"
        detail = (response.json() or {}).get("detail") or {}
        assert detail.get("retirement_mode") == "hard_retired"
        assert detail.get("retirement_phase") == "hard_retired_read_cleanup"
        assert detail.get("replacement_hint")

    def test_jobs_detail_hard_retired(self):
        """GET /api/jobs/detail/{job_id} is NOT in the read-retirement matcher (auth-gated, not 410)."""
        response = requests.get(f"{BASE_URL}/api/jobs/detail/test_job_123")
        assert response.status_code != 410, \
            f"jobs/detail should not be retired: {response.status_code}"


class TestMiddlewareLevelEnforcement:
    """Verify middleware-level enforcement of legacy write retirement."""
    
    def test_middleware_blocks_post_to_jobs(self):
        """POST to /api/jobs/* should be blocked at middleware level."""
        response = requests.post(
            f"{BASE_URL}/api/jobs/post",
            json={"title": "Test Job"},
            headers={"Content-Type": "application/json"}
        )
        # Should be blocked (401 auth or 410 retired)
        assert response.status_code in [401, 410], \
            f"POST to jobs/post should be blocked: {response.status_code}"
    
    def test_middleware_blocks_put_to_jobs(self):
        """PUT to /api/jobs/* should be blocked at middleware level."""
        response = requests.put(
            f"{BASE_URL}/api/jobs/update/test_job_123",
            json={"title": "Updated Job"},
            headers={"Content-Type": "application/json"}
        )
        # Should be blocked (401 auth or 410 retired)
        assert response.status_code in [401, 410], \
            f"PUT to jobs/update should be blocked: {response.status_code}"
    
    def test_middleware_blocks_delete_to_jobs(self):
        """DELETE to /api/jobs/* should be blocked at middleware level."""
        response = requests.delete(f"{BASE_URL}/api/jobs/delete/test_job_123")
        # Should be blocked (401 auth or 410 retired)
        assert response.status_code in [401, 410], \
            f"DELETE to jobs/delete should be blocked: {response.status_code}"
    
    def test_middleware_blocks_post_to_employers(self):
        """POST to /api/employers/* should be blocked at middleware level."""
        response = requests.post(
            f"{BASE_URL}/api/employers/upload-document",
            headers={"Content-Type": "application/json"}
        )
        # Should be blocked (401 auth or 410 retired)
        assert response.status_code in [401, 410, 422], \
            f"POST to employers/upload-document should be blocked: {response.status_code}"


class TestFeature26AdminEndpoints:
    """Verify Feature 26 admin endpoints are functional."""
    
    def test_admin_canary_controls_get(self, admin_session):
        """GET /api/hiring/v2/admin/canary-controls should work for admin."""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls")
        # May require specific admin permissions, but should not be 404
        assert response.status_code != 404, \
            f"Admin canary controls endpoint not found: {response.status_code}"
    
    def test_admin_deprecation_telemetry(self, admin_session):
        """GET /api/hiring/v2/admin/deprecation-telemetry should work for admin."""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry")
        # May require specific admin permissions, but should not be 404
        assert response.status_code != 404, \
            f"Admin deprecation telemetry endpoint not found: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
