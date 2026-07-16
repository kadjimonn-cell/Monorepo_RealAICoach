"""
Preview Shell Mismatch Banner and GPS Health Tests
Tests for iteration 474 - verifying GPS endpoints, wrapper recovery, and preview shell diagnostics
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://coach-web-preview.preview.emergentagent.com"


class TestGPSEndpoints:
    """GPS endpoint health verification on active preview host"""
    
    def test_gps_state_endpoint_healthy(self):
        """Feature 1: GPS /api/gps/state endpoint returns valid state"""
        response = requests.get(f"{BASE_URL}/api/gps/state", timeout=10)
        
        # Status code assertion
        assert response.status_code == 200, f"GPS state endpoint returned {response.status_code}"
        
        # Data assertions
        data = response.json()
        assert "state_id" in data, "GPS state missing state_id"
        assert data["state_id"] == "global-platform-state", f"Unexpected state_id: {data['state_id']}"
        assert "features" in data, "GPS state missing features array"
        assert "plans" in data, "GPS state missing plans array"
        assert "_gps_runtime" in data, "GPS state missing _gps_runtime metadata"
        
        # Verify runtime mode
        runtime = data["_gps_runtime"]
        assert runtime.get("mode") == "live", f"GPS runtime mode is not live: {runtime.get('mode')}"
        # Source can be 'live' or 'live_repaired' - both indicate healthy live state
        valid_sources = ["live", "live_repaired"]
        assert runtime.get("source") in valid_sources, f"GPS runtime source is not valid: {runtime.get('source')}"
        
        print(f"GPS state endpoint healthy - {len(data['features'])} features, {len(data['plans'])} plans")
    
    def test_gps_health_endpoint_healthy(self):
        """Feature 1: GPS /api/gps/health endpoint returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/gps/health", timeout=10)
        
        # Status code assertion
        assert response.status_code == 200, f"GPS health endpoint returned {response.status_code}"
        
        # Data assertions
        data = response.json()
        assert data.get("ready") is True, f"GPS health not ready: {data.get('ready')}"
        assert data.get("mode") == "live", f"GPS health mode is not live: {data.get('mode')}"
        
        # Verify dependencies are healthy
        dependencies = data.get("dependencies", {})
        for dep_name, dep_status in dependencies.items():
            assert dep_status.get("status") == "healthy", f"Dependency {dep_name} is not healthy: {dep_status}"
        
        # Verify completeness
        completeness = data.get("completeness", {})
        assert completeness.get("is_complete") is True, f"GPS completeness check failed: {completeness}"
        assert completeness.get("features_count", 0) >= 25, f"Too few features: {completeness.get('features_count')}"
        assert completeness.get("plans_count", 0) >= 3, f"Too few plans: {completeness.get('plans_count')}"
        
        print(f"GPS health endpoint healthy - mode: {data.get('mode')}, features: {completeness.get('features_count')}")


class TestWrapperArtifactRecovery:
    """Wrapper artifact /wo recovery tests"""
    
    def test_wo_redirects_with_recovery_param(self):
        """Feature 5: /wo wrapper artifact route redirects with previewHostRecovered=1"""
        response = requests.get(
            f"{BASE_URL}/wo",
            allow_redirects=False,
            timeout=10
        )
        
        # Should return 307 redirect
        assert response.status_code == 307, f"/wo returned {response.status_code}, expected 307"
        
        # Check Location header
        location = response.headers.get("Location", "")
        assert "previewHostRecovered=1" in location, f"Location header missing previewHostRecovered=1: {location}"
        
        # Check custom headers
        assert response.headers.get("x-rac-wrapper-path-recovered") == "/wo", \
            "Missing x-rac-wrapper-path-recovered header"
        
        print(f"/wo recovery redirect working - Location: {location}")
    
    def test_wo_recovery_headers_present(self):
        """Feature 5: /wo recovery includes proper headers"""
        response = requests.get(
            f"{BASE_URL}/wo",
            allow_redirects=False,
            timeout=10
        )
        
        # Verify bundle hash header is present
        bundle_hash = response.headers.get("x-rac-dist-bundle-hash")
        assert bundle_hash, "Missing x-rac-dist-bundle-hash header"
        assert len(bundle_hash) == 32, f"Bundle hash has unexpected length: {len(bundle_hash)}"
        
        # Verify serving mode header
        serving_mode = response.headers.get("x-rac-serving-mode")
        assert serving_mode, "Missing x-rac-serving-mode header"
        
        print(f"/wo recovery headers present - bundle_hash: {bundle_hash}, serving_mode: {serving_mode}")


