from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_scheduler_has_deterministic_challenge_guard_v2() -> None:
    source = _read("/app/backend/scheduler_jobs/audit_gates.py")

    assert "PREVIEW_CHALLENGE_GUARD_VERSION = \"v2_deterministic\"" in source
    assert "def _classify_external_preview_block(" in source
    assert "strict_cloudflare_markers" in source
    assert "soft_cloudflare_markers" in source
    assert "app_shell_markers" in source
    assert "title_has_challenge" in source
    assert "challenge_detection_guard" in source


def test_platform_health_exposes_challenge_guard_payload() -> None:
    source = _read("/app/backend/routes/platform_health.py")

    assert '"challenge_detection_guard": 1' in source
    assert '"challenge_detection_guard": item.get("challenge_detection_guard") or {}' in source
