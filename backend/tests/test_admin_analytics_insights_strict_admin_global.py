import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
NON_ADMIN_EMAIL = "curation.1779076352@example.com"
NON_ADMIN_PASSWORD = "NovaV2#2026!Aa"


def _assert_base_url() -> str:
    assert BASE_URL, "REACT_APP_BACKEND_URL is required"
    return BASE_URL


def _login(email: str, password: str) -> requests.Session:
    base = _assert_base_url()
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    resp = session.post(
        f"{base}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.status_code} {resp.text}"
    return session


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def non_admin_session() -> requests.Session:
    return _login(NON_ADMIN_EMAIL, NON_ADMIN_PASSWORD)


def test_non_admin_blocked_for_global_admin_analytics_and_insights(non_admin_session: requests.Session):
    base = _assert_base_url()
    blocked_paths = [
        "/api/admin/analytics",
        "/api/admin/subscription-analytics",
        "/api/admin/payment-analytics/provider-incidents/canary-status",
        "/api/admin/ai-insights/dashboard",
        "/api/admin/insights/dashboard",
        "/api/admin/executive/templates/analytics/summary",
    ]
    for path in blocked_paths:
        resp = non_admin_session.get(f"{base}{path}", timeout=40)
        assert resp.status_code == 403, f"Expected strict 403 for non-admin at {path}, got {resp.status_code}"
        payload = resp.json()
        assert (
            payload.get("error") == "Admin Access Required"
            or str(payload.get("detail") or "").strip().lower() in {"admin access required", "admin access required."}
            or str(payload.get("detail") or "").strip().lower() == "admin access required"
        ), f"Unexpected deny payload for {path}: {payload}"


def test_admin_allowed_for_global_admin_analytics_and_insights(admin_session: requests.Session):
    base = _assert_base_url()
    allowed_paths = [
        "/api/admin/analytics",
        "/api/admin/subscription-analytics",
        "/api/admin/payment-analytics/provider-incidents/canary-status",
        "/api/admin/ai-insights/dashboard",
        "/api/admin/insights/dashboard",
    ]
    for path in allowed_paths:
        resp = admin_session.get(f"{base}{path}", timeout=40)
        assert resp.status_code in {200, 404, 422}, (
            f"Admin should not be blocked by RBAC on {path}; got {resp.status_code} body={resp.text}"
        )
