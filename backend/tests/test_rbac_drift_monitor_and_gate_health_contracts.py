from pathlib import Path


def test_rbac_drift_monitor_endpoint_contract_present() -> None:
    source = Path('/app/backend/routes/platform_health.py').read_text(encoding='utf-8')
    assert '@router.get("/rbac-drift-monitor")' in source
    assert '_extract_admin_api_routes_for_drift' in source
    assert 'uncovered_route_count' in source


def test_rbac_gate_health_endpoint_contract_present() -> None:
    source = Path('/app/backend/routes/platform_health.py').read_text(encoding='utf-8')
    assert '@router.get("/rbac-gate-health")' in source
    assert 'health_score' in source
    assert 'block_rate' in source
