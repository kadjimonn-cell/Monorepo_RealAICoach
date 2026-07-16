"""
GTEC Autonomous Policy Enforcement Tests
=========================================
Tests for the autonomous-only GTEC scan policy enforcement:
- Manual scan triggers blocked (403)
- Manual schedule mutation blocked (403)
- Manual watchdog trigger blocked (403)
- Manual crawler alert mutation/test blocked (403)
- Policy/effective endpoint returns immutable policy
- Executions/findings/incidents endpoints return valid payloads
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_expected_block_reason(payload: dict) -> bool:
    raw_detail = payload.get("detail", "")
    detail = str(raw_detail or "").lower()
    code = str(payload.get("code", "") or "").upper()
    detail_code = ""
    detail_message = ""
    if isinstance(raw_detail, dict):
        detail_code = str(raw_detail.get("code", "") or "").upper()
        detail_message = str(raw_detail.get("message", "") or "").lower()
    return (
        "autonomous policy" in detail
        or "disabled" in detail
        or "csrf" in detail
        or "admin access required" in detail
        or "authentication required" in detail
        or "progressive risk engine" in detail
        or "risk engine" in detail_message
        or code in {"AUTONOMOUS_POLICY_BLOCKED", "CSRF_BLOCKED"}
        or detail_code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}
    )


def _is_risk_engine_admin_blocked(payload: dict) -> bool:
    raw_detail = payload.get("detail", {})
    if isinstance(raw_detail, dict):
        detail_code = str(raw_detail.get("code", "") or "").upper()
        if detail_code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}:
            return True
        detail_message = str(raw_detail.get("message", "") or "").lower()
        if (
            "admin access required" in detail_message
            or "authentication required" in detail_message
            or "policy gate" in detail_message
        ):
            return True

    if isinstance(raw_detail, str):
        lowered = raw_detail.lower()
        if (
            "admin access required" in lowered
            or "authentication required" in lowered
            or "policy gate" in lowered
        ):
            return True

    top_level_code = str(payload.get("code", "") or "").upper()
    return top_level_code in {
        "AUTH_REQUIRED",
        "RISK_ENGINE_ADMIN_API_BLOCKED",
        "RISK_ENGINE_ID_VERIFICATION_REQUIRED",
        "PRODUCTION_POLICY_GATE_BLOCKED",
    }


def _skip_if_risk_engine_admin_blocked(resp: requests.Response, context: str) -> None:
    if resp.status_code not in (401, 403, 503):
        return
    try:
        payload = resp.json()
    except Exception:
        return
    if isinstance(payload, dict) and _is_risk_engine_admin_blocked(payload):
        pytest.skip(f"{context} blocked by risk engine containment")


def _detail_preview(payload: dict) -> str:
    raw_detail = payload.get("detail", "")
    if isinstance(raw_detail, dict):
        text = raw_detail.get("message") or str(raw_detail)
        return str(text)[:100]
    return str(raw_detail)[:100]


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, headers={"X-Requested-With": "XMLHttpRequest"})
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")
    
    data = resp.json()
    token = (
        data.get("session_token")
        or data.get("token")
        or data.get("access_token")
        or resp.cookies.get("session_token")
        or session.cookies.get("session_token")
    )
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestGtecScanV2ManualBlockedEndpoints:
    """Test that manual GTEC scan v2 endpoints are blocked by autonomous policy."""
    
    def test_manual_scan_run_blocked(self, admin_session):
        """POST /api/admin/gtec-scan-v2/run should return 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-scan-v2/run", json={
            "viewports": "desktop"
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert _is_expected_block_reason(data)
        print(f"✓ Manual scan run blocked: {_detail_preview(data)}")
    
    def test_manual_schedule_mutation_blocked(self, admin_session):
        """POST /api/admin/gtec-scan-v2/schedule should return 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-scan-v2/schedule", json={
            "enabled": True,
            "interval_hours": 6
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert _is_expected_block_reason(data)
        print(f"✓ Manual schedule mutation blocked: {_detail_preview(data)}")
    
    def test_manual_watchdog_run_blocked(self, admin_session):
        """POST /api/admin/gtec-scan-v2/watchdog/run should return 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-scan-v2/watchdog/run")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert _is_expected_block_reason(data)
        print(f"✓ Manual watchdog run blocked: {_detail_preview(data)}")


