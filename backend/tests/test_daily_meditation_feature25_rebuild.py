"""
Feature 25 Daily Meditation Rebuild - Comprehensive Backend Tests
Tests:
- Global entitlement enforcement via compute_effective_plan
- Identity hardening: non-admin cannot access another user_id (403)
- Admin-only protection on prayer-audio publish/catalog seed and reminder dispatch
- Core API flows for authenticated own user
- Mutation flows for authenticated own user
"""

import os
import pytest
import requests
import uuid
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"

ADMIN_USER_EMAIL = "watchvideos.phase4.admin.306786@example.com"
ADMIN_USER_PASSWORD = "Phase4Admin#2026Aa"

ADMIN_FALLBACK_EMAIL = "admin@realaicoach.app"
ADMIN_FALLBACK_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def free_user_session():
    """Login as free user and return session with cookies"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": FREE_USER_EMAIL,
        "password": FREE_USER_PASSWORD
    })
    
    if resp.status_code != 200:
        pytest.skip(f"Free user login failed: {resp.status_code} - {resp.text[:200]}")
    
    data = resp.json()
    user_id = data.get("user_id") or data.get("user", {}).get("user_id") or data.get("id")
    
    return {
        "session": session,
        "user_id": user_id,
        "email": FREE_USER_EMAIL,
        "plan": data.get("subscription_plan", "free")
    }


@pytest.fixture(scope="module")
def admin_user_session():
    """Login as admin user and return session with cookies"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Try primary admin
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_USER_EMAIL,
        "password": ADMIN_USER_PASSWORD
    })
    
    if resp.status_code != 200:
        # Try fallback admin
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_FALLBACK_EMAIL,
            "password": ADMIN_FALLBACK_PASSWORD
        })
    
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")
    
    data = resp.json()
    user_id = data.get("user_id") or data.get("user", {}).get("user_id") or data.get("id")
    
    return {
        "session": session,
        "user_id": user_id,
        "email": data.get("email", ADMIN_USER_EMAIL),
        "is_admin": data.get("is_admin", True)
    }


class TestDailyMeditationEntitlementEnforcement:
    """Test global entitlement enforcement uses compute_effective_plan"""
    
    def test_feature_map_returns_plan_based_features(self, free_user_session):
        """Feature map should return features based on user's effective plan"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map?user_id={user_id}")
        assert resp.status_code == 200, f"Feature map failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "plan" in data, "Response should include plan"
        assert "features" in data, "Response should include features"
        assert data["plan"] in ["free", "basic", "premium"], f"Invalid plan: {data['plan']}"
        
        # Verify features have availability based on plan
        features = data.get("features", [])
        assert len(features) > 0, "Should have features"
        
        for feat in features:
            assert "available" in feat, f"Feature {feat.get('feature_id')} missing 'available' field"
    
    def test_overview_returns_plan_and_limits(self, free_user_session):
        """Overview should return plan-based limits from compute_effective_plan"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/overview/{user_id}")
        assert resp.status_code == 200, f"Overview failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "plan" in data, "Response should include plan"
        assert "limits" in data, "Response should include limits"
        assert data["plan"] in ["free", "basic", "premium"], f"Invalid plan: {data['plan']}"
        
        # Verify limits structure
        limits = data.get("limits", {})
        assert "daily_checkins" in limits, "Limits should include daily_checkins"
        assert "daily_journal_entries" in limits, "Limits should include daily_journal_entries"


