from pathlib import Path


REALTIME_CONTEXT_PATH = Path('/app/frontend/src/context/RealtimeContext.tsx')
USE_LIVE_DATA_PATH = Path('/app/frontend/src/hooks/useLiveData.ts')
WS_ENDPOINTS_PATH = Path('/app/backend/ws_endpoints.py')
WS_HEARTBEAT_UTIL_PATH = Path('/app/backend/utils/ws_heartbeat.py')
VIDEO_INTERVIEW_PATH = Path('/app/backend/routes/video_interview.py')
WHITEBOARD_PATH = Path('/app/backend/routes/whiteboard.py')
WS_MANAGER_PATH = Path('/app/backend/utils/ws_manager.py')


def test_realtime_context_backoff_floor_is_5000ms_and_connected_exposed() -> None:
    source = REALTIME_CONTEXT_PATH.read_text(encoding='utf-8')

    assert 'const MIN_RECONNECT_BACKOFF_MS = 5000;' in source
    assert 'connected: boolean;' in source
    assert 'value={{ connected, subscribe, subscribeType, reconnectNow' in source


def test_use_live_data_stays_consolidated_on_realtime_context() -> None:
    source = USE_LIVE_DATA_PATH.read_text(encoding='utf-8')

    assert 'const { subscribe } = useRealtime();' in source
    assert '/auth/ws-ticket' not in source
    assert '/auth/me' not in source
    assert 'const unsubscribers = uniqueEntities.map((entity) => subscribe(entity, () => fetchData()));' in source
    assert 'return () => {' in source
    assert 'unsubscribers.forEach((unsub) => unsub());' in source


def test_ws_endpoints_use_heartbeat_helper_and_two_unanswered_ping_guard() -> None:
    source = WS_ENDPOINTS_PATH.read_text(encoding='utf-8')

    assert 'from utils.ws_heartbeat import MAX_UNANSWERED_PINGS, receive_text_with_heartbeat' in source
    assert source.count('receive_text_with_heartbeat(') >= 5
    assert source.count('if unanswered_pings >= MAX_UNANSWERED_PINGS:') >= 5


def test_ws_heartbeat_utility_defines_timeout_ping_cycle_contract() -> None:
    source = WS_HEARTBEAT_UTIL_PATH.read_text(encoding='utf-8')

    assert 'RECEIVE_TIMEOUT_SECONDS = 60.0' in source
    assert 'MAX_UNANSWERED_PINGS = 2' in source
    assert 'await asyncio.wait_for(websocket.receive_text(), timeout=receive_timeout)' in source
    assert 'await ping_sender(websocket)' in source


def test_interview_and_whiteboard_routes_use_shared_heartbeat_receive() -> None:
    interview_source = VIDEO_INTERVIEW_PATH.read_text(encoding='utf-8')
    whiteboard_source = WHITEBOARD_PATH.read_text(encoding='utf-8')

    assert 'from utils.ws_heartbeat import MAX_UNANSWERED_PINGS, receive_text_with_heartbeat' in interview_source
    assert 'from utils.ws_heartbeat import MAX_UNANSWERED_PINGS, receive_text_with_heartbeat' in whiteboard_source
    assert 'raw, unanswered_pings = await receive_text_with_heartbeat(ws, unanswered_pings)' in interview_source
    assert 'raw, unanswered_pings = await receive_text_with_heartbeat(ws, unanswered_pings)' in whiteboard_source


def test_ws_manager_still_has_single_initializer_definition() -> None:
    source = WS_MANAGER_PATH.read_text(encoding='utf-8')

    assert source.count('def __init__(self):') == 1
