from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_deploy_script_uses_current_guard_suite_and_no_legacy_stale_tests() -> None:
    source = _read("/app/scripts/deploy_expo_web.sh")

    # Must include current fail-closed guard suite structure.
    assert "GUARD_TESTS=(" in source
    assert "tests/test_env_guard.py" in source
    assert "tests/test_stale_url_ci_guard.py" in source
    assert "tests/test_issue11_theme_consistency_contract.py" in source
    assert "tests/test_polling_guardrails_locked_protocol_contract.py" in source
    assert "tests/test_polling_guardrails_release_gate_contract.py" in source
    assert "tests/test_i18n_language_switch_deadlock_contract.py" in source
    assert "Required guard test missing" in source

    # Must not reference stale legacy GTEC tests that do not exist.
    assert "tests/test_theme_no_bypass_guard.py" not in source
    assert "tests/test_v7_no_bypasses_guard.py" not in source
    assert "tests/test_careers_apply_emails_guard.py" not in source
    assert "tests/test_careers_attachments_guard.py" not in source
    assert "tests/test_route_health_v2_theme_guard.py" not in source
