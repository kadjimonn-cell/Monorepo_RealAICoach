from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_feature28_bootstrap_uses_dedicated_service_extraction() -> None:
    source = _read("/app/backend/routes/audio_studio_v2_service.py")

    assert "from .audio_studio_v2_bootstrap_service import build_audio_studio_bootstrap" in source
    assert "return await build_audio_studio_bootstrap(request)" in source


def test_feature28_recommendation_logic_extracted_to_service_class_file() -> None:
    source = _read("/app/backend/routes/audio_studio_v2_recommendation_service.py")

    assert "async def refresh_taste_profile(" in source
    assert "async def adaptive_queue(" in source
    assert "async def build_behavioral_ai(" in source
    assert "def advanced_ml_rank(" in source


def test_feature28_conversion_dashboard_contains_cohorts_and_benchmarks_contract() -> None:
    source = _read("/app/backend/routes/audio_studio_v2_service.py")

    assert '"cohort_segmentation": {' in source
    assert '"benchmark_deltas": benchmark_deltas' in source
    assert '"required_cohorts": ["geo_country", "device_bucket", "channel"]' in source
    assert '"required_benchmark_metrics": ["avg_session_length_seconds", "completion_rate_pct", "free_to_paid_rate_pct"]' in source
