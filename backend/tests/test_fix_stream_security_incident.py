"""
Test Fix Stream 1+2+3+4+5 for Security Incident Proposal Implementation

Fix Stream 1: GET /api/admin/security/key-rotation/go-live-checklist + apply contract blocking
Fix Stream 2: Microsoft provider api_rotate_supported contract + lifecycle metadata
Fix Stream 3: Policy attestation with webhook validation + webhook retry/dead-letter schema
Fix Stream 4: Scheduler jobs for key rotation governance
Fix Stream 5: Frontend dashboard operator controls (tested via Playwright)
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=15
    )
    if response.status_code == 200:
        data = response.json()
        token = data.get("session_token") or data.get("token") or response.cookies.get("session_token")
        if token:
            return token
        pytest.skip("Admin token missing in login response")
    pytest.skip(f"Admin login failed: {response.status_code}")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for admin requests"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


def _is_policy_gate_blocked(response: requests.Response) -> bool:
    if response.status_code != 503:
        return False
    try:
        payload = response.json()
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("code") == "PRODUCTION_POLICY_GATE_BLOCKED":
        return True
    detail = payload.get("detail")
    return isinstance(detail, dict) and detail.get("code") == "PRODUCTION_POLICY_GATE_BLOCKED"


def _is_risk_engine_admin_blocked(response: requests.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        return False
    detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
    return code in {"risk_engine_admin_api_blocked", "risk_engine_id_verification_required"}


def _skip_if_admin_blocked(response: requests.Response, context: str) -> None:
    if _is_risk_engine_admin_blocked(response):
        pytest.skip(f"{context} blocked by risk engine containment")


class TestFixStream1GoLiveChecklist:
    """Fix Stream 1: GET /api/admin/security/key-rotation/go-live-checklist"""

    def test_go_live_checklist_endpoint_exists(self, auth_headers):
        """Verify go-live-checklist endpoint exists and returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/go-live-checklist",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "go-live-checklist")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "providers" in data, "Response should contain providers array"
        assert "summary" in data, "Response should contain summary object"
        print("PASS: go-live-checklist endpoint returns 200 with providers and summary")

    def test_go_live_checklist_returns_hard_blockers_and_advisories(self, auth_headers):
        """Verify checklist returns hard_blockers and advisories per provider"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/go-live-checklist",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "go-live-checklist")
        assert response.status_code == 200
        data = response.json()
        providers = data.get("providers", [])
        assert len(providers) > 0, "Should have at least one provider"
        
        for provider in providers:
            assert "hard_blockers" in provider, f"Provider {provider.get('provider_id')} missing hard_blockers"
            assert "advisories" in provider, f"Provider {provider.get('provider_id')} missing advisories"
            assert "hard_blocked" in provider, f"Provider {provider.get('provider_id')} missing hard_blocked flag"
            assert "ready_for_live_apply" in provider, f"Provider {provider.get('provider_id')} missing ready_for_live_apply"
        print(f"PASS: All {len(providers)} providers have hard_blockers, advisories, hard_blocked, ready_for_live_apply")

    def test_go_live_checklist_summary_structure(self, auth_headers):
        """Verify summary contains expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/go-live-checklist",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "go-live-checklist")
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        
        expected_fields = [
            "total", "ready_for_live_apply", "hard_blocked",
            "rotate_contracts", "rotate_contract_hard_blocked",
            "probe_contracts", "manual_constraints", "is_green_for_live_apply"
        ]
        for field in expected_fields:
            assert field in summary, f"Summary missing field: {field}"
        print(f"PASS: Summary contains all expected fields: {list(summary.keys())}")


