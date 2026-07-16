"""
Travel Visa P0 Auth & Authorization Test Suite
Tests:
1. Route-level auth enforcement (401 for unauthenticated)
2. User-scope authorization (403 for accessing another user's resources)
3. Admin-only endpoint enforcement (403 for non-admin users)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "tv.free.test@realaicoach.app"
FREE_USER_PASSWORD = "TvFree#2026!Aa"
FREE_USER_ID = "user_b64e4f3053ec"


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session token and user_id"""
    session = requests.Session()
    session.headers.update({"X-Client-Platform": "native"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        token = data.get("session_token") or data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, data.get("user_id")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def free_user_session():
    """Get free user session token and user_id"""
    session = requests.Session()
    session.headers.update({"X-Client-Platform": "native"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        token = data.get("session_token") or data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, data.get("user_id")
    pytest.skip(f"Free user login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def unauthenticated_session():
    """Session without auth token"""
    return requests.Session()


class TestRouteAuthEnforcement:
    """Test that Travel Visa routes require authentication (401 for unauthenticated)"""
    
    def test_countries_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/countries should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/countries")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /countries returns 401 for unauthenticated requests")
    
    def test_trending_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/trending should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/trending")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /trending returns 401 for unauthenticated requests")
    
    def test_categories_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/categories should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/categories")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /categories returns 401 for unauthenticated requests")
    
    def test_lessons_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/lessons should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/lessons")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /lessons returns 401 for unauthenticated requests")
    
    def test_quizzes_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/quizzes should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/quizzes")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /quizzes returns 401 for unauthenticated requests")
    
    def test_embassies_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/embassies should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/embassies")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /embassies returns 401 for unauthenticated requests")
    
    def test_search_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/search should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/search?q=united")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /search returns 401 for unauthenticated requests")
    
    def test_leaderboard_weekly_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/leaderboard/weekly should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/leaderboard/weekly")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /leaderboard/weekly returns 401 for unauthenticated requests")
    
    def test_daily_lessons_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/daily-lessons should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/daily-lessons")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /daily-lessons returns 401 for unauthenticated requests")
    
    def test_achievements_catalog_requires_auth(self, unauthenticated_session):
        """GET /api/travel-visa/achievements/catalog should return 401 without auth"""
        response = unauthenticated_session.get(f"{BASE_URL}/api/travel-visa/achievements/catalog")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("✓ /achievements/catalog returns 401 for unauthenticated requests")


class TestUserScopeAuthorization:
    """Test that users cannot access another user's resources (403 for scope mismatch)"""
    
    def test_progress_user_scope(self, free_user_session):
        """GET /api/travel-visa/progress/{other_user_id} should return 403"""
        session, user_id = free_user_session
        # Try to access another user's progress
        response = session.get(f"{BASE_URL}/api/travel-visa/progress/some-other-user")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /progress/{user_id} returns 403 for user scope mismatch")
    
    def test_progress_own_user_allowed(self, free_user_session):
        """GET /api/travel-visa/progress/{own_user_id} should return 200"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/progress/{user_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ /progress/{user_id} returns 200 for own user")
    
    def test_subscription_info_user_scope(self, free_user_session):
        """GET /api/travel-visa/subscription/info/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/subscription/info/another-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /subscription/info/{user_id} returns 403 for user scope mismatch")
    
    def test_subscription_info_own_user_allowed(self, free_user_session):
        """GET /api/travel-visa/subscription/info/{own_user_id} should return 200"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/subscription/info/{user_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ /subscription/info/{user_id} returns 200 for own user")
    
    def test_achievements_user_scope(self, free_user_session):
        """GET /api/travel-visa/achievements/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/achievements/different-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /achievements/{user_id} returns 403 for user scope mismatch")
    
    def test_notifications_user_scope(self, free_user_session):
        """GET /api/travel-visa/notifications/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/notifications/other-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /notifications/{user_id} returns 403 for user scope mismatch")
    
    def test_notification_prefs_user_scope(self, free_user_session):
        """GET /api/travel-visa/notifications/prefs/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/notifications/prefs/other-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /notifications/prefs/{user_id} returns 403 for user scope mismatch")
    
    def test_challenge_list_user_scope(self, free_user_session):
        """GET /api/travel-visa/challenge/list/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/challenge/list/other-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /challenge/list/{user_id} returns 403 for user scope mismatch")
    
    def test_coaching_history_user_scope(self, free_user_session):
        """GET /api/travel-visa/coaching/history/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/coaching/history/other-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /coaching/history/{user_id} returns 403 for user scope mismatch")
    
    def test_interview_history_user_scope(self, free_user_session):
        """GET /api/travel-visa/interview/history/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/interview/history/other-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /interview/history/{user_id} returns 403 for user scope mismatch")
    
    def test_saved_content_user_scope(self, free_user_session):
        """GET /api/travel-visa/saved/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/saved/other-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /saved/{user_id} returns 403 for user scope mismatch")
    
    def test_readiness_user_scope(self, free_user_session):
        """GET /api/travel-visa/readiness/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/readiness/other-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /readiness/{user_id} returns 403 for user scope mismatch")
    
    def test_leaderboard_me_user_scope(self, free_user_session):
        """GET /api/travel-visa/leaderboard/me/{other_user_id} should return 403"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/leaderboard/me/other-user-id")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /leaderboard/me/{user_id} returns 403 for user scope mismatch")


