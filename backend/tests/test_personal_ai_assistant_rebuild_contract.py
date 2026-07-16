from pathlib import Path


ASSISTANT_ROUTE_PATH = Path('/app/backend/routes/personal_assistant.py')
AI_CHATBOT_PAGE_PATH = Path('/app/frontend/app/features/ai-chatbot.tsx')
SERVER_PATH = Path('/app/backend/server.py')
ASSISTANT_E2E_PATH = Path('/app/frontend/e2e/ai-chatbot.spec.ts')


def test_personal_assistant_route_exists_with_core_endpoints() -> None:
    source = ASSISTANT_ROUTE_PATH.read_text(encoding='utf-8')

    assert 'router = APIRouter(prefix="/personal-assistant", tags=["Personal AI Assistant"])' in source
    assert '@router.get("/bootstrap")' in source
    assert '@router.post("/sessions")' in source
    assert '@router.get("/sessions/{session_id}")' in source
    assert '@router.post("/sessions/{session_id}/messages")' in source
    assert '@router.post("/memory")' in source
    assert '@router.post("/actions")' in source
    assert '@router.post("/daily-brief")' in source


def test_personal_assistant_route_registered_in_server() -> None:
    source = SERVER_PATH.read_text(encoding='utf-8')

    assert 'from routes.personal_assistant import router as personal_assistant_router' in source
    assert 'api_router.include_router(personal_assistant_router)' in source


def test_ai_chatbot_frontend_uses_personal_assistant_v2_endpoints() -> None:
    source = AI_CHATBOT_PAGE_PATH.read_text(encoding='utf-8')

    assert '/personal-assistant/bootstrap' in source
    assert '/personal-assistant/sessions' in source
    assert '/personal-assistant/actions' in source
    assert '/personal-assistant/memory' in source
    assert '/personal-assistant/daily-brief' in source
    assert 'handleAppRecoverableError' in source
    assert 'personal-ai-assistant-v2-root' in source


def test_personal_assistant_e2e_exists() -> None:
    source = ASSISTANT_E2E_PATH.read_text(encoding='utf-8')

    assert 'Personal AI Assistant v2 @component' in source
    assert 'personal-ai-assistant-v2-root' in source
    assert 'personal-ai-assistant-create-session-button' in source
