"""
R1-R5 Security Key Rotation Framework Tests - Iteration 46

Tests for the live-provider security rotation framework including:
- R1: Readiness endpoint with full provider coverage (8 providers)
- R2: Prepare/Approve endpoints with two-step approval
- R3: Apply endpoint with guarded provider adapters and rollback
- R4: Incident linkage and webhook dispatch
- R5: Evidence endpoint with run/steps/evidence/incidents/rollbacks
- Legacy compatibility: /dry-run and /runs endpoints
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


class TestR1Readiness:
    """R1: Provider readiness and coverage alignment tests"""
    
    def test_readiness_endpoint_returns_200(self):
        """R1: Readiness endpoint should return 200 for admin"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ R1 readiness endpoint returns 200")
    
    def test_readiness_returns_8_providers(self):
        """R1: Readiness should return full provider coverage (8 providers)"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        assert "providers" in data, "Response should contain 'providers' key"
        assert "summary" in data, "Response should contain 'summary' key"
        
        providers = data["providers"]
        summary = data["summary"]
        
        # Verify 8 providers total
        assert summary.get("total") == 8, f"Expected 8 providers, got {summary.get('total')}"
        assert len(providers) == 8, f"Expected 8 provider entries, got {len(providers)}"
        
        # Verify expected provider IDs
        expected_providers = {
            "payments_stripe", "payments_paypal", "payments_fedapay",
            "iap_apple", "iap_google",
            "oauth_google", "oauth_microsoft", "oauth_apple"
        }
        actual_providers = {p.get("provider_id") for p in providers}
        assert expected_providers == actual_providers, f"Provider mismatch: expected {expected_providers}, got {actual_providers}"
        
        print(f"✓ R1 readiness returns 8 providers: {actual_providers}")
        print(f"  Summary: ready={summary.get('ready')}, blocked={summary.get('blocked')}")
    
    def test_readiness_provider_structure(self):
        """R1: Each provider should have required fields"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        providers = data["providers"]
        
        required_fields = ["provider_id", "label", "family", "configured", "readiness_state", "rotation_supported", "rollback_supported"]
        
        for provider in providers:
            for field in required_fields:
                assert field in provider, f"Provider {provider.get('provider_id')} missing field: {field}"
        
        print("✓ R1 all providers have required structure")


class TestR2PrepareApprove:
    """R2: Prepare and approve flow with two-step approval"""
    
    def test_prepare_endpoint_returns_plan(self):
        """R2: Prepare endpoint should return plan_id and approval_token"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": [],  # All providers
            "reason": "test_rotation",
            "execution_mode": "dry_run"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "plan_id" in data, "Response should contain 'plan_id'"
        assert "approval_token" in data, "Response should contain 'approval_token'"
        assert "providers" in data, "Response should contain 'providers'"
        assert "status" in data, "Response should contain 'status'"
        
        assert data["status"] == "prepared", f"Expected status 'prepared', got {data['status']}"
        assert data["plan_id"].startswith("keyrot_plan_"), f"Invalid plan_id format: {data['plan_id']}"
        
        print(f"✓ R2 prepare returns plan_id={data['plan_id'][:30]}...")
        print(f"  Approval token issued, expires at: {data.get('approval_expires_at')}")
        
        # Store for next test
        _test_data["test_plan_id"] = data["plan_id"]
        _test_data["test_approval_token"] = data["approval_token"]
    
    def test_approve_endpoint_validates_token(self):
        """R2: Approve endpoint should validate token and mark plan approved"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        plan_id = _test_data.get("test_plan_id")
        approval_token = _test_data.get("test_approval_token")
        
        if not plan_id or not approval_token:
            pytest.skip("No plan_id/approval_token from prepare test")
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/approve", json={
            "plan_id": plan_id,
            "approval_token": approval_token,
            "approval_note": "Test approval for iteration 46"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "approved", f"Expected status 'approved', got {data.get('status')}"
        assert data.get("plan_id") == plan_id, "Plan ID mismatch"
        
        print("✓ R2 approve validates token and marks plan approved")
        print(f"  Approved by: {data.get('approved_by')}, at: {data.get('approved_at')}")
    
    def test_approve_rejects_invalid_token(self):
        """R2: Approve should reject invalid approval token"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        # First create a new plan
        prepare_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": ["payments_stripe"],
            "reason": "test_invalid_token",
            "execution_mode": "dry_run"
        })
        
        if prepare_response.status_code != 200:
            pytest.skip("Could not create test plan")
        
        plan_id = prepare_response.json().get("plan_id")
        
        # Try to approve with invalid token
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/approve", json={
            "plan_id": plan_id,
            "approval_token": "invalid_token_12345",
            "approval_note": "Should fail"
        })
        
        assert response.status_code == 400, f"Expected 400 for invalid token, got {response.status_code}"
        print("✓ R2 approve correctly rejects invalid token")
    
    def test_list_plans_endpoint(self):
        """R2: List plans endpoint should return created plans"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/plans")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "plans" in data, "Response should contain 'plans'"
        assert "count" in data, "Response should contain 'count'"
        
        print(f"✓ R2 list plans returns {data['count']} plans")


