from pathlib import Path


def test_jobs_shared_has_transition_guard() -> None:
    source = Path('/app/backend/routes/jobs_shared.py').read_text(encoding='utf-8')
    assert 'def validate_application_transition(' in source
    assert 'terminal_status' in source
    assert 'reverse_transition' in source


def test_jobs_status_update_uses_transition_guard() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'validate_application_transition(' in source
    assert 'Invalid application status transition' in source
    assert 'status_code=409' in source


def test_jobs_apply_uses_hiring_plan_guard() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'require_hiring_plan(request, min_plan="free")' in source
    assert 'candidate_application_submitted' in source
