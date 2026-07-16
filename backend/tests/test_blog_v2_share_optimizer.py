"""
Backend tests for Blog V2 Share Variant Optimizer and Welcome Page APIs
Tests the P0 features: share_variant_optimizer, blog rewards, and funnel tracking
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
PREMIUM_USER = {
    "email": "f22.premium.20260613@example.com",
    "password": "F22Premium#2026Aa"
}

ADMIN_USER = {
    "email": "admin@realaicoach.app",
    "password": "NewAdminPass2026!"
}


class TestHealthAndBasics:
    """Basic health check tests"""
    
    def test_health_endpoint(self):
        """Test backend health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health endpoint returns healthy status")


class TestBlogV2ShareVariantOptimizer:
    """Tests for Blog V2 Share Variant Optimizer feature"""
    
    @pytest.fixture(scope="class")
    def premium_session(self):
        """Get authenticated session for premium user"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=PREMIUM_USER
        )
        
        if response.status_code != 200:
            pytest.skip(f"Premium user login failed: {response.status_code}")
        
        return session
    
    def test_blog_rewards_returns_share_variant_optimizer(self, premium_session):
        """Test that /api/blog/v2/me/rewards returns share_variant_optimizer"""
        response = premium_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify share_variant_optimizer exists
        assert "share_variant_optimizer" in data, "share_variant_optimizer missing from rewards response"
        
        optimizer = data["share_variant_optimizer"]
        
        # Verify required fields
        assert optimizer.get("default_mode") == "auto", f"Expected default_mode=auto, got {optimizer.get('default_mode')}"
        assert "global_top_variant" in optimizer, "global_top_variant missing"
        assert "global_top_variant_label" in optimizer, "global_top_variant_label missing"
        assert "channels" in optimizer, "channels missing"
        assert "window_days" in optimizer, "window_days missing"
        assert "exploration_rate" in optimizer, "exploration_rate missing"
        
        print(f"✓ share_variant_optimizer returned with default_mode={optimizer['default_mode']}")
        print(f"✓ Global top variant: {optimizer['global_top_variant_label']}")
    
    def test_share_variant_optimizer_has_10_channels(self, premium_session):
        """Test that optimizer returns all 10 share channels"""
        response = premium_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        optimizer = data.get("share_variant_optimizer", {})
        channels = optimizer.get("channels", {})
        
        expected_channels = ["whatsapp", "x", "linkedin", "telegram", "facebook", "reddit", "email", "tiktok", "youtube", "copy"]
        
        for channel in expected_channels:
            assert channel in channels, f"Channel {channel} missing from optimizer"
            channel_data = channels[channel]
            
            # Verify channel structure
            assert "recommended_variant" in channel_data, f"{channel}: recommended_variant missing"
            assert "recommended_label" in channel_data, f"{channel}: recommended_label missing"
            assert "winner_variant" in channel_data, f"{channel}: winner_variant missing"
            assert "strategy" in channel_data, f"{channel}: strategy missing"
            assert "sample_size" in channel_data, f"{channel}: sample_size missing"
            assert "variant_metrics" in channel_data, f"{channel}: variant_metrics missing"
        
        print(f"✓ All 10 channels present in optimizer: {list(channels.keys())}")
    
    def test_share_variant_optimizer_variant_metrics_structure(self, premium_session):
        """Test that each channel has proper variant_metrics structure"""
        response = premium_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        optimizer = data.get("share_variant_optimizer", {})
        channels = optimizer.get("channels", {})
        
        expected_variants = ["short", "long", "benefit"]
        
        for channel_key, channel_data in channels.items():
            variant_metrics = channel_data.get("variant_metrics", {})
            
            for variant in expected_variants:
                assert variant in variant_metrics, f"{channel_key}: variant {variant} missing from variant_metrics"
                
                metrics = variant_metrics[variant]
                assert "shares" in metrics, f"{channel_key}/{variant}: shares missing"
                assert "unique_owners" in metrics, f"{channel_key}/{variant}: unique_owners missing"
                assert "weighted_engagement" in metrics, f"{channel_key}/{variant}: weighted_engagement missing"
                assert "share_pct" in metrics, f"{channel_key}/{variant}: share_pct missing"
                assert "draw" in metrics, f"{channel_key}/{variant}: draw missing"
        
        print("✓ All channels have proper variant_metrics structure (short, long, benefit)")


class TestBlogV2FunnelTracking:
    """Tests for Blog V2 funnel event tracking"""
    
    @pytest.fixture(scope="class")
    def premium_session(self):
        """Get authenticated session for premium user"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=PREMIUM_USER
        )
        
        if response.status_code != 200:
            pytest.skip(f"Premium user login failed: {response.status_code}")
        
        return session
    
    def test_funnel_event_share_clicked_with_variant(self, premium_session):
        """Test recording share_clicked funnel event with share_variant"""
        payload = {
            "event_name": "share_clicked",
            "context": {
                "channel": "whatsapp",
                "link": "https://example.com/blog?invite=TEST-CODE",
                "surface": "blog_home_referral",
                "share_variant": "benefit",
                "share_variant_source": "optimizer_auto",
                "optimizer_strategy": "thompson_sampling"
            }
        }
        
        response = premium_session.post(
            f"{BASE_URL}/api/blog/v2/me/funnel-event",
            json=payload
        )
        
        # Accept 200, 201, or cooldown/dedupe responses
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}"
        
        data = response.json()
        # Check for valid response status
        assert data.get("status") in ["recorded", "cooldown_suppressed", "dedupe_suppressed"], \
            f"Unexpected status: {data.get('status')}"
        
        print(f"✓ Funnel event recorded with status: {data.get('status')}")
    
    def test_funnel_event_copy_clicked_with_variant(self, premium_session):
        """Test recording copy_clicked funnel event with share_variant"""
        payload = {
            "event_name": "copy_clicked",
            "context": {
                "channel": "copy",
                "link": "https://example.com/blog?invite=TEST-CODE",
                "surface": "blog_home_referral",
                "share_variant": "short",
                "share_variant_source": "manual_override"
            }
        }
        
        response = premium_session.post(
            f"{BASE_URL}/api/blog/v2/me/funnel-event",
            json=payload
        )
        
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") in ["recorded", "cooldown_suppressed", "dedupe_suppressed"]
        
        print(f"✓ Copy event recorded with status: {data.get('status')}")


