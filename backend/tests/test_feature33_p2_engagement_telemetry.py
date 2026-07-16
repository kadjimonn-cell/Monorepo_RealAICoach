"""
Feature 33 P2 - Content Library Engagement Loop & Recommendation Telemetry Tests
Tests:
- GET /api/content/library/engagement-loop/{user_id} - streak_days, continue_item, daily_mission
- GET /api/content/library/recommendation-telemetry/{user_id} - event counters, conversion rates
- Telemetry event logging via /api/actions/log
- Regression: sort chips, bookmarks, export, free-user gate
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


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_check(self):
        """Verify API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("✓ Health check passed")
    
    def test_login_admin_user(self):
        """Login as admin user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Admin login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "user" in data or "user_id" in data, "Login response missing user data"
        print("✓ Admin login passed")
        return response.cookies
    
    def test_login_basic_user(self):
        """Login as basic tier user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": BASIC_EMAIL, "password": BASIC_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Basic user login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "user" in data or "user_id" in data, "Login response missing user data"
        print("✓ Basic user login passed")
        return response.cookies
    
    def test_login_free_user(self):
        """Login as free tier user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_EMAIL, "password": FREE_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Free user login failed: {response.status_code} - {response.text}"
        print("✓ Free user login passed")
        return response.cookies


class TestEngagementLoopEndpoint:
    """Tests for GET /api/content/library/engagement-loop/{user_id}"""
    
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
    
    def test_engagement_loop_returns_required_fields(self, admin_session):
        """Verify engagement-loop endpoint returns streak_days, continue_item, daily_mission"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200, f"Engagement loop failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify required fields exist
        assert "streak_days" in data, "Missing streak_days field"
        assert "continue_item" in data, "Missing continue_item field"
        assert "daily_mission" in data, "Missing daily_mission field"
        assert "window_days" in data, "Missing window_days field"
        
        # Verify streak_days is a number
        assert isinstance(data["streak_days"], int), f"streak_days should be int, got {type(data['streak_days'])}"
        
        # Verify daily_mission structure
        daily_mission = data["daily_mission"]
        assert "target" in daily_mission, "daily_mission missing target"
        assert "progress" in daily_mission, "daily_mission missing progress"
        assert "completed" in daily_mission, "daily_mission missing completed"
        assert "adaptive_context" in daily_mission, "daily_mission missing adaptive_context"
        
        # Verify target structure
        target = daily_mission["target"]
        assert "opens" in target, "target missing opens"
        assert "bookmarks" in target, "target missing bookmarks"
        
        # Verify progress structure
        progress = daily_mission["progress"]
        assert "opens" in progress, "progress missing opens"
        assert "bookmarks" in progress, "progress missing bookmarks"

        # Verify adaptive_context structure
        adaptive_context = daily_mission["adaptive_context"]
        assert "mode" in adaptive_context, "adaptive_context missing mode"
        assert adaptive_context["mode"] in {"baseline", "adaptive"}, "adaptive_context.mode should be baseline/adaptive"
        assert "history_days_used" in adaptive_context, "adaptive_context missing history_days_used"
        assert "active_days" in adaptive_context, "adaptive_context missing active_days"
        assert "consistency_ratio" in adaptive_context, "adaptive_context missing consistency_ratio"
        assert "weighted_avg" in adaptive_context, "adaptive_context missing weighted_avg"
        assert "baseline_target" in adaptive_context, "adaptive_context missing baseline_target"
        assert "target_delta" in adaptive_context, "adaptive_context missing target_delta"
        assert "change_direction" in adaptive_context, "adaptive_context missing change_direction"
        assert "tone_profile" in adaptive_context, "adaptive_context missing tone_profile"
        assert "change_reason_short" in adaptive_context, "adaptive_context missing change_reason_short"
        assert "change_reason_detail" in adaptive_context, "adaptive_context missing change_reason_detail"
        assert isinstance(adaptive_context["history_days_used"], int), "history_days_used should be int"
        assert isinstance(adaptive_context["active_days"], int), "active_days should be int"
        assert isinstance(adaptive_context["consistency_ratio"], float), "consistency_ratio should be float"
        assert isinstance(adaptive_context["weighted_avg"], dict), "weighted_avg should be dict"
        assert isinstance(adaptive_context["baseline_target"], dict), "baseline_target should be dict"
        assert isinstance(adaptive_context["target_delta"], dict), "target_delta should be dict"
        assert isinstance(adaptive_context["change_reason_detail"], list), "change_reason_detail should be list"
        assert adaptive_context["change_direction"] in {"increased", "decreased", "stable", "adjusted"}, "invalid change_direction"
        assert adaptive_context["tone_profile"] in {"free", "basic", "premium"}, "invalid tone_profile"
        assert "opens" in adaptive_context["weighted_avg"], "weighted_avg missing opens"
        assert "bookmarks" in adaptive_context["weighted_avg"], "weighted_avg missing bookmarks"
        assert "opens" in adaptive_context["baseline_target"], "baseline_target missing opens"
        assert "bookmarks" in adaptive_context["baseline_target"], "baseline_target missing bookmarks"
        assert "opens" in adaptive_context["target_delta"], "target_delta missing opens"
        assert "bookmarks" in adaptive_context["target_delta"], "target_delta missing bookmarks"
        
        print("✓ Engagement loop returns all required fields")
        print(f"  - streak_days: {data['streak_days']}")
        print(f"  - continue_item: {'present' if data['continue_item'] else 'null'}")
        print(f"  - daily_mission completed: {daily_mission['completed']}")
    
    def test_engagement_loop_continue_item_structure(self, admin_session):
        """Verify continue_item has correct structure when present"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        
        continue_item = data.get("continue_item")
        if continue_item is not None:
            # If continue_item exists, verify its structure
            expected_fields = ["title", "type", "category", "url", "last_opened_at"]
            for field in expected_fields:
                assert field in continue_item, f"continue_item missing {field}"
            print(f"✓ continue_item structure verified: {continue_item.get('title', 'N/A')}")
        else:
            print("✓ continue_item is null (no recent activity)")
    
    def test_engagement_loop_with_days_param(self, admin_session):
        """Verify days parameter works"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}?days=14",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        # Days should be clamped between 7 and 90
        assert data["window_days"] >= 7, "window_days should be at least 7"
        assert data["window_days"] <= 90, "window_days should be at most 90"
        print(f"✓ Engagement loop with days param: window_days={data['window_days']}")


