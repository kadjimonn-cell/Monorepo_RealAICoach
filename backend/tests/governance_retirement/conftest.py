import os

import pytest
import requests


FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def assert_base_url() -> str:
    base_url = os.environ.get("REACT_APP_BACKEND_URL")
    assert base_url, "REACT_APP_BACKEND_URL is required for governance retirement tests"
    return str(base_url).rstrip("/")


def _login_session(email: str, password: str) -> requests.Session:
    base = assert_base_url()
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    login = session.post(
        f"{base}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert login.status_code == 200, f"Login failed for {email}: {login.text}"
    return session


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    return _login_session(FREE_USER_EMAIL, FREE_USER_PASSWORD)


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login_session(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def base_url() -> str:
    return assert_base_url()


def set_retirement_controls(session: requests.Session, payload: dict) -> requests.Response:
    base = assert_base_url()
    return session.post(
        f"{base}/api/videos/admin/legacy-wrapper-retirement-controls",
        json=payload,
        timeout=45,
    )


def current_user_id(session: requests.Session) -> str:
    base = assert_base_url()
    me = session.get(f"{base}/api/auth/me", timeout=30)
    assert me.status_code == 200, f"/auth/me failed: {me.text}"
    return str((me.json() or {}).get("user_id") or "").strip()


@pytest.fixture(scope="module")
def set_controls_fn():
    return set_retirement_controls


@pytest.fixture(scope="module")
def current_user_id_fn():
    return current_user_id
