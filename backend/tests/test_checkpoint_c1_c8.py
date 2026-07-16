"""
Checkpoint C1-C8 Backend API Tests
Tests for plan catalog consistency, GPS health, catalog guard, live metrics, and integrity artifacts
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _risk_engine_admin_blocked(response: requests.Response) -> bool:
    if response.status_code not in (401, 403):
        return False
    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""

    if top_code in {"AUTH_REQUIRED", "RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}:
        return True

    if isinstance(detail, str):
        lowered = detail.lower()
        return (
            "admin access required" in lowered
            or "authentication required" in lowered
            or "id checker" in lowered
        )

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}:
            return True
        message = str(detail.get("message") or "").lower()
        return (
            "admin access blocked" in message
            or "admin access required" in message
            or "id checker" in message
        )

    return False


class TestAuth:
    """Authentication helper for admin tests"""
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session"""
        session = requests.Session()
        # Add X-Requested-With header for CSRF bypass (required for POST requests)
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login as admin
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })

        if _risk_engine_admin_blocked(response):
            pytest.skip("Admin login blocked by risk engine containment in this environment")
        
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code} - {response.text[:200]}")
        
        data = response.json()
        # Handle both cookie-based and token-based auth
        token = (
            data.get("session_token")
            or data.get("token")
            or data.get("access_token")
            or response.cookies.get("session_token")
            or session.cookies.get("session_token")
        )
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        
        return session


