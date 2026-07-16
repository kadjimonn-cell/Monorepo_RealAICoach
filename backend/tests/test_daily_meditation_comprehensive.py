"""
Daily Meditation Comprehensive E2E Tests
Tests: feature map, check-in flow, companion chat, community share/pray, reminder trigger, compliance export, safety check
"""

import os
import requests
import pytest
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

ADMIN_CREDS = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}
FREE_CREDS = {"email": "tv.free.test@realaicoach.app", "password": "TvFree#2026!Aa"}
FREE_CREDS_FALLBACKS = [
    {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"},
    {"email": "sso.test.1779125847@example.com", "password": "SsoTest#2026Aa"},
    {"email": "apple.link.e2e.1779207440@example.com", "password": "AppleLinkE2E#2026Aa!"},
    {"email": "jobs.free.final.90705154@gmail.com", "password": "JobsFree#2026Aa!"},
]


class Session:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
        )
        self.tokens = {}
        self.user_ids = {}

    def login(self, creds: dict, alias: str) -> str:
        attempts = 0
        r = None
        while attempts < 3:
            attempts += 1
            r = self.s.post(
                f"{BASE_URL}/api/auth/login",
                json=creds,
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if r.status_code == 200:
                break
            if r.status_code == 429:
                retry_after = 1
                try:
                    payload = r.json()
                    retry_after = int(payload.get("retry_after") or payload.get("detail", {}).get("retry_after_seconds") or 1)
                except Exception:
                    retry_after = 1
                time.sleep(min(max(retry_after, 1), 3))
                continue
            return ""

        if not r or r.status_code != 200:
            return ""
        data = r.json()
        cookie_token = r.cookies.get("session_token") or self.s.cookies.get("session_token")
        token = cookie_token or data.get("session_token") or data.get("token")
        uid = data.get("user_id")
        self.tokens[alias] = token
        self.user_ids[alias] = uid
        return token or ""

    def headers(self, alias: str):
        return {"Authorization": f"Bearer {self.tokens.get(alias, '')}", "Content-Type": "application/json"}


session = Session()


@pytest.fixture(scope="module", autouse=True)
def bootstrap_auth():
    if not session.login(ADMIN_CREDS, "admin"):
        pytest.skip("Admin login failed in current environment")
    free_candidates = [FREE_CREDS, *FREE_CREDS_FALLBACKS]
    for creds in free_candidates:
        if session.login(creds, "free"):
            return
    pytest.skip("No valid free test credential available for daily meditation suite")


# ─────────────────────────────────────────────────────────────────────────────
# Feature Registry Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureRegistry:
    """Verify daily-meditation is in feature registry with 25 total features"""
    
    def test_feature_registry_returns_25_features(self):
        r = requests.get(f"{BASE_URL}/api/features/registry")
        assert r.status_code == 200, r.text
        data = r.json()
        assert (data.get("total") or 0) >= 25, f"Expected at least 25 features, got {data.get('total')}"
    
    def test_feature_registry_includes_daily_meditation(self):
        r = requests.get(f"{BASE_URL}/api/features/registry")
        assert r.status_code == 200, r.text
        data = r.json()
        features = data.get("features", [])
        dm_feature = next((f for f in features if f.get("feature_id") == "daily-meditation"), None)
        assert dm_feature is not None, "daily-meditation not found in feature registry"
        assert dm_feature.get("title") == "Daily Meditation"
        assert dm_feature.get("route") == "/features/daily-meditation"
        assert dm_feature.get("enabled") is True


# ─────────────────────────────────────────────────────────────────────────────
# Feature Map Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureMap:
    """Verify feature map returns 31 meditation functionalities"""
    
    def test_feature_map_returns_31_features(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
            params={"user_id": uid},
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert (data.get("total_features") or 0) >= 31, f"Expected at least 31, got {data.get('total_features')}"
        assert data.get("tab") == "Daily Meditation"
    
    def test_feature_map_shows_plan(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
            params={"user_id": uid},
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("plan") in ["free", "basic", "premium"]


# ─────────────────────────────────────────────────────────────────────────────
# Overview Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOverview:
    """Verify overview endpoint returns user data"""
    
    def test_overview_returns_user_data(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/overview/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("user_id") == uid
        assert "plan" in data
        assert "limits" in data
        assert "progress" in data


# ─────────────────────────────────────────────────────────────────────────────
# Health Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:
    """Verify lightweight health endpoint for Feature 25 governance checks"""

    def test_health_returns_feature_contract(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/health",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("feature_number") == 25
        assert data.get("feature_id") == "daily-meditation"
        assert data.get("feature_route") == "/features/daily-meditation"
        assert data.get("plan") in ["free", "basic", "premium"]
        assert isinstance(data.get("generated_at"), str)


# ─────────────────────────────────────────────────────────────────────────────
# Daily Gift Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyGift:
    """Verify daily gift endpoint returns gift data"""
    
    def test_daily_gift_returns_gift(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/daily-gift/{uid}",
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "gift" in data
        gift = data.get("gift")
        assert "title" in gift
        assert "scripture" in gift
        assert "reflection" in gift


# ─────────────────────────────────────────────────────────────────────────────
# Check-in Flow Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckinFlow:
    """Verify check-in creation and quota enforcement"""
    
    def test_admin_can_create_checkin(self):
        uid = session.user_ids["admin"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/checkin",
            headers=session.headers("admin"),
            json={
                "user_id": uid,
                "heart_text": "Testing check-in from admin user.",
                "mood": "peaceful",
                "energy": 4,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "saved"
        assert "checkin" in data
        assert data["checkin"].get("checkin_id") is not None
    
    def test_checkin_list_returns_entries(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/checkins/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "checkins" in data
        assert isinstance(data["checkins"], list)


# ─────────────────────────────────────────────────────────────────────────────
# Companion Chat Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCompanionChat:
    """Verify companion chat session flow"""
    
    def test_companion_chat_creates_session(self):
        uid = session.user_ids["admin"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/companion/chat",
            headers=session.headers("admin"),
            json={
                "user_id": uid,
                "message": "I need some peace today.",
                "language": "en",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "session_id" in data
        assert "response" in data
        assert len(data["response"]) > 0
    
    def test_companion_history_returns_messages(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/companion/history/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "messages" in data


# ─────────────────────────────────────────────────────────────────────────────
# Community Share/Pray Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCommunityFlow:
    """Verify community share and prayer support flow"""
    
    def test_admin_can_share_to_community(self):
        uid = session.user_ids["admin"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/community/share",
            headers=session.headers("admin"),
            json={
                "user_id": uid,
                "text": "Praying for wisdom and clarity today.",
                "anonymized": True,
                "tags": ["wisdom"],
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "shared"
        assert "post" in data
    
    def test_community_feed_returns_posts(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/community/feed/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "posts" in data
        assert isinstance(data["posts"], list)
    
    def test_prayer_support_works(self):
        uid = session.user_ids["admin"]
        # First get a post
        feed = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/community/feed/{uid}",
            headers=session.headers("admin"),
        )
        posts = feed.json().get("posts", [])
        if posts:
            post_id = posts[0].get("post_id")
            r = requests.post(
                f"{BASE_URL}/api/travel-visa/daily-meditation/community/pray",
                headers=session.headers("admin"),
                json={"user_id": uid, "post_id": post_id},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data.get("status") == "supported"


# ─────────────────────────────────────────────────────────────────────────────
# Reminder Trigger Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReminderFlow:
    """Verify reminder trigger flow without crash"""
    
    def test_reminder_prefs_get(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/reminders/prefs/{uid}",
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "preferences" in data
    
    def test_reminder_prefs_update(self):
        uid = session.user_ids["admin"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/reminders/prefs",
            headers=session.headers("admin"),
            json={
                "user_id": uid,
                "in_app_enabled": True,
                "email_enabled": False,
                "quiet_hours_start": 22,
                "quiet_hours_end": 6,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "updated"
    
    def test_notify_now_dispatches_without_crash(self):
        uid = session.user_ids["free"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/reminders/notify-now",
            headers=session.headers("free"),
            json={"user_id": uid, "kind": "daily_gift"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "queued_and_dispatched"
        assert "dispatch" in data


# ─────────────────────────────────────────────────────────────────────────────
# Compliance Export Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestComplianceExport:
    """Verify compliance export JSON/CSV behavior"""
    
    def test_export_json_returns_data(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/compliance/export/{uid}",
            headers=session.headers("admin"),
            params={"format": "json"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("user_id") == uid
        assert "counts" in data
        assert "data" in data
    
    def test_export_csv_returns_file(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/compliance/export/{uid}",
            headers=session.headers("admin"),
            params={"format": "csv"},
        )
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")


# ─────────────────────────────────────────────────────────────────────────────
# Safety Check Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSafetyCheck:
    """Verify safety check high-risk phrase classification"""
    
    def test_safety_check_low_risk(self):
        uid = session.user_ids["free"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/safety/check",
            headers=session.headers("free"),
            json={"user_id": uid, "text": "I feel peaceful and grateful today."},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("risk_level") == "low"
    
    def test_safety_check_medium_risk(self):
        uid = session.user_ids["free"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/safety/check",
            headers=session.headers("free"),
            json={"user_id": uid, "text": "I feel anxious and overwhelmed today."},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("risk_level") == "medium"
    
    def test_safety_check_high_risk_harm_myself(self):
        uid = session.user_ids["free"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/safety/check",
            headers=session.headers("free"),
            json={"user_id": uid, "text": "I want to harm myself."},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("risk_level") == "high", f"Expected high risk for 'harm myself', got {data.get('risk_level')}"
    
    def test_safety_check_high_risk_end_everything(self):
        uid = session.user_ids["free"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/safety/check",
            headers=session.headers("free"),
            json={"user_id": uid, "text": "I want to end everything."},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("risk_level") == "high", f"Expected high risk for 'end everything', got {data.get('risk_level')}"


# ─────────────────────────────────────────────────────────────────────────────
# Progress Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProgress:
    """Verify progress endpoint returns milestones"""
    
    def test_progress_returns_milestones(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/progress/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "progress" in data
        assert "milestones" in data
        assert "progress_score" in data
        assert "next_step" in data


# ─────────────────────────────────────────────────────────────────────────────
# Somatic Library Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSomaticLibrary:
    """Verify somatic library returns invitations"""
    
    def test_somatic_library_returns_invitations(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/somatic/library",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "invitations" in data
        assert len(data["invitations"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Lookback Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLookback:
    """Verify lookback endpoint returns summary"""
    
    def test_lookback_returns_summary(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/lookback/{uid}",
            headers=session.headers("admin"),
            params={"days": 7},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "summary" in data
        assert "counts" in data


# ─────────────────────────────────────────────────────────────────────────────
# Notifications Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNotifications:
    """Verify notifications endpoint returns data"""
    
    def test_notifications_returns_list(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/notifications/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "notifications" in data
        assert "unread_count" in data


# ─────────────────────────────────────────────────────────────────────────────
# Prayer Audio + Animation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPrayerAudio:
    """Verify prayer audio categories, daily auto-drop, playback, favorites, and notifications"""

    def test_prayer_audio_categories_returns_150_plus(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/categories",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("total", 0) >= 150
        assert len(data.get("categories", [])) >= 150
        assert data.get("total_audio_count", 0) >= 500

    def test_prayer_audio_publish_run_now_creates_three_daily(self):
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/publish/run-now",
            headers=session.headers("admin"),
            json={"force": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("today_total") == 3
        assert "notifications" in data

    def test_prayer_audio_today_returns_items(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data.get("items", [])) == 3

    def test_prayer_audio_library_total_500_plus(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/library/{uid}",
            headers=session.headers("admin"),
            params={"page": 1, "limit": 100},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("total", 0) >= 500

    def test_prayer_audio_play_progress_favorite_flow(self):
        uid = session.user_ids["admin"]
        today = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        items = today.json().get("items", [])
        assert items, "No prayer audio items found"
        audio_id = items[0].get("audio_id")

        play = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/play",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id},
        )
        assert play.status_code == 200, play.text

        progress = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/progress",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 45, "duration_sec": 180, "completed": False},
        )
        assert progress.status_code == 200, progress.text

        fav = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/favorite",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id, "favorite": True},
        )
        assert fav.status_code == 200, fav.text

        fav_list = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/favorites/{uid}",
            headers=session.headers("admin"),
        )
        assert fav_list.status_code == 200, fav_list.text
        assert any(row.get("audio_id") == audio_id for row in fav_list.json().get("items", []))

    def test_prayer_audio_recommendations_returns_items(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/recommendations/{uid}",
            headers=session.headers("admin"),
            params={"limit": 6},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data

    def test_prayer_audio_drop_notification_record_exists(self):
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/notifications/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        rows = r.json().get("notifications", [])
        assert any("prayer_audio_daily_drop" in str(n.get("type", "")) for n in rows), "Expected prayer audio drop notification"

    def test_prayer_audio_funnel_summary_available_for_admin(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        if r.status_code == 403:
            try:
                detail = r.json().get("detail", {})
            except Exception:
                detail = {}
            code = detail.get("code") if isinstance(detail, dict) else None
            if code == "risk_engine_admin_api_blocked":
                pytest.skip("Prayer audio funnel summary blocked by risk engine containment in this environment")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("attribution") == "last_touch"
        assert "cohorts" in data
        assert "totals" in data

    def test_prayer_audio_funnel_export_csv_available_for_admin(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "csv"},
        )
        if r.status_code == 403:
            try:
                detail = r.json().get("detail", {})
            except Exception:
                detail = {}
            code = detail.get("code") if isinstance(detail, dict) else None
            if code == "risk_engine_admin_api_blocked":
                pytest.skip("Prayer audio funnel export blocked by risk engine containment in this environment")
        assert r.status_code == 200, r.text
        assert "cohort_plan" in r.text


# ─────────────────────────────────────────────────────────────────────────────
# Weekly Digest Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWeeklyDigest:
    """Verify digest preview and send-now endpoints"""

    def test_digest_preview_returns_dynamic_snippets(self):
        uid = session.user_ids["admin"]
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/digest/preview",
            headers=session.headers("admin"),
            json={"user_id": uid, "days": 7},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        digest = data.get("digest") or {}
        assert digest.get("subject")
        assert isinstance(digest.get("snippets"), list)
        assert len(digest.get("snippets", [])) >= 3

    def test_digest_send_now_responds(self):
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
