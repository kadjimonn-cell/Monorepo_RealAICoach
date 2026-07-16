"""Feature 26 Final Legacy v1 Hard Retirement Tests

Tests for final hard retirement of legacy v1 write routes under /api/jobs and /api/employers.
All legacy write operations should return 410 Gone with locked metadata.

Feature: 26
Feature ID: jobs-portal
Locked Protocol: feature_number=26, feature_id=jobs-portal
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"
EMPLOYER_EMAIL = "e2e.employer.feature26@realaicoach.app"
EMPLOYER_PASSWORD = "E2EEmployer#Feature26!2026"


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with CSRF header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
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
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_EMAIL,
        "password": FREE_PASSWORD
    })
    assert resp.status_code == 200, f"Free user login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def employer_session():
    """Login as employer and return session with CSRF header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": EMPLOYER_EMAIL,
        "password": EMPLOYER_PASSWORD
    })
    assert resp.status_code == 200, f"Employer login failed: {resp.text}"
    return session


# ============================================================================
# SECTION 1: Legacy /api/jobs Write Routes Return 410
# ============================================================================

class TestLegacyJobsWriteRoutes410:
    """Test that all legacy /api/jobs write routes return 410 Gone"""

    def test_jobs_apply_returns_410(self, free_session):
        """POST /api/jobs/apply should return 410 with locked metadata"""
        resp = free_session.post(f"{BASE_URL}/api/jobs/apply", json={
            "job_id": "test_job_410_check",
            "cover_letter": "Test application for 410 verification"
        })
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        # Verify locked metadata
        assert detail.get("feature_number") == 26, "feature_number should be 26"
        assert detail.get("feature_id") == "jobs-portal", "feature_id should be jobs-portal"
        assert detail.get("route_family") == "jobs", "route_family should be jobs"
        assert detail.get("retirement_mode") == "hard_retired", "retirement_mode should be hard_retired"
        assert "replacement_hint" in detail, "Should include replacement_hint"
        print("PASS: /api/jobs/apply returns 410 with correct metadata")

    def test_jobs_save_returns_410(self, free_session):
        """POST /api/jobs/save/{job_id} should return 410 with locked metadata"""
        resp = free_session.post(f"{BASE_URL}/api/jobs/save/test_job_410_save")
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "jobs"
        assert detail.get("retirement_mode") == "hard_retired"
        assert detail.get("feature_number") == 26
        print("PASS: /api/jobs/save returns 410 with correct metadata")

    def test_jobs_profile_update_returns_410(self, free_session):
        """POST /api/jobs/profile/update should return 410 with locked metadata"""
        resp = free_session.post(f"{BASE_URL}/api/jobs/profile/update", json={
            "skills": ["python", "testing"],
            "experience_years": 5
        })
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "jobs"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/jobs/profile/update returns 410")

    def test_jobs_resume_upload_returns_410(self, free_session):
        """POST /api/jobs/resume/upload should return 410 with locked metadata"""
        # Create a minimal file-like payload
        files = {'file': ('test.txt', b'test content', 'text/plain')}
        # Remove Content-Type header for multipart
        headers = {"X-Requested-With": "XMLHttpRequest"}
        resp = free_session.post(
            f"{BASE_URL}/api/jobs/resume/upload",
            files=files,
            headers=headers
        )
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "jobs"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/jobs/resume/upload returns 410")


# ============================================================================
# SECTION 2: Legacy /api/employers Write Routes Return 410
# ============================================================================

