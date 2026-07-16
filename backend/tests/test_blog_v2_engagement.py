"""
Blog V2 Engagement Loop API Tests
Tests for Read Streak + Smart Reminders feature (Checkpoint A-D)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
BASIC_USER_EMAIL = "f22.basic.20260613@example.com"
BASIC_USER_PASSWORD = "F22Basic#2026Aa"
PREMIUM_USER_EMAIL = "f22.premium.20260613@example.com"
PREMIUM_USER_PASSWORD = "F22Premium#2026Aa"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    return session


@pytest.fixture(scope="module")
def basic_user_session(api_client):
    """Login as basic user and return session"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": BASIC_USER_EMAIL,
        "password": BASIC_USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Basic user login failed: {response.status_code}")
    return api_client


@pytest.fixture(scope="module")
def premium_user_session():
    """Login as premium user and return session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": PREMIUM_USER_EMAIL,
        "password": PREMIUM_USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Premium user login failed: {response.status_code}")
    return session


class TestGuestEngagementLoop:
    """Tests for unauthenticated/guest engagement loop behavior"""

    def test_home_includes_engagement_loop_for_guest(self, api_client):
        """GET /api/blog/v2/home includes engagement_loop payload for guest"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        
        data = response.json()
        assert "engagement_loop" in data, "engagement_loop missing from home response"
        
        loop = data["engagement_loop"]
        assert "streak" in loop
        assert "reminder" in loop
        assert "conversion_trigger" in loop

    def test_guest_engagement_loop_has_signin_required_status(self, api_client):
        """Guest engagement_loop should have signin_required reminder status"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        
        data = response.json()
        loop = data["engagement_loop"]
        
        # Verify signin_required status for guest
        assert loop["reminder"]["status"] == "signin_required"
        assert loop["reminder"]["enabled"] == False
        assert loop["reminder"]["recommended_action"] == "signin"
        assert "Sign in" in loop["reminder"]["message"]

    def test_guest_engagement_loop_endpoint(self, api_client):
        """GET /api/blog/v2/engagement-loop returns signin_required for guest"""
        # Create fresh session without auth
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/engagement-loop")
        assert response.status_code == 200
        
        data = response.json()
        assert "engagement_loop" in data
        assert data["engagement_loop"]["reminder"]["status"] == "signin_required"

    def test_guest_streak_is_zero(self, api_client):
        """Guest should have zero streak"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        
        data = response.json()
        loop = data["engagement_loop"]
        
        assert loop["streak"]["current"] == 0
        assert loop["streak"]["longest"] == 0
        assert loop["streak"]["last_read_date"] == ""


class TestAuthenticatedEngagementLoop:
    """Tests for authenticated user engagement loop behavior"""

    def test_authenticated_engagement_loop_endpoint(self, basic_user_session):
        """GET /api/blog/v2/engagement-loop returns authenticated reminder mode/status"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/engagement-loop")
        assert response.status_code == 200
        
        data = response.json()
        assert "engagement_loop" in data
        assert "viewer_plan" in data
        
        loop = data["engagement_loop"]
        # Authenticated user should NOT have signin_required status
        assert loop["reminder"]["status"] != "signin_required"
        assert loop["reminder"]["enabled"] == True
        assert loop["reminder"]["mode"] in ["adaptive", "daily", "three_per_week"]

    def test_authenticated_home_includes_engagement_loop(self, basic_user_session):
        """GET /api/blog/v2/home includes engagement_loop for authenticated user"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        
        data = response.json()
        assert "engagement_loop" in data
        
        loop = data["engagement_loop"]
        # Should have real streak data
        assert "streak" in loop
        assert isinstance(loop["streak"]["current"], int)
        assert isinstance(loop["streak"]["longest"], int)


