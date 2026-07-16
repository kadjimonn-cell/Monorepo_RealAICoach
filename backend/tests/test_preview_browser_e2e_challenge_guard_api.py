"""
Test suite for Preview Browser E2E Challenge Guard API Contract.

Validates:
1. Scheduler challenge classification guard is deterministic (v2_deterministic)
2. Preview-browser E2E payload includes challenge_detection_guard field in API responses
3. Status contract preserved: PASS/FAIL/BLOCKED + status_reason_code + external_lane_status + localhost_fallback_status
4. No regression in preview-browser E2E admin endpoints after guard patch
"""

import os
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text[:200]}")
    
    return session


class TestChallengeGuardSourceContract:
    """Static source-level contract tests for challenge guard."""
    
    def test_scheduler_has_deterministic_challenge_guard_v2(self):
        """Verify scheduler has v2_deterministic guard version."""
        source = Path("/app/backend/scheduler_jobs/audit_gates.py").read_text(encoding="utf-8", errors="ignore")
        
        assert 'PREVIEW_CHALLENGE_GUARD_VERSION = "v2_deterministic"' in source, \
            "Missing v2_deterministic guard version constant"
        assert "def _classify_external_preview_block(" in source, \
            "Missing _classify_external_preview_block function"
        assert "strict_cloudflare_markers" in source, \
            "Missing strict_cloudflare_markers for deterministic detection"
        assert "soft_cloudflare_markers" in source, \
            "Missing soft_cloudflare_markers for false-positive prevention"
        assert "app_shell_markers" in source, \
            "Missing app_shell_markers for app detection"
        assert "title_has_challenge" in source, \
            "Missing title_has_challenge check"
        assert "challenge_detection_guard" in source, \
            "Missing challenge_detection_guard payload field"
    
    def test_platform_health_exposes_challenge_guard_payload(self):
        """Verify platform_health.py exposes challenge_detection_guard in API projection."""
        source = Path("/app/backend/routes/platform_health.py").read_text(encoding="utf-8", errors="ignore")
        
        assert '"challenge_detection_guard": 1' in source, \
            "Missing challenge_detection_guard in MongoDB projection"
        assert '"challenge_detection_guard": item.get("challenge_detection_guard") or {}' in source, \
            "Missing challenge_detection_guard in normalized history response"