class TestAdminOnlyEndpoints:
    """Test that admin-only endpoints return 403 for non-admin users"""
    
    def test_admin_stats_non_admin(self, free_user_session):
        """GET /api/travel-visa/admin/stats should return 403 for non-admin"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/admin/stats")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /admin/stats returns 403 for non-admin users")
    
    def test_admin_stats_admin_allowed(self, admin_session):
        """GET /api/travel-visa/admin/stats should return 200 for admin"""
        session, user_id = admin_session
        response = session.get(f"{BASE_URL}/api/travel-visa/admin/stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /admin/stats returns 200 for admin users")
    
    def test_admin_engagement_non_admin(self, free_user_session):
        """GET /api/travel-visa/admin/engagement should return 403 for non-admin"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/admin/engagement")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /admin/engagement returns 403 for non-admin users")
    
    def test_admin_engagement_admin_allowed(self, admin_session):
        """GET /api/travel-visa/admin/engagement should return 200 for admin"""
        session, user_id = admin_session
        response = session.get(f"{BASE_URL}/api/travel-visa/admin/engagement")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ /admin/engagement returns 200 for admin users")
    
    def test_seed_non_admin(self, free_user_session):
        """POST /api/travel-visa/seed should return 403 for non-admin"""
        session, user_id = free_user_session
        response = session.post(f"{BASE_URL}/api/travel-visa/seed")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ /seed returns 403 for non-admin users")


class TestAuthenticatedDataAccess:
    """Test that authenticated users can access Travel Visa data"""
    
    def test_countries_authenticated(self, free_user_session):
        """GET /api/travel-visa/countries should return data for authenticated user"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/countries")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "countries" in data, "Missing 'countries' key"
        assert len(data["countries"]) > 0, "No countries returned"
        print(f"✓ /countries returns {len(data['countries'])} countries for authenticated user")
    
    def test_trending_authenticated(self, free_user_session):
        """GET /api/travel-visa/trending should return data for authenticated user"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/trending")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "trending" in data, "Missing 'trending' key"
        print(f"✓ /trending returns {len(data.get('trending', []))} trending destinations")
    
    def test_categories_authenticated(self, free_user_session):
        """GET /api/travel-visa/categories should return data for authenticated user"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/categories")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "categories" in data, "Missing 'categories' key"
        print(f"✓ /categories returns {len(data.get('categories', []))} categories")
    
    def test_quizzes_authenticated(self, free_user_session):
        """GET /api/travel-visa/quizzes should return data for authenticated user"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/quizzes")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "quizzes" in data, "Missing 'quizzes' key"
        print(f"✓ /quizzes returns {len(data.get('quizzes', []))} quizzes")
    
    def test_leaderboard_weekly_authenticated(self, free_user_session):
        """GET /api/travel-visa/leaderboard/weekly should return data for authenticated user"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/leaderboard/weekly")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "leaderboard" in data, "Missing 'leaderboard' key"
        print(f"✓ /leaderboard/weekly returns {len(data.get('leaderboard', []))} entries")
    
    def test_leaderboard_alltime_authenticated(self, free_user_session):
        """GET /api/travel-visa/leaderboard/alltime should return data for authenticated user"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/leaderboard/alltime")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "leaderboard" in data, "Missing 'leaderboard' key"
        print(f"✓ /leaderboard/alltime returns {len(data.get('leaderboard', []))} entries")


class TestAdminCanAccessUserResources:
    """Test that admin can access any user's resources (admin bypass)"""
    
    def test_admin_can_access_any_user_progress(self, admin_session):
        """Admin should be able to access any user's progress"""
        session, admin_user_id = admin_session
        # Admin accessing free user's progress
        response = session.get(f"{BASE_URL}/api/travel-visa/progress/{FREE_USER_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Admin can access user {FREE_USER_ID}'s progress")
    
    def test_admin_can_access_any_user_subscription(self, admin_session):
        """Admin should be able to access any user's subscription info"""
        session, admin_user_id = admin_session
        response = session.get(f"{BASE_URL}/api/travel-visa/subscription/info/{FREE_USER_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Admin can access user {FREE_USER_ID}'s subscription info")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