class TestWriteHistoryUpdatesStreak:
    """Tests for write history updating streak"""

    def test_write_history_returns_engagement_loop(self, basic_user_session):
        """POST /api/blog/v2/me/history returns engagement_loop with streak"""
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/history", json={
            "post_id": "blogv2-0002",
            "progress_percent": 75,
            "dwell_seconds": 180
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        assert "engagement_loop" in data
        
        loop = data["engagement_loop"]
        # After writing history, streak should be >= 1
        assert loop["streak"]["current"] >= 1
        assert loop["streak"]["last_read_date"] != ""

    def test_write_history_updates_streak_current(self, basic_user_session):
        """Writing history should update streak.current to >= 1"""
        # First get current streak
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/engagement-loop")
        assert response.status_code == 200
        response.json()["engagement_loop"]["streak"]["current"]
        
        # Write history
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/history", json={
            "post_id": "blogv2-0003",
            "progress_percent": 100,
            "dwell_seconds": 300
        })
        assert response.status_code == 200
        
        new_streak = response.json()["engagement_loop"]["streak"]["current"]
        # Streak should be at least 1 after reading
        assert new_streak >= 1


class TestReminderSettings:
    """Tests for reminder settings PATCH endpoint"""

    def test_update_reminder_mode_to_daily(self, basic_user_session):
        """PATCH /api/blog/v2/me/reminder-settings updates mode to daily"""
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "mode": "daily"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        assert "engagement_loop" in data
        assert data["engagement_loop"]["reminder"]["mode"] == "daily"

    def test_update_reminder_mode_to_adaptive(self, basic_user_session):
        """PATCH /api/blog/v2/me/reminder-settings updates mode to adaptive"""
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "mode": "adaptive"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        assert data["engagement_loop"]["reminder"]["mode"] == "adaptive"

    def test_update_reminder_mode_to_three_per_week(self, basic_user_session):
        """PATCH /api/blog/v2/me/reminder-settings updates mode to three_per_week"""
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "mode": "three_per_week"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        assert data["engagement_loop"]["reminder"]["mode"] == "three_per_week"

    def test_update_reminder_settings_returns_updated_loop(self, basic_user_session):
        """PATCH should return the updated engagement_loop"""
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "mode": "daily"
        })
        assert response.status_code == 200
        
        data = response.json()
        loop = data["engagement_loop"]
        
        # Verify full loop structure
        assert "streak" in loop
        assert "reminder" in loop
        assert "conversion_trigger" in loop
        assert loop["reminder"]["enabled"] == True

    def test_reminder_settings_requires_auth(self):
        """PATCH /api/blog/v2/me/reminder-settings requires authentication"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "mode": "daily"
        })
        # 401 Unauthorized or 403 Forbidden (CSRF protection) are both acceptable
        assert response.status_code in [401, 403]


class TestReminderAction:
    """Tests for reminder action POST endpoint"""

    def test_snooze_24h_sets_snoozed_status(self, basic_user_session):
        """POST /api/blog/v2/me/reminder-action with snooze_24h sets status to snoozed"""
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/reminder-action", json={
            "action": "snooze_24h"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        assert "engagement_loop" in data
        
        loop = data["engagement_loop"]
        assert loop["reminder"]["status"] == "snoozed"
        assert loop["reminder"]["snoozed_until"] != ""

    def test_snooze_24h_sets_snoozed_until(self, basic_user_session):
        """POST snooze_24h should set snoozed_until timestamp"""
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/reminder-action", json={
            "action": "snooze_24h"
        })
        assert response.status_code == 200
        
        data = response.json()
        snoozed_until = data["engagement_loop"]["reminder"]["snoozed_until"]
        
        # Should be a valid ISO timestamp
        assert snoozed_until != ""
        assert "T" in snoozed_until  # ISO format check

    def test_dismiss_action(self, basic_user_session):
        """POST /api/blog/v2/me/reminder-action with dismiss clears snooze"""
        # First snooze
        basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/reminder-action", json={
            "action": "snooze_24h"
        })
        
        # Then dismiss
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/reminder-action", json={
            "action": "dismiss"
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        # After dismiss, snoozed_until should be cleared
        assert data["engagement_loop"]["reminder"]["snoozed_until"] == ""

    def test_reminder_action_requires_auth(self):
        """POST /api/blog/v2/me/reminder-action requires authentication"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.post(f"{BASE_URL}/api/blog/v2/me/reminder-action", json={
            "action": "snooze_24h"
        })
        # 401 Unauthorized or 403 Forbidden (CSRF protection) are both acceptable
        assert response.status_code in [401, 403]


