"""DEPRECATED: moved to governance_retirement package.

Use:
- tests/governance_retirement/test_governance_endpoints.py
- tests/governance_retirement/test_phase_rollout_and_hard_delete.py
"""

import pytest


pytest.skip("Deprecated duplicate retirement suite; replaced by governance_retirement package", allow_module_level=True)

import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _assert_base_url() -> str:
    assert BASE_URL, "REACT_APP_BACKEND_URL is required for Phase 2 retirement tests"
    return str(BASE_URL).rstrip("/")


def _set_retirement_controls(session: requests.Session, payload: dict) -> requests.Response:
    base = _assert_base_url()
    return session.post(
        f"{base}/api/videos/admin/legacy-wrapper-retirement-controls",
        json=payload,
        timeout=45,
    )


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


@pytest.fixture(scope="module", autouse=True)
def reset_wrapper_retirement_controls():
    """No-op fixture after hard-delete route removal."""
    yield


class TestAdminRetirementEndpoints:
    """Test admin retirement readiness and controls endpoints"""

    def test_admin_readiness_endpoint_requires_admin(
        self, free_session: requests.Session, admin_session: requests.Session
    ):
        """GET /api/videos/admin/legacy-wrapper-retirement-readiness requires admin"""
        base = _assert_base_url()

        # Free user should get 403
        free_resp = free_session.get(
            f"{base}/api/videos/admin/legacy-wrapper-retirement-readiness", timeout=30
        )
        assert free_resp.status_code == 403, f"Expected 403 for free user, got {free_resp.status_code}"

        # Admin should get 200
        admin_resp = admin_session.get(
            f"{base}/api/videos/admin/legacy-wrapper-retirement-readiness", timeout=30
        )
        assert admin_resp.status_code == 200, f"Admin readiness failed: {admin_resp.text}"
        data = admin_resp.json()
        assert "family_readiness" in data
        assert isinstance(data.get("family_readiness"), list)
        assert "controls" in data
        assert "retirement_phase" in data

    def test_admin_controls_endpoint_requires_admin(
        self, free_session: requests.Session, admin_session: requests.Session
    ):
        """POST /api/videos/admin/legacy-wrapper-retirement-controls requires admin"""
        base = _assert_base_url()

        # Free user should get 403
        free_resp = free_session.post(
            f"{base}/api/videos/admin/legacy-wrapper-retirement-controls",
            json={"legacy_retirement_enabled": False},
            timeout=30,
        )
        assert free_resp.status_code == 403, f"Expected 403 for free user, got {free_resp.status_code}"

        # Admin should be able to set controls
        admin_resp = _set_retirement_controls(
            admin_session,
            {
                "legacy_retirement_enabled": False,
                "retirement_phase": "observe",
                "retirement_force_apply": False,
            },
        )
        assert admin_resp.status_code == 200, f"Admin controls failed: {admin_resp.text}"
        data = admin_resp.json()
        assert data.get("success") is True
        assert "controls" in data
        assert "family_readiness" in data

    def test_admin_removal_endpoints_exist(self, free_session: requests.Session, admin_session: requests.Session):
        """Dedicated governance module exposes removal readiness + hard delete endpoints"""
        base = _assert_base_url()

        free_readiness = free_session.get(
            f"{base}/api/videos/admin/legacy-wrapper-removal-readiness",
            timeout=30,
        )
        assert free_readiness.status_code == 403

        admin_readiness = admin_session.get(
            f"{base}/api/videos/admin/legacy-wrapper-removal-readiness",
            timeout=30,
        )
        assert admin_readiness.status_code == 200

        bad_hard_delete = free_session.post(
            f"{base}/api/videos/admin/legacy-wrapper-hard-delete",
            json={"lookback_hours": 168, "route_families": ["audio_studio"]},
            timeout=30,
        )
        assert bad_hard_delete.status_code == 403


