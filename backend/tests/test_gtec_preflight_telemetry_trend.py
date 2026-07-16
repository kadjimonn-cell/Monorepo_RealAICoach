"""Comprehensive tests for GTEC C5 Preflight Telemetry Trend feature.

Validates:
1. GET /api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend returns trend payload
2. Trend payload includes pass/fail split, reasons, mode_mix, latest_classification
3. mode_mix distinguishes strict_global vs diagnostic_relaxed
4. No regression in existing strict hotfix behavior
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest
import requests


def _load_base_url() -> str:
    env = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if env:
        return env.rstrip("/")

    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        text = env_file.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^REACT_APP_BACKEND_URL=(.+)$", text, re.M)
        if m:
            return m.group(1).strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _load_base_url()
LOCAL_FALLBACK_BASE_URL = "http://127.0.0.1:8001"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@realaicoach.app")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "NewAdminPass2026!")


# Module-level session to avoid rate limiting
_ADMIN_SESSION = None
_SESSION_TOKEN = None


def _is_admin_forbidden(response: requests.Response) -> bool:
    if response.status_code == 401:
        return True
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    if isinstance(detail, str) and "admin access required" in detail.lower():
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}:
            return True
        message = str(detail.get("message") or "").lower()
        if "admin access blocked" in message:
            return True

    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    return top_code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}


def _skip_if_admin_blocked_response(response: requests.Response, context: str) -> None:
    if _is_admin_forbidden(response):
        pytest.skip(f"{context} blocked by environment containment/authorization policy")


def _get_admin_session() -> requests.Session:
    """Get or create a shared admin session to avoid rate limiting."""
    global _ADMIN_SESSION, _SESSION_TOKEN, BASE_URL
    
    if _ADMIN_SESSION is not None and _SESSION_TOKEN is not None:
        return _ADMIN_SESSION
    
    s = requests.Session()
    login_resp = None
    candidates = [LOCAL_FALLBACK_BASE_URL, BASE_URL]
    for _ in range(8):
        for candidate in candidates:
            try:
                r = s.post(
                    f"{candidate}/api/auth/login",
                    json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    timeout=25,
                )
                login_resp = r
                if r.status_code == 200:
                    BASE_URL = candidate.rstrip("/")
                    break
            except Exception:
                continue
        if login_resp is not None and login_resp.status_code == 200:
            break
        time.sleep(2)

    if login_resp is None:
        pytest.skip("admin login failed: no response")
    if login_resp.status_code != 200:
        pytest.skip(
            f"login failed: {getattr(login_resp, 'status_code', 'no_response')} "
            f"{(login_resp.text[:200] if login_resp is not None else '')}"
        )
    data = login_resp.json()
    token = (
        data.get("session_token")
        or data.get("token")
        or data.get("access_token")
        or login_resp.cookies.get("session_token")
        or s.cookies.get("session_token")
    )
    if not token:
        pytest.skip("missing token in login JSON/cookies")
    s.headers.update({"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"})

    original_get = s.get

    def guarded_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        if _is_admin_forbidden(response):
            pytest.skip("Admin API blocked by environment containment/authorization policy")
        return response

    s.get = guarded_get
    
    _ADMIN_SESSION = s
    _SESSION_TOKEN = token
    return s


@pytest.fixture(scope="module")
def admin_session():
    """Module-scoped fixture for admin session."""
    return _get_admin_session()


class TestPreflightTelemetryTrend:
    """Tests for preflight telemetry trend endpoint and data contract."""

    def test_trend_endpoint_returns_200(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend returns 200"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend",
            timeout=30
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
        print("Trend endpoint returns 200 OK")

    def test_trend_payload_has_required_top_level_fields(self, admin_session):
        """Test trend payload contains trend object and generated_at"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend",
            timeout=30
        )
        assert r.status_code == 200
        body = r.json()
        
        assert "trend" in body, "Missing 'trend' key in response"
        assert "generated_at" in body, "Missing 'generated_at' key in response"
        print(f"Top-level fields present: trend, generated_at={body.get('generated_at')}")

    def test_trend_has_pass_fail_split(self, admin_session):
        """Test trend contains samples, passed, failed, pass_rate_percent"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend?hours=24&limit=100",
            timeout=30
        )
        assert r.status_code == 200
        trend = r.json().get("trend") or {}
        
        # Required pass/fail split fields
        assert "samples" in trend, "Missing 'samples' in trend"
        assert "passed" in trend, "Missing 'passed' in trend"
        assert "failed" in trend, "Missing 'failed' in trend"
        assert "pass_rate_percent" in trend, "Missing 'pass_rate_percent' in trend"
        
        # Validate types
        assert isinstance(trend["samples"], int), "samples should be int"
        assert isinstance(trend["passed"], int), "passed should be int"
        assert isinstance(trend["failed"], int), "failed should be int"
        assert trend["pass_rate_percent"] is None or isinstance(trend["pass_rate_percent"], (int, float)), \
            "pass_rate_percent should be number or null"
        
        # Validate consistency
        assert trend["passed"] + trend["failed"] == trend["samples"], \
            f"passed ({trend['passed']}) + failed ({trend['failed']}) should equal samples ({trend['samples']})"
        
        print(f"Pass/fail split: samples={trend['samples']}, passed={trend['passed']}, failed={trend['failed']}, rate={trend['pass_rate_percent']}%")

    def test_trend_has_top_fail_reasons(self, admin_session):
        """Test trend contains top_fail_reasons array with reason and count"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend?hours=24&limit=100",
            timeout=30
        )
        assert r.status_code == 200
        trend = r.json().get("trend") or {}
        
        assert "top_fail_reasons" in trend, "Missing 'top_fail_reasons' in trend"
        reasons = trend["top_fail_reasons"]
        assert isinstance(reasons, list), "top_fail_reasons should be a list"
        
        # If there are reasons, validate structure
        for reason_item in reasons:
            assert "reason" in reason_item, "Each reason item should have 'reason' key"
            assert "count" in reason_item, "Each reason item should have 'count' key"
            assert isinstance(reason_item["reason"], str), "reason should be string"
            assert isinstance(reason_item["count"], int), "count should be int"
        
        print(f"Top fail reasons: {reasons[:5]}")

    def test_trend_has_mode_mix_with_strict_and_relaxed(self, admin_session):
        """Test trend contains mode_mix with strict_global and diagnostic_relaxed"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend?hours=24&limit=100",
            timeout=30
        )
        assert r.status_code == 200
        trend = r.json().get("trend") or {}
        
        assert "mode_mix" in trend, "Missing 'mode_mix' in trend"
        mode_mix = trend["mode_mix"]
        
        # Must have both mode keys
        assert "strict_global" in mode_mix, "Missing 'strict_global' in mode_mix"
        assert "diagnostic_relaxed" in mode_mix, "Missing 'diagnostic_relaxed' in mode_mix"
        
        # Validate strict_global structure
        strict = mode_mix["strict_global"]
        assert "samples" in strict, "strict_global missing 'samples'"
        assert "failed" in strict, "strict_global missing 'failed'"
        assert "pass_rate_percent" in strict, "strict_global missing 'pass_rate_percent'"
        
        # Validate diagnostic_relaxed structure
        relaxed = mode_mix["diagnostic_relaxed"]
        assert "samples" in relaxed, "diagnostic_relaxed missing 'samples'"
        assert "failed" in relaxed, "diagnostic_relaxed missing 'failed'"
        assert "pass_rate_percent" in relaxed, "diagnostic_relaxed missing 'pass_rate_percent'"
        
        print(f"Mode mix - strict_global: samples={strict['samples']}, failed={strict['failed']}, rate={strict['pass_rate_percent']}")
        print(f"Mode mix - diagnostic_relaxed: samples={relaxed['samples']}, failed={relaxed['failed']}, rate={relaxed['pass_rate_percent']}")

    def test_trend_has_latest_classification(self, admin_session):
        """Test trend contains latest_classification field"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend?hours=24&limit=100",
            timeout=30
        )
        assert r.status_code == 200
        trend = r.json().get("trend") or {}
        
        assert "latest_classification" in trend, "Missing 'latest_classification' in trend"
        classification = trend["latest_classification"]
        
        # Valid values: "infra_blocked_window", "healthy_window", "none"
        valid_classifications = {"infra_blocked_window", "healthy_window", "none"}
        assert classification in valid_classifications, \
            f"Invalid latest_classification: {classification}, expected one of {valid_classifications}"
        
        print(f"Latest classification: {classification}")

    def test_trend_has_latest_telemetry_record(self, admin_session):
        """Test trend contains latest telemetry record with expected fields"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend?hours=24&limit=100",
            timeout=30
        )
        assert r.status_code == 200
        trend = r.json().get("trend") or {}
        
        assert "latest" in trend, "Missing 'latest' in trend"
        latest = trend["latest"]
        
        # latest can be None if no telemetry exists
        if latest is not None:
            # Required fields in telemetry record
            expected_fields = [
                "telemetry_id", "triggered_by", "actor", "attempt_tag", "attempt_index",
                "scan_mode", "passed", "required_checks", "attempts_completed",
                "reasons", "require_external_preview", "require_local_backend",
                "attempts", "checked_at", "created_at"
            ]
            for field in expected_fields:
                assert field in latest, f"Missing '{field}' in latest telemetry record"
            
            # Validate scan_mode is valid
            assert latest["scan_mode"] in {"STRICT_GLOBAL", "DIAGNOSTIC_RELAXED"}, \
                f"Invalid scan_mode: {latest['scan_mode']}"
            
            print(f"Latest telemetry: id={latest['telemetry_id']}, mode={latest['scan_mode']}, passed={latest['passed']}")
        else:
            print("No latest telemetry record (none recorded yet)")

    def test_trend_window_hours_parameter(self, admin_session):
        """Test hours parameter affects window_hours in response"""
        for hours in [1, 12, 24, 48]:
            r = admin_session.get(
                f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend?hours={hours}",
                timeout=30
            )
            assert r.status_code == 200
            trend = r.json().get("trend") or {}
            
            assert "window_hours" in trend, "Missing 'window_hours' in trend"
            # window_hours is clamped to max 168
            expected = min(hours, 168)
            assert trend["window_hours"] == expected, \
                f"Expected window_hours={expected}, got {trend['window_hours']}"
        
        print("Window hours parameter works correctly")

    def test_trend_limit_parameter(self, admin_session):
        """Test limit parameter affects sample_limit in response"""
        for limit in [10, 50, 100, 400]:
            r = admin_session.get(
                f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend?limit={limit}",
                timeout=30
            )
            assert r.status_code == 200
            trend = r.json().get("trend") or {}
            
            assert "sample_limit" in trend, "Missing 'sample_limit' in trend"
            # sample_limit is clamped to max 2000
            expected = min(limit, 2000)
            assert trend["sample_limit"] == expected, \
                f"Expected sample_limit={expected}, got {trend['sample_limit']}"
        
        print("Limit parameter works correctly")

    def test_trend_classification_matches_latest_passed_state(self, admin_session):
        """Test latest_classification is consistent with latest.passed"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/preflight-telemetry/trend?hours=24&limit=100",
            timeout=30
        )
        assert r.status_code == 200
        trend = r.json().get("trend") or {}
        
        latest = trend.get("latest")
        classification = trend.get("latest_classification")
        
        if latest is None:
            assert classification == "none", \
                f"Expected 'none' classification when no latest, got {classification}"
        else:
            passed = bool(latest.get("passed"))
            if passed:
                assert classification == "healthy_window", \
                    f"Expected 'healthy_window' when passed=True, got {classification}"
            else:
                assert classification == "infra_blocked_window", \
                    f"Expected 'infra_blocked_window' when passed=False, got {classification}"
        
        print(f"Classification consistency verified: latest.passed={latest.get('passed') if latest else None}, classification={classification}")


