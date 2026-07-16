from pathlib import Path


ROUTE_PATH = Path('/app/backend/routes/research_navigator.py')
SERVER_PATH = Path('/app/backend/server.py')
FRONTEND_PATH = Path('/app/frontend/src/components/AISearchScreen.tsx')
E2E_PATH = Path('/app/frontend/e2e/ai-search.spec.ts')


def test_research_navigator_route_has_core_endpoints() -> None:
    source = ROUTE_PATH.read_text(encoding='utf-8')

    assert 'router = APIRouter(prefix="/research-navigator", tags=["Deep Research Navigator"])' in source
    assert '@router.get("/bootstrap")' in source
    assert '@router.post("/projects")' in source
    assert '@router.get("/projects/{project_id}")' in source
    assert '@router.post("/projects/{project_id}/runs")' in source
    assert '@router.get("/runs/{run_id}")' in source
    assert '@router.post("/projects/{project_id}/insights")' in source


def test_research_navigator_multi_source_connectors_exist() -> None:
    """Phase 2: multi-source connectors (arXiv + PubMed + SEC EDGAR) must exist."""
    source = ROUTE_PATH.read_text(encoding='utf-8')
    
    # All 5 connector functions must exist
    assert 'async def _fetch_wikipedia_sources(' in source
    assert 'async def _fetch_duckduckgo_source(' in source
    assert 'async def _fetch_arxiv_sources(' in source
    assert 'async def _fetch_pubmed_sources(' in source
    assert 'async def _fetch_sec_sources(' in source
    
    # Source metadata fields must be present
    assert '"source_type":' in source or "'source_type':" in source
    assert '"published_at":' in source or "'published_at':" in source


def test_research_navigator_route_registered() -> None:
    source = SERVER_PATH.read_text(encoding='utf-8')
    assert 'from routes.research_navigator import router as research_navigator_router' in source
    assert 'api_router.include_router(research_navigator_router)' in source


def test_frontend_ai_search_uses_research_navigator_v2_endpoints() -> None:
    source = FRONTEND_PATH.read_text(encoding='utf-8')

    assert '/research-navigator/bootstrap' in source
    assert '/research-navigator/projects' in source
    assert '/research-navigator/projects/${projectId}/runs' in source
    assert '/research-navigator/projects/${activeProjectId}/insights' in source
    assert 'deep-research-navigator-v2-root' in source
    assert 'handleAppRecoverableError' in source


def test_deep_research_e2e_exists() -> None:
    source = E2E_PATH.read_text(encoding='utf-8')
    assert 'Deep Research Navigator v2 @component' in source
    assert 'deep-research-run-button' in source
    assert 'deep-research-save-insight-button' in source