class TestLegacyEmployersWriteRoutes410:
    """Test that all legacy /api/employers write routes return 410 Gone"""

    def test_employers_apply_returns_410(self, free_session):
        """POST /api/employers/apply should return 410 with locked metadata"""
        resp = free_session.post(f"{BASE_URL}/api/employers/apply", json={
            "business_name": "Test Business 410",
            "registration_number": "TEST410",
            "country": "US",
            "business_email": "test410@example.com",
            "industry": "Technology",
            "contact_person_name": "Test Person",
            "contact_person_phone": "+1234567890"
        })
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("feature_number") == 26, "feature_number should be 26"
        assert detail.get("feature_id") == "jobs-portal", "feature_id should be jobs-portal"
        assert detail.get("route_family") == "employers", "route_family should be employers"
        assert detail.get("retirement_mode") == "hard_retired", "retirement_mode should be hard_retired"
        assert "replacement_hint" in detail, "Should include replacement_hint"
        print("PASS: /api/employers/apply returns 410 with correct metadata")

    def test_employers_upload_document_returns_410(self, free_session):
        """POST /api/employers/upload-document should return 410 with locked metadata"""
        files = {'file': ('test.pdf', b'%PDF-1.4 test', 'application/pdf')}
        data = {'document_type': 'business_registration'}
        headers = {"X-Requested-With": "XMLHttpRequest"}
        resp = free_session.post(
            f"{BASE_URL}/api/employers/upload-document",
            files=files,
            data=data,
            headers=headers
        )
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        response_data = resp.json()
        detail = response_data.get("detail", {})
        
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/employers/upload-document returns 410")

    def test_employers_resubmit_info_returns_410(self, free_session):
        """POST /api/employers/resubmit-info should return 410 with locked metadata"""
        resp = free_session.post(f"{BASE_URL}/api/employers/resubmit-info", json={
            "business_name": "Updated Business",
            "registration_number": "UPDATED410",
            "country": "US",
            "business_email": "updated410@example.com",
            "industry": "Technology",
            "contact_person_name": "Updated Person",
            "contact_person_phone": "+1234567890"
        })
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/employers/resubmit-info returns 410")

    def test_employers_reverify_returns_410(self, free_session):
        """POST /api/employers/reverify should return 410 with locked metadata"""
        resp = free_session.post(f"{BASE_URL}/api/employers/reverify")
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/employers/reverify returns 410")

    def test_employers_message_post_returns_410(self, free_session):
        """POST /api/employers/messages/{employer_id} should return 410 with locked metadata"""
        resp = free_session.post(f"{BASE_URL}/api/employers/messages/emp_test_410", json={
            "message": "Test message for 410 verification"
        })
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/employers/messages POST returns 410")


# ============================================================================
# SECTION 3: Admin Legacy Employer Routes Also Return 410
# ============================================================================

class TestAdminLegacyEmployerRoutes410:
    """Test that admin legacy employer write routes also return 410"""

    def test_admin_review_returns_410(self, admin_session):
        """POST /api/employers/admin/review/{employer_id} should return 410"""
        resp = admin_session.post(f"{BASE_URL}/api/employers/admin/review/emp_test_admin_410", json={
            "action": "approve",
            "reason": "Test approval for 410 verification",
            "checklist_doc_completeness": True,
            "checklist_identity_match": True,
            "checklist_fraud_risk_reviewed": True
        })
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/employers/admin/review returns 410")

    def test_admin_access_control_returns_410(self, admin_session):
        """POST /api/employers/admin/access-control/{employer_id} should return 410"""
        resp = admin_session.post(f"{BASE_URL}/api/employers/admin/access-control/emp_test_admin_410", json={
            "action": "suspend",
            "reason": "Test suspension for 410 verification"
        })
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/employers/admin/access-control returns 410")

    def test_admin_risk_assess_returns_410(self, admin_session):
        """POST /api/employers/admin/risk-assess/{employer_id} should return 410"""
        resp = admin_session.post(f"{BASE_URL}/api/employers/admin/risk-assess/emp_test_admin_410")
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/employers/admin/risk-assess returns 410")

    def test_admin_add_note_returns_410(self, admin_session):
        """POST /api/employers/admin/add-note/{employer_id} should return 410"""
        resp = admin_session.post(f"{BASE_URL}/api/employers/admin/add-note/emp_test_admin_410", json={
            "note": "Test note for 410 verification"
        })
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("route_family") == "employers"
        assert detail.get("retirement_mode") == "hard_retired"
        print("PASS: /api/employers/admin/add-note returns 410")


# ============================================================================
# SECTION 4: 410 Payload Structure Verification
# ============================================================================

