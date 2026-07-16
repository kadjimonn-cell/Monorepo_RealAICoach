import os

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _assert_base_url() -> str:
    assert BASE_URL, "REACT_APP_BACKEND_URL is required"
    return str(BASE_URL).rstrip("/")


def _login(email: str, password: str) -> requests.Session:
    base = _assert_base_url()
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    resp = session.post(f"{base}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return session


def test_podcasts_admin_conversion_dashboard_requires_admin() -> None:
    base = _assert_base_url()
    free_session = _login(FREE_USER_EMAIL, FREE_USER_PASSWORD)
    resp = free_session.get(f"{base}/api/podcasts/v2/admin/conversion-dashboard", params={"window_days": 7}, timeout=30)

    assert resp.status_code == 403, f"Expected 403 for non-admin; got {resp.status_code} body={resp.text}"
    data = resp.json()
    assert data.get("error") == "Admin Access Required"


def test_podcasts_admin_conversion_dashboard_allows_admin() -> None:
    base = _assert_base_url()
    admin_session = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    resp = admin_session.get(f"{base}/api/podcasts/v2/admin/conversion-dashboard", params={"window_days": 7}, timeout=45)

    assert resp.status_code == 200, f"Admin should be allowed: {resp.text}"
    data = resp.json()
    assert data.get("feature_id") == "my-podcasts"
    assert isinstance(data.get("kpis"), dict)