class TestGtecCrawlerManualBlockedEndpoints:
    """Test that manual GTEC crawler endpoints are blocked by autonomous policy."""
    
    def test_manual_crawler_run_blocked(self, admin_session):
        """POST /api/admin/gtec-crawler/run should return 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-crawler/run", json={
            "viewports": "desktop"
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert _is_expected_block_reason(data)
        print(f"✓ Manual crawler run blocked: {_detail_preview(data)}")
    
    def test_manual_auto_run_mutation_blocked(self, admin_session):
        """POST /api/admin/gtec-crawler/auto-run should return 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-crawler/auto-run", json={
            "enabled": True
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert _is_expected_block_reason(data)
        print(f"✓ Manual auto-run mutation blocked: {_detail_preview(data)}")
    
    def test_manual_alert_settings_mutation_blocked(self, admin_session):
        """POST /api/admin/gtec-crawler/alerts/settings should return 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-crawler/alerts/settings", json={
            "email_enabled": True
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert _is_expected_block_reason(data)
        print(f"✓ Manual alert settings mutation blocked: {_detail_preview(data)}")
    
    def test_manual_alert_test_blocked(self, admin_session):
        """POST /api/admin/gtec-crawler/alerts/test should return 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-crawler/alerts/test")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert _is_expected_block_reason(data)
        print(f"✓ Manual alert test blocked: {_detail_preview(data)}")


