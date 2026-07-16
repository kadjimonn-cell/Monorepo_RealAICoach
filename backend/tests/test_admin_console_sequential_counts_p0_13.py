from pathlib import Path


SOURCE_PATH = Path("/app/backend/routes/admin_console.py")


def _endpoint_segment(marker: str) -> str:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    start = source.index(marker)
    next_router = source.find("@router.get(", start + 1)
    if next_router == -1:
        return source[start:]
    return source[start:next_router]


def test_admin_overview_uses_aggregated_user_counts() -> None:
    segment = _endpoint_segment('@router.get("/admin/overview")')

    assert "count_documents(" not in segment
    assert "db.users.aggregate(" in segment
    assert '"$group"' in segment
    assert '"premium"' in segment
    assert '"basic"' in segment
    assert '"free"' in segment
    assert '"suspended"' in segment


def test_admin_ai_monitor_uses_single_aggregate_pipeline() -> None:
    segment = _endpoint_segment('@router.get("/admin/ai/monitor")')

    assert "count_documents(" not in segment
    assert "db.llm_search_logs.aggregate(" in segment
    assert '"$unionWith"' in segment
    assert '"media_playback_events"' in segment
    assert '"conversations"' in segment
