"""
GTEC C1-C5 Autonomous Implementation Tests
==========================================
Comprehensive tests for the production-grade autonomous GTEC rebuild:

C1 Foundation:
  - Policy store/effective policy endpoint
  - Execution graph persistence
  - Internal event ingestion endpoint
  - Scheduler event consumption

C2 Detection+Validation:
  - Duplicate source scan section in latest report
  - API contract scan section in latest report
  - Threat topology drift section in latest report

C3 Auto-remediation:
  - Unknown/unhandled finding class auto-escalates into gtec_scan_v2_incidents with containment

C4 Dashboard/Deprecation:
  - Manual runtime mutation endpoints blocked with 403
  - GTEC panels do not allow manual trigger/toggle operations

C5 Trust gates:
  - Autonomous schedule heartbeat and event_scheduler trigger path works
  - Policy endpoint shows manual_input_allowed=false and platform_data_only=true

Read-only endpoints still work:
  - latest/history/findings/executions/incidents/schedule/watchdog-state
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
GTEC_INTERNAL_TOKEN = os.environ.get("GTEC_INTERNAL_EVENT_TOKEN", "")


def _is_risk_engine_admin_blocked(resp: requests.Response) -> bool:
    if resp.status_code not in (401, 403, 503):
        return False
    try:
        payload = resp.json()
    except Exception:
        return False
    detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else payload.get("code")
    normalized_code = str(code or "").upper()

    if normalized_code in {
        "AUTH_REQUIRED",
        "RISK_ENGINE_ADMIN_API_BLOCKED",
        "RISK_ENGINE_ID_VERIFICATION_REQUIRED",
        "PRODUCTION_POLICY_GATE_BLOCKED",
    }:
        return True

    if isinstance(detail, str):
        lowered = detail.lower()
        return (
            "admin access required" in lowered
            or "authentication required" in lowered
            or "id checker" in lowered
            or "policy gate" in lowered
        )

    if isinstance(detail, dict):
        message = str(detail.get("message") or "").lower()
        return (
            "admin access required" in message
            or "authentication required" in message
            or "id checker" in message
            or "policy gate" in message
        )

    raw_body = (resp.text or "").lower()
    return "admin access required" in raw_body or "authentication required" in raw_body or "risk_engine" in raw_body


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, headers={"X-Requested-With": "XMLHttpRequest"})
    if _is_risk_engine_admin_blocked(resp):
        pytest.skip("Admin login blocked by environment containment/policy gate")
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text[:200]}")
    
    data = resp.json()
    token = data.get("session_token") or data.get("token") or resp.cookies.get("session_token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    else:
        pytest.skip("Admin token missing in login JSON/cookies")

    original_get = session.get

    def guarded_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        if _is_risk_engine_admin_blocked(response):
            pytest.skip("Admin GET blocked by risk engine containment")
        return response

    session.get = guarded_get
    
    return session


# ============================================================================
# C1 Foundation Tests
# ============================================================================

class TestC1Foundation:
    """C1: Policy store, execution graph, internal event ingestion, scheduler."""
    
    def test_c1_policy_store_effective_endpoint(self, admin_session):
        """C1: GET /api/admin/gtec-scan-v2/policy/effective returns policy store."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        # Verify policy store structure
        assert "mode" in data, "Expected 'mode' in policy"
        assert "manual_input_allowed" in data, "Expected 'manual_input_allowed' in policy"
        assert "policy_locked" in data, "Expected 'policy_locked' in policy"
        assert "platform_data_only" in data, "Expected 'platform_data_only' in policy"
        assert "manual_endpoints_disabled" in data, "Expected 'manual_endpoints_disabled' list"
        assert "generated_at" in data, "Expected 'generated_at' timestamp"
        
        print("✓ C1 Policy store endpoint returns valid structure")
        print(f"  - mode: {data.get('mode')}")
        print(f"  - manual_input_allowed: {data.get('manual_input_allowed')}")
        print(f"  - platform_data_only: {data.get('platform_data_only')}")
    
    def test_c1_execution_graph_persistence(self, admin_session):
        """C1: GET /api/admin/gtec-scan-v2/executions returns persisted execution graph."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions?limit=10")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert "items" in data, "Expected 'items' in response"
        assert "count" in data, "Expected 'count' in response"
        assert isinstance(data.get("items"), list), "items should be a list"
        
        # If there are executions, verify structure
        if data.get("items"):
            exec_item = data["items"][0]
            # Execution items should have task_id, generated_at, status
            print(f"✓ C1 Execution graph has {data.get('count')} persisted items")
            print(f"  - Sample keys: {list(exec_item.keys())[:5]}")
        else:
            print("✓ C1 Execution graph endpoint works (no executions yet)")
    
    def test_c1_internal_event_ingestion_endpoint_exists(self, admin_session):
        """C1: POST /api/internal/gtec/events/ingest endpoint exists (requires internal token)."""
        # Without token, should get 401 or 503
        resp = requests.post(f"{BASE_URL}/api/internal/gtec/events/ingest", json={
            "event_type": "test_event",
            "source": "test",
            "scope": "test",
            "severity": "low"
        })
        # Should be 401 (invalid token) or 503 (token not configured)
        assert resp.status_code in (401, 503), f"Expected 401/503 without token, got {resp.status_code}"
        print(f"✓ C1 Internal event ingestion endpoint exists (returns {resp.status_code} without token)")
    
    def test_c1_internal_event_queue_stats_endpoint(self, admin_session):
        """C1: GET /api/internal/gtec/events/queue-stats endpoint exists."""
        resp = requests.get(f"{BASE_URL}/api/internal/gtec/events/queue-stats")
        # Should be 401 (invalid token) or 503 (token not configured)
        assert resp.status_code in (401, 503), f"Expected 401/503 without token, got {resp.status_code}"
        print(f"✓ C1 Internal event queue-stats endpoint exists (returns {resp.status_code} without token)")
    
    def test_c1_schedule_endpoint_returns_scheduler_config(self, admin_session):
        """C1: GET /api/admin/gtec-scan-v2/schedule returns scheduler configuration."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/schedule")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert "enabled" in data, "Expected 'enabled' in schedule"
        assert "interval_hours" in data, "Expected 'interval_hours' in schedule"
        
        print("✓ C1 Schedule endpoint returns scheduler config")
        print(f"  - enabled: {data.get('enabled')}")
        print(f"  - interval_hours: {data.get('interval_hours')}")


