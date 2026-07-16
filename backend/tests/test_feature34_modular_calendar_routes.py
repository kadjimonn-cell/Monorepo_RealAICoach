"""
Feature 34 Modular Calendar Routes Tests (iteration 435)
--------------------------------------------------------
Tests for architecture split regression, legacy compatibility routes,
sync telemetry, reliability/observability endpoints, release-gate profiles,
and admin controls after modular router split.

Modules tested:
- calendar_core.py
- calendar_sync.py
- calendar_ai.py
- calendar_booking.py
- calendar_sharing.py
- calendar_reliability.py
"""

import os
import pytest
import requests
from datetime import datetime, timedelta, timezone


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL environment variable is required")
BASE_URL = BASE_URL.rstrip("/")


CREDENTIALS = {
    "free": {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"},
    "basic": {"email": "f22.basic.20260613@example.com", "password": "F22Basic#2026Aa"},
    "premium": {"email": "f22.premium.20260613@example.com", "password": "F22Premium#2026Aa"},
    "admin": {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
}


class AuthSession:
    def __init__(self):
        self.sessions = {}
        self.user_ids = {}

    def get_session(self, tier: str) -> requests.Session:
        if tier in self.sessions:
            return self.sessions[tier]

        session = requests.Session()
        session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        creds = CREDENTIALS[tier]
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": creds["email"], "password": creds["password"]},
            timeout=20,
        )
        assert resp.status_code == 200, f"login failed for {tier}: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        self.user_ids[tier] = data.get("user_id", "") or data.get("user", {}).get("user_id", "")
        self.sessions[tier] = session
        return session

    def get_user_id(self, tier: str) -> str:
        if tier not in self.user_ids:
            self.get_session(tier)
        return self.user_ids.get(tier, "")


auth = AuthSession()


# ============================================================================
# SECTION 1: Architecture Split Regression - Core Calendar APIs
# ============================================================================

class TestCalendarCoreModuleRegression:
    """Verify calendar_core.py routes still work after modular split."""

    def test_calendar_status_route_works(self):
        """GET /api/calendar/status - basic user allowed"""
        session = auth.get_session("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/status", timeout=20)
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
        data = resp.json()
        assert "google_available" in data
        assert "sync_mode" in data

    def test_calendar_events_route_works(self):
        """GET /api/calendar/events/{user_id} - basic user can read own events"""
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/events/{user_id}", timeout=20)
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
        data = resp.json()
        assert "events" in data
        assert "source" in data

    def test_calendar_upcoming_route_works(self):
        """GET /api/calendar/upcoming/{user_id} - basic user can read upcoming"""
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/upcoming/{user_id}?limit=5", timeout=20)
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
        data = resp.json()
        assert "events" in data

    def test_calendar_reminders_route_works(self):
        """GET /api/calendar/reminders/{user_id} - basic user can read reminders"""
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/reminders/{user_id}", timeout=20)
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}"


# ============================================================================
# SECTION 2: Legacy Compatibility Routes
# ============================================================================

class TestLegacyCompatibilityRoutes:
    """Verify legacy routes still work: /api/integrations/calendar/auth, /api/calendar/connect"""

    def test_legacy_integrations_calendar_auth_route(self):
        """GET /api/integrations/calendar/auth - legacy route returns auth URL"""
        session = auth.get_session("basic")
        resp = session.get(f"{BASE_URL}/api/integrations/calendar/auth", timeout=20)
        # Should return 200 with authorization_url or 500 if Google not configured
        assert resp.status_code in [200, 500], f"unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert "authorization_url" in data

    def test_legacy_calendar_connect_route(self):
        """GET /api/calendar/connect - legacy route returns auth URL"""
        session = auth.get_session("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/connect", timeout=20)
        assert resp.status_code in [200, 500], f"unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert "authorization_url" in data


# ============================================================================
# SECTION 3: Sync Telemetry Path
# ============================================================================

class TestSyncTelemetryPath:
    """Verify POST /api/calendar/sync records telemetry and reliability endpoint consumes it."""

    def test_calendar_sync_endpoint_works(self):
        """POST /api/calendar/sync - basic user can trigger sync"""
        session = auth.get_session("basic")
        resp = session.post(f"{BASE_URL}/api/calendar/sync", timeout=30)
        # May return 200 (success) or 400 (not connected) depending on Google state
        assert resp.status_code in [200, 400], f"unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("success") is True
            assert "sync_mode" in data

    def test_reliability_endpoint_has_sync_metrics(self):
        """GET /api/calendar/reliability/{user_id} - returns sync_error_rate_7d and sync_latency_p95_ms"""
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/reliability/{user_id}", timeout=20)
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
        data = resp.json()
        metrics = data.get("metrics", {})
        assert "sync_error_rate_7d" in metrics, "missing sync_error_rate_7d"
        assert "sync_latency_p95_ms" in metrics, "missing sync_latency_p95_ms"


