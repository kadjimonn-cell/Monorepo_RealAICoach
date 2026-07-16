"""
Blog V2 Channel-Specific Deep Links Tests
Tests for channel set A (WhatsApp, X, LinkedIn, TikTok, YouTube, Telegram, Facebook, Reddit, Email, Copy)
and per-channel funnel tracking.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
PREMIUM_EMAIL = "f22.premium.20260613@example.com"
PREMIUM_PASSWORD = "F22Premium#2026Aa"

# Channel set A
SHARE_CHANNELS = ['whatsapp', 'x', 'linkedin', 'tiktok', 'youtube', 'telegram', 'facebook', 'reddit', 'email', 'copy']


class TestBlogV2ChannelShare:
    """Tests for Blog V2 channel-specific share deep links and funnel tracking."""

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

    # ============ FUNNEL EVENT CHANNEL TRACKING TESTS ============

    def test_funnel_event_copy_clicked_with_channel(self):
        """Test funnel event copy_clicked records channel in context."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        response = self.session.post(
            f"{BASE_URL}/api/blog/v2/me/funnel-event",
            json={
                "event_name": "copy_clicked",
                "context": {"channel": "copy", "link": "https://test.com/blog/test", "surface": "blog_home_referral"}
            }
        )
        assert response.status_code == 200, f"Funnel event failed: {response.status_code}"
        data = response.json()
        assert data.get("ok") is True
        assert data.get("event_name") == "copy_clicked"
        print("PASS: copy_clicked funnel event with channel recorded")

    def test_funnel_event_share_clicked_with_channel(self):
        """Test funnel event share_clicked records channel in context."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        for channel in ['whatsapp', 'x', 'linkedin', 'telegram']:
            response = self.session.post(
                f"{BASE_URL}/api/blog/v2/me/funnel-event",
                json={
                    "event_name": "share_clicked",
                    "context": {"channel": channel, "link": "https://test.com/blog/test", "surface": "blog_home_referral"}
                }
            )
            assert response.status_code == 200, f"Funnel event for {channel} failed: {response.status_code}"
            data = response.json()
            assert data.get("ok") is True
            print(f"PASS: share_clicked funnel event for channel={channel} recorded")

    def test_funnel_event_share_clicked_blog_detail_surface(self):
        """Test funnel event share_clicked from blog_detail surface."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        response = self.session.post(
            f"{BASE_URL}/api/blog/v2/me/funnel-event",
            json={
                "event_name": "share_clicked",
                "context": {
                    "channel": "facebook",
                    "link": "https://test.com/blog/test-article",
                    "post_id": "post_test123",
                    "slug": "test-article",
                    "surface": "blog_detail"
                }
            }
        )
        assert response.status_code == 200, f"Funnel event failed: {response.status_code}"
        data = response.json()
        assert data.get("ok") is True
        print("PASS: share_clicked from blog_detail surface recorded")

    def test_funnel_event_all_channels(self):
        """Test funnel events can be recorded for all channel set A channels."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        for channel in SHARE_CHANNELS:
            event_name = "copy_clicked" if channel == "copy" else "share_clicked"
            response = self.session.post(
                f"{BASE_URL}/api/blog/v2/me/funnel-event",
                json={
                    "event_name": event_name,
                    "context": {"channel": channel, "surface": "blog_home_referral"}
                }
            )
            assert response.status_code == 200, f"Funnel event for {channel} failed: {response.status_code}"
            print(f"PASS: {event_name} for channel={channel}")

    # ============ FUNNEL SUMMARY IN REWARDS TESTS ============

    def test_funnel_summary_visible_in_rewards(self):
        """Test funnel summary is visible in /api/blog/v2/me/rewards."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        # Track some events first
        self.session.post(
            f"{BASE_URL}/api/blog/v2/me/funnel-event",
            json={"event_name": "share_clicked", "context": {"channel": "whatsapp"}}
        )
        
        response = self.session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200, f"Rewards failed: {response.status_code}"
        data = response.json()
        
        # Verify funnel data is present
        assert "funnel" in data, "Rewards should contain funnel summary"
        funnel = data.get("funnel", {})
        print(f"PASS: Funnel summary in rewards: {funnel}")

    # ============ EXISTING REFERRAL CONTROLS TESTS ============

    def test_referral_invite_code_present(self):
        """Test authenticated user has invite_code in rewards."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        response = self.session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        data = response.json()
        
        referral = data.get("referral", {})
        assert referral.get("invite_code"), "Should have invite_code"
        assert referral.get("invite_link"), "Should have invite_link"
        print(f"PASS: Referral controls present: invite_code={referral.get('invite_code')}")

    def test_referral_claim_endpoint_works(self):
        """Test referral claim endpoint is functional."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        # Try to claim an invalid code - should return 400 with proper error
        response = self.session.post(
            f"{BASE_URL}/api/blog/v2/me/referral-claim",
            json={"invite_code": "BLOG-INVALID999"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Referral claim endpoint functional (returns 400 for invalid code)")

    # ============ BLOG HOME AND DETAIL ENDPOINTS ============

    def test_blog_home_loads_with_engagement_loop(self):
        """Test blog home loads with engagement_loop containing rewards."""
        response = self.session.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        data = response.json()
        
        assert "engagement_loop" in data
        engagement = data.get("engagement_loop", {})
        assert "streak" in engagement
        assert "reminder" in engagement
        print("PASS: Blog home loads with engagement_loop")

    def test_blog_post_detail_loads(self):
        """Test blog post detail endpoint loads."""
        # First get a post slug from home
        response = self.session.get(f"{BASE_URL}/api/blog/v2/home")
        assert response.status_code == 200
        data = response.json()
        
        latest = data.get("latest", [])
        if not latest:
            pytest.skip("No posts available")
        
        slug = latest[0].get("slug")
        detail_response = self.session.get(f"{BASE_URL}/api/blog/v2/posts/{slug}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        
        assert detail.get("title")
        assert detail.get("post_id")
        print(f"PASS: Blog post detail loads for slug={slug}")

    def test_blog_post_detail_premium_gate(self):
        """Test blog post detail has premium_gate structure."""
        # Get a premium post
        response = self.session.get(f"{BASE_URL}/api/blog/v2/posts")
        assert response.status_code == 200
        data = response.json()
        
        items = data.get("items", [])
        premium_post = next((p for p in items if p.get("premium_required")), None)
        
        if not premium_post:
            pytest.skip("No premium posts available")
        
        slug = premium_post.get("slug")
        detail_response = self.session.get(f"{BASE_URL}/api/blog/v2/posts/{slug}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        
        assert "premium_gate" in detail
        gate = detail.get("premium_gate", {})
        assert "required" in gate
        assert "unlocked" in gate
        print(f"PASS: Premium gate structure present for slug={slug}")

    # ============ REMINDER/DIGEST/REWARDS REGRESSION TESTS ============

    def test_reminder_settings_endpoint(self):
        """Test reminder settings endpoint works."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        response = self.session.patch(
            f"{BASE_URL}/api/blog/v2/me/reminder-settings",
            json={"mode": "adaptive"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert "engagement_loop" in data
        print("PASS: Reminder settings endpoint works")

    def test_weekly_digest_endpoint(self):
        """Test weekly digest endpoint works."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        response = self.session.get(f"{BASE_URL}/api/blog/v2/weekly-digest")
        assert response.status_code == 200
        data = response.json()
        assert "digest" in data
        print("PASS: Weekly digest endpoint works")

    def test_rewards_endpoint_structure(self):
        """Test rewards endpoint returns expected structure."""
        logged_in = self._login(PREMIUM_EMAIL, PREMIUM_PASSWORD)
        if not logged_in:
            pytest.skip("Could not login with premium user")
        
        response = self.session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected fields
        assert "streak" in data
        assert "rewards" in data
        assert "referral" in data
        assert "funnel" in data
        print("PASS: Rewards endpoint returns expected structure")
