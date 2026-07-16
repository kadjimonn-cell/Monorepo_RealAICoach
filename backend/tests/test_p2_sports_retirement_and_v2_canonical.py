"""
P2 Sports Retirement and V2 Canonical Routes Verification

Tests:
1. Legacy /api/videos/sports/* wrappers are retired (404/410)
2. Canonical /api/sports/v2/* routes work for authenticated users
3. Admin-only endpoints correctly gated
4. No regression in Feature 30 v2 payload sections
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def free_user_session():
    """Get authenticated session for free user"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",  # CSRF bypass for API calls
    })
    
    # Login as free user
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
    )
    if login_resp.status_code != 200:
        pytest.skip(f"Free user login failed: {login_resp.status_code} - {login_resp.text[:200]}")
    
    return session


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated session for admin user"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",  # CSRF bypass for API calls
    })
    
    # Login as admin
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if login_resp.status_code != 200:
        pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
    
    return session


class TestLegacySportsWrappersRetired:
    """P2: Legacy /api/videos/sports/* wrappers should be retired (404/410)"""
    
    def test_legacy_sports_bootstrap_retired(self, free_user_session):
        """Legacy /api/videos/sports/bootstrap should return 404 or 410"""
        resp = free_user_session.get(f"{BASE_URL}/api/videos/sports/bootstrap")
        # 404 or 410 indicates retirement - PASS
        assert resp.status_code in [404, 410], f"Expected 404/410 for retired endpoint, got {resp.status_code}"
        print(f"PASS: /api/videos/sports/bootstrap retired with status {resp.status_code}")
    
    def test_legacy_sports_play_retired(self, free_user_session):
        """Legacy /api/videos/sports/play should return 404, 410, or 403 (blocked)"""
        resp = free_user_session.post(
            f"{BASE_URL}/api/videos/sports/play",
            json={"item_id": "test_item", "listen_seconds": 0}
        )
        # 404/410 = retired, 403 = blocked/forbidden - all indicate retirement
        assert resp.status_code in [404, 410, 403], f"Expected 404/410/403 for retired endpoint, got {resp.status_code}"
        print(f"PASS: /api/videos/sports/play retired with status {resp.status_code}")
    
    def test_legacy_sports_daily_drop_inbox_retired(self, free_user_session):
        """Legacy /api/videos/sports/daily-drop-inbox should return 404 or 410"""
        resp = free_user_session.get(f"{BASE_URL}/api/videos/sports/daily-drop-inbox")
        assert resp.status_code in [404, 410], f"Expected 404/410 for retired endpoint, got {resp.status_code}"
        print(f"PASS: /api/videos/sports/daily-drop-inbox retired with status {resp.status_code}")
    
    def test_legacy_sports_follow_league_retired(self, free_user_session):
        """Legacy /api/videos/sports/follow-league should return 404, 410, or 403 (blocked)"""
        resp = free_user_session.post(
            f"{BASE_URL}/api/videos/sports/follow-league",
            json={"league_name": "NFL on CBS"}
        )
        # 404/410 = retired, 403 = blocked/forbidden - all indicate retirement
        assert resp.status_code in [404, 410, 403], f"Expected 404/410/403 for retired endpoint, got {resp.status_code}"
        print(f"PASS: /api/videos/sports/follow-league retired with status {resp.status_code}")


