from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_release_gate_script_exists_and_orders_steps() -> None:
    source = _read("/app/scripts/polling_guardrails_release_gate.sh")
    assert "[Step 1] Script gate" in source
    assert "[Step 1b] Feature32 override writer static gate" in source
    assert "[Step 2] Frontend observation gate" in source
    assert "[Step 3] Variability check (history)" in source
    assert "RELEASE_GATE_STATUS=PASS" in source


def test_release_gate_blocks_on_script_or_frontend_failure() -> None:
    source = _read("/app/scripts/polling_guardrails_release_gate.sh")
    assert "script gate failed" in source
    assert "feature32 override write gate failed" in source
    assert "feature32 override write gate failed" in source
    assert "frontend observation failed" in source
    assert "exit 2" in source


def test_release_gate_has_variability_fail_lock() -> None:
    source = _read("/app/scripts/polling_guardrails_release_gate.sh")
    assert "VARIABILITY_STATUS=FAIL" in source
    assert "oscillation" in source


def test_frontend_observation_parser_enforces_threshold_and_flood_state() -> None:
    source = _read("/app/scripts/polling_guardrails_frontend_observation_check.sh")
    assert "POLLING_GUARDRAILS_FRONTEND_MAX_429_TOTAL" in source
    assert "total_429_count" in source
    assert "flood_present" in source
    assert "FRONTEND_OBSERVATION_STATUS=FAIL (429 threshold exceeded)" in source
    assert "FRONTEND_OBSERVATION_STATUS=FAIL (flood marked present)" in source
    assert "FRONTEND_OBSERVATION_STATUS=PASS" in source
