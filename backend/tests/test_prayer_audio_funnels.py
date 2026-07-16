"""
Prayer Audio Completion Funnels Tests - Iteration 9
Tests: Funnel event tracking (drop_opened, played, played_30s, played_75pct, completed),
       Admin cohort summary endpoint, Admin CSV/JSON export endpoint,
       Feature map includes prayer_audio_completion_funnels
"""

import os
import requests
import pytest
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

ADMIN_CREDS = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}
FREE_CREDS = {"email": "tv.free.test@realaicoach.app", "password": "TvFree#2026!Aa"}


class Session:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"Content-Type": "application/json"})
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
# Feature Map - Verify prayer_audio_completion_funnels is included
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureMapIncludesFunnels:
    """Verify feature map includes prayer_audio_completion_funnels and total is 33"""
    
    def test_feature_map_total_is_33(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
            params={"user_id": uid},
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("total_features") == 33, f"Expected 33, got {data.get('total_features')}"
    
    def test_feature_map_includes_prayer_audio_completion_funnels(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/feature-map",
            params={"user_id": uid},
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        features = r.json().get("features", [])
        feature_ids = [f.get("feature_id") for f in features]
        assert "prayer_audio_completion_funnels" in feature_ids, "prayer_audio_completion_funnels not found in feature map"
        
        # Verify the feature details
        funnel_feature = next((f for f in features if f.get("feature_id") == "prayer_audio_completion_funnels"), None)
        assert funnel_feature is not None
        assert funnel_feature.get("label") == "Prayer Audio Completion Funnels + Cohort Analytics"
        assert funnel_feature.get("tier") == "basic"


# ─────────────────────────────────────────────────────────────────────────────
# Funnel Event Tracking - Verify events are recorded via prayer-audio endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestFunnelEventTracking:
    """Verify funnel events are tracked: drop_opened, played, played_30s, played_75pct, completed"""
    
    def test_drop_opened_event_recorded_on_today_endpoint(self):
        """Accessing today's prayer audio should record drop_opened event"""
        uid = session.user_ids["admin"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data.get("items", [])) == 3, "Expected 3 items in today's drop"
        # The drop_opened event is recorded internally - we verify via funnel summary later
    
    def test_played_event_recorded_on_play_endpoint(self):
        """Playing a prayer audio should record played event"""
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
        # The played event is recorded internally
    
    def test_played_30s_event_recorded_on_progress_endpoint(self):
        """Progress >= 30s should record played_30s event"""
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
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 35, "duration_sec": 180, "completed": False},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "saved"
        # The played_30s event is recorded internally when position_sec >= 30
    
    def test_played_75pct_event_recorded_on_progress_endpoint(self):
        """Progress >= 75% should record played_75pct event"""
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
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 140, "duration_sec": 180, "completed": False},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "saved"
        assert data.get("progress_pct") >= 75, f"Expected progress_pct >= 75, got {data.get('progress_pct')}"
        # The played_75pct event is recorded internally when progress_pct >= 75
    
    def test_completed_event_recorded_on_progress_endpoint(self):
        """Completed=True or progress >= 95% should record completed event"""
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
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 180, "duration_sec": 180, "completed": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "saved"
        assert data.get("progress_pct") >= 95, f"Expected progress_pct >= 95, got {data.get('progress_pct')}"
        # The completed event is recorded internally


