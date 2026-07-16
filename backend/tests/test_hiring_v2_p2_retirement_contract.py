from pathlib import Path


def test_hiring_v2_p2_retirement_endpoints_exist() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert '@router.get("/admin/legacy-retirement-readiness")' in source
    assert '@router.post("/admin/legacy-retirement-controls")' in source


def test_hiring_v2_p2_retirement_contract_keywords() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert 'target_phase_gate_ready' in source
    assert 'recommended_phase' in source
    assert 'family_readiness' in source
    assert 'retired_legacy_route_families' in source
    assert 'feature_number": 26' in source
    assert 'feature_id": "jobs-portal"' in source


def test_jobs_policy_has_retirement_phase_gate_helpers() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'F26_RETIREMENT_PHASE_TO_FAMILIES' in source
    assert '_compute_legacy_retirement_gate_status' in source
    assert '_enforce_legacy_route_family_retirement' not in source
    assert 'legacy_retirement_enabled' in source