class TestRecommendationTelemetryEndpoint:
    """Tests for GET /api/content/library/recommendation-telemetry/{user_id}"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200
        user_data = response.json()
        user_id = user_data.get("user", {}).get("user_id") or user_data.get("user_id")
        return session, user_id
    
    def test_telemetry_returns_required_fields(self, admin_session):
        """Verify recommendation-telemetry endpoint returns event counters and conversion rates"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/recommendation-telemetry/{user_id}",
            timeout=15
        )
        assert response.status_code == 200, f"Telemetry failed: {response.status_code} - {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "window_days" in data, "Missing window_days"
        assert "events" in data, "Missing events"
        assert "conversion" in data, "Missing conversion"
        assert "top_reasons" in data, "Missing top_reasons"
        
        # Verify events structure
        events = data["events"]
        assert "recommendation_reason_click" in events, "events missing recommendation_reason_click"
        assert "open_after_recommendation" in events, "events missing open_after_recommendation"
        assert "bookmark_after_recommendation" in events, "events missing bookmark_after_recommendation"
        
        # Verify conversion structure
        conversion = data["conversion"]
        assert "open_after_reason_click_rate" in conversion, "conversion missing open_after_reason_click_rate"
        assert "bookmark_after_open_rate" in conversion, "conversion missing bookmark_after_open_rate"
        
        # Verify top_reasons is a list
        assert isinstance(data["top_reasons"], list), "top_reasons should be a list"
        
        print("✓ Recommendation telemetry returns all required fields")
        print(f"  - events: {events}")
        print(f"  - conversion: {conversion}")
        print(f"  - top_reasons count: {len(data['top_reasons'])}")
    
    def test_telemetry_with_days_param(self, admin_session):
        """Verify days parameter works"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library/recommendation-telemetry/{user_id}?days=30",
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        # Days should be clamped between 7 and 60
        assert data["window_days"] >= 7, "window_days should be at least 7"
        assert data["window_days"] <= 60, "window_days should be at most 60"
        print(f"✓ Telemetry with days param: window_days={data['window_days']}")


class TestTelemetryEventLogging:
    """Tests for telemetry event logging via /api/actions/log"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session with CSRF headers"""
        session = requests.Session()
        session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json"
        })
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200
        user_data = response.json()
        user_id = user_data.get("user", {}).get("user_id") or user_data.get("user_id")
        return session, user_id
    
    def test_log_recommendation_reason_click(self, admin_session):
        """Test logging recommendation_reason_click event"""
        session, user_id = admin_session
        response = session.post(
            f"{BASE_URL}/api/actions/log",
            json={
                "user_id": user_id,
                "feature_key": "content-library",
                "action": "recommendation_reason_click",
                "details": {
                    "reason": "fresh",
                    "title": "Test Content",
                    "type": "article",
                    "category": "productivity"
                }
            },
            timeout=15
        )
        assert response.status_code == 200, f"Log action failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("success") == True, "Log action should return success=True"
        assert "action_id" in data, "Log action should return action_id"
        print(f"✓ recommendation_reason_click event logged: {data['action_id']}")
    
    def test_log_open_after_recommendation(self, admin_session):
        """Test logging open_after_recommendation event"""
        session, user_id = admin_session
        response = session.post(
            f"{BASE_URL}/api/actions/log",
            json={
                "user_id": user_id,
                "feature_key": "content-library",
                "action": "open_after_recommendation",
                "details": {
                    "title": "Test Content",
                    "type": "article",
                    "category": "productivity",
                    "url": "https://example.com/test",
                    "reasons": ["fresh", "matches_activity"],
                    "score": 8.5
                }
            },
            timeout=15
        )
        assert response.status_code == 200, f"Log action failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("success") == True
        print(f"✓ open_after_recommendation event logged: {data['action_id']}")
    
    def test_log_bookmark_after_recommendation(self, admin_session):
        """Test logging bookmark_after_recommendation event"""
        session, user_id = admin_session
        response = session.post(
            f"{BASE_URL}/api/actions/log",
            json={
                "user_id": user_id,
                "feature_key": "content-library",
                "action": "bookmark_after_recommendation",
                "details": {
                    "content_id": "https://example.com/test",
                    "title": "Test Content",
                    "reasons": ["bookmarked"],
                    "score": 7.2
                }
            },
            timeout=15
        )
        assert response.status_code == 200, f"Log action failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data.get("success") == True
        print(f"✓ bookmark_after_recommendation event logged: {data['action_id']}")


