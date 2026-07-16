from pathlib import Path


def test_hiring_v2_admin_canary_controls_endpoints_exist() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert '@router.get("/admin/canary-controls")' in source
    assert '@router.post("/admin/canary-controls")' in source
    assert '@router.post("/admin/canary-simulator")' in source


def test_hiring_v2_admin_canary_simulator_contract_keywords() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert 'rollback_risk_level' in source
    assert 'would_trigger_auto_rollback' in source
    assert 'projected_blocked_events' in source
    assert 'recommendation' in source
    assert 'feature_number": 26' in source
    assert 'feature_id": "jobs-portal"' in source


def test_hiring_v2_admin_premium_conversion_cohorts_endpoint_exists() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert '@router.get("/admin/premium-conversion-cohorts")' in source
    assert 'repeat_rate_pct' in source
    assert 'churn_signal_pct' in source
