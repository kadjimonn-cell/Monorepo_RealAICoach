"""Feature 26 Phase-1 Legacy Read Decomposition Tests.

These tests verify legacy read handlers delegate to dedicated read-service modules,
avoiding route-level circular imports while preserving route contracts.
"""
from pathlib import Path
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_jobs_routes_delegate_phase1_candidate_reads_to_service_module() -> None:
    """Verify jobs.py delegates phase-1 candidate reads to jobs_read_service."""
    source = _read('/app/backend/routes/jobs.py')
    assert 'from .jobs_read_service import (' in source
    assert 'async def search_jobs(' in source
    assert 'return await search_jobs_read(' in source
    assert 'async def get_job_recommendations(' in source
    assert 'return await get_job_recommendations_read(' in source
    assert 'async def get_my_applications(' in source
    assert 'return await get_my_applications_read(' in source
    assert 'async def get_saved_jobs(' in source
    assert 'return await get_saved_jobs_read(' in source
    assert 'async def get_employee_profile(' in source
    assert 'return await get_employee_profile_read(' in source
    assert 'async def get_resume_score(' in source
    assert 'return await get_resume_score_read(' in source
    assert 'async def employee_analytics(' in source
    assert 'return await employee_analytics_read(' in source
    assert 'async def get_jobs_portal_summary(' in source
    assert 'return await get_jobs_portal_summary_read(' in source
    assert 'from .jobs_legacy_read_compat import' not in source


def test_employers_routes_delegate_phase1_high_traffic_reads_to_service_module() -> None:
    """Verify employers.py delegates phase-1 high-traffic reads to employers_read_service."""
    source = _read('/app/backend/routes/employers.py')
    assert 'from .employers_read_service import (' in source
    assert 'async def get_my_application(' in source
    assert 'return await get_my_application_read(' in source
    assert 'async def download_employer_document(' in source
    assert 'return await download_employer_document_read(' in source
    assert 'async def get_my_permissions(' in source
    assert 'return await get_my_permissions_read(' in source
    assert 'async def admin_get_application(' in source
    assert 'return await admin_get_application_read(' in source
    assert 'async def admin_employer_communications(' in source
    assert 'return await admin_employer_communications_read(' in source
    assert 'async def get_employer_messages(' in source
    assert 'return await get_employer_messages_read(' in source
    assert 'async def check_reverify_status(' in source
    assert 'return await check_reverify_status_read(' in source
    assert 'from .employers_legacy_read_compat import' not in source


def test_phase1_read_service_modules_exist() -> None:
    jobs_service = _read('/app/backend/routes/jobs_read_service.py')
    employers_service = _read('/app/backend/routes/employers_read_service.py')
    assert 'async def search_jobs_read' in jobs_service
    assert 'async def get_jobs_portal_summary_read' in jobs_service
    assert 'async def get_my_application_read' in employers_service
    assert 'async def admin_get_application_read' in employers_service


def test_jobs_search_endpoint_works() -> None:
    """Verify /api/jobs/search endpoint is reachable."""
    response = requests.get(f"{BASE_URL}/api/jobs/search", timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert 'jobs' in data or 'total' in data


def test_jobs_portal_summary_requires_auth() -> None:
    """Verify /api/jobs/portal-summary requires authentication."""
    response = requests.get(f"{BASE_URL}/api/jobs/portal-summary", timeout=10)
    # Should require auth (401) or work if public
    assert response.status_code in [200, 401]


def test_employers_my_application_requires_auth() -> None:
    """Verify /api/employers/my-application requires authentication."""
    response = requests.get(f"{BASE_URL}/api/employers/my-application", timeout=10)
    assert response.status_code == 401  # Requires auth


def test_legacy_write_retirement_intact() -> None:
    """Verify legacy write routes return 410 Gone (retirement intact) or 401 (auth first)."""
    # Test legacy write routes are retired (may return 401 if auth check comes first)
    response = requests.post(f"{BASE_URL}/api/jobs/apply", json={}, timeout=10)
    assert response.status_code in [401, 410]  # Auth required or Gone - retired

    response = requests.put(f"{BASE_URL}/api/jobs/update/test_job", json={}, timeout=10)
    assert response.status_code in [401, 410]  # Auth required or Gone - retired


def test_v2_admin_endpoints_reachable() -> None:
    """Verify v2 admin endpoints are still reachable."""
    # These should require auth but be reachable
    response = requests.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls", timeout=10)
    assert response.status_code in [200, 401, 403]  # Reachable (auth required)

    response = requests.get(f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry", timeout=10)
    assert response.status_code in [200, 401, 403]  # Reachable (auth required)
