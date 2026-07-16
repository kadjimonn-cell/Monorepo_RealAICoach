"""
Travel Visa Deep Audit Test Suite
Tests all Travel Visa endpoints for the global system-level audit
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "tv.free.test@realaicoach.app"
FREE_USER_PASSWORD = "TvFree#2026!Aa"


@pytest.fixture(scope="module")
def admin_session():
    """Get admin session token"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        token = data.get("session_token") or data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, data.get("user_id")
    pytest.skip("Admin login failed")


@pytest.fixture(scope="module")
def free_user_session():
    """Get free user session token"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        token = data.get("session_token") or data.get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session, data.get("user_id")
    pytest.skip("Free user login failed")


class TestTravelVisaCoreAPIs:
    """Test core Travel Visa data endpoints"""
    
    def test_countries_endpoint(self, free_user_session):
        """Test /api/travel-visa/countries returns data"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/countries")
        assert response.status_code == 200, f"Countries endpoint failed: {response.text}"
        data = response.json()
        assert "countries" in data, "Missing 'countries' key"
        assert len(data["countries"]) > 0, "No countries returned"
        assert "regions" in data, "Missing 'regions' key"
        # Verify country structure
        country = data["countries"][0]
        assert "code" in country, "Country missing 'code'"
        assert "name" in country, "Country missing 'name'"
        assert "flag" in country, "Country missing 'flag'"
        assert "visa_types" in country, "Country missing 'visa_types'"
        print(f"✓ Countries endpoint: {len(data['countries'])} countries, {len(data['regions'])} regions")
    
    def test_trending_endpoint(self, free_user_session):
        """Test /api/travel-visa/trending returns data"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/trending")
        assert response.status_code == 200, f"Trending endpoint failed: {response.text}"
        data = response.json()
        assert "trending" in data, "Missing 'trending' key"
        assert len(data["trending"]) > 0, "No trending countries returned"
        print(f"✓ Trending endpoint: {len(data['trending'])} trending countries")
    
    def test_categories_endpoint(self, free_user_session):
        """Test /api/travel-visa/categories returns data"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/categories")
        assert response.status_code == 200, f"Categories endpoint failed: {response.text}"
        data = response.json()
        assert "categories" in data, "Missing 'categories' key"
        assert len(data["categories"]) > 0, "No categories returned"
        assert "groups" in data, "Missing 'groups' key"
        # Verify category structure
        category = data["categories"][0]
        assert "id" in category, "Category missing 'id'"
        assert "name" in category, "Category missing 'name'"
        assert "group" in category, "Category missing 'group'"
        print(f"✓ Categories endpoint: {len(data['categories'])} categories, {len(data['groups'])} groups")
    
    def test_lessons_endpoint(self, free_user_session):
        """Test /api/travel-visa/lessons returns data"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/lessons")
        assert response.status_code == 200, f"Lessons endpoint failed: {response.text}"
        data = response.json()
        assert "lessons" in data, "Missing 'lessons' key"
        print(f"✓ Lessons endpoint: {len(data.get('lessons', []))} lessons")
    
    def test_quizzes_endpoint(self, free_user_session):
        """Test /api/travel-visa/quizzes returns data"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/quizzes")
        assert response.status_code == 200, f"Quizzes endpoint failed: {response.text}"
        data = response.json()
        assert "quizzes" in data, "Missing 'quizzes' key"
        assert len(data["quizzes"]) > 0, "No quizzes returned"
        # Verify quiz structure
        quiz = data["quizzes"][0]
        assert "quiz_id" in quiz, "Quiz missing 'quiz_id'"
        assert "title" in quiz, "Quiz missing 'title'"
        print(f"✓ Quizzes endpoint: {len(data['quizzes'])} quizzes")
    
    def test_embassies_endpoint(self, free_user_session):
        """Test /api/travel-visa/embassies returns data"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/embassies")
        assert response.status_code == 200, f"Embassies endpoint failed: {response.text}"
        data = response.json()
        assert "embassies" in data, "Missing 'embassies' key"
        assert len(data["embassies"]) > 0, "No embassies returned"
        print(f"✓ Embassies endpoint: {len(data['embassies'])} embassies")


class TestTravelVisaUserFeatures:
    """Test user-specific Travel Visa features"""
    
    def test_user_progress(self, free_user_session):
        """Test /api/travel-visa/progress/{user_id}"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/progress/{user_id}")
        assert response.status_code == 200, f"Progress endpoint failed: {response.text}"
        data = response.json()
        assert "stats" in data, "Missing 'stats' key"
        print("✓ User progress endpoint working")
    
    def test_subscription_info(self, free_user_session):
        """Test /api/travel-visa/subscription/info/{user_id}"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/subscription/info/{user_id}")
        assert response.status_code == 200, f"Subscription info failed: {response.text}"
        data = response.json()
        assert "plan" in data, "Missing 'plan' key"
        assert "limits" in data, "Missing 'limits' key"
        print(f"✓ Subscription info endpoint: plan={data['plan']}")
    
    def test_search_endpoint(self, free_user_session):
        """Test /api/travel-visa/search"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/search?q=united")
        assert response.status_code == 200, f"Search endpoint failed: {response.text}"
        data = response.json()
        assert "countries" in data or "categories" in data or "lessons" in data, "Search returned no results structure"
        print("✓ Search endpoint working")
    
    def test_leaderboard_weekly(self, free_user_session):
        """Test /api/travel-visa/leaderboard/weekly"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/leaderboard/weekly")
        assert response.status_code == 200, f"Leaderboard weekly failed: {response.text}"
        data = response.json()
        assert "leaderboard" in data, "Missing 'leaderboard' key"
        print(f"✓ Leaderboard weekly endpoint: {len(data.get('leaderboard', []))} entries")
    
    def test_leaderboard_alltime(self, free_user_session):
        """Test /api/travel-visa/leaderboard/alltime"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/leaderboard/alltime")
        assert response.status_code == 200, f"Leaderboard alltime failed: {response.text}"
        data = response.json()
        assert "leaderboard" in data, "Missing 'leaderboard' key"
        print(f"✓ Leaderboard alltime endpoint: {len(data.get('leaderboard', []))} entries")


