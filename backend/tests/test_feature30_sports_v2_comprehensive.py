"""Feature 30 Sports v2 Comprehensive E2E Tests

Tests all v2 backend endpoints for authenticated free users and admin-only gating:
- /api/sports/v2/bootstrap
- /api/sports/v2/play
- /api/sports/v2/daily-drop-inbox
- /api/sports/v2/daily-drop-inbox/mark-listened
- /api/sports/v2/continue-watching
- /api/sports/v2/live-now
- /api/sports/v2/admin/conversion-dashboard (admin-only)
- /api/sports/v2/admin/source-health (admin-only)
"""

import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _assert_base_url() -> str:
    assert BASE_URL, "REACT_APP_BACKEND_URL is required for Feature 30 v2 E2E tests"
    return str(BASE_URL).rstrip("/")


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    """Authenticated session for free user"""
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
    """Authenticated session for admin user"""
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


class TestFeature30V2FreeUserEndpoints:
    """Test all v2 endpoints accessible by authenticated free users"""

    def test_sports_v2_bootstrap_returns_200_with_contract(self, free_session: requests.Session):
        """Free user can access /api/sports/v2/bootstrap"""
        base = _assert_base_url()
        response = free_session.get(f"{base}/api/sports/v2/bootstrap", params={"tz": "UTC"}, timeout=45)
        assert response.status_code == 200, f"sports v2 bootstrap failed: {response.text}"
        
        data = response.json()
        assert data.get("feature_id") == "watch-videos-sports"
        assert isinstance(data.get("catalog"), list)
        assert isinstance(data.get("categories"), list)
        
        # Contract verification
        contract = data.get("contract", {})
        assert contract.get("no_manual_input") is True
        assert contract.get("no_upload") is True
        assert "sports_playability_summary" in contract.get("required_sections", [])

    def test_sports_v2_play_returns_200_for_free_item(self, free_session: requests.Session):
        """Free user can play free-tier sports items"""
        base = _assert_base_url()
        
        # Get a free item first
        bootstrap = free_session.get(f"{base}/api/sports/v2/bootstrap", params={"tz": "UTC"}, timeout=45)
        assert bootstrap.status_code == 200
        catalog = bootstrap.json().get("catalog", [])
        free_items = [item for item in catalog if str(item.get("min_plan", "free")).lower() == "free"]
        assert free_items, "No free-tier sports items found"
        
        item_id = free_items[0].get("item_id")
        response = free_session.post(
            f"{base}/api/sports/v2/play",
            json={"item_id": item_id, "listen_seconds": 5, "completed": False, "source": "pytest_comprehensive"},
            timeout=35,
        )
        # 200 = success, 429 = rate limited (acceptable)
        assert response.status_code in {200, 429}, f"Unexpected play status: {response.status_code}"

    def test_sports_v2_daily_drop_inbox_returns_200(self, free_session: requests.Session):
        """Free user can access /api/sports/v2/daily-drop-inbox"""
        base = _assert_base_url()
        response = free_session.get(f"{base}/api/sports/v2/daily-drop-inbox", timeout=30)
        assert response.status_code == 200, f"daily-drop-inbox failed: {response.text}"
        
        data = response.json()
        assert "items" in data
        assert isinstance(data.get("items"), list)

    def test_sports_v2_mark_listened_returns_200(self, free_session: requests.Session):
        """Free user can mark inbox items as listened"""
        base = _assert_base_url()
        
        # Get inbox items first
        inbox = free_session.get(f"{base}/api/sports/v2/daily-drop-inbox", timeout=30)
        assert inbox.status_code == 200
        items = inbox.json().get("items", [])
        
        if not items:
            pytest.skip("No inbox items to mark as listened")
        
        item_id = items[0].get("item_id")
        response = free_session.post(
            f"{base}/api/sports/v2/daily-drop-inbox/mark-listened",
            json={"item_id": item_id},
            timeout=30,
        )
        assert response.status_code == 200, f"mark-listened failed: {response.text}"
        assert response.json().get("ok") is True

    def test_sports_v2_continue_watching_returns_200(self, free_session: requests.Session):
        """Free user can access /api/sports/v2/continue-watching"""
        base = _assert_base_url()
        response = free_session.get(f"{base}/api/sports/v2/continue-watching", timeout=30)
        assert response.status_code == 200, f"continue-watching failed: {response.text}"
        
        data = response.json()
        assert data.get("surface") == "sports"
        assert "items" in data
        assert isinstance(data.get("items"), list)

    def test_sports_v2_live_now_returns_200(self, free_session: requests.Session):
        """Free user can access /api/sports/v2/live-now"""
        base = _assert_base_url()
        response = free_session.get(f"{base}/api/sports/v2/live-now", timeout=30)
        assert response.status_code == 200, f"live-now failed: {response.text}"
        
        data = response.json()
        assert data.get("surface") == "sports"
        assert "live_now" in data
        assert "coming_up" in data
        assert "counts" in data
        assert isinstance(data.get("live_now"), list)
        assert isinstance(data.get("coming_up"), list)

    def test_sports_v2_matchday_streak_returns_200(self, free_session: requests.Session):
        """Free user can access /api/sports/v2/matchday-streak"""
        base = _assert_base_url()
        response = free_session.get(f"{base}/api/sports/v2/matchday-streak", timeout=30)
        assert response.status_code == 200, f"matchday-streak failed: {response.text}"

        data = response.json()
        assert data.get("surface") == "sports"
        streak = data.get("matchday_streak") or {}
        assert "current_streak_days" in streak
        assert "comeback_prompt" in streak

    def test_sports_v2_prediction_challenges_and_submit(self, free_session: requests.Session):
        """Free user can view and submit prediction challenges"""
        base = _assert_base_url()
        rail = free_session.get(f"{base}/api/sports/v2/prediction-challenges", timeout=30)
        assert rail.status_code == 200, f"prediction-challenges failed: {rail.text}"
        rail_data = rail.json().get("prediction_challenge_rail") or {}
        challenges = rail_data.get("challenges") or []
        assert isinstance(challenges, list)
        assert challenges, "Expected at least one seeded prediction challenge"

        challenge = challenges[0]
        options = challenge.get("option_keys") or []
        assert options, "Expected challenge options"
        submit = free_session.post(
            f"{base}/api/sports/v2/prediction-challenges/submit",
            json={"challenge_id": challenge.get("challenge_id"), "option_key": options[0]},
            timeout=30,
        )
        assert submit.status_code == 200, f"prediction submit failed: {submit.text}"
        submit_data = submit.json()
        assert submit_data.get("ok") is True
        assert submit_data.get("challenge_id") == challenge.get("challenge_id")