class TestStrictHotfixNoRegression:
    """Tests to ensure no regression in existing strict hotfix behavior."""

    def test_release_certificate_still_has_strict_run_policy(self, admin_session):
        """Verify release certificate still includes strict_run_policy fields"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate",
            timeout=30
        )
        assert r.status_code == 200
        body = r.json()
        
        checks = body.get("checks") or {}
        assert "strict_run_policy" in checks, "Missing strict_run_policy in release certificate checks"
        
        policy = checks["strict_run_policy"]
        expected_fields = [
            "scan_mode", "strict_global_mode", "transient_artifact_count",
            "strict_gate_passed", "preflight_require_external_preview", "preflight_require_local_backend"
        ]
        for field in expected_fields:
            assert field in policy, f"Missing '{field}' in strict_run_policy"
        
        print(f"Strict run policy in certificate: {policy}")

    def test_go_no_go_drill_still_validates_strict_gate(self, admin_session):
        """Verify GO/NO-GO drill still validates strict gate"""
        r = admin_session.post(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/go-no-go-drill",
            json={"simulate_hard_block": True},
            timeout=240
        )
        _skip_if_admin_blocked_response(r, "go-no-go drill strict gate validation")
        assert r.status_code == 200
        body = r.json()
        
        # Drill should have validation with strict gate check
        validation = body.get("validation") or {}
        assert "hard_block_validation_passed" in validation, "Missing hard_block_validation_passed"
        
        # Decision should be GO or NO_GO
        assert body.get("decision") in {"GO", "NO_GO"}, f"Invalid decision: {body.get('decision')}"
        
        print(f"GO/NO-GO drill: decision={body.get('decision')}, validation={validation}")

    def test_latest_report_has_strict_mode_fields(self, admin_session):
        """Verify latest report includes strict mode fields"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/latest",
            timeout=30
        )
        assert r.status_code == 200
        body = r.json()
        report = body.get("report")
        
        if report:
            # Check for strict mode fields
            assert "scan_mode" in report, "Missing scan_mode in report"
            assert "strict_global_mode" in report, "Missing strict_global_mode in report"
            
            scan_mode = report.get("scan_mode")
            assert scan_mode in {"STRICT_GLOBAL", "DIAGNOSTIC_RELAXED"}, \
                f"Invalid scan_mode: {scan_mode}"
            
            print(f"Latest report: scan_mode={scan_mode}, strict_global_mode={report.get('strict_global_mode')}")
        else:
            print("No latest report available")

    def test_manual_mutation_endpoints_still_blocked(self, admin_session):
        """Verify manual mutation endpoints remain blocked (403)"""
        blocked_endpoints = [
            ("POST", "/api/admin/gtec-scan-v2/run", {"viewports": "desktop"}),
            ("POST", "/api/admin/gtec-scan-v2/schedule", {"enabled": True}),
        ]
        
        for method, endpoint, body in blocked_endpoints:
            r = admin_session.post(f"{BASE_URL}{endpoint}", json=body, timeout=25)
            assert r.status_code == 403, \
                f"Expected 403 for {method} {endpoint}, got {r.status_code}"
        
        print("Manual mutation endpoints still blocked (403)")

    def test_trust_gates_endpoint_still_works(self, admin_session):
        """Verify trust gates endpoint still returns expected payload"""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/trust-gates",
            timeout=30
        )
        assert r.status_code == 200
        body = r.json()
        
        assert body.get("system_name") == "GTEC C5"
        assert "trust_score_percent" in body
        assert "passed_gates" in body
        assert "total_gates" in body
        assert "gates" in body
        
        print(f"Trust gates: score={body.get('trust_score_percent')}%, passed={body.get('passed_gates')}/{body.get('total_gates')}")
