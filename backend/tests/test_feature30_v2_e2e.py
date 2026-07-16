import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _assert_base_url() -> str:
    assert BASE_URL, "REACT_APP_BACKEND_URL is required for Feature 30 v2 E2E tests"
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


def test_feature30_v2_bootstrap_and_play_flow(free_session: requests.Session):
    base = _assert_base_url()

    bootstrap = free_session.get(f"{base}/api/sports/v2/bootstrap", params={"tz": "UTC"}, timeout=45)
    assert bootstrap.status_code == 200, f"sports v2 bootstrap failed: {bootstrap.text}"
    payload = bootstrap.json()

    assert payload.get("feature_id") == "watch-videos-sports"
    assert isinstance(payload.get("catalog"), list)
    assert bool(payload.get("contract", {}).get("no_manual_input"))
    assert bool(payload.get("contract", {}).get("no_upload"))

    free_items = [row for row in (payload.get("catalog") or []) if str(row.get("min_plan") or "free").lower() == "free"]
    assert free_items, "No free-tier sports item found for v2 play flow"
    item_id = str(free_items[0].get("item_id") or "")
    assert item_id, "Missing sports item_id"

    play = free_session.post(
        f"{base}/api/sports/v2/play",
        json={"item_id": item_id, "listen_seconds": 6, "completed": False, "source": "pytest_feature30_v2"},
        timeout=35,
    )
    assert play.status_code in {200, 429}, f"Unexpected sports v2 play status: {play.status_code} body={play.text}"


def test_feature30_v2_daily_drop_and_continue_watching(free_session: requests.Session):
    base = _assert_base_url()

    inbox = free_session.get(f"{base}/api/sports/v2/daily-drop-inbox", timeout=30)
    assert inbox.status_code == 200, f"sports v2 inbox failed: {inbox.text}"
    inbox_data = inbox.json()
    items = inbox_data.get("items") or []

    continue_watch = free_session.get(f"{base}/api/sports/v2/continue-watching", timeout=30)
    assert continue_watch.status_code == 200, f"sports continue watching failed: {continue_watch.text}"
    cont_payload = continue_watch.json()
    assert "items" in cont_payload

    if not items:
        return

    item_id = str(items[0].get("item_id") or "")
    assert item_id, "Missing inbox item_id"
    mark = free_session.post(
        f"{base}/api/sports/v2/daily-drop-inbox/mark-listened",
        json={"item_id": item_id},
        timeout=30,
    )
    assert mark.status_code == 200, f"sports v2 mark-listened failed: {mark.text}"


def test_feature30_v2_bootstrap_contract_shape(free_session: requests.Session):
    base = _assert_base_url()
    modern = free_session.get(f"{base}/api/sports/v2/bootstrap", params={"tz": "UTC"}, timeout=45)
    assert modern.status_code == 200
    modern_data = modern.json()
    assert modern_data.get("feature_id") == "watch-videos-sports"
    assert "sports_playability_summary" in modern_data


def test_feature30_admin_conversion_dashboard_access_contract(
    free_session: requests.Session,
    admin_session: requests.Session,
):
    base = _assert_base_url()

    blocked = free_session.get(
        f"{base}/api/sports/v2/admin/conversion-dashboard",
        params={"window_days": 7},
        timeout=35,
    )
    assert blocked.status_code == 403, f"Free user should be blocked from sports admin dashboard: {blocked.text}"

    allowed = admin_session.get(
        f"{base}/api/sports/v2/admin/conversion-dashboard",
        params={"window_days": 7},
        timeout=45,
    )
    assert allowed.status_code == 200, f"Admin dashboard failed: {allowed.text}"
    data = allowed.json()
    assert data.get("feature_id") == "sports"
    assert isinstance(data.get("kpis"), dict)
    assert isinstance(data.get("upgrade_funnel"), dict)
    cohorts = data.get("cohort_segmentation") or {}
    assert "geo_country" in cohorts
    assert "device_bucket" in cohorts
    assert "channel" in cohorts
