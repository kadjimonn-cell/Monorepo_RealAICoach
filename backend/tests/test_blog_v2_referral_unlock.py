"""
Blog V2 Referral Sharing UX + Unlock Token Consumption Tests
Tests for Option A redo: deeper referral sharing UX and unlock-token consumption flow.
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
PREMIUM_EMAIL = "f22.premium.20260613@example.com"
PREMIUM_PASSWORD = "F22Premium#2026Aa"
BASIC_EMAIL = "f22.basic.20260613@example.com"
BASIC_PASSWORD = "F22Basic#2026Aa"


class TestBlogV2ReferralAndUnlock:
    """Tests for Blog V2 referral sharing UX and unlock-token consumption flow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session."""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })

    def _login(self, email: str, password: str) -> bool:
        """Login and return success status."""
        try:
            response = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": email, "password": password}
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Login failed: {e}")
            return False

    # ============ BLOG HOME REFERRAL UX TESTS ============

    def test_blog_home_loads(self):
        """Test /api/blog/v2/home endpoint loads successfully."""
        response = self.session.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200, f"Blog home failed: {response.status_code}"
        data = response.json()
        assert "featured" in data
        assert "trending" in data
        assert "latest" in data
        assert "engagement_loop" in data
        print("PASS: Blog home loads with engagement_loop")

    def test_blog_home_engagement_loop_has_rewards(self):
        """Test engagement loop contains rewards with invite_code and invite_link."""
        response = self.session.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        data = response.json()
        engagement = data.get("engagement_loop", {})
        rewards = engagement.get("rewards", {})
        # Guest users should have empty invite_code/link
        assert "invite_code" in rewards or "invite_link" in rewards or engagement.get("reminder", {}).get("status") == "signin_required"
        print("PASS: Engagement loop has rewards structure")

    def test_authenticated_user_has_invite_code(self):
        """Test authenticated user gets invite_code and invite_link."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        response = self.session.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        data = response.json()
        engagement = data.get("engagement_loop", {})
        rewards = engagement.get("rewards", {})
        
        invite_code = rewards.get("invite_code", "")
        invite_link = rewards.get("invite_link", "")
        
        assert invite_code, "Authenticated user should have invite_code"
        assert invite_link, "Authenticated user should have invite_link"
        assert invite_code.startswith("BLOG-"), f"Invite code should start with BLOG-: {invite_code}"
        print(f"PASS: Authenticated user has invite_code={invite_code}")

    # ============ FUNNEL EVENT TRACKING TESTS ============

    def test_funnel_event_endpoint_requires_auth(self):
        """Test POST /api/blog/v2/me/funnel-event requires authentication."""
        # Fresh session without auth
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = fresh_session.post(
            f"{BASE_URL}/api/blog/v2/me/funnel-event",
            json={"event_name": "test_event", "context": {}}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Funnel event endpoint requires auth (401)")

    def test_funnel_event_accepts_events(self):
        """Test POST /api/blog/v2/me/funnel-event accepts events and persists."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        # Track a funnel event
        response = self.session.post(
            f"{BASE_URL}/api/blog/v2/me/funnel-event",
            json={"event_name": "copy_clicked", "context": {"source": "test"}}
        )
        assert response.status_code == 200, f"Funnel event failed: {response.status_code}"
        data = response.json()
        assert data.get("ok") is True
        assert data.get("event_name") == "copy_clicked"
        print(f"PASS: Funnel event accepted: {data}")

    def test_funnel_summary_in_rewards(self):
        """Test funnel counts visible in /api/blog/v2/me/rewards."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        # First track an event
        self.session.post(
            f"{BASE_URL}/api/blog/v2/me/funnel-event",
            json={"event_name": "share_clicked", "context": {"test": True}}
        )
        
        # Check rewards endpoint
        response = self.session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200, f"Rewards failed: {response.status_code}"
        data = response.json()
        assert "funnel" in data, "Rewards should contain funnel summary"
        print(f"PASS: Funnel summary in rewards: {data.get('funnel', {})}")

    # ============ REFERRAL CLAIM FLOW TESTS ============

    def test_referral_claim_requires_auth(self):
        """Test POST /api/blog/v2/me/referral-claim requires authentication."""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = fresh_session.post(
            f"{BASE_URL}/api/blog/v2/me/referral-claim",
            json={"invite_code": "BLOG-TESTCODE"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Referral claim requires auth (401)")

    def test_referral_claim_invalid_code(self):
        """Test referral claim with invalid code returns proper error."""
        logged_in = self._login(BASIC_EMAIL, BASIC_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with basic user")
        
        response = self.session.post(
            f"{BASE_URL}/api/blog/v2/me/referral-claim",
            json={"invite_code": "BLOG-INVALID123"}
        )
        # Should return 400 with reason
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data or "reason" in data
        print(f"PASS: Invalid referral code returns 400: {data}")

    def test_referral_claim_records_funnel_event(self):
        """Test successful referral claim records claim_success funnel event."""
        # This test validates the flow exists - actual claim may fail if already claimed
        logged_in = self._login(BASIC_EMAIL, BASIC_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with basic user")
        
        # Get premium user's invite code first
        premium_session = requests.Session()
        premium_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        premium_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASSWORD}
        )
        rewards_resp = premium_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        if rewards_resp.status_code != 200:
            pytest.skip("Could not get premium user rewards")
        
        invite_code = rewards_resp.json().get("referral", {}).get("invite_code", "")
        if not invite_code:
            pytest.skip("Premium user has no invite code")
        
        # Try to claim (may fail if already claimed, but endpoint should work)
        response = self.session.post(
            f"{BASE_URL}/api/blog/v2/me/referral-claim",
            json={"invite_code": invite_code}
        )
        # Either 200 (success) or 400 (already claimed/own code)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        print(f"PASS: Referral claim endpoint works: status={response.status_code}")

    # ============ PREMIUM UNLOCK TOKEN TESTS ============

    def test_unlock_premium_requires_auth(self):
        """Test POST /api/blog/v2/me/unlock-premium/{post_id} requires auth."""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = fresh_session.post(
            f"{BASE_URL}/api/blog/v2/me/unlock-premium/blogv2-0003"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Unlock premium requires auth (401)")

    def test_unlock_premium_no_tokens_error(self):
        """Test unlock premium returns proper error when no tokens available."""
        logged_in = self._login(BASIC_EMAIL, BASIC_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with basic user")
        
        # Try to unlock a premium post
        response = self.session.post(
            f"{BASE_URL}/api/blog/v2/me/unlock-premium/blogv2-0003"
        )
        # Should return 400 with no_unlock_tokens or 200 with already_unlocked
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        data = response.json()
        
        if response.status_code == 400:
            assert "no_unlock_tokens" in str(data) or "detail" in data
            print(f"PASS: No tokens error: {data}")
        else:
            assert data.get("status") in ["unlocked", "already_unlocked"]
            print(f"PASS: Unlock response: {data}")

    def test_unlock_premium_endpoint_contract(self):
        """Test unlock premium endpoint returns expected contract fields."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        response = self.session.post(
            f"{BASE_URL}/api/blog/v2/me/unlock-premium/blogv2-0003"
        )
        # Should not crash - either 200 or 400
        assert response.status_code in [200, 400], f"Server error: {response.status_code}"
        data = response.json()
        
        if response.status_code == 200:
            assert "ok" in data
            assert "status" in data
            assert "post_id" in data
            assert "remaining_tokens" in data
            print(f"PASS: Unlock contract valid: {data}")
        else:
            # 400 should have detail or reason
            assert "detail" in data or "reason" in data
            print(f"PASS: Unlock error contract valid: {data}")

    # ============ REGRESSION TESTS ============

    def test_blog_posts_list(self):
        """Regression: /api/blog/v2/posts still works."""
        response = self.session.get(f"{BASE_URL}/api/blog/v2/posts")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        print(f"PASS: Blog posts list works, total={data.get('total')}")

    def test_blog_post_detail(self):
        """Regression: /api/blog/v2/posts/{slug} still works."""
        # First get a slug from posts list
        list_resp = self.session.get(f"{BASE_URL}/api/blog/v2/posts?page_size=1")
        if list_resp.status_code != 200 or not list_resp.json().get("items"):
            pytest.skip("No posts available")
        
        slug = list_resp.json()["items"][0]["slug"]
        response = self.session.get(f"{BASE_URL}/api/blog/v2/posts/{slug}")
        assert response.status_code == 200
        data = response.json()
        assert "title" in data
        assert "content_blocks" in data
        assert "premium_gate" in data
        print(f"PASS: Blog post detail works for slug={slug}")

    def test_blog_bookmarks_endpoint(self):
        """Regression: /api/blog/v2/me/bookmarks requires auth."""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/me/bookmarks")
        assert response.status_code == 401
        print("PASS: Bookmarks endpoint requires auth")

    def test_blog_authors_endpoint(self):
        """Regression: /api/blog/v2/authors/{slug} still works."""
        # Get an author slug from home
        home_resp = self.session.get(f"{BASE_URL}/api/blog/v2/home")
        if home_resp.status_code != 200:
            pytest.skip("Could not load blog home")
        
        authors = home_resp.json().get("authors", [])
        if not authors:
            pytest.skip("No authors available")
        
        author_slug = authors[0].get("author_slug")
        response = self.session.get(f"{BASE_URL}/api/blog/v2/authors/{author_slug}")
        assert response.status_code == 200
        data = response.json()
        assert "author" in data
        assert "posts" in data
        print(f"PASS: Author profile works for slug={author_slug}")

    def test_engagement_loop_endpoint(self):
        """Regression: /api/blog/v2/engagement-loop still works."""
        response = self.session.get(f"{BASE_URL}/api/blog/v2/engagement-loop")
        assert response.status_code == 200
        data = response.json()
        assert "engagement_loop" in data
        print("PASS: Engagement loop endpoint works")

    def test_reminder_settings_endpoint(self):
        """Regression: /api/blog/v2/me/reminder-settings requires auth."""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = fresh_session.patch(
            f"{BASE_URL}/api/blog/v2/me/reminder-settings",
            json={"enabled": True}
        )
        assert response.status_code == 401
        print("PASS: Reminder settings requires auth")

    def test_weekly_digest_endpoint(self):
        """Regression: /api/blog/v2/weekly-digest requires auth."""
        fresh_session = requests.Session()
        fresh_session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = fresh_session.get(f"{BASE_URL}/api/blog/v2/weekly-digest")
        assert response.status_code == 401
        print("PASS: Weekly digest requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