class TestFeature30V2AdminOnlyEndpoints:
    """Test admin-only endpoints are correctly gated"""

    def test_free_user_blocked_from_admin_conversion_dashboard(self, free_session: requests.Session):
        """Free user gets 403 on /api/sports/v2/admin/conversion-dashboard"""
        base = _assert_base_url()
        response = free_session.get(
            f"{base}/api/sports/v2/admin/conversion-dashboard",
            params={"window_days": 7},
            timeout=35,
        )
        assert response.status_code == 403, f"Free user should be blocked: {response.text}"
        
        # Verify error response structure
        data = response.json()
        assert "error" in data or "detail" in data

    def test_free_user_blocked_from_admin_source_health(self, free_session: requests.Session):
        """Free user gets 403 on /api/sports/v2/admin/source-health"""
        base = _assert_base_url()
        response = free_session.get(f"{base}/api/sports/v2/admin/source-health", timeout=35)
        assert response.status_code == 403, f"Free user should be blocked: {response.text}"

    def test_admin_can_access_conversion_dashboard(self, admin_session: requests.Session):
        """Admin user can access /api/sports/v2/admin/conversion-dashboard"""
        base = _assert_base_url()
        response = admin_session.get(
            f"{base}/api/sports/v2/admin/conversion-dashboard",
            params={"window_days": 7},
            timeout=45,
        )
        assert response.status_code == 200, f"Admin dashboard failed: {response.text}"
        
        data = response.json()
        assert data.get("feature_id") == "sports"
        assert isinstance(data.get("kpis"), dict)
        assert isinstance(data.get("upgrade_funnel"), dict)
        assert isinstance(data.get("cohort_segmentation"), dict)
        
        # Verify KPI structure
        kpis = data.get("kpis", {})
        assert "active_viewers" in kpis
        assert "total_plays" in kpis
        assert "completion_rate_pct" in kpis
        
        # Verify cohort structure
        cohorts = data.get("cohort_segmentation", {})
        assert "geo_country" in cohorts
        assert "device_bucket" in cohorts
        assert "channel" in cohorts
        assert "league" in cohorts

    def test_admin_can_access_source_health(self, admin_session: requests.Session):
        """Admin user can access /api/sports/v2/admin/source-health"""
        base = _assert_base_url()
        response = admin_session.get(f"{base}/api/sports/v2/admin/source-health", timeout=45)
        assert response.status_code == 200, f"Admin source-health failed: {response.text}"
        
        data = response.json()
        assert "generated_at" in data
        assert "summary" in data
        assert "sources" in data
        assert isinstance(data.get("sources"), list)


class TestFeature30ACLEngineIntegration:
    """Verify ACL engine correctly handles sports v2 routes"""

    def test_free_patterns_include_sports_v2_user_endpoints(self):
        """Verify access_control_engine.py includes sports v2 free patterns"""
        from pathlib import Path
        source = Path('/app/backend/utils/access_control_engine.py').read_text(encoding='utf-8')
        
        # All user-facing sports v2 endpoints should be in FREE_PATTERNS
        assert r'^/api/sports/v2/bootstrap' in source
        assert r'^/api/sports/v2/play' in source
        assert r'^/api/sports/v2/daily-drop-inbox' in source
        assert r'^/api/sports/v2/continue-watching' in source
        assert r'^/api/sports/v2/matchday-streak' in source
        assert r'^/api/sports/v2/prediction-challenges' in source
        assert r'^/api/sports/v2/prediction-challenges/submit' in source
        assert r'^/api/sports/v2/live-now' in source

    def test_admin_block_logic_covers_sports_v2_admin(self):
        """Verify access_control_engine.py blocks /api/sports/v2/admin/ for non-admins"""
        from pathlib import Path
        source = Path('/app/backend/utils/access_control_engine.py').read_text(encoding='utf-8')
        
        # Admin block logic should include sports v2 admin paths
        assert '/api/sports/v2/admin/' in source