# ============================================================================
# SECTION 4: Reliability Endpoint Contract
# ============================================================================

class TestReliabilityEndpointContract:
    """GET /api/calendar/reliability/{user_id} returns metrics including conversion/reminder/conflict/sync."""

    def test_reliability_full_contract(self):
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/reliability/{user_id}", timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        
        # Top-level fields
        assert data.get("user_id") == user_id
        assert "plan_scope" in data
        assert "sync_mode" in data
        assert "window" in data
        
        # Metrics block
        metrics = data.get("metrics", {})
        required_keys = [
            "conflict_events_30d",
            "conflicts_current_7d",
            "conflicts_previous_7d",
            "bookings_7d",
            "booking_pages_active",
            "booking_views_7d",
            "bookings_confirmed_7d",
            "reminder_success_rate_7d",
            "error_rate_7d",
            "booking_conversion_7d",
            "sync_total_7d",
            "sync_error_rate_7d",
            "sync_latency_p95_ms",
        ]
        for key in required_keys:
            assert key in metrics, f"missing reliability metric: {key}"


# ============================================================================
# SECTION 5: Observability Compatibility
# ============================================================================

class TestObservabilityCompatibility:
    """GET /api/calendar/observability/{user_id} returns baseline summary + reliability block."""

    def test_observability_returns_summary_and_reliability(self):
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/observability/{user_id}", timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        
        # Baseline summary
        assert data.get("feature") == "book-meeting"
        assert "summary" in data
        summary = data["summary"]
        for key in ["total_events", "upcoming_events", "bookings_last_7d", "active_booking_pages"]:
            assert key in summary, f"missing summary key: {key}"
        
        # Reliability block
        assert "reliability" in data, "missing reliability block in observability"
        reliability = data["reliability"]
        assert "metrics" in reliability
        assert "sync_error_rate_7d" in reliability["metrics"]


# ============================================================================
# SECTION 6: Release-Gate User Endpoint
# ============================================================================

