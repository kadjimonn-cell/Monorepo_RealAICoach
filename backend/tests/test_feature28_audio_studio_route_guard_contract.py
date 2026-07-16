from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_access_control_explicitly_allows_feature28_audio_studio_route() -> None:
    source = _read("/app/frontend/src/context/AccessControlContext.tsx")

    assert "Explicit allowlist for Feature 28 (Audio Studio)" in source
    assert "normalizedPath.startsWith('/features/audio-studio')" in source
    assert "return { allowed: true };" in source