class TestPreviewHostRendering:
    """Preview host app-origin rendering tests"""
    
    def test_root_response_has_bundle_hash_header(self):
        """Feature 4: Root response includes x-rac-dist-bundle-hash header"""
        response = requests.get(
            f"{BASE_URL}/",
            allow_redirects=True,
            timeout=10
        )
        
        # Should return 200
        assert response.status_code == 200, f"Root returned {response.status_code}"
        
        # Check bundle hash header
        bundle_hash = response.headers.get("x-rac-dist-bundle-hash")
        assert bundle_hash, "Missing x-rac-dist-bundle-hash header on root response"
        assert len(bundle_hash) == 32, f"Bundle hash has unexpected length: {len(bundle_hash)}"
        
        print(f"Root response has bundle hash header: {bundle_hash}")
    
    def test_welcome_page_accessible(self):
        """Feature 4: Welcome page is accessible on preview host"""
        response = requests.get(
            f"{BASE_URL}/welcome",
            allow_redirects=True,
            timeout=10
        )
        
        # Should return 200
        assert response.status_code == 200, f"Welcome page returned {response.status_code}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "text/html" in content_type, f"Unexpected content type: {content_type}"
        
        # Check for basic HTML structure
        assert "<html" in response.text.lower(), "Response missing HTML tag"
        assert "realaicoach" in response.text.lower(), "Response missing RealAICoach branding"
        
        print("Welcome page accessible and contains expected content")


class TestPreviewShellMismatchBannerLogic:
    """Tests for PreviewShellMismatchBanner component logic (code review)"""
    
    def test_banner_component_has_correct_testids(self):
        """Feature 2 & 3: Verify banner component has required data-testid attributes"""
        # This is a code review test - we verify the component file has the right structure
        component_path = "/app/frontend/src/components/PreviewShellMismatchBanner.tsx"
        
        with open(component_path, 'r') as f:
            content = f.read()
        
        # Check for required data-testid attributes
        required_testids = [
            'preview-shell-mismatch-banner',
            'preview-shell-mismatch-title',
            'preview-shell-mismatch-copy',
            'preview-shell-open-direct-button',
            'preview-shell-mismatch-dismiss-button'
        ]
        
        for testid in required_testids:
            assert f'data-testid="{testid}"' in content, f"Missing data-testid: {testid}"
        
        print(f"All {len(required_testids)} required data-testid attributes present in banner component")
    
    def test_banner_component_has_wrapper_detection_logic(self):
        """Feature 2: Verify banner has wrapper shell host detection"""
        component_path = "/app/frontend/src/components/PreviewShellMismatchBanner.tsx"
        
        with open(component_path, 'r') as f:
            content = f.read()
        
        # Check for wrapper shell detection logic
        assert "isWrapperShellHost" in content, "Missing isWrapperShellHost function"
        assert "app.emergent.sh" in content, "Missing app.emergent.sh detection"
        assert "emergentagent.com" in content, "Missing emergentagent.com detection"
        
        print("Banner component has wrapper shell host detection logic")
    
    def test_banner_component_has_direct_preview_cta(self):
        """Feature 3: Verify banner has direct preview CTA functionality"""
        component_path = "/app/frontend/src/components/PreviewShellMismatchBanner.tsx"
        
        with open(component_path, 'r') as f:
            content = f.read()
        
        # Check for direct preview open functionality
        assert "openDirectPreview" in content, "Missing openDirectPreview function"
        assert "Open Direct" in content, "Missing 'Open Direct' button text"
        assert "window.location.href" in content, "Missing navigation logic"
        
        print("Banner component has direct preview CTA functionality")
    
    def test_banner_wired_in_layout(self):
        """Feature 2: Verify banner is wired in _layout.tsx"""
        layout_path = "/app/frontend/app/_layout.tsx"
        
        with open(layout_path, 'r') as f:
            content = f.read()
        
        # Check for banner import and usage
        assert "PreviewShellMismatchBanner" in content, "PreviewShellMismatchBanner not imported in _layout.tsx"
        assert "<PreviewShellMismatchBanner" in content, "PreviewShellMismatchBanner not rendered in _layout.tsx"
        
        print("PreviewShellMismatchBanner is properly wired in _layout.tsx")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
