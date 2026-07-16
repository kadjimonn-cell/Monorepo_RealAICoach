"""
Feature 25 Daily Meditation Email V7 Compliance Tests
Tests:
- Static source verification: email template mapping, catalog template usage, template registration
- Runtime verification: digest preview returns v7 wrapped HTML, endpoints functional
- Canonical feature registry: feature_number=25
"""

import os
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin user and return session with cookies"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")
    
    data = resp.json()
    user_id = data.get("user_id") or data.get("user", {}).get("user_id") or data.get("id")
    
    return {
        "session": session,
        "user_id": user_id,
        "email": ADMIN_EMAIL,
        "is_admin": data.get("is_admin", True)
    }


class TestFeature25EmailV7StaticCompliance:
    """Static source verification for v7 email template compliance"""
    
    def test_daily_meditation_email_template_mapping(self):
        """Verify DM_EMAIL_TEMPLATE_MAP contains all required template keys"""
        source = Path("/app/backend/routes/travel_visa_daily_meditation.py").read_text(encoding="utf-8")
        assert 'DM_EMAIL_TEMPLATE_MAP = {' in source, "DM_EMAIL_TEMPLATE_MAP should be defined"
        assert '"daily_meditation_reminder": "daily_meditation_reminder"' in source
        assert '"daily_meditation_prayer_audio_drop": "daily_meditation_prayer_audio_drop"' in source
        assert '"daily_meditation_weekly_digest": "daily_meditation_weekly_digest"' in source
    
    def test_send_dm_email_uses_catalog_template(self):
        """Verify _send_dm_email uses send_catalog_template (not legacy helper)"""
        source = Path("/app/backend/routes/travel_visa_daily_meditation.py").read_text(encoding="utf-8")
        assert "from utils.email_service import send_catalog_template" in source, \
            "_send_dm_email should import send_catalog_template"
        assert "send_catalog_template(" in source, \
            "_send_dm_email should call send_catalog_template"
        # Verify no legacy direct raw helper path
        assert "from routes.travel_visa_ext import _send_email" not in source, \
            "Should not use legacy _send_email from travel_visa_ext"
    
    def test_feature25_templates_registered_in_catalog(self):
        """Verify all Feature 25 templates are registered in email_templates.py"""
        source = Path("/app/backend/utils/email_templates.py").read_text(encoding="utf-8")
        
        # Check template keys are registered
        assert '"daily_meditation_reminder"' in source, "daily_meditation_reminder should be registered"
        assert '"daily_meditation_prayer_audio_drop"' in source, "daily_meditation_prayer_audio_drop should be registered"
        assert '"daily_meditation_weekly_digest"' in source, "daily_meditation_weekly_digest should be registered"
        
        # Check builder functions exist
        assert "def build_daily_meditation_reminder_email(" in source, \
            "build_daily_meditation_reminder_email function should exist"
        assert "def build_daily_meditation_prayer_audio_drop_email(" in source, \
            "build_daily_meditation_prayer_audio_drop_email function should exist"
        assert "def build_daily_meditation_weekly_digest_email(" in source, \
            "build_daily_meditation_weekly_digest_email function should exist"
    
    def test_weekly_digest_uses_v7_template_builder(self):
        """Verify _build_weekly_digest_payload uses v7 template builder"""
        source = Path("/app/backend/routes/travel_visa_daily_meditation.py").read_text(encoding="utf-8")
        assert "from utils.email_templates import build_daily_meditation_weekly_digest_email" in source, \
            "_build_weekly_digest_payload should import v7 template builder"
        assert "build_daily_meditation_weekly_digest_email(" in source, \
            "_build_weekly_digest_payload should call v7 template builder"