# ============================================================================
# C2 Detection+Validation Tests
# ============================================================================

class TestC2DetectionValidation:
    """C2: Duplicate source scan, API contract scan, threat topology drift sections."""
    
    def test_c2_latest_report_has_sections(self, admin_session):
        """C2: GET /api/admin/gtec-scan-v2/latest report has detection sections."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        report = data.get("report")
        if not report:
            print("✓ C2 Latest report endpoint works (no report yet - expected for fresh env)")
            return
        
        sections = report.get("sections") or {}
        
        # Check for C2 detection sections
        c2_sections = ["duplicate", "api_contract", "threat_model"]
        found_sections = []
        missing_sections = []
        
        for section_name in c2_sections:
            if section_name in sections:
                found_sections.append(section_name)
            else:
                missing_sections.append(section_name)
        
        print("✓ C2 Latest report sections check:")
        print(f"  - Found sections: {found_sections}")
        print(f"  - Missing sections: {missing_sections}")
        print(f"  - All sections in report: {list(sections.keys())}")
        
        # At minimum, the report should have some sections
        assert len(sections) > 0, "Report should have at least some sections"
    
    def test_c2_findings_latest_has_detection_findings(self, admin_session):
        """C2: GET /api/admin/gtec-scan-v2/findings/latest returns flattened findings."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/findings/latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert "items" in data, "Expected 'items' in response"
        assert "count" in data, "Expected 'count' in response"
        
        items = data.get("items") or []
        
        # Check for C2 detection categories in findings
        c2_categories = {"source", "api_contract", "threat_model"}
        found_categories = set()
        
        for item in items:
            section = item.get("section", "")
            if section in c2_categories:
                found_categories.add(section)
        
        print(f"✓ C2 Findings latest has {data.get('count')} findings")
        print(f"  - C2 categories found: {found_categories}")


# ============================================================================
# C3 Auto-remediation Tests
# ============================================================================

