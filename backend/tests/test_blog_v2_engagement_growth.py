"""
Blog V2 Engagement Growth Features API Tests
Tests for: rewards, next-best sequencing, weekly-digest, referral-claim, digest toggles
Checkpoint A-D mandatory features
"""

import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
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


class TestRewardsEndpoint:
    """Tests for GET /api/blog/v2/me/rewards endpoint"""

    def test_rewards_endpoint_returns_200(self, basic_user_session):
        """GET /api/blog/v2/me/rewards returns 200 for authenticated user"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200

    def test_rewards_contains_streak_data(self, basic_user_session):
        """Rewards response contains streak data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        assert "streak" in data
        assert "current" in data["streak"]
        assert "longest" in data["streak"]
        assert "badges" in data["streak"]
        assert "next_milestone" in data["streak"]

    def test_rewards_contains_rewards_data(self, basic_user_session):
        """Rewards response contains rewards wallet data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        assert "rewards" in data
        assert "unlock_tokens" in data["rewards"]
        assert "premium_preview_unlocks_used" in data["rewards"]
        assert "referral_bonus_days_total" in data["rewards"]
        assert "invite_code" in data["rewards"]
        assert "invite_link" in data["rewards"]
        assert "referrals_count" in data["rewards"]

    def test_rewards_contains_unlockables(self, basic_user_session):
        """Rewards response contains unlockables data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        assert "unlockables" in data
        assert "premium_preview_tokens" in data["unlockables"]
        assert "available" in data["unlockables"]

    def test_rewards_contains_referral_data(self, basic_user_session):
        """Rewards response contains referral data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        assert "referral" in data
        assert "invite_code" in data["referral"]
        assert "invite_link" in data["referral"]
        assert "referrals_count" in data["referral"]
        assert "bonus_days_total" in data["referral"]

    def test_rewards_contains_weekly_digest(self, basic_user_session):
        """Rewards response contains weekly_digest data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        assert "weekly_digest" in data
        assert "week_key" in data["weekly_digest"]
        assert "generated_at" in data["weekly_digest"]
        assert "headline" in data["weekly_digest"]

    def test_rewards_contains_next_best(self, basic_user_session):
        """Rewards response contains next_best data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        assert "next_best" in data
        assert "week_key" in data["next_best"]
        assert "strategy" in data["next_best"]
        assert "items" in data["next_best"]

    def test_rewards_requires_auth(self):
        """GET /api/blog/v2/me/rewards requires authentication"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 401


class TestNextBestEndpoint:
    """Tests for GET /api/blog/v2/next-best endpoint"""

    def test_next_best_returns_200(self, basic_user_session):
        """GET /api/blog/v2/next-best returns 200 for authenticated user"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/next-best")
        assert response.status_code == 200

    def test_next_best_contains_strategy(self, basic_user_session):
        """Next-best response contains hybrid strategy info"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/next-best")
        assert response.status_code == 200
        
        data = response.json()
        assert "strategy" in data
        assert data["strategy"] == "hybrid_rules_gpt52"

    def test_next_best_contains_week_key(self, basic_user_session):
        """Next-best response contains week_key"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/next-best")
        assert response.status_code == 200
        
        data = response.json()
        assert "week_key" in data
        # Week key format: YYYY-WNN
        assert "-W" in data["week_key"]

    def test_next_best_contains_items(self, basic_user_session):
        """Next-best response contains items array"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/next-best")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_next_best_items_have_sequence_reason(self, basic_user_session):
        """Next-best items have sequence_reason field"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/next-best")
        assert response.status_code == 200
        
        data = response.json()
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "sequence_reason" in item
            assert "post_id" in item
            assert "slug" in item
            assert "title" in item

    def test_next_best_with_limit_param(self, basic_user_session):
        """Next-best respects limit parameter"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/next-best?limit=3")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) <= 3

    def test_next_best_with_refresh_param(self, basic_user_session):
        """Next-best supports refresh parameter"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/next-best?refresh=true")
        assert response.status_code == 200
        
        data = response.json()
        assert "source" in data
        # When refresh=true, source should be "fresh"
        assert data["source"] == "fresh"

    def test_next_best_requires_auth(self):
        """GET /api/blog/v2/next-best requires authentication"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/next-best")
        assert response.status_code == 401


