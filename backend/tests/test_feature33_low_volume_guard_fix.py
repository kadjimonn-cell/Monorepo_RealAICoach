"""
Feature 33 Low-Volume Guard Fix Verification Tests

Tests verify:
1. Release-gate endpoint uses low-volume guard logic for conversion checks
2. volume_context includes sample counts and guard flags
3. No false WARN due to 0/low volume samples
4. Transition alerting contract remains intact
5. Regression: observability and library endpoints still operational
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


# ── Test 1: Verify volume_context structure in release-gate response ──
def test_release_gate_volume_context_structure() -> None:
    """Verify release-gate response includes complete volume_context with guard flags."""
    session = _admin_session()
    r = session.get(f"{BASE_URL}/api/admin/content-library/release-gate", timeout=20)
    assert r.status_code == 200, f"release gate failed: {r.status_code} {r.text}"
    payload = r.json() or {}

    # Verify volume_context exists and has required fields
    assert "volume_context" in payload, "volume_context missing from release-gate response"
    volume_context = payload.get("volume_context") or {}

    # Required sample count fields
    assert "bookmark_toggle_events" in volume_context, "bookmark_toggle_events missing"
    assert "recommendation_reason_click_events" in volume_context, "recommendation_reason_click_events missing"

    # Required threshold fields
    assert "min_bookmark_sample" in volume_context, "min_bookmark_sample missing"
    assert "min_recommendation_sample" in volume_context, "min_recommendation_sample missing"

    # Required guard flag fields
    assert "bookmark_volume_guard_active" in volume_context, "bookmark_volume_guard_active missing"
    assert "recommendation_volume_guard_active" in volume_context, "recommendation_volume_guard_active missing"

    # Verify types
    assert isinstance(volume_context["bookmark_toggle_events"], int)
    assert isinstance(volume_context["recommendation_reason_click_events"], int)
    assert isinstance(volume_context["min_bookmark_sample"], int)
    assert isinstance(volume_context["min_recommendation_sample"], int)
    assert isinstance(volume_context["bookmark_volume_guard_active"], bool)
    assert isinstance(volume_context["recommendation_volume_guard_active"], bool)

    print(f"volume_context verified: {volume_context}")


# ── Test 2: Verify low-volume guard logic prevents false WARN ──
def test_release_gate_low_volume_guard_logic() -> None:
    """Verify that low-volume guard prevents false WARN when samples < threshold."""
    session = _admin_session()
    r = session.get(f"{BASE_URL}/api/admin/content-library/release-gate", timeout=20)
    assert r.status_code == 200, f"release gate failed: {r.status_code} {r.text}"
    payload = r.json() or {}

    volume_context = payload.get("volume_context") or {}
    checks = payload.get("checks") or {}
    failed_checks = payload.get("failed_checks") or []

    bookmark_events = volume_context.get("bookmark_toggle_events", 0)
    recommendation_events = volume_context.get("recommendation_reason_click_events", 0)
    min_bookmark = volume_context.get("min_bookmark_sample", 30)
    min_recommendation = volume_context.get("min_recommendation_sample", 30)

    bookmark_guard_active = volume_context.get("bookmark_volume_guard_active", False)
    recommendation_guard_active = volume_context.get("recommendation_volume_guard_active", False)

    # Verify guard activation logic
    expected_bookmark_guard = bookmark_events < min_bookmark
    expected_recommendation_guard = recommendation_events < min_recommendation

    assert bookmark_guard_active == expected_bookmark_guard, (
        f"bookmark_volume_guard_active mismatch: got {bookmark_guard_active}, "
        f"expected {expected_bookmark_guard} (events={bookmark_events}, min={min_bookmark})"
    )
    assert recommendation_guard_active == expected_recommendation_guard, (
        f"recommendation_volume_guard_active mismatch: got {recommendation_guard_active}, "
        f"expected {expected_recommendation_guard} (events={recommendation_events}, min={min_recommendation})"
    )

    # Verify check names include low_volume_guard suffix
    assert "bookmark_success_rate_over_15pct_or_low_volume_guard" in checks, (
        "bookmark check should include low_volume_guard suffix"
    )
    assert "recommendation_open_after_click_rate_over_10pct_or_low_volume_guard" in checks, (
        "recommendation check should include low_volume_guard suffix"
    )

    # If guard is active, the check should pass (not in failed_checks)
    if bookmark_guard_active:
        assert "bookmark_success_rate_over_15pct_or_low_volume_guard" not in failed_checks, (
            "bookmark check should pass when low-volume guard is active"
        )
        print(f"Bookmark low-volume guard active (events={bookmark_events} < min={min_bookmark}) - check passes")

    if recommendation_guard_active:
        assert "recommendation_open_after_click_rate_over_10pct_or_low_volume_guard" not in failed_checks, (
            "recommendation check should pass when low-volume guard is active"
        )
        print(f"Recommendation low-volume guard active (events={recommendation_events} < min={min_recommendation}) - check passes")


# ── Test 3: Verify transition_alert contract remains intact ──
def test_release_gate_transition_alert_contract() -> None:
    """Verify transition_alert structure is present and valid."""
    session = _admin_session()
    r = session.get(f"{BASE_URL}/api/admin/content-library/release-gate", timeout=20)
    assert r.status_code == 200, f"release gate failed: {r.status_code} {r.text}"
    payload = r.json() or {}

    assert "transition_alert" in payload, "transition_alert missing"
    transition_alert = payload.get("transition_alert") or {}

    # Required fields
    assert "triggered" in transition_alert, "triggered field missing in transition_alert"
    assert "from" in transition_alert, "from field missing in transition_alert"
    assert "to" in transition_alert, "to field missing in transition_alert"
    assert "severity" in transition_alert, "severity field missing in transition_alert"

    # Type checks
    assert isinstance(transition_alert["triggered"], bool)

    # If triggered, severity should be set
    if transition_alert["triggered"]:
        assert transition_alert["severity"] in {"info", "warning"}, (
            f"invalid severity: {transition_alert['severity']}"
        )
        assert transition_alert["from"] in {"pass", "warn", None}
        assert transition_alert["to"] in {"pass", "warn"}

    print(f"transition_alert verified: {transition_alert}")


# ── Test 4: Verify state persistence contract ──
def test_release_gate_state_persistence() -> None:
    """Verify release-gate persists state to system_runtime_flags."""
    session = _admin_session()

    # Call release-gate twice to ensure state is persisted
    r1 = session.get(f"{BASE_URL}/api/admin/content-library/release-gate", timeout=20)
    assert r1.status_code == 200
    payload1 = r1.json() or {}
    verdict1 = payload1.get("verdict")

    r2 = session.get(f"{BASE_URL}/api/admin/content-library/release-gate", timeout=20)
    assert r2.status_code == 200
    payload2 = r2.json() or {}
    verdict2 = payload2.get("verdict")

    # Verdicts should be consistent
    assert verdict1 == verdict2, f"verdict inconsistent: {verdict1} vs {verdict2}"

    # transition_alert.from should reflect previous state on second call
    transition_alert = payload2.get("transition_alert") or {}
    # If no change, triggered should be False
    if not transition_alert.get("triggered"):
        assert transition_alert.get("from") == transition_alert.get("to"), (
            "when not triggered, from and to should match"
        )

    print(f"State persistence verified: verdict={verdict2}")


# ── Test 5: Regression - observability endpoint still operational ──
def test_regression_observability_endpoint() -> None:
    """Verify /api/admin/content-library/observability still works."""
    session = _admin_session()
    r = session.get(f"{BASE_URL}/api/admin/content-library/observability?hours=24", timeout=20)
    assert r.status_code == 200, f"observability failed: {r.status_code} {r.text}"
    payload = r.json() or {}

    # Required fields
    assert "lookback_hours" in payload
    assert "volume" in payload
    assert "latency" in payload
    assert "freshness" in payload
    assert "conversion" in payload
    assert "events" in payload

    print(f"Observability endpoint operational: lookback_hours={payload.get('lookback_hours')}")


# ── Test 6: Regression - content library endpoint still operational ──
def test_regression_content_library_endpoint() -> None:
    """Verify /api/content/library still works for basic user."""
    session, user_id = _basic_session()
    r = session.get(
        f"{BASE_URL}/api/content/library",
        params={"user_id": user_id, "sort": "newest", "page": 1, "per_page": 12},
        timeout=20,
    )
    assert r.status_code in {200, 423}, f"library failed: {r.status_code} {r.text}"

    if r.status_code == 423:
        # Holdback is valid response
        payload = r.json() or {}
        assert payload.get("error") == "feature_rollout_holdback"
        print("Content library: user in holdback (valid)")
        return

    payload = r.json() or {}
    assert "items" in payload
    assert "rollout" in payload
    assert "observability" in payload

    print(f"Content library operational: items={len(payload.get('items', []))}")


# ── Test 7: Verify complete release-gate response contract ──
def test_release_gate_complete_response_contract() -> None:
    """Verify all required fields in release-gate response."""
    session = _admin_session()
    r = session.get(f"{BASE_URL}/api/admin/content-library/release-gate", timeout=20)
    assert r.status_code == 200, f"release gate failed: {r.status_code} {r.text}"
    payload = r.json() or {}

    # Top-level required fields
    required_fields = [
        "feature",
        "verdict",
        "checks",
        "failed_checks",
        "transition_alert",
        "volume_context",
        "rollout",
        "observability_snapshot",
        "generated_at",
    ]

    for field in required_fields:
        assert field in payload, f"required field '{field}' missing from release-gate response"

    # Verify feature name
    assert payload.get("feature") == "feature33_library"

    # Verify verdict is valid
    assert payload.get("verdict") in {"pass", "warn"}

    # Verify checks is dict
    assert isinstance(payload.get("checks"), dict)

    # Verify failed_checks is list
    assert isinstance(payload.get("failed_checks"), list)

    # Verify rollout structure
    rollout = payload.get("rollout") or {}
    assert "enabled" in rollout
    assert "rollout_percentage" in rollout
    assert "flag_key" in rollout

    # Verify observability_snapshot is present
    obs = payload.get("observability_snapshot") or {}
    assert "latency" in obs
    assert "freshness" in obs
    assert "conversion" in obs

    print(f"Complete response contract verified: verdict={payload.get('verdict')}, "
          f"failed_checks={payload.get('failed_checks')}")


# ── Test 8: Verify min sample thresholds are correct ──
def test_release_gate_min_sample_thresholds() -> None:
    """Verify min sample thresholds are set to expected values (30)."""
    session = _admin_session()
    r = session.get(f"{BASE_URL}/api/admin/content-library/release-gate", timeout=20)
    assert r.status_code == 200, f"release gate failed: {r.status_code} {r.text}"
    payload = r.json() or {}

    volume_context = payload.get("volume_context") or {}

    # Verify thresholds are 30 as per implementation
    assert volume_context.get("min_bookmark_sample") == 30, (
        f"min_bookmark_sample should be 30, got {volume_context.get('min_bookmark_sample')}"
    )
    assert volume_context.get("min_recommendation_sample") == 30, (
        f"min_recommendation_sample should be 30, got {volume_context.get('min_recommendation_sample')}"
    )

    print("Min sample thresholds verified: bookmark=30, recommendation=30")
