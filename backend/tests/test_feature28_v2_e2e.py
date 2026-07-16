import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _assert_base_url() -> str:
    assert BASE_URL, "REACT_APP_BACKEND_URL is required for Feature 28 v2 E2E tests"
    return str(BASE_URL).rstrip("/")


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    base = _assert_base_url()
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    login = session.post(
        f"{base}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Free login failed: {login.text}"
    return session


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    base = _assert_base_url()
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    login = session.post(
        f"{base}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Admin login failed: {login.text}"
    return session


def test_feature28_v2_bootstrap_and_play_flow(free_session: requests.Session):
    base = _assert_base_url()

    bootstrap = free_session.get(f"{base}/api/audio-studio/v2/bootstrap", params={"tz": "UTC"}, timeout=45)
    assert bootstrap.status_code == 200, f"v2 bootstrap failed: {bootstrap.text}"
    payload = bootstrap.json()

    assert payload.get("feature_id") == "watch-videos-audio-studio"
    assert isinstance(payload.get("catalog"), list)
    assert "source_health" in payload
    assert "status" in (payload.get("source_health") or {})

    free_items = [row for row in (payload.get("catalog") or []) if str(row.get("min_plan") or "free").lower() == "free"]
    assert free_items, "No free-tier item found for v2 play flow"
    item_id = str(free_items[0].get("item_id") or "")
    assert item_id, "Missing item_id"

    play = free_session.post(
        f"{base}/api/audio-studio/v2/play",
        json={"item_id": item_id, "listen_seconds": 5, "completed": False, "source": "pytest_v2"},
        timeout=30,
    )
    assert play.status_code in {200, 429}, f"Unexpected v2 play status: {play.status_code} body={play.text}"


def test_feature28_v2_daily_drop_and_mark_listened(free_session: requests.Session):
    base = _assert_base_url()
    inbox = free_session.get(f"{base}/api/audio-studio/v2/daily-drop-inbox", timeout=30)
    assert inbox.status_code == 200, f"v2 inbox failed: {inbox.text}"
    inbox_data = inbox.json()
    items = inbox_data.get("items") or []
    if not items:
        return

    item_id = str(items[0].get("item_id") or "")
    assert item_id, "Missing inbox item_id"
    mark = free_session.post(
        f"{base}/api/audio-studio/v2/daily-drop-inbox/mark-listened",
        json={"item_id": item_id},
        timeout=30,
    )
    assert mark.status_code == 200, f"v2 mark-listened failed: {mark.text}"


def test_feature28_legacy_wrapper_is_retired(free_session: requests.Session):
    base = _assert_base_url()

    legacy = free_session.get(f"{base}/api/videos/audio-studio/bootstrap", params={"tz": "UTC"}, timeout=45)
    assert legacy.status_code in {404, 410}, f"Expected retired wrapper status, got {legacy.status_code}"

    modern = free_session.get(f"{base}/api/audio-studio/v2/bootstrap", params={"tz": "UTC"}, timeout=45)
    assert modern.status_code == 200


def test_feature28_admin_conversion_dashboard_contract(admin_session: requests.Session):
    base = _assert_base_url()

    resp = admin_session.get(
        f"{base}/api/audio-studio/v2/admin/conversion-dashboard",
        params={"window_days": 7},
        timeout=45,
    )
    assert resp.status_code == 200, f"dashboard failed: {resp.text}"
    data = resp.json()

    assert data.get("feature_id") == "audio-studio"
    assert isinstance(data.get("kpis"), dict)
    assert isinstance(data.get("upgrade_funnel"), dict)
    assert "avg_session_length_seconds" in data.get("kpis", {})
    assert "completion_rate_pct" in data.get("kpis", {})
    assert "free_to_paid_rate_pct" in data.get("upgrade_funnel", {})
    assert "cohort_segmentation" in data
    assert "benchmark_deltas" in data
    cohorts = data.get("cohort_segmentation") or {}
    assert "geo_country" in cohorts
    assert "device_bucket" in cohorts
    assert "channel" in cohorts