class TestWeeklyDigestEndpoint:
    """Tests for GET /api/blog/v2/weekly-digest endpoint"""

    def test_weekly_digest_returns_200(self, basic_user_session):
        """GET /api/blog/v2/weekly-digest returns 200 for authenticated user"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/weekly-digest")
        assert response.status_code == 200

    def test_weekly_digest_contains_digest_data(self, basic_user_session):
        """Weekly digest response contains digest data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/weekly-digest")
        assert response.status_code == 200
        
        data = response.json()
        assert "digest" in data
        assert "week_key" in data["digest"]
        assert "generated_at" in data["digest"]
        assert "headline" in data["digest"]
        assert "highlights" in data["digest"]

    def test_weekly_digest_contains_next_best(self, basic_user_session):
        """Weekly digest response contains next_best data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/weekly-digest")
        assert response.status_code == 200
        
        data = response.json()
        assert "next_best" in data["digest"]
        assert "items" in data["digest"]["next_best"]

    def test_weekly_digest_with_refresh_param(self, basic_user_session):
        """Weekly digest supports refresh parameter"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/weekly-digest?refresh=true")
        assert response.status_code == 200
        
        data = response.json()
        assert "digest" in data

    def test_weekly_digest_with_send_email_param(self, basic_user_session):
        """Weekly digest supports send_email parameter and returns email_result"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/weekly-digest?send_email=true")
        assert response.status_code == 200
        
        data = response.json()
        assert "digest" in data
        assert "email_result" in data
        # email_result can be null or an object with ok/status/reason

    def test_weekly_digest_requires_auth(self):
        """GET /api/blog/v2/weekly-digest requires authentication"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/weekly-digest")
        assert response.status_code == 401


class TestDigestSettingsToggle:
    """Tests for digest settings toggles in PATCH /api/blog/v2/me/reminder-settings"""

    def test_toggle_digest_in_app_enabled(self, basic_user_session):
        """PATCH supports digest_in_app_enabled toggle"""
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "digest_in_app_enabled": False
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        assert "engagement_loop" in data
        assert data["engagement_loop"]["reminder"]["digest"]["in_app_enabled"] == False
        
        # Toggle back on
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "digest_in_app_enabled": True
        })
        assert response.status_code == 200
        assert response.json()["engagement_loop"]["reminder"]["digest"]["in_app_enabled"] == True

    def test_toggle_digest_email_enabled(self, basic_user_session):
        """PATCH supports digest_email_enabled toggle"""
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "digest_email_enabled": False
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        assert data["engagement_loop"]["reminder"]["digest"]["email_enabled"] == False
        
        # Toggle back on
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "digest_email_enabled": True
        })
        assert response.status_code == 200
        assert response.json()["engagement_loop"]["reminder"]["digest"]["email_enabled"] == True

    def test_toggle_both_digest_settings(self, basic_user_session):
        """PATCH supports toggling both digest settings at once"""
        response = basic_user_session.patch(f"{BASE_URL}/api/blog/v2/me/reminder-settings", json={
            "digest_in_app_enabled": True,
            "digest_email_enabled": True
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["ok"] == True
        digest = data["engagement_loop"]["reminder"]["digest"]
        assert digest["in_app_enabled"] == True
        assert digest["email_enabled"] == True


class TestReferralClaimEndpoint:
    """Tests for POST /api/blog/v2/me/referral-claim endpoint"""

    def test_referral_claim_rejects_empty_code(self, basic_user_session):
        """POST /api/blog/v2/me/referral-claim rejects empty invite_code"""
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/referral-claim", json={
            "invite_code": ""
        })
        # Should return 400 or 422 for validation error
        assert response.status_code in [400, 422]

    def test_referral_claim_rejects_invalid_code(self, basic_user_session):
        """POST /api/blog/v2/me/referral-claim rejects invalid invite_code"""
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/referral-claim", json={
            "invite_code": "INVALID-CODE-12345"
        })
        assert response.status_code == 400
        
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "invite_code_not_found"

    def test_referral_claim_rejects_self_claim(self, basic_user_session):
        """POST /api/blog/v2/me/referral-claim rejects claiming own code"""
        # First get user's own invite code
        rewards_response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert rewards_response.status_code == 200
        
        own_code = rewards_response.json()["referral"]["invite_code"]
        
        # Try to claim own code
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/referral-claim", json={
            "invite_code": own_code
        })
        assert response.status_code == 400
        
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "cannot_claim_own_code"

    def test_referral_claim_requires_auth(self):
        """POST /api/blog/v2/me/referral-claim requires authentication"""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = fresh_session.post(f"{BASE_URL}/api/blog/v2/me/referral-claim", json={
            "invite_code": "BLOG-12345678"
        })
        assert response.status_code in [401, 403]

    def test_referral_claim_valid_code_from_another_user(self, basic_user_session, premium_user_session):
        """POST /api/blog/v2/me/referral-claim accepts valid code from another user"""
        # Get premium user's invite code
        rewards_response = premium_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert rewards_response.status_code == 200
        
        premium_code = rewards_response.json()["referral"]["invite_code"]
        
        # Try to claim premium user's code with basic user
        # Note: This may fail with "already_claimed" if previously claimed
        response = basic_user_session.post(f"{BASE_URL}/api/blog/v2/me/referral-claim", json={
            "invite_code": premium_code
        })
        
        # Either success (200) or already_claimed (400)
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            data = response.json()
            assert data["ok"] == True
            assert data["boost_days"] == 2
            assert "rewards" in data
        else:
            data = response.json()
            assert data["detail"] == "already_claimed"


