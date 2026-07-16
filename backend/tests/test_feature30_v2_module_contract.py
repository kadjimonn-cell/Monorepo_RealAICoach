from pathlib import Path


def test_feature30_v2_router_registered_in_global_domain():
    source = Path('/app/backend/domains/miniapps.py').read_text(encoding='utf-8')
    assert 'from routes.sports_v2 import router as sports_v2_router' in source
    assert 'api_router.include_router(sports_v2_router' in source


def test_feature30_legacy_routes_delegate_to_v2_service():
    source = Path('/app/backend/routes/watch_audio_shared.py').read_text(encoding='utf-8')
    assert '@router.get("/sports/bootstrap")' not in source
    assert '@router.post("/sports/play")' not in source
    assert '@router.get("/sports/daily-drop-inbox")' not in source
    assert '@router.post("/sports/daily-drop-inbox/mark-listened")' not in source
    assert '@router.get("/admin/sports-source-health")' not in source


def test_feature30_v2_router_exports_core_endpoints():
    source = Path('/app/backend/routes/sports_v2.py').read_text(encoding='utf-8')
    assert 'router = APIRouter(prefix="/sports/v2"' in source
    assert '@router.get("/bootstrap")' in source
    assert '@router.post("/play")' in source
    assert '@router.get("/daily-drop-inbox")' in source
    assert '@router.get("/continue-watching")' in source
    assert '@router.get("/matchday-streak")' in source
    assert '@router.get("/prediction-challenges")' in source
    assert '@router.post("/prediction-challenges/submit")' in source
    assert '@router.get("/admin/conversion-dashboard")' in source


def test_feature30_v2_services_no_longer_depend_on_watch_audio_hub_sports_internals():
    service_source = Path('/app/backend/routes/sports_v2_service.py').read_text(encoding='utf-8')
    bootstrap_source = Path('/app/backend/routes/sports_v2_bootstrap_service.py').read_text(encoding='utf-8')
    assert 'from .watch_audio_shared import' not in service_source
    assert 'from .watch_audio_shared import' not in bootstrap_source