class TestConversionTrigger:
    """Tests for conversion trigger behavior"""

    def test_conversion_trigger_structure(self, basic_user_session):
        """Verify conversion_trigger has required fields"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/engagement-loop")
        assert response.status_code == 200
        
        data = response.json()
        trigger = data["engagement_loop"]["conversion_trigger"]
        
        assert "show_upgrade_nudge" in trigger
        assert "reason" in trigger
        assert "streak_threshold" in trigger
        assert "locked_premium_available" in trigger
        assert trigger["streak_threshold"] == 3

    def test_member_does_not_see_upgrade_nudge(self, basic_user_session):
        """Basic/Premium members should not see upgrade nudge"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/engagement-loop")
        assert response.status_code == 200
        
        data = response.json()
        # Basic user is a member, should not see upgrade nudge
        assert data["engagement_loop"]["conversion_trigger"]["show_upgrade_nudge"] == False


class TestExistingBlogRoutes:
    """Regression tests for existing Blog routes"""

    def test_blog_home_endpoint(self, api_client):
        """GET /api/blog/v2/home returns expected structure"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        
        data = response.json()
        assert "featured" in data
        assert "trending" in data
        assert "latest" in data
        assert "categories" in data
        assert "authors" in data
        assert "stats" in data
        assert "viewer_plan" in data

    def test_blog_posts_list(self, api_client):
        """GET /api/blog/v2/posts returns paginated list"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/posts")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "has_next" in data
        assert len(data["items"]) > 0

    def test_blog_post_detail(self, api_client):
        """GET /api/blog/v2/posts/{slug} returns post detail"""
        # First get a valid slug
        list_response = api_client.get(f"{BASE_URL}/api/blog/v2/posts")
        slug = list_response.json()["items"][0]["slug"]
        
        response = api_client.get(f"{BASE_URL}/api/blog/v2/posts/{slug}")
        assert response.status_code == 200
        
        data = response.json()
        assert "title" in data
        assert "content_blocks" in data
        assert "author" in data or "author_name" in data

    def test_blog_author_profile(self, api_client):
        """GET /api/blog/v2/authors/{author_slug} returns author profile"""
        # First get a valid author slug
        home_response = api_client.get(f"{BASE_URL}/api/blog/v2/home")
        author_slug = home_response.json()["authors"][0]["author_slug"]
        
        response = api_client.get(f"{BASE_URL}/api/blog/v2/authors/{author_slug}")
        assert response.status_code == 200
        
        data = response.json()
        assert "author" in data
        assert "posts" in data

    def test_blog_recommendations(self, api_client):
        """GET /api/blog/v2/recommendations returns recommendations"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/recommendations")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data

    def test_blog_bookmarks_requires_auth(self):
        """GET /api/blog/v2/me/bookmarks requires authentication"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/me/bookmarks")
        assert response.status_code == 401

    def test_blog_history_requires_auth(self):
        """GET /api/blog/v2/me/history requires authentication"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/me/history")
        assert response.status_code == 401

    def test_authenticated_bookmarks(self, basic_user_session):
        """GET /api/blog/v2/me/bookmarks works for authenticated user"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/bookmarks")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data

    def test_authenticated_history(self, basic_user_session):
        """GET /api/blog/v2/me/history works for authenticated user"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/history")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