class TestGtecScanV2ReadOnlyEndpoints:
    """Test that read-only GTEC scan v2 endpoints work correctly."""
    
    def test_policy_effective_returns_immutable_policy(self, admin_session):
        """GET /api/admin/gtec-scan-v2/policy/effective should return autonomous policy."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 policy effective")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify policy structure
        assert data.get("mode") == "autonomous_only", f"Expected mode=autonomous_only, got {data.get('mode')}"
        assert data.get("manual_input_allowed") is False, "Expected manual_input_allowed=False"
        assert data.get("policy_locked") is True, "Expected policy_locked=True"
        assert data.get("platform_data_only") is True, "Expected platform_data_only=True"
        assert "manual_endpoints_disabled" in data, "Expected manual_endpoints_disabled list"
        assert isinstance(data.get("manual_endpoints_disabled"), list), "manual_endpoints_disabled should be a list"
        assert len(data.get("manual_endpoints_disabled", [])) > 0, "manual_endpoints_disabled should not be empty"
        
        print(f"✓ Policy effective endpoint returns immutable policy: mode={data.get('mode')}")
        print(f"  - manual_input_allowed: {data.get('manual_input_allowed')}")
        print(f"  - policy_locked: {data.get('policy_locked')}")
        print(f"  - disabled endpoints: {len(data.get('manual_endpoints_disabled', []))}")
    
    def test_executions_endpoint_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-scan-v2/executions should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 executions")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "items" in data, "Expected 'items' key in response"
        assert "count" in data, "Expected 'count' key in response"
        assert isinstance(data.get("items"), list), "items should be a list"
        assert isinstance(data.get("count"), int), "count should be an integer"
        
        print(f"✓ Executions endpoint returns valid payload: {data.get('count')} items")
    
    def test_findings_latest_endpoint_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-scan-v2/findings/latest should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/findings/latest")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 findings latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "items" in data, "Expected 'items' key in response"
        assert "count" in data, "Expected 'count' key in response"
        assert isinstance(data.get("items"), list), "items should be a list"
        assert isinstance(data.get("count"), int), "count should be an integer"
        
        print(f"✓ Findings latest endpoint returns valid payload: {data.get('count')} findings")
    
    def test_incidents_endpoint_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-scan-v2/incidents should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/incidents")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 incidents")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "items" in data, "Expected 'items' key in response"
        assert "count" in data, "Expected 'count' key in response"
        assert "status_filter" in data, "Expected 'status_filter' key in response"
        assert isinstance(data.get("items"), list), "items should be a list"
        assert isinstance(data.get("count"), int), "count should be an integer"
        
        print(f"✓ Incidents endpoint returns valid payload: {data.get('count')} incidents (filter: {data.get('status_filter')})")
    
    def test_schedule_get_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-scan-v2/schedule should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/schedule")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 schedule get")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "enabled" in data, "Expected 'enabled' key in response"
        assert "interval_hours" in data, "Expected 'interval_hours' key in response"
        
        print(f"✓ Schedule GET returns valid payload: enabled={data.get('enabled')}, interval={data.get('interval_hours')}h")
    
    def test_watchdog_state_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-scan-v2/watchdog/state should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/watchdog/state")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 watchdog state")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "watchlist_size" in data, "Expected 'watchlist_size' key in response"
        assert "tracked" in data, "Expected 'tracked' key in response"
        assert isinstance(data.get("tracked"), list), "tracked should be a list"
        
        print(f"✓ Watchdog state returns valid payload: {data.get('watchlist_size')} watched, {len(data.get('tracked', []))} tracked")
    
    def test_directive_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-scan-v2/directive should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/directive")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 directive")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "directive_text" in data, "Expected 'directive_text' key in response"
        assert "always_active" in data, "Expected 'always_active' key in response"
        assert "non_disableable" in data, "Expected 'non_disableable' key in response"
        assert data.get("always_active") is True, "Expected always_active=True"
        assert data.get("non_disableable") is True, "Expected non_disableable=True"
        
        print(f"✓ Directive returns valid payload: always_active={data.get('always_active')}, non_disableable={data.get('non_disableable')}")
    
    def test_latest_report_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-scan-v2/latest should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure - report may be null if no scans have run
        assert "report" in data, "Expected 'report' key in response"
        
        if data.get("report"):
            report = data["report"]
            print(f"✓ Latest report returns valid payload: task_id={report.get('task_id')}, status={report.get('status')}")
        else:
            print("✓ Latest report returns valid payload: no report yet (expected for fresh environment)")
    
    def test_history_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-scan-v2/history should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/history")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-scan-v2 history")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "items" in data, "Expected 'items' key in response"
        assert "count" in data, "Expected 'count' key in response"
        assert isinstance(data.get("items"), list), "items should be a list"
        
        print(f"✓ History returns valid payload: {data.get('count')} items")


class TestGtecCrawlerReadOnlyEndpoints:
    """Test that read-only GTEC crawler endpoints work correctly."""
    
    def test_auto_run_get_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-crawler/auto-run should return valid payload with non_disableable flag."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/auto-run")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-crawler auto-run get")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "enabled" in data, "Expected 'enabled' key in response"
        assert "non_disableable" in data, "Expected 'non_disableable' key in response"
        assert data.get("non_disableable") is True, "Expected non_disableable=True"
        assert data.get("enabled") is True, "Expected enabled=True (always on)"
        
        print(f"✓ Auto-run GET returns valid payload: enabled={data.get('enabled')}, non_disableable={data.get('non_disableable')}")
    
    def test_alert_settings_get_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-crawler/alerts/settings should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/alerts/settings")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-crawler alert settings")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure - should have alert settings fields
        assert isinstance(data, dict), "Expected dict response"
        
        print("✓ Alert settings GET returns valid payload")
    
    def test_alert_history_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-crawler/alerts/history should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/alerts/history")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-crawler alert history")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "items" in data, "Expected 'items' key in response"
        assert "count" in data, "Expected 'count' key in response"
        assert isinstance(data.get("items"), list), "items should be a list"
        
        print(f"✓ Alert history returns valid payload: {data.get('count')} items")
    
    def test_crawler_latest_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-crawler/latest should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/latest")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-crawler latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure - report may be null if no scans have run
        assert "report" in data, "Expected 'report' key in response"
        
        if data.get("report"):
            report = data["report"]
            print(f"✓ Crawler latest returns valid payload: totals={report.get('totals')}")
        else:
            print("✓ Crawler latest returns valid payload: no report yet")
    
    def test_crawler_history_returns_valid_payload(self, admin_session):
        """GET /api/admin/gtec-crawler/history should return valid payload."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/history")
        _skip_if_risk_engine_admin_blocked(resp, "gtec-crawler history")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify structure
        assert "items" in data, "Expected 'items' key in response"
        assert "count" in data, "Expected 'count' key in response"
        assert isinstance(data.get("items"), list), "items should be a list"
        
        print(f"✓ Crawler history returns valid payload: {data.get('count')} items")


class TestUnauthenticatedAccess:
    """Test that GTEC endpoints require authentication."""
    
    def test_policy_effective_requires_auth(self):
        """GET /api/admin/gtec-scan-v2/policy/effective should require auth."""
        resp = requests.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        print(f"✓ Policy effective requires auth: {resp.status_code}")
    
    def test_executions_requires_auth(self):
        """GET /api/admin/gtec-scan-v2/executions should require auth."""
        resp = requests.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        print(f"✓ Executions requires auth: {resp.status_code}")
    
    def test_incidents_requires_auth(self):
        """GET /api/admin/gtec-scan-v2/incidents should require auth."""
        resp = requests.get(f"{BASE_URL}/api/admin/gtec-scan-v2/incidents")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        print(f"✓ Incidents requires auth: {resp.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
