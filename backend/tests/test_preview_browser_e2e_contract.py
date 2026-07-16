from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_preview_browser_e2e_scheduler_has_deterministic_status_contract() -> None:
    source = _read("/app/backend/scheduler_jobs/audit_gates.py")

    assert 'status_reason_code' in source
    assert 'NO_PREVIEW_RUN_DATA' in source
    assert 'PASS_EXTERNAL_PREVIEW_E2E' in source
    assert 'FAIL_EXTERNAL_PREVIEW_CHECKS' in source
    assert 'BLOCKED_EXTERNAL_PREVIEW_CLOUDFLARE' in source
    assert 'localhost_fallback_status' in source
    assert 'availability_contract' in source
    assert 'allowed_statuses' in source


def test_preview_browser_e2e_scheduler_has_localhost_fallback_lane() -> None:
    source = _read("/app/backend/scheduler_jobs/audit_gates.py")

    assert 'localhost_fallback_triggered' in source
    assert 'localhost_fallback_summary' in source
    assert 'fallback_base = "http://127.0.0.1:3000"' in source
    assert 'preview_block_wake_layer_code' in source
    assert 'preview_block_cloudflare_code' in source


def test_preview_browser_e2e_latest_endpoint_exposes_reason_and_lane_fields() -> None:
    source = _read("/app/backend/routes/platform_health.py")

    assert 'status_reason_code' in source
    assert 'external_lane_status' in source
    assert 'localhost_fallback_status' in source
