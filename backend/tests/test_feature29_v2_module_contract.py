from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def test_feature29_v2_router_is_registered_in_miniapps_domain() -> None:
    source = _read("/app/backend/domains/miniapps.py")

    assert "from routes.podcasts_v2 import router as podcasts_v2_router" in source
    assert "api_router.include_router(podcasts_v2_router" in source


def test_feature29_v2_routes_expose_required_contracts() -> None:
    source = _read("/app/backend/routes/podcasts_v2.py")

    assert "APIRouter(prefix=\"/podcasts/v2\"" in source
    assert "@router.get(\"/bootstrap\")" in source
    assert "@router.post(\"/play\")" in source
    assert "@router.get(\"/continue-listening\")" in source
    assert "@router.get(\"/season-arc\")" in source
    assert "@router.get(\"/admin/conversion-dashboard\")" in source


def test_feature29_legacy_routes_delegate_to_v2_service() -> None:
    source = _read("/app/backend/routes/watch_audio_shared.py")

    assert '@router.get("/podcasts/bootstrap")' not in source
    assert '@router.post("/podcasts/play")' not in source
    assert '@router.get("/podcasts/daily-drop-inbox")' not in source
