"""Comprehensive GPS Health and Observability Tests.

Tests for:
1. GPS health endpoint should not falsely report degraded when runtime state is live
2. GPS health payload should include completeness and not fail freshness_contract under live runtime
3. Public GPS state endpoint returns non-empty features/plans/faq
4. Admin observability overview exposes GPS health from runtime incident stream
"""
import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture
def admin_session() -> requests.Session:
    """Create an authenticated admin session using cookie-based auth."""
    session = requests.Session()
    login_res = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=20,
    )
    assert login_res.status_code == 200, f"Admin login failed: {login_res.status_code} {login_res.text[:300]}"
    return session


class TestGPSHealthRuntimeFreshness:
    """Tests for GPS health endpoint freshness contract fix."""

    def test_gps_state_returns_live_mode(self):
        """GPS state endpoint should return live mode when healthy."""
        res = requests.get(f"{BASE_URL}/api/gps/state", timeout=20)
        assert res.status_code == 200, f"gps/state failed: {res.status_code}"
        payload = res.json()
        runtime = payload.get("_gps_runtime") or {}
        
        # Should be in live mode
        assert runtime.get("mode") == "live", f"Expected mode=live, got {runtime.get('mode')}"
        assert runtime.get("source") in ("live", "live_repaired"), f"Expected source=live, got {runtime.get('source')}"
        assert runtime.get("last_success_at"), "Missing last_success_at in runtime"

    def test_gps_state_returns_non_empty_data(self):
        """GPS state endpoint should return non-empty features, plans, and FAQ."""
        res = requests.get(f"{BASE_URL}/api/gps/state", timeout=20)
        assert res.status_code == 200
        payload = res.json()
        
        features = payload.get("features") or []
        plans = payload.get("plans") or []
        faq = payload.get("faq") or []
        
        assert len(features) >= 25, f"Expected at least 25 features, got {len(features)}"
        assert len(plans) >= 3, f"Expected at least 3 plans, got {len(plans)}"
        assert len(faq) >= 3, f"Expected at least 3 FAQ entries, got {len(faq)}"

    def test_gps_health_does_not_false_degrade_when_runtime_is_live(self):
        """If runtime is live and dependencies are healthy, freshness must use runtime last_success_at.

        This prevents false degraded mode when global_platform_state.updated_at is old but
        the GPS runtime feed is currently healthy.
        """
        # First get state to ensure runtime is live
        state_res = requests.get(f"{BASE_URL}/api/gps/state", timeout=20)
        assert state_res.status_code == 200, f"gps/state failed: {state_res.status_code}"
        state_payload = state_res.json()
        runtime = state_payload.get("_gps_runtime") or {}

        # Then check health
        health_res = requests.get(f"{BASE_URL}/api/gps/health", timeout=20)
        assert health_res.status_code == 200, f"gps/health failed: {health_res.status_code}"
        health_payload = health_res.json()

        deps = health_payload.get("dependencies") or {}
        deps_all_healthy = all((row or {}).get("status") == "healthy" for row in deps.values())
        failed_checks = (health_payload.get("completeness") or {}).get("failed_checks") or []

        if runtime.get("mode") == "live" and deps_all_healthy:
            assert "freshness_contract" not in failed_checks, (
                "freshness_contract should not fail when runtime is live and dependencies are healthy"
            )
            assert health_payload.get("mode") == "live", (
                f"Expected gps/health mode=live, got {health_payload.get('mode')} with checks={failed_checks}"
            )

    def test_gps_health_completeness_uses_runtime_freshness_reference(self):
        """GPS health completeness should use runtime last_success_at for freshness check."""
        health_res = requests.get(f"{BASE_URL}/api/gps/health", timeout=20)
        assert health_res.status_code == 200
        health_payload = health_res.json()
        
        completeness = health_payload.get("completeness") or {}
        freshness_ref = completeness.get("freshness_reference_at")
        health_payload.get("last_success_at")
        
        # freshness_reference_at should be set when runtime is live
        if health_payload.get("mode") == "live":
            assert freshness_ref is not None, "freshness_reference_at should be set when mode is live"
            # The freshness reference should be recent (within the last few seconds)
            state_age = completeness.get("state_age_seconds")
            assert state_age is not None, "state_age_seconds should be present"
            # Age should be small since we just fetched
            assert state_age < 60, f"state_age_seconds should be recent, got {state_age}"

    def test_gps_health_ready_when_all_healthy(self):
        """GPS health should report ready=True when all dependencies are healthy."""
        health_res = requests.get(f"{BASE_URL}/api/gps/health", timeout=20)
        assert health_res.status_code == 200
        health_payload = health_res.json()
        
        deps = health_payload.get("dependencies") or {}
        all_healthy = all((row or {}).get("status") == "healthy" for row in deps.values())
        completeness = health_payload.get("completeness") or {}
        is_complete = completeness.get("is_complete")
        
        if all_healthy and is_complete:
            assert health_payload.get("ready") is True, "ready should be True when all healthy"
            assert health_payload.get("mode") == "live", "mode should be live when all healthy"


class TestObservabilityGPSRuntimeCollection:
    """Tests for observability center GPS health integration."""

    def test_observability_overview_includes_gps_health_shape(self, admin_session):
        """Observability overview should include GPS health with correct shape."""
        res = admin_session.get(f"{BASE_URL}/api/admin/observability/overview", timeout=20)
        assert res.status_code == 200, f"overview failed: {res.status_code} {res.text[:300]}"
        payload = res.json()

        gps_health = payload.get("gps_health")
        assert isinstance(gps_health, dict), "gps_health should be an object"

        # Collection alignment guard: route should expose runtime incident shape fields.
        if gps_health:
            assert "component" in gps_health, "gps_health missing component"
            assert "error" in gps_health, "gps_health missing error"
            assert "created_at" in gps_health, "gps_health missing created_at"
            assert gps_health.get("severity") == "critical", "gps_health severity normalization missing"

    def test_observability_overview_returns_valid_structure(self, admin_session):
        """Observability overview should return all expected sections."""
        res = admin_session.get(f"{BASE_URL}/api/admin/observability/overview", timeout=20)
        assert res.status_code == 200
        payload = res.json()
        
        # Check required top-level keys
        assert "timestamp" in payload
        assert "system" in payload
        assert "application" in payload
        assert "frontend_experience" in payload
        assert "alerts" in payload
        assert "gps_health" in payload
        assert "correlation" in payload


class TestGPSAdminEndpoints:
    """Tests for GPS admin endpoints."""

    def test_gps_admin_incidents_endpoint(self, admin_session):
        """GPS admin incidents endpoint should return incident list."""
        res = admin_session.get(f"{BASE_URL}/api/gps/admin/incidents", timeout=20)
        assert res.status_code == 200, f"incidents failed: {res.status_code}"
        payload = res.json()
        
        assert "items" in payload
        assert "count" in payload
        assert isinstance(payload["items"], list)

    def test_gps_admin_catalog_integrity_status(self, admin_session):
        """GPS admin catalog integrity status should return completeness info."""
        res = admin_session.get(f"{BASE_URL}/api/gps/admin/catalog-integrity/status", timeout=20)
        assert res.status_code == 200, f"catalog-integrity/status failed: {res.status_code}"
        payload = res.json()
        
        assert payload.get("status") == "ok"
        catalog = payload.get("catalog") or {}
        assert "is_complete" in catalog
        assert "features_count" in catalog
        assert "plans_count" in catalog
        assert "faq_count" in catalog
