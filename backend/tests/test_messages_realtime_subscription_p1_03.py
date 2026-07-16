from pathlib import Path


SOURCE_PATH = Path("/app/frontend/app/messages.tsx")


def test_messages_screen_no_longer_uses_15s_polling_interval() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "setInterval(fetchInbox, 15000)" not in source


def test_messages_screen_subscribes_to_realtime_bus_events() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "useRealtime" in source
    assert "subscribeType('new_message'" in source
    assert "subscribeType('read_receipt'" in source
    assert "subscribeType('typing_indicator'" in source
