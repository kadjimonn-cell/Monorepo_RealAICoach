"""
Feature 25 Daily Meditation Health Endpoint Tests
Tests: /api/travel-visa/daily-meditation/health endpoint and regression on nearby endpoints
"""

import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://coach-web-preview.preview.emergentagent.com"

ADMIN_CREDS = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}
FREE_CREDS = {"email": "tv.free.test@realaicoach.app", "password": "TvFree#2026!Aa"}


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session with auth token"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    
    r = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} - {r.text[:200]}")
    
    data = r.json()
    user_id = data.get("user_id")
    
    # Get token from cookies or response
    token = None
    for cookie in session.cookies:
        if cookie.name == "session_token":
            token = cookie.value
            break
    
    if not token:
        token = data.get("session_token") or data.get("token")
    
    return {"session": session, "token": token, "user_id": user_id}


@pytest.fixture(scope="module")
def free_session():
    """Get free user session with auth token"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    
    r = session.post(f"{BASE_URL}/api/auth/login", json=FREE_CREDS)
    if r.status_code != 200:
        pytest.skip(f"Free user login failed: {r.status_code} - {r.text[:200]}")
    
    data = r.json()
    user_id = data.get("user_id")
    
    # Get token from cookies or response
    token = None
    for cookie in session.cookies:
        if cookie.name == "session_token":
            token = cookie.value
            break
    
    if not token:
        token = data.get("session_token") or data.get("token")
    
    return {"session": session, "token": token, "user_id": user_id}


# ─────────────────────────────────────────────────────────────────────────────
# Health Endpoint Tests (Feature 25 Governance Hygiene)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    """Verify lightweight health endpoint for Feature 25 governance checks"""

    def test_health_returns_200_for_authenticated_user(self, admin_session):
        """GET /api/travel-visa/daily-meditation/health returns 200 for authenticated user"""
        r = admin_session["session"].get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/health"
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

    def test_health_payload_includes_locked_contract_fields(self, admin_session):
        """Health payload includes locked contract fields: feature_number=25, feature_id=daily-meditation, feature_route=/features/daily-meditation"""
        r = admin_session["session"].get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/health"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        
        # Verify locked contract fields
        assert data.get("ok") is True, f"Expected ok=True, got {data.get('ok')}"
        assert data.get("feature_number") == 25, f"Expected feature_number=25, got {data.get('feature_number')}"
        assert data.get("feature_id") == "daily-meditation", f"Expected feature_id='daily-meditation', got {data.get('feature_id')}"
        assert data.get("feature_route") == "/features/daily-meditation", f"Expected feature_route='/features/daily-meditation', got {data.get('feature_route')}"

    def test_health_payload_includes_plan_and_scope_label(self, admin_session):
        """Health payload includes plan and scope_label"""
        r = admin_session["session"].get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/health"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        
        # Verify plan and scope_label
        assert data.get("plan") in ["free", "basic", "premium"], f"Expected plan in [free, basic, premium], got {data.get('plan')}"
        assert isinstance(data.get("scope_label"), str), f"Expected scope_label to be string, got {type(data.get('scope_label'))}"
        assert len(data.get("scope_label", "")) > 0, "Expected non-empty scope_label"
        assert isinstance(data.get("generated_at"), str), f"Expected generated_at to be string, got {type(data.get('generated_at'))}"

    def test_health_unauthenticated_request_blocked(self):
        """Unauthenticated request is blocked with auth error"""
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/health",
            headers={"Content-Type": "application/json"}
        )
        # Should return 401 or 403 for unauthenticated request
        assert r.status_code in [401, 403], f"Expected 401 or 403 for unauthenticated request, got {r.status_code}: {r.text[:200]}"

    def test_health_works_for_free_user(self, free_session):
        """Health endpoint works for free user with correct plan"""
        r = free_session["session"].get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/health"
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
        data = r.json()
        
        # Verify response structure
        assert data.get("ok") is True
        assert data.get("feature_number") == 25
        assert data.get("feature_id") == "daily-meditation"
        assert data.get("plan") in ["free", "basic", "premium"]


# ─────────────────────────────────────────────────────────────────────────────
# Regression Tests for Nearby Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureMapRegression:
    """Regression test for /api/travel-visa/daily-meditation/feature-map"""

    def test_feature_map_returns_200(self, admin_session):
        """GET /api/travel-visa/daily-meditation/feature-map returns 200"""
        r = admin_session["session"].get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
            params={"user_id": admin_session["user_id"]}
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

    def test_feature_map_returns_expected_structure(self, admin_session):
        """Feature map returns expected structure with tab, total_features, features, plan"""
        r = admin_session["session"].get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
            params={"user_id": admin_session["user_id"]}
        )
        assert r.status_code == 200, r.text
        data = r.json()
        
        assert data.get("tab") == "Daily Meditation", f"Expected tab='Daily Meditation', got {data.get('tab')}"
        assert isinstance(data.get("total_features"), int), "Expected total_features to be int"
        assert data.get("total_features") >= 31, f"Expected at least 31 features, got {data.get('total_features')}"
        assert isinstance(data.get("features"), list), "Expected features to be list"
        assert data.get("plan") in ["free", "basic", "premium"], "Expected plan in [free, basic, premium]"


class TestOverviewRegression:
    """Regression test for /api/travel-visa/daily-meditation/overview/{user_id}"""

    def test_overview_returns_200(self, admin_session):
        """GET /api/travel-visa/daily-meditation/overview/{user_id} returns 200"""
        r = admin_session["session"].get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/overview/{admin_session['user_id']}"
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

    def test_overview_returns_expected_structure(self, admin_session):
        """Overview returns expected structure with user_id, plan, limits, progress"""
        r = admin_session["session"].get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/overview/{admin_session['user_id']}"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        
        assert data.get("user_id") == admin_session["user_id"], "Expected user_id match"
        assert data.get("plan") in ["free", "basic", "premium"], "Expected plan in [free, basic, premium]"
        assert isinstance(data.get("limits"), dict), "Expected limits to be dict"
        assert isinstance(data.get("progress"), dict), "Expected progress to be dict"
        assert "usage_today" in data, "Expected usage_today in response"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