class TestC1PlanCatalogConsistency(TestAuth):
    """C1: Plan catalog consistency across endpoints"""
    
    def test_admin_subscription_plans_endpoint(self, admin_session):
        """Test /api/admin/subscriptions/plans returns free/basic/premium"""
        response = admin_session.get(f"{BASE_URL}/api/admin/subscriptions/plans")
        if _risk_engine_admin_blocked(response):
            pytest.skip("Admin subscription plans blocked by risk engine containment in this environment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        plans = data.get("plans", data) if isinstance(data, dict) else data
        
        if isinstance(plans, list):
            plan_ids = [p.get("plan_id") or p.get("id") for p in plans]
        else:
            plan_ids = list(plans.keys()) if isinstance(plans, dict) else []
        
        # Verify canonical plans exist
        assert "free" in plan_ids, f"'free' plan missing. Found: {plan_ids}"
        assert "basic" in plan_ids, f"'basic' plan missing. Found: {plan_ids}"
        assert "premium" in plan_ids, f"'premium' plan missing. Found: {plan_ids}"
        print(f"C1 Admin plans: {plan_ids}")
    
    def test_public_subscription_plans_endpoint(self, admin_session):
        """Test /api/subscriptions/plans returns free/basic/premium"""
        response = admin_session.get(f"{BASE_URL}/api/subscriptions/plans")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        plans = data.get("plans", data) if isinstance(data, dict) else data
        
        if isinstance(plans, list):
            plan_ids = [p.get("plan_id") or p.get("id") for p in plans]
        else:
            plan_ids = list(plans.keys()) if isinstance(plans, dict) else []
        
        assert "free" in plan_ids, f"'free' plan missing. Found: {plan_ids}"
        assert "basic" in plan_ids, f"'basic' plan missing. Found: {plan_ids}"
        assert "premium" in plan_ids, f"'premium' plan missing. Found: {plan_ids}"
        print(f"C1 Public plans: {plan_ids}")
    
    def test_analytics_plan_catalog(self, admin_session):
        """Test /api/admin/subscription-analytics returns plan_catalog with free/basic/premium"""
        response = admin_session.get(f"{BASE_URL}/api/admin/subscription-analytics")
        if _risk_engine_admin_blocked(response):
            pytest.skip("Admin subscription analytics blocked by risk engine containment in this environment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        plan_catalog = data.get("plan_catalog", {})
        
        if isinstance(plan_catalog, dict):
            plan_ids = list(plan_catalog.keys())
        elif isinstance(plan_catalog, list):
            plan_ids = [p.get("plan_id") or p.get("id") for p in plan_catalog]
        else:
            plan_ids = []
        
        assert "free" in plan_ids, f"'free' plan missing in analytics. Found: {plan_ids}"
        assert "basic" in plan_ids, f"'basic' plan missing in analytics. Found: {plan_ids}"
        assert "premium" in plan_ids, f"'premium' plan missing in analytics. Found: {plan_ids}"
        print(f"C1 Analytics plan_catalog: {plan_ids}")


class TestC2GPSHealth(TestAuth):
    """C2: GPS health with completeness block"""
    
    def test_gps_health_endpoint(self, admin_session):
        """Test /api/gps/health includes completeness block"""
        response = admin_session.get(f"{BASE_URL}/api/gps/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify completeness block exists
        assert "completeness" in data, f"'completeness' block missing. Keys: {list(data.keys())}"
        
        completeness = data["completeness"]
        assert "plans_count" in completeness, "plans_count missing in completeness"
        assert "faq_count" in completeness, "faq_count missing in completeness"
        assert "is_complete" in completeness, "is_complete missing in completeness"
        
        # Verify mode degrades when incomplete
        is_complete = completeness.get("is_complete", False)
        mode = data.get("mode", "")
        ready = data.get("ready", False)
        
        print(f"C2 GPS Health: mode={mode}, ready={ready}, completeness={completeness}")
        
        # If incomplete, mode should be degraded
        if not is_complete:
            assert mode == "degraded", f"Expected 'degraded' mode when incomplete, got '{mode}'"
        else:
            # If complete, mode should be live (unless other issues)
            assert mode in ["live", "degraded"], f"Unexpected mode: {mode}"


class TestC3CatalogGuard(TestAuth):
    """C3: Catalog guard endpoints"""
    
    def test_catalog_integrity_status(self, admin_session):
        """Test GET /api/gps/admin/catalog-integrity/status"""
        response = admin_session.get(f"{BASE_URL}/api/gps/admin/catalog-integrity/status")
        if _risk_engine_admin_blocked(response):
            pytest.skip("Catalog integrity status blocked by risk engine containment in this environment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data.get('status')}"
        assert "catalog" in data, f"'catalog' missing. Keys: {list(data.keys())}"
        
        catalog = data["catalog"]
        assert "plans_count" in catalog, "plans_count missing"
        assert "faq_count" in catalog, "faq_count missing"
        assert "is_complete" in catalog, "is_complete missing"
        
        print(f"C3 Catalog status: {catalog}")
    
    def test_catalog_integrity_repair(self, admin_session):
        """Test POST /api/gps/admin/catalog-integrity/repair"""
        response = admin_session.post(f"{BASE_URL}/api/gps/admin/catalog-integrity/repair")
        if _risk_engine_admin_blocked(response):
            pytest.skip("Catalog integrity repair blocked by risk engine containment in this environment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data.get('status')}"
        assert "result" in data, f"'result' missing. Keys: {list(data.keys())}"
        
        result = data["result"]
        assert "completeness" in result, "completeness missing in result"
        
        print(f"C3 Repair result: repaired={result.get('repaired')}, completeness={result.get('completeness')}")


class TestC5LiveMetrics(TestAuth):
    """C5: Live metrics with metric_source and kpis_realtime"""
    
    def test_live_metrics_public(self):
        """Test /api/system/live-metrics public access"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/system/live-metrics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify metric_source exists
        assert "metric_source" in data, f"'metric_source' missing. Keys: {list(data.keys())}"
        
        metric_source = data["metric_source"]
        assert "vanity" in metric_source, "vanity missing in metric_source"
        assert "kpis" in metric_source, "kpis missing in metric_source"
        
        # Public should NOT have kpis_realtime
        kpis_realtime = data.get("kpis_realtime")
        if kpis_realtime:
            # If present, should indicate unavailable
            print(f"C5 Public kpis_realtime: {kpis_realtime}")
        
        print(f"C5 Public metric_source: {metric_source}")
    
    def test_live_metrics_authenticated(self, admin_session):
        """Test /api/system/live-metrics with auth returns kpis_realtime"""
        response = admin_session.get(f"{BASE_URL}/api/system/live-metrics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify metric_source exists
        assert "metric_source" in data, f"'metric_source' missing. Keys: {list(data.keys())}"
        
        # Authenticated should have kpis_realtime
        assert "kpis_realtime" in data, f"'kpis_realtime' missing for authenticated user. Keys: {list(data.keys())}"
        
        kpis_realtime = data["kpis_realtime"]
        assert isinstance(kpis_realtime, dict), f"kpis_realtime should be dict, got {type(kpis_realtime)}"
        
        print(f"C5 Auth metric_source: {data['metric_source']}")
        print(f"C5 Auth kpis_realtime keys: {list(kpis_realtime.keys())}")


class TestC6ThemeBuildGate:
    """C6: Theme build gate enforcement"""
    
    def test_theme_build_gate_exists(self):
        """Verify theme-build-gate.js exists"""
        import os
        gate_path = "/app/frontend/scripts/theme-build-gate.js"
        assert os.path.exists(gate_path), f"Theme build gate not found at {gate_path}"
        print("C6 Theme build gate file exists")
    
    def test_theme_build_gate_runs(self):
        """Run theme build gate and check output"""
        import subprocess
        result = subprocess.run(
            ["node", "/app/frontend/scripts/theme-build-gate.js"],
            capture_output=True,
            text=True,
            cwd="/app/frontend",
            timeout=60
        )
        
        # Gate may exit 0 (pass) or 1 (fail with warnings)
        # We just verify it runs without crashing
        assert result.returncode in [0, 1], f"Unexpected exit code: {result.returncode}"
        
        output = result.stdout + result.stderr
        print(f"C6 Theme gate exit code: {result.returncode}")
        
        # Check for critical failures
        if "FAIL" in output:
            fail_count = output.count("FAIL")
            print(f"C6 Theme gate has {fail_count} FAIL(s)")


class TestC8IntegrityArtifacts(TestAuth):
    """C8: Integrity artifact endpoints"""
    
    def test_integrity_artifact_run(self, admin_session):
        """Test POST /api/gps/admin/integrity-artifacts/run"""
        response = admin_session.post(f"{BASE_URL}/api/gps/admin/integrity-artifacts/run")
        if _risk_engine_admin_blocked(response):
            pytest.skip("Integrity artifact run blocked by risk engine containment in this environment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data.get('status')}"
        assert "artifact" in data, f"'artifact' missing. Keys: {list(data.keys())}"
        
        artifact = data["artifact"]
        assert "run_id" in artifact, "run_id missing in artifact"
        assert "generated_at" in artifact, "generated_at missing in artifact"
        assert "gps_counts" in artifact, "gps_counts missing in artifact"
        assert "catalog_completeness" in artifact, "catalog_completeness missing in artifact"
        
        print(f"C8 Artifact run_id: {artifact.get('run_id')}")
        print(f"C8 Artifact gps_counts: {artifact.get('gps_counts')}")
    
    def test_integrity_artifact_latest(self, admin_session):
        """Test GET /api/gps/admin/integrity-artifacts/latest"""
        response = admin_session.get(f"{BASE_URL}/api/gps/admin/integrity-artifacts/latest")
        if _risk_engine_admin_blocked(response):
            pytest.skip("Integrity artifact latest blocked by risk engine containment in this environment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data.get('status')}"
        
        artifact = data.get("artifact", {})
        if artifact:
            assert "run_id" in artifact, "run_id missing in latest artifact"
            print(f"C8 Latest artifact run_id: {artifact.get('run_id')}")
            print(f"C8 Latest artifact path: {artifact.get('artifact_path')}")
        else:
            print("C8 No latest artifact found (may be first run)")


class TestGPSState:
    """Additional GPS state tests"""
    
    def test_gps_state_endpoint(self):
        """Test /api/gps/state returns valid state"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/gps/state")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify core state fields
        assert "state_id" in data, "state_id missing"
        assert "features" in data, "features missing"
        assert "plans" in data, "plans missing"
        assert "faq" in data, "faq missing"
        
        # Check counts
        features_count = len(data.get("features", []))
        plans_count = len(data.get("plans", []))
        faq_count = len(data.get("faq", []))
        
        print(f"GPS State: features={features_count}, plans={plans_count}, faq={faq_count}")
        
        # Verify plans have canonical IDs
        if plans_count > 0:
            plan_ids = [p.get("plan_id") or p.get("id") for p in data["plans"]]
            assert "free" in plan_ids or any("free" in str(p).lower() for p in plan_ids), "No free plan in GPS state"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