class TestDailyMeditationIdentityHardening:
    """Test identity hardening: non-admin cannot access another user_id"""
    
    def test_non_admin_cannot_access_other_user_overview(self, free_user_session):
        """Non-admin should get 403 when accessing another user's overview"""
        session = free_user_session["session"]
        
        # Try to access a different user's data
        fake_user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/overview/{fake_user_id}")
        assert resp.status_code == 403, f"Expected 403 for accessing other user, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        assert "detail" in data, "Error response should have detail"
        assert "another user" in data["detail"].lower() or "cannot access" in data["detail"].lower() or "access denied" in data["detail"].lower(), \
            f"Error message should indicate access denied: {data['detail']}"
    
    def test_non_admin_cannot_access_other_user_checkins(self, free_user_session):
        """Non-admin should get 403 when accessing another user's checkins"""
        session = free_user_session["session"]
        
        fake_user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/checkins/{fake_user_id}")
        assert resp.status_code == 403, f"Expected 403 for accessing other user checkins, got {resp.status_code}"
    
    def test_non_admin_cannot_access_other_user_journal(self, free_user_session):
        """Non-admin should get 403 when accessing another user's journal"""
        session = free_user_session["session"]
        
        fake_user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/journal/{fake_user_id}")
        assert resp.status_code == 403, f"Expected 403 for accessing other user journal, got {resp.status_code}"
    
    def test_non_admin_cannot_access_other_user_progress(self, free_user_session):
        """Non-admin should get 403 when accessing another user's progress"""
        session = free_user_session["session"]
        
        fake_user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/progress/{fake_user_id}")
        assert resp.status_code == 403, f"Expected 403 for accessing other user progress, got {resp.status_code}"
    
    def test_non_admin_cannot_access_other_user_notifications(self, free_user_session):
        """Non-admin should get 403 when accessing another user's notifications"""
        session = free_user_session["session"]
        
        fake_user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/notifications/{fake_user_id}")
        assert resp.status_code == 403, f"Expected 403 for accessing other user notifications, got {resp.status_code}"
    
    def test_admin_can_access_other_user_overview(self, admin_user_session, free_user_session):
        """Admin should be able to access another user's overview"""
        admin_session = admin_user_session["session"]
        free_user_id = free_user_session["user_id"]
        
        resp = admin_session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/overview/{free_user_id}")
        # Admin should get 200 or at least not 403
        assert resp.status_code != 403, f"Admin should not get 403: {resp.status_code}"
        assert resp.status_code == 200, f"Admin overview access failed: {resp.status_code} - {resp.text[:200]}"


class TestDailyMeditationAdminOnlyEndpoints:
    """Test admin-only protection on maintenance endpoints"""
    
    def test_non_admin_cannot_run_prayer_audio_publish(self, free_user_session):
        """Non-admin should get 401/403 on prayer-audio publish run-now"""
        session = free_user_session["session"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/publish/run-now",
            json={"force": False}
        )
        assert resp.status_code in [401, 403], \
            f"Expected 401/403 for non-admin publish, got {resp.status_code}: {resp.text[:200]}"
    
    def test_non_admin_cannot_run_catalog_seed(self, free_user_session):
        """Non-admin should get 401/403 on prayer-audio catalog seed run-now"""
        session = free_user_session["session"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/catalog/seed/run-now",
            json={"target_count": 600}
        )
        assert resp.status_code in [401, 403], \
            f"Expected 401/403 for non-admin catalog seed, got {resp.status_code}: {resp.text[:200]}"
    
    def test_non_admin_cannot_run_reminder_dispatch(self, free_user_session):
        """Non-admin should get 401/403 on reminder dispatch run-now"""
        session = free_user_session["session"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/reminders/dispatch/run-now",
            json={}
        )
        # This endpoint may not exist or may be admin-only
        assert resp.status_code in [401, 403, 404], \
            f"Expected 401/403/404 for non-admin reminder dispatch, got {resp.status_code}"
    
    def test_admin_can_run_prayer_audio_publish(self, admin_user_session):
        """Admin should be able to run prayer-audio publish"""
        session = admin_user_session["session"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/publish/run-now",
            json={"force": False}
        )
        assert resp.status_code == 200, f"Admin publish failed: {resp.status_code} - {resp.text[:200]}"
        
        data = resp.json()
        assert "status" in data, "Response should have status"
    
    def test_admin_can_run_catalog_seed(self, admin_user_session):
        """Admin should be able to run catalog seed"""
        session = admin_user_session["session"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/catalog/seed/run-now",
            json={"target_count": 600}
        )
        assert resp.status_code == 200, f"Admin catalog seed failed: {resp.status_code} - {resp.text[:200]}"
        
        data = resp.json()
        assert "status" in data, "Response should have status"