class TestPhase1AudioOnlyRetirement:
    """Test Phase 1: Audio wrappers retired, podcasts remain active"""

    def test_phase1_audio_wrapper_retirement_blocks_legacy_audio_only(
        self, free_session: requests.Session, admin_session: requests.Session
    ):
        """Phase 1: /api/videos/audio-studio/* returns 410, podcasts legacy remains active"""
        base = _assert_base_url()

        # Enable phase1 retirement (audio only)
        enable = _set_retirement_controls(
            admin_session,
            {
                "legacy_retirement_enabled": True,
                "retirement_phase": "phase1_audio_wrappers",
                "retirement_force_apply": True,
                "retirement_gate_max_events": 0,
                "retirement_gate_max_active_users": 0,
            },
        )
        assert enable.status_code == 200, f"Enable retirement failed: {enable.text}"

        # Legacy audio-studio should be retired (410 pre-delete or 404 post-delete)
        retired_audio = free_session.get(
            f"{base}/api/videos/audio-studio/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert retired_audio.status_code in {404, 410}, f"Audio legacy wrapper should be retired: {retired_audio.status_code}"
        if retired_audio.status_code == 410:
            retired_data = retired_audio.json()
            assert "detail" in retired_data
            detail = retired_data.get("detail", {})
            assert detail.get("retirement_mode") == "hard_retired"
            assert detail.get("route_family") == "audio_studio"

        # Legacy podcasts may remain active (200) before hard-delete or retired after hard-delete
        podcasts_legacy = free_session.get(
            f"{base}/api/videos/podcasts/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert podcasts_legacy.status_code in {200, 404, 410}, f"Unexpected podcasts legacy status: {podcasts_legacy.status_code}"

        # Canonical v2 audio-studio should still work
        audio_v2 = free_session.get(
            f"{base}/api/audio-studio/v2/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert audio_v2.status_code == 200, f"Canonical v2 audio-studio should stay active: {audio_v2.status_code}"

        # Canonical v2 podcasts should still work
        podcasts_v2 = free_session.get(
            f"{base}/api/podcasts/v2/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert podcasts_v2.status_code == 200, f"Canonical v2 podcasts should stay active: {podcasts_v2.status_code}"




class TestPhase2AudioPodcastsRetirement:
    """Test Phase 2: Both audio and podcasts wrappers retired"""

    def test_phase2_audio_podcasts_wrapper_retirement_blocks_both(
        self, free_session: requests.Session, admin_session: requests.Session
    ):
        """Phase 2: Both /api/videos/audio-studio/* and /api/videos/podcasts/* return 410"""
        base = _assert_base_url()

        # Enable phase2 retirement (audio + podcasts)
        enable = _set_retirement_controls(
            admin_session,
            {
                "legacy_retirement_enabled": True,
                "retirement_phase": "phase2_audio_podcasts_wrappers",
                "retirement_force_apply": True,
                "retirement_gate_max_events": 0,
                "retirement_gate_max_active_users": 0,
            },
        )
        assert enable.status_code == 200, f"Enable phase2 retirement failed: {enable.text}"

        # Legacy audio-studio should be retired (410 pre-delete or 404 post-delete)
        retired_audio = free_session.get(
            f"{base}/api/videos/audio-studio/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert retired_audio.status_code in {404, 410}, f"Audio legacy wrapper should be retired in phase2: {retired_audio.status_code}"

        # Legacy podcasts should also be retired (410 pre-delete or 404 post-delete)
        retired_podcasts = free_session.get(
            f"{base}/api/videos/podcasts/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert retired_podcasts.status_code in {404, 410}, f"Podcasts legacy wrapper should be retired in phase2: {retired_podcasts.status_code}"
        if retired_podcasts.status_code == 410:
            retired_data = retired_podcasts.json()
            assert "detail" in retired_data
            detail = retired_data.get("detail", {})
            assert detail.get("retirement_mode") == "hard_retired"
            assert detail.get("route_family") == "podcasts"

        # Canonical v2 endpoints should still work
        audio_v2 = free_session.get(
            f"{base}/api/audio-studio/v2/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert audio_v2.status_code == 200, f"Canonical v2 audio-studio should stay active: {audio_v2.status_code}"

        podcasts_v2 = free_session.get(
            f"{base}/api/podcasts/v2/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert podcasts_v2.status_code == 200, f"Canonical v2 podcasts should stay active: {podcasts_v2.status_code}"




class TestCanonicalV2EndpointsAlwaysWork:
    """Test that canonical v2 endpoints work regardless of retirement state"""

    def test_audio_studio_v2_bootstrap_always_works(self, free_session: requests.Session):
        """GET /api/audio-studio/v2/bootstrap always returns 200"""
        base = _assert_base_url()
        response = free_session.get(
            f"{base}/api/audio-studio/v2/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert response.status_code == 200, f"audio-studio v2 bootstrap failed: {response.text}"
        data = response.json()
        assert data.get("feature_id") == "watch-videos-audio-studio"
        assert isinstance(data.get("catalog"), list)

    def test_podcasts_v2_bootstrap_always_works(self, free_session: requests.Session):
        """GET /api/podcasts/v2/bootstrap always returns 200"""
        base = _assert_base_url()
        response = free_session.get(
            f"{base}/api/podcasts/v2/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert response.status_code == 200, f"podcasts v2 bootstrap failed: {response.text}"
        data = response.json()
        assert data.get("feature_id") == "watch-videos-my-podcasts"
        assert isinstance(data.get("catalog"), list)


class TestResetToObserveRestoresLegacyAccess:
    """Legacy wrappers are hard-deleted and should remain retired after phase completion"""

    def test_reset_to_observe_keeps_legacy_wrappers_retired_after_hard_delete(
        self, free_session: requests.Session, admin_session: requests.Session
    ):
        """After hard-delete, observe reset cannot restore removed wrapper routes"""
        base = _assert_base_url()

        # First enable phase2 retirement
        enable = _set_retirement_controls(
            admin_session,
            {
                "legacy_retirement_enabled": True,
                "retirement_phase": "phase2_audio_podcasts_wrappers",
                "retirement_force_apply": True,
            },
        )
        assert enable.status_code == 200

        # Verify both are retired before reset
        audio_retired = free_session.get(
            f"{base}/api/videos/audio-studio/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert audio_retired.status_code in {404, 410}

        podcasts_retired = free_session.get(
            f"{base}/api/videos/podcasts/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert podcasts_retired.status_code in {404, 410}

        # Reset to observe mode
        reset = _set_retirement_controls(
            admin_session,
            {
                "legacy_retirement_enabled": False,
                "retirement_phase": "observe",
                "retirement_force_apply": False,
            },
        )
        assert reset.status_code == 200, f"Reset to observe failed: {reset.text}"

        # Verify legacy wrappers remain retired after reset
        audio_restored = free_session.get(
            f"{base}/api/videos/audio-studio/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert audio_restored.status_code in {404, 410}, f"Audio legacy wrapper should remain retired: {audio_restored.status_code}"

        podcasts_restored = free_session.get(
            f"{base}/api/videos/podcasts/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert podcasts_restored.status_code in {404, 410}, f"Podcasts legacy wrapper should remain retired: {podcasts_restored.status_code}"


class TestSportsRetirementNoRegression:
    """Test that Feature 30 sports retirement state is not affected"""

    def test_sports_legacy_wrappers_remain_retired(self, free_session: requests.Session):
        """Legacy /api/videos/sports/* wrappers should remain retired (404/403)"""
        base = _assert_base_url()

        # Legacy sports bootstrap should be retired
        sports_legacy = free_session.get(
            f"{base}/api/videos/sports/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        # Should be 404 (not found) or 403 (forbidden) - sports wrappers were retired in previous step
        assert sports_legacy.status_code in {404, 403, 410}, f"Sports legacy wrapper should be retired: {sports_legacy.status_code}"

    def test_sports_v2_canonical_routes_work(self, free_session: requests.Session):
        """Canonical /api/sports/v2/* routes should work"""
        base = _assert_base_url()

        # Sports v2 bootstrap should work
        sports_v2 = free_session.get(
            f"{base}/api/sports/v2/bootstrap", params={"tz": "UTC"}, timeout=45
        )
        assert sports_v2.status_code == 200, f"Sports v2 bootstrap failed: {sports_v2.text}"
        data = sports_v2.json()
        assert data.get("feature_id") == "watch-videos-sports"
        assert isinstance(data.get("catalog"), list)


class TestRetirementControlsContract:
    """Test retirement controls API contract"""

    def test_readiness_endpoint_returns_expected_structure(self, admin_session: requests.Session):
        """Readiness endpoint returns expected structure"""
        base = _assert_base_url()
        response = admin_session.get(
            f"{base}/api/videos/admin/legacy-wrapper-retirement-readiness",
            params={"lookback_hours": 168},
            timeout=45,
        )
        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "generated_at" in data
        assert "feature_number" in data
        assert data.get("feature_number") == 28
        assert "feature_id" in data
        assert data.get("feature_id") == "watch-videos-audio-podcasts"
        assert "lookback_hours" in data
        assert "controls" in data
        assert "retirement_phase" in data
        assert "target_route_families" in data
        assert "target_phase_gate_ready" in data
        assert "recommended_phase" in data
        assert "family_readiness" in data

        # Verify family_readiness structure
        family_readiness = data.get("family_readiness", [])
        assert len(family_readiness) == 2  # audio_studio and podcasts
        for family in family_readiness:
            assert "route_family" in family
            assert "lookback_hours" in family
            assert "total_events" in family
            assert "active_users" in family
            assert "gate_thresholds" in family
            assert "gate_met" in family
            assert "readiness_score" in family

    def test_controls_endpoint_returns_expected_structure(self, admin_session: requests.Session):
        """Controls endpoint returns expected structure"""
        _assert_base_url()
        response = _set_retirement_controls(
            admin_session,
            {
                "legacy_retirement_enabled": False,
                "retirement_phase": "observe",
                "retirement_force_apply": False,
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert data.get("success") is True
        assert "generated_at" in data
        assert "controls" in data
        assert "family_readiness" in data

        controls = data.get("controls", {})
        assert "legacy_retirement_enabled" in controls
        assert "retirement_phase" in controls
        assert "retired_legacy_route_families" in controls
