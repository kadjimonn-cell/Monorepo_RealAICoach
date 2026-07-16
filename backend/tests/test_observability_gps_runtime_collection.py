import os

import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _admin_session() -> requests.Session:
    """Create an authenticated admin session using cookie-based auth."""
    session = requests.Session()
    login_res = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=20,
    )
    assert login_res.status_code == 200, f"Admin login failed: {login_res.status_code} {login_res.text[:300]}"
    return session


def test_observability_overview_includes_gps_runtime_health_shape():
    session = _admin_session()
    res = session.get(f"{BASE_URL}/api/admin/observability/overview", timeout=20)
    assert res.status_code == 200, f"overview failed: {res.status_code} {res.text[:300]}"
    payload = res.json()

    gps_health = payload.get("gps_health")
    assert isinstance(gps_health, dict), "gps_health should be an object"

    # Collection alignment guard: route should expose runtime incident shape fields.
    if gps_health:
        assert "component" in gps_health, "gps_health missing component"
        assert "error" in gps_health, "gps_health missing error"
        assert "created_at" in gps_health, "gps_health missing created_at"
        assert gps_health.get("severity") == "critical", "gps_health severity normalization missing"
