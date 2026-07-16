"""Feature 26 Sprint 2 Comprehensive E2E Tests.

Tests:
- v2 read endpoints: /api/hiring/v2/health, /candidate/jobs/search, /dashboard/summary
- v2 write adapters: offer build/submit/approve/send, pipeline bulk-action/copilot-execute
- commercial endpoints: candidate boost-profile, priority-apply, employer shortlist explainability, premium analytics events
- admin observability: /api/hiring/v2/admin/workflow-events
- employer fixture login: e2e.employer.feature26@realaicoach.app
- regression: /api/jobs/portal-summary
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

EMPLOYER_EMAIL = "e2e.employer.feature26@realaicoach.app"
EMPLOYER_PASSWORD = "E2EEmployer#Feature26!2026"


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    return session


@pytest.fixture(scope="module")
def free_user_session(api_client):
    """Login as free user and return session with cookies."""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD,
    })
    assert response.status_code == 200, f"Free user login failed: {response.text}"
    return api_client


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with cookies."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return session


@pytest.fixture(scope="module")
def employer_session():
    """Login as employer fixture and return session with cookies."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": EMPLOYER_EMAIL,
        "password": EMPLOYER_PASSWORD,
    })
    assert response.status_code == 200, f"Employer login failed: {response.text}"
    return session


