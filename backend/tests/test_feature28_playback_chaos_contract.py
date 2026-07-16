from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_feature28_playback_resilience_chaos_harness_contract() -> None:
    source = _read("/app/frontend/src/components/feature28/playbackResilience.ts")

    assert "export const MAX_RETRY_ATTEMPTS = 3" in source
    assert "export const RETRY_BACKOFF_MS = [1500, 3000, 5000]" in source
    assert "class PlaybackChaosController" in source
    assert "transient_5xx_once" in source
    assert "always_5xx" in source
    assert "network_once" in source
    assert "evaluateResilienceDecision" in source
    assert "getNextQueueCandidateIndex" in source


def test_feature28_frontend_uses_chaos_harness_in_resilience_loop() -> None:
    source = _read("/app/frontend/src/components/feature28/AudioStudioFeature28.tsx")

    assert "PlaybackChaosController" in source
    assert "evaluateResilienceDecision" in source
    assert "getNextQueueCandidateIndex" in source
    assert "chaosControllerRef" in source
