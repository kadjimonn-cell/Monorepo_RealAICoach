from pathlib import Path


def test_hiring_v2_router_exists_and_has_prefix() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert 'APIRouter(prefix="/hiring/v2")' in source


def test_hiring_v2_core_endpoints_present() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    for route in [
        '@router.get("/health")',
        '@router.get("/candidate/jobs/search")',
        '@router.get("/candidate/applications")',
        '@router.get("/candidate/saved-jobs")',
        '@router.get("/candidate/analytics")',
        '@router.get("/dashboard/summary")',
        '@router.get("/employer/offers")',
        '@router.get("/employer/pipeline-board")',
        '@router.get("/employer/kpi-header")',
        '@router.get("/employer/sla-alerts")',
        '@router.get("/admin/workflow-events")',
    ]:
        assert route in source


def test_hiring_domain_registers_hiring_v2_router() -> None:
    source = Path('/app/backend/domains/hiring.py').read_text(encoding='utf-8')
    assert 'from routes import hiring_v2' in source
    assert 'api_router.include_router(hiring_v2.router' in source
