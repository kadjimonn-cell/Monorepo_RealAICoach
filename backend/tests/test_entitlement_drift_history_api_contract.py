from pathlib import Path


SOURCE_PATH = Path("/app/backend/routes/code_health.py")


def test_entitlement_drift_history_endpoint_exists() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert '@router.get("/entitlement-drift/history")' in source
    assert 'await require_admin(request)' in source
    assert 'ENTITLEMENT_DRIFT_COLLECTION = "entitlement_drift_audit_log"' in source


def test_entitlement_drift_history_endpoint_caps_limit_and_excludes_objectid() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert 'ENTITLEMENT_DRIFT_MAX_HISTORY = 30' in source
    assert 'safe_limit = max(1, min(int(limit or 7), ENTITLEMENT_DRIFT_MAX_HISTORY))' in source
    assert 'find({}, {"_id": 0})' in source


def test_entitlement_drift_history_shapes_preview_findings() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert 'def _shape_entitlement_drift_history_row' in source
    assert 'preview_source = "new_findings" if payload.get("new_findings") else "findings"' in source
    assert '"preview_findings": preview_findings' in source
    assert '"baseline_previous_finding_count": int(payload.get("baseline_previous_finding_count") or 0)' in source
