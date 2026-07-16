from pathlib import Path


def test_require_hiring_plan_uses_effective_plan_engine() -> None:
    source = Path('/app/backend/routes/jobs_shared.py').read_text(encoding='utf-8')
    assert 'compute_effective_plan' in source
    assert 'normalize_plan(compute_effective_plan(' in source
    assert 'PLAN_LEVEL' in source


def test_hiring_plan_guard_supports_tiered_min_plan() -> None:
    source = Path('/app/backend/routes/jobs_shared.py').read_text(encoding='utf-8')
    assert 'async def require_hiring_plan(' in source
    assert 'min_plan: str = "free"' in source
    assert 'required_plan' in source
    assert 'upgrade_url' in source


def test_feature26_apply_flow_is_guarded_by_plan_check() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'require_hiring_plan(request, min_plan="free")' in source
