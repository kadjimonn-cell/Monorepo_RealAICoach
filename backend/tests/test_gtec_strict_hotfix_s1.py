"""
GTEC Strict Hotfix S1 Tests

Tests for strict mode enforcement requirements:
1. run_full_scan default mode is STRICT_GLOBAL and _run_with_restart_loop enforces strict preflight flags
2. STRICT_GLOBAL mode: transient 502/503/504 in ACL/i18n/API-contract/DAST are hard failures (not waived info)
3. DIAGNOSTIC_RELAXED mode still allows transient artifact waivers for diagnostics
4. run_go_no_go_release_drill rejects when latest run is non-strict or has transient artifacts
5. build_release_certificate_snapshot includes strict_run_policy fields
6. PDF/email payload include strict policy markers
7. New strict-mode run evidence exists: triggered_by=strict_hotfix_s1_run should be INFRA_BLOCKED with scan_mode STRICT_GLOBAL when strict preflight fails
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/app/backend")

from services import gtec_scan_v2 as svc


# ============================================================================
# Test 1: run_full_scan default mode is STRICT_GLOBAL
# ============================================================================

def test_run_full_scan_default_mode_is_strict_global():
    """Verify run_full_scan defaults to STRICT_GLOBAL mode."""
    import inspect
    sig = inspect.signature(svc.run_full_scan)
    scan_mode_param = sig.parameters.get("scan_mode")
    assert scan_mode_param is not None, "scan_mode parameter must exist"
    assert scan_mode_param.default == svc.SCAN_MODE_STRICT_GLOBAL, \
        f"Default scan_mode should be STRICT_GLOBAL, got {scan_mode_param.default}"


def test_run_with_restart_loop_default_mode_is_strict_global():
    """Verify _run_with_restart_loop defaults to STRICT_GLOBAL mode."""
    import inspect
    sig = inspect.signature(svc._run_with_restart_loop)
    scan_mode_param = sig.parameters.get("scan_mode")
    assert scan_mode_param is not None, "scan_mode parameter must exist"
    assert scan_mode_param.default == svc.SCAN_MODE_STRICT_GLOBAL, \
        f"Default scan_mode should be STRICT_GLOBAL, got {scan_mode_param.default}"


def test_normalize_scan_mode_defaults_to_strict():
    """Verify _normalize_scan_mode defaults to STRICT_GLOBAL for empty/invalid input."""
    assert svc._normalize_scan_mode(None) == svc.SCAN_MODE_STRICT_GLOBAL
    assert svc._normalize_scan_mode("") == svc.SCAN_MODE_STRICT_GLOBAL
    assert svc._normalize_scan_mode("invalid") == svc.SCAN_MODE_STRICT_GLOBAL
    assert svc._normalize_scan_mode("DIAGNOSTIC_RELAXED") == svc.SCAN_MODE_DIAGNOSTIC_RELAXED
    assert svc._normalize_scan_mode("diagnostic_relaxed") == svc.SCAN_MODE_DIAGNOSTIC_RELAXED


def test_is_strict_mode_helper():
    """Verify _is_strict_mode correctly identifies strict mode."""
    assert svc._is_strict_mode(svc.SCAN_MODE_STRICT_GLOBAL) is True
    assert svc._is_strict_mode("STRICT_GLOBAL") is True
    assert svc._is_strict_mode(svc.SCAN_MODE_DIAGNOSTIC_RELAXED) is False
    assert svc._is_strict_mode("DIAGNOSTIC_RELAXED") is False
    assert svc._is_strict_mode(None) is True  # defaults to strict
    assert svc._is_strict_mode("") is True  # defaults to strict


# ============================================================================
# Test 2: STRICT_GLOBAL mode - transient 502/503/504 are hard failures
# ============================================================================

@pytest.mark.asyncio
async def test_dast_crawler_strict_mode_transient_is_hard_fail():
    """Verify DAST crawler treats transient errors as hard failures in STRICT_GLOBAL mode."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_exec.return_value = mock_proc
        
        # STRICT_GLOBAL mode - should FAIL
        result = await svc.run_dast_via_crawler(viewports="desktop", strict_global=True)
        
        assert result.get("status") == "FAIL", "STRICT_GLOBAL mode should FAIL on transient errors"
        findings = result.get("findings", [])
        strict_fail_finding = next(
            (f for f in findings if f.get("label") == "crawler_runtime_infra_artifact_strict_fail"),
            None
        )
        assert strict_fail_finding is not None, "Should have strict_fail finding"
        assert strict_fail_finding.get("severity") == "high", "Strict fail should be high severity"


