"""
Prayer Audio Feature Tests - Scaled Catalog
Tests: 150 categories, 500+ catalog audios, daily auto-publish with animation metadata,
today feed, play/progress/favorite/recommendations flows
"""

import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

ADMIN_CREDS = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}
FREE_CREDS = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}


class Session:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json", "X-Client-Platform": "native"})
        self.tokens = {}
        self.user_ids = {}

    def login(self, creds: dict, alias: str) -> str:
        r = self.s.post(f"{BASE_URL}/api/auth/login", json=creds)
        if r.status_code != 200:
            return ""
        data = r.json()
        token = data.get("session_token") or data.get("token")
        uid = data.get("user_id")
        self.tokens[alias] = token
        self.user_ids[alias] = uid
        return token or ""

    def headers(self, alias: str):
        return {"Authorization": f"Bearer {self.tokens.get(alias, '')}", "Content-Type": "application/json"}


session = Session()


@pytest.fixture(scope="module", autouse=True)
def bootstrap_auth():
    assert session.login(ADMIN_CREDS, "admin"), "Admin login failed"
    assert session.login(FREE_CREDS, "free"), "Free login failed"


# ─────────────────────────────────────────────────────────────────────────────
# Prayer Audio Categories - Must return >= 150
# ─────────────────────────────────────────────────────────────────────────────