class TestDailyMeditationCoreAPIFlows:
    """Test core API flows for authenticated own user"""
    
    def test_feature_map_endpoint(self, free_user_session):
        """Test feature-map endpoint returns valid data"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map?user_id={user_id}")
        assert resp.status_code == 200, f"Feature map failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "tab" in data, "Should have tab field"
        assert "total_features" in data, "Should have total_features"
        assert "features" in data, "Should have features list"
        assert data["total_features"] > 0, "Should have features"
    
    def test_daily_gift_endpoint(self, free_user_session):
        """Test daily-gift endpoint returns valid gift"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/daily-gift/{user_id}")
        assert resp.status_code == 200, f"Daily gift failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "gift" in data, "Should have gift"
        assert "date" in data, "Should have date"
        
        gift = data.get("gift", {})
        assert "title" in gift, "Gift should have title"
        assert "scripture" in gift, "Gift should have scripture"
    
    def test_checkins_list_endpoint(self, free_user_session):
        """Test checkins list endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/checkins/{user_id}?limit=10")
        assert resp.status_code == 200, f"Checkins list failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "checkins" in data, "Should have checkins list"
    
    def test_journal_list_endpoint(self, free_user_session):
        """Test journal list endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/journal/{user_id}?limit=10")
        assert resp.status_code == 200, f"Journal list failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "entries" in data, "Should have entries list"
    
    def test_progress_endpoint(self, free_user_session):
        """Test progress endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/progress/{user_id}")
        assert resp.status_code == 200, f"Progress failed: {resp.text[:200]}"
        
        data = resp.json()
        # Progress endpoint should return progress data
        assert "user_id" in data or "progress_score" in data or "milestones" in data, \
            f"Progress response missing expected fields: {list(data.keys())}"
    
    def test_lookback_endpoint(self, free_user_session):
        """Test lookback endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/lookback/{user_id}?days=14")
        assert resp.status_code == 200, f"Lookback failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "summary" in data or "days" in data, "Lookback should have summary or days"
    
    def test_reminder_prefs_endpoint(self, free_user_session):
        """Test reminder preferences endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/reminders/prefs/{user_id}")
        assert resp.status_code == 200, f"Reminder prefs failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "preferences" in data or "in_app_enabled" in data, \
            "Should have preferences or in_app_enabled"
    
    def test_notifications_endpoint(self, free_user_session):
        """Test notifications endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/notifications/{user_id}")
        assert resp.status_code == 200, f"Notifications failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "notifications" in data, "Should have notifications list"


class TestDailyMeditationMutationFlows:
    """Test mutation flows for authenticated own user"""
    
    def test_checkin_create(self, free_user_session):
        """Test creating a check-in"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/checkin",
            json={
                "user_id": user_id,
                "heart_text": f"Test check-in from pytest {uuid.uuid4().hex[:8]}",
                "mood": "peaceful",
                "energy": 3,
                "tags": ["test"],
                "request_support": False
            }
        )
        
        # May hit rate limit, so accept 200 or 429
        assert resp.status_code in [200, 201, 429], \
            f"Checkin create failed: {resp.status_code} - {resp.text[:200]}"
        
        if resp.status_code in [200, 201]:
            data = resp.json()
            assert "checkin_id" in data or "status" in data, "Should have checkin_id or status"
    
    def test_journal_create(self, free_user_session):
        """Test creating a journal entry"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/journal",
            json={
                "user_id": user_id,
                "title": f"Test Journal {uuid.uuid4().hex[:8]}",
                "content": "This is a test journal entry from pytest.",
                "prayer_text": "Test prayer",
                "visibility": "private"
            }
        )
        
        # May hit rate limit
        assert resp.status_code in [200, 201, 429], \
            f"Journal create failed: {resp.status_code} - {resp.text[:200]}"
    
    def test_safety_check(self, free_user_session):
        """Test safety check endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/safety/check",
            json={
                "user_id": user_id,
                "text": "I am feeling peaceful and grateful today."
            }
        )
        
        assert resp.status_code == 200, f"Safety check failed: {resp.status_code} - {resp.text[:200]}"
        
        data = resp.json()
        assert "risk_level" in data, "Should have risk_level"
    
    def test_notifications_mark_read(self, free_user_session):
        """Test marking notifications as read"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/notifications/read",
            json={
                "user_id": user_id,
                "notification_timestamps": []
            }
        )
        
        assert resp.status_code == 200, f"Mark read failed: {resp.status_code} - {resp.text[:200]}"