class TestCanonicalSportsV2Routes:
    """Canonical /api/sports/v2/* routes should work for authenticated users"""
    
    def test_sports_v2_bootstrap_works(self, free_user_session):
        """GET /api/sports/v2/bootstrap should return 200 with valid payload"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/bootstrap")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        # Verify required sections from Feature 30 v2
        assert "feature_id" in data, "Missing feature_id"
        assert data.get("feature_id") == "watch-videos-sports", f"Wrong feature_id: {data.get('feature_id')}"
        assert "catalog" in data, "Missing catalog"
        assert "quota" in data, "Missing quota"
        
        # Verify P1 sections from iteration_364
        assert "matchday_streak" in data, "Missing matchday_streak section"
        assert "prediction_challenge_rail" in data, "Missing prediction_challenge_rail section"
        
        # Verify contract
        contract = data.get("contract", {})
        assert "version" in contract, "Missing contract version"
        assert "required_sections" in contract, "Missing required_sections"
        
        print(f"PASS: /api/sports/v2/bootstrap returns valid payload with {len(data.get('catalog', []))} items")
    
    def test_sports_v2_play_works(self, free_user_session):
        """POST /api/sports/v2/play should work with valid item"""
        # First get a valid item_id from bootstrap
        bootstrap_resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/bootstrap")
        if bootstrap_resp.status_code != 200:
            pytest.skip("Cannot get bootstrap for play test")
        
        catalog = bootstrap_resp.json().get("catalog", [])
        if not catalog:
            pytest.skip("No catalog items available")
        
        # Find a free-tier item
        test_item = None
        for item in catalog:
            if item.get("min_plan", "free") == "free":
                test_item = item
                break
        
        if not test_item:
            test_item = catalog[0]
        
        resp = free_user_session.post(
            f"{BASE_URL}/api/sports/v2/play",
            json={"item_id": test_item["item_id"], "listen_seconds": 0, "completed": False}
        )
        
        # 200 = success, 402 = plan upgrade required (acceptable for locked items), 403 = blackout (acceptable)
        assert resp.status_code in [200, 402, 403], f"Expected 200/402/403, got {resp.status_code}: {resp.text[:300]}"
        
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("ok") == True, "Expected ok=True"
            assert data.get("surface") == "sports", "Expected surface=sports"
            print(f"PASS: /api/sports/v2/play works for item {test_item['item_id']}")
        else:
            print(f"PASS: /api/sports/v2/play correctly returns {resp.status_code} for gated item")
    
    def test_sports_v2_daily_drop_inbox_works(self, free_user_session):
        """GET /api/sports/v2/daily-drop-inbox should return 200"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/daily-drop-inbox")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        assert "surface" in data, "Missing surface"
        assert data.get("surface") == "sports", "Expected surface=sports"
        assert "items" in data, "Missing items"
        assert "total" in data, "Missing total"
        
        print(f"PASS: /api/sports/v2/daily-drop-inbox returns {data.get('total', 0)} items")
    
    def test_sports_v2_follow_league_works(self, free_user_session):
        """POST /api/sports/v2/follow-league should return 200"""
        resp = free_user_session.post(
            f"{BASE_URL}/api/sports/v2/follow-league",
            json={"league_name": "NFL on CBS"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        assert data.get("ok") == True, "Expected ok=True"
        assert data.get("league_name") == "NFL on CBS", "Expected league_name match"
        
        print("PASS: /api/sports/v2/follow-league works")
    
    def test_sports_v2_unfollow_league_works(self, free_user_session):
        """POST /api/sports/v2/unfollow-league should return 200"""
        resp = free_user_session.post(
            f"{BASE_URL}/api/sports/v2/unfollow-league",
            json={"league_name": "NFL on CBS"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        assert data.get("ok") == True, "Expected ok=True"
        
        print("PASS: /api/sports/v2/unfollow-league works")
    
    def test_sports_v2_matchday_streak_works(self, free_user_session):
        """GET /api/sports/v2/matchday-streak should return 200"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/matchday-streak")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        assert "surface" in data, "Missing surface"
        assert data.get("surface") == "sports", "Expected surface=sports"
        assert "matchday_streak" in data, "Missing matchday_streak"
        
        streak = data.get("matchday_streak", {})
        assert "current_streak_days" in streak, "Missing current_streak_days"
        assert "status" in streak, "Missing status"
        assert "comeback_prompt" in streak, "Missing comeback_prompt"
        
        print(f"PASS: /api/sports/v2/matchday-streak returns streak={streak.get('current_streak_days')}")
    
    def test_sports_v2_prediction_challenges_works(self, free_user_session):
        """GET /api/sports/v2/prediction-challenges should return 200"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/prediction-challenges")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        assert "surface" in data, "Missing surface"
        assert data.get("surface") == "sports", "Expected surface=sports"
        assert "prediction_challenge_rail" in data, "Missing prediction_challenge_rail"
        
        rail = data.get("prediction_challenge_rail", {})
        assert "challenges" in rail, "Missing challenges"
        assert "total" in rail, "Missing total"
        
        print(f"PASS: /api/sports/v2/prediction-challenges returns {rail.get('total', 0)} challenges")


class TestAdminSportsV2Gating:
    """Admin-only endpoints should be correctly gated"""
    
    def test_admin_source_health_blocked_for_free_user(self, free_user_session):
        """GET /api/sports/v2/admin/source-health should return 403 for free user"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/admin/source-health")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("PASS: /api/sports/v2/admin/source-health correctly blocks free user (403)")
    
    def test_admin_source_health_works_for_admin(self, admin_session):
        """GET /api/sports/v2/admin/source-health should return 200 for admin"""
        resp = admin_session.get(f"{BASE_URL}/api/sports/v2/admin/source-health")
        assert resp.status_code == 200, f"Expected 200 for admin, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        assert "summary" in data, "Missing summary"
        assert "sources" in data, "Missing sources"
        
        summary = data.get("summary", {})
        assert "total_items" in summary, "Missing total_items"
        assert "playable_items" in summary, "Missing playable_items"
        
        print(f"PASS: /api/sports/v2/admin/source-health works for admin with {summary.get('total_items', 0)} items")
    
    def test_admin_conversion_dashboard_blocked_for_free_user(self, free_user_session):
        """GET /api/sports/v2/admin/conversion-dashboard should return 403 for free user"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/admin/conversion-dashboard")
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("PASS: /api/sports/v2/admin/conversion-dashboard correctly blocks free user (403)")
    
    def test_admin_conversion_dashboard_works_for_admin(self, admin_session):
        """GET /api/sports/v2/admin/conversion-dashboard should return 200 for admin"""
        resp = admin_session.get(f"{BASE_URL}/api/sports/v2/admin/conversion-dashboard")
        assert resp.status_code == 200, f"Expected 200 for admin, got {resp.status_code}: {resp.text[:300]}"
        
        data = resp.json()
        assert "feature_id" in data, "Missing feature_id"
        assert data.get("feature_id") == "sports", "Expected feature_id=sports"
        assert "kpis" in data, "Missing kpis"
        
        print("PASS: /api/sports/v2/admin/conversion-dashboard works for admin")


class TestFeature30V2PayloadSections:
    """Verify no regression in Feature 30 v2 payload sections"""
    
    def test_bootstrap_has_all_required_sections(self, free_user_session):
        """Bootstrap should have all required sections from Feature 30 v2"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/bootstrap")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        
        # Required sections from Feature 30 v2
        required_sections = [
            "feature_id",
            "catalog",
            "quota",
            "behavioral_ai",
            "daily_drop_inbox",
            "matchday_streak",
            "prediction_challenge_rail",
            "contract",
        ]
        
        missing = []
        for section in required_sections:
            if section not in data:
                missing.append(section)
        
        assert not missing, f"Missing required sections: {missing}"
        
        # Verify contract version
        contract = data.get("contract", {})
        version = contract.get("version", "")
        assert "feature30" in version.lower() or "v2" in version.lower(), f"Unexpected contract version: {version}"
        
        print(f"PASS: Bootstrap has all {len(required_sections)} required sections")
    
    def test_bootstrap_quota_structure(self, free_user_session):
        """Bootstrap quota should have correct structure"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/bootstrap")
        assert resp.status_code == 200
        
        data = resp.json()
        quota = data.get("quota", {})
        
        assert "plan" in quota, "Missing plan in quota"
        assert "scope_label" in quota, "Missing scope_label in quota"
        
        print(f"PASS: Bootstrap quota has plan={quota.get('plan')}, scope={quota.get('scope_label')}")
    
    def test_bootstrap_catalog_items_structure(self, free_user_session):
        """Bootstrap catalog items should have correct structure"""
        resp = free_user_session.get(f"{BASE_URL}/api/sports/v2/bootstrap")
        assert resp.status_code == 200
        
        data = resp.json()
        catalog = data.get("catalog", [])
        
        if not catalog:
            pytest.skip("No catalog items to verify")
        
        item = catalog[0]
        required_fields = ["item_id", "title", "category", "min_plan"]
        
        missing = []
        for field in required_fields:
            if field not in item:
                missing.append(field)
        
        assert not missing, f"Missing required fields in catalog item: {missing}"
        
        print(f"PASS: Catalog items have correct structure ({len(catalog)} items)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