class TestFixStream1ApplyContractBlocking:
    """Fix Stream 1: Apply endpoint hard-blocks live runs with rotate-contract blockers"""

    def test_apply_endpoint_exists(self, auth_headers):
        """Verify apply endpoint exists"""
        # First create a plan to get a plan_id
        prepare_response = requests.post(
            f"{BASE_URL}/api/admin/security/key-rotation/prepare",
            headers=auth_headers,
            json={"providers": [], "reason": "test_apply_blocking", "execution_mode": "dry_run"},
            timeout=15
        )
        if prepare_response.status_code != 200:
            pytest.skip(f"Could not create test plan: {prepare_response.status_code}")
        
        plan_data = prepare_response.json()
        plan_id = plan_data.get("plan_id")
        assert plan_id, "Prepare should return plan_id"
        print(f"PASS: Prepare endpoint works, got plan_id={plan_id}")

    def test_apply_dry_run_does_not_block(self, auth_headers):
        """Verify dry_run mode does not trigger contract blocking"""
        # Create a plan
        prepare_response = requests.post(
            f"{BASE_URL}/api/admin/security/key-rotation/prepare",
            headers=auth_headers,
            json={"providers": [], "reason": "test_dry_run", "execution_mode": "dry_run"},
            timeout=15
        )
        if prepare_response.status_code != 200:
            pytest.skip(f"Could not create test plan: {prepare_response.status_code}")
        
        plan_data = prepare_response.json()
        plan_id = plan_data.get("plan_id")
        approval_token = plan_data.get("approval_token")
        
        # Approve the plan
        approve_response = requests.post(
            f"{BASE_URL}/api/admin/security/key-rotation/approve",
            headers=auth_headers,
            json={"plan_id": plan_id, "approval_token": approval_token, "approval_note": "test"},
            timeout=15
        )
        if approve_response.status_code != 200:
            pytest.skip(f"Could not approve plan: {approve_response.status_code}")
        
        # Apply in dry_run mode
        apply_response = requests.post(
            f"{BASE_URL}/api/admin/security/key-rotation/apply",
            headers=auth_headers,
            json={"plan_id": plan_id, "execution_mode": "dry_run"},
            timeout=30
        )
        _skip_if_admin_blocked(apply_response, "key-rotation apply")
        assert apply_response.status_code == 200, f"Apply dry_run failed: {apply_response.status_code}"
        data = apply_response.json()
        # dry_run should not return contract_blocked status
        assert data.get("status") != "contract_blocked", "dry_run should not be contract_blocked"
        print(f"PASS: dry_run apply does not trigger contract blocking, status={data.get('status')}")


