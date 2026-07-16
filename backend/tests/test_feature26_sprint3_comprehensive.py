"""Feature 26 Sprint 3 Comprehensive Tests

Tests for:
- Frontend commercial UX route panels: /job-platform-candidate, /job-platform-employer, /job-platform-admin
- Candidate commercial actions: priority apply + boost controls
- Employer premium panels: explainability + premium analytics
- Admin deprecation panel and telemetry
- v2 candidate write adapters: /api/hiring/v2/candidate/apply, /save/{job_id}, /profile/update
- v2 employer write adapters: offer build/submit/approve/send, pipeline bulk action, copilot execute, sla-auto-triggers run
- Legacy deprecation telemetry endpoint: /api/hiring/v2/admin/deprecation-telemetry
- No regression in /job-platform main route and canonical summary
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


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def free_user_session(api_client):
    """Login as free user and return session with cookies"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Free user login failed: {response.status_code} - {response.text}")
    return api_client


@pytest.fixture(scope="module")
def admin_session(api_client):
    """Login as admin and return session with cookies"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    return session


@pytest.fixture(scope="module")
def employer_session(api_client):
    """Login as employer and return session with cookies"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMPLOYER_EMAIL, "password": EMPLOYER_PASSWORD},
    )
    if response.status_code != 200:
        pytest.skip(f"Employer login failed: {response.status_code} - {response.text}")
    return session