class TestRegressionSortChips:
    """Regression tests for sort chips functionality"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200
        user_data = response.json()
        user_id = user_data.get("user", {}).get("user_id") or user_data.get("user_id")
        return session, user_id
    
    def test_library_sort_recommended(self, admin_session):
        """Test library with sort=recommended"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library?user_id={user_id}&sort=recommended",
            timeout=15
        )
        assert response.status_code == 200, f"Library recommended sort failed: {response.status_code}"
        data = response.json()
        assert "items" in data, "Response missing items"
        print(f"✓ Library sort=recommended: {len(data.get('items', []))} items")
    
    def test_library_sort_newest(self, admin_session):
        """Test library with sort=newest"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library?user_id={user_id}&sort=newest",
            timeout=15
        )
        assert response.status_code == 200, f"Library newest sort failed: {response.status_code}"
        data = response.json()
        assert "items" in data
        print(f"✓ Library sort=newest: {len(data.get('items', []))} items")
    
    def test_library_sort_oldest(self, admin_session):
        """Test library with sort=oldest"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/library?user_id={user_id}&sort=oldest",
            timeout=15
        )
        assert response.status_code == 200, f"Library oldest sort failed: {response.status_code}"
        data = response.json()
        assert "items" in data
        print(f"✓ Library sort=oldest: {len(data.get('items', []))} items")


