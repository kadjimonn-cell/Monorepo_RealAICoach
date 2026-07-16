from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_governance_package_files_exist() -> None:
    assert Path("/app/backend/tests/governance_retirement/conftest.py").exists()
    assert Path("/app/backend/tests/governance_retirement/test_governance_endpoints.py").exists()
    assert Path("/app/backend/tests/governance_retirement/test_phase_rollout_and_hard_delete.py").exists()


def test_deprecated_legacy_suites_are_marked_skip() -> None:
    old_files = [
        "/app/backend/tests/test_watch_videos_legacy_wrapper_retirement.py",
        "/app/backend/tests/test_phase2_audio_podcasts_retirement.py",
        "/app/backend/tests/test_watch_videos_legacy_wrapper_strict_zero_promotion.py",
    ]
    for path in old_files:
        source = _read(path)
        assert "pytest.skip(\"Deprecated duplicate retirement suite; replaced by governance_retirement package\"" in source


def test_governance_module_has_telemetry_scaffold() -> None:
    source = _read("/app/backend/routes/watch_videos_retirement_governance.py")
    assert "async def _future_telemetry_rollup_stub" in source
    assert "telemetry_scaffold" in source
