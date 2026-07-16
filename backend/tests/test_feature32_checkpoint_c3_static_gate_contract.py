from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_feature32_override_write_gate_script_enforces_allowlist() -> None:
    source = _read("/app/scripts/feature32_override_write_gate.sh")
    assert "email_subject_overrides.(update_one|insert_one|update_many|replace_one)" in source
    assert "backend/services/email_override_service.py" in source
    assert "backend/scripts/remediate_protected_subject_overrides.py" in source
    assert "FEATURE32_OVERRIDE_WRITE_GATE=FAIL" in source
    assert "FEATURE32_OVERRIDE_WRITE_GATE=PASS" in source


def test_release_gate_executes_feature32_static_gate() -> None:
    source = _read("/app/scripts/polling_guardrails_release_gate.sh")
    assert "[Step 1b] Feature32 override writer static gate" in source
    assert "bash scripts/feature32_override_write_gate.sh" in source
