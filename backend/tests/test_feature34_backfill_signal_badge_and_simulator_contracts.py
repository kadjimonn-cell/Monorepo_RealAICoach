from pathlib import Path


def _read_source() -> str:
    return Path('/app/backend/routes/platform_health.py').read_text(encoding='utf-8')


def test_backfill_signal_badge_contract_present() -> None:
    source = _read_source()
    assert '_derive_backfill_signal_badge' in source
    assert 'likely_false_positive_count' in source
    assert 'likely_true_challenge_count' in source
    assert 'signal_badge' in source


def test_backfill_safe_rollout_simulator_contract_present() -> None:
    source = _read_source()
    assert 'BACKFILL_SIMULATOR_PROFILES' in source
    assert '@router.get("/preview-browser-e2e/backfill-false-positives/simulator")' in source
    assert 'delta_vs_standard' in source