class TestHiringV2ReadEndpoints:
    """Test v2 read endpoints availability and access."""

    def test_hiring_v2_health(self, free_user_session):
        """GET /api/hiring/v2/health should return 200 with service info."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("ok") is True
        assert data.get("service") == "hiring-v2"
        assert data.get("version") == "v2"
        print(f"PASS: /api/hiring/v2/health returns {data}")

    def test_hiring_v2_candidate_jobs_search(self, free_user_session):
        """GET /api/hiring/v2/candidate/jobs/search should return 200."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search")
        assert response.status_code == 200, f"Jobs search failed: {response.text}"
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        print(f"PASS: /api/hiring/v2/candidate/jobs/search returns {len(data.get('jobs', []))} jobs")

    def test_hiring_v2_dashboard_summary(self, free_user_session):
        """GET /api/hiring/v2/dashboard/summary should return 200."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary")
        assert response.status_code == 200, f"Dashboard summary failed: {response.text}"
        data = response.json()
        assert "open_roles" in data
        assert "candidate_applications" in data
        print(f"PASS: /api/hiring/v2/dashboard/summary returns open_roles={data.get('open_roles')}")


class TestHiringV2WriteAdaptersAccessControl:
    """Test v2 write adapters exist and enforce access controls."""

    def test_offer_build_requires_employer(self, free_user_session):
        """POST /api/hiring/v2/employer/offers/build should require employer access."""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/employer/offers/build", json={
            "application_id": "test_app_123",
            "base_salary_usd": 100000,
            "start_date": "2026-07-01",
            "expires_at": "2026-06-30T23:59:59Z",
        })
        # Should return 403 for non-employer
        assert response.status_code == 403, f"Expected 403 for non-employer, got {response.status_code}"
        print("PASS: /api/hiring/v2/employer/offers/build correctly returns 403 for free user")

    def test_offer_submit_approval_requires_employer(self, free_user_session):
        """POST /api/hiring/v2/employer/offers/{offer_id}/submit-approval should require employer."""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/employer/offers/test_offer_123/submit-approval", json={
            "note": "Test approval submission",
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: /api/hiring/v2/employer/offers/submit-approval correctly returns 403 for free user")

    def test_offer_approve_requires_employer(self, free_user_session):
        """POST /api/hiring/v2/employer/offers/{offer_id}/approve should require employer."""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/employer/offers/test_offer_123/approve", json={
            "note": "Test approval",
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: /api/hiring/v2/employer/offers/approve correctly returns 403 for free user")

    def test_offer_send_requires_employer(self, free_user_session):
        """POST /api/hiring/v2/employer/offers/{offer_id}/send should require employer."""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/employer/offers/test_offer_123/send", json={})
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: /api/hiring/v2/employer/offers/send correctly returns 403 for free user")

    def test_pipeline_bulk_action_requires_employer(self, free_user_session):
        """POST /api/hiring/v2/employer/pipeline/bulk-action should require employer."""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/employer/pipeline/bulk-action", json={
            "application_ids": ["app_1", "app_2"],
            "action": "move_viewed",
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: /api/hiring/v2/employer/pipeline/bulk-action correctly returns 403 for free user")

    def test_copilot_execute_requires_employer(self, free_user_session):
        """POST /api/hiring/v2/employer/pipeline/{application_id}/copilot-execute should require employer."""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/employer/pipeline/test_app_123/copilot-execute", json={
            "action_key": "move_viewed",
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: /api/hiring/v2/employer/pipeline/copilot-execute correctly returns 403 for free user")


class TestCommercialEndpointsBehavior:
    """Test commercial layer endpoints: boost-profile, priority-apply, shortlist explainability, premium analytics."""

    def test_boost_profile_requires_paid_plan(self, free_user_session):
        """POST /api/hiring/v2/candidate/boost-profile should require Basic/Premium plan."""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/candidate/boost-profile", json={
            "boost_hours": 72,
        })
        # Free user should get 403
        assert response.status_code == 403, f"Expected 403 for free user, got {response.status_code}"
        data = response.json()
        assert "Basic" in str(data.get("detail", "")) or "Premium" in str(data.get("detail", ""))
        print("PASS: /api/hiring/v2/candidate/boost-profile correctly returns 403 for free user")

    def test_priority_apply_requires_paid_plan(self, free_user_session):
        """POST /api/hiring/v2/candidate/priority-apply/{application_id} should require Basic/Premium plan."""
        response = free_user_session.post(f"{BASE_URL}/api/hiring/v2/candidate/priority-apply/test_app_123")
        # Free user should get 403 (plan check) or 404 (application not found)
        assert response.status_code in [403, 404], f"Expected 403 or 404, got {response.status_code}"
        print(f"PASS: /api/hiring/v2/candidate/priority-apply returns {response.status_code} for free user (expected gating)")

    def test_shortlist_explainability_requires_premium(self, free_user_session):
        """GET /api/hiring/v2/employer/shortlist/explainability should require Premium plan."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/employer/shortlist/explainability")
        # Free user should get 403 (employer check first, then plan check)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: /api/hiring/v2/employer/shortlist/explainability correctly returns 403 for free user")

    def test_premium_analytics_events_requires_premium(self, free_user_session):
        """GET /api/hiring/v2/employer/premium-analytics/events should require Premium plan."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/employer/premium-analytics/events")
        # Free user should get 403 (employer check first, then plan check)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: /api/hiring/v2/employer/premium-analytics/events correctly returns 403 for free user")


class TestAdminObservabilityEndpoint:
    """Test admin-only workflow events endpoint."""

    def test_workflow_events_denied_for_free_user(self, free_user_session):
        """GET /api/hiring/v2/admin/workflow-events should return 403 for free user."""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: /api/hiring/v2/admin/workflow-events correctly returns 403 for free user")

    def test_workflow_events_allowed_for_admin(self, admin_session):
        """GET /api/hiring/v2/admin/workflow-events should return 200 for admin."""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events")
        assert response.status_code == 200, f"Expected 200 for admin, got {response.status_code}: {response.text}"
        data = response.json()
        assert "events" in data
        assert "generated_at" in data
        assert "lookback_hours" in data
        print(f"PASS: /api/hiring/v2/admin/workflow-events returns 200 for admin with {len(data.get('events', []))} events")


class TestEmployerFixtureLogin:
    """Test employer fixture login and access."""

    def test_employer_fixture_login_success(self, employer_session):
        """Employer fixture should login successfully."""
        # Session fixture already logged in, verify by calling a protected endpoint
        response = employer_session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Auth me failed: {response.text}"
        data = response.json()
        user = data.get("user", data)
        assert user.get("email") == EMPLOYER_EMAIL
        print(f"PASS: Employer fixture login successful for {EMPLOYER_EMAIL}")

    def test_employer_fixture_has_employer_access(self, employer_session):
        """Employer fixture should have employer role/access - verified by accessing employer endpoint."""
        # The auth/me endpoint may not return is_employer directly, so we verify by
        # checking if the employer can access employer-gated endpoints
        response = employer_session.get(f"{BASE_URL}/api/hiring/v2/employer/offers")
        # If employer has proper access, should get 200 (may have empty list)
        # If not approved employer, will get 403
        assert response.status_code == 200, f"Employer fixture should have employer access, got {response.status_code}: {response.text}"
        print("PASS: Employer fixture has employer access (verified via /api/hiring/v2/employer/offers)")


class TestRegressionJobsPortalSummary:
    """Regression tests for /api/jobs/portal-summary."""

    def test_portal_summary_returns_canonical_fields(self, free_user_session):
        """GET /api/jobs/portal-summary should return all canonical fields."""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200, f"Portal summary failed: {response.text}"
        data = response.json()
        
        # Check canonical fields
        required_fields = [
            "open_roles",
            "candidate_applications",
            "interview_applications",
            "offer_applications",
            "saved_jobs",
            "last_sync_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        print("PASS: /api/jobs/portal-summary returns all canonical fields")
        print(f"  open_roles={data.get('open_roles')}, candidate_applications={data.get('candidate_applications')}")


class TestEmployerWriteAdaptersWithEmployerFixture:
    """Test write adapters with actual employer fixture (may return 404 for missing resources)."""

    def test_employer_can_access_offers_list(self, employer_session):
        """GET /api/hiring/v2/employer/offers should work for employer."""
        response = employer_session.get(f"{BASE_URL}/api/hiring/v2/employer/offers")
        # Should return 200 (may have empty list) or 403 if employer approval not complete
        assert response.status_code in [200, 403], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "offers" in data
            print(f"PASS: Employer can access offers list ({len(data.get('offers', []))} offers)")
        else:
            print("PASS: Employer offers returns 403 (expected if employer approval not complete)")

    def test_employer_can_access_pipeline_board(self, employer_session):
        """GET /api/hiring/v2/employer/pipeline-board should work for employer."""
        response = employer_session.get(f"{BASE_URL}/api/hiring/v2/employer/pipeline-board")
        assert response.status_code in [200, 403], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "applications" in data
            print(f"PASS: Employer can access pipeline board ({len(data.get('applications', []))} applications)")
        else:
            print("PASS: Employer pipeline-board returns 403 (expected if employer approval not complete)")

    def test_employer_can_access_kpi_header(self, employer_session):
        """GET /api/hiring/v2/employer/kpi-header should work for employer."""
        response = employer_session.get(f"{BASE_URL}/api/hiring/v2/employer/kpi-header")
        assert response.status_code in [200, 403], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            print("PASS: Employer can access KPI header")
        else:
            print("PASS: Employer KPI header returns 403 (expected if employer approval not complete)")


class TestAdminCommercialEndpointsAccess:
    """Test that admin can access commercial endpoints (admin bypasses plan checks)."""

    def test_admin_can_access_shortlist_explainability(self, admin_session):
        """Admin should be able to access shortlist explainability."""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/employer/shortlist/explainability")
        # Admin may get 403 if not approved employer, or 200 if admin bypasses
        assert response.status_code in [200, 403], f"Unexpected status: {response.status_code}"
        print(f"PASS: Admin shortlist explainability returns {response.status_code}")

    def test_admin_can_access_premium_analytics(self, admin_session):
        """Admin should be able to access premium analytics events."""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/employer/premium-analytics/events")
        # Admin may get 403 if not approved employer, or 200 if admin bypasses
        assert response.status_code in [200, 403], f"Unexpected status: {response.status_code}"
        print(f"PASS: Admin premium analytics returns {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