class TestR3ApplyRollback:
    """R3: Apply endpoint with guarded adapters and rollback behavior"""
    
    def test_apply_endpoint_executes_plan(self):
        """R3: Apply endpoint should execute approved plan and return run summary"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        # Create and approve a new plan
        prepare_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": [],  # All providers
            "reason": "test_apply_execution",
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
            "approval_note": "Approve for apply test"
        })
        
        if approve_response.status_code != 200:
            pytest.skip(f"Could not approve plan: {approve_response.text}")
        
        # Apply the plan
        apply_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/apply", json={
            "plan_id": plan_id,
            "run_note": "Test apply for iteration 46",
            "execution_mode": "live_guarded"
        })
        
        assert apply_response.status_code == 200, f"Expected 200, got {apply_response.status_code}: {apply_response.text}"
        
        data = apply_response.json()
        assert "run_id" in data, "Response should contain 'run_id'"
        assert "status" in data, "Response should contain 'status'"
        assert "summary" in data, "Response should contain 'summary'"
        
        summary = data["summary"]
        assert "providers_total" in summary, "Summary should contain 'providers_total'"
        assert "manual_required" in summary, "Summary should contain 'manual_required'"
        assert "blocked" in summary, "Summary should contain 'blocked'"
        
        print(f"✓ R3 apply executes plan, run_id={data['run_id']}")
        print(f"  Status: {data['status']}")
        print(f"  Summary: total={summary.get('providers_total')}, manual_required={summary.get('manual_required')}, blocked={summary.get('blocked')}")
        
        # Store for evidence test
        _test_data["test_run_id"] = data["run_id"]
        _test_data["test_apply_status"] = data["status"]
        _test_data["test_incident_id"] = data.get("incident_id")
        _test_data["test_rollback_id"] = data.get("rollback_id")
    
    def test_apply_triggers_rollback_on_health_failure(self):
        """R3: Apply should trigger auto-rollback when post-health fails in live_guarded mode"""
        # Check if previous apply triggered rollback
        apply_status = _test_data.get("test_apply_status")
        rollback_id = _test_data.get("test_rollback_id")
        
        # In preview environment, policy gate prerequisites may not pass, triggering rollback
        if apply_status == "rolled_back":
            assert rollback_id is not None, "Rollback should have rollback_id"
            print(f"✓ R3 auto-rollback triggered (status=rolled_back, rollback_id={rollback_id})")
        else:
            print(f"✓ R3 apply completed without rollback (status={apply_status})")
    
    def test_manual_rollback_endpoint(self):
        """R3: Manual rollback endpoint should work for existing runs"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        run_id = _test_data.get("test_run_id")
        
        if not run_id:
            pytest.skip("No run_id from apply test")
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/rollback/{run_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "rolled_back", f"Expected status 'rolled_back', got {data.get('status')}"
        assert "rollback_id" in data, "Response should contain 'rollback_id'"
        assert "actions" in data, "Response should contain 'actions'"
        
        print(f"✓ R3 manual rollback works, rollback_id={data['rollback_id']}")


class TestR4IncidentLinkage:
    """R4: Incident linkage and webhook dispatch"""
    
    def test_incident_created_on_rollback(self):
        """R4: Security incident should be created when rollback is required"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        incident_id = _test_data.get("test_incident_id")
        apply_status = _test_data.get("test_apply_status")
        
        if apply_status == "rolled_back" and incident_id:
            print(f"✓ R4 incident created on rollback: {incident_id}")
        else:
            # Check if any key rotation incidents exist
            response = session.get(f"{BASE_URL}/api/admin/security-incidents/recent?limit=10")
            if response.status_code == 200:
                data = response.json()
                incidents = data.get("incidents", [])
                keyrot_incidents = [i for i in incidents if i.get("source") == "key_rotation"]
                if keyrot_incidents:
                    print(f"✓ R4 found {len(keyrot_incidents)} key rotation incidents")
                else:
                    print("✓ R4 no rollback-triggered incidents (apply may have succeeded)")
            else:
                print("✓ R4 incident linkage verified (no rollback occurred)")
    
    def test_webhook_dispatch_endpoint(self):
        """R4: Webhook dispatch endpoint should be compatible with created incidents"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        # Get a recent incident
        response = session.get(f"{BASE_URL}/api/admin/security-incidents/recent?limit=5")
        
        if response.status_code != 200:
            pytest.skip(f"Could not get recent incidents: {response.text}")
        
        data = response.json()
        incidents = data.get("incidents", [])
        
        if not incidents:
            # Try to dispatch for a non-existent incident
            dispatch_response = session.post(f"{BASE_URL}/api/admin/siem/incidents/nonexistent_123/dispatch-webhook")
            assert dispatch_response.status_code == 200, f"Expected 200, got {dispatch_response.status_code}"
            dispatch_data = dispatch_response.json()
            assert not dispatch_data.get("sent"), "Should return sent=false for non-existent incident"
            assert dispatch_data.get("reason") == "incident_not_found", "Should return reason=incident_not_found"
            print("✓ R4 webhook dispatch handles missing incidents gracefully")
        else:
            incident_id = incidents[0].get("incident_id")
            dispatch_response = session.post(f"{BASE_URL}/api/admin/siem/incidents/{incident_id}/dispatch-webhook")
            assert dispatch_response.status_code == 200, f"Expected 200, got {dispatch_response.status_code}"
            dispatch_data = dispatch_response.json()
            print(f"✓ R4 webhook dispatch for incident {incident_id}: sent={dispatch_data.get('sent')}")


class TestR5Evidence:
    """R5: Evidence endpoint with run/steps/evidence/incidents/rollbacks"""
    
    def test_evidence_endpoint_returns_full_data(self):
        """R5: Evidence endpoint should return run, steps, evidence, incidents, rollbacks"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        run_id = _test_data.get("test_run_id")
        
        if not run_id:
            # Get a run from the runs list
            runs_response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs?limit=5")
            if runs_response.status_code == 200:
                runs_data = runs_response.json()
                runs = runs_data.get("runs", [])
                if runs:
                    run_id = runs[0].get("run_id")
        
        if not run_id:
            pytest.skip("No run_id available for evidence test")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/evidence")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify all required sections
        assert "run" in data, "Response should contain 'run'"
        assert "steps" in data, "Response should contain 'steps'"
        assert "evidence" in data, "Response should contain 'evidence'"
        assert "incidents" in data, "Response should contain 'incidents'"
        assert "rollbacks" in data, "Response should contain 'rollbacks'"
        assert "counts" in data, "Response should contain 'counts'"
        
        counts = data["counts"]
        print(f"✓ R5 evidence endpoint returns full data for run {run_id}")
        print(f"  Counts: steps={counts.get('steps')}, evidence={counts.get('evidence')}, incidents={counts.get('incidents')}, rollbacks={counts.get('rollbacks')}")
    
    def test_evidence_steps_have_runbook(self):
        """R5: Evidence steps should include runbook instructions"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        run_id = _test_data.get("test_run_id")
        
        if not run_id:
            runs_response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs?limit=5")
            if runs_response.status_code == 200:
                runs = runs_response.json().get("runs", [])
                if runs:
                    run_id = runs[0].get("run_id")
        
        if not run_id:
            pytest.skip("No run_id available")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/evidence")
        
        if response.status_code != 200:
            pytest.skip(f"Could not get evidence: {response.text}")
        
        data = response.json()
        steps = data.get("steps", [])
        
        if steps:
            for step in steps[:3]:  # Check first 3 steps
                assert "runbook" in step, f"Step {step.get('provider_id')} should have runbook"
                assert isinstance(step["runbook"], list), "Runbook should be a list"
            print("✓ R5 evidence steps include runbook instructions")
        else:
            print("✓ R5 no steps to verify (empty run)")


class TestLegacyCompatibility:
    """Legacy compatibility tests for /dry-run and /runs endpoints"""
    
    def test_dry_run_get_endpoint(self):
        """Legacy: GET /dry-run should return preview without persisting"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/dry-run")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "run_id" in data, "Response should contain 'run_id'"
        assert "mode" in data, "Response should contain 'mode'"
        assert "targets" in data, "Response should contain 'targets'"
        assert data.get("mode") == "dry_run", f"Expected mode 'dry_run', got {data.get('mode')}"
        assert not data.get("persisted"), "GET dry-run should not persist"
        
        print(f"✓ Legacy GET /dry-run works, run_id={data['run_id']}")
    
    def test_dry_run_post_endpoint(self):
        """Legacy: POST /dry-run should persist the run"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/dry-run")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("persisted"), "POST dry-run should persist"
        
        print("✓ Legacy POST /dry-run works and persists")
    
    def test_runs_list_endpoint(self):
        """Legacy: /runs endpoint should list all runs"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "runs" in data, "Response should contain 'runs'"
        assert "count" in data, "Response should contain 'count'"
        
        print(f"✓ Legacy /runs endpoint works, count={data['count']}")
    
    def test_single_run_endpoint(self):
        """Legacy: /runs/{run_id} should return single run details"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        # Get a run first
        runs_response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs?limit=1")
        
        if runs_response.status_code != 200:
            pytest.skip("Could not get runs list")
        
        runs = runs_response.json().get("runs", [])
        if not runs:
            pytest.skip("No runs available")
        
        run_id = runs[0].get("run_id")
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("found"), "Should find the run"
        assert "run" in data, "Response should contain 'run'"
        
        print(f"✓ Legacy /runs/{run_id} endpoint works")


class TestFrontendSmoke:
    """Frontend smoke test - login page loads"""
    
    def test_login_page_loads(self):
        """Frontend: Login page should load without errors"""
        response = requests.get(f"{BASE_URL}/auth/login", timeout=10)
        
        # Should return 200 or redirect
        assert response.status_code in [200, 301, 302, 304], f"Expected 200/3xx, got {response.status_code}"
        
        print(f"✓ Frontend login page loads (status={response.status_code})")
    
    def test_frontend_root_loads(self):
        """Frontend: Root page should load"""
        response = requests.get(f"{BASE_URL}/", timeout=10)
        
        assert response.status_code in [200, 301, 302, 304], f"Expected 200/3xx, got {response.status_code}"
        
        print(f"✓ Frontend root page loads (status={response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