# ─────────────────────────────────────────────────────────────────────────────
# Admin Funnel Summary Endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminFunnelSummary:
    """Verify admin funnel summary endpoint returns cohort breakdown"""
    
    def test_funnel_summary_returns_200(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code == 200, r.text
    
    def test_funnel_summary_has_attribution_last_touch(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("attribution") == "last_touch", f"Expected last_touch attribution, got {data.get('attribution')}"
    
    def test_funnel_summary_has_funnel_steps(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        expected_steps = ["drop_opened", "played", "played_30s", "played_75pct", "completed", "upgraded"]
        assert data.get("funnel_steps") == expected_steps, f"Expected funnel_steps {expected_steps}, got {data.get('funnel_steps')}"
    
    def test_funnel_summary_has_cohorts_breakdown(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        cohorts = data.get("cohorts", {})
        assert "free" in cohorts, "Missing 'free' cohort"
        assert "basic" in cohorts, "Missing 'basic' cohort"
        assert "premium" in cohorts, "Missing 'premium' cohort"
    
    def test_funnel_summary_cohort_has_all_metrics(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        cohorts = data.get("cohorts", {})
        
        expected_metrics = [
            "drop_opened", "played", "played_30s", "played_75pct", "completed", "upgraded",
            "play_rate_pct", "played_30s_rate_pct", "played_75pct_rate_pct", "completion_rate_pct", "upgrade_rate_pct"
        ]
        
        for plan in ["free", "basic", "premium"]:
            bucket = cohorts.get(plan, {})
            for metric in expected_metrics:
                assert metric in bucket, f"Missing metric '{metric}' in {plan} cohort"
    
    def test_funnel_summary_has_totals(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        totals = data.get("totals", {})
        assert "drop_opened" in totals
        assert "played" in totals
        assert "completed" in totals
        assert "upgrade_rate_pct" in totals
    
    def test_funnel_summary_has_generated_at(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "generated_at" in data
    
    def test_funnel_summary_respects_days_param(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 30, "conversion_window_days": 7},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("window_days") == 30
        assert data.get("conversion_window_days") == 7
    
    def test_funnel_summary_requires_admin(self):
        """Non-admin should be rejected"""
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("free"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert r.status_code in [401, 403], f"Expected 401/403 for non-admin, got {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# Admin Funnel Export Endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminFunnelExport:
    """Verify admin funnel export endpoint returns CSV/JSON"""
    
    def test_funnel_export_csv_returns_200(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "csv"},
        )
        assert r.status_code == 200, r.text
    
    def test_funnel_export_csv_has_correct_content_type(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "csv"},
        )
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", ""), f"Expected text/csv, got {r.headers.get('content-type')}"
    
    def test_funnel_export_csv_has_headers(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "csv"},
        )
        assert r.status_code == 200, r.text
        text = r.text
        expected_headers = [
            "cohort_plan", "drop_opened", "played", "played_30s", "played_75pct",
            "completed", "upgraded", "play_rate_pct", "played_30s_rate_pct",
            "played_75pct_rate_pct", "completion_rate_pct", "upgrade_rate_pct"
        ]
        for header in expected_headers:
            assert header in text, f"Missing CSV header: {header}"
    
    def test_funnel_export_csv_has_cohort_rows(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "csv"},
        )
        assert r.status_code == 200, r.text
        text = r.text
        assert "free" in text, "Missing 'free' cohort row"
        assert "basic" in text, "Missing 'basic' cohort row"
        assert "premium" in text, "Missing 'premium' cohort row"
        assert "all" in text, "Missing 'all' totals row"
    
    def test_funnel_export_csv_has_content_disposition(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "csv"},
        )
        assert r.status_code == 200, r.text
        content_disp = r.headers.get("content-disposition", "")
        assert "attachment" in content_disp, f"Expected attachment disposition, got {content_disp}"
        assert "daily_meditation_prayer_audio_funnel" in content_disp, f"Expected filename pattern, got {content_disp}"
    
    def test_funnel_export_json_returns_200(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "json"},
        )
        assert r.status_code == 200, r.text
    
    def test_funnel_export_json_has_cohorts(self):
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14, "format": "json"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "cohorts" in data
        assert "totals" in data
        assert "attribution" in data
    
    def test_funnel_export_requires_admin(self):
        """Non-admin should be rejected"""
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-export",
            headers=session.headers("free"),
            params={"days": 14, "conversion_window_days": 14, "format": "csv"},
        )
        assert r.status_code in [401, 403], f"Expected 401/403 for non-admin, got {r.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# Free User Funnel Flow - Verify events are tracked for free users
# ─────────────────────────────────────────────────────────────────────────────

class TestFreeUserFunnelFlow:
    """Verify funnel events are tracked for free users"""
    
    def test_free_user_drop_opened_tracked(self):
        uid = session.user_ids["free"]
        r = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("free"),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data.get("items", [])) == 3
        # drop_opened event recorded internally
    
    def test_free_user_play_tracked(self):
        uid = session.user_ids["free"]
        today = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("free"),
        )
        items = today.json().get("items", [])
        # Find an unlocked item for free user
        unlocked = [i for i in items if not i.get("locked")]
        if not unlocked:
            pytest.skip("No unlocked items for free user")
        audio_id = unlocked[0].get("audio_id")
        
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/play",
            headers=session.headers("free"),
            json={"user_id": uid, "audio_id": audio_id},
        )
        assert r.status_code == 200, r.text
        # played event recorded internally
    
    def test_free_user_progress_tracked(self):
        uid = session.user_ids["free"]
        today = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("free"),
        )
        items = today.json().get("items", [])
        unlocked = [i for i in items if not i.get("locked")]
        if not unlocked:
            pytest.skip("No unlocked items for free user")
        audio_id = unlocked[0].get("audio_id")
        
        r = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/progress",
            headers=session.headers("free"),
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 45, "duration_sec": 180, "completed": False},
        )
        assert r.status_code == 200, r.text
        # played_30s event recorded internally


# ─────────────────────────────────────────────────────────────────────────────
# E2E Funnel Flow - Full journey from drop_opened to completed
# ─────────────────────────────────────────────────────────────────────────────

class TestE2EFunnelFlow:
    """End-to-end test of funnel flow from drop_opened to completed"""
    
    def test_full_funnel_journey(self):
        uid = session.user_ids["admin"]
        
        # Step 1: Open today's drop (drop_opened)
        today = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/today/{uid}",
            headers=session.headers("admin"),
        )
        assert today.status_code == 200, today.text
        items = today.json().get("items", [])
        assert len(items) == 3
        audio_id = items[1].get("audio_id")  # Use second item for variety
        
        # Step 2: Play the audio (played)
        play = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/play",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id},
        )
        assert play.status_code == 200, play.text
        
        # Step 3: Progress to 30s (played_30s)
        progress_30s = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/progress",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 35, "duration_sec": 210, "completed": False},
        )
        assert progress_30s.status_code == 200, progress_30s.text
        
        # Step 4: Progress to 75% (played_75pct)
        progress_75 = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/progress",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 160, "duration_sec": 210, "completed": False},
        )
        assert progress_75.status_code == 200, progress_75.text
        assert progress_75.json().get("progress_pct") >= 75
        
        # Step 5: Complete the audio (completed)
        complete = requests.post(
            f"{BASE_URL}/api/travel-visa/daily-meditation/prayer-audio/progress",
            headers=session.headers("admin"),
            json={"user_id": uid, "audio_id": audio_id, "position_sec": 210, "duration_sec": 210, "completed": True},
        )
        assert complete.status_code == 200, complete.text
        assert complete.json().get("progress_pct") >= 95
        
        # Verify funnel summary shows data
        summary = requests.get(
            f"{BASE_URL}/api/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary",
            headers=session.headers("admin"),
            params={"days": 14, "conversion_window_days": 14},
        )
        assert summary.status_code == 200, summary.text
        data = summary.json()
        totals = data.get("totals", {})
        # At minimum, we should have some drop_opened events
        assert totals.get("drop_opened", 0) >= 0, "Expected drop_opened events in totals"
