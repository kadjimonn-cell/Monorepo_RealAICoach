from pathlib import Path


def test_offer_transition_guard_exists() -> None:
    source = Path('/app/backend/routes/jobs_shared.py').read_text(encoding='utf-8')
    assert 'def validate_offer_transition(' in source
    assert 'terminal_offer_status' in source
    assert 'reverse_offer_transition' in source
    assert 'sent_requires_approval' in source


def test_offer_endpoints_use_transition_guard() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'validate_offer_transition(' in source
    assert 'Invalid offer lifecycle transition' in source
    assert 'target_status": "pending_approval"' in source
    assert 'target_status": "approved"' in source
    assert 'target_status": "sent"' in source


def test_esign_offer_uses_transition_guard() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'target_offer_status = "accepted" if decision == "accept" else "declined"' in source
    assert 'validate_offer_transition(' in source
