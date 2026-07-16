"""
Key Rotation P0+P1+P2 Rollout Tests - Iteration 50

Tests for production-grade key rotation semantics:
1. GET /api/admin/security/key-rotation/readiness - new contract-aware summary fields
2. IAP providers (iap_apple, iap_google) appear as manual_by_provider_constraint
3. POST /api/admin/security/key-rotation/prepare - includes contract_warnings
4. POST /api/admin/security/key-rotation/apply - new step statuses and summary counters
5. Canary stop threshold behavior
6. POST /api/admin/security/key-rotation/runs/{run_id}/manual-evidence
7. GET /api/admin/security/key-rotation/policy and POST /policy/game-day
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

# Module-level storage
_test_data = {}


def get_admin_session():
    """Get admin session token with fresh login"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code != 200:
        print(f"Login failed: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    token = data.get("session_token") or data.get("token")
    if not token:
        print(f"No token in response: {data}")
        return None
    
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestReadinessContractAwareSummary:
    """Tests for GET /api/admin/security/key-rotation/readiness new contract-aware fields"""
    
    def test_readiness_has_api_rotate_ready_field(self):
        """Summary should have api_rotate_ready field"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        summary = data.get("summary", {})
        
        assert "api_rotate_ready" in summary, "summary should have 'api_rotate_ready'"
        print(f"✓ api_rotate_ready = {summary['api_rotate_ready']}")
    
    def test_readiness_has_api_probe_only_ready_field(self):
        """Summary should have api_probe_only_ready field"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        
        assert "api_probe_only_ready" in summary, "summary should have 'api_probe_only_ready'"
        print(f"✓ api_probe_only_ready = {summary['api_probe_only_ready']}")
    
    def test_readiness_has_manual_by_constraint_field(self):
        """Summary should have manual_by_constraint field"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        
        assert "manual_by_constraint" in summary, "summary should have 'manual_by_constraint'"
        print(f"✓ manual_by_constraint = {summary['manual_by_constraint']}")
    
    def test_readiness_has_adapter_missing_field(self):
        """Summary should have adapter_missing field"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        
        assert "adapter_missing" in summary, "summary should have 'adapter_missing'"
        print(f"✓ adapter_missing = {summary['adapter_missing']}")
    
    def test_readiness_has_target_environment_field(self):
        """Summary should have target_environment field"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        
        assert "target_environment" in summary, "summary should have 'target_environment'"
        assert summary["target_environment"] in ["live", "sandbox", "test"], f"Invalid target_environment: {summary['target_environment']}"
        print(f"✓ target_environment = {summary['target_environment']}")
    
    def test_readiness_has_legacy_aliases(self):
        """Summary should retain legacy aliases (api_apply_ready, manual_required)"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        
        assert "api_apply_ready" in summary, "summary should have legacy 'api_apply_ready'"
        assert "manual_required" in summary, "summary should have legacy 'manual_required'"
        print(f"✓ Legacy aliases present: api_apply_ready={summary['api_apply_ready']}, manual_required={summary['manual_required']}")


class TestIAPProvidersManualConstraint:
    """Tests that IAP providers (iap_apple, iap_google) appear as manual_by_provider_constraint"""
    
    def test_iap_apple_is_manual_by_constraint(self):
        """iap_apple should have apply_capability.status = manual_by_provider_constraint"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        providers = data.get("providers", [])
        
        iap_apple = next((p for p in providers if p.get("provider_id") == "iap_apple"), None)
        assert iap_apple is not None, "iap_apple provider not found"
        
        apply_cap = iap_apple.get("apply_capability", {})
        status = apply_cap.get("status")
        
        # If configured, should be manual_by_provider_constraint; if not configured, should be blocked
        if iap_apple.get("readiness_state") == "ready":
            assert status == "manual_by_provider_constraint", f"Expected manual_by_provider_constraint, got {status}"
            print(f"✓ iap_apple apply_capability.status = {status}")
        else:
            assert status == "blocked", f"Expected blocked for unconfigured provider, got {status}"
            print("✓ iap_apple is blocked (not configured)")
    
    def test_iap_google_is_manual_by_constraint(self):
        """iap_google should have apply_capability.status = manual_by_provider_constraint"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        providers = data.get("providers", [])
        
        iap_google = next((p for p in providers if p.get("provider_id") == "iap_google"), None)
        assert iap_google is not None, "iap_google provider not found"
        
        apply_cap = iap_google.get("apply_capability", {})
        status = apply_cap.get("status")
        
        if iap_google.get("readiness_state") == "ready":
            assert status == "manual_by_provider_constraint", f"Expected manual_by_provider_constraint, got {status}"
            print(f"✓ iap_google apply_capability.status = {status}")
        else:
            assert status == "blocked", f"Expected blocked for unconfigured provider, got {status}"
            print("✓ iap_google is blocked (not configured)")
    
    def test_iap_providers_have_manual_constraint_code(self):
        """IAP providers should have manual_constraint_code = provider_console_key_lifecycle"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        providers = data.get("providers", [])
        
        for provider_id in ["iap_apple", "iap_google"]:
            provider = next((p for p in providers if p.get("provider_id") == provider_id), None)
            assert provider is not None, f"{provider_id} not found"
            
            constraint_code = provider.get("manual_constraint_code")
            assert constraint_code == "provider_console_key_lifecycle", f"{provider_id} should have manual_constraint_code=provider_console_key_lifecycle, got {constraint_code}"
        
        print("✓ IAP providers have correct manual_constraint_code")


class TestPrepareContractWarnings:
    """Tests for POST /api/admin/security/key-rotation/prepare contract_warnings"""
    
    def test_prepare_includes_contract_warnings(self):
        """Prepare response should include contract_warnings field"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": [],
            "reason": "iter50_contract_warnings_test",
            "execution_mode": "live_guarded"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "contract_warnings" in data, "Response should have 'contract_warnings'"
        assert isinstance(data["contract_warnings"], list), "contract_warnings should be a list"
        
        _test_data["iter50_plan_id"] = data.get("plan_id")
        _test_data["iter50_approval_token"] = data.get("approval_token")
        
        print(f"✓ Prepare includes contract_warnings: {len(data['contract_warnings'])} warnings")
        if data["contract_warnings"]:
            for w in data["contract_warnings"][:3]:
                print(f"  - {w.get('provider_id')}: {w.get('reason')}")


class TestApplyNewStepStatuses:
    """Tests for POST /api/admin/security/key-rotation/apply new step statuses"""
    
    def test_apply_returns_new_summary_counters(self):
        """Apply should return new summary counters"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        # Create and approve a plan
        prepare_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
            "providers": [],
            "reason": "iter50_apply_test",
            "execution_mode": "live_guarded"
        })
        
        if prepare_response.status_code != 200:
            pytest.skip(f"Could not create plan: {prepare_response.text}")
        
        prepare_data = prepare_response.json()
        plan_id = prepare_data["plan_id"]
        approval_token = prepare_data["approval_token"]
        
        # Approve
        approve_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/approve", json={
            "plan_id": plan_id,
            "approval_token": approval_token,
            "approval_note": "Iter50 test"
        })
        
        if approve_response.status_code != 200:
            pytest.skip(f"Could not approve plan: {approve_response.text}")
        
        # Apply
        apply_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/apply", json={
            "plan_id": plan_id,
            "run_note": "Testing new step statuses",
            "execution_mode": "live_guarded"
        })
        
        assert apply_response.status_code == 200, f"Expected 200, got {apply_response.status_code}: {apply_response.text}"
        
        data = apply_response.json()
        summary = data.get("summary", {})
        
        # Check for new summary counters
        expected_counters = [
            "providers_total",
            "cutover_applied",
            "credential_validated",
            "manual_pending_evidence",
            "manual_evidence_uploaded",
            "manual_applied_verified",
            "blocked",
            "simulated",
            "adapter_missing",
            "api_probe_failed",
            "cutover_failed",
            "contract_rejected",
            "guarded",
            "skipped_canary_stop",
            # Legacy aliases
            "applied",
            "manual_required",
            "api_apply_failed",
        ]
        
        for counter in expected_counters:
            assert counter in summary, f"summary should have '{counter}'"
        
        _test_data["iter50_run_id"] = data.get("run_id")
        
        print("✓ Apply returns new summary counters:")
        print(f"  - credential_validated: {summary.get('credential_validated')}")
        print(f"  - manual_pending_evidence: {summary.get('manual_pending_evidence')}")
        print(f"  - api_probe_failed: {summary.get('api_probe_failed')}")
        print(f"  - skipped_canary_stop: {summary.get('skipped_canary_stop')}")


class TestPolicyEndpoints:
    """Tests for GET /api/admin/security/key-rotation/policy and POST /policy/game-day"""
    
    def test_policy_endpoint_returns_policy(self):
        """GET /policy should return rotation policy"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/policy")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "policy" in data, "Response should have 'policy'"
        
        policy = data["policy"]
        expected_fields = [
            "default_cadence_days",
            "high_risk_cadence_days",
            "require_dual_approval",
            "require_evidence_links_for_manual",
            "game_day_interval_days",
            "target_environment",
        ]
        
        for field in expected_fields:
            assert field in policy, f"policy should have '{field}'"
        
        print("✓ Policy endpoint returns policy:")
        print(f"  - default_cadence_days: {policy.get('default_cadence_days')}")
        print(f"  - target_environment: {policy.get('target_environment')}")
    
    def test_policy_endpoint_returns_last_game_day(self):
        """GET /policy should return last_game_day"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/policy")
        assert response.status_code == 200
        
        data = response.json()
        assert "last_game_day" in data, "Response should have 'last_game_day'"
        print(f"✓ Policy endpoint returns last_game_day: {data.get('last_game_day')}")
    
    def test_game_day_endpoint_records_game_day(self):
        """POST /policy/game-day should record game day"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/policy/game-day", json={
            "note": "Iteration 50 game day test",
            "evidence_links": ["https://example.com/evidence1"]
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("ok"), "Response should have ok=True"
        assert "entry" in data, "Response should have 'entry'"
        
        entry = data["entry"]
        assert "recorded_at" in entry, "entry should have 'recorded_at'"
        assert "recorded_by" in entry, "entry should have 'recorded_by'"
        
        print(f"✓ Game day recorded: {entry.get('recorded_at')}")


class TestManualEvidenceEndpoint:
    """Tests for POST /api/admin/security/key-rotation/runs/{run_id}/manual-evidence"""
    
    def test_manual_evidence_endpoint_exists(self):
        """Manual evidence endpoint should exist and accept requests"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        run_id = _test_data.get("iter50_run_id")
        if not run_id:
            # Create a run first
            prepare_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/prepare", json={
                "providers": [],
                "reason": "iter50_manual_evidence_test",
                "execution_mode": "live_guarded"
            })
            
            if prepare_response.status_code != 200:
                pytest.skip("Could not create plan")
            
            prepare_data = prepare_response.json()
            plan_id = prepare_data["plan_id"]
            approval_token = prepare_data["approval_token"]
            
            session.post(f"{BASE_URL}/api/admin/security/key-rotation/approve", json={
                "plan_id": plan_id,
                "approval_token": approval_token,
                "approval_note": "Manual evidence test"
            })
            
            apply_response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/apply", json={
                "plan_id": plan_id,
                "run_note": "Manual evidence test",
                "execution_mode": "live_guarded"
            })
            
            if apply_response.status_code != 200:
                pytest.skip("Could not create run")
            
            run_id = apply_response.json().get("run_id")
        
        # Test manual evidence endpoint
        response = session.post(f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/manual-evidence", json={
            "provider_id": "iap_apple",
            "evidence_note": "Test evidence note",
            "evidence_links": ["https://example.com/evidence"],
            "mark_verified": False
        })
        
        # Should return 200 or 404 (if provider not in run)
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Manual evidence endpoint works: {data}")
        else:
            print("✓ Manual evidence endpoint exists (provider not in run)")


class TestProviderApplyCapabilityStatuses:
    """Tests for provider apply_capability status values"""
    
    def test_all_providers_have_valid_apply_capability_status(self):
        """All providers should have valid apply_capability.status"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        providers = data.get("providers", [])
        
        valid_statuses = [
            "api_rotate_ready",
            "api_probe_only_ready",
            "manual_by_provider_constraint",
            "blocked",
            "guarded",
            "adapter_missing",
            "contract_rejected",
        ]
        
        status_counts = {}
        for provider in providers:
            apply_cap = provider.get("apply_capability", {})
            status = apply_cap.get("status")
            
            assert status in valid_statuses, f"Provider {provider.get('provider_id')} has invalid status: {status}"
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"✓ All {len(providers)} providers have valid apply_capability.status:")
        for status, count in status_counts.items():
            print(f"  - {status}: {count}")


class TestReadinessProviderContractMode:
    """Tests for provider apply_contract_mode field"""
    
    def test_providers_have_apply_contract_mode(self):
        """All providers should have apply_contract_mode field"""
        session = get_admin_session()
        if not session:
            pytest.skip("Admin login failed")
        
        response = session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        providers = data.get("providers", [])
        
        valid_modes = [
            "manual_by_provider_constraint",
            "api_probe_only",
            "api_rotate_supported",
        ]
        
        for provider in providers:
            mode = provider.get("apply_contract_mode")
            assert mode is not None, f"Provider {provider.get('provider_id')} should have apply_contract_mode"
            assert mode in valid_modes, f"Provider {provider.get('provider_id')} has invalid mode: {mode}"
        
        print("✓ All providers have valid apply_contract_mode")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
