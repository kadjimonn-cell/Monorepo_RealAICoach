from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_feature28_frontend_uses_dedicated_audio_studio_component() -> None:
    route_source = _read("/app/frontend/app/features/audio-studio.tsx")

    assert "AudioStudioFeature28" in route_source
    assert "<AudioStudioFeature28 />" in route_source


def test_feature28_frontend_resilience_loop_and_queue_continuity_contract() -> None:
    source = _read("/app/frontend/src/components/feature28/AudioStudioFeature28.tsx")

    assert "MAX_RETRY_ATTEMPTS = 3" in source
    assert "RETRY_BACKOFF_MS = [1500, 3000, 5000]" in source
    assert "playItemWithResilience" in source
    assert "playNextInQueue" in source
    assert "handleAudioEnded" in source
    assert "feature28_v2_track_ended" in source
    assert 'data-testid="feature28-audio-studio-v2-auto-advance-toggle"' in source


def test_feature28_admin_dashboard_card_is_wired_into_operations_console() -> None:
    source = _read("/app/frontend/src/components/OperationsConsoleView.tsx")

    assert "AudioStudioConversionCard" in source
    assert "<AudioStudioConversionCard colors={colors} />" in source
