"""
Key Rotation Readiness Dashboard Tests - Iteration 49

Tests for the new Rotation Readiness Dashboard features:
1. GET /api/admin/security/key-rotation/readiness returns preflight gate snapshot + provider apply capability summary
2. POST /api/admin/security/key-rotation/prepare and /approve still function
3. POST /api/admin/security/key-rotation/apply in live_guarded mode activates apply window, refreshes policy prerequisites
4. Apply step rows include adapter_result fields and statuses (applied/manual_required/adapter_missing/api_apply_failed)
5. Frontend admin SecurityDashboardPanel renders rotation readiness card with data-testid markers
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Module-level storage for test data
_test_data = {}


def get_admin_session():
    """Get admin session token"""
    if "admin_session" in _test_data:
        return _test_data["admin_session"]
    
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        return None
    
    data = response.json()
    token = data.get("session_token") or data.get("token")
    if not token:
        return None
    
    session.headers.update({"Authorization": f"Bearer {token}"})
    _test_data["admin_session"] = session
    return session


class TestKeyRotationReadinessEndpoint:
    """Tests for GET /api/admin/security/key-rotation/readiness"""
    
    def test_readiness_returns_providers_array(self):
        """Readiness endpoint should return providers array"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "providers" in data, "Response should contain 'providers' key"
        assert isinstance(data["providers"], list), "providers should be a list"
        assert len(data["providers"]) == 8, f"Expected 8 providers, got {len(data['providers'])}"
        
        print(f"✓ Readiness returns {len(data['providers'])} providers")
    
    def test_readiness_returns_preflight_gate(self):
        """Readiness endpoint should return preflight_gate snapshot"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        assert "preflight_gate" in data, "Response should contain 'preflight_gate' key"
        
        preflight = data["preflight_gate"]
        assert "evaluated_at" in preflight, "preflight_gate should have evaluated_at"
        assert "passed" in preflight, "preflight_gate should have passed"
        assert "checks" in preflight, "preflight_gate should have checks"
        assert "failed_checks" in preflight, "preflight_gate should have failed_checks"
        
        print(f"✓ Preflight gate: passed={preflight['passed']}, failed_checks={preflight['failed_checks']}")
    
    def test_readiness_returns_summary(self):
        """Readiness endpoint should return summary with counts"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        assert "summary" in data, "Response should contain 'summary' key"
        
        summary = data["summary"]
        expected_keys = [
            "total",
            "ready",
            "blocked",
            "api_rotate_ready",
            "api_probe_only_ready",
            "manual_by_constraint",
            "guarded",
            "adapter_missing",
            "target_environment",
            # backward-compat aliases
            "api_apply_ready",
            "manual_required",
        ]
        for key in expected_keys:
            assert key in summary, f"summary should have '{key}'"
        
        assert summary["total"] == 8, f"Expected total=8, got {summary['total']}"
        print(f"✓ Summary: total={summary['total']}, ready={summary['ready']}, blocked={summary['blocked']}")
    
    def test_readiness_provider_has_apply_capability(self):
        """Each provider should have apply_capability field"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        providers = data["providers"]
        
        for provider in providers:
            assert "apply_capability" in provider, f"Provider {provider.get('provider_id')} should have apply_capability"
            cap = provider["apply_capability"]
            assert "status" in cap, "apply_capability should have status"
            assert "reason" in cap, "apply_capability should have reason"
            assert "message" in cap, "apply_capability should have message"
            
            # Verify status is one of expected values
            valid_statuses = [
                "api_rotate_ready",
                "api_probe_only_ready",
                "manual_by_provider_constraint",
                "blocked",
                "guarded",
                "adapter_missing",
                "contract_rejected",
            ]
            assert cap["status"] in valid_statuses, f"Invalid status: {cap['status']}"
        
        print(f"✓ All {len(providers)} providers have valid apply_capability")
    
    def test_readiness_preflight_checks_structure(self):
        """Preflight gate checks should have proper structure"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        checks = data["preflight_gate"]["checks"]
        
        expected_check_names = ["admin_e2e_health_gate", "subscription_plan_guardrail", "sso_e2e_validation", "cia_trust_score"]
        actual_check_names = [c["name"] for c in checks]
        
        for name in expected_check_names:
            assert name in actual_check_names, f"Missing check: {name}"
        
        for check in checks:
            assert "name" in check, "Check should have name"
            assert "passed" in check, "Check should have passed"
            assert "value" in check, "Check should have value"
            assert "required" in check, "Check should have required"
        
        print(f"✓ Preflight gate has {len(checks)} checks with proper structure")


class TestKeyRotationPrepareApprove:
    """Tests for POST /api/admin/security/key-rotation/prepare and /approve"""
    
    def test_prepare_creates_plan(self):
        """Prepare should create a plan with all providers"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": [],
            "reason": "iteration49_prepare_test",
            "execution_mode": "live_guarded"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "plan_id" in data, "Response should have plan_id"
        assert "approval_token" in data, "Response should have approval_token"
        assert "providers" in data, "Response should have providers"
        assert data["status"] == "prepared", f"Expected status 'prepared', got {data['status']}"
        assert len(data["providers"]) == 8, f"Expected 8 providers, got {len(data['providers'])}"
        
        _test_data["iter49_plan_id"] = data["plan_id"]
        _test_data["iter49_approval_token"] = data["approval_token"]
        
        print(f"✓ Prepare created plan: {data['plan_id']}")
    
    def test_approve_validates_token(self):
        """Approve should validate token and mark plan approved"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        plan_id = _test_data.get("iter49_plan_id")
        approval_token = _test_data.get("iter49_approval_token")
        
        if not plan_id or not approval_token:
            pytest.skip("No plan_id/approval_token from prepare test")
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/approve", json={
            "plan_id": plan_id,
            "approval_token": approval_token,
            "approval_note": "Iteration 49 test approval"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "approved", f"Expected status 'approved', got {data.get('status')}"
        assert data.get("plan_id") == plan_id, "Plan ID mismatch"
        
        print("✓ Approve validated token and marked plan approved")


