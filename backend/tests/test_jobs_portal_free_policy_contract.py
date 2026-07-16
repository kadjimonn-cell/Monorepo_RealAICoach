from pathlib import Path


def test_jobs_and_employer_onboarding_are_free_in_subscription_enforcement() -> None:
    source = Path('/app/backend/routes/subscription_enforcement.py').read_text(encoding='utf-8')
    assert 'r"^/api/jobs/"' in source
    assert 'r"^/api/employers/(apply|upload-document|my-application|my-permissions|permissions|messages/|documents/|resubmit-info|reverify-status|reverify)(/|$)"' in source


def test_jobs_and_employer_onboarding_are_free_in_access_control_engine() -> None:
    source = Path('/app/backend/utils/access_control_engine.py').read_text(encoding='utf-8')
    assert 'r"^/api/jobs/"' in source
    assert 'r"^/api/employers/(apply|upload-document|my-application|my-permissions|permissions|messages/|documents/|resubmit-info|reverify-status|reverify)(/|$)"' in source
