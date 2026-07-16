from pathlib import Path


SOURCE_PATH = Path("/app/frontend/src/components/ErrorBoundary.tsx")


def test_error_boundary_declares_session_attempt_limit_constants() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "AUTO_RECOVERY_ATTEMPTS_KEY" in source
    assert "MAX_AUTO_RELOAD_ATTEMPTS = 3" in source
    assert "tryConsumeAutoReloadAttempt" in source


def test_hooks_and_general_paths_use_attempt_limit_before_reload() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert source.count("const attemptInfo = tryConsumeAutoReloadAttempt();") >= 1
    assert "if (attemptInfo.allowed)" in source
    assert "auto_reload_blocked" in source
    assert "setTimeout(() => window.location.reload(), 120);" not in source


def test_general_runtime_errors_do_not_trigger_auto_reload() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "reason: 'general_runtime_error'" in source
    assert "mode: 'manual_required'" in source


def test_recovery_window_is_extended_to_30_seconds() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "const RECOVERY_WINDOW_MS = 30000;" in source


def test_static_recovery_mode_marker_exists_after_limit() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert "autoRecoveryLocked" in source
    assert "error-boundary-static-recovery-note" in source
    assert "Automatic reload is paused after multiple failures" in source
