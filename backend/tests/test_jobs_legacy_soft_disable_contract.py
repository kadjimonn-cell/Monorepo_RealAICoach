from pathlib import Path


def test_jobs_soft_disable_legacy_helpers_removed_after_final_cleanup() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'async def _enforce_legacy_write_policy(' not in source
    assert 'async def _record_canary_decision(' not in source
    assert 'async def _maybe_auto_rollback_from_deprecation_telemetry(' not in source


def test_jobs_handler_no_longer_has_endpoint_level_legacy_write_hooks() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'await _enforce_legacy_write_policy(' not in source