class TestDailyMeditationPrayerAudioEndpoints:
    """Test prayer audio endpoints"""
    
    def test_prayer_audio_categories(self, free_user_session):
        """Test prayer audio categories endpoint"""
        session = free_user_session["session"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/categories")
        assert resp.status_code == 200, f"Categories failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "categories" in data, "Should have categories"
        assert "total" in data, "Should have total"
    
    def test_prayer_audio_today(self, free_user_session):
        """Test prayer audio today endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{user_id}")
        assert resp.status_code == 200, f"Today audio failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "items" in data, "Should have items"
        assert "published_date" in data, "Should have published_date"
    
    def test_prayer_audio_library(self, free_user_session):
        """Test prayer audio library endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/library/{user_id}?page=1&limit=10")
        assert resp.status_code == 200, f"Library failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "items" in data, "Should have items"
        assert "total" in data, "Should have total"
    
    def test_prayer_audio_catalog_stats(self, free_user_session):
        """Test prayer audio catalog stats endpoint"""
        session = free_user_session["session"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/catalog/stats")
        assert resp.status_code == 200, f"Catalog stats failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "audio_total" in data or "category_total" in data, "Should have audio or category total"


class TestDailyMeditationSomaticEndpoints:
    """Test somatic endpoints"""
    
    def test_somatic_library(self, free_user_session):
        """Test somatic library endpoint"""
        session = free_user_session["session"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/somatic/library")
        assert resp.status_code == 200, f"Somatic library failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "invitations" in data, "Should have invitations"


class TestDailyMeditationCommunityEndpoints:
    """Test community endpoints"""
    
    def test_community_feed(self, free_user_session):
        """Test community feed endpoint"""
        session = free_user_session["session"]
        user_id = free_user_session["user_id"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/community/feed/{user_id}?limit=10")
        assert resp.status_code == 200, f"Community feed failed: {resp.text[:200]}"
        
        data = resp.json()
        assert "posts" in data, "Should have posts"


class TestDailyMeditationEmailV7Compliance:
    """Feature 25 email path should use v7 catalog templates (no legacy raw helper path)."""

    def test_daily_meditation_email_template_mapping(self):
        source = Path("/app/backend/routes/travel_visa_daily_meditation.py").read_text(encoding="utf-8")
        assert 'DM_EMAIL_TEMPLATE_MAP = {' in source
        assert '"daily_meditation_reminder": "daily_meditation_reminder"' in source
        assert '"daily_meditation_prayer_audio_drop": "daily_meditation_prayer_audio_drop"' in source
        assert '"daily_meditation_weekly_digest": "daily_meditation_weekly_digest"' in source

    def test_send_dm_email_uses_catalog_template(self):
        source = Path("/app/backend/routes/travel_visa_daily_meditation.py").read_text(encoding="utf-8")
        assert "from utils.email_service import send_catalog_template" in source
        assert "send_catalog_template(" in source
        assert "from routes.travel_visa_ext import _send_email" not in source

    def test_feature25_templates_registered(self):
        source = Path("/app/backend/utils/email_templates.py").read_text(encoding="utf-8")
        assert '"daily_meditation_reminder"' in source
        assert '"daily_meditation_prayer_audio_drop"' in source
        assert '"daily_meditation_weekly_digest"' in source
        assert "def build_daily_meditation_reminder_email(" in source
        assert "def build_daily_meditation_prayer_audio_drop_email(" in source
        assert "def build_daily_meditation_weekly_digest_email(" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
