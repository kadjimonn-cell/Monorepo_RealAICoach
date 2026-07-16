from pathlib import Path


WRITING_STUDIO_ROUTE_PATH = Path('/app/backend/routes/writing_studio.py')
AI_WRITER_PAGE_PATH = Path('/app/frontend/app/features/ai-writer.tsx')
SERVER_PATH = Path('/app/backend/server.py')
AI_WRITER_E2E_PATH = Path('/app/frontend/e2e/ai-writer.spec.ts')


def test_writing_studio_route_exists_with_core_endpoints() -> None:
    source = WRITING_STUDIO_ROUTE_PATH.read_text(encoding='utf-8')

    assert 'router = APIRouter(prefix="/writing-studio", tags=["Writing Studio"])' in source
    assert '@router.get("/bootstrap")' in source
    assert '@router.post("/documents")' in source
    assert '@router.patch("/documents/{doc_id}")' in source
    assert '@router.get("/documents/{doc_id}")' in source
    assert '@router.post("/runs")' in source
    assert '@router.put("/brand-profile")' in source


def test_writing_studio_route_included_in_server_registry() -> None:
    source = SERVER_PATH.read_text(encoding='utf-8')

    assert 'from routes.writing_studio import router as writing_studio_router' in source
    assert 'api_router.include_router(writing_studio_router)' in source


def test_ai_writer_frontend_uses_writing_studio_v2_apis_and_recoverable_errors() -> None:
    source = AI_WRITER_PAGE_PATH.read_text(encoding='utf-8')

    assert '/writing-studio/bootstrap' in source
    assert '/writing-studio/documents' in source
    assert '/writing-studio/runs' in source
    assert 'handleAppRecoverableError' in source
    assert 'smart-writing-studio-v2-root' in source


def test_ai_writer_e2e_contract_exists() -> None:
    source = AI_WRITER_E2E_PATH.read_text(encoding='utf-8')

    assert "Smart Writing Studio v2 @component" in source
    assert 'smart-writing-studio-v2-root' in source
    assert 'smart-writing-studio-create-doc-button' in source
