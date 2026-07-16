import os

import pytest
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
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = s.post(f"{base}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return s


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    return _login(FREE_USER_EMAIL, FREE_USER_PASSWORD)


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


def test_non_admin_blocked_from_admin_analytics_endpoints(free_session: requests.Session):
    base = _assert_base_url()
    blocked_paths = [
        "/api/admin/analytics",
        "/api/admin/analytics/retention",
        "/api/admin/analytics/churn",
        "/api/admin/analytics/feature-quality",
        "/api/admin/executive/overview",
        "/api/sports/v2/admin/conversion-dashboard",
    ]
    for path in blocked_paths:
        r = free_session.get(f"{base}{path}", timeout=30)
        assert r.status_code in {401, 403}, f"Expected blocked access for free user at {path}, got {r.status_code}"


def test_admin_can_access_admin_analytics_endpoints(admin_session: requests.Session):
    base = _assert_base_url()
    allowed_paths = [
        "/api/admin/analytics",
        "/api/admin/executive/overview",
        "/api/sports/v2/admin/conversion-dashboard",
    ]
    for path in allowed_paths:
        r = admin_session.get(f"{base}{path}", timeout=30)
        assert r.status_code == 200, f"Expected admin access at {path}, got {r.status_code}"
