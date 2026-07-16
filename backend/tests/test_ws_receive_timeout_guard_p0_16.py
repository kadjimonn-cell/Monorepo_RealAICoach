from pathlib import Path


SOURCE_PATH = Path("/app/backend/ws_endpoints.py")


def _endpoint_segment(marker: str) -> str:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    start = source.index(marker)
    next_ws = source.find("@app.websocket(", start + 1)
    if next_ws == -1:
        return source[start:]
    return source[start:next_ws]


def test_affected_ws_endpoints_use_wait_for_60s() -> None:
    markers = [
        'async def ws_notifications(',
        'async def ws_activity_stream(',
        'async def ws_admin_activity(',
        'async def ws_automation_dashboard(',
        'async def ws_aso_dashboard(',
    ]

    for marker in markers:
        segment = _endpoint_segment(marker)
        assert "await receive_text_with_heartbeat(" in segment
        assert "if unanswered_pings >= MAX_UNANSWERED_PINGS:" in segment
        assert "await websocket.receive_text()" not in segment
        assert "except asyncio.TimeoutError:" in segment


def test_unaffected_enterprise_live_keeps_existing_wait_pattern() -> None:
    segment = _endpoint_segment('async def ws_enterprise_live(')
    assert "await asyncio.wait_for(websocket.receive_text(), timeout=1)" in segment