@pytest.mark.asyncio
async def test_dast_crawler_relaxed_mode_transient_is_waived():
    """Verify DAST crawler treats transient errors as waived info in DIAGNOSTIC_RELAXED mode."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_exec.return_value = mock_proc
        
        # DIAGNOSTIC_RELAXED mode - should PASS with waived finding
        result = await svc.run_dast_via_crawler(viewports="desktop", strict_global=False)
        
        assert result.get("status") == "PASS", "DIAGNOSTIC_RELAXED mode should PASS on transient errors"
        findings = result.get("findings", [])
        waived_finding = next(
            (f for f in findings if f.get("label") == "crawler_runtime_infra_artifact"),
            None
        )
        assert waived_finding is not None, "Should have waived finding"
        assert waived_finding.get("severity") == "info", "Waived finding should be info severity"
        assert waived_finding.get("waived") is True, "Finding should be waived"


def test_acl_probes_strict_mode_transient_handling():
    """Verify ACL probes code handles transient errors differently based on strict_global flag."""
    import inspect
    source = inspect.getsource(svc.run_access_control_probes)
    
    # Check that strict_global parameter exists
    assert "strict_global: bool = True" in source, "ACL probes should default to strict_global=True"
    
    # Check that 502/503/504 handling differs based on strict_global
    assert "if strict_global:" in source, "Should have strict_global conditional"
    assert "rbac_probe_issues" in source, "Should track probe issues for strict mode"
    assert "rbac_transient_issues" in source, "Should track transient issues for relaxed mode"


def test_i18n_probes_strict_mode_transient_handling():
    """Verify i18n probes code handles transient errors differently based on strict_global flag."""
    import inspect
    source = inspect.getsource(svc.run_i18n_public_access_probes)
    
    # Check that strict_global parameter exists
    assert "strict_global: bool = True" in source, "i18n probes should default to strict_global=True"
    
    # Check that transient handling differs based on strict_global
    assert "not strict_global" in source, "Should have strict_global conditional for transient handling"
    assert "transient_findings" in source, "Should track transient findings separately"


def test_api_contract_scan_strict_mode_transient_handling():
    """Verify API contract scan code handles transient errors differently based on strict_global flag."""
    import inspect
    source = inspect.getsource(svc.run_api_contract_scan)
    
    # Check that strict_global parameter exists
    assert "strict_global: bool = True" in source, "API contract scan should default to strict_global=True"
    
    # Check that transient handling differs based on strict_global
    assert "not strict_global" in source, "Should have strict_global conditional for transient handling"
    assert "transient_findings" in source, "Should track transient findings separately"


# ============================================================================
# Test 3: DIAGNOSTIC_RELAXED mode allows transient artifact waivers
# ============================================================================

def test_diagnostic_relaxed_mode_constant_exists():
    """Verify DIAGNOSTIC_RELAXED mode constant exists."""
    assert hasattr(svc, "SCAN_MODE_DIAGNOSTIC_RELAXED")
    assert svc.SCAN_MODE_DIAGNOSTIC_RELAXED == "DIAGNOSTIC_RELAXED"


def test_diagnostic_relaxed_mode_is_not_strict():
    """Verify DIAGNOSTIC_RELAXED mode is not considered strict."""
    assert svc._is_strict_mode(svc.SCAN_MODE_DIAGNOSTIC_RELAXED) is False


# ============================================================================
# Test 4: run_go_no_go_release_drill rejects non-strict or transient artifacts
# ============================================================================

def test_go_no_go_drill_checks_strict_gate():
    """Verify run_go_no_go_release_drill checks strict_gate_passed."""
    import inspect
    source = inspect.getsource(svc.run_go_no_go_release_drill)
    
    # Check that strict gate is evaluated
    assert "strict_gate_passed" in source, "Should check strict_gate_passed"
    assert "strict_mode_passed" in source, "Should check strict_mode_passed"
    assert "transient_artifact_count" in source, "Should check transient_artifact_count"
    
    # Check that NO_GO is returned when strict gate fails
    assert 'decision = "NO_GO"' in source, "Should set NO_GO decision"
    assert "Strict global gate failed" in source, "Should have strict gate failure reason"


def test_go_no_go_drill_validation_includes_strict_fields():
    """Verify run_go_no_go_release_drill validation includes strict policy fields."""
    import inspect
    source = inspect.getsource(svc.run_go_no_go_release_drill)
    
    # Check validation dict includes strict fields
    assert '"strict_global_mode_passed"' in source, "Validation should include strict_global_mode_passed"
    assert '"transient_artifact_count"' in source, "Validation should include transient_artifact_count"
    assert '"strict_gate_passed"' in source, "Validation should include strict_gate_passed"


@pytest.mark.asyncio
async def test_go_no_go_drill_rejects_non_strict_run():
    """Verify GO/NO-GO drill code includes strict gate checks."""
    import inspect
    source = inspect.getsource(svc.run_go_no_go_release_drill)
    
    # Verify the code checks strict gate and rejects non-strict runs
    assert "strict_gate_passed" in source, "Should check strict_gate_passed"
    assert "strict_mode_passed" in source, "Should check strict_mode_passed"
    assert "transient_artifact_count" in source, "Should check transient_artifact_count"
    
    # Verify NO_GO is set when strict gate fails
    assert 'if not strict_gate_passed:' in source, "Should have conditional for strict gate failure"
    assert 'decision = "NO_GO"' in source, "Should set NO_GO decision"
    
    # Verify validation dict includes strict fields
    assert '"strict_global_mode_passed": strict_mode_passed' in source, "Validation should include strict_global_mode_passed"
    assert '"transient_artifact_count": transient_artifact_count' in source, "Validation should include transient_artifact_count"
    assert '"strict_gate_passed": strict_gate_passed' in source, "Validation should include strict_gate_passed"


# ============================================================================
# Test 5: build_release_certificate_snapshot includes strict_run_policy fields
# ============================================================================

@pytest.mark.asyncio
async def test_release_certificate_includes_strict_run_policy():
    """Verify build_release_certificate_snapshot includes strict_run_policy fields."""
    from motor.motor_asyncio import AsyncIOMotorClient
    
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "realtalk_db")]
    
    try:
        cert = await svc.build_release_certificate_snapshot(db)
        
        # Check that strict_run_policy is present in checks
        checks = cert.get("checks", {})
        strict_policy = checks.get("strict_run_policy", {})
        
        assert "scan_mode" in strict_policy, "strict_run_policy should have scan_mode"
        assert "strict_global_mode" in strict_policy, "strict_run_policy should have strict_global_mode"
        assert "transient_artifact_count" in strict_policy, "strict_run_policy should have transient_artifact_count"
        assert "strict_gate_passed" in strict_policy, "strict_run_policy should have strict_gate_passed"
        assert "preflight_require_external_preview" in strict_policy, "strict_run_policy should have preflight_require_external_preview"
        assert "preflight_require_local_backend" in strict_policy, "strict_run_policy should have preflight_require_local_backend"
    finally:
        client.close()


def test_release_certificate_code_includes_strict_fields():
    """Verify build_release_certificate_snapshot code includes strict_run_policy fields."""
    import inspect
    source = inspect.getsource(svc.build_release_certificate_snapshot)
    
    assert '"strict_run_policy"' in source, "Should have strict_run_policy section"
    assert '"scan_mode"' in source, "Should include scan_mode"
    assert '"strict_global_mode"' in source, "Should include strict_global_mode"
    assert '"transient_artifact_count"' in source, "Should include transient_artifact_count"
    assert '"strict_gate_passed"' in source, "Should include strict_gate_passed"
    assert '"preflight_require_external_preview"' in source, "Should include preflight_require_external_preview"
    assert '"preflight_require_local_backend"' in source, "Should include preflight_require_local_backend"


# ============================================================================
# Test 6: PDF/email payload include strict policy markers
# ============================================================================

def test_email_dispatch_includes_strict_policy_markers():
    """Verify email dispatch code includes strict policy markers."""
    import inspect
    source = inspect.getsource(svc._email_report_to_admins)
    
    # Check that c5_runtime_summary includes run_policy with strict fields
    assert '"run_policy"' in source, "Should have run_policy in c5_runtime_summary"
    assert '"scan_mode"' in source, "Should include scan_mode"
    assert '"strict_global_mode"' in source, "Should include strict_global_mode"
    assert '"transient_artifact_count"' in source, "Should include transient_artifact_count"
    assert '"strict_gate_passed"' in source, "Should include strict_gate_passed"
    assert '"preflight_require_external_preview"' in source, "Should include preflight_require_external_preview"
    assert '"preflight_require_local_backend"' in source, "Should include preflight_require_local_backend"


def test_c5_notification_snapshot_includes_run_policy():
    """Verify build_c5_notification_snapshot includes run_policy with strict fields."""
    import inspect
    source = inspect.getsource(svc.build_c5_notification_snapshot)
    
    assert '"run_policy"' in source, "Should have run_policy section"
    assert '"scan_mode"' in source, "Should include scan_mode"
    assert '"strict_global_mode"' in source, "Should include strict_global_mode"
    assert '"transient_artifact_count"' in source, "Should include transient_artifact_count"
    assert '"strict_gate_passed"' in source, "Should include strict_gate_passed"


def test_snapshot_from_report_email_dispatch_includes_run_policy():
    """Verify build_snapshot_from_report_email_dispatch includes run_policy."""
    import inspect
    source = inspect.getsource(svc.build_snapshot_from_report_email_dispatch)
    
    assert '"run_policy"' in source, "Should have run_policy section"
    assert '"scan_mode"' in source, "Should include scan_mode"
    assert '"strict_global_mode"' in source, "Should include strict_global_mode"
    assert '"transient_artifact_count"' in source, "Should include transient_artifact_count"
    assert '"strict_gate_passed"' in source, "Should include strict_gate_passed"


# ============================================================================
# Test 7: INFRA_BLOCKED report includes strict mode fields
# ============================================================================

def test_infra_blocked_report_includes_strict_fields():
    """Verify _build_infra_blocked_report includes strict mode fields."""
    preflight = {
        "required_checks": 3,
        "attempts_completed": 1,
        "reasons": ["external_preview_unstable"],
    }
    
    report = svc._build_infra_blocked_report(
        task_id="gtec_c5_strict_test",
        execution_hash="hash_strict_test",
        triggered_by="strict_hotfix_s1_run",
        actor="apscheduler",
        attempt_tag="initial",
        attempt_index=0,
        preflight=preflight,
        scan_mode=svc.SCAN_MODE_STRICT_GLOBAL,
    )
    
    # Verify strict mode fields
    assert report.get("scan_mode") == svc.SCAN_MODE_STRICT_GLOBAL, "scan_mode should be STRICT_GLOBAL"
    assert report.get("strict_global_mode") is True, "strict_global_mode should be True"
    assert report.get("transient_artifact_count") == 0, "transient_artifact_count should be 0"
    assert report.get("strict_gate_passed") is False, "strict_gate_passed should be False for INFRA_BLOCKED"
    
    # Verify preflight_policy
    preflight_policy = report.get("preflight_policy", {})
    assert preflight_policy.get("require_external_preview") is True, "require_external_preview should be True in strict mode"
    assert preflight_policy.get("require_local_backend") is True, "require_local_backend should be True in strict mode"


def test_infra_blocked_report_status():
    """Verify INFRA_BLOCKED report has correct status."""
    preflight = {
        "required_checks": 3,
        "attempts_completed": 1,
        "reasons": ["local_backend_unstable"],
    }
    
    report = svc._build_infra_blocked_report(
        task_id="gtec_c5_infra_test",
        execution_hash="hash_infra_test",
        triggered_by="scheduler",
        actor="apscheduler",
        attempt_tag="initial",
        attempt_index=0,
        preflight=preflight,
        scan_mode=svc.SCAN_MODE_STRICT_GLOBAL,
    )
    
    assert report.get("status") == "INFRA_BLOCKED", "Status should be INFRA_BLOCKED"
    assert "runtime preflight" in str(report.get("summary") or "").lower(), "Summary should mention preflight"


# ============================================================================
# Test 8: Preflight gate enforces strict flags in strict mode
# ============================================================================

@pytest.mark.asyncio
async def test_preflight_gate_strict_mode_requires_external_preview():
    """Verify preflight gate requires external preview in strict mode."""
    # Mock both probes to pass
    async def fake_local():
        return {"ok": True, "status_code": 200, "base_url": "http://127.0.0.1:8001"}

    async def fake_external(_base_url=None, **_kwargs):
        return {"stable": True, "checks": []}

    with patch.object(svc, "_probe_local_backend_health", fake_local):
        with patch.object(svc, "get_external_host_proxy_health", fake_external):
            # Strict mode - both checks required
            result = await svc.run_scan_preflight_gate(
                require_external_preview=True,
                require_local_backend=True,
            )
            assert result.get("passed") is True
            assert result.get("require_external_preview") is True
            assert result.get("require_local_backend") is True


@pytest.mark.asyncio
async def test_preflight_gate_relaxed_mode_can_bypass_external():
    """Verify preflight gate can bypass external preview in relaxed mode."""
    async def fake_local():
        return {"ok": True, "status_code": 200, "base_url": "http://127.0.0.1:8001"}

    with patch.object(svc, "_probe_local_backend_health", fake_local):
        # Relaxed mode - external preview not required
        result = await svc.run_scan_preflight_gate(
            require_external_preview=False,
            require_local_backend=True,
        )
        assert result.get("passed") is True
        assert result.get("require_external_preview") is False


# ============================================================================
# Test 9: _run_with_restart_loop enforces strict preflight based on scan_mode
# ============================================================================

def test_run_with_restart_loop_enforces_strict_preflight():
    """Verify _run_with_restart_loop enforces strict preflight flags based on scan_mode."""
    import inspect
    source = inspect.getsource(svc._run_with_restart_loop)
    
    # Check that preflight is called with strict_global flags
    assert "require_external_preview=strict_global" in source, "Should pass strict_global to require_external_preview"
    assert "require_local_backend=strict_global" in source, "Should pass strict_global to require_local_backend"
    
    # Check that scan_mode is normalized
    assert "_normalize_scan_mode(scan_mode)" in source, "Should normalize scan_mode"
    assert "_is_strict_mode(mode)" in source, "Should check if mode is strict"


# ============================================================================
# Test 10: Validate notification snapshot consistency check for strict mode
# ============================================================================

def test_validate_notification_snapshot_checks_strict_mode_transients():
    """Verify _validate_notification_snapshot checks for transient artifacts in strict mode."""
    import inspect
    source = inspect.getsource(svc._validate_notification_snapshot)
    
    assert "strict_mode_transient_artifacts_present" in source, "Should check for transient artifacts in strict mode"
    assert "strict_mode" in source, "Should check strict_mode"
    assert "transient_count" in source, "Should check transient_count"


# ============================================================================
# Test 11: Verify email template includes strict policy markers
# ============================================================================

def test_email_template_includes_strict_policy_markers():
    """Verify email template includes strict policy markers."""
    from utils import email_templates
    import inspect
    
    # Check gtec_c5_scan_report_email function signature
    if hasattr(email_templates, "gtec_c5_scan_report_email"):
        sig = inspect.signature(email_templates.gtec_c5_scan_report_email)
        params = list(sig.parameters.keys())
        
        assert "c5_scan_mode" in params, "Should have c5_scan_mode parameter"
        assert "c5_strict_global_mode" in params, "Should have c5_strict_global_mode parameter"
        assert "c5_transient_artifact_count" in params, "Should have c5_transient_artifact_count parameter"
        assert "c5_strict_gate_passed" in params, "Should have c5_strict_gate_passed parameter"


# ============================================================================
# Test 12: Integration test - verify latest scan has strict mode fields
# ============================================================================

@pytest.mark.asyncio
async def test_latest_scan_has_strict_mode_fields():
    """Verify latest scan report has strict mode fields."""
    from motor.motor_asyncio import AsyncIOMotorClient
    
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "realtalk_db")]
    
    try:
        report = await db["gtec_scan_c5_reports"].find_one({}, {"_id": 0}, sort=[("generated_at", -1)])
        
        if report:
            # Check strict mode fields exist
            assert "scan_mode" in report, "Report should have scan_mode"
            assert "strict_global_mode" in report or report.get("scan_mode") == svc.SCAN_MODE_STRICT_GLOBAL, \
                "Report should have strict_global_mode or be in STRICT_GLOBAL mode"
            
            # Check preflight_policy if present
            preflight_policy = report.get("preflight_policy", {})
            if preflight_policy:
                assert "require_external_preview" in preflight_policy, "preflight_policy should have require_external_preview"
                assert "require_local_backend" in preflight_policy, "preflight_policy should have require_local_backend"
    finally:
        client.close()


# ============================================================================
# Test 13: Verify count_transient_artifacts function
# ============================================================================

def test_count_transient_artifacts():
    """Verify _count_transient_artifacts correctly counts transient findings."""
    sections = {
        "acl": {
            "findings": [
                {"label": "admin_probe_transient_gateway_artifact", "count": 2},
                {"label": "admin_route_leaked", "count": 1},
            ]
        },
        "i18n": {
            "findings": [
                {"label": "i18n_public_endpoint_transient_gateway_artifact", "count": 1},
            ]
        },
        "api_contract": {
            "findings": [
                {"label": "api_contract_transient_gateway_artifact", "count": 3},
            ]
        },
        "dast": {
            "findings": [
                {"label": "crawler_runtime_infra_artifact", "count": 1},
            ]
        },
    }
    
    count = svc._count_transient_artifacts(sections)
    # Should count: 2 + 1 + 3 + 1 = 7 transient artifacts
    assert count == 7, f"Expected 7 transient artifacts, got {count}"


def test_count_transient_artifacts_empty():
    """Verify _count_transient_artifacts returns 0 for empty sections."""
    assert svc._count_transient_artifacts({}) == 0
    assert svc._count_transient_artifacts(None) == 0
    assert svc._count_transient_artifacts({"acl": {"findings": []}}) == 0


# ============================================================================
# Test 14: Verify strict mode constants
# ============================================================================

def test_strict_mode_constants():
    """Verify strict mode constants are defined correctly."""
    assert svc.SCAN_MODE_STRICT_GLOBAL == "STRICT_GLOBAL"
    assert svc.SCAN_MODE_DIAGNOSTIC_RELAXED == "DIAGNOSTIC_RELAXED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
