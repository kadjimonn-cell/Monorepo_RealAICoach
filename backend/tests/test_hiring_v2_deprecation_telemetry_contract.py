from pathlib import Path


def test_jobs_deprecation_telemetry_helpers_removed_after_final_cleanup() -> None:
    source = Path('/app/backend/routes/jobs.py').read_text(encoding='utf-8')
    assert 'LEGACY_V2_WRITE_TELEMETRY' not in source
    assert 'async def _record_legacy_write_telemetry(' not in source


def test_hiring_v2_admin_deprecation_endpoint_exists() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    assert '@router.get("/admin/deprecation-telemetry")' in source
    assert 'migration_progress_pct' in source
    assert 'top_legacy_endpoints' in source