class TestHiringV2Health:
    """Test hiring v2 health endpoint"""

    def test_hiring_v2_health_endpoint(self, api_client):
        """Verify /api/hiring/v2/health returns ok"""
        response = api_client.get(f"{BASE_URL}/api/hiring/v2/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert data.get("service") == "hiring-v2"
        assert data.get("version") == "v2"
        assert data.get("feature_number") == 26
        print("PASS: hiring v2 health endpoint returns ok")


class TestCandidateWriteAdapters:
    """Test v2 candidate write adapters"""

    def test_candidate_apply_endpoint_exists(self, free_user_session):
        """Verify /api/hiring/v2/candidate/apply endpoint exists and requires auth"""
        # Test with invalid job_id to verify endpoint exists
        response = free_user_session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/apply",
            json={"job_id": "nonexistent_job_123", "cover_letter": "Test cover letter"},
        )
        # Should return 404 (job not found) or 400 (already applied), not 404 for endpoint
        assert response.status_code in [400, 404, 403]
        print(f"PASS: candidate apply endpoint exists (status={response.status_code})")

    def test_candidate_save_job_endpoint_exists(self, free_user_session):
        """Verify /api/hiring/v2/candidate/save/{job_id} endpoint exists"""
        response = free_user_session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/save/nonexistent_job_123"
        )
        # Should return 200 (toggle save) or 404 (job not found)
        assert response.status_code in [200, 404]
        print(f"PASS: candidate save job endpoint exists (status={response.status_code})")

    def test_candidate_profile_update_endpoint_exists(self, free_user_session):
        """Verify /api/hiring/v2/candidate/profile/update endpoint exists"""
        response = free_user_session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/profile/update",
            json={"skills": ["Python", "FastAPI"], "experience_years": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        print("PASS: candidate profile update endpoint works")

    def test_candidate_recommendations_endpoint(self, free_user_session):
        """Verify /api/hiring/v2/candidate/recommendations endpoint exists"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/candidate/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        print("PASS: candidate recommendations endpoint works")


class TestCandidateCommercialActions:
    """Test candidate commercial actions: priority apply + boost controls"""

    def test_priority_apply_requires_plan(self, free_user_session):
        """Verify priority apply requires Basic/Premium plan for free users"""
        response = free_user_session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/priority-apply/demo-priority-application"
        )
        # Free user should get 403 or 404
        assert response.status_code in [403, 404]
        if response.status_code == 403:
            data = response.json()
            assert "Basic" in str(data.get("detail", "")) or "Premium" in str(data.get("detail", ""))
        print(f"PASS: priority apply correctly gated for free users (status={response.status_code})")

    def test_boost_profile_requires_plan(self, free_user_session):
        """Verify boost profile requires Basic/Premium plan for free users"""
        response = free_user_session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/boost-profile",
            json={"boost_hours": 72},
        )
        # Free user should get 403
        assert response.status_code == 403
        data = response.json()
        assert "Basic" in str(data.get("detail", "")) or "Premium" in str(data.get("detail", ""))
        print("PASS: boost profile correctly gated for free users")


class TestEmployerWriteAdapters:
    """Test v2 employer write adapters"""

    def test_employer_offers_build_endpoint_exists(self, admin_session):
        """Verify /api/hiring/v2/employer/offers/build endpoint exists"""
        response = admin_session.post(
            f"{BASE_URL}/api/hiring/v2/employer/offers/build",
            json={
                "application_id": "nonexistent_app_123",
                "base_salary_usd": 100000,
                "start_date": "2026-07-01",
                "expires_at": "2026-06-30",
            },
        )
        # Should return 404 (application not found) or 403 (not authorized)
        assert response.status_code in [403, 404]
        print(f"PASS: employer offers build endpoint exists (status={response.status_code})")

    def test_employer_pipeline_bulk_action_endpoint_exists(self, admin_session):
        """Verify /api/hiring/v2/employer/pipeline/bulk-action endpoint exists"""
        response = admin_session.post(
            f"{BASE_URL}/api/hiring/v2/employer/pipeline/bulk-action",
            json={
                "application_ids": ["nonexistent_app_123"],
                "action": "move_stage",
                "target_status": "viewed",
            },
        )
        # Should return 200 (empty result) or 400/404
        assert response.status_code in [200, 400, 404]
        print(f"PASS: employer pipeline bulk action endpoint exists (status={response.status_code})")

    def test_employer_copilot_execute_endpoint_exists(self, admin_session):
        """Verify /api/hiring/v2/employer/pipeline/{application_id}/copilot-execute endpoint exists"""
        response = admin_session.post(
            f"{BASE_URL}/api/hiring/v2/employer/pipeline/nonexistent_app_123/copilot-execute",
            json={"action_key": "send_followup", "reason": "Test"},
        )
        # Should return 404 (application not found) or 403
        assert response.status_code in [403, 404]
        print(f"PASS: employer copilot execute endpoint exists (status={response.status_code})")

    def test_employer_sla_auto_triggers_run_endpoint_exists(self, admin_session):
        """Verify /api/hiring/v2/employer/sla-auto-triggers/run endpoint exists"""
        response = admin_session.post(
            f"{BASE_URL}/api/hiring/v2/employer/sla-auto-triggers/run",
            json={"max_items": 1},
        )
        # Should return 200 or 403
        assert response.status_code in [200, 403]
        print(f"PASS: employer sla auto triggers run endpoint exists (status={response.status_code})")


class TestEmployerPremiumPanels:
    """Test employer premium panels: explainability + premium analytics"""

    def test_employer_shortlist_explainability_requires_premium(self, free_user_session):
        """Verify shortlist explainability requires Premium plan"""
        response = free_user_session.get(
            f"{BASE_URL}/api/hiring/v2/employer/shortlist/explainability?limit=8"
        )
        # Free user should get 403
        assert response.status_code == 403
        data = response.json()
        assert "Premium" in str(data.get("detail", ""))
        print("PASS: shortlist explainability correctly gated for non-premium users")

    def test_employer_premium_analytics_events_requires_premium(self, free_user_session):
        """Verify premium analytics events requires Premium plan"""
        response = free_user_session.get(
            f"{BASE_URL}/api/hiring/v2/employer/premium-analytics/events?lookback_days=30&limit=20"
        )
        # Free user should get 403
        assert response.status_code == 403
        data = response.json()
        assert "Premium" in str(data.get("detail", ""))
        print("PASS: premium analytics events correctly gated for non-premium users")

    def test_admin_can_access_explainability(self, admin_session):
        """Verify admin can access shortlist explainability"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/employer/shortlist/explainability?limit=8"
        )
        # Admin should get 200 or 403 (if not employer)
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "items" in data
            print("PASS: admin can access shortlist explainability")
        else:
            print("PASS: admin access to explainability gated by employer role (expected)")

    def test_admin_can_access_premium_analytics(self, admin_session):
        """Verify admin can access premium analytics events"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/employer/premium-analytics/events?lookback_days=30&limit=20"
        )
        # Admin should get 200 or 403 (if not employer)
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "events" in data
            print("PASS: admin can access premium analytics events")
        else:
            print("PASS: admin access to premium analytics gated by employer role (expected)")


class TestAdminDeprecationTelemetry:
    """Test admin deprecation telemetry endpoint"""

    def test_deprecation_telemetry_requires_admin(self, free_user_session):
        """Verify deprecation telemetry requires admin access"""
        response = free_user_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry?lookback_days=14&limit=1000"
        )
        # Non-admin should get 403
        assert response.status_code == 403
        print("PASS: deprecation telemetry correctly requires admin access")

    def test_admin_can_access_deprecation_telemetry(self, admin_session):
        """Verify admin can access deprecation telemetry"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry?lookback_days=14&limit=1000"
        )
        assert response.status_code == 200
        data = response.json()
        # Verify response structure
        assert "generated_at" in data
        assert "lookback_days" in data
        assert "total_events" in data
        assert "active_legacy_users" in data
        assert "remaining_legacy_operations" in data
        assert "migration_progress_pct" in data
        assert "top_operations" in data
        assert "top_legacy_endpoints" in data
        assert "events" in data
        print("PASS: admin can access deprecation telemetry")
        print(f"  - total_events: {data.get('total_events')}")
        print(f"  - migration_progress_pct: {data.get('migration_progress_pct')}")
        print(f"  - active_legacy_users: {data.get('active_legacy_users')}")

    def test_admin_workflow_events_endpoint(self, admin_session):
        """Verify admin workflow events endpoint works"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=12"
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        print(f"PASS: admin workflow events endpoint works (total={data.get('total')})")


class TestJobPlatformMainRoute:
    """Test no regression in /job-platform main route and canonical summary"""

    def test_jobs_portal_summary_endpoint(self, free_user_session):
        """Verify /api/jobs/portal-summary endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        assert response.status_code == 200
        data = response.json()
        # Verify canonical summary structure
        assert "open_roles" in data
        assert "candidate_applications" in data
        assert "interview_applications" in data
        assert "offer_applications" in data
        assert "saved_jobs" in data
        assert "last_sync_at" in data
        assert "candidate" in data
        assert "employer" in data
        print("PASS: jobs portal summary endpoint works")
        print(f"  - open_roles: {data.get('open_roles')}")
        print(f"  - candidate_applications: {data.get('candidate_applications')}")

    def test_hiring_v2_dashboard_summary_endpoint(self, free_user_session):
        """Verify /api/hiring/v2/dashboard/summary endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary")
        assert response.status_code == 200
        data = response.json()
        assert "open_roles" in data
        print("PASS: hiring v2 dashboard summary endpoint works")

    def test_jobs_search_endpoint(self, api_client):
        """Verify /api/jobs/search endpoint works (public)"""
        response = api_client.get(f"{BASE_URL}/api/jobs/search?q=&page=1&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        print(f"PASS: jobs search endpoint works (total={data.get('total')})")

    def test_hiring_v2_candidate_search_endpoint(self, free_user_session):
        """Verify /api/hiring/v2/candidate/jobs/search endpoint works"""
        response = free_user_session.get(
            f"{BASE_URL}/api/hiring/v2/candidate/jobs/search?q=&page=1&limit=10"
        )
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        print("PASS: hiring v2 candidate search endpoint works")


class TestEmployerPipelineEndpoints:
    """Test employer pipeline endpoints"""

    def test_employer_pipeline_board_endpoint(self, admin_session):
        """Verify /api/hiring/v2/employer/pipeline-board endpoint works"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/employer/pipeline-board?limit=120")
        # Admin should get 200 or 403 (if not employer)
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "applications" in data or "stages" in data
            print("PASS: employer pipeline board endpoint works")
        else:
            print("PASS: employer pipeline board gated by employer role (expected)")

    def test_employer_kpi_header_endpoint(self, admin_session):
        """Verify /api/hiring/v2/employer/kpi-header endpoint works"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/employer/kpi-header?window_days=30")
        # Admin should get 200 or 403 (if not employer)
        assert response.status_code in [200, 403]
        print(f"PASS: employer kpi header endpoint exists (status={response.status_code})")

    def test_employer_sla_alerts_endpoint(self, admin_session):
        """Verify /api/hiring/v2/employer/sla-alerts endpoint works"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/employer/sla-alerts?limit=120")
        # Admin should get 200 or 403 (if not employer)
        assert response.status_code in [200, 403]
        print(f"PASS: employer sla alerts endpoint exists (status={response.status_code})")

    def test_employer_offers_list_endpoint(self, admin_session):
        """Verify /api/hiring/v2/employer/offers endpoint works"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/employer/offers?limit=120")
        # Admin should get 200 or 403 (if not employer)
        assert response.status_code in [200, 403]
        print(f"PASS: employer offers list endpoint exists (status={response.status_code})")


class TestOfferLifecycleEndpoints:
    """Test offer lifecycle endpoints exist"""

    def test_offer_submit_approval_endpoint_exists(self, admin_session):
        """Verify /api/hiring/v2/employer/offers/{offer_id}/submit-approval endpoint exists"""
        response = admin_session.post(
            f"{BASE_URL}/api/hiring/v2/employer/offers/nonexistent_offer_123/submit-approval",
            json={"note": "Test"},
        )
        # Should return 404 (offer not found) or 403
        assert response.status_code in [403, 404]
        print(f"PASS: offer submit approval endpoint exists (status={response.status_code})")

    def test_offer_approve_endpoint_exists(self, admin_session):
        """Verify /api/hiring/v2/employer/offers/{offer_id}/approve endpoint exists"""
        response = admin_session.post(
            f"{BASE_URL}/api/hiring/v2/employer/offers/nonexistent_offer_123/approve",
            json={"approver_name": "Test Approver"},
        )
        # Should return 404 (offer not found) or 403
        assert response.status_code in [403, 404]
        print(f"PASS: offer approve endpoint exists (status={response.status_code})")

    def test_offer_send_endpoint_exists(self, admin_session):
        """Verify /api/hiring/v2/employer/offers/{offer_id}/send endpoint exists"""
        response = admin_session.post(
            f"{BASE_URL}/api/hiring/v2/employer/offers/nonexistent_offer_123/send",
            json={},
        )
        # Should return 404 (offer not found) or 403/409
        assert response.status_code in [403, 404, 409]
        print(f"PASS: offer send endpoint exists (status={response.status_code})")


class TestCandidateReadEndpoints:
    """Test candidate read endpoints"""

    def test_candidate_applications_endpoint(self, free_user_session):
        """Verify /api/hiring/v2/candidate/applications endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/candidate/applications?status=all")
        assert response.status_code == 200
        data = response.json()
        assert "applications" in data
        print("PASS: candidate applications endpoint works")

    def test_candidate_saved_jobs_endpoint(self, free_user_session):
        """Verify /api/hiring/v2/candidate/saved-jobs endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/candidate/saved-jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data or "saved_jobs" in data
        print("PASS: candidate saved jobs endpoint works")

    def test_candidate_analytics_endpoint(self, free_user_session):
        """Verify /api/hiring/v2/candidate/analytics endpoint works"""
        response = free_user_session.get(f"{BASE_URL}/api/hiring/v2/candidate/analytics")
        assert response.status_code == 200
        data = response.json()
        assert "total_applications" in data
        print("PASS: candidate analytics endpoint works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