class TestTravelVisaNotifications:
    """Test notification features"""
    
    def test_notification_prefs(self, free_user_session):
        """Test /api/travel-visa/notifications/prefs/{user_id}"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/notifications/prefs/{user_id}")
        assert response.status_code == 200, f"Notification prefs failed: {response.text}"
        data = response.json()
        assert "preferences" in data, "Missing 'preferences' key"
        print("✓ Notification prefs endpoint working")
    
    def test_notifications_list(self, free_user_session):
        """Test /api/travel-visa/notifications/{user_id}"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/notifications/{user_id}")
        assert response.status_code == 200, f"Notifications list failed: {response.text}"
        data = response.json()
        assert "notifications" in data, "Missing 'notifications' key"
        print(f"✓ Notifications list endpoint: {len(data.get('notifications', []))} notifications")


class TestTravelVisaChallenges:
    """Test challenge features"""
    
    def test_challenge_list(self, free_user_session):
        """Test /api/travel-visa/challenge/list/{user_id}"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/challenge/list/{user_id}")
        assert response.status_code == 200, f"Challenge list failed: {response.text}"
        data = response.json()
        assert "challenges" in data, "Missing 'challenges' key"
        print(f"✓ Challenge list endpoint: {len(data.get('challenges', []))} challenges")


class TestTravelVisaAchievements:
    """Test achievement features"""
    
    def test_achievements_catalog(self, free_user_session):
        """Test /api/travel-visa/achievements/catalog"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/achievements/catalog")
        assert response.status_code == 200, f"Achievements catalog failed: {response.text}"
        data = response.json()
        assert "achievements" in data, "Missing 'achievements' key"
        print(f"✓ Achievements catalog: {len(data.get('achievements', []))} achievements")
    
    def test_user_achievements(self, free_user_session):
        """Test /api/travel-visa/achievements/{user_id}"""
        session, user_id = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/achievements/{user_id}")
        assert response.status_code == 200, f"User achievements failed: {response.text}"
        data = response.json()
        assert "earned" in data, "Missing 'earned' key"
        assert "catalog" in data, "Missing 'catalog' key"
        print(f"✓ User achievements: {len(data.get('earned', []))} earned")


class TestTravelVisaDailyLessons:
    """Test daily lessons feature"""
    
    def test_daily_lessons(self, free_user_session):
        """Test /api/travel-visa/daily-lessons"""
        session, _ = free_user_session
        response = session.get(f"{BASE_URL}/api/travel-visa/daily-lessons")
        assert response.status_code == 200, f"Daily lessons failed: {response.text}"
        data = response.json()
        assert "lessons" in data, "Missing 'lessons' key"
        assert "date" in data, "Missing 'date' key"
        print(f"✓ Daily lessons: {len(data.get('lessons', []))} lessons for {data.get('date')}")


class TestTravelVisaMedia:
    """Test media/video/audio features"""
    
    def test_media_lessons(self, free_user_session):
        """Test /api/travel-visa/lessons with type filter"""
        session, _ = free_user_session
        # Test video lessons
        response = session.get(f"{BASE_URL}/api/travel-visa/lessons")
        assert response.status_code == 200, f"Lessons endpoint failed: {response.text}"
        data = response.json()
        lessons = data.get("lessons", [])
        video_lessons = [lesson for lesson in lessons if lesson.get("type") == "video"]
        audio_lessons = [lesson for lesson in lessons if lesson.get("type") == "audio"]
        print(f"✓ Media lessons: {len(video_lessons)} video, {len(audio_lessons)} audio")


class TestTravelVisaSeedData:
    """Test seed data endpoint"""
    
    def test_seed_endpoint(self, admin_session):
        """Test /api/travel-visa/seed (admin only)"""
        session, _ = admin_session
        response = session.post(f"{BASE_URL}/api/travel-visa/seed")
        assert response.status_code == 200, f"Seed endpoint failed: {response.text}"
        data = response.json()
        assert "status" in data, "Missing 'status' key"
        print(f"✓ Seed endpoint: {data}")


class TestTravelVisaAdminStats:
    """Test admin stats endpoint"""
    
    def test_admin_stats(self, admin_session):
        """Test /api/travel-visa/admin/stats"""
        session, _ = admin_session
        response = session.get(f"{BASE_URL}/api/travel-visa/admin/stats")
        assert response.status_code == 200, f"Admin stats failed: {response.text}"
        data = response.json()
        assert "total_users" in data or "total_lessons" in data, "Missing expected stats keys"
        print("✓ Admin stats endpoint working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
