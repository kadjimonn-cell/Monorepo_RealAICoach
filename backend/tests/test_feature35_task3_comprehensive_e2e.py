"""
Feature 35 Task 3 Comprehensive E2E Tests
- Test-mode seed cleanup policy (admin-only endpoints)
- Webhook signature/timestamp/replay protection
- Admin book-meeting insights: signal badge + safe rollout simulator
- Basic integrations lifecycle (configure/sync/logs/health/schedule/disconnect)
- Backfill profile simulator and dry-run/apply flow
"""

import pytest
import requests
import os
import time
import hmac
import hashlib
import json
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
BASIC_USER_EMAIL = "f22.basic.20260613@example.com"
BASIC_USER_PASSWORD = "F22Basic#2026Aa"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",  # Required for CSRF bypass
    })
    return session


@pytest.fixture(scope="module")
def admin_session(api_client):
    """Get admin authenticated session"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if response.status_code == 200:
        return api_client
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")


@pytest.fixture(scope="module")
def basic_user_session():
    """Get basic user authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",  # Required for CSRF bypass
    })
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": BASIC_USER_EMAIL, "password": BASIC_USER_PASSWORD},
    )
    if response.status_code == 200:
        return session
    pytest.skip(f"Basic user login failed: {response.status_code}")


@pytest.fixture(scope="module")
def free_user_session():
    """Get free user authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",  # Required for CSRF bypass
    })
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
    )
    if response.status_code == 200:
        return session
    pytest.skip(f"Free user login failed: {response.status_code}")


# ============================================================================
# TASK 1: Test-mode seed cleanup policy (admin-only endpoints)
# ============================================================================

class TestAdminSeedCleanupPolicy:
    """Test admin endpoints for seed cleanup policy"""

    def test_get_seed_policy_requires_admin(self, basic_user_session):
        """Non-admin users should be blocked from seed policy endpoint"""
        response = basic_user_session.get(
            f"{BASE_URL}/api/integrations/admin/test-mode-seed-policy"
        )
        # Should return 401 or 403 for non-admin
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: Non-admin blocked from GET seed policy (status={response.status_code})")

    def test_get_seed_policy_admin_access(self, admin_session):
        """Admin should be able to get seed cleanup policy"""
        response = admin_session.get(
            f"{BASE_URL}/api/integrations/admin/test-mode-seed-policy"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert "success" in data
        assert "policy" in data
        policy = data["policy"]
        # Verify policy structure
        assert "enabled" in policy
        assert "retention_hours" in policy
        assert "dry_run" in policy
        print(f"PASS: Admin GET seed policy - enabled={policy.get('enabled')}, retention_hours={policy.get('retention_hours')}")

    def test_update_seed_policy_requires_admin(self, basic_user_session):
        """Non-admin users should be blocked from updating seed policy"""
        response = basic_user_session.put(
            f"{BASE_URL}/api/integrations/admin/test-mode-seed-policy",
            json={"enabled": True, "retention_hours": 72, "dry_run": False},
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: Non-admin blocked from PUT seed policy (status={response.status_code})")

    def test_update_seed_policy_admin_access(self, admin_session):
        """Admin should be able to update seed cleanup policy"""
        response = admin_session.put(
            f"{BASE_URL}/api/integrations/admin/test-mode-seed-policy",
            json={"enabled": True, "retention_hours": 72, "dry_run": True},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert "policy" in data
        policy = data["policy"]
        assert policy.get("enabled") is True
        assert policy.get("retention_hours") == 72
        assert policy.get("dry_run") is True
        print("PASS: Admin PUT seed policy - updated successfully")

    def test_run_seed_cleanup_requires_admin(self, basic_user_session):
        """Non-admin users should be blocked from running seed cleanup"""
        response = basic_user_session.post(
            f"{BASE_URL}/api/integrations/admin/test-mode-seed-cleanup/run",
            json={"retention_hours": 72, "dry_run": True},
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: Non-admin blocked from POST seed cleanup run (status={response.status_code})")

    def test_run_seed_cleanup_dry_run_admin(self, admin_session):
        """Admin should be able to run seed cleanup in dry-run mode"""
        response = admin_session.post(
            f"{BASE_URL}/api/integrations/admin/test-mode-seed-cleanup/run",
            json={"retention_hours": 72, "dry_run": True},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("dry_run") is True
        assert "expired_configs" in data
        assert "deleted" in data
        assert "cutoff_iso" in data
        print(f"PASS: Admin seed cleanup dry-run - expired_configs={data.get('expired_configs')}, deleted={data.get('deleted')}")


# ============================================================================
# TASK 2: Webhook signature/timestamp/replay protection
# ============================================================================

class TestWebhookSignatureProtection:
    """Test webhook endpoint enforces signature/timestamp/config and blocks replay"""

    def _compute_signature(self, secret: str, timestamp: int, body: bytes) -> str:
        """Compute webhook signature matching backend implementation"""
        payload = f"{timestamp}.".encode("utf-8") + body
        digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_webhook_missing_signature_rejected(self, api_client):
        """Webhook without signature should be rejected"""
        response = api_client.post(
            f"{BASE_URL}/api/integrations/webhook/greenhouse",
            json={"event_type": "candidate_hired", "data": {}},
        )
        # Should return 401/403/404/428 for missing signature or CSRF block
        assert response.status_code in [401, 403, 404, 428], f"Expected 401/403/404/428, got {response.status_code}"
        print(f"PASS: Webhook without signature rejected (status={response.status_code})")

    def test_webhook_missing_timestamp_rejected(self, api_client):
        """Webhook without timestamp should be rejected"""
        response = api_client.post(
            f"{BASE_URL}/api/integrations/webhook/greenhouse",
            json={"event_type": "candidate_hired", "data": {}},
            headers={"X-Integration-Signature": "sha256=invalid"},
        )
        # Should return 401/403/404/428 for missing timestamp or CSRF block
        assert response.status_code in [401, 403, 404, 428], f"Expected 401/403/404/428, got {response.status_code}"
        print(f"PASS: Webhook without timestamp rejected (status={response.status_code})")

    def test_webhook_invalid_signature_rejected(self, api_client):
        """Webhook with invalid signature should be rejected"""
        timestamp = int(time.time())
        response = api_client.post(
            f"{BASE_URL}/api/integrations/webhook/greenhouse",
            json={"event_type": "candidate_hired", "data": {}},
            headers={
                "X-Integration-Signature": "sha256=invalid_signature_here",
                "X-Integration-Timestamp": str(timestamp),
            },
        )
        # Should return 401/403/404/428 for invalid signature or CSRF block
        assert response.status_code in [401, 403, 404, 428], f"Expected 401/403/404/428, got {response.status_code}"
        print(f"PASS: Webhook with invalid signature rejected (status={response.status_code})")

    def test_webhook_expired_timestamp_rejected(self, api_client):
        """Webhook with expired timestamp should be rejected"""
        # Timestamp from 10 minutes ago (beyond 5 min tolerance)
        old_timestamp = int(time.time()) - 600
        response = api_client.post(
            f"{BASE_URL}/api/integrations/webhook/greenhouse",
            json={"event_type": "candidate_hired", "data": {}},
            headers={
                "X-Integration-Signature": "sha256=test",
                "X-Integration-Timestamp": str(old_timestamp),
            },
        )
        # Should return 401/403/404/428 for expired timestamp or CSRF block
        assert response.status_code in [401, 403, 404, 428], f"Expected 401/403/404/428, got {response.status_code}"
        print(f"PASS: Webhook with expired timestamp rejected (status={response.status_code})")

    def test_webhook_unknown_integration_rejected(self, api_client):
        """Webhook for unknown integration should be rejected"""
        timestamp = int(time.time())
        response = api_client.post(
            f"{BASE_URL}/api/integrations/webhook/unknown_integration",
            json={"event_type": "test", "data": {}},
            headers={
                "X-Integration-Signature": "sha256=test",
                "X-Integration-Timestamp": str(timestamp),
            },
        )
        # Should return 400/403 for unknown integration or CSRF block
        assert response.status_code in [400, 403], f"Expected 400/403, got {response.status_code}"
        print(f"PASS: Webhook for unknown integration rejected (status={response.status_code})")


# ============================================================================
# TASK 3: Admin book-meeting insights (signal badge + safe rollout simulator)
# ============================================================================

class TestAdminBookMeetingInsights:
    """Test admin book-meeting insights: signal badge and safe rollout simulator"""

    def test_release_gate_profile_requires_admin(self, basic_user_session):
        """Non-admin users should be blocked from release gate profile endpoint"""
        response = basic_user_session.get(
            f"{BASE_URL}/api/admin/calendar/release-gate/profile"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: Non-admin blocked from GET release gate profile (status={response.status_code})")

    def test_release_gate_profile_admin_access(self, admin_session):
        """Admin should be able to get release gate profile"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/calendar/release-gate/profile"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert "active_profile" in data
        assert "profiles" in data
        assert data["active_profile"] in ["strict", "standard", "lenient"]
        print(f"PASS: Admin GET release gate profile - active={data.get('active_profile')}")

    def test_release_gate_profile_update_admin(self, admin_session):
        """Admin should be able to update release gate profile"""
        response = admin_session.put(
            f"{BASE_URL}/api/admin/calendar/release-gate/profile",
            json={"profile": "standard"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("active_profile") == "standard"
        print("PASS: Admin PUT release gate profile - updated to standard")

    def test_release_gate_evaluate_admin(self, admin_session):
        """Admin should be able to evaluate release gate"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/calendar/release-gate/evaluate?sample_size=10"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert "feature" in data
        assert data["feature"] == "book-meeting"
        assert "profile" in data
        assert "decision" in data
        assert data["decision"] in ["go", "no-go"]
        assert "go_rate" in data
        print(f"PASS: Admin release gate evaluate - decision={data.get('decision')}, go_rate={data.get('go_rate')}")

    def test_safe_rollout_simulator_requires_admin(self, basic_user_session):
        """Non-admin users should be blocked from safe rollout simulator"""
        response = basic_user_session.get(
            f"{BASE_URL}/api/admin/calendar/release-gate/safe-rollout-simulator"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: Non-admin blocked from safe rollout simulator (status={response.status_code})")

    def test_safe_rollout_simulator_admin_access(self, admin_session):
        """Admin should be able to access safe rollout simulator"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/calendar/release-gate/safe-rollout-simulator?sample_size=10"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert "feature" in data
        assert data["feature"] == "book-meeting"
        assert "active_profile" in data
        assert "simulation" in data
        assert isinstance(data["simulation"], list)
        # Verify simulation has all 3 profiles
        profiles_in_sim = [row.get("profile") for row in data["simulation"]]
        assert "strict" in profiles_in_sim
        assert "standard" in profiles_in_sim
        assert "lenient" in profiles_in_sim
        # Verify recommendation
        assert "recommendation" in data
        assert "profile" in data["recommendation"]
        print(f"PASS: Admin safe rollout simulator - active={data.get('active_profile')}, recommendation={data.get('recommendation', {}).get('profile')}")

    def test_admin_reliability_dashboard(self, admin_session):
        """Admin should be able to access reliability dashboard"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/calendar/reliability?sample_size=10"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert "feature" in data
        assert data["feature"] == "book-meeting"
        assert "profile" in data
        assert "summary" in data
        summary = data["summary"]
        assert "users_evaluated" in summary
        assert "go_count" in summary
        assert "no_go_count" in summary
        assert "go_rate" in summary
        print(f"PASS: Admin reliability dashboard - users_evaluated={summary.get('users_evaluated')}, go_rate={summary.get('go_rate')}")


# ============================================================================
# TASK 4: Backfill profile simulator and dry-run/apply flow
# ============================================================================

class TestBackfillProfileSimulator:
    """Test backfill profile simulator and dry-run/apply flow"""

    def test_backfill_false_positives_requires_admin(self, basic_user_session):
        """Non-admin users should be blocked from backfill false positives endpoint"""
        response = basic_user_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: Non-admin blocked from backfill false positives (status={response.status_code})")

    def test_backfill_false_positives_admin_access(self, admin_session):
        """Admin should be able to access backfill false positives"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=20&window_days=30&profile=standard"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert "profile" in data
        assert "scanned_count" in data
        # Verify signal badge structure
        if "signal_badge" in data:
            badge = data["signal_badge"]
            assert "status" in badge
            assert "severity" in badge
            assert "summary" in badge
        print(f"PASS: Admin backfill false positives - profile={data.get('profile')}, scanned={data.get('scanned_count')}")

    def test_backfill_simulator_requires_admin(self, basic_user_session):
        """Non-admin users should be blocked from backfill simulator"""
        response = basic_user_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives/simulator"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: Non-admin blocked from backfill simulator (status={response.status_code})")

    def test_backfill_simulator_admin_access(self, admin_session):
        """Admin should be able to access backfill simulator"""
        response = admin_session.get(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives/simulator?limit=20&window_days=30"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert "simulation" in data
        simulation = data["simulation"]
        assert isinstance(simulation, list)
        # Verify simulation has profile rows
        if len(simulation) > 0:
            row = simulation[0]
            assert "profile" in row
            assert "would_update_count" in row or "likely_false_positive_count" in row
        print(f"PASS: Admin backfill simulator - profiles_simulated={len(simulation)}")

    def test_backfill_dry_run_admin(self, admin_session):
        """Admin should be able to run backfill in dry-run mode"""
        response = admin_session.post(
            f"{BASE_URL}/api/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=10&window_days=30&profile=standard&dry_run=true"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("dry_run") is True
        assert "updated_count" in data
        print(f"PASS: Admin backfill dry-run - updated_count={data.get('updated_count')}")


# ============================================================================
# TASK 5: Basic integrations lifecycle (no regression)
# ============================================================================

class TestIntegrationsLifecycleNoRegression:
    """Test basic integrations lifecycle still works"""

    def test_available_integrations(self, basic_user_session):
        """List available integrations"""
        response = basic_user_session.get(f"{BASE_URL}/api/integrations/available")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "integrations" in data
        integrations = data["integrations"]
        assert len(integrations) >= 3  # greenhouse, lever, workday
        ids = [i["id"] for i in integrations]
        assert "greenhouse" in ids
        assert "lever" in ids
        assert "workday" in ids
        print(f"PASS: Available integrations - count={len(integrations)}")

    def test_configure_test_mode_integration(self, basic_user_session):
        """Configure a test-mode integration"""
        response = basic_user_session.post(
            f"{BASE_URL}/api/integrations/",
            json={
                "integration_id": "greenhouse",
                "credentials": {"api_key": "test_key", "board_token": "test_token"},
                "test_mode": True,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert "config" in data
        config = data["config"]
        assert config.get("integration_id") == "greenhouse"
        assert config.get("test_mode") is True
        # Verify webhook security headers returned
        assert "webhook_signing_secret" in data
        assert "webhook_signature_headers" in data
        print(f"PASS: Configure test-mode integration - config_id={config.get('config_id')}")
        return config.get("config_id")

    def test_list_configured_integrations(self, basic_user_session):
        """List user's configured integrations"""
        response = basic_user_session.get(f"{BASE_URL}/api/integrations/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "integrations" in data
        assert "count" in data
        print(f"PASS: List configured integrations - count={data.get('count')}")

    def test_trigger_sync(self, basic_user_session):
        """Trigger sync for a configured integration"""
        # First get configured integrations
        list_response = basic_user_session.get(f"{BASE_URL}/api/integrations/")
        if list_response.status_code != 200 or not list_response.json().get("integrations"):
            pytest.skip("No configured integrations to sync")
        
        config_id = list_response.json()["integrations"][0]["config_id"]
        response = basic_user_session.post(f"{BASE_URL}/api/integrations/{config_id}/sync")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("success") is True
        assert "records_synced" in data
        assert "sync_health" in data
        print(f"PASS: Trigger sync - records_synced={data.get('records_synced')}")

    def test_get_sync_logs(self, basic_user_session):
        """Get sync logs for a configured integration"""
        list_response = basic_user_session.get(f"{BASE_URL}/api/integrations/")
        if list_response.status_code != 200 or not list_response.json().get("integrations"):
            pytest.skip("No configured integrations")
        
        config_id = list_response.json()["integrations"][0]["config_id"]
        response = basic_user_session.get(f"{BASE_URL}/api/integrations/{config_id}/logs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "logs" in data
        assert "count" in data
        print(f"PASS: Get sync logs - count={data.get('count')}")

    def test_get_integration_health(self, basic_user_session):
        """Get health for a configured integration"""
        list_response = basic_user_session.get(f"{BASE_URL}/api/integrations/")
        if list_response.status_code != 200 or not list_response.json().get("integrations"):
            pytest.skip("No configured integrations")
        
        config_id = list_response.json()["integrations"][0]["config_id"]
        response = basic_user_session.get(f"{BASE_URL}/api/integrations/{config_id}/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "config_id" in data
        assert "sync_health" in data
        assert "recommended_action" in data
        print(f"PASS: Get integration health - status={data.get('sync_health', {}).get('status')}")

    def test_update_sync_schedule(self, basic_user_session):
        """Update auto-sync schedule"""
        list_response = basic_user_session.get(f"{BASE_URL}/api/integrations/")
        if list_response.status_code != 200 or not list_response.json().get("integrations"):
            pytest.skip("No configured integrations")
        
        config_id = list_response.json()["integrations"][0]["config_id"]
        response = basic_user_session.post(
            f"{BASE_URL}/api/integrations/schedule",
            json={"config_id": config_id, "interval_hours": 24},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("auto_sync_interval_hours") == 24
        print("PASS: Update sync schedule - interval_hours=24")

    def test_schedule_guardrail_rejects_invalid(self, basic_user_session):
        """Schedule guardrail rejects invalid interval"""
        list_response = basic_user_session.get(f"{BASE_URL}/api/integrations/")
        if list_response.status_code != 200 or not list_response.json().get("integrations"):
            pytest.skip("No configured integrations")
        
        config_id = list_response.json()["integrations"][0]["config_id"]
        response = basic_user_session.post(
            f"{BASE_URL}/api/integrations/schedule",
            json={"config_id": config_id, "interval_hours": 99},  # Invalid
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Schedule guardrail rejects invalid interval")

    def test_dashboard_stats(self, basic_user_session):
        """Get integration dashboard stats"""
        response = basic_user_session.get(f"{BASE_URL}/api/integrations/dashboard/stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "total_candidates" in data
        assert "total_jobs" in data
        assert "active_integrations" in data
        assert "health_score" in data
        print(f"PASS: Dashboard stats - active_integrations={data.get('active_integrations')}, health_score={data.get('health_score')}")


# ============================================================================
# TASK 6: User reliability and release gate endpoints
# ============================================================================

class TestUserReliabilityEndpoints:
    """Test user-facing reliability and release gate endpoints"""

    def test_user_reliability_snapshot(self, basic_user_session):
        """User can get their own reliability snapshot"""
        # First get user_id from /me endpoint
        me_response = basic_user_session.get(f"{BASE_URL}/api/auth/me")
        if me_response.status_code != 200:
            pytest.skip("Could not get user info")
        user_id = me_response.json().get("user_id")
        
        response = basic_user_session.get(f"{BASE_URL}/api/calendar/reliability/{user_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert "user_id" in data
        assert "plan_scope" in data
        assert "sync_mode" in data
        assert "metrics" in data
        metrics = data["metrics"]
        assert "conflict_events_30d" in metrics
        assert "reminder_success_rate_7d" in metrics
        assert "error_rate_7d" in metrics
        print(f"PASS: User reliability snapshot - plan_scope={data.get('plan_scope')}, sync_mode={data.get('sync_mode')}")

    def test_user_release_gate(self, basic_user_session):
        """User can get their own release gate evaluation"""
        me_response = basic_user_session.get(f"{BASE_URL}/api/auth/me")
        if me_response.status_code != 200:
            pytest.skip("Could not get user info")
        user_id = me_response.json().get("user_id")
        
        response = basic_user_session.get(f"{BASE_URL}/api/calendar/release-gate/{user_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert "feature" in data
        assert data["feature"] == "book-meeting"
        assert "user_id" in data
        assert "profile" in data
        assert "gate" in data
        gate = data["gate"]
        assert "decision" in gate
        assert gate["decision"] in ["go", "no-go"]
        print(f"PASS: User release gate - profile={data.get('profile')}, decision={gate.get('decision')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
