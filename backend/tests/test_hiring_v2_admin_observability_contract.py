from pathlib import Path


def test_hiring_v2_admin_observability_is_admin_guarded() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert '@router.get("/admin/workflow-events")' in source
    assert 'if not getattr(user, "is_admin", False):' in source
    assert 'raise HTTPException(status_code=403, detail="Admin access required")' in source


def test_hiring_v2_admin_observability_queries_hiring_events_collection() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert 'db.hiring_workflow_events' in source
    assert 'lookback_hours' in source
    assert 'include_metadata' in source