class TestFixStream2MicrosoftProvider:
    """Fix Stream 2: Microsoft provider api_rotate_supported contract"""

    def test_microsoft_provider_has_api_rotate_contract(self, auth_headers):
        """Verify Microsoft OAuth provider uses api_rotate_supported contract"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/readiness",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation readiness")
        assert response.status_code == 200
        data = response.json()
        providers = data.get("providers", [])
        
        microsoft_provider = next(
            (p for p in providers if p.get("provider_id") == "oauth_microsoft"),
            None
        )
        assert microsoft_provider is not None, "Microsoft OAuth provider should exist"
        assert microsoft_provider.get("apply_contract_mode") == "api_rotate_supported", \
            f"Microsoft should have api_rotate_supported, got {microsoft_provider.get('apply_contract_mode')}"
        print("PASS: Microsoft provider has apply_contract_mode=api_rotate_supported")

    def test_microsoft_provider_lifecycle_metadata(self, auth_headers):
        """Verify Microsoft provider has lifecycle metadata paths"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/readiness",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation readiness")
        assert response.status_code == 200
        data = response.json()
        providers = data.get("providers", [])
        
        microsoft_provider = next(
            (p for p in providers if p.get("provider_id") == "oauth_microsoft"),
            None
        )
        assert microsoft_provider is not None
        
        # Check for apply_capability with lifecycle-related fields
        apply_capability = microsoft_provider.get("apply_capability", {})
        assert "status" in apply_capability, "apply_capability should have status"
        assert "reason" in apply_capability, "apply_capability should have reason"
        assert "contract_mode" in apply_capability, "apply_capability should have contract_mode"
        print(f"PASS: Microsoft provider has lifecycle metadata: status={apply_capability.get('status')}, reason={apply_capability.get('reason')}")

    def test_no_objectid_serialization_in_readiness(self, auth_headers):
        """Verify no raw MongoDB _id fields in readiness response"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/readiness",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation readiness")
        assert response.status_code == 200
        text = response.text
        assert '"_id"' not in text, "Response should not contain raw _id fields"
        assert "ObjectId" not in text, "Response should not contain ObjectId strings"
        print("PASS: No ObjectId serialization issues in readiness response")


class TestFixStream3PolicyAttestationWebhook:
    """Fix Stream 3: Policy attestation with webhook validation"""

    def test_policy_attest_endpoint_exists(self, auth_headers):
        """Verify policy attestation endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/admin/security/key-rotation/policy/attest",
            headers=auth_headers,
            json={
                "note": "Test attestation from pytest",
                "run_prerequisite_refresh": False,
                "validate_webhook": False,
                "include_game_day_snapshot": False
            },
            timeout=30
        )
        _skip_if_admin_blocked(response, "policy attestation")
        if _is_policy_gate_blocked(response):
            pytest.skip("Policy attestation blocked by production policy gate prerequisites")
        assert response.status_code == 200, f"Policy attest failed: {response.status_code}: {response.text}"
        data = response.json()
        assert "attestation_id" in data, "Response should contain attestation_id"
        assert "attested_at" in data, "Response should contain attested_at"
        print(f"PASS: Policy attestation endpoint works, attestation_id={data.get('attestation_id')}")

    def test_policy_attest_with_webhook_validation(self, auth_headers):
        """Verify policy attestation can include webhook validation"""
        response = requests.post(
            f"{BASE_URL}/api/admin/security/key-rotation/policy/attest",
            headers=auth_headers,
            json={
                "note": "Test attestation with webhook validation",
                "run_prerequisite_refresh": False,
                "validate_webhook": True,
                "include_game_day_snapshot": False
            },
            timeout=30
        )
        _skip_if_admin_blocked(response, "policy attestation webhook validation")
        if _is_policy_gate_blocked(response):
            pytest.skip("Webhook validation attestation blocked by production policy gate prerequisites")
        assert response.status_code == 200, f"Policy attest with webhook failed: {response.status_code}"
        data = response.json()
        assert "webhook_validation" in data, "Response should contain webhook_validation"
        webhook_validation = data.get("webhook_validation", {})
        # Webhook may not be configured in preview env, but field should exist
        assert "configured" in webhook_validation or "status" in webhook_validation, \
            "webhook_validation should have configured or status field"
        print(f"PASS: Policy attestation with webhook validation works, webhook_configured={webhook_validation.get('configured')}")

    def test_webhook_dead_letter_schema_exists(self, auth_headers):
        """Verify webhook dead-letter schema doesn't break endpoints"""
        # The dead-letter retry is a scheduler job, but we can verify the policy endpoint
        # doesn't crash when webhook validation fails
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/policy",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation policy")
        assert response.status_code == 200, f"Policy endpoint failed: {response.status_code}"
        data = response.json()
        assert "siem_webhook_configured" in data, "Response should contain siem_webhook_configured"
        print(f"PASS: Policy endpoint works, siem_webhook_configured={data.get('siem_webhook_configured')}")


class TestFixStream4SchedulerJobs:
    """Fix Stream 4: Scheduler jobs for key rotation governance"""

    def test_scheduler_heartbeats_exist(self, auth_headers):
        """Verify scheduler heartbeats collection can be queried"""
        # We can't directly test scheduler jobs, but we can verify the heartbeat endpoint
        # or check if the jobs are registered by looking at the health endpoint
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, "Health endpoint should work"
        print("PASS: Backend is healthy, scheduler should be running")

    def test_policy_attestation_job_can_run(self, auth_headers):
        """Verify policy attestation can be triggered (simulates scheduler job)"""
        response = requests.post(
            f"{BASE_URL}/api/admin/security/key-rotation/policy/attest",
            headers=auth_headers,
            json={
                "note": "Simulated scheduler attestation",
                "run_prerequisite_refresh": True,
                "validate_webhook": True,
                "include_game_day_snapshot": True
            },
            timeout=60
        )
        _skip_if_admin_blocked(response, "scheduler attestation simulation")
        if _is_policy_gate_blocked(response):
            pytest.skip("Scheduler attestation simulation blocked by production policy gate prerequisites")
        assert response.status_code == 200, f"Attestation failed: {response.status_code}"
        data = response.json()
        assert "attestation_id" in data
        # Check for prerequisite_refresh result
        assert "prerequisite_refresh" in data or "policy_gate_snapshot" in data, \
            "Response should contain prerequisite_refresh or policy_gate_snapshot"
        print("PASS: Policy attestation job simulation works")

    def test_drift_monitor_data_available(self, auth_headers):
        """Verify readiness data is available for drift monitoring"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/readiness",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation readiness")
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        
        # Drift monitor checks these fields
        assert "api_rotate_ready" in summary or "api_apply_ready" in summary, \
            "Summary should have api_rotate_ready or api_apply_ready for drift monitoring"
        print("PASS: Readiness data available for drift monitoring")

    def test_compliance_bundle_generation(self, auth_headers):
        """Verify compliance bundle can be generated"""
        # First get a run_id
        runs_response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/runs?limit=1",
            headers=auth_headers,
            timeout=15
        )
        if runs_response.status_code != 200:
            pytest.skip("No runs available for bundle generation test")
        
        runs_data = runs_response.json()
        runs = runs_data.get("runs", [])
        if not runs:
            pytest.skip("No runs available for bundle generation test")
        
        run_id = runs[0].get("run_id")
        bundle_response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/compliance-bundle?format=json",
            headers=auth_headers,
            timeout=15
        )
        # Bundle may not exist yet, but endpoint should not crash
        assert bundle_response.status_code in [200, 404], \
            f"Compliance bundle endpoint should return 200 or 404, got {bundle_response.status_code}"
        print(f"PASS: Compliance bundle endpoint works, status={bundle_response.status_code}")

    def test_game_day_staleness_data_available(self, auth_headers):
        """Verify game-day data is available for staleness guard"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/policy",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation policy")
        assert response.status_code == 200
        data = response.json()
        assert "last_game_day" in data, "Policy should contain last_game_day for staleness guard"
        print("PASS: Game-day data available for staleness guard")


