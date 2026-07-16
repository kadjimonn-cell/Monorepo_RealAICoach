"""
P0 Checkpoint D Validation Tests
================================
Tests for GPS health truthfulness, preview stale-code guardrails, 
wrapper artifact recovery, and responsive smoke stability.

Test Coverage:
- GPS /api/gps/health returns ready=true, mode=live, completeness checks passing
- GPS /api/gps/state returns populated counts/features/plans and _gps_runtime.mode=live
- Preview /_preview/health returns active_bundle_hash and non-null build_state
- Wrapper artifact recovery: /wo, /loading-preview, /s/<any> redirect with previewHostRecovered=1
- Root response headers include x-rac-dist-bundle-hash
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestGPSHealthEndpoints:
    """GPS health and state endpoint validation"""
    
    def test_gps_health_returns_ready_true(self):
        """GET /api/gps/health returns ready=true"""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert data.get("ready") is True, f"Expected ready=true, got {data.get('ready')}"
        
    def test_gps_health_mode_is_live(self):
        """GET /api/gps/health returns mode=live"""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "live", f"Expected mode=live, got {data.get('mode')}"
        
    def test_gps_health_completeness_checks_passing(self):
        """GET /api/gps/health completeness.is_complete=true"""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        completeness = data.get("completeness", {})
        assert completeness.get("is_complete") is True, f"Completeness check failed: {completeness.get('failed_checks')}"
        
    def test_gps_health_no_false_degraded_signal(self):
        """GPS health should not report false degraded signal"""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        # Check no error state
        assert data.get("last_error") is None, f"Unexpected error: {data.get('last_error')}"
        assert data.get("failing_component") is None, f"Unexpected failing component: {data.get('failing_component')}"
        
    def test_gps_state_returns_populated_data(self):
        """GET /api/gps/state returns populated features/plans"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200
        data = response.json()
        
        # Check features populated
        features = data.get("features", [])
        assert len(features) >= 25, f"Expected at least 25 features, got {len(features)}"
        
        # Check plans populated
        plans = data.get("plans", [])
        assert len(plans) >= 3, f"Expected at least 3 plans, got {len(plans)}"
        
    def test_gps_state_runtime_mode_is_live(self):
        """GET /api/gps/state _gps_runtime.mode=live"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=15)
        assert response.status_code == 200
        data = response.json()
        runtime = data.get("_gps_runtime", {})
        assert runtime.get("mode") == "live", f"Expected _gps_runtime.mode=live, got {runtime.get('mode')}"


class TestPreviewHealthEndpoint:
    """Preview health endpoint validation"""
    
    def test_preview_health_returns_ok(self):
        """GET /_preview/health returns ok=true"""
        response = requests.get(f"{BASE_URL}/_preview/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        
    def test_preview_health_has_active_bundle_hash(self):
        """GET /_preview/health returns active_bundle_hash"""
        response = requests.get(f"{BASE_URL}/_preview/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        bundle_hash = data.get("active_bundle_hash")
        assert bundle_hash is not None and len(bundle_hash) > 0, "active_bundle_hash should be non-empty"
        
    def test_preview_health_has_build_state(self):
        """GET /_preview/health returns non-null build_state"""
        response = requests.get(f"{BASE_URL}/_preview/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        build_state = data.get("build_state")
        assert build_state is not None, "build_state should not be null"
        
    def test_preview_health_build_state_has_source_fingerprint(self):
        """build_state contains source_fingerprint"""
        response = requests.get(f"{BASE_URL}/_preview/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        build_state = data.get("build_state", {})
        fingerprint = build_state.get("source_fingerprint")
        assert fingerprint is not None and len(fingerprint) > 0, "source_fingerprint should be non-empty"
        
    def test_preview_health_build_state_has_index_bundle(self):
        """build_state contains index_bundle"""
        response = requests.get(f"{BASE_URL}/_preview/health", timeout=15)
        assert response.status_code == 200
        data = response.json()
        build_state = data.get("build_state", {})
        index_bundle = build_state.get("index_bundle")
        assert index_bundle is not None and "index-" in index_bundle, f"index_bundle should contain 'index-', got {index_bundle}"


class TestWrapperArtifactRecovery:
    """Wrapper artifact path recovery validation"""
    
    def test_wo_redirects_with_recovery_param(self):
        """/wo redirects to /?previewHostRecovered=1"""
        response = requests.get(f"{BASE_URL}/wo", allow_redirects=False, timeout=15)
        assert response.status_code == 307, f"Expected 307 redirect, got {response.status_code}"
        location = response.headers.get("location", "")
        assert "previewHostRecovered=1" in location, f"Expected previewHostRecovered=1 in location, got {location}"
        
    def test_wo_has_recovery_header(self):
        """/wo response has x-rac-wrapper-path-recovered header"""
        response = requests.get(f"{BASE_URL}/wo", allow_redirects=False, timeout=15)
        recovered_path = response.headers.get("x-rac-wrapper-path-recovered")
        assert recovered_path == "/wo", f"Expected x-rac-wrapper-path-recovered=/wo, got {recovered_path}"
        
    def test_loading_preview_redirects_with_recovery_param(self):
        """/loading-preview redirects to /?previewHostRecovered=1"""
        response = requests.get(f"{BASE_URL}/loading-preview", allow_redirects=False, timeout=15)
        assert response.status_code == 307, f"Expected 307 redirect, got {response.status_code}"
        location = response.headers.get("location", "")
        assert "previewHostRecovered=1" in location, f"Expected previewHostRecovered=1 in location, got {location}"
        
    def test_s_path_redirects_with_recovery_param(self):
        """/s/<any> redirects to /?previewHostRecovered=1"""
        response = requests.get(f"{BASE_URL}/s/test-session-id", allow_redirects=False, timeout=15)
        assert response.status_code == 307, f"Expected 307 redirect, got {response.status_code}"
        location = response.headers.get("location", "")
        assert "previewHostRecovered=1" in location, f"Expected previewHostRecovered=1 in location, got {location}"


class TestRootResponseHeaders:
    """Root response header validation"""
    
    def test_root_has_bundle_hash_header(self):
        """Root response includes x-rac-dist-bundle-hash header"""
        response = requests.get(f"{BASE_URL}/", timeout=15)
        assert response.status_code == 200
        bundle_hash = response.headers.get("x-rac-dist-bundle-hash")
        assert bundle_hash is not None and len(bundle_hash) > 0, "x-rac-dist-bundle-hash header should be present"
        
    def test_root_has_serving_mode_header(self):
        """Root response includes x-rac-serving-mode header"""
        response = requests.get(f"{BASE_URL}/", timeout=15)
        assert response.status_code == 200
        serving_mode = response.headers.get("x-rac-serving-mode")
        assert serving_mode is not None, "x-rac-serving-mode header should be present"
        
    def test_root_no_stale_cache_behavior(self):
        """Root response has no-store cache control"""
        response = requests.get(f"{BASE_URL}/", timeout=15)
        assert response.status_code == 200
        cache_control = response.headers.get("cache-control", "")
        assert "no-store" in cache_control.lower() or "no-cache" in cache_control.lower(), \
            f"Expected no-store/no-cache in cache-control, got {cache_control}"


class TestWelcomePageAccessibility:
    """Welcome page accessibility validation"""
    
    def test_welcome_page_accessible(self):
        """/welcome returns 200"""
        response = requests.get(f"{BASE_URL}/welcome", timeout=15)
        assert response.status_code == 200
        
    def test_welcome_page_has_content(self):
        """/welcome returns HTML content"""
        response = requests.get(f"{BASE_URL}/welcome", timeout=15)
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type.lower(), f"Expected text/html, got {content_type}"
        # Check for key content markers
        assert "RealAICoach" in response.text or "welcome" in response.text.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
