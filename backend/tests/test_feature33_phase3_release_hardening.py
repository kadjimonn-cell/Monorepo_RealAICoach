"""
Feature 33 Phase 3 release hardening contracts:
- rollout holdback contract for /api/content/library
- admin observability endpoint
- admin release-gate endpoint
"""

from __future__ import annotations

import os
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
BASIC_EMAIL = "f21.basic.1781338672@example.com"
BASIC_PASSWORD = "F21Basic#2026Aa"


def _admin_session() -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


def _basic_session() -> tuple[requests.Session, str]:
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": BASIC_EMAIL, "password": BASIC_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"basic login failed: {r.status_code} {r.text}"
    data = r.json() or {}
    user_id = (data.get("user") or {}).get("user_id") or data.get("user_id") or ""
    assert user_id, "basic user_id missing"
    return s, user_id


def test_feature33_library_response_contains_rollout_and_observability_contract() -> None:
    session, user_id = _basic_session()
    r = session.get(
        f"{BASE_URL}/api/content/library",
        params={"user_id": user_id, "sort": "recommended", "page": 1, "per_page": 12},
        timeout=20,
    )
    assert r.status_code in {200, 423}, f"unexpected status: {r.status_code} {r.text}"
    payload = r.json() or {}

    if r.status_code == 423:
        assert payload.get("error") == "feature_rollout_holdback"
        assert "rollout_percentage" in payload
        assert "bucket" in payload
        return

    assert "rollout" in payload, "rollout contract missing"
    rollout = payload.get("rollout") or {}
    assert "enabled" in rollout
    assert "rollout_percentage" in rollout
    assert "bucket" in rollout

    assert "observability" in payload, "observability contract missing"
    obs = payload.get("observability") or {}
    assert "latency_ms" in obs
    assert "feed_freshness_lag_hours" in obs


def test_feature33_admin_observability_endpoint_contract() -> None:
    session = _admin_session()
    r = session.get(f"{BASE_URL}/api/admin/content-library/observability?hours=24", timeout=20)
    assert r.status_code == 200, f"admin observability failed: {r.status_code} {r.text}"
    payload = r.json() or {}

    assert "lookback_hours" in payload
    assert "latency" in payload
    assert "freshness" in payload
    assert "conversion" in payload
    assert "events" in payload


def test_feature33_admin_release_gate_endpoint_contract() -> None:
    session = _admin_session()
    r = session.get(f"{BASE_URL}/api/admin/content-library/release-gate", timeout=20)
    assert r.status_code == 200, f"release gate failed: {r.status_code} {r.text}"
    payload = r.json() or {}

    assert payload.get("feature") == "feature33_library"
    assert payload.get("verdict") in {"pass", "warn"}
    assert isinstance(payload.get("checks"), dict)
    assert isinstance(payload.get("failed_checks"), list)
    assert isinstance(payload.get("transition_alert"), dict)
    assert "triggered" in (payload.get("transition_alert") or {})
    assert isinstance(payload.get("volume_context"), dict)
    volume_context = payload.get("volume_context") or {}
    assert "bookmark_toggle_events" in volume_context
    assert "recommendation_reason_click_events" in volume_context
    assert "min_bookmark_sample" in volume_context
    assert "min_recommendation_sample" in volume_context
    assert "bookmark_volume_guard_active" in volume_context
    assert "recommendation_volume_guard_active" in volume_context
    assert isinstance(payload.get("rollout"), dict)
    assert isinstance(payload.get("observability_snapshot"), dict)


def test_feature33_release_gate_alerting_implementation_contract() -> None:
    with open("/app/backend/routes/content.py", "r", encoding="utf-8") as f:
        source = f.read()

    assert "state_key = \"feature33_library_release_gate_state\"" in source
    assert "db.system_runtime_flags.update_one(" in source
    assert "db.admin_push_notifications.insert_one(" in source
    assert '"type": "feature33_release_gate_state_change"' in source
    assert "transition_alert" in source
    assert "bookmark_success_rate_over_15pct_or_low_volume_guard" in source
    assert "recommendation_open_after_click_rate_over_10pct_or_low_volume_guard" in source
    assert "volume_context" in source
