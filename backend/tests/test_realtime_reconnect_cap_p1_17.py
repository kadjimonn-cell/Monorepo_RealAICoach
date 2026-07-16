from pathlib import Path


REALTIME_CONTEXT_PATH = Path('/app/frontend/src/context/RealtimeContext.tsx')
RECONNECT_BANNER_PATH = Path('/app/frontend/src/components/RealtimeReconnectBanner.tsx')
LAYOUT_PATH = Path('/app/frontend/app/_layout.tsx')


def test_realtime_context_has_auto_reconnect_cap_and_manual_resume() -> None:
    source = REALTIME_CONTEXT_PATH.read_text(encoding='utf-8')

    assert 'const MAX_AUTO_RECONNECT_ATTEMPTS = 10;' in source
    assert 'if (reconnectAttemptRef.current >= MAX_AUTO_RECONNECT_ATTEMPTS)' in source
    assert 'autoReconnectPausedRef.current = true' in source
    assert 'const reconnectNow = useCallback(() => {' in source
    assert 'void connect();' in source


def test_realtime_context_exposes_reconnect_state_and_action() -> None:
    source = REALTIME_CONTEXT_PATH.read_text(encoding='utf-8')

    assert 'connectionHealth' in source
    assert 'reconnectAttempt' in source
    assert 'autoReconnectPaused' in source
    assert 'const reconnectNow = useCallback(() => {' in source


def test_global_reconnect_button_is_rendered_when_auto_reconnect_paused() -> None:
    banner_source = RECONNECT_BANNER_PATH.read_text(encoding='utf-8')
    layout_source = LAYOUT_PATH.read_text(encoding='utf-8')

    assert 'data-testid="realtime-reconnect-button"' in banner_source
    assert 'onPress={reconnectNow}' in banner_source
    assert '<RealtimeReconnectBanner />' in layout_source
