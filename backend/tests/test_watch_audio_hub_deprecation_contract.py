"""
Test suite for watch_audio_hub monolith deprecation/deletion verification.

Contracts verified:
1. Legacy wrappers under /api/videos/audio-studio/*, /api/videos/podcasts/*, /api/videos/sports/* return 404
2. Canonical v2 endpoints remain healthy: /api/audio-studio/v2/bootstrap, /api/podcasts/v2/bootstrap, /api/sports/v2/bootstrap
3. Admin analytics ACL lock: non-admin blocked (403), admin allowed (200)
4. Module extraction: services import from watch_audio_shared instead of watch_audio_hub
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def free_user_session():
    """Login as free user and return session with cookies."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Free user login failed: {response.status_code}")
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session with cookies."""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    return session


class TestLegacyWrapperRetirement:
    """Legacy wrappers under /api/videos/* must return 404."""

    @pytest.mark.parametrize("endpoint", [
        "/api/videos/audio-studio/bootstrap",
        "/api/videos/podcasts/bootstrap",
        "/api/videos/sports/bootstrap",
    ])
    def test_legacy_wrapper_returns_404(self, free_user_session, endpoint):
        """Legacy wrapper endpoints should return 404 (retired)."""
        response = free_user_session.get(f"{BASE_URL}{endpoint}")
        assert response.status_code == 404, f"Expected 404 for {endpoint}, got {response.status_code}"
        # Verify it's a proper 404 response
        data = response.json()
        assert "detail" in data or "error" in data or "code" in data


class TestCanonicalV2Endpoints:
    """Canonical v2 endpoints must remain healthy (200)."""

    @pytest.mark.parametrize("endpoint,expected_keys", [
        ("/api/audio-studio/v2/bootstrap", ["feature_id", "surface", "quota"]),
        ("/api/podcasts/v2/bootstrap", ["feature_id", "surface", "quota"]),
        ("/api/sports/v2/bootstrap", ["feature_id", "surface", "quota"]),
    ])
    def test_canonical_v2_bootstrap_healthy(self, free_user_session, endpoint, expected_keys):
        """Canonical v2 bootstrap endpoints should return 200 with expected structure."""
        response = free_user_session.get(f"{BASE_URL}{endpoint}")
        assert response.status_code == 200, f"Expected 200 for {endpoint}, got {response.status_code}"
        data = response.json()
        for key in expected_keys:
            assert key in data, f"Missing key '{key}' in response for {endpoint}"


class TestAdminAnalyticsACL:
    """Admin analytics endpoints must enforce ACL: non-admin blocked (403), admin allowed (200)."""

    ADMIN_ENDPOINTS = [
        "/api/sports/v2/admin/conversion-dashboard",
        "/api/audio-studio/v2/admin/conversion-dashboard",
        "/api/podcasts/v2/admin/conversion-dashboard",
        "/api/videos/admin/legacy-wrapper-retirement-readiness",
    ]

    @pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
    def test_free_user_blocked_from_admin_endpoints(self, free_user_session, endpoint):
        """Free user should get 403 on admin analytics endpoints."""
        response = free_user_session.get(f"{BASE_URL}{endpoint}")
        assert response.status_code == 403, f"Expected 403 for free user on {endpoint}, got {response.status_code}"
        data = response.json()
        # Verify it's an admin access denied response
        assert any(key in data for key in ["error", "detail", "message"]), f"Missing error info in 403 response for {endpoint}"

    @pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
    def test_admin_can_access_admin_endpoints(self, admin_session, endpoint):
        """Admin should get 200 on admin analytics endpoints."""
        response = admin_session.get(f"{BASE_URL}{endpoint}")
        assert response.status_code == 200, f"Expected 200 for admin on {endpoint}, got {response.status_code}"
        data = response.json()
        # Verify response has meaningful data
        assert isinstance(data, dict), f"Expected dict response for {endpoint}"
        assert len(data) > 0, f"Expected non-empty response for {endpoint}"


class TestModuleExtractionContract:
    """Services must import from watch_audio_shared, not watch_audio_hub."""

    def test_no_watch_audio_hub_imports_in_routes(self):
        """No routes should import from watch_audio_hub."""
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "from.*watch_audio_hub\\|import.*watch_audio_hub", "/app/backend/routes/"],
            capture_output=True,
            text=True
        )
        # grep returns 1 if no matches found (which is what we want)
        assert result.returncode == 1, f"Found watch_audio_hub imports: {result.stdout}"

    def test_watch_audio_shared_imports_exist(self):
        """Services should import from watch_audio_shared."""
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "from.*watch_audio_shared\\|import.*watch_audio_shared", "/app/backend/routes/"],
            capture_output=True,
            text=True
        )
        # grep returns 0 if matches found
        assert result.returncode == 0, "No watch_audio_shared imports found"
        # Verify key service files have the import
        assert "audio_studio_v2" in result.stdout, "audio_studio_v2 should import from watch_audio_shared"
        assert "podcasts_v2" in result.stdout, "podcasts_v2 should import from watch_audio_shared"

    def test_watch_audio_hub_is_tombstone(self):
        """watch_audio_hub.py should be a deprecated tombstone."""
        with open("/app/backend/routes/watch_audio_hub.py", "r") as f:
            content = f.read()
        assert "Deprecated" in content or "deprecated" in content, "watch_audio_hub.py should be marked as deprecated"
        assert "tombstone" in content.lower(), "watch_audio_hub.py should be a tombstone"


class TestRouterRegistration:
    """Verify router registration in miniapps.py."""

    def test_watch_audio_shared_router_registered(self):
        """watch_audio_shared_router should be registered in miniapps.py."""
        with open("/app/backend/domains/miniapps.py", "r") as f:
            content = f.read()
        assert "watch_audio_shared_router" in content, "watch_audio_shared_router should be registered"
        assert "from routes.watch_audio_shared import router as watch_audio_shared_router" in content, \
            "watch_audio_shared_router import should exist"

    def test_v2_routers_registered(self):
        """v2 routers should be registered in miniapps.py."""
        with open("/app/backend/domains/miniapps.py", "r") as f:
            content = f.read()
        assert "audio_studio_v2_router" in content, "audio_studio_v2_router should be registered"
        assert "podcasts_v2_router" in content, "podcasts_v2_router should be registered"
        assert "sports_v2_router" in content, "sports_v2_router should be registered"
