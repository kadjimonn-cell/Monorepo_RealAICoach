from pathlib import Path


AI_DASHBOARD_PATH = Path('/app/frontend/app/ai-feature-dashboard.tsx')
ADMIN_ACTIVITY_PATH = Path('/app/frontend/app/admin-activity-log.tsx')
INTERVIEW_ROOM_PATH = Path('/app/frontend/app/interview-room.tsx')
AUTH_CONTEXT_PATH = Path('/app/frontend/src/context/AuthContext.tsx')
API_SERVICE_PATH = Path('/app/frontend/src/services/api.ts')


def test_ai_dashboard_uses_realtime_context_instead_of_page_level_ws() -> None:
    source = AI_DASHBOARD_PATH.read_text(encoding='utf-8')

    assert "useRealtime" in source
    assert "subscribeType('ai_alert'" in source
    assert "subscribeType('data_change'" in source
    assert 'new WebSocket(' not in source
    assert '/api/ws/notifications/' not in source
    assert 'useAutoRefresh(refreshAlerts, { intervalMs: connected ? undefined : 30000 })' not in source


def test_admin_activity_uses_realtime_context_instead_of_page_level_ws() -> None:
    source = ADMIN_ACTIVITY_PATH.read_text(encoding='utf-8')

    assert "useRealtime" in source
    assert "subscribeType('admin_alert'" in source
    assert "subscribeType('data_change'" in source
    assert 'new WebSocket(' not in source
    assert '/api/ws/notifications/' not in source
    assert 'useAutoRefresh(useCallback(() => fetchLog(page), [fetchLog, page]), { intervalMs: connected ? undefined : 30000 })' not in source


def test_interview_room_no_longer_runs_five_second_refresh_interval() -> None:
    source = INTERVIEW_ROOM_PATH.read_text(encoding='utf-8')

    assert 'setInterval(() => {' not in source
    assert "payload.type === 'data_change'" in source
    assert "api.get(`/interview-room/${roomId}`)" in source


def test_verify_2fa_forces_post_session_auth_me_refresh() -> None:
    source = AUTH_CONTEXT_PATH.read_text(encoding='utf-8')

    assert "await fetchAuthMeResilient({ phase: 'post-2fa', snapshot: null, force: true });" in source


def test_api_401_reset_uses_structured_error_code_matching() -> None:
    source = API_SERVICE_PATH.read_text(encoding='utf-8')

    assert 'function extractStructuredErrorCode(payload: any): string {' in source
    assert 'const errorCode = extractStructuredErrorCode(payload);' in source
    assert 'invalidTokenSignals' not in source
