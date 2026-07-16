from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_preview_browser_e2e_runtime_failure_persists_failure_run_doc() -> None:
    source = _read("/app/backend/scheduler_jobs/audit_gates.py")

    assert "FAIL_PREVIEW_E2E_PLAYWRIGHT_RUNTIME_MISSING" in source
    assert "FAIL_PREVIEW_E2E_RUNTIME_UNAVAILABLE" in source
    assert "db.preview_browser_e2e_runs.insert_one" in source
    assert "preview_e2e_runtime_guard" in source
    assert '"status": "fail"' in source
    assert '"gate_status": "fail"' in source


def test_preview_browser_e2e_runtime_failure_updates_state_and_flags() -> None:
    source = _read("/app/backend/scheduler_jobs/audit_gates.py")

    assert "db.preview_browser_e2e_state.update_one" in source
    assert "db.system_runtime_flags.update_one" in source
    assert '"allowed_statuses": ["PASS", "FAIL", "BLOCKED"]' in source
    assert '"deterministic_outcome": True' in source