class TestPreviewBrowserE2ELatestAPI:
    """Runtime API tests for /api/admin/platform-health/preview-browser-e2e/latest."""
    
    def test_latest_endpoint_requires_admin(self):
        """Verify endpoint requires admin authentication."""
        response = requests.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {response.status_code}"
    
    def test_latest_endpoint_returns_200_for_admin(self, admin_session):
        """Verify endpoint returns 200 for authenticated admin."""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200, \
            f"Expected 200 for admin, got {response.status_code}: {response.text[:300]}"
    
    def test_latest_response_structure(self, admin_session):
        """Verify response has required top-level fields."""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        
        data = response.json()
        
        # Required top-level fields
        required_fields = ["latest", "history", "trend", "alert_state", "runtime_state", "heartbeat", "job_id"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
    
    def test_latest_has_status_contract_fields(self, admin_session):
        """Verify latest run has status contract fields: PASS/FAIL/BLOCKED + status_reason_code + external_lane_status + localhost_fallback_status."""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        
        data = response.json()
        latest = data.get("latest", {})
        
        # If there's a latest run, verify status contract
        if latest and latest.get("run_id"):
            # Status must be one of PASS/FAIL/BLOCKED
            status = str(latest.get("status") or "").lower()
            assert status in ["pass", "fail", "blocked"], \
                f"Status must be pass/fail/blocked, got: {status}"
            
            # Must have status_reason_code
            assert "status_reason_code" in latest, \
                "Missing status_reason_code in latest run"
            
            # Must have external_lane_status
            assert "external_lane_status" in latest, \
                "Missing external_lane_status in latest run"
            
            # Must have localhost_fallback_status
            assert "localhost_fallback_status" in latest, \
                "Missing localhost_fallback_status in latest run"
    
    def test_latest_has_challenge_detection_guard(self, admin_session):
        """Verify latest run includes challenge_detection_guard field when available."""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        
        data = response.json()
        latest = data.get("latest", {})
        
        # If there's a latest run, verify challenge_detection_guard
        if latest and latest.get("run_id"):
            # Note: challenge_detection_guard may be missing if the run failed before
            # reaching the challenge detection phase (e.g., Playwright runtime failure)
            blocking_reason = str(latest.get("blocking_reason") or "")
            is_runtime_failure = "Playwright" in blocking_reason or "Executable doesn't exist" in blocking_reason
            
            if is_runtime_failure:
                # Runtime failures don't have challenge_detection_guard - this is expected
                print(f"Skipping challenge_detection_guard check - runtime failure detected: {blocking_reason[:100]}")
            else:
                # Normal runs should have challenge_detection_guard
                assert "challenge_detection_guard" in latest, \
                    "Missing challenge_detection_guard in latest run"
                
                guard = latest.get("challenge_detection_guard", {})
                if guard:
                    # Verify guard has expected structure
                    assert "guard_version" in guard, \
                        "Missing guard_version in challenge_detection_guard"
                    assert guard.get("guard_version") == "v2_deterministic", \
                        f"Expected v2_deterministic guard version, got: {guard.get('guard_version')}"
    
    def test_history_items_have_challenge_detection_guard(self, admin_session):
        """Verify history items include challenge_detection_guard field."""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        
        data = response.json()
        history = data.get("history", [])
        
        # If there's history, verify each item has challenge_detection_guard
        for item in history[:5]:  # Check first 5 items
            assert "challenge_detection_guard" in item, \
                f"Missing challenge_detection_guard in history item: {item.get('run_id')}"
            
            # Verify status contract in history items
            status = str(item.get("status") or "").lower()
            if status:
                assert status in ["pass", "fail", "blocked"], \
                    f"History item status must be pass/fail/blocked, got: {status}"
    
    def test_trend_statistics_present(self, admin_session):
        """Verify trend statistics are present and valid."""
        response = admin_session.get(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest")
        assert response.status_code == 200
        
        data = response.json()
        trend = data.get("trend", {})
        
        # Required trend fields
        required_trend_fields = ["window_days", "total", "pass_count", "fail_count", "blocked_count", "pass_rate"]
        for field in required_trend_fields:
            assert field in trend, f"Missing trend field: {field}"
        
        # Validate types
        assert isinstance(trend.get("total"), int), "trend.total must be int"
        assert isinstance(trend.get("pass_count"), int), "trend.pass_count must be int"
        assert isinstance(trend.get("fail_count"), int), "trend.fail_count must be int"
        assert isinstance(trend.get("blocked_count"), int), "trend.blocked_count must be int"


class TestChallengeGuardClassificationLogic:
    """Tests for the deterministic challenge classification logic."""
    
    def test_classify_function_exists_and_is_deterministic(self):
        """Verify _classify_external_preview_block function has deterministic logic."""
        source = Path("/app/backend/scheduler_jobs/audit_gates.py").read_text(encoding="utf-8", errors="ignore")
        
        # Verify deterministic classification rules
        assert "title_has_challenge and (len(strict_hits) >= 1 or len(soft_hits) >= 2) and len(app_shell_hits) <= 1" in source, \
            "Missing deterministic rule 1: title_has_challenge with strict/soft hits"
        assert "len(strict_hits) >= 2 and len(app_shell_hits) == 0" in source, \
            "Missing deterministic rule 2: strict_hits >= 2 with no app_shell"
        assert "len(strict_hits) >= 3" in source, \
            "Missing deterministic rule 3: strict_hits >= 3"
    
    def test_strict_markers_include_key_cloudflare_indicators(self):
        """Verify strict markers include key Cloudflare challenge indicators."""
        source = Path("/app/backend/scheduler_jobs/audit_gates.py").read_text(encoding="utf-8", errors="ignore")
        
        key_strict_markers = [
            "challenges.cloudflare.com",
            "__cf_chl",
            "cf-browser-verification",
            "ray id",
        ]
        
        for marker in key_strict_markers:
            assert marker in source, f"Missing key strict marker: {marker}"
    
    def test_soft_markers_prevent_false_positives(self):
        """Verify soft markers are separated to prevent false positives."""
        source = Path("/app/backend/scheduler_jobs/audit_gates.py").read_text(encoding="utf-8", errors="ignore")
        
        # These markers alone should NOT trigger Cloudflare detection
        soft_markers = [
            "cloudflare",
            "verify you are human",
        ]
        
        for marker in soft_markers:
            assert marker in source, f"Missing soft marker: {marker}"
        
        # Verify soft markers are in separate list from strict
        assert "soft_cloudflare_markers" in source, "Missing soft_cloudflare_markers list"
        assert "strict_cloudflare_markers" in source, "Missing strict_cloudflare_markers list"
    
    def test_app_shell_markers_prevent_false_positives(self):
        """Verify app shell markers are used to prevent false positives."""
        source = Path("/app/backend/scheduler_jobs/audit_gates.py").read_text(encoding="utf-8", errors="ignore")
        
        # Note: markers in source are escaped as 'id=\"root\"' not 'id="root"'
        app_shell_markers = [
            'id=\\"root\\"',  # Escaped version in source
            "realaicoach",
        ]
        
        for marker in app_shell_markers:
            assert marker.lower() in source.lower(), f"Missing app shell marker: {marker}"


class TestNoRegressionAfterGuardPatch:
    """Verify no regression in preview-browser E2E admin endpoints."""
    
    def test_health_endpoint_still_works(self, admin_session):
        """Verify /api/health still works."""
        response = admin_session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health endpoint failed: {response.status_code}"
    
    def test_preview_browser_e2e_run_endpoint_exists(self, admin_session):
        """Verify /api/admin/platform-health/preview-browser-e2e/run endpoint exists."""
        # Just verify endpoint exists (don't actually trigger a run)
        response = admin_session.options(f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/run")
        # Should not be 404
        assert response.status_code != 404, "preview-browser-e2e/run endpoint not found"
    
    def test_latest_endpoint_with_params(self, admin_session):
        """Verify latest endpoint accepts limit and window_days params."""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/latest",
            params={"limit": 10, "window_days": 3}
        )
        assert response.status_code == 200, \
            f"Latest endpoint with params failed: {response.status_code}"
        
        data = response.json()
        history = data.get("history", [])
        assert len(history) <= 10, "Limit param not respected"
        
        trend = data.get("trend", {})
        assert trend.get("window_days") == 3, "window_days param not respected"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