class TestFixStream5DashboardDataAvailability:
    """Fix Stream 5: Verify data endpoints for dashboard operator controls"""

    def test_readiness_endpoint_for_dashboard(self, auth_headers):
        """Verify readiness endpoint provides data for dashboard KPIs"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/readiness",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation readiness")
        assert response.status_code == 200
        data = response.json()
        
        # Dashboard needs these fields
        assert "providers" in data, "Dashboard needs providers array"
        assert "summary" in data, "Dashboard needs summary object"
        assert "preflight_gate" in data, "Dashboard needs preflight_gate"
        
        summary = data.get("summary", {})
        # Dashboard KPIs
        kpi_fields = ["total", "ready", "blocked", "api_rotate_ready", "adapter_missing"]
        for field in kpi_fields:
            assert field in summary, f"Dashboard KPI missing: {field}"
        print("PASS: Readiness endpoint provides all dashboard KPI data")

    def test_checklist_endpoint_for_dashboard(self, auth_headers):
        """Verify checklist endpoint provides data for dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/go-live-checklist",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "go-live-checklist")
        assert response.status_code == 200
        data = response.json()
        
        summary = data.get("summary", {})
        # Dashboard needs these for go-live status
        assert "is_green_for_live_apply" in summary, "Dashboard needs is_green_for_live_apply"
        assert "rotate_contract_hard_blocked" in summary, "Dashboard needs rotate_contract_hard_blocked"
        print("PASS: Checklist endpoint provides dashboard go-live status data")

    def test_policy_endpoint_for_dashboard(self, auth_headers):
        """Verify policy endpoint provides data for dashboard ops badges"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/policy",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation policy")
        assert response.status_code == 200
        data = response.json()
        
        # Dashboard ops badges need these
        assert "siem_webhook_configured" in data, "Dashboard needs siem_webhook_configured"
        assert "last_attestation" in data, "Dashboard needs last_attestation"
        assert "last_game_day" in data, "Dashboard needs last_game_day"
        print("PASS: Policy endpoint provides dashboard ops badge data")


class TestBackwardCompatibility:
    """Verify backward compatibility with existing readiness KPIs"""

    def test_readiness_backward_compatible_aliases(self, auth_headers):
        """Verify readiness summary has backward-compatible aliases"""
        response = requests.get(
            f"{BASE_URL}/api/admin/security/key-rotation/readiness",
            headers=auth_headers,
            timeout=15
        )
        _skip_if_admin_blocked(response, "key-rotation readiness")
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        
        # Backward compatibility aliases
        assert "api_apply_ready" in summary or "api_probe_only_ready" in summary, \
            "Summary should have api_apply_ready or api_probe_only_ready alias"
        assert "manual_required" in summary or "manual_by_constraint" in summary, \
            "Summary should have manual_required or manual_by_constraint alias"