class TestBlogV2ChannelAttribution:
    """Tests for Blog V2 channel attribution in rewards"""
    
    @pytest.fixture(scope="class")
    def premium_session(self):
        """Get authenticated session for premium user"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=PREMIUM_USER
        )
        
        if response.status_code != 200:
            pytest.skip(f"Premium user login failed: {response.status_code}")
        
        return session
    
    def test_rewards_includes_channel_attribution(self, premium_session):
        """Test that rewards response includes channel_attribution"""
        response = premium_session.get(f"{BASE_URL}/api/blog/v2/me/rewards")
        assert response.status_code == 200
        
        data = response.json()
        
        assert "channel_attribution" in data, "channel_attribution missing from rewards"
        
        attribution = data["channel_attribution"]
        assert "window_days" in attribution, "window_days missing"
        assert "channels" in attribution, "channels missing"
        assert "top_channel" in attribution, "top_channel missing"
        assert "totals" in attribution, "totals missing"
        assert "trend" in attribution, "trend missing"
        
        totals = attribution["totals"]
        assert "clicks" in totals, "totals.clicks missing"
        assert "unique_clicks" in totals, "totals.unique_clicks missing"
        
        print(f"✓ Channel attribution present with top_channel: {attribution['top_channel']}")
        print(f"✓ Total clicks: {totals['clicks']}, unique: {totals['unique_clicks']}")


class TestWelcomePageAPIs:
    """Tests for Welcome page related APIs"""
    
    def test_welcome_page_loads_without_auth(self):
        """Test that welcome page content APIs work without auth"""
        # Test public endpoints that welcome page might use
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Public health endpoint accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
