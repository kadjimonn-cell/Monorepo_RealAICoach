"""
Feature 33 P2 Enhancement - Weekly Summary & Admin Ranking Tuning Tests
Tests:
- GET /api/content/library/engagement-loop/{user_id} - weekly_summary field with wins/misses/streak_risk/current_streak
- GET /api/admin/content-library/recommendation-tuning - admin-only endpoint with by_plan reason-level conversion
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
BASIC_EMAIL = "f21.basic.1781338672@example.com"
BASIC_PASSWORD = "F21Basic#2026Aa"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


class TestWeeklySummaryInEngagementLoop:
    """Tests for weekly_summary field in engagement-loop endpoint"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        user_data = response.json()
        user_id = user_data.get("user", {}).get("user_id") or user_data.get("user_id")
        return session, user_id
    
    @pytest.fixture
    def basic_session(self):
        """Get authenticated basic user session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": BASIC_EMAIL, "password": BASIC_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Basic login failed: {response.text}"
        user_data = response.json()
        user_id = user_data.get("user", {}).get("user_id") or user_data.get("user_id")
        return session, user_id
    
    def test_engagement_loop_includes_weekly_summary(self, admin_session):
        """Verify engagement-loop endpoint returns weekly_summary field"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200, f"Engagement loop failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify weekly_summary exists
        assert "weekly_summary" in data, "Missing weekly_summary field in engagement-loop response"
        weekly_summary = data["weekly_summary"]
        
        # Verify weekly_summary structure
        assert "wins" in weekly_summary, "weekly_summary missing 'wins' field"
        assert "misses" in weekly_summary, "weekly_summary missing 'misses' field"
        assert "streak_risk" in weekly_summary, "weekly_summary missing 'streak_risk' field"
        assert "current_streak" in weekly_summary, "weekly_summary missing 'current_streak' field"
        
        print("✓ weekly_summary present with all required fields")
        print(f"  - wins: {weekly_summary['wins']}")
        print(f"  - misses: {weekly_summary['misses']}")
        print(f"  - streak_risk: {weekly_summary['streak_risk']}")
        print(f"  - current_streak: {weekly_summary['current_streak']}")
    
    def test_weekly_summary_wins_is_integer(self, admin_session):
        """Verify wins field is an integer"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        wins = data["weekly_summary"]["wins"]
        assert isinstance(wins, int), f"wins should be int, got {type(wins)}"
        assert wins >= 0, f"wins should be non-negative, got {wins}"
        assert wins <= 7, f"wins should be at most 7 (days in a week), got {wins}"
        print(f"✓ wins is valid integer: {wins}")
    
    def test_weekly_summary_misses_is_integer(self, admin_session):
        """Verify misses field is an integer"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        misses = data["weekly_summary"]["misses"]
        assert isinstance(misses, int), f"misses should be int, got {type(misses)}"
        assert misses >= 0, f"misses should be non-negative, got {misses}"
        assert misses <= 7, f"misses should be at most 7 (days in a week), got {misses}"
        print(f"✓ misses is valid integer: {misses}")
    
    def test_weekly_summary_streak_risk_valid_values(self, admin_session):
        """Verify streak_risk is one of low/medium/high"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        streak_risk = data["weekly_summary"]["streak_risk"]
        valid_values = {"low", "medium", "high"}
        assert streak_risk in valid_values, f"streak_risk should be one of {valid_values}, got '{streak_risk}'"
        print(f"✓ streak_risk is valid: {streak_risk}")
    
    def test_weekly_summary_current_streak_matches_streak_days(self, admin_session):
        """Verify current_streak in weekly_summary matches streak_days at top level"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        streak_days = data["streak_days"]
        current_streak = data["weekly_summary"]["current_streak"]
        assert streak_days == current_streak, f"streak_days ({streak_days}) should match weekly_summary.current_streak ({current_streak})"
        print(f"✓ current_streak matches streak_days: {current_streak}")
    
    def test_weekly_summary_wins_plus_misses_equals_seven(self, admin_session):
        """Verify wins + misses = 7 (days in a week)"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        wins = data["weekly_summary"]["wins"]
        misses = data["weekly_summary"]["misses"]
        total = wins + misses
        assert total == 7, f"wins ({wins}) + misses ({misses}) should equal 7, got {total}"
        print(f"✓ wins + misses = 7: {wins} + {misses} = {total}")
    
    def test_weekly_summary_for_basic_user(self, basic_session):
        """Verify basic user also gets weekly_summary"""
        session, user_id = basic_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200, f"Basic user engagement loop failed: {response.status_code}"
        data = response.json()
        
        assert "weekly_summary" in data, "Basic user should also get weekly_summary"
        weekly_summary = data["weekly_summary"]
        assert "wins" in weekly_summary
        assert "misses" in weekly_summary
        assert "streak_risk" in weekly_summary
        assert "current_streak" in weekly_summary
        print(f"✓ Basic user gets weekly_summary: wins={weekly_summary['wins']}, misses={weekly_summary['misses']}")


class TestAdminRecommendationTuningEndpoint:
    """Tests for GET /api/admin/content-library/recommendation-tuning (admin-only)"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return session
    
    @pytest.fixture
    def basic_session(self):
        """Get authenticated basic user session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": BASIC_EMAIL, "password": BASIC_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Basic login failed: {response.text}"
        return session
    
    @pytest.fixture
    def free_session(self):
        """Get authenticated free user session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_EMAIL, "password": FREE_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Free login failed: {response.text}"
        return session
    
    def test_admin_tuning_endpoint_accessible_for_admin(self, admin_session):
        """Verify admin can access recommendation-tuning endpoint"""
        session = admin_session
        response = session.get(
            f"{BASE_URL}/api/admin/content-library/recommendation-tuning",
            timeout=15
        )
        assert response.status_code == 200, f"Admin tuning endpoint failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "window_days" in data, "Missing window_days"
        assert "by_plan" in data, "Missing by_plan"
        assert "plans_covered" in data, "Missing plans_covered"
        
        print("✓ Admin can access recommendation-tuning endpoint")
        print(f"  - window_days: {data['window_days']}")
        print(f"  - plans_covered: {data['plans_covered']}")
    
    def test_admin_tuning_blocked_for_basic_user(self, basic_session):
        """Verify basic user cannot access admin tuning endpoint"""
        session = basic_session
        response = session.get(
            f"{BASE_URL}/api/admin/content-library/recommendation-tuning",
            timeout=15
        )
        assert response.status_code == 403, f"Expected 403 for basic user, got {response.status_code}"
        print(f"✓ Basic user blocked from admin tuning endpoint: {response.status_code}")
    
    def test_admin_tuning_blocked_for_free_user(self, free_session):
        """Verify free user cannot access admin tuning endpoint"""
        session = free_session
        response = session.get(
            f"{BASE_URL}/api/admin/content-library/recommendation-tuning",
            timeout=15
        )
        assert response.status_code == 403, f"Expected 403 for free user, got {response.status_code}"
        print(f"✓ Free user blocked from admin tuning endpoint: {response.status_code}")
    
    def test_admin_tuning_blocked_for_unauthenticated(self):
        """Verify unauthenticated request is blocked"""
        response = requests.get(
            f"{BASE_URL}/api/admin/content-library/recommendation-tuning",
            timeout=15
        )
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated, got {response.status_code}"
        print(f"✓ Unauthenticated request blocked: {response.status_code}")
    
    def test_admin_tuning_by_plan_structure(self, admin_session):
        """Verify by_plan contains proper structure with reason-level conversion"""
        session = admin_session
        response = session.get(
            f"{BASE_URL}/api/admin/content-library/recommendation-tuning",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        by_plan = data["by_plan"]
        assert isinstance(by_plan, dict), f"by_plan should be dict, got {type(by_plan)}"
        
        # Check structure for each plan if data exists
        for plan, plan_data in by_plan.items():
            assert "events" in plan_data, f"Plan '{plan}' missing 'events'"
            assert "reason_level_conversion" in plan_data, f"Plan '{plan}' missing 'reason_level_conversion'"
            
            # Verify events structure
            events = plan_data["events"]
            assert "recommendation_reason_click" in events, f"Plan '{plan}' events missing recommendation_reason_click"
            assert "open_after_recommendation" in events, f"Plan '{plan}' events missing open_after_recommendation"
            assert "bookmark_after_recommendation" in events, f"Plan '{plan}' events missing bookmark_after_recommendation"
            
            # Verify reason_level_conversion is a list
            reason_conversion = plan_data["reason_level_conversion"]
            assert isinstance(reason_conversion, list), f"reason_level_conversion should be list, got {type(reason_conversion)}"
            
            # If there are entries, verify their structure
            for entry in reason_conversion:
                assert "reason" in entry, "reason_level_conversion entry missing 'reason'"
                assert "clicks" in entry, "reason_level_conversion entry missing 'clicks'"
                assert "opens" in entry, "reason_level_conversion entry missing 'opens'"
                assert "bookmarks" in entry, "reason_level_conversion entry missing 'bookmarks'"
                assert "open_after_click_rate" in entry, "reason_level_conversion entry missing 'open_after_click_rate'"
                assert "bookmark_after_open_rate" in entry, "reason_level_conversion entry missing 'bookmark_after_open_rate'"
            
            print(f"✓ Plan '{plan}' has valid structure with {len(reason_conversion)} reason entries")
        
        print(f"✓ by_plan structure verified for {len(by_plan)} plans")
    
    def test_admin_tuning_with_days_param(self, admin_session):
        """Verify days parameter works"""
        session = admin_session
        response = session.get(
            f"{BASE_URL}/api/admin/content-library/recommendation-tuning?days=30",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        # Days should be clamped between 7 and 60
        assert data["window_days"] >= 7, "window_days should be at least 7"
        assert data["window_days"] <= 60, "window_days should be at most 60"
        print(f"✓ Admin tuning with days param: window_days={data['window_days']}")
    
    def test_admin_tuning_plans_covered_matches_by_plan_keys(self, admin_session):
        """Verify plans_covered list matches by_plan keys"""
        session = admin_session
        response = session.get(
            f"{BASE_URL}/api/admin/content-library/recommendation-tuning",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        plans_covered = set(data["plans_covered"])
        by_plan_keys = set(data["by_plan"].keys())
        
        assert plans_covered == by_plan_keys, f"plans_covered {plans_covered} should match by_plan keys {by_plan_keys}"
        print(f"✓ plans_covered matches by_plan keys: {sorted(plans_covered)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