class Test410PayloadStructure:
    """Test that 410 responses have correct payload structure"""

    def test_410_has_required_fields(self, free_session):
        """410 response should have all required fields"""
        resp = free_session.post(f"{BASE_URL}/api/jobs/apply", json={
            "job_id": "test_payload_structure",
            "cover_letter": "Test"
        })
        assert resp.status_code == 410
        
        data = resp.json()
        detail = data.get("detail", {})
        
        required_fields = [
            "message",
            "feature_number",
            "feature_id",
            "route_family",
            "retirement_mode",
            "retirement_phase",
            "replacement_hint"
        ]
        
        for field in required_fields:
            assert field in detail, f"Missing required field: {field}"
        
        print(f"PASS: 410 response has all required fields: {required_fields}")

    def test_410_retirement_phase_is_hard_retired_cleanup(self, free_session):
        """410 response retirement_phase should be hard_retired_cleanup"""
        resp = free_session.post(f"{BASE_URL}/api/jobs/save/test_phase_check")
        assert resp.status_code == 410
        
        data = resp.json()
        detail = data.get("detail", {})
        
        assert detail.get("retirement_phase") == "hard_retired_cleanup", \
            f"Expected hard_retired_cleanup, got {detail.get('retirement_phase')}"
        print("PASS: retirement_phase is hard_retired_cleanup")

    def test_410_replacement_hint_points_to_v2(self, free_session):
        """410 response replacement_hint should point to v2 routes"""
        resp = free_session.post(f"{BASE_URL}/api/jobs/apply", json={
            "job_id": "test_hint_check",
            "cover_letter": "Test"
        })
        assert resp.status_code == 410
        
        data = resp.json()
        detail = data.get("detail", {})
        
        replacement_hint = detail.get("replacement_hint", "")
        assert "/api/hiring/v2/" in replacement_hint or "/v2/" in replacement_hint, \
            f"replacement_hint should point to v2: {replacement_hint}"
        print(f"PASS: replacement_hint points to v2: {replacement_hint}")


# ============================================================================
# SECTION 5: v2 Endpoints Remain Available
# ============================================================================

