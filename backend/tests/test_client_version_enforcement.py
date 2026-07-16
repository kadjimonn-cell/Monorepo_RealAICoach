"""Client version enforcement — policy, middleware gate and admin management tests."""

import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

CSRF = {"X-Requested-With": "XMLHttpRequest"}
PUBLIC_PROBE = f"{BASE_URL}/api/v1/i18n/languages"
POLICY_URL = f"{BASE_URL}/api/v1/admin/client-version-policy"


def _login(email, password):
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers={**CSRF, "X-Client-Platform": "native"},
        timeout=30,
    )
    assert resp.status_code == 200, f"login failed for {email}: {resp.text[:200]}"
    return resp.json()["session_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE_EMAIL, FREE_PASSWORD)


class TestEnforcementGate:
    def test_web_requests_unaffected(self):
        assert requests.get(PUBLIC_PROBE, timeout=15).status_code == 200

    def test_native_without_version_header_allowed(self):
        resp = requests.get(PUBLIC_PROBE, headers={"X-Client-Platform": "android"}, timeout=15)
        assert resp.status_code == 200

    def test_native_outdated_version_blocked_426(self):
        resp = requests.get(
            PUBLIC_PROBE,
            headers={"X-Client-Platform": "android", "X-App-Version": "0.0.1"},
            timeout=15,
        )
        assert resp.status_code == 426
        body = resp.json()
        assert body["code"] == "CLIENT_UPDATE_REQUIRED"
        assert body["platform"] == "android"
        assert body["min_supported_version"]
        assert "latest_version" in body and "update_url" in body
        assert resp.headers.get("X-API-Version") == "1"

    def test_native_current_version_allowed(self):
        resp = requests.get(
            PUBLIC_PROBE,
            headers={"X-Client-Platform": "ios", "X-App-Version": "1.0.0"},
            timeout=15,
        )
        assert resp.status_code == 200

    def test_malformed_version_fails_open(self):
        resp = requests.get(
            PUBLIC_PROBE,
            headers={"X-Client-Platform": "android", "X-App-Version": "not-a-version"},
            timeout=15,
        )
        assert resp.status_code == 200

    def test_bootstrap_exempt_for_outdated_client(self):
        resp = requests.get(
            f"{BASE_URL}/api/v1/client/bootstrap",
            headers={"X-Client-Platform": "android", "X-App-Version": "0.0.1"},
            timeout=15,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["version_enforcement"]["blocked_status"] == 426
        assert body["version_enforcement"]["blocked_code"] == "CLIENT_UPDATE_REQUIRED"
        assert body["platforms"]["android"]["min_supported_version"]

    def test_health_exempt_for_outdated_client(self):
        resp = requests.get(
            f"{BASE_URL}/api/health",
            headers={"X-Client-Platform": "ios", "X-App-Version": "0.0.1"},
            timeout=15,
        )
        assert resp.status_code == 200

    def test_legacy_unversioned_path_also_enforced(self):
        resp = requests.get(
            f"{BASE_URL}/api/i18n/languages",
            headers={"X-Client-Platform": "expo", "X-App-Version": "0.0.1"},
            timeout=15,
        )
        assert resp.status_code == 426
        assert resp.headers.get("X-API-Version") is None


class TestAdminPolicyManagement:
    def test_policy_requires_auth(self):
        assert requests.get(POLICY_URL, timeout=15).status_code in (401, 403)

    def test_policy_forbidden_for_non_admin(self, free_token):
        resp = requests.get(
            POLICY_URL, headers={"Authorization": f"Bearer {free_token}"}, timeout=15
        )
        assert resp.status_code == 403

    def test_admin_reads_policy(self, admin_token):
        resp = requests.get(
            POLICY_URL, headers={"Authorization": f"Bearer {admin_token}"}, timeout=15
        )
        assert resp.status_code == 200
        body = resp.json()
        for key in ("android", "ios", "expo", "default"):
            assert key in body["platforms"]
        assert body["enforcement"]["version_header"] == "X-App-Version"

    def test_put_unknown_platform_rejected(self, admin_token):
        resp = requests.put(
            f"{POLICY_URL}/windows",
            json={"min_supported_version": "2.0.0"},
            headers={**CSRF, "Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert resp.status_code == 400

    def test_put_invalid_semver_rejected(self, admin_token):
        resp = requests.put(
            f"{POLICY_URL}/android",
            json={"min_supported_version": "banana"},
            headers={**CSRF, "Authorization": f"Bearer {admin_token}"},
            timeout=15,
        )
        assert resp.status_code == 400

    def test_policy_update_lifecycle(self, admin_token):
        auth = {**CSRF, "Authorization": f"Bearer {admin_token}"}
        native = {"X-Client-Platform": "android", "X-App-Version": "1.5.0"}
        try:
            resp = requests.put(
                f"{POLICY_URL}/android",
                json={"min_supported_version": "2.0.0", "latest_version": "2.1.0",
                      "update_url": "https://play.google.com/store/apps/details?id=app.realaicoach"},
                headers=auth, timeout=15,
            )
            assert resp.status_code == 200
            assert resp.json()["policy"]["min_supported_version"] == "2.0.0"

            blocked = requests.get(PUBLIC_PROBE, headers=native, timeout=15)
            assert blocked.status_code == 426
            body = blocked.json()
            assert body["min_supported_version"] == "2.0.0"
            assert body["latest_version"] == "2.1.0"
            assert "play.google.com" in body["update_url"]

            ok = requests.get(
                PUBLIC_PROBE,
                headers={"X-Client-Platform": "android", "X-App-Version": "2.1.0"},
                timeout=15,
            )
            assert ok.status_code == 200

            resp = requests.put(
                f"{POLICY_URL}/android", json={"enforced": False}, headers=auth, timeout=15
            )
            assert resp.status_code == 200
            disabled = requests.get(PUBLIC_PROBE, headers=native, timeout=15)
            assert disabled.status_code == 200

            boot = requests.get(f"{BASE_URL}/api/v1/client/bootstrap", timeout=15).json()
            assert boot["platforms"]["android"]["min_supported_version"] == "2.0.0"
            assert boot["platforms"]["android"]["enforced"] is False
        finally:
            restore = requests.put(
                f"{POLICY_URL}/android",
                json={"min_supported_version": "1.0.0", "latest_version": "1.0.0",
                      "update_url": "", "enforced": True},
                headers=auth, timeout=15,
            )
            assert restore.status_code == 200

    def test_state_restored_after_lifecycle(self):
        resp = requests.get(
            PUBLIC_PROBE,
            headers={"X-Client-Platform": "android", "X-App-Version": "1.0.0"},
            timeout=15,
        )
        assert resp.status_code == 200