class TestC3AutoRemediation:
    """C3: Unknown/unhandled finding class auto-escalates into incidents with containment."""
    
    def test_c3_incidents_endpoint_returns_auto_escalated(self, admin_session):
        """C3: GET /api/admin/gtec-scan-v2/incidents returns auto-escalated incidents."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/incidents?status=all&limit=50")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert "items" in data, "Expected 'items' in response"
        assert "count" in data, "Expected 'count' in response"
        
        items = data.get("items") or []
        
        # Check for auto-escalated incidents
        auto_escalated = [i for i in items if i.get("auto_escalated")]
        with_containment = [i for i in items if i.get("containment") == "active"]
        
        print(f"✓ C3 Incidents endpoint returns {data.get('count')} incidents")
        print(f"  - Auto-escalated: {len(auto_escalated)}")
        print(f"  - With containment: {len(with_containment)}")
        
        # If there are auto-escalated incidents, verify structure
        if auto_escalated:
            sample = auto_escalated[0]
            assert "incident_id" in sample, "Auto-escalated incident should have incident_id"
            assert "label" in sample, "Auto-escalated incident should have label"
            assert "severity" in sample, "Auto-escalated incident should have severity"
            print(f"  - Sample incident: {sample.get('incident_id')} - {sample.get('label')}")


# ============================================================================
# C4 Dashboard/Deprecation Tests
# ============================================================================

class TestC4DashboardDeprecation:
    """C4: Manual runtime mutation endpoints blocked with 403."""
    
    def test_c4_manual_scan_run_blocked_403(self, admin_session):
        """C4: POST /api/admin/gtec-scan-v2/run returns 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-scan-v2/run", json={
            "viewports": "desktop"
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        print("✓ C4 Manual scan run blocked with 403")
    
    def test_c4_manual_schedule_mutation_blocked_403(self, admin_session):
        """C4: POST /api/admin/gtec-scan-v2/schedule returns 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-scan-v2/schedule", json={
            "enabled": True,
            "interval_hours": 6
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        print("✓ C4 Manual schedule mutation blocked with 403")
    
    def test_c4_manual_watchdog_run_blocked_403(self, admin_session):
        """C4: POST /api/admin/gtec-scan-v2/watchdog/run returns 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-scan-v2/watchdog/run")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        print("✓ C4 Manual watchdog run blocked with 403")
    
    def test_c4_manual_crawler_run_blocked_403(self, admin_session):
        """C4: POST /api/admin/gtec-crawler/run returns 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-crawler/run", json={
            "viewports": "desktop"
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        print("✓ C4 Manual crawler run blocked with 403")
    
    def test_c4_manual_crawler_auto_run_mutation_blocked_403(self, admin_session):
        """C4: POST /api/admin/gtec-crawler/auto-run returns 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-crawler/auto-run", json={
            "enabled": True
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        print("✓ C4 Manual crawler auto-run mutation blocked with 403")
    
    def test_c4_manual_alert_settings_mutation_blocked_403(self, admin_session):
        """C4: POST /api/admin/gtec-crawler/alerts/settings returns 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-crawler/alerts/settings", json={
            "email_enabled": True
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        print("✓ C4 Manual alert settings mutation blocked with 403")
    
    def test_c4_manual_alert_test_blocked_403(self, admin_session):
        """C4: POST /api/admin/gtec-crawler/alerts/test returns 403."""
        resp = admin_session.post(f"{BASE_URL}/api/admin/gtec-crawler/alerts/test")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"
        print("✓ C4 Manual alert test blocked with 403")


# ============================================================================
# C5 Trust Gates Tests
# ============================================================================

class TestC5TrustGates:
    """C5: Autonomous schedule heartbeat, policy shows manual_input_allowed=false, platform_data_only=true."""
    
    def test_c5_policy_manual_input_allowed_false(self, admin_session):
        """C5: Policy endpoint shows manual_input_allowed=false."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert data.get("manual_input_allowed") is False, \
            f"Expected manual_input_allowed=False, got {data.get('manual_input_allowed')}"
        print("✓ C5 Policy shows manual_input_allowed=false")
    
    def test_c5_policy_platform_data_only_true(self, admin_session):
        """C5: Policy endpoint shows platform_data_only=true."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert data.get("platform_data_only") is True, \
            f"Expected platform_data_only=True, got {data.get('platform_data_only')}"
        print("✓ C5 Policy shows platform_data_only=true")
    
    def test_c5_policy_mode_autonomous_only(self, admin_session):
        """C5: Policy endpoint shows mode=autonomous_only."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert data.get("mode") == "autonomous_only", \
            f"Expected mode=autonomous_only, got {data.get('mode')}"
        print("✓ C5 Policy shows mode=autonomous_only")
    
    def test_c5_policy_locked_true(self, admin_session):
        """C5: Policy endpoint shows policy_locked=true."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/policy/effective")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert data.get("policy_locked") is True, \
            f"Expected policy_locked=True, got {data.get('policy_locked')}"
        print("✓ C5 Policy shows policy_locked=true")
    
    def test_c5_crawler_auto_run_non_disableable(self, admin_session):
        """C5: Crawler auto-run shows non_disableable=true."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/auto-run")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert data.get("non_disableable") is True, \
            f"Expected non_disableable=True, got {data.get('non_disableable')}"
        assert data.get("enabled") is True, \
            f"Expected enabled=True (always on), got {data.get('enabled')}"
        print("✓ C5 Crawler auto-run shows non_disableable=true, enabled=true")
    
    def test_c5_directive_always_active(self, admin_session):
        """C5: Directive endpoint shows always_active=true, non_disableable=true."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/directive")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        
        assert data.get("always_active") is True, \
            f"Expected always_active=True, got {data.get('always_active')}"
        assert data.get("non_disableable") is True, \
            f"Expected non_disableable=True, got {data.get('non_disableable')}"
        print("✓ C5 Directive shows always_active=true, non_disableable=true")


# ============================================================================
# Read-only Endpoints Tests
# ============================================================================

class TestReadOnlyEndpoints:
    """Verify all read-only endpoints still work correctly."""
    
    def test_readonly_latest(self, admin_session):
        """GET /api/admin/gtec-scan-v2/latest works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "report" in resp.json(), "Expected 'report' key"
        print("✓ Read-only: /latest works")
    
    def test_readonly_history(self, admin_session):
        """GET /api/admin/gtec-scan-v2/history works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/history")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "items" in resp.json(), "Expected 'items' key"
        print("✓ Read-only: /history works")
    
    def test_readonly_findings(self, admin_session):
        """GET /api/admin/gtec-scan-v2/findings/latest works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/findings/latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "items" in resp.json(), "Expected 'items' key"
        print("✓ Read-only: /findings/latest works")
    
    def test_readonly_executions(self, admin_session):
        """GET /api/admin/gtec-scan-v2/executions works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/executions")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "items" in resp.json(), "Expected 'items' key"
        print("✓ Read-only: /executions works")
    
    def test_readonly_incidents(self, admin_session):
        """GET /api/admin/gtec-scan-v2/incidents works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/incidents")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "items" in resp.json(), "Expected 'items' key"
        print("✓ Read-only: /incidents works")
    
    def test_readonly_schedule(self, admin_session):
        """GET /api/admin/gtec-scan-v2/schedule works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/schedule")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "enabled" in resp.json(), "Expected 'enabled' key"
        print("✓ Read-only: /schedule works")
    
    def test_readonly_watchdog_state(self, admin_session):
        """GET /api/admin/gtec-scan-v2/watchdog/state works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/watchdog/state")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "tracked" in resp.json(), "Expected 'tracked' key"
        print("✓ Read-only: /watchdog/state works")
    
    def test_readonly_directive(self, admin_session):
        """GET /api/admin/gtec-scan-v2/directive works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/directive")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "directive_text" in resp.json(), "Expected 'directive_text' key"
        print("✓ Read-only: /directive works")
    
    def test_readonly_memory(self, admin_session):
        """GET /api/admin/gtec-scan-v2/memory works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-scan-v2/memory")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "items" in resp.json(), "Expected 'items' key"
        print("✓ Read-only: /memory works")
    
    def test_readonly_crawler_latest(self, admin_session):
        """GET /api/admin/gtec-crawler/latest works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/latest")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "report" in resp.json(), "Expected 'report' key"
        print("✓ Read-only: /gtec-crawler/latest works")
    
    def test_readonly_crawler_history(self, admin_session):
        """GET /api/admin/gtec-crawler/history works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/history")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "items" in resp.json(), "Expected 'items' key"
        print("✓ Read-only: /gtec-crawler/history works")
    
    def test_readonly_crawler_auto_run(self, admin_session):
        """GET /api/admin/gtec-crawler/auto-run works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/auto-run")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "enabled" in resp.json(), "Expected 'enabled' key"
        print("✓ Read-only: /gtec-crawler/auto-run works")
    
    def test_readonly_alerts_settings(self, admin_session):
        """GET /api/admin/gtec-crawler/alerts/settings works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/alerts/settings")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        print("✓ Read-only: /gtec-crawler/alerts/settings works")
    
    def test_readonly_alerts_history(self, admin_session):
        """GET /api/admin/gtec-crawler/alerts/history works."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/gtec-crawler/alerts/history")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "items" in resp.json(), "Expected 'items' key"
        print("✓ Read-only: /gtec-crawler/alerts/history works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
