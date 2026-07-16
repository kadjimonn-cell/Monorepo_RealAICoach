from __future__ import annotations

import sys

import pytest

sys.path.append("/app/backend")

from services import gtec_scan_v2 as svc


@pytest.mark.asyncio
async def test_preflight_gate_passes_when_local_and_external_stable(monkeypatch):
    async def fake_local():
        return {"ok": True, "status_code": 200, "base_url": "http://127.0.0.1:8001"}

    async def fake_external(_base_url=None, **_kwargs):
        return {"stable": True, "checks": []}

    monkeypatch.setattr(svc, "_probe_local_backend_health", fake_local)
    monkeypatch.setattr(svc, "get_external_host_proxy_health", fake_external)

    result = await svc.run_scan_preflight_gate(required_checks=3)
    assert result.get("passed") is True
    assert result.get("attempts_completed") == 3
    assert result.get("reasons") == []


@pytest.mark.asyncio
async def test_preflight_gate_fails_fast_on_unstable_preview(monkeypatch):
    async def fake_local():
        return {"ok": True, "status_code": 200, "base_url": "http://127.0.0.1:8001"}

    async def fake_external(_base_url=None, **_kwargs):
        return {"stable": False, "checks": [{"path": "/_preview/health", "ok": False}]}

    monkeypatch.setattr(svc, "_probe_local_backend_health", fake_local)
    monkeypatch.setattr(svc, "get_external_host_proxy_health", fake_external)

    result = await svc.run_scan_preflight_gate(required_checks=3)
    assert result.get("passed") is False
    assert result.get("attempts_completed") == 1
    assert "external_preview_unstable" in (result.get("reasons") or [])


@pytest.mark.asyncio
async def test_external_proxy_health_retries_429_as_transient(monkeypatch):
    """External proxy health must treat 429 as transient retry candidate."""

    class _FakeResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

    seen_calls = []

    async def fake_probe(_cli, _method, url, **kwargs):
        seen_calls.append({"url": url, **kwargs})
        if url.endswith("/_preview/health"):
            return _FakeResponse(200, '{"ok":true}'), None
        return _FakeResponse(200, "<html>login page</html>"), None

    monkeypatch.setattr(svc, "_probe_with_transient_retry", fake_probe)

    result = await svc.get_external_host_proxy_health("https://coach-web-preview.preview.emergentagent.com")
    checks = result.get("checks") or []
    preview = next((c for c in checks if c.get("path") == "/_preview/health"), {})

    assert result.get("stable") is True
    assert preview.get("ok") is True
    assert preview.get("status_code") == 200

    # ensure retry helper is invoked with 429 as transient for preflight endpoint probes
    assert seen_calls, "Expected _probe_with_transient_retry to be called"
    for call in seen_calls:
        assert call.get("attempts") == svc.SCAN_PREFLIGHT_ENDPOINT_RETRY_ATTEMPTS
        transient = tuple(call.get("transient_statuses") or ())
        assert 429 in transient


@pytest.mark.asyncio
async def test_external_proxy_health_marks_unstable_when_429_persists(monkeypatch):
    """If probe repeatedly gets 429, preflight external check should remain unstable."""

    class _FakeResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

    async def fake_probe(_cli, _method, url, **_kwargs):
        if url.endswith("/_preview/health"):
            return _FakeResponse(429, "rate limited"), None
        return _FakeResponse(429, "rate limited"), None

    monkeypatch.setattr(svc, "_probe_with_transient_retry", fake_probe)

    result = await svc.get_external_host_proxy_health("https://coach-web-preview.preview.emergentagent.com")
    checks = result.get("checks") or []
    preview = next((c for c in checks if c.get("path") == "/_preview/health"), {})

    assert result.get("stable") is False
    assert preview.get("status_code") == 429
    assert preview.get("ok") is False


def test_infra_blocked_report_contains_expected_markers():
    preflight = {
        "required_checks": 3,
        "attempts_completed": 1,
        "reasons": ["external_preview_unstable"],
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

    assert report.get("status") == "INFRA_BLOCKED"
    assert report.get("high_vulns") == 1
    assert "runtime preflight" in str(report.get("summary") or "").lower()
    fail_reason = svc._build_fail_reason_summary(report)
    assert "INFRA_BLOCKED because" in fail_reason