class TestPrayerAudioCategories:
    """Verify prayer audio categories endpoint returns >= 150 categories and 500+ audios"""
    
    def test_categories_returns_at_least_150(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/categories",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("total", 0) >= 150, f"Expected >= 150 categories, got {data.get('total')}"
        assert len(data.get("categories", [])) >= 150, "Expected >= 150 category items"
        assert data.get("total_audio_count", 0) >= 500, f"Expected >= 500 audios, got {data.get('total_audio_count')}"
        
    def test_categories_includes_expected_types(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/categories",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        categories = r.json().get("categories", [])
        expected = ["Morning Gratitude", "Evening Surrender", "Anxiety Relief", "Peace & Stillness", "Healing & Recovery"]
        for cat in expected:
            assert cat in categories, f"Expected category '{cat}' not found"

    def test_catalog_stats_returns_500_plus(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/catalog/stats",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("category_total", 0) >= 150
        assert data.get("audio_total", 0) >= 500


# ─────────────────────────────────────────────────────────────────────────────
# Daily Auto-Publish Run-Now - Creates 3 items with animation metadata
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyAutoPublish:
    """Verify daily auto-publish creates 3 items with animation metadata"""
    
    def test_run_now_creates_three_items(self):
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/publish/run-now",
            headers=session.headers("admin"),
            json={"force": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "ok"
        assert data.get("today_total") == 3, f"Expected 3 items, got {data.get('today_total')}"
        
    def test_run_now_returns_notification_stats(self):
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/publish/run-now",
            headers=session.headers("admin"),
            json={"force": False},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "notifications" in data
        notif = data.get("notifications", {})
        assert "users_scanned" in notif
        assert "in_app_sent" in notif

    def test_seed_run_now_keeps_catalog_above_500(self):
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/catalog/seed/run-now",
            headers=session.headers("admin"),
            json={"target_count": 600},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("catalog_total", 0) >= 500


# ─────────────────────────────────────────────────────────────────────────────
# Today Prayer Audio Feed - Returns items with image/audio/animation
# ─────────────────────────────────────────────────────────────────────────────

class TestTodayPrayerAudioFeed:
    """Verify today prayer audio feed returns items with image/audio/animation metadata"""
    
    def test_today_returns_three_items(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data.get("items", [])) == 3, f"Expected 3 items, got {len(data.get('items', []))}"
        
    def test_today_items_have_audio_url(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        for item in items:
            assert "audio_url" in item, f"Item missing audio_url: {item.get('audio_id')}"
            assert item.get("audio_url"), f"audio_url is empty for {item.get('audio_id')}"
            
    def test_today_items_have_image_url(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        for item in items:
            assert "image_url" in item, f"Item missing image_url: {item.get('audio_id')}"
            assert item.get("image_url"), f"image_url is empty for {item.get('audio_id')}"
            
    def test_today_items_have_animation_metadata(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        for item in items:
            assert "animation" in item, f"Item missing animation: {item.get('audio_id')}"
            anim = item.get("animation", {})
            assert "preset" in anim, f"Animation missing preset for {item.get('audio_id')}"
            assert "duration_ms" in anim, f"Animation missing duration_ms for {item.get('audio_id')}"
            assert "overlay" in anim, f"Animation missing overlay for {item.get('audio_id')}"
            assert "loop" in anim, f"Animation missing loop for {item.get('audio_id')}"


# ─────────────────────────────────────────────────────────────────────────────
# Prayer Audio Play + Progress + Favorite + Recommendations Flows
# ─────────────────────────────────────────────────────────────────────────────

class TestPrayerAudioPlayFlow:
    """Verify prayer audio play, progress, favorite, and recommendations flows"""
    
    def test_play_returns_audio_data(self):
        uid = session.user_ids["admin"]
        # Get today's items first
        today = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        items = today.json().get("items", [])
        assert items, "No prayer audio items found"
        audio_id = items[0].get("audio_id")
        
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/play",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "ok"
        assert "audio" in data
        assert "quota" in data
        
    def test_progress_saves_position(self):
        uid = session.user_ids["admin"]
        today = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        items = today.json().get("items", [])
        assert items, "No prayer audio items found"
        audio_id = items[0].get("audio_id")
        
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/progress",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 60, "duration_sec": 180, "completed": False},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "saved"
        assert "progress_pct" in data
        
    def test_progress_list_returns_items(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/progress/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        assert "total" in data
        
    def test_favorite_toggle_works(self):
        uid = session.user_ids["admin"]
        today = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        items = today.json().get("items", [])
        assert items, "No prayer audio items found"
        audio_id = items[0].get("audio_id")
        
        # Add favorite
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/favorite",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id, "favorite": True},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "ok"
        
        # Check favorites list
        fav_list = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/favorites/{uid}",
            headers=session.headers("admin"),
        )
        assert fav_list.status_code == 200, fav_list.text
        assert any(row.get("audio_id") == audio_id for row in fav_list.json().get("items", []))
        
        # Remove favorite
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/favorite",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id, "favorite": False},
        )
        assert r.status_code == 200, r.text
        
    def test_recommendations_returns_items(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/recommendations/{uid}",
            headers=session.headers("admin"),
            params={"limit": 6},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        assert "target_categories" in data

    def test_library_endpoint_returns_large_total(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/library/{uid}",
            headers=session.headers("admin"),
            params={"page": 1, "limit": 120},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("total", 0) >= 500, f"Expected library total >= 500, got {data.get('total')}"
        assert len(data.get("items", [])) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Feature Map - Total changed to 33
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureMapTotal:
    """Verify feature map total is 33"""
    
    def test_feature_map_returns_33_features(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
            params={"user_id": uid},
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("total_features") == 33, f"Expected 33, got {data.get('total_features')}"
        
    def test_feature_map_includes_prayer_audio_features(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
            params={"user_id": uid},
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        features = r.json().get("features", [])
        feature_ids = [f.get("feature_id") for f in features]
        expected_ids = [
            "prayer_audio_library_150_categories",
            "animated_prayer_visuals",
            "daily_three_audio_auto_drop",
            "audio_drop_notifications",
            "audio_player_personalization",
            "prayer_audio_completion_funnels",
            "prayer_audio_semantic_search",
            "prayer_audio_upgrade_attribution_by_category",
        ]
        for fid in expected_ids:
            assert fid in feature_ids, f"Expected feature '{fid}' not found in feature map"


class TestPrayerAudioP1SemanticSearchAndAttribution:
    """Verify semantic search and category attribution endpoints"""

    def test_semantic_search_returns_ranked_items(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/semantic-search/{uid}",
            headers=session.headers("admin"),
            params={"intent": "peace", "mood": "anxious", "scripture": "Psalm 46", "limit": 8},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data
        assert "total_matches" in data
        if data.get("items"):
            first = data["items"][0]
            assert "semantic_score" in first
            assert "match_reasons" in first

    def test_semantic_search_requires_at_least_one_signal(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/semantic-search/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 400, r.text

    def test_upgrade_attribution_by_category_returns_admin_payload(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/upgrade-attribution/categories",
            headers=session.headers("admin"),
            params={"days": 30, "conversion_window_days": 14, "top": 12},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("attribution") == "last_touch_category"
        assert "category_slices" in data
        assert "totals" in data

    def test_upgrade_attribution_by_category_requires_admin(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/upgrade-attribution/categories",
            headers=session.headers("free"),
            params={"days": 30, "conversion_window_days": 14, "top": 12},
        )
        assert r.status_code in [401, 403], f"Expected 401/403, got {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# Funnel Analytics + Cohorts
# ─────────────────────────────────────────────────────────────────────────────

class TestPrayerAudioFunnelAnalytics:
    """Verify prayer audio completion funnel summary and export endpoints"""

    def test_funnel_summary_returns_cohort_breakdown(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("attribution") == "last_touch"
        assert "cohorts" in data
        assert "totals" in data
        assert "free" in (data.get("cohorts") or {})

    def test_funnel_export_csv_works(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "csv"},
        )
        assert r.status_code == 200, r.text
        text = r.text
        assert "cohort_plan" in text
        assert "drop_opened" in text


# ─────────────────────────────────────────────────────────────────────────────
# Digest Endpoints Regression Check
# ─────────────────────────────────────────────────────────────────────────────

class TestDigestRegression:
    """Verify digest endpoints still function (regression check)"""
    
    def test_digest_preview_works(self):
        uid = session.user_ids["admin"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/digest/preview",
            headers=session.headers("admin"),
            json={"user_id": uid, "days": 7},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "ok"
        assert "digest" in data
        
    def test_digest_send_now_works(self):
        uid = session.user_ids["admin"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/digest/send-now",
            headers=session.headers("admin"),
            json={"user_id": uid, "days": 7},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "sent"
        assert "email_status" in data