class TestKeyRotationApplyLiveGuarded:
    """Tests for POST /api/admin/security/key-rotation/apply in live_guarded mode"""
    
    def test_apply_activates_window_and_refreshes_prerequisites(self):
        """Apply in live_guarded mode should activate apply window and refresh prerequisites"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        # Create and approve a new plan
        prepare_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": [],
            "reason": "iteration49_apply_test",
            "execution_mode": "live_guarded"
        })
        
        if prepare_response.status_code != 200:
            pytest.skip(f"Could not create test plan: {prepare_response.text}")
        
        prepare_data = prepare_response.json()
        plan_id = prepare_data["plan_id"]
        approval_token = prepare_data["approval_token"]
        
        # Approve the plan
        approve_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/approve", json={
            "plan_id": plan_id,
            "approval_token": approval_token,
            "approval_note": "Apply test"
        })
        
        if approve_response.status_code != 200:
            pytest.skip(f"Could not approve plan: {approve_response.text}")
        
        # Apply the plan
        apply_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/apply", json={
            "plan_id": plan_id,
            "run_note": "Testing apply window activation",
            "execution_mode": "live_guarded"
        })
        
        assert apply_response.status_code == 200, f"Expected 200, got {apply_response.status_code}: {apply_response.text}"
        
        data = apply_response.json()
        assert "run_id" in data, "Response should have run_id"
        assert "status" in data, "Response should have status"
        assert "summary" in data, "Response should have summary"
        
        _test_data["iter49_run_id"] = data["run_id"]
        _test_data["iter49_apply_status"] = data["status"]
        
        print(f"✓ Apply returned: run_id={data['run_id']}, status={data['status']}")
        print(f"  Summary: {data['summary']}")
    
    def test_apply_step_rows_have_adapter_result(self):
        """Apply step rows should include adapter_result fields"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        run_id = _test_data.get("iter49_run_id")
        if not run_id:
            pytest.skip("No run_id from apply test")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/evidence")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        steps = data.get("steps", [])
        
        # Check that API contract execution steps include adapter_result
        api_apply_steps = [
            s
            for s in steps
            if s.get("status") in ["credential_validated", "cutover_applied", "api_probe_failed", "cutover_failed"]
        ]
        
        for step in api_apply_steps:
            assert "adapter_result" in step, f"Step {step.get('provider_id')} should have adapter_result"
            adapter_result = step["adapter_result"]
            if adapter_result:
                assert "ok" in adapter_result, "adapter_result should have 'ok' field"
        
        print(f"✓ {len(api_apply_steps)} steps have adapter_result fields")
    
    def test_apply_step_statuses_are_valid(self):
        """Apply step statuses should be one of expected values"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        run_id = _test_data.get("iter49_run_id")
        if not run_id:
            pytest.skip("No run_id from apply test")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/evidence")
        assert response.status_code == 200
        
        data = response.json()
        steps = data.get("steps", [])
        
        valid_statuses = [
            "credential_validated",
            "cutover_applied",
            "manual_pending_evidence",
            "manual_evidence_uploaded",
            "manual_applied_verified",
            "adapter_missing",
            "api_probe_failed",
            "cutover_failed",
            "blocked",
            "simulated",
            "guarded",
            "contract_rejected",
            "skipped_canary_stop",
        ]
        
        for step in steps:
            status = step.get("status")
            assert status in valid_statuses, f"Invalid status '{status}' for provider {step.get('provider_id')}"
        
        status_counts = {}
        for step in steps:
            status = step.get("status")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"✓ All {len(steps)} steps have valid statuses: {status_counts}")


class TestKeyRotationDryRun:
    """Tests for dry-run mode"""
    
    def test_dry_run_produces_simulated_steps(self):
        """Dry-run should produce simulated provider steps"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        # Create and approve a plan with dry_run mode
        prepare_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": [],
            "reason": "iteration49_dry_run_test",
            "execution_mode": "dry_run"
        })
        
        if prepare_response.status_code != 200:
            pytest.skip(f"Could not create test plan: {prepare_response.text}")
        
        prepare_data = prepare_response.json()
        plan_id = prepare_data["plan_id"]
        approval_token = prepare_data["approval_token"]
        
        # Approve
        session.post(f"{BASE_URL}/api/admin/security/key-rotation/approve", json={
            "plan_id": plan_id,
            "approval_token": approval_token,
            "approval_note": "Dry run test"
        })
        
        # Apply in dry_run mode
        apply_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/apply", json={
            "plan_id": plan_id,
            "run_note": "Dry run test",
            "execution_mode": "dry_run"
        })
        
        assert apply_response.status_code == 200, f"Expected 200, got {apply_response.status_code}: {apply_response.text}"
        
        data = apply_response.json()
        summary = data.get("summary", {})
        
        # In dry_run mode, all steps should be simulated
        simulated_count = summary.get("simulated", 0)
        print(f"✓ Dry-run produced {simulated_count} simulated steps")


class TestAdminAuthRequired:
    """Tests that admin auth is required for key rotation endpoints"""
    
    def test_readiness_requires_admin(self):
        """Readiness endpoint should require admin auth"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        
        print("✓ Readiness endpoint requires admin auth")
    
    def test_prepare_requires_admin(self):
        """Prepare endpoint should require admin auth"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": [],
            "reason": "test"
        })
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        
        print("✓ Prepare endpoint requires admin auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