class TestV2EndpointsAvailable:
    """Test that v2 endpoints remain available and functional"""

    def test_v2_health_endpoint(self, free_session):
        """GET /api/hiring/v2/health should return 200"""
        resp = free_session.get(f"{BASE_URL}/api/hiring/v2/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("service") == "hiring-v2"
        assert data.get("feature_number") == 26
        print("PASS: /api/hiring/v2/health returns 200")

    def test_v2_dashboard_summary(self, free_session):
        """GET /api/hiring/v2/dashboard/summary should return 200"""
        resp = free_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "open_roles" in data
        print("PASS: /api/hiring/v2/dashboard/summary returns 200")

    def test_v2_candidate_jobs_search(self, free_session):
        """GET /api/hiring/v2/candidate/jobs/search should return 200"""
        resp = free_session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "jobs" in data
        print("PASS: /api/hiring/v2/candidate/jobs/search returns 200")

    def test_v2_candidate_apply_endpoint_exists(self, free_session):
        """POST /api/hiring/v2/candidate/apply should exist (may return 404 for non-existent job)"""
        resp = free_session.post(f"{BASE_URL}/api/hiring/v2/candidate/apply", json={
            "job_id": "nonexistent_job_v2_test",
            "cover_letter": "Test via v2"
        })
        # Should NOT be 405 (method not allowed) or 410 (retired)
        assert resp.status_code not in [405, 410], \
            f"v2 endpoint should exist, got {resp.status_code}: {resp.text}"
        print(f"PASS: /api/hiring/v2/candidate/apply endpoint exists (status: {resp.status_code})")

    def test_v2_candidate_save_endpoint_exists(self, free_session):
        """POST /api/hiring/v2/candidate/save/{job_id} should exist"""
        resp = free_session.post(f"{BASE_URL}/api/hiring/v2/candidate/save/nonexistent_job_v2")
        # Should NOT be 405 or 410
        assert resp.status_code not in [405, 410], \
            f"v2 endpoint should exist, got {resp.status_code}: {resp.text}"
        print(f"PASS: /api/hiring/v2/candidate/save endpoint exists (status: {resp.status_code})")


# ============================================================================
# SECTION 6: Feature 26 Admin Endpoints (Telemetry/Readiness) Still Work
# ============================================================================

class TestFeature26AdminEndpoints:
    """Test that Feature 26 admin endpoints for telemetry/readiness still work"""

    def test_admin_canary_controls_get(self, admin_session):
        """GET /api/hiring/v2/admin/canary-controls should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "controls" in data
        assert "generated_at" in data
        print("PASS: /api/hiring/v2/admin/canary-controls GET returns 200")

    def test_admin_deprecation_telemetry(self, admin_session):
        """GET /api/hiring/v2/admin/deprecation-telemetry should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "total_events" in data
        assert "migration_progress_pct" in data
        print("PASS: /api/hiring/v2/admin/deprecation-telemetry returns 200")

    def test_admin_legacy_retirement_readiness(self, admin_session):
        """GET /api/hiring/v2/admin/legacy-retirement-readiness should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-readiness")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("feature_number") == 26
        assert data.get("feature_id") == "jobs-portal"
        assert "family_readiness" in data
        print("PASS: /api/hiring/v2/admin/legacy-retirement-readiness returns 200")

    def test_admin_legacy_removal_readiness(self, admin_session):
        """GET /api/hiring/v2/admin/legacy-removal-readiness should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/legacy-removal-readiness")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert data.get("feature_number") == 26
        assert data.get("feature_id") == "jobs-portal"
        print("PASS: /api/hiring/v2/admin/legacy-removal-readiness returns 200")

    def test_admin_premium_conversion_cohorts(self, admin_session):
        """GET /api/hiring/v2/admin/premium-conversion-cohorts should return 200"""
        resp = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/premium-conversion-cohorts")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "activation_users" in data
        print("PASS: /api/hiring/v2/admin/premium-conversion-cohorts returns 200")


# ============================================================================
# SECTION 7: Middleware-Level 410 Enforcement
# ============================================================================

class TestMiddlewareLevelEnforcement:
    """Test that middleware enforces 410 for legacy write methods"""

    def test_middleware_blocks_post_to_jobs(self, free_session):
        """Middleware should block POST to /api/jobs/* write paths"""
        resp = free_session.post(f"{BASE_URL}/api/jobs/apply", json={"job_id": "test"})
        assert resp.status_code == 410
        print("PASS: Middleware blocks POST to /api/jobs/apply")

    def test_middleware_blocks_put_to_jobs(self, free_session):
        """Middleware should block PUT to /api/jobs/* write paths"""
        resp = free_session.put(f"{BASE_URL}/api/jobs/update/test_job_id", json={"title": "Updated"})
        assert resp.status_code == 410
        print("PASS: Middleware blocks PUT to /api/jobs/update")

    def test_middleware_blocks_delete_to_jobs(self, free_session):
        """Middleware should block DELETE to /api/jobs/* write paths"""
        resp = free_session.delete(f"{BASE_URL}/api/jobs/delete/test_job_id")
        assert resp.status_code == 410
        print("PASS: Middleware blocks DELETE to /api/jobs/delete")

    def test_middleware_blocks_patch_to_employers(self, free_session):
        """Middleware should block PATCH to /api/employers/* write paths"""
        resp = free_session.patch(f"{BASE_URL}/api/employers/update/emp_test", json={"status": "updated"})
        assert resp.status_code == 410
        print("PASS: Middleware blocks PATCH to /api/employers/update")


# ============================================================================
# SECTION 8: Legacy Read Endpoints Are Fully Retired
# ============================================================================

class TestLegacyReadEndpointsRetired:
    """Feature 26 P2 final: legacy reads now return 410 with v2 replacement hints."""

    def test_jobs_search_retired(self, free_session):
        resp = free_session.get(f"{BASE_URL}/api/jobs/search")
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", {})
        assert detail.get("feature_number") == 26
        assert detail.get("route_family") == "jobs"
        assert detail.get("retirement_phase") == "hard_retired_read_cleanup"
        assert "hiring/v2" in str(detail.get("replacement_hint") or "")
        print("PASS: /api/jobs/search retired with v2 replacement hint")

    def test_jobs_detail_retired(self, free_session):
        resp = free_session.get(f"{BASE_URL}/api/jobs/detail/test_job_read")
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", {})
        assert "hiring/v2" in str(detail.get("replacement_hint") or "")
        print("PASS: /api/jobs/detail/{job_id} retired with v2 replacement hint")

    def test_jobs_portal_summary_retired(self, free_session):
        resp = free_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", {})
        assert "/api/hiring/v2/dashboard/summary" == detail.get("replacement_hint")
        print("PASS: /api/jobs/portal-summary retired with exact v2 replacement hint")

    def test_employers_my_application_retired(self, free_session):
        resp = free_session.get(f"{BASE_URL}/api/employers/my-application")
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", {})
        assert detail.get("route_family") == "employers"
        assert "hiring/v2" in str(detail.get("replacement_hint") or "")
        print("PASS: /api/employers/my-application retired with v2 replacement hint")

    def test_employers_my_permissions_retired(self, free_session):
        resp = free_session.get(f"{BASE_URL}/api/employers/my-permissions")
        assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", {})
        assert "hiring/v2" in str(detail.get("replacement_hint") or "")
        print("PASS: /api/employers/my-permissions retired with v2 replacement hint")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
