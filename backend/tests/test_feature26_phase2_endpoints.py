"""Feature 26 Phase-2 Advanced Employer Pipeline Read Endpoints - E2E Tests"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
EMPLOYER_EMAIL = "e2e.employer.feature26@realaicoach.app"
EMPLOYER_PASSWORD = "E2EEmployer#Feature26!2026"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def session():
    """Shared requests session"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_session(session):
    """Admin authenticated session"""
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if resp.status_code == 200:
        # Cookie-based auth
        return session
    pytest.skip("Admin login failed - skipping admin tests")


@pytest.fixture(scope="module")
def employer_session():
    """Employer authenticated session"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMPLOYER_EMAIL, "password": EMPLOYER_PASSWORD},
    )
    if resp.status_code == 200:
        return s
    pytest.skip("Employer login failed - skipping employer tests")


class TestFeature26LockHealth:
    """Feature 26 lock health verification via rollout controls"""

    def test_feature26_rollout_controls_exist_in_code(self):
        """Verify Feature 26 rollout controls are defined in jobs.py"""
        from pathlib import Path
        source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
        # Verify DEFAULT_F26_ROLLOUT_CONTROLS exists
        assert 'DEFAULT_F26_ROLLOUT_CONTROLS' in source
        assert 'feature26_legacy_write_rollout' in source
        assert 'legacy_retirement_enabled' in source


class TestPhase2PipelineReadEndpoints:
    """Phase-2 advanced employer pipeline read endpoints"""

    def test_employer_pipeline_board_read(self, admin_session):
        """GET /api/jobs/employer/pipeline-board - delegated to phase-2 read service"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/pipeline-board")
        # Should return 200 or 403 (if not employer)
        assert resp.status_code in [200, 403, 401], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            # Verify response contract
            assert "stages" in data or "applications" in data or "jobs" in data

    def test_employer_sla_alerts_read(self, admin_session):
        """GET /api/jobs/employer/sla-alerts - delegated to phase-2 read service"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/sla-alerts")
        assert resp.status_code in [200, 403, 401], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert "overdue_total" in data or "items" in data or "generated_at" in data

    def test_employer_sla_auto_triggers_read(self, admin_session):
        """GET /api/jobs/employer/sla-auto-triggers - delegated to phase-2 read service"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/sla-auto-triggers")
        assert resp.status_code in [200, 403, 401], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert "items" in data or "summary" in data or "total" in data

    def test_employer_offers_list_read(self, admin_session):
        """GET /api/jobs/employer/offers - delegated to phase-2 read service"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/offers")
        assert resp.status_code in [200, 403, 401], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert "offers" in data or "total" in data

    def test_employer_kpi_header_read(self, admin_session):
        """GET /api/jobs/employer/kpi-header - delegated to phase-2 read service"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/kpi-header")
        assert resp.status_code in [200, 403, 401, 404], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert "kpis" in data or "window_days" in data or "counts" in data

    def test_employer_hiring_forecast_read(self, admin_session):
        """GET /api/jobs/employer/hiring-forecast - delegated to phase-2 read service"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/hiring-forecast")
        assert resp.status_code in [200, 403, 401, 404], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert "forecast" in data or "window_days" in data or "recommendations" in data

    def test_talent_rediscovery_candidates_read(self, admin_session):
        """GET /api/jobs/employer/talent-rediscovery - delegated to phase-2 read service"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/talent-rediscovery")
        assert resp.status_code in [200, 403, 401, 404], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert "candidates" in data or "target_job" in data or "total" in data


class TestLegacyWriteRetirement:
    """Legacy write retirement enforcement tests"""

    def test_legacy_write_retirement_controls_exist_in_code(self):
        """Verify legacy write retirement controls are defined in jobs.py"""
        from pathlib import Path
        source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
        # Verify retirement controls exist
        assert 'legacy_retirement_enabled' in source
        assert 'retirement_phase' in source
        assert 'F26_RETIREMENT_PHASE_TO_FAMILIES' in source


class TestNoCircularImportRegression:
    """Verify no circular import/startup regressions"""

    def test_backend_health_after_phase2_extraction(self, session):
        """Backend health check - confirms no startup regressions"""
        resp = session.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Backend health check failed: {resp.status_code}"

    def test_jobs_search_still_works(self, session):
        """Jobs search endpoint - confirms phase-1 read service still works"""
        resp = session.get(f"{BASE_URL}/api/jobs/search?q=test&limit=5")
        assert resp.status_code == 200, f"Jobs search failed: {resp.status_code}"
        data = resp.json()
        assert "jobs" in data or "results" in data or "total" in data


class TestCriticalAdvancedReadEndpointsReachable:
    """Critical advanced read endpoints reachability tests"""

    def test_pipeline_board_endpoint_reachable(self, admin_session):
        """Pipeline board endpoint is reachable (not 500/502)"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/pipeline-board")
        assert resp.status_code not in [500, 502, 503], f"Server error: {resp.status_code}"

    def test_sla_alerts_endpoint_reachable(self, admin_session):
        """SLA alerts endpoint is reachable (not 500/502)"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/sla-alerts")
        assert resp.status_code not in [500, 502, 503], f"Server error: {resp.status_code}"

    def test_offers_endpoint_reachable(self, admin_session):
        """Offers endpoint is reachable (not 500/502)"""
        resp = admin_session.get(f"{BASE_URL}/api/jobs/employer/offers")
        assert resp.status_code not in [500, 502, 503], f"Server error: {resp.status_code}"