class TestEngagementLoopDigestFields:
    """Tests for digest fields in engagement_loop response"""

    def test_engagement_loop_contains_digest_settings(self, basic_user_session):
        """Engagement loop contains digest settings in reminder"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/engagement-loop")
        assert response.status_code == 200
        
        data = response.json()
        reminder = data["engagement_loop"]["reminder"]
        
        assert "digest" in reminder
        assert "in_app_enabled" in reminder["digest"]
        assert "email_enabled" in reminder["digest"]
        assert "last_digest_at" in reminder["digest"]
        assert "last_email_digest_at" in reminder["digest"]

    def test_engagement_loop_contains_rewards(self, basic_user_session):
        """Engagement loop contains rewards data"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/engagement-loop")
        assert response.status_code == 200
        
        data = response.json()
        loop = data["engagement_loop"]
        
        assert "rewards" in loop
        assert "unlock_tokens" in loop["rewards"]
        assert "invite_code" in loop["rewards"]
        assert "invite_link" in loop["rewards"]
        assert "referrals_count" in loop["rewards"]


class TestMilestonesBadges:
    """Tests for milestone badges in streak data"""

    def test_streak_contains_badges_array(self, basic_user_session):
        """Streak data contains badges array"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        assert "badges" in data["streak"]
        assert isinstance(data["streak"]["badges"], list)

    def test_streak_contains_next_milestone(self, basic_user_session):
        """Streak data contains next_milestone info"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        assert "next_milestone" in data["streak"]
        
        milestone = data["streak"]["next_milestone"]
        if milestone is not None:
            assert "threshold" in milestone
            assert "remaining" in milestone


class TestExistingBlogRoutesRegression:
    """Regression tests for existing Blog routes after growth features"""

    def test_blog_home_still_works(self, api_client):
        """GET /api/blog/v2/home still returns expected structure"""
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
        assert "engagement_loop" in data

    def test_blog_posts_still_works(self, api_client):
        """GET /api/blog/v2/posts still returns paginated list"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/posts")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "has_next" in data

    def test_blog_post_detail_still_works(self, api_client):
        """GET /api/blog/v2/posts/{slug} still returns post detail"""
        list_response = api_client.get(f"{BASE_URL}/api/blog/v2/posts")
        if list_response.json()["items"]:
            slug = list_response.json()["items"][0]["slug"]
            
            response = api_client.get(f"{BASE_URL}/api/blog/v2/posts/{slug}")
            assert response.status_code == 200
            
            data = response.json()
            assert "title" in data
            assert "content_blocks" in data

    def test_blog_bookmarks_still_works(self, basic_user_session):
        """GET /api/blog/v2/me/bookmarks still works for authenticated user"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/bookmarks")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data

    def test_blog_history_still_works(self, basic_user_session):
        """GET /api/blog/v2/me/history still works for authenticated user"""
        response = basic_user_session.get(f"{BASE_URL}/api/blog/v2/me/history")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data

    def test_blog_recommendations_still_works(self, api_client):
        """GET /api/blog/v2/recommendations still works"""
        response = api_client.get(f"{BASE_URL}/api/blog/v2/recommendations")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
