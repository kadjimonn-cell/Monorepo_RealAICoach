"""
Feature 28-36 Contract Hardening API Tests
==========================================
Tests API contracts for Features 28-36 across free/basic/premium tiers.
- Feature 28: Audio Studio (all tiers 200)
- Feature 29: My Podcasts (all tiers 200)
- Feature 30: Sports (all tiers 200, admin endpoint)
- Feature 31: AI Problem Solver (all tiers 200)
- Feature 32: AI Briefing (free=403 gated, basic/premium=200)
- Feature 33: Library (free=403 gated, basic/premium=200)
- Feature 34: Book Meeting (free=403 gated, basic/premium=200)
- Feature 35: Integrations (free=403 gated, basic/premium=200)
- Feature 36: Referrals (all tiers 200, admin endpoint)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL environment variable is required for test_feature28_36_contracts.py")
BASE_URL = BASE_URL.rstrip('/')

# Test credentials from test_credentials.md
CREDENTIALS = {
    "free": {
        "email": "p1.free.1779113329@example.com",
        "password": "P1Free#2026!Aa"
    },
    "basic": {
        "email": "f22.basic.20260613@example.com",
        "password": "F22Basic#2026Aa"
    },
    "premium": {
        "email": "f22.premium.20260613@example.com",
        "password": "F22Premium#2026Aa"
    },
    "admin": {
        "email": "admin@realaicoach.app",
        "password": "NewAdminPass2026!"
    }
}


class AuthSession:
    """Helper class to manage authenticated sessions"""
    
    def __init__(self):
        self.sessions = {}
        self.user_ids = {}
    
    def get_session(self, tier: str) -> requests.Session:
        """Get or create authenticated session for tier"""
        if tier not in self.sessions:
            session = requests.Session()
            session.headers.update({
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            })
            
            creds = CREDENTIALS.get(tier)
            if not creds:
                raise ValueError(f"Unknown tier: {tier}")
            
            # Login
            resp = session.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": creds["email"], "password": creds["password"]}
            )
            
            if resp.status_code != 200:
                pytest.skip(f"Login failed for {tier}: {resp.status_code} - {resp.text[:200]}")
            
            data = resp.json()
            # user_id can be at root level or nested under 'user'
            self.user_ids[tier] = data.get("user_id", "") or data.get("user", {}).get("user_id", "")
            
            # Store token if present (for admin)
            if "token" in data:
                session.headers["Authorization"] = f"Bearer {data['token']}"
            
            self.sessions[tier] = session
        
        return self.sessions[tier]
    
    def get_user_id(self, tier: str) -> str:
        """Get user_id for tier (must call get_session first)"""
        if tier not in self.user_ids:
            self.get_session(tier)
        return self.user_ids.get(tier, "")


# Global auth session manager
auth = AuthSession()


# ============================================================================
# Feature 28: Audio Studio Tests
# ============================================================================
class TestFeature28AudioStudio:
    """Feature 28 - Audio Studio v2: All tiers should get 200"""
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_audio_studio_bootstrap(self, tier):
        """GET /api/audio-studio/v2/bootstrap returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/audio-studio/v2/bootstrap")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        # Validate contract keys
        expected_keys = ["feature_id", "quota", "categories", "catalog", "surface"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_audio_studio_daily_drop_inbox(self, tier):
        """GET /api/audio-studio/v2/daily-drop-inbox returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/audio-studio/v2/daily-drop-inbox")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["surface", "total", "items"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"


# ============================================================================
# Feature 29: My Podcasts Tests
# ============================================================================
class TestFeature29MyPodcasts:
    """Feature 29 - My Podcasts v2: All tiers should get 200"""
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_podcasts_bootstrap(self, tier):
        """GET /api/podcasts/v2/bootstrap returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/podcasts/v2/bootstrap")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["feature_id", "label", "quota", "categories", "catalog"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_podcasts_daily_drop_inbox(self, tier):
        """GET /api/podcasts/v2/daily-drop-inbox returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/podcasts/v2/daily-drop-inbox")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["surface", "total", "items"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"


# ============================================================================
# Feature 30: Sports Tests
# ============================================================================
class TestFeature30Sports:
    """Feature 30 - Sports v2: All tiers should get 200, plus admin endpoint"""
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_sports_bootstrap(self, tier):
        """GET /api/sports/v2/bootstrap returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/sports/v2/bootstrap")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["feature_id", "label", "quota", "categories", "catalog"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_sports_daily_drop_inbox(self, tier):
        """GET /api/sports/v2/daily-drop-inbox returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/sports/v2/daily-drop-inbox")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["surface", "total", "items"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"
    
    def test_sports_admin_health(self):
        """GET /api/sports/v2/admin/source-health returns 200 for admin"""
        session = auth.get_session("admin")
        resp = session.get(f"{BASE_URL}/api/sports/v2/admin/source-health")
        
        assert resp.status_code == 200, f"Admin: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["generated_at", "summary", "sources"]
        for key in expected_keys:
            assert key in data, f"Admin: Missing key '{key}' in response"


# ============================================================================
# Feature 31: AI Coaching Team Tests (replaced legacy AI Problem Solver)
# ============================================================================
class TestFeature31AICoachingTeam:
    """Feature 31 - AI Coaching Team: All tiers should get 200"""
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_coaching_team_coaches(self, tier):
        """GET /api/ai-coaching-team/coaches returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/ai-coaching-team/coaches")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "coaches" in data, f"{tier}: Missing key 'coaches' in response"
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_coaching_team_sessions(self, tier):
        """GET /api/ai-coaching-team/sessions returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/ai-coaching-team/sessions")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"


# ============================================================================
# Feature 32: AI Briefing Tests (Free = limited access, POLICY 2026-06.v3)
# ============================================================================
class TestFeature32AIBriefing:
    """Feature 32 - AI Briefing: Free=limited (POLICY 2026-06.v3), Basic/Premium=200"""
    
    def test_ai_briefing_preferences_free_limited_allowed(self):
        """POLICY 2026-06.v3: GET /api/ai-briefing/preferences is free-accessible (limited access)"""
        session = auth.get_session("free")
        resp = session.get(f"{BASE_URL}/api/ai-briefing/preferences")
        assert resp.status_code == 200, f"Free: expected limited access 200, got {resp.status_code}"
    
    def test_ai_briefing_today_free_limited_allowed(self):
        """POLICY 2026-06.v3: GET /api/ai-briefing/today is free-accessible (limited access)"""
        session = auth.get_session("free")
        resp = session.get(f"{BASE_URL}/api/ai-briefing/today")
        assert resp.status_code == 200, f"Free: expected limited access 200, got {resp.status_code}"
    
    @pytest.mark.parametrize("tier", ["basic", "premium"])
    def test_ai_briefing_preferences_allowed(self, tier):
        """GET /api/ai-briefing/preferences returns 200 for basic/premium"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/ai-briefing/preferences")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["interests", "industry", "briefing_time"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"
    
    @pytest.mark.parametrize("tier", ["basic", "premium"])
    def test_ai_briefing_today_allowed(self, tier):
        """GET /api/ai-briefing/today returns 200 for basic/premium"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/ai-briefing/today")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["briefing_id", "user_id", "date", "greeting"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"


# ============================================================================
# Feature 33: Library Tests (Free = limited access, POLICY 2026-06.v3)
# ============================================================================
class TestFeature33Library:
    """Feature 33 - Library: Free=limited (POLICY 2026-06.v3), Basic/Premium=200"""
    
    def test_library_free_limited_allowed(self):
        """POLICY 2026-06.v3: GET /api/content/library is free-accessible (limited access)"""
        session = auth.get_session("free")
        resp = session.get(f"{BASE_URL}/api/content/library")
        assert resp.status_code == 200, f"Free: expected limited access 200, got {resp.status_code}"
    
    @pytest.mark.parametrize("tier", ["basic", "premium"])
    def test_library_allowed(self, tier):
        """GET /api/content/library returns 200 for basic/premium"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/content/library")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["items", "total", "page", "per_page"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"


# ============================================================================
# Feature 34: Book Meeting Tests (Free = limited access, POLICY 2026-06.v3)
# ============================================================================
class TestFeature34BookMeeting:
    """Feature 34 - Book Meeting: Free=limited (POLICY 2026-06.v3), Basic/Premium=200"""
    
    def test_calendar_status_free_limited_allowed(self):
        """POLICY 2026-06.v3: GET /api/calendar/status is free-accessible (limited access)"""
        session = auth.get_session("free")
        resp = session.get(f"{BASE_URL}/api/calendar/status")
        assert resp.status_code == 200, f"Free: expected limited access 200, got {resp.status_code}"
    
    def test_calendar_events_free_limited_allowed(self):
        """POLICY 2026-06.v3: GET /api/calendar/events/{user_id} is free-accessible (limited access)"""
        session = auth.get_session("free")
        user_id = auth.get_user_id("free")
        resp = session.get(f"{BASE_URL}/api/calendar/events/{user_id}")
        assert resp.status_code == 200, f"Free: expected limited access 200, got {resp.status_code}"
    
    @pytest.mark.parametrize("tier", ["basic", "premium"])
    def test_calendar_status_allowed(self, tier):
        """GET /api/calendar/status returns 200 for basic/premium"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/calendar/status")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["google_available", "google_connected", "provider"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"
    
    @pytest.mark.parametrize("tier", ["basic", "premium"])
    def test_calendar_events_allowed(self, tier):
        """GET /api/calendar/events/{user_id} returns 200 for basic/premium"""
        session = auth.get_session(tier)
        user_id = auth.get_user_id(tier)
        resp = session.get(f"{BASE_URL}/api/calendar/events/{user_id}")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["events", "source"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"


# ============================================================================
# Feature 35: Integrations Tests (Free = limited access, POLICY 2026-06.v3)
# ============================================================================
class TestFeature35Integrations:
    """Feature 35 - Integrations: Free=limited (POLICY 2026-06.v3), Basic/Premium=200"""
    
    def test_integrations_available_free_limited_allowed(self):
        """POLICY 2026-06.v3: GET /api/integrations/available is free-accessible (limited access)"""
        session = auth.get_session("free")
        resp = session.get(f"{BASE_URL}/api/integrations/available")
        assert resp.status_code == 200, f"Free: expected limited access 200, got {resp.status_code}"
    
    def test_integrations_dashboard_stats_free_limited_allowed(self):
        """POLICY 2026-06.v3: GET /api/integrations/dashboard/stats is free-accessible (limited access)"""
        session = auth.get_session("free")
        resp = session.get(f"{BASE_URL}/api/integrations/dashboard/stats")
        assert resp.status_code == 200, f"Free: expected limited access 200, got {resp.status_code}"
    
    @pytest.mark.parametrize("tier", ["basic", "premium"])
    def test_integrations_available_allowed(self, tier):
        """GET /api/integrations/available returns 200 for basic/premium"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/integrations/available")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        assert "integrations" in data, f"{tier}: Missing 'integrations' key in response"
    
    @pytest.mark.parametrize("tier", ["basic", "premium"])
    def test_integrations_dashboard_stats_allowed(self, tier):
        """GET /api/integrations/dashboard/stats returns 200 for basic/premium"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/integrations/dashboard/stats")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["total_candidates", "total_jobs", "integrations"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"


# ============================================================================
# Feature 36: Referrals Tests
# ============================================================================
class TestFeature36Referrals:
    """Feature 36 - Referrals: All tiers should get 200, plus admin endpoint"""
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_referrals_my_stats(self, tier):
        """GET /api/referrals/my-stats returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/referrals/my-stats")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["referral_code", "referral_link", "total_clicks", "total_signups"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"
    
    @pytest.mark.parametrize("tier", ["free", "basic", "premium"])
    def test_referrals_my_referrals(self, tier):
        """GET /api/referrals/my-referrals returns 200 for all tiers"""
        session = auth.get_session(tier)
        resp = session.get(f"{BASE_URL}/api/referrals/my-referrals")
        
        assert resp.status_code == 200, f"{tier}: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["referrals", "total"]
        for key in expected_keys:
            assert key in data, f"{tier}: Missing key '{key}' in response"
    
    def test_referrals_admin_analytics(self):
        """GET /api/referrals/admin/analytics returns 200 for admin"""
        session = auth.get_session("admin")
        resp = session.get(f"{BASE_URL}/api/referrals/admin/analytics")
        
        assert resp.status_code == 200, f"Admin: Expected 200, got {resp.status_code}"
        data = resp.json()
        
        expected_keys = ["total_referrers", "total_clicks", "total_signups", "conversion_rate"]
        for key in expected_keys:
            assert key in data, f"Admin: Missing key '{key}' in response"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
