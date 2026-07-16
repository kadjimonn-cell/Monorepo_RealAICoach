from pathlib import Path


def test_feature34_safe_rollout_simulator_endpoint_contract_present() -> None:
    source = Path('/app/backend/routes/calendar_reliability.py').read_text(encoding='utf-8')
    assert '@router.get("/admin/calendar/release-gate/safe-rollout-simulator")' in source
    assert 'delta_go_rate_vs_active' in source
    assert 'recommendation' in source
