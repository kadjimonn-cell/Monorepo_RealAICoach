"""
GTEC Phase A Preflight & Retry Hardening Tests

Tests for:
1. run_scan_preflight_gate enforces required stable checks and fails fast when unstable
2. _run_with_restart_loop creates INFRA_BLOCKED report when preflight fails (no full scan)
3. INFRA_BLOCKED report contains preflight details and fail reason summary
4. access-control probes use transient retries for 502/503/504 before marking inconclusive
5. api_contract probes use transient retries and still report correct pass/fail semantics
6. scheduler tick preserves queued events when report status is INFRA_BLOCKED
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.append("/app/backend")

from services import gtec_scan_v2 as svc


# ============================================================================
# PREFLIGHT GATE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_preflight_gate_passes_all_checks_when_stable(monkeypatch):
    """Preflight passes when all required checks are stable."""
    async def fake_local():
        return {"ok": True, "status_code": 200, "base_url": "http://127.0.0.1:8001"}

    async def fake_external(_base_url=None, **_kwargs):
        return {"stable": True, "checks": [{"path": "/_preview/health", "ok": True}]}

    monkeypatch.setattr(svc, "_probe_local_backend_health", fake_local)
    monkeypatch.setattr(svc, "get_external_host_proxy_health", fake_external)

    result = await svc.run_scan_preflight_gate(required_checks=3)
    
    assert result.get("passed") is True
    assert result.get("attempts_completed") == 3
    assert result.get("required_checks") == 3
    assert result.get("reasons") == []
    assert "checked_at" in result


@pytest.mark.asyncio
async def test_preflight_gate_fails_fast_on_first_unstable_check(monkeypatch):
    """Preflight fails fast on first unstable check (no wasted attempts)."""
    async def fake_local():
        return {"ok": True, "status_code": 200, "base_url": "http://127.0.0.1:8001"}

    async def fake_external(_base_url=None, **_kwargs):
        return {"stable": False, "checks": [{"path": "/_preview/health", "ok": False}]}

    monkeypatch.setattr(svc, "_probe_local_backend_health", fake_local)
    monkeypatch.setattr(svc, "get_external_host_proxy_health", fake_external)

    result = await svc.run_scan_preflight_gate(required_checks=3)
    
    assert result.get("passed") is False
    assert result.get("attempts_completed") == 1  # Fails fast
    assert "external_preview_unstable" in (result.get("reasons") or [])


@pytest.mark.asyncio
async def test_preflight_gate_fails_on_local_backend_unstable(monkeypatch):
    """Preflight fails when local backend is unstable."""
    async def fake_local():
        return {"ok": False, "status_code": 500, "base_url": "http://127.0.0.1:8001"}

    async def fake_external(_base_url=None, **_kwargs):
        return {"stable": True, "checks": []}

    monkeypatch.setattr(svc, "_probe_local_backend_health", fake_local)
    monkeypatch.setattr(svc, "get_external_host_proxy_health", fake_external)

    result = await svc.run_scan_preflight_gate(required_checks=3)
    
    assert result.get("passed") is False
    assert result.get("attempts_completed") == 1
    assert "local_backend_unstable" in (result.get("reasons") or [])


@pytest.mark.asyncio
async def test_preflight_gate_fails_on_both_unstable(monkeypatch):
    """Preflight captures both reasons when both local and external are unstable."""
    async def fake_local():
        return {"ok": False, "status_code": 503, "base_url": "http://127.0.0.1:8001"}

    async def fake_external(_base_url=None, **_kwargs):
        return {"stable": False, "checks": []}

    monkeypatch.setattr(svc, "_probe_local_backend_health", fake_local)
    monkeypatch.setattr(svc, "get_external_host_proxy_health", fake_external)

    result = await svc.run_scan_preflight_gate(required_checks=3)
    
    assert result.get("passed") is False
    reasons = result.get("reasons") or []
    assert "local_backend_unstable" in reasons
    assert "external_preview_unstable" in reasons


@pytest.mark.asyncio
async def test_preflight_gate_respects_custom_required_checks(monkeypatch):
    """Preflight respects custom required_checks parameter."""
    call_count = 0
    
    async def fake_local():
        nonlocal call_count
        call_count += 1
        return {"ok": True, "status_code": 200, "base_url": "http://127.0.0.1:8001"}

    async def fake_external(_base_url=None, **_kwargs):
        return {"stable": True, "checks": []}

    monkeypatch.setattr(svc, "_probe_local_backend_health", fake_local)
    monkeypatch.setattr(svc, "get_external_host_proxy_health", fake_external)

    result = await svc.run_scan_preflight_gate(required_checks=5)
    
    assert result.get("passed") is True
    assert result.get("attempts_completed") == 5
    assert call_count == 5


# ============================================================================
# INFRA_BLOCKED REPORT TESTS
# ============================================================================

def test_infra_blocked_report_structure():
    """INFRA_BLOCKED report contains all required fields."""
    preflight = {
        "passed": False,
        "required_checks": 3,
        "attempts_completed": 1,
        "reasons": ["external_preview_unstable"],
        "attempts": [{"attempt": 1, "ok": False}],
        "checked_at": "2026-01-15T00:00:00+00:00",
    }
    
    report = svc._build_infra_blocked_report(
        task_id="gtec_c5_test_infra",
        execution_hash="hash_test",
        triggered_by="scheduler",
        actor="apscheduler",
        scan_mode="manual",
        attempt_tag="initial",
        attempt_index=0,
        preflight=preflight,
    )
    
    # Status and core fields
    assert report.get("status") == "INFRA_BLOCKED"
    assert report.get("task_id") == "gtec_c5_test_infra"
    assert report.get("execution_hash") == "hash_test"
    assert report.get("triggered_by") == "scheduler"
    assert report.get("actor") == "apscheduler"
    
    # Preflight details embedded
    assert report.get("preflight") == preflight
    
    # Severity counts (1 high for preflight failure)
    assert report.get("high_vulns") == 1
    assert report.get("critical_vulns") == 0
    
    # Steps skipped (no full scan executed)
    steps_skipped = report.get("steps_skipped") or []
    assert "sast" in steps_skipped
    assert "dast" in steps_skipped
    assert "acl" in steps_skipped
    assert "api_contract" in steps_skipped


def test_infra_blocked_report_summary_contains_preflight_info():
    """INFRA_BLOCKED report summary contains preflight stability info."""
    preflight = {
        "required_checks": 3,
        "attempts_completed": 1,
        "reasons": ["external_preview_unstable", "local_backend_unstable"],
    }
    
    report = svc._build_infra_blocked_report(
        task_id="gtec_c5_test",
        execution_hash="hash",
        triggered_by="scheduler",
        actor="apscheduler",
        scan_mode="manual",
        attempt_tag="initial",
        attempt_index=0,
        preflight=preflight,
    )
    
    summary = str(report.get("summary") or "").lower()
    assert "infra_blocked" in summary
    assert "preflight" in summary
    assert "1/3" in summary  # attempts_completed/required_checks


def test_fail_reason_summary_for_infra_blocked():
    """_build_fail_reason_summary returns correct message for INFRA_BLOCKED."""
    preflight = {
        "required_checks": 3,
        "attempts_completed": 1,
        "reasons": ["external_preview_unstable"],
    }
    
    report = svc._build_infra_blocked_report(
        task_id="gtec_c5_test",
        execution_hash="hash",
        triggered_by="scheduler",
        actor="apscheduler",
        scan_mode="manual",
        attempt_tag="initial",
        attempt_index=0,
        preflight=preflight,
    )
    
    fail_reason = svc._build_fail_reason_summary(report)
    
    assert "INFRA_BLOCKED because" in fail_reason
    assert "preflight stability not met" in fail_reason
    assert "1/3" in fail_reason
    assert "external_preview_unstable" in fail_reason


def test_infra_blocked_report_v3_output_block():
    """INFRA_BLOCKED report contains v3_output block with FAIL statuses."""
    preflight = {
        "required_checks": 3,
        "attempts_completed": 1,
        "reasons": ["external_preview_unstable"],
    }
    
    report = svc._build_infra_blocked_report(
        task_id="gtec_c5_test",
        execution_hash="hash",
        triggered_by="scheduler",
        actor="apscheduler",
        scan_mode="manual",
        attempt_tag="initial",
        attempt_index=0,
        preflight=preflight,
    )
    
    v3 = report.get("v3_output") or {}
    assert v3.get("SYSTEM_STATUS") == "FAIL"
    assert v3.get("SECURITY_STATUS") == "FAIL"


# ============================================================================
# TRANSIENT RETRY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_probe_with_transient_retry_retries_on_502():
    """_probe_with_transient_retry retries on 502 status."""
    call_count = 0
    
    class FakeResponse:
        def __init__(self, status):
            self.status_code = status
            self.text = "test"
            self.headers = {}
    
    async def fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return FakeResponse(502)
        return FakeResponse(200)
    
    class FakeClient:
        async def get(self, url, **kwargs):
            return await fake_get(url, **kwargs)
        
        async def post(self, url, **kwargs):
            return await fake_get(url, **kwargs)
    
    cli = FakeClient()
    resp, err = await svc._probe_with_transient_retry(
        cli, "GET", "http://test.com/api/health",
        attempts=3, transient_statuses=(502, 503, 504), backoff_seconds=0.01
    )
    
    assert call_count == 3
    assert resp is not None
    assert resp.status_code == 200
    assert err is None


@pytest.mark.asyncio
async def test_probe_with_transient_retry_retries_on_503():
    """_probe_with_transient_retry retries on 503 status."""
    call_count = 0
    
    class FakeResponse:
        def __init__(self, status):
            self.status_code = status
            self.text = "test"
            self.headers = {}
    
    async def fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return FakeResponse(503)
        return FakeResponse(200)
    
    class FakeClient:
        async def get(self, url, **kwargs):
            return await fake_get(url, **kwargs)
        
        async def post(self, url, **kwargs):
            return await fake_get(url, **kwargs)
    
    cli = FakeClient()
    resp, err = await svc._probe_with_transient_retry(
        cli, "GET", "http://test.com/api/health",
        attempts=3, transient_statuses=(502, 503, 504), backoff_seconds=0.01
    )
    
    assert call_count == 2
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_probe_with_transient_retry_retries_on_504():
    """_probe_with_transient_retry retries on 504 status."""
    call_count = 0
    
    class FakeResponse:
        def __init__(self, status):
            self.status_code = status
            self.text = "test"
            self.headers = {}
    
    async def fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return FakeResponse(504)
        return FakeResponse(200)
    
    class FakeClient:
        async def get(self, url, **kwargs):
            return await fake_get(url, **kwargs)
        
        async def post(self, url, **kwargs):
            return await fake_get(url, **kwargs)
    
    cli = FakeClient()
    resp, err = await svc._probe_with_transient_retry(
        cli, "GET", "http://test.com/api/health",
        attempts=3, transient_statuses=(502, 503, 504), backoff_seconds=0.01
    )
    
    assert call_count == 2
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_probe_with_transient_retry_returns_last_response_on_exhausted_attempts():
    """_probe_with_transient_retry returns last response when attempts exhausted."""
    call_count = 0
    
    class FakeResponse:
        def __init__(self, status):
            self.status_code = status
            self.text = "test"
            self.headers = {}
    
    async def fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return FakeResponse(502)  # Always return 502
    
    class FakeClient:
        async def get(self, url, **kwargs):
            return await fake_get(url, **kwargs)
        
        async def post(self, url, **kwargs):
            return await fake_get(url, **kwargs)
    
    cli = FakeClient()
    resp, err = await svc._probe_with_transient_retry(
        cli, "GET", "http://test.com/api/health",
        attempts=3, transient_statuses=(502, 503, 504), backoff_seconds=0.01
    )
    
    assert call_count == 3
    assert resp is not None
    assert resp.status_code == 502
    assert err is None


@pytest.mark.asyncio
async def test_probe_with_transient_retry_handles_exception():
    """_probe_with_transient_retry handles exceptions and retries."""
    call_count = 0
    
    class FakeResponse:
        def __init__(self, status):
            self.status_code = status
            self.text = "test"
            self.headers = {}
    
    async def fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("Connection refused")
        return FakeResponse(200)
    
    class FakeClient:
        async def get(self, url, **kwargs):
            return await fake_get(url, **kwargs)
        
        async def post(self, url, **kwargs):
            return await fake_get(url, **kwargs)
    
    cli = FakeClient()
    resp, err = await svc._probe_with_transient_retry(
        cli, "GET", "http://test.com/api/health",
        attempts=3, transient_statuses=(502, 503, 504), backoff_seconds=0.01
    )
    
    assert call_count == 2
    assert resp is not None
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_probe_with_transient_retry_returns_error_on_all_exceptions():
    """_probe_with_transient_retry returns error when all attempts fail with exceptions."""
    call_count = 0
    
    async def fake_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Connection refused")
    
    class FakeClient:
        async def get(self, url, **kwargs):
            return await fake_get(url, **kwargs)
        
        async def post(self, url, **kwargs):
            return await fake_get(url, **kwargs)
    
    cli = FakeClient()
    resp, err = await svc._probe_with_transient_retry(
        cli, "GET", "http://test.com/api/health",
        attempts=3, transient_statuses=(502, 503, 504), backoff_seconds=0.01
    )
    
    assert call_count == 3
    assert resp is None
    assert err is not None
    assert "ConnectionError" in err


# ============================================================================
# ACCESS CONTROL PROBES WITH TRANSIENT RETRY
# ============================================================================

@pytest.mark.asyncio
async def test_access_control_probes_use_transient_retry(monkeypatch):
    """Access control probes use transient retry for 502/503/504."""
    retry_calls = []
    
    
    async def tracking_probe(cli, method, url, **kwargs):
        retry_calls.append({
            "url": url,
            "attempts": kwargs.get("attempts"),
            "transient_statuses": kwargs.get("transient_statuses"),
        })
        # Return a 401 (expected for access control)
        class FakeResp:
            status_code = 401
            text = ""
            headers = {}
        return FakeResp(), None
    
    monkeypatch.setattr(svc, "_probe_with_transient_retry", tracking_probe)
    
    await svc.run_access_control_probes("http://127.0.0.1:8001")
    
    # Verify transient retry was called with correct parameters
    assert len(retry_calls) > 0
    for call in retry_calls:
        assert call["attempts"] == 3
        assert call["transient_statuses"] == (502, 503, 504)


# ============================================================================
# API CONTRACT PROBES WITH TRANSIENT RETRY
# ============================================================================

@pytest.mark.asyncio
async def test_api_contract_probes_use_transient_retry(monkeypatch):
    """API contract probes use transient retry for 502/503/504."""
    retry_calls = []
    
    async def tracking_probe(cli, method, url, **kwargs):
        retry_calls.append({
            "url": url,
            "attempts": kwargs.get("attempts"),
            "transient_statuses": kwargs.get("transient_statuses"),
        })
        # Return a 200 with JSON content type
        class FakeResp:
            status_code = 200
            text = '{"status": "ok"}'
            headers = {"content-type": "application/json"}
        return FakeResp(), None
    
    monkeypatch.setattr(svc, "_probe_with_transient_retry", tracking_probe)
    
    result = await svc.run_api_contract_scan()
    
    # Verify transient retry was called with correct parameters
    assert len(retry_calls) > 0
    for call in retry_calls:
        assert call["attempts"] == 3
        assert call["transient_statuses"] == (502, 503, 504)
    
    # Verify pass/fail semantics still work
    assert result.get("status") == "PASS"


@pytest.mark.asyncio
async def test_api_contract_probes_report_failure_correctly(monkeypatch):
    """API contract probes report failure correctly after transient retries."""
    async def failing_probe(cli, method, url, **kwargs):
        class FakeResp:
            status_code = 500
            text = "Internal Server Error"
            headers = {"content-type": "text/plain"}
        return FakeResp(), None
    
    monkeypatch.setattr(svc, "_probe_with_transient_retry", failing_probe)
    
    result = await svc.run_api_contract_scan()
    
    assert result.get("status") == "FAIL"
    findings = result.get("findings") or []
    assert len(findings) > 0
    assert any(f.get("label") == "api_contract_violation" for f in findings)


# ============================================================================
# SCHEDULER TICK EVENT PRESERVATION TESTS
# ============================================================================

def test_scheduler_tick_event_preservation_logic():
    """Verify scheduler tick logic preserves events when INFRA_BLOCKED.
    
    This tests the conditional logic in scheduled_gtec_v2_tick that:
    - When report_status == "INFRA_BLOCKED", events are kept queued
    - When report_status != "INFRA_BLOCKED", events are marked processed
    
    We test this by examining the code structure rather than full integration
    since the scheduler tick has complex async dependencies.
    """
    import inspect
    source = inspect.getsource(svc.scheduled_gtec_v2_tick)
    
    # Verify the INFRA_BLOCKED event preservation logic exists
    assert 'report_status == "INFRA_BLOCKED"' in source or "report_status == 'INFRA_BLOCKED'" in source
    assert '"status": "queued"' in source or "'status': 'queued'" in source
    assert '"last_skip_reason": "infra_blocked_preflight"' in source or "'last_skip_reason': 'infra_blocked_preflight'" in source
    
    # Verify the normal processing logic exists
    assert '"status": "processed"' in source or "'status': 'processed'" in source
    
    # Verify heartbeat records the blocked state
    assert "scan_blocked_preflight" in source


def test_scheduler_tick_heartbeat_reflects_infra_blocked():
    """Verify scheduler tick heartbeat correctly reflects INFRA_BLOCKED state."""
    import inspect
    source = inspect.getsource(svc.scheduled_gtec_v2_tick)
    
    # Verify heartbeat result distinguishes between completed and blocked
    assert 'scan_completed' in source
    assert 'scan_blocked_preflight' in source
    
    # Verify the conditional logic for heartbeat result
    assert 'if report_status != "INFRA_BLOCKED"' in source or "if report_status != 'INFRA_BLOCKED'" in source


# ============================================================================
# _run_with_restart_loop INFRA_BLOCKED TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_run_with_restart_loop_returns_infra_blocked_on_preflight_fail(monkeypatch):
    """_run_with_restart_loop returns INFRA_BLOCKED when preflight fails."""
    # Mock preflight to fail
    async def failing_preflight(**kwargs):
        return {
            "passed": False,
            "required_checks": 3,
            "attempts_completed": 1,
            "reasons": ["external_preview_unstable"],
            "attempts": [],
            "checked_at": "2026-01-15T00:00:00+00:00",
        }
    
    monkeypatch.setattr(svc, "run_scan_preflight_gate", failing_preflight)
    
    # Mock database operations
    mock_db = MagicMock()
    mock_db[svc.REPORTS_COL].insert_one = AsyncMock()
    mock_db[svc.LEGACY_REPORTS_COL].update_one = AsyncMock()
    mock_db[svc.REPORTS_COL].update_one = AsyncMock()
    mock_db[svc.LEGACY_REPORTS_COL].update_one = AsyncMock()
    mock_db[svc.INCIDENTS_COL].find = MagicMock(return_value=AsyncIteratorMock([]))
    
    # Mock build_c5_notification_snapshot
    async def mock_snapshot(db, report):
        return {"snapshot_version": "test", "source_task_id": report.get("task_id")}
    
    monkeypatch.setattr(svc, "build_c5_notification_snapshot", mock_snapshot)
    monkeypatch.setattr(svc, "apply_incident_auto_closure_policy", AsyncMock(return_value={}))
    
    result = await svc._run_with_restart_loop(
        mock_db,
        triggered_by="test",
        actor="test_actor",
        viewports="desktop",
        legacy_mirror_on=False,
    )
    
    assert result.get("status") == "INFRA_BLOCKED"
    assert result.get("preflight") is not None
    assert result.get("preflight", {}).get("passed") is False


@pytest.mark.asyncio
async def test_run_with_restart_loop_does_not_execute_scan_on_preflight_fail(monkeypatch):
    """_run_with_restart_loop does not execute full scan when preflight fails."""
    scan_executed = False
    
    async def failing_preflight(**kwargs):
        return {
            "passed": False,
            "required_checks": 3,
            "attempts_completed": 1,
            "reasons": ["local_backend_unstable"],
            "attempts": [],
            "checked_at": "2026-01-15T00:00:00+00:00",
        }
    
    async def mock_single_scan(*args, **kwargs):
        nonlocal scan_executed
        scan_executed = True
        return {"status": "PASS", "task_id": "test", "execution_hash": "hash"}
    
    monkeypatch.setattr(svc, "run_scan_preflight_gate", failing_preflight)
    monkeypatch.setattr(svc, "_single_scan_pass", mock_single_scan)
    
    # Mock database operations
    mock_db = MagicMock()
    mock_db[svc.REPORTS_COL].insert_one = AsyncMock()
    mock_db[svc.LEGACY_REPORTS_COL].update_one = AsyncMock()
    mock_db[svc.REPORTS_COL].update_one = AsyncMock()
    mock_db[svc.INCIDENTS_COL].find = MagicMock(return_value=AsyncIteratorMock([]))
    
    monkeypatch.setattr(svc, "build_c5_notification_snapshot", AsyncMock(return_value={}))
    monkeypatch.setattr(svc, "apply_incident_auto_closure_policy", AsyncMock(return_value={}))
    
    result = await svc._run_with_restart_loop(
        mock_db,
        triggered_by="test",
        actor="test_actor",
        viewports="desktop",
        legacy_mirror_on=False,
    )
    
    assert result.get("status") == "INFRA_BLOCKED"
    assert scan_executed is False  # Full scan should NOT have been executed


# ============================================================================
# NOTIFICATION SNAPSHOT FOR INFRA_BLOCKED
# ============================================================================

@pytest.mark.asyncio
async def test_c5_notification_snapshot_for_infra_blocked(monkeypatch):
    """build_c5_notification_snapshot handles INFRA_BLOCKED reports correctly."""
    # Mock database
    mock_db = MagicMock()
    monkeypatch.setattr(svc, "ensure_internal_collections_migrated", AsyncMock())
    
    report = {
        "task_id": "gtec_c5_blocked_test",
        "execution_hash": "hash_blocked",
        "status": "INFRA_BLOCKED",
        "generated_at": "2026-01-15T00:00:00+00:00",
        "preflight": {
            "passed": False,
            "required_checks": 3,
            "attempts_completed": 1,
            "reasons": ["external_preview_unstable"],
        },
    }
    
    snapshot = await svc.build_c5_notification_snapshot(mock_db, report)
    
    assert snapshot.get("source_task_id") == "gtec_c5_blocked_test"
    assert snapshot.get("data_freshness") == "INFRA_BLOCKED"
    assert snapshot.get("snapshot_status") == "INCOMPLETE"
    
    # Consistency should flag the issue
    consistency = snapshot.get("consistency") or {}
    assert consistency.get("passed") is False
    assert "scan_preflight_unstable" in (consistency.get("issues") or [])
    
    # External host certification should indicate skipped
    ext_cert = snapshot.get("external_host_certification") or {}
    assert ext_cert.get("status") == "skipped_preflight_unstable"
    
    # Fail reason summary should mention INFRA_BLOCKED
    fail_reason = snapshot.get("fail_reason_summary") or ""
    assert "INFRA_BLOCKED" in fail_reason


# ============================================================================
# HELPER CLASSES
# ============================================================================

class AsyncIteratorMock:
    """Mock async iterator for database cursors."""
    def __init__(self, items):
        self.items = items
        self.index = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


@pytest.mark.asyncio
async def test_hydrate_report_write_path_uses_snapshot_build_failed_fallback(monkeypatch):
    """hydrate_report_write_path writes fallback snapshot when snapshot build fails."""
    report = {
        "task_id": "gtec_c5_writepath_fallback",
        "execution_hash": "hash_writepath_fallback",
        "status": "FAIL",
        "generated_at": "2026-01-15T00:00:00+00:00",
        "sections": {},
    }

    monkeypatch.setattr(
        svc,
        "ensure_report_sections_complete",
        lambda r: (dict(r), False),
    )

    async def failing_snapshot(_db, _report):
        raise RuntimeError("snapshot builder failed")

    monkeypatch.setattr(svc, "build_c5_notification_snapshot", failing_snapshot)

    mock_db = MagicMock()
    mock_db[svc.REPORTS_COL].insert_one = AsyncMock()
    mock_db[svc.LEGACY_REPORTS_COL].update_one = AsyncMock()

    out = await svc.hydrate_report_write_path(mock_db, report, legacy_mirror_on=True)

    snapshot = out.get("c5_notification_snapshot") or {}
    assert snapshot.get("snapshot_status") == "INCOMPLETE"
    assert snapshot.get("data_freshness") == "STALE_OR_PARTIAL"
    assert "snapshot_build_failed_write_path" in ((snapshot.get("consistency") or {}).get("issues") or [])
    assert snapshot.get("source_task_id") == "gtec_c5_writepath_fallback"

    mock_db[svc.REPORTS_COL].insert_one.assert_awaited_once()
    mock_db[svc.LEGACY_REPORTS_COL].update_one.assert_awaited_once()
