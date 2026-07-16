"""
Feature 34 Enterprise Hardening Tests
------------------------------------
Validates strict ownership, auth behavior, and new observability endpoint.
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


def test_feature34_status_free_limited_allowed_contract():
    # POLICY 2026-06.v3: My Agenda is free-accessible with limited access.
    session = auth.get_session("free")
    resp = session.get(f"{BASE_URL}/api/calendar/status", timeout=20)
    assert resp.status_code == 200, f"expected limited access 200 for free, got {resp.status_code}"


def test_feature34_status_basic_allowed_contract():
    session = auth.get_session("basic")
    resp = session.get(f"{BASE_URL}/api/calendar/status", timeout=20)
    assert resp.status_code == 200, f"expected 200 for basic, got {resp.status_code}"
    data = resp.json()
    for key in ["google_available", "google_connected", "provider", "sync_mode", "timezone"]:
        assert key in data, f"missing key: {key}"


def test_feature34_cross_user_events_forbidden():
    basic_session = auth.get_session("basic")
    premium_user_id = auth.get_user_id("premium")
    assert premium_user_id, "premium user_id missing"

    resp = basic_session.get(f"{BASE_URL}/api/calendar/events/{premium_user_id}", timeout=20)
    assert resp.status_code == 403, f"expected 403 for cross-user read, got {resp.status_code}"


def test_feature34_invalid_window_rejected():
    session = auth.get_session("basic")
    user_id = auth.get_user_id("basic")
    payload = {
        "user_id": user_id,
        "title": "Invalid Window Test",
        "start": "2030-01-10T12:00:00+00:00",
        "end": "2030-01-10T11:00:00+00:00",
        "category": "meeting",
        "recurrence": "none",
    }
    resp = session.post(f"{BASE_URL}/api/calendar/events", json=payload, timeout=20)
    assert resp.status_code == 400, f"expected 400 for invalid window, got {resp.status_code}"
    assert "after start" in str(resp.text).lower() or "end time" in str(resp.text).lower()


def test_feature34_observability_contract():
    session = auth.get_session("basic")
    user_id = auth.get_user_id("basic")
    resp = session.get(f"{BASE_URL}/api/calendar/observability/{user_id}", timeout=20)
    assert resp.status_code == 200, f"expected 200 observability, got {resp.status_code}"
    data = resp.json()
    assert data.get("feature") == "book-meeting"
    assert "summary" in data and isinstance(data["summary"], dict)
    for key in [
        "total_events",
        "upcoming_events",
        "bookings_last_7d",
        "active_booking_pages",
        "conflict_events_last_30d",
        "scheduled_minutes_last_30d",
    ]:
        assert key in data["summary"], f"missing summary key {key}"


def test_feature34_best_slot_recommender_contract():
    session = auth.get_session("basic")
    user_id = auth.get_user_id("basic")
    payload = {
        "user_id": user_id,
        "title": "Priority Session",
        "category": "meeting",
        "duration_minutes": 60,
    }
    resp = session.post(f"{BASE_URL}/api/calendar/recommend-best-slot", json=payload, timeout=20)
    assert resp.status_code == 200, f"expected 200 best-slot, got {resp.status_code}"
    data = resp.json()
    assert data.get("success") is True
    recommendation = data.get("recommendation") or {}
    for key in ["start", "end", "reason", "confidence", "source"]:
        assert key in recommendation, f"missing recommendation key: {key}"
    meta = data.get("meta") or {}
    assert "plan_scope" in meta
    assert "acceptance_ratio_30d" in meta
    assert "behavior_counts_30d" in meta


def test_feature34_best_slot_cross_user_forbidden():
    basic_session = auth.get_session("basic")
    premium_user_id = auth.get_user_id("premium")
    payload = {
        "user_id": premium_user_id,
        "title": "Cross User Attack",
        "category": "meeting",
        "duration_minutes": 45,
    }
    resp = basic_session.post(f"{BASE_URL}/api/calendar/recommend-best-slot", json=payload, timeout=20)
    assert resp.status_code == 403, f"expected 403 cross-user best-slot, got {resp.status_code}"


def test_feature34_best_slot_telemetry_actions_contract():
    session = auth.get_session("basic")
    user_id = auth.get_user_id("basic")
    rec = {
        "title": "Priority Session",
        "start": "2030-01-10T10:00:00+00:00",
        "end": "2030-01-10T11:00:00+00:00",
        "category": "meeting",
        "confidence": 88,
    }

    for action in ["recomputed", "ignored", "accepted"]:
        resp = session.post(
            f"{BASE_URL}/api/calendar/recommend-best-slot/telemetry",
            json={"user_id": user_id, "action": action, "recommendation": rec, "metadata": {"source": "pytest"}},
            timeout=20,
        )
        assert resp.status_code == 200, f"telemetry {action} failed: {resp.status_code}"
        body = resp.json()
        assert body.get("success") is True
        assert body.get("action") == action
        assert body.get("telemetry_id")


def test_feature34_best_slot_commit_creates_event_and_returns_contract():
    session = auth.get_session("basic")
    user_id = auth.get_user_id("basic")

    start_dt = datetime.now(timezone.utc) + timedelta(days=4, hours=2)
    end_dt = start_dt + timedelta(minutes=60)
    recommendation = {
        "title": "Committed Priority Session",
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "reason": "pytest commit path",
        "category": "meeting",
        "confidence": 91,
        "source": "pytest",
    }
    resp = session.post(
        f"{BASE_URL}/api/calendar/recommend-best-slot/commit",
        json={"user_id": user_id, "recommendation": recommendation},
        timeout=20,
    )
    assert resp.status_code == 200, f"expected 200 commit, got {resp.status_code}: {resp.text[:240]}"
    data = resp.json()
    assert data.get("success") is True
    assert data.get("telemetry_id")
    event = data.get("event") or {}
    assert event.get("id")
    assert event.get("title") == "Committed Priority Session"
    assert event.get("user_id") == user_id

    # Cleanup committed test event
    event_id = event.get("id")
    if event_id:
        del_resp = session.delete(f"{BASE_URL}/api/calendar/events/{event_id}", timeout=20)
        assert del_resp.status_code in [200, 404], f"cleanup failed: {del_resp.status_code}"


def test_feature34_reliability_snapshot_contract():
    session = auth.get_session("basic")
    user_id = auth.get_user_id("basic")
    resp = session.get(f"{BASE_URL}/api/calendar/reliability/{user_id}", timeout=20)
    assert resp.status_code == 200, f"expected 200 reliability snapshot, got {resp.status_code}"
    data = resp.json()
    assert data.get("user_id") == user_id
    metrics = data.get("metrics") or {}
    for key in [
        "conflict_events_30d",
        "reminder_success_rate_7d",
        "error_rate_7d",
        "booking_conversion_7d",
        "sync_error_rate_7d",
        "sync_latency_p95_ms",
    ]:
        assert key in metrics, f"missing reliability metric key: {key}"


def test_feature34_release_gate_user_contract():
    session = auth.get_session("basic")
    user_id = auth.get_user_id("basic")
    resp = session.get(f"{BASE_URL}/api/calendar/release-gate/{user_id}?profile=standard", timeout=20)
    assert resp.status_code == 200, f"expected 200 release gate, got {resp.status_code}"
    data = resp.json()
    assert data.get("profile") == "standard"
    gate = data.get("gate") or {}
    assert gate.get("decision") in ["go", "no-go"]
    assert isinstance(gate.get("checks"), dict)


def test_feature34_release_gate_admin_profile_update_and_dashboard():
    session = auth.get_session("admin")
    get_resp = session.get(f"{BASE_URL}/api/admin/calendar/release-gate/profile", timeout=20)
    assert get_resp.status_code == 200, f"expected 200 profile read, got {get_resp.status_code}"

    put_resp = session.put(
        f"{BASE_URL}/api/admin/calendar/release-gate/profile",
        json={"profile": "strict"},
        timeout=20,
    )
    assert put_resp.status_code == 200, f"expected 200 profile update, got {put_resp.status_code}"
    body = put_resp.json()
    assert body.get("active_profile") == "strict"

    dash_resp = session.get(f"{BASE_URL}/api/admin/calendar/reliability?sample_size=10", timeout=20)
    assert dash_resp.status_code == 200, f"expected 200 reliability dashboard, got {dash_resp.status_code}"
    dash = dash_resp.json()
    assert "summary" in dash
    assert "rows" in dash


def test_feature34_release_gate_admin_evaluate_contract():
    session = auth.get_session("admin")
    resp = session.get(f"{BASE_URL}/api/admin/calendar/release-gate/evaluate?sample_size=8", timeout=20)
    assert resp.status_code == 200, f"expected 200 release gate evaluate, got {resp.status_code}"
    data = resp.json()
    assert data.get("decision") in ["go", "no-go"]
    assert "go_rate" in data