class TestReleaseGateUserEndpoint:
    """GET /api/calendar/release-gate/{user_id}?profile=strict|standard|lenient returns checks + decision."""

    def test_release_gate_strict_profile(self):
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/release-gate/{user_id}?profile=strict", timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("profile") == "strict"
        gate = data.get("gate", {})
        assert gate.get("decision") in ["go", "no-go"]
        assert "checks" in gate
        assert "thresholds" in gate

    def test_release_gate_standard_profile(self):
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/release-gate/{user_id}?profile=standard", timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("profile") == "standard"
        gate = data.get("gate", {})
        assert gate.get("decision") in ["go", "no-go"]

    def test_release_gate_lenient_profile(self):
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/release-gate/{user_id}?profile=lenient", timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("profile") == "lenient"
        gate = data.get("gate", {})
        assert gate.get("decision") in ["go", "no-go"]

    def test_release_gate_default_profile(self):
        """Without profile param, uses active profile from platform config."""
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = session.get(f"{BASE_URL}/api/calendar/release-gate/{user_id}", timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("profile") in ["strict", "standard", "lenient"]


# ============================================================================
# SECTION 7: Admin Profile Management
# ============================================================================

class TestAdminProfileManagement:
    """GET/PUT /api/admin/calendar/release-gate/profile works and profile persists."""

    def test_admin_get_release_gate_profile(self):
        session = auth.get_session("admin")
        resp = session.get(f"{BASE_URL}/api/admin/calendar/release-gate/profile", timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert data.get("active_profile") in ["strict", "standard", "lenient"]
        assert "profiles" in data

    def test_admin_put_release_gate_profile_strict(self):
        session = auth.get_session("admin")
        resp = session.put(
            f"{BASE_URL}/api/admin/calendar/release-gate/profile",
            json={"profile": "strict"},
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active_profile") == "strict"

    def test_admin_put_release_gate_profile_standard(self):
        session = auth.get_session("admin")
        resp = session.put(
            f"{BASE_URL}/api/admin/calendar/release-gate/profile",
            json={"profile": "standard"},
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active_profile") == "standard"

    def test_admin_put_release_gate_profile_lenient(self):
        session = auth.get_session("admin")
        resp = session.put(
            f"{BASE_URL}/api/admin/calendar/release-gate/profile",
            json={"profile": "lenient"},
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("active_profile") == "lenient"

    def test_admin_put_invalid_profile_rejected(self):
        session = auth.get_session("admin")
        resp = session.put(
            f"{BASE_URL}/api/admin/calendar/release-gate/profile",
            json={"profile": "invalid_profile"},
            timeout=20,
        )
        assert resp.status_code == 400


# ============================================================================
# SECTION 8: Admin Global Release-Gate Evaluation
# ============================================================================

class TestAdminGlobalReleaseGateEvaluation:
    """GET /api/admin/calendar/release-gate/evaluate returns decision/go_rate."""

    def test_admin_release_gate_evaluate(self):
        session = auth.get_session("admin")
        resp = session.get(f"{BASE_URL}/api/admin/calendar/release-gate/evaluate?sample_size=10", timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("feature") == "book-meeting"
        assert data.get("decision") in ["go", "no-go"]
        assert "go_rate" in data
        assert "summary" in data


# ============================================================================
# SECTION 9: Admin Reliability Dashboard
# ============================================================================

class TestAdminReliabilityDashboard:
    """GET /api/admin/calendar/reliability returns summary + rows."""

    def test_admin_reliability_dashboard(self):
        session = auth.get_session("admin")
        resp = session.get(f"{BASE_URL}/api/admin/calendar/reliability?sample_size=10", timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("feature") == "book-meeting"
        assert "profile" in data
        assert "summary" in data
        summary = data["summary"]
        assert "users_evaluated" in summary
        assert "go_count" in summary
        assert "no_go_count" in summary
        assert "go_rate" in summary
        assert "rows" in data
        assert isinstance(data["rows"], list)


# ============================================================================
# SECTION 10: Best-Slot/Commit/Telemetry Flows Still Intact
# ============================================================================

class TestBestSlotFlowsIntact:
    """Verify best-slot, commit, telemetry flows still work after split."""

    def test_best_slot_recommender_works(self):
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        payload = {
            "user_id": user_id,
            "title": "Test Session",
            "category": "meeting",
            "duration_minutes": 60,
        }
        resp = session.post(f"{BASE_URL}/api/calendar/recommend-best-slot", json=payload, timeout=20)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert "recommendation" in data
        assert "alternatives" in data
        assert "meta" in data

    def test_best_slot_telemetry_works(self):
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        rec = {
            "title": "Test Session",
            "start": "2030-01-15T10:00:00+00:00",
            "end": "2030-01-15T11:00:00+00:00",
            "category": "meeting",
            "confidence": 85,
        }
        resp = session.post(
            f"{BASE_URL}/api/calendar/recommend-best-slot/telemetry",
            json={"user_id": user_id, "action": "accepted", "recommendation": rec},
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert data.get("telemetry_id")

    def test_best_slot_commit_works(self):
        session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        start_dt = datetime.now(timezone.utc) + timedelta(days=5, hours=3)
        end_dt = start_dt + timedelta(minutes=60)
        recommendation = {
            "title": "Commit Test Session",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "reason": "pytest commit test",
            "category": "meeting",
            "confidence": 90,
        }
        resp = session.post(
            f"{BASE_URL}/api/calendar/recommend-best-slot/commit",
            json={"user_id": user_id, "recommendation": recommendation},
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        event = data.get("event", {})
        assert event.get("id")
        
        # Cleanup
        event_id = event.get("id")
        if event_id:
            session.delete(f"{BASE_URL}/api/calendar/events/{event_id}", timeout=20)


# ============================================================================
# SECTION 11: Free User Tier Gating
# ============================================================================

class TestFreeUserTierGating:
    """Verify free users are gated from calendar features."""

    def test_free_user_calendar_status_gated(self):
        session = auth.get_session("free")
        resp = session.get(f"{BASE_URL}/api/calendar/status", timeout=20)
        assert resp.status_code == 403
        data = resp.json()
        assert data.get("required_plan") == "basic"

    def test_free_user_best_slot_gated(self):
        session = auth.get_session("free")
        user_id = auth.get_user_id("free")
        payload = {
            "user_id": user_id,
            "title": "Test",
            "category": "meeting",
            "duration_minutes": 60,
        }
        resp = session.post(f"{BASE_URL}/api/calendar/recommend-best-slot", json=payload, timeout=20)
        assert resp.status_code == 403

    def test_free_user_reliability_gated(self):
        session = auth.get_session("free")
        user_id = auth.get_user_id("free")
        resp = session.get(f"{BASE_URL}/api/calendar/reliability/{user_id}", timeout=20)
        assert resp.status_code == 403


# ============================================================================
# SECTION 12: Cross-User Protection
# ============================================================================

class TestCrossUserProtection:
    """Verify cross-user access is forbidden."""

    def test_cross_user_events_forbidden(self):
        basic_session = auth.get_session("basic")
        premium_user_id = auth.get_user_id("premium")
        resp = basic_session.get(f"{BASE_URL}/api/calendar/events/{premium_user_id}", timeout=20)
        assert resp.status_code == 403

    def test_cross_user_reliability_forbidden(self):
        basic_session = auth.get_session("basic")
        premium_user_id = auth.get_user_id("premium")
        resp = basic_session.get(f"{BASE_URL}/api/calendar/reliability/{premium_user_id}", timeout=20)
        assert resp.status_code == 403

    def test_cross_user_release_gate_forbidden(self):
        basic_session = auth.get_session("basic")
        premium_user_id = auth.get_user_id("premium")
        resp = basic_session.get(f"{BASE_URL}/api/calendar/release-gate/{premium_user_id}", timeout=20)
        assert resp.status_code == 403


# ============================================================================
# SECTION 13: Preview E2E False-Positive Historical Backfill (P2)
# ============================================================================

class TestPreviewE2EHistoricalBackfill:
    """Verify admin preview/apply endpoints for historical weak-signal false-positive backfill."""

    def test_backfill_preview_requires_admin(self):
        basic_session = auth.get_session("basic")
        resp = basic_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=50&window_days=180",
            timeout=20,
        )
        assert resp.status_code == 403

    def test_backfill_preview_admin_works(self):
        admin_session = auth.get_session("admin")
        resp = admin_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=50&window_days=180",
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert "candidate_count" in data
        assert "scanned_count" in data
        assert "backfill_version" in data
        assert isinstance(data.get("candidates", []), list)

    def test_backfill_apply_admin_dry_run(self):
        admin_session = auth.get_session("admin")
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=50&window_days=180&dry_run=true",
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert data.get("dry_run") is True
        assert "updated_count" in data
        assert "updates" in data
        assert isinstance(data.get("updates", []), list)


# ============================================================================
# SECTION 14: Best-Slot Weekly Reward Badge (P2)
# ============================================================================

class TestBestSlotWeeklyRewardBadge:
    """Verify weekly best-slot reward badge endpoint contract and tier protection."""

    def test_best_slot_weekly_reward_badge_contract(self):
        basic_session = auth.get_session("basic")
        user_id = auth.get_user_id("basic")
        resp = basic_session.get(
            f"{BASE_URL}/api/calendar/recommend-best-slot/reward-badge/{user_id}",
            timeout=20,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert data.get("feature") == "book-meeting"
        assert data.get("protocol") == "platform_locked"
        assert data.get("user_id") == user_id

        badge = data.get("badge", {})
        required_keys = [
            "key",
            "title",
            "subtitle",
            "status_label",
            "target_accepts_per_week",
            "accepted_this_week",
            "remaining_to_unlock",
            "progress_ratio",
            "earned",
            "plan_scope",
            "premium_conversion_nudge",
            "support_copy",
            "telemetry_breakdown",
            "cta",
        ]
        for key in required_keys:
            assert key in badge, f"missing badge key: {key}"

        assert badge.get("target_accepts_per_week") == 3
        assert isinstance(badge.get("earned"), bool)
        assert isinstance(badge.get("progress_ratio"), (int, float))
        assert 0 <= float(badge.get("progress_ratio", 0)) <= 1

        cta = badge.get("cta", {})
        assert "label" in cta
        assert "intent" in cta
        assert "url" in cta

    def test_best_slot_weekly_reward_badge_free_user_gated(self):
        free_session = auth.get_session("free")
        free_user_id = auth.get_user_id("free")
        resp = free_session.get(
            f"{BASE_URL}/api/calendar/recommend-best-slot/reward-badge/{free_user_id}",
            timeout=20,
        )
        assert resp.status_code == 403

    def test_best_slot_weekly_reward_badge_cross_user_forbidden(self):
        basic_session = auth.get_session("basic")
        premium_user_id = auth.get_user_id("premium")
        resp = basic_session.get(
            f"{BASE_URL}/api/calendar/recommend-best-slot/reward-badge/{premium_user_id}",
            timeout=20,
        )
        assert resp.status_code == 403
