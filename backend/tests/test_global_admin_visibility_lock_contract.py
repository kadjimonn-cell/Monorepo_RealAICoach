import os

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
    resp = session.post(f"{base}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert resp.status_code == 200, f"Login failed for {email}: {resp.status_code} {resp.text}"
    return session


def test_global_admin_analytics_insights_non_admin_denied() -> None:
    base = _assert_base_url()
    non_admin = _login(NON_ADMIN_EMAIL, NON_ADMIN_PASSWORD)
    blocked_paths = [
        "/api/admin/analytics",
        "/api/admin/analytics/retention",
        "/api/admin/insights/dashboard",
        "/api/admin/ai-insights/dashboard",
    ]
    for path in blocked_paths:
        resp = non_admin.get(f"{base}{path}", timeout=30)
        assert resp.status_code == 403, f"Expected 403 for non-admin: {path}, got {resp.status_code}"


def test_global_admin_analytics_insights_admin_allowed() -> None:
    base = _assert_base_url()
    admin = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    allowed_paths = [
        "/api/admin/analytics",
        "/api/admin/insights/dashboard",
    ]
    for path in allowed_paths:
        resp = admin.get(f"{base}{path}", timeout=30)
        assert resp.status_code in {200, 404, 422}, f"Admin should not be RBAC-blocked at {path}: {resp.status_code}"


def test_global_admin_non_analytics_routes_unchanged() -> None:
    base = _assert_base_url()
    non_admin = _login(NON_ADMIN_EMAIL, NON_ADMIN_PASSWORD)
    admin = _login(ADMIN_EMAIL, ADMIN_PASSWORD)

    non_admin_resp = non_admin.get(f"{base}/api/admin/platform-health", timeout=30)
    assert non_admin_resp.status_code in {401, 403, 404}, "Non-admin should not gain admin route access"

    admin_resp = admin.get(f"{base}/api/admin/platform-health", timeout=30)
    assert admin_resp.status_code != 403, "Admin unexpectedly blocked from admin route"
