from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_feature28_v2_router_is_registered_in_miniapps_domain() -> None:
    source = _read("/app/backend/domains/miniapps.py")

    assert "from routes.audio_studio_v2 import router as audio_studio_v2_router" in source
    assert "api_router.include_router(audio_studio_v2_router" in source


def test_feature28_v2_routes_expose_bootstrap_play_and_dashboard() -> None:
    source = _read("/app/backend/routes/audio_studio_v2.py")

    assert "APIRouter(prefix=\"/audio-studio/v2\"" in source
    assert "@router.get(\"/bootstrap\")" in source
    assert "@router.post(\"/play\")" in source
    assert "@router.get(\"/admin/conversion-dashboard\")" in source


def test_feature28_legacy_routes_delegate_to_v2_service() -> None:
    source = _read("/app/backend/routes/watch_audio_shared.py")

    assert '@router.get("/audio-studio/bootstrap")' not in source
    assert '@router.post("/audio-studio/play")' not in source
    assert '@router.get("/audio-studio/daily-drop-inbox")' not in source


def test_feature28_legacy_retirement_admin_endpoints_present() -> None:
    source = _read("/app/backend/routes/watch_videos_retirement_governance.py")

    assert '@router.get("/legacy-wrapper-retirement-readiness")' in source
    assert '@router.post("/legacy-wrapper-retirement-controls")' in source


def test_feature28_retirement_governance_router_is_registered_in_miniapps_domain() -> None:
    source = _read("/app/backend/domains/miniapps.py")
    assert "from routes.watch_videos_retirement_governance import router as watch_videos_retirement_governance_router" in source
    assert "api_router.include_router(watch_videos_retirement_governance_router" in source


def test_feature28_governance_test_suite_consolidated() -> None:
    source = _read("/app/backend/tests/governance_retirement/test_package_contract.py")
    assert "test_governance_package_files_exist" in source
