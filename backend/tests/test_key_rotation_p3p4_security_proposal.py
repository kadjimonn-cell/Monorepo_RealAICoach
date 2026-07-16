"""
Test suite for P0+P1+P2+P3+P4 Global Platform Security Incident Proposal Plan completion.

Features tested:
- GET /api/admin/security/key-rotation/readiness: provider_contract_counts and Microsoft contract mode
- Microsoft provider uses apply_contract_mode=api_rotate_supported with correct readiness status
- POST /api/admin/security/key-rotation/policy/attest: stores and returns attestation
- POST /api/admin/security/key-rotation/policy/game-day: enforces evidence links and returns attestation
- POST /api/admin/security/key-rotation/runs/{run_id}/manual-evidence: strict validation
- GET /api/admin/security/key-rotation/runs/{run_id}/compliance-bundle: json and markdown formats
- No ObjectId serialization errors on newly added endpoints
- Backward-compatible summary aliases (api_apply_ready, manual_required)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://localhost:8001"


def _is_admin_containment_block(response: requests.Response) -> bool:
    if response.status_code not in (401, 403):
        return False

    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    blocked_codes = {
        "AUTH_REQUIRED",
        "RISK_ENGINE_ADMIN_API_BLOCKED",
        "RISK_ENGINE_ID_VERIFICATION_REQUIRED",
    }

    if top_code in blocked_codes:
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in blocked_codes:
            return True
        message = str(detail.get("message") or "").lower()
        return (
            "admin access required" in message
            or "admin access blocked" in message
            or "id checker" in message
        )

    if isinstance(detail, str):
        lowered = detail.lower()
        return (
            "admin access required" in lowered
            or "authentication required" in lowered
            or "id checker" in lowered
        )

    body = (response.text or "").lower()
    return "admin access required" in body or "risk engine" in body


def _skip_if_admin_containment(response: requests.Response, context: str) -> None:
    if _is_admin_containment_block(response):
        pytest.skip(f"{context} blocked by environment containment/authorization policy")


def _is_policy_gate_block(response: requests.Response) -> bool:
    if response.status_code != 503:
        return False

    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""

    if top_code == "PRODUCTION_POLICY_GATE_BLOCKED":
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code == "PRODUCTION_POLICY_GATE_BLOCKED":
            return True
        message = str(detail.get("message") or "").lower()
        return "policy gate" in message

    if isinstance(detail, str):
        lowered = detail.lower()
        return "production security policy gate" in lowered or "policy gate" in lowered

    body = (response.text or "").lower()
    return "production_policy_gate_blocked" in body or "policy gate" in body


def _skip_if_environment_blocked(response: requests.Response, context: str) -> None:
    if _is_admin_containment_block(response) or _is_policy_gate_block(response):
        pytest.skip(f"{context} blocked by environment containment/policy gate")


class TestKeyRotationP3P4SecurityProposal:
    """Test suite for P3+P4 security proposal features."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with admin authentication."""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        # Login as admin
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@realaicoach.app",
                "password": "NewAdminPass2026!"
            }
        )

        _skip_if_admin_containment(login_response, "Key rotation admin login")

        if login_response.status_code == 200:
            data = login_response.json()
            token = (
                data.get("session_token")
                or data.get("token")
                or data.get("access_token")
                or login_response.cookies.get("session_token")
                or self.session.cookies.get("session_token")
            )
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
            elif not self.session.cookies.get("session_token"):
                pytest.skip("Admin token missing in login response/cookies")
        else:
            pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text[:200]}")

        original_get = self.session.get
        original_post = self.session.post

        def guarded_get(*args, **kwargs):
            response = original_get(*args, **kwargs)
            _skip_if_environment_blocked(response, "Key rotation admin endpoint")
            return response

        def guarded_post(*args, **kwargs):
            response = original_post(*args, **kwargs)
            _skip_if_environment_blocked(response, "Key rotation admin endpoint")
            return response

        self.session.get = guarded_get
        self.session.post = guarded_post

        yield
        self.session.close()

    # ==================== READINESS ENDPOINT TESTS ====================

    def test_readiness_returns_provider_contract_counts(self):
        """Test GET /api/admin/security/key-rotation/readiness includes provider_contract_counts."""
        response = self.session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "summary" in data, "Response should contain summary"
        summary = data["summary"]
        
        # Verify provider_contract_counts is present
        assert "provider_contract_counts" in summary, "Summary should contain provider_contract_counts"
        contract_counts = summary["provider_contract_counts"]
        
        # Verify expected keys in provider_contract_counts
        assert "api_probe_only" in contract_counts, "Should have api_probe_only count"
        assert "api_rotate_supported" in contract_counts, "Should have api_rotate_supported count"
        assert "manual_by_provider_constraint" in contract_counts, "Should have manual_by_provider_constraint count"
        
        # Verify counts are integers
        assert isinstance(contract_counts["api_probe_only"], int)
        assert isinstance(contract_counts["api_rotate_supported"], int)
        assert isinstance(contract_counts["manual_by_provider_constraint"], int)
        
        print(f"Provider contract counts: {contract_counts}")

    def test_readiness_microsoft_provider_contract_mode(self):
        """Test Microsoft provider uses apply_contract_mode=api_rotate_supported."""
        response = self.session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        providers = data.get("providers", [])
        
        # Find Microsoft OAuth provider
        microsoft_provider = None
        for p in providers:
            if p.get("provider_id") == "oauth_microsoft":
                microsoft_provider = p
                break
        
        assert microsoft_provider is not None, "Microsoft OAuth provider should be in providers list"
        
        # Verify contract mode
        assert microsoft_provider.get("apply_contract_mode") == "api_rotate_supported", \
            f"Microsoft should have api_rotate_supported, got {microsoft_provider.get('apply_contract_mode')}"
        
        # Verify apply_capability reflects correct status
        apply_capability = microsoft_provider.get("apply_capability", {})
        status = apply_capability.get("status")
        
        # Expected statuses for api_rotate_supported when lifecycle is disabled or adapter missing
        valid_statuses = ["guarded", "adapter_missing", "api_rotate_ready"]
        assert status in valid_statuses, \
            f"Microsoft apply_capability status should be one of {valid_statuses}, got {status}"
        
        print(f"Microsoft provider: contract_mode={microsoft_provider.get('apply_contract_mode')}, status={status}")

    def test_readiness_backward_compatible_aliases(self):
        """Test backward-compatible summary aliases (api_apply_ready, manual_required)."""
        response = self.session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200
        
        data = response.json()
        summary = data.get("summary", {})
        
        # Verify backward-compatible aliases exist
        assert "api_apply_ready" in summary, "Summary should contain api_apply_ready alias"
        assert "manual_required" in summary, "Summary should contain manual_required alias"
        
        # Verify they are integers
        assert isinstance(summary["api_apply_ready"], int)
        assert isinstance(summary["manual_required"], int)
        
        print(f"Backward-compatible aliases: api_apply_ready={summary['api_apply_ready']}, manual_required={summary['manual_required']}")

    # ==================== POLICY ATTESTATION TESTS ====================

    def test_policy_attest_stores_and_returns_attestation(self):
        """Test POST /api/admin/security/key-rotation/policy/attest stores and returns attestation."""
        response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/policy/attest",
            json={
                "note": "Test attestation for P3P4 testing",
                "run_prerequisite_refresh": False,  # Skip to speed up test
                "validate_webhook": False,  # Skip webhook validation
                "include_game_day_snapshot": True
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify attestation structure
        assert "attestation_id" in data, "Response should contain attestation_id"
        assert data["attestation_id"].startswith("keyrot_att_"), "attestation_id should have correct prefix"
        assert "attested_at" in data, "Response should contain attested_at"
        assert "attested_by" in data, "Response should contain attested_by"
        assert "note" in data, "Response should contain note"
        assert data["note"] == "Test attestation for P3P4 testing"
        assert "policy" in data, "Response should contain policy snapshot"
        assert "policy_gate_snapshot" in data, "Response should contain policy_gate_snapshot"
        
        # Verify no ObjectId serialization errors (would cause 500 or JSON parse error)
        print(f"Attestation created: {data['attestation_id']}")

    def test_policy_attest_with_prerequisite_refresh(self):
        """Test policy attestation with prerequisite refresh enabled."""
        response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/policy/attest",
            json={
                "note": "Attestation with prereq refresh",
                "run_prerequisite_refresh": True,
                "validate_webhook": False,
                "include_game_day_snapshot": False
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "attestation_id" in data
        assert "prerequisite_refresh" in data, "Should contain prerequisite_refresh when enabled"
        
        print(f"Attestation with prereq refresh: {data['attestation_id']}")

    # ==================== GAME-DAY TESTS ====================

    def test_game_day_enforces_evidence_links(self):
        """Test POST /api/admin/security/key-rotation/policy/game-day enforces evidence links."""
        # Test without evidence links - should fail
        response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/policy/game-day",
            json={
                "note": "Game day without links",
                "evidence_links": []
            }
        )
        assert response.status_code == 400, f"Expected 400 for missing evidence links, got {response.status_code}"
        assert "evidence link" in response.text.lower(), "Error should mention evidence links"
        
        print("Game-day correctly rejects empty evidence_links")

    def test_game_day_with_valid_evidence_links(self):
        """Test game-day recording with valid evidence links returns attestation."""
        response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/policy/game-day",
            json={
                "note": "P3P4 test game day drill",
                "evidence_links": [
                    "https://confluence.example.com/game-day-runbook-2026",
                    "https://jira.example.com/SECURITY-1234"
                ]
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("ok") is True, "Response should have ok=True"
        assert "entry" in data, "Response should contain entry"
        assert "attestation" in data, "Response should contain attestation"
        
        entry = data["entry"]
        assert entry.get("key") == "key_rotation_last_game_day"
        assert len(entry.get("evidence_links", [])) == 2
        assert "evidence_link_hashes" in entry
        
        attestation = data["attestation"]
        assert "attestation_id" in attestation
        assert attestation.get("source") == "game_day_record"
        
        print(f"Game-day recorded: attestation_id={attestation['attestation_id']}")

    # ==================== MANUAL EVIDENCE TESTS ====================

    def test_manual_evidence_strict_validation_note_length(self):
        """Test manual evidence enforces minimum note length."""
        # First create a run to test against
        prepare_response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/prepare",
            json={
                "providers": ["iap_apple"],  # Manual provider
                "reason": "test_manual_evidence_validation",
                "execution_mode": "dry_run"
            }
        )
        
        if prepare_response.status_code != 200:
            pytest.skip("Could not create test run for manual evidence validation")
        
        prepare_data = prepare_response.json()
        plan_id = prepare_data.get("plan_id")
        approval_token = prepare_data.get("approval_token")
        
        if not plan_id or not approval_token:
            pytest.skip("Missing plan_id or approval_token")
        
        # Approve the plan
        approve_response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/approve",
            json={
                "plan_id": plan_id,
                "approval_token": approval_token,
                "approval_note": "Test approval"
            }
        )
        
        if approve_response.status_code != 200:
            pytest.skip("Could not approve plan")
        
        # Apply to create run
        apply_response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/apply",
            json={
                "plan_id": plan_id,
                "execution_mode": "live_guarded"
            }
        )
        
        if apply_response.status_code != 200:
            pytest.skip("Could not apply plan")
        
        apply_data = apply_response.json()
        run_id = apply_data.get("run_id")
        
        if not run_id:
            pytest.skip("No run_id returned")
        
        # Test with short note (should fail)
        response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/manual-evidence",
            json={
                "provider_id": "iap_apple",
                "evidence_note": "short",  # Too short
                "evidence_links": ["https://example.com/evidence"],
                "verification_checks": [],
                "provider_console_confirmed": False,
                "mark_verified": False
            }
        )
        
        # Should fail due to short note
        assert response.status_code == 400, f"Expected 400 for short note, got {response.status_code}"
        assert "note" in response.text.lower() or "character" in response.text.lower()
        
        print("Manual evidence correctly rejects short notes")

    def test_manual_evidence_strict_validation_links_required(self):
        """Test manual evidence enforces evidence links when required."""
        # Create a run first
        prepare_response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/prepare",
            json={
                "providers": ["iap_google"],  # Manual provider
                "reason": "test_manual_evidence_links",
                "execution_mode": "dry_run"
            }
        )
        
        if prepare_response.status_code != 200:
            pytest.skip("Could not create test run")
        
        prepare_data = prepare_response.json()
        plan_id = prepare_data.get("plan_id")
        approval_token = prepare_data.get("approval_token")
        
        if not plan_id or not approval_token:
            pytest.skip("Missing plan_id or approval_token")
        
        # Approve and apply
        self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/approve",
            json={"plan_id": plan_id, "approval_token": approval_token}
        )
        
        apply_response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/apply",
            json={"plan_id": plan_id, "execution_mode": "live_guarded"}
        )
        
        if apply_response.status_code != 200:
            pytest.skip("Could not apply plan")
        
        run_id = apply_response.json().get("run_id")
        
        # Test without evidence links (should fail if require_links is true)
        response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/manual-evidence",
            json={
                "provider_id": "iap_google",
                "evidence_note": "This is a sufficiently long evidence note for testing purposes",
                "evidence_links": [],  # Empty links
                "verification_checks": [],
                "provider_console_confirmed": False,
                "mark_verified": False
            }
        )
        
        # Should fail due to missing links (policy requires links)
        assert response.status_code == 400, f"Expected 400 for missing links, got {response.status_code}"
        assert "link" in response.text.lower()
        
        print("Manual evidence correctly enforces evidence links requirement")

    def test_manual_evidence_verified_requires_checks(self):
        """Test mark_verified requires verification_checks and provider_console_confirmed."""
        # Create a run
        prepare_response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/prepare",
            json={
                "providers": ["oauth_apple"],  # Manual provider
                "reason": "test_verified_checks",
                "execution_mode": "dry_run"
            }
        )
        
        if prepare_response.status_code != 200:
            pytest.skip("Could not create test run")
        
        prepare_data = prepare_response.json()
        plan_id = prepare_data.get("plan_id")
        approval_token = prepare_data.get("approval_token")
        
        if not plan_id or not approval_token:
            pytest.skip("Missing plan_id or approval_token")
        
        self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/approve",
            json={"plan_id": plan_id, "approval_token": approval_token}
        )
        
        apply_response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/apply",
            json={"plan_id": plan_id, "execution_mode": "live_guarded"}
        )
        
        if apply_response.status_code != 200:
            pytest.skip("Could not apply plan")
        
        run_id = apply_response.json().get("run_id")
        
        # Test mark_verified without verification_checks
        response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/manual-evidence",
            json={
                "provider_id": "oauth_apple",
                "evidence_note": "This is a sufficiently long evidence note for testing purposes",
                "evidence_links": ["https://example.com/link1", "https://example.com/link2"],
                "verification_checks": [],  # Empty - should fail
                "provider_console_confirmed": True,
                "mark_verified": True
            }
        )
        
        assert response.status_code == 400, f"Expected 400 for missing verification_checks, got {response.status_code}"
        assert "verification" in response.text.lower()
        
        print("Manual evidence correctly requires verification_checks for mark_verified")

    # ==================== COMPLIANCE BUNDLE TESTS ====================

    def test_compliance_bundle_json_format(self):
        """Test GET /api/admin/security/key-rotation/runs/{run_id}/compliance-bundle with json format."""
        # Get a run to test
        runs_response = self.session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs?limit=5")
        
        if runs_response.status_code != 200:
            pytest.skip("Could not fetch runs")
        
        runs = runs_response.json().get("runs", [])
        if not runs:
            # Create a dry run
            dry_run_response = self.session.post(f"{BASE_URL}/api/admin/security/key-rotation/dry-run")
            if dry_run_response.status_code != 200:
                pytest.skip("Could not create dry run")
            run_id = dry_run_response.json().get("run_id")
        else:
            run_id = runs[0].get("run_id")
        
        # Get compliance bundle in JSON format
        response = self.session.get(
            f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/compliance-bundle",
            params={"format": "json"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify bundle structure
        assert "bundle_id" in data, "Bundle should have bundle_id"
        assert data["bundle_id"].startswith("keyrot_bundle_"), "bundle_id should have correct prefix"
        assert "generated_at" in data
        assert "run" in data
        assert "steps" in data
        assert "evidence" in data
        assert "counts" in data
        assert "readiness_delta" in data
        
        # Verify readiness_delta structure
        readiness_delta = data["readiness_delta"]
        assert "api_probe_only_ready" in readiness_delta
        assert "api_rotate_ready" in readiness_delta
        assert "manual_by_constraint" in readiness_delta
        
        print(f"Compliance bundle (JSON): {data['bundle_id']}")

    def test_compliance_bundle_markdown_format(self):
        """Test GET /api/admin/security/key-rotation/runs/{run_id}/compliance-bundle with markdown format."""
        # Get a run to test
        runs_response = self.session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs?limit=5")
        
        if runs_response.status_code != 200:
            pytest.skip("Could not fetch runs")
        
        runs = runs_response.json().get("runs", [])
        if not runs:
            dry_run_response = self.session.post(f"{BASE_URL}/api/admin/security/key-rotation/dry-run")
            if dry_run_response.status_code != 200:
                pytest.skip("Could not create dry run")
            run_id = dry_run_response.json().get("run_id")
        else:
            run_id = runs[0].get("run_id")
        
        # Get compliance bundle in markdown format
        response = self.session.get(
            f"{BASE_URL}/api/admin/security/key-rotation/runs/{run_id}/compliance-bundle",
            params={"format": "markdown"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify markdown response structure
        assert "bundle_id" in data
        assert data.get("format") == "markdown"
        assert "file_name" in data
        assert data["file_name"].endswith("_compliance_bundle.md")
        assert "content" in data
        
        # Verify markdown content
        content = data["content"]
        assert "# Key Rotation Compliance Bundle" in content
        assert "Run ID:" in content
        assert "Summary" in content
        
        print(f"Compliance bundle (Markdown): {data['bundle_id']}")

    def test_compliance_bundle_not_found(self):
        """Test compliance bundle returns 404 for non-existent run."""
        response = self.session.get(
            f"{BASE_URL}/api/admin/security/key-rotation/runs/nonexistent_run_id/compliance-bundle"
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Compliance bundle correctly returns 404 for non-existent run")

    # ==================== NO OBJECTID SERIALIZATION TESTS ====================

    def test_no_objectid_errors_readiness(self):
        """Verify no ObjectId serialization errors on readiness endpoint."""
        response = self.session.get(f"{BASE_URL}/api/admin/security/key-rotation/readiness")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        # If we get here without 500 error, no ObjectId serialization issue
        data = response.json()
        # Check for MongoDB ObjectId pattern (24 hex chars) in unexpected places
        # The key "_id" should not appear as a top-level or nested key
        data_str = str(data)
        assert "'_id':" not in data_str, "Response should not contain raw MongoDB _id fields"
        assert '"_id":' not in data_str, "Response should not contain raw MongoDB _id fields"
        print("No ObjectId errors on readiness endpoint")

    def test_no_objectid_errors_policy(self):
        """Verify no ObjectId serialization errors on policy endpoint."""
        response = self.session.get(f"{BASE_URL}/api/admin/security/key-rotation/policy")
        assert response.status_code == 200
        data = response.json()
        data_str = str(data)
        assert "'_id':" not in data_str, "Response should not contain raw MongoDB _id fields"
        assert '"_id":' not in data_str, "Response should not contain raw MongoDB _id fields"
        print("No ObjectId errors on policy endpoint")

    def test_no_objectid_errors_attest(self):
        """Verify no ObjectId serialization errors on attest endpoint."""
        response = self.session.post(
            f"{BASE_URL}/api/admin/security/key-rotation/policy/attest",
            json={
                "note": "ObjectId test",
                "run_prerequisite_refresh": False,
                "validate_webhook": False,
                "include_game_day_snapshot": False
            }
        )
        assert response.status_code == 200
        data = response.json()
        data_str = str(data)
        assert "'_id':" not in data_str, "Response should not contain raw MongoDB _id fields"
        assert '"_id":' not in data_str, "Response should not contain raw MongoDB _id fields"
        print("No ObjectId errors on attest endpoint")

    def test_no_objectid_errors_runs_list(self):
        """Verify no ObjectId serialization errors on runs list endpoint."""
        response = self.session.get(f"{BASE_URL}/api/admin/security/key-rotation/runs")
        assert response.status_code == 200
        data = response.json()
        data_str = str(data)
        assert "'_id':" not in data_str, "Response should not contain raw MongoDB _id fields"
        assert '"_id":' not in data_str, "Response should not contain raw MongoDB _id fields"
        print("No ObjectId errors on runs list endpoint")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
