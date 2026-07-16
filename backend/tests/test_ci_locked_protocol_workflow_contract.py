from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_locked_protocol_ci_workflow_exists_and_runs_required_checks() -> None:
    source = _read("/app/.github/workflows/locked-protocol-release-gates.yml")
    assert "name: locked-protocol-release-gates" in source
    assert "test_i18n_language_switch_deadlock_contract.py" in source
    assert "test_polling_guardrails_locked_protocol_contract.py" in source
    assert "test_polling_guardrails_release_gate_contract.py" in source
    assert "bash scripts/polling_guardrails_locked_protocol_check.sh" in source


def test_locked_protocol_script_supports_ci_paths_and_log_override() -> None:
    source = _read("/app/scripts/polling_guardrails_locked_protocol_check.sh")
    assert 'ROOT_DIR="${ROOT_DIR:-/app}"' in source
    assert 'REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/test_reports}"' in source
    assert "BACKEND_LOG_PATH" in source