from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_audio_studio_bootstrap_exposes_source_health_contract() -> None:
    source = _read("/app/backend/routes/watch_audio_shared.py")

    assert "def _audio_source_health_summary" in source
    assert '"AUDIO_STUDIO_SOURCE_HEALTH_OK"' in source
    assert '"AUDIO_STUDIO_SOURCE_HEALTH_PARTIAL_DEGRADATION"' in source
    assert '"AUDIO_STUDIO_SOURCE_HEALTH_NO_PLAYABLE_ITEMS"' in source
    assert '"source_health": source_health' in source
    assert '"allowed_statuses": ["HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN"]' in source


def test_audio_studio_frontend_uses_cookie_auth_only_and_source_health_banner() -> None:
    source = _read("/app/frontend/src/components/AudioCatalogTab.tsx")

    assert "const getAuthHeaders = useCallback(() => ({} as Record<string, string>), [])" in source
    assert 'data-testid="audio-studio-source-health-banner"' in source
    assert 'data-testid="audio-studio-source-health-status"' in source
    assert 'data-testid="audio-studio-source-health-reason"' in source