class TestFeature25DigestPreviewV7Runtime:
    """Runtime verification: digest preview returns v7 wrapped HTML"""
    
    def test_digest_preview_returns_v7_html_fingerprints(self, admin_session):
        """Digest preview should return v7 template wrapped HTML with em-outer fingerprint"""
        session = admin_session["session"]
        user_id = admin_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/digest/preview",
            json={"user_id": user_id, "days": 7}
        )
        
        assert resp.status_code == 200, f"Digest preview failed: {resp.status_code} - {resp.text[:300]}"
        
        data = resp.json()
        assert "digest" in data, "Response should contain digest field"
        
        digest = data.get("digest", {})
        assert "html" in digest, "Digest should contain html field"
        
        html = digest.get("html", "")
        
        # V7 template fingerprints
        v7_fingerprints = ["em-outer", "em-card", "em-body", "email-outer", "email-card"]
        found_fingerprints = [fp for fp in v7_fingerprints if fp in html]
        
        assert len(found_fingerprints) >= 2, \
            f"Digest preview HTML should contain v7 fingerprints. Found: {found_fingerprints}"
        
        # Verify Daily Meditation specific content
        assert "Daily Meditation" in html, "HTML should contain Daily Meditation content"
        assert "features/daily-meditation" in html, "HTML should contain Daily Meditation CTA link"
    
    def test_digest_preview_returns_valid_subject(self, admin_session):
        """Digest preview should return valid subject line"""
        session = admin_session["session"]
        user_id = admin_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/digest/preview",
            json={"user_id": user_id, "days": 7}
        )
        
        assert resp.status_code == 200
        
        data = resp.json()
        digest = data.get("digest", {})
        subject = digest.get("subject", "")
        
        assert "Daily Meditation" in subject or "digest" in subject.lower(), \
            f"Subject should mention Daily Meditation or digest: {subject}"


class TestFeature25EndpointsFunctional:
    """Test Feature 25 endpoints remain functional after email-path migration"""
    
    def test_digest_preview_endpoint_functional(self, admin_session):
        """Test /digest/preview endpoint returns expected structure"""
        session = admin_session["session"]
        user_id = admin_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/digest/preview",
            json={"user_id": user_id, "days": 7}
        )
        
        assert resp.status_code == 200, f"Digest preview failed: {resp.status_code}"
        
        data = resp.json()
        assert data.get("status") == "ok", "Status should be ok"
        
        digest = data.get("digest", {})
        assert "html" in digest, "Should have html"
        assert "subject" in digest, "Should have subject"
        assert "stats" in digest or "headline" in digest, "Should have stats or headline"
    
    def test_digest_send_now_endpoint_functional(self, admin_session):
        """Test /digest/send-now endpoint is accessible to admin"""
        session = admin_session["session"]
        user_id = admin_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/digest/send-now",
            json={"user_id": user_id, "days": 7}
        )
        
        # Admin should not get 401/403
        assert resp.status_code not in [401, 403], \
            f"Admin should not get 401/403 for digest send-now, got {resp.status_code}"
        
        # Should get 200 (may skip email due to prefs)
        assert resp.status_code == 200, f"Digest send-now failed: {resp.status_code}"
    
    def test_reminders_notify_now_endpoint_functional(self, admin_session):
        """Test /reminders/notify-now endpoint is accessible to admin"""
        session = admin_session["session"]
        user_id = admin_session["user_id"]
        
        resp = session.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/reminders/notify-now",
            json={"user_id": user_id, "kind": "daily_gift"}
        )
        
        # Admin should not get 401/403
        assert resp.status_code not in [401, 403], \
            f"Admin should not get 401/403 for notify-now, got {resp.status_code}"


class TestFeature25CanonicalRegistry:
    """Test canonical feature registry for feature_number=25"""
    
    def test_health_endpoint_returns_feature_25_identity(self, admin_session):
        """Health endpoint should return correct feature identity"""
        session = admin_session["session"]
        
        resp = session.get(f"{BASE_URL}/api/travel-visa/daily-meditation/health")
        
        assert resp.status_code == 200, f"Health endpoint failed: {resp.status_code}"
        
        data = resp.json()
        assert data.get("feature_number") == 25, \
            f"Feature number should be 25, got {data.get('feature_number')}"
        assert data.get("feature_id") == "daily-meditation", \
            f"Feature ID should be daily-meditation, got {data.get('feature_id')}"
        assert data.get("feature_route") == "/features/daily-meditation", \
            f"Feature route should be /features/daily-meditation, got {data.get('feature_route')}"
        assert data.get("ok") is True, "Health check should return ok=True"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