class TestRegressionBookmarks:
    """Regression tests for bookmark functionality"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session with CSRF headers"""
        session = requests.Session()
        session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json"
        })
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200
        user_data = response.json()
        user_id = user_data.get("user", {}).get("user_id") or user_data.get("user_id")
        return session, user_id
    
    def test_get_bookmarks(self, admin_session):
        """Test GET /api/content/bookmarks/{user_id}"""
        session, user_id = admin_session
        response = session.get(
            f"{BASE_URL}/api/content/bookmarks/{user_id}",
            timeout=15
        )
        assert response.status_code == 200, f"Get bookmarks failed: {response.status_code}"
        data = response.json()
        assert "bookmarks" in data, "Response missing bookmarks"
        assert "count" in data, "Response missing count"
        print(f"✓ Get bookmarks: {data['count']} bookmarks")
    
    def test_toggle_bookmark(self, admin_session):
        """Test POST /api/content/bookmarks/toggle"""
        session, user_id = admin_session
        test_content_id = f"test_bookmark_{user_id}_p2"
        
        # Toggle bookmark on
        response = session.post(
            f"{BASE_URL}/api/content/bookmarks/toggle",
            json={
                "user_id": user_id,
                "content_id": test_content_id,
                "title": "P2 Test Bookmark"
            },
            timeout=15
        )
        assert response.status_code == 200, f"Toggle bookmark failed: {response.status_code}"
        data = response.json()
        assert "bookmarked" in data, "Response missing bookmarked field"
        assert data["content_id"] == test_content_id
        first_state = data["bookmarked"]
        print(f"✓ Toggle bookmark (first): bookmarked={first_state}")
        
        # Toggle again to reverse
        response = session.post(
            f"{BASE_URL}/api/content/bookmarks/toggle",
            json={
                "user_id": user_id,
                "content_id": test_content_id,
                "title": "P2 Test Bookmark"
            },
            timeout=15
        )
        assert response.status_code == 200
        data = response.json()
        assert data["bookmarked"] != first_state, "Toggle should reverse bookmark state"
        print(f"✓ Toggle bookmark (second): bookmarked={data['bookmarked']}")


class TestRegressionExport:
    """Regression tests for export functionality"""
    
    @pytest.fixture
    def admin_session(self):
        """Get authenticated admin session with CSRF headers"""
        session = requests.Session()
        session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json"
        })
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200
        return session
    
    def test_export_txt(self, admin_session):
        """Test library export as TXT"""
        session = admin_session
        response = session.post(
            f"{BASE_URL}/api/content/library/export",
            json={
                "items": [
                    {"title": "Test Item 1", "type": "article", "category": "productivity", "url": "https://example.com/1", "added_date": "2026-01-01"},
                    {"title": "Test Item 2", "type": "guide", "category": "health", "url": "https://example.com/2", "added_date": "2026-01-02"}
                ],
                "format": "txt"
            },
            timeout=15
        )
        assert response.status_code == 200, f"Export TXT failed: {response.status_code}"
        assert "text/plain" in response.headers.get("content-type", ""), "Should return text/plain"
        print(f"✓ Export TXT: {len(response.content)} bytes")
    
    def test_export_csv(self, admin_session):
        """Test library export as CSV"""
        session = admin_session
        response = session.post(
            f"{BASE_URL}/api/content/library/export",
            json={
                "items": [
                    {"title": "Test Item 1", "type": "article", "category": "productivity", "url": "https://example.com/1", "added_date": "2026-01-01"}
                ],
                "format": "csv"
            },
            timeout=15
        )
        assert response.status_code == 200, f"Export CSV failed: {response.status_code}"
        assert "text/csv" in response.headers.get("content-type", ""), "Should return text/csv"
        print(f"✓ Export CSV: {len(response.content)} bytes")


class TestRegressionFreeUserGate:
    """POLICY 2026-06.v3: free users get limited (not blocked) Library access"""

    def _free_session(self):
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_EMAIL, "password": FREE_PASSWORD},
            timeout=15
        )
        assert response.status_code == 200, f"Free user login failed: {response.text}"
        user_data = response.json()
        user_id = user_data.get("user", {}).get("user_id") or user_data.get("user_id")
        return session, user_id

    def test_free_user_library_access_limited_allowed(self):
        """POLICY 2026-06.v3: free users can read the library (limited access)"""
        session, user_id = self._free_session()
        response = session.get(
            f"{BASE_URL}/api/content/library?user_id={user_id}",
            timeout=15
        )
        assert response.status_code == 200, f"Expected limited access 200 for free user, got {response.status_code}"
        print("✓ Free user has limited library access")

    def test_free_user_engagement_loop_limited_allowed(self):
        session, user_id = self._free_session()
        response = session.get(
            f"{BASE_URL}/api/content/library/engagement-loop/{user_id}",
            timeout=15
        )
        assert response.status_code == 200, f"Expected limited access 200 for free user engagement-loop, got {response.status_code}"
        print(f"✓ Free user engagement-loop limited-allowed: {response.status_code}")

    def test_free_user_telemetry_limited_allowed(self):
        session, user_id = self._free_session()
        response = session.get(
            f"{BASE_URL}/api/content/library/recommendation-telemetry/{user_id}",
            timeout=15
        )
        assert response.status_code == 200, f"Expected limited access 200 for free user telemetry, got {response.status_code}"
        print(f"✓ Free user telemetry limited-allowed: {response.status_code}")
