from pathlib import Path


REALTIME_CONTEXT = Path("/app/frontend/src/context/RealtimeContext.tsx")
HOOK_LIVE_DATA = Path("/app/frontend/src/hooks/useLiveData.ts")


def test_realtime_context_remains_notifications_ws_owner() -> None:
    source = REALTIME_CONTEXT.read_text(encoding="utf-8")

    assert "new WebSocket(" in source
    assert "/api/ws/notifications/${userId}?ticket=" in source


def test_legacy_notifications_hook_is_removed() -> None:
    assert not Path("/app/frontend/src/hooks/useRealtimeNotifications.ts").exists()


def test_live_data_hook_uses_context_subscription_not_local_socket() -> None:
    source = HOOK_LIVE_DATA.read_text(encoding="utf-8")

    assert "useRealtime()" in source
    assert "subscribe(entity" in source
    assert "new WebSocket(" not in source
    assert "/auth/me" not in source
    assert "/auth/ws-ticket" not in source
