from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_feature29_page_uses_dedicated_v2_component_not_shared_audio_catalog_tab() -> None:
    source = _read("/app/frontend/app/features/my-podcasts.tsx")

    assert "PodcastsFeature29" in source
    assert "AudioCatalogTab mode=\"podcasts\"" not in source


def test_feature29_ui_has_no_manual_input_or_upload_controls() -> None:
    source = _read("/app/frontend/src/components/feature29/PodcastsFeature29.tsx").lower()

    blocked_signals = [
        "<textinput",
        "type=\"file\"",
        "documentpicker",
        "upload",
        "textarea",
    ]
    for signal in blocked_signals:
        assert signal not in source, f"Found blocked manual/upload signal: {signal}"


def test_feature29_v2_bootstrap_contract_marks_no_manual_no_upload() -> None:
    source = _read("/app/backend/routes/podcasts_v2_bootstrap_service.py")

    assert '"no_manual_input": True' in source
    assert '"no_upload": True' in source
