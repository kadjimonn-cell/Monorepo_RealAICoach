"""Multi-platform API v1 architecture — contract, versioning and regression tests.

Validates:
- /api/v1/* alias transparently maps to /api/* (backward compatible)
- X-API-Version response header on versioned requests
- public client bootstrap handshake payload contract
- admin-gated OpenAPI docs (401 unauth / 200 admin)
- native-token auth channel via X-Client-Platform header
- contracts/v1/*.contract.json structural validity
- legacy unversioned routes unaffected (zero regression)
"""

import json
import os
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts" / "v1"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def _admin_login(extra_headers=None):
    headers = {**CSRF_HEADERS, **(extra_headers or {})}
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=headers,
        timeout=30,
    )
    return resp


class TestV1VersioningShim:
    def test_legacy_health_unchanged(self):
        resp = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert resp.status_code == 200
        assert resp.json().get("status") == "healthy"

    def test_v1_health_alias(self):
        resp = requests.get(f"{BASE_URL}/api/v1/health", timeout=15)
        assert resp.status_code == 200
        assert resp.json().get("status") == "healthy"

    def test_v1_response_carries_version_header(self):
        resp = requests.get(f"{BASE_URL}/api/v1/health", timeout=15)
        assert resp.headers.get("X-API-Version") == "1"

    def test_legacy_response_has_no_version_header(self):
        resp = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert resp.headers.get("X-API-Version") is None

    def test_v1_auth_gate_still_enforced(self):
        resp = requests.get(f"{BASE_URL}/api/v1/admin/users", timeout=15)
        assert resp.status_code in (401, 403)

    def test_v1_public_i18n_languages(self):
        resp = requests.get(f"{BASE_URL}/api/v1/i18n/languages", timeout=15)
        assert resp.status_code == 200


class TestClientBootstrap:
    REQUIRED_FIELDS = [
        "api_version", "base_paths", "platforms", "auth",
        "capabilities", "i18n", "theming", "docs",
    ]

    def test_bootstrap_public_versioned(self):
        resp = requests.get(f"{BASE_URL}/api/v1/client/bootstrap", timeout=15)
        assert resp.status_code == 200
        body = resp.json()
        for field in self.REQUIRED_FIELDS:
            assert field in body, f"bootstrap missing field: {field}"
        assert body["api_version"] == "v1"

    def test_bootstrap_public_legacy_path(self):
        resp = requests.get(f"{BASE_URL}/api/client/bootstrap", timeout=15)
        assert resp.status_code == 200

    def test_bootstrap_auth_capability_map(self):
        body = requests.get(f"{BASE_URL}/api/v1/client/bootstrap", timeout=15).json()
        auth = body["auth"]
        assert auth["native_token_header"] == "X-Client-Platform"
        assert "android" in auth["native_token_values"]
        assert "ios" in auth["native_token_values"]
        assert auth["refresh_tokens_supported"] is True
        assert auth["mfa_supported"] is True
        assert set(auth["oauth_providers"]) == {"google", "microsoft", "apple"}

    def test_bootstrap_echoes_native_platform(self):
        body = requests.get(
            f"{BASE_URL}/api/v1/client/bootstrap",
            headers={"X-Client-Platform": "android"},
            timeout=15,
        ).json()
        assert body["client_platform"] == "android"

    def test_bootstrap_theming_contracts(self):
        body = requests.get(f"{BASE_URL}/api/v1/client/bootstrap", timeout=15).json()
        assert body["theming"]["app_theme_contract"] == "v2-light-dark"
        assert body["theming"]["email_theme_contract"] == "v7-light-dark"


class TestApiDocs:
    def test_openapi_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/api/v1/openapi.json", timeout=15)
        assert resp.status_code in (401, 403)

    def test_docs_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/api/v1/docs", timeout=15)
        assert resp.status_code in (401, 403)

    def test_openapi_accessible_to_admin(self):
        login = _admin_login({"X-Client-Platform": "native"})
        assert login.status_code == 200, f"admin login failed: {login.text[:300]}"
        token = login.json().get("session_token")
        assert token, "native admin login must return session_token in body"
        resp = requests.get(
            f"{BASE_URL}/api/v1/openapi.json",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        assert resp.status_code == 200
        schema = resp.json()
        assert schema.get("openapi", "").startswith("3")
        assert schema.get("info", {}).get("version") == "1.0.0"


class TestNativeAuthChannel:
    def test_web_login_does_not_leak_tokens_in_body(self):
        resp = _admin_login()
        assert resp.status_code == 200
        body = resp.json()
        assert "session_token" not in body
        assert "refresh_token" not in body

    def test_native_login_returns_tokens_in_body(self):
        resp = _admin_login({"X-Client-Platform": "ios"})
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("session_token")
        assert body.get("refresh_token")

    def test_native_bearer_token_grants_session_access(self):
        token = _admin_login({"X-Client-Platform": "android"}).json()["session_token"]
        resp = requests.get(
            f"{BASE_URL}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert resp.status_code == 200
        assert resp.json().get("email") == ADMIN_EMAIL


class TestContractFiles:
    EXPECTED_CONTRACTS = [
        "auth.contract.json",
        "users.contract.json",
        "subscriptions.contract.json",
        "client.contract.json",
    ]

    @pytest.mark.parametrize("name", EXPECTED_CONTRACTS)
    def test_contract_file_valid(self, name):
        path = CONTRACTS_DIR / name
        assert path.exists(), f"missing contract: {name}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == "v1"
        assert data["module"]
        assert isinstance(data["endpoints"], list) and data["endpoints"]
        for ep in data["endpoints"]:
            assert ep["path"].startswith("/api/")
            assert ep["method"] in {"get", "post", "put", "patch", "delete"}

    def test_client_contract_matches_live_response(self):
        contract = json.loads((CONTRACTS_DIR / "client.contract.json").read_text())
        endpoint = contract["endpoints"][0]
        body = requests.get(f"{BASE_URL}{endpoint['path']}", timeout=15).json()
        for field in endpoint["response_contract"]["required_fields"]:
            assert field in body, f"live bootstrap missing contract field: {field}"


class TestBackwardCompatRegression:
    def test_legacy_flappy_bird_route_intact(self):
        resp = requests.get(f"{BASE_URL}/api/flappy-bird/leaderboard", timeout=15)
        assert resp.status_code in (200, 401)

    def test_legacy_features_registry_intact(self):
        resp = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert resp.status_code == 200

    def test_v1_flappy_bird_alias_parity(self):
        legacy = requests.get(f"{BASE_URL}/api/flappy-bird/leaderboard", timeout=15)
        v1 = requests.get(f"{BASE_URL}/api/v1/flappy-bird/leaderboard", timeout=15)
        assert legacy.status_code == v1.status_code
