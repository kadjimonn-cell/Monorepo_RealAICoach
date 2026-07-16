"""
Test Preview Host Recovery Banner - Backend Verification
Tests wrapper-path recovery behavior and previewHostRecovered marker
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestWrapperPathRecovery:
    """Tests for wrapper artifact path recovery to root with recovery marker"""
    
    def test_wo_path_redirects_with_recovery_marker(self):
        """Test /wo redirects to /?previewHostRecovered=1"""
        response = requests.get(
            f"{BASE_URL}/wo",
            allow_redirects=False,
            headers={"Accept": "text/html"}
        )
        assert response.status_code == 307, f"Expected 307, got {response.status_code}"
        location = response.headers.get('Location', '')
        assert 'previewHostRecovered=1' in location, f"Expected previewHostRecovered=1 in Location, got {location}"
        
        # Check recovery header
        wrapper_header = response.headers.get('x-rac-wrapper-path-recovered', '')
        assert wrapper_header == '/wo', f"Expected x-rac-wrapper-path-recovered=/wo, got {wrapper_header}"
    
    def test_loading_preview_path_redirects_with_recovery_marker(self):
        """Test /loading-preview redirects to /?previewHostRecovered=1"""
        response = requests.get(
            f"{BASE_URL}/loading-preview",
            allow_redirects=False,
            headers={"Accept": "text/html"}
        )
        assert response.status_code == 307, f"Expected 307, got {response.status_code}"
        location = response.headers.get('Location', '')
        assert 'previewHostRecovered=1' in location, f"Expected previewHostRecovered=1 in Location, got {location}"
        
        # Check recovery header
        wrapper_header = response.headers.get('x-rac-wrapper-path-recovered', '')
        assert wrapper_header == '/loading-preview', f"Expected x-rac-wrapper-path-recovered=/loading-preview, got {wrapper_header}"
    
    def test_s_artifact_path_redirects_with_recovery_marker(self):
        """Test /s/* artifact paths redirect to /?previewHostRecovered=1"""
        response = requests.get(
            f"{BASE_URL}/s/test-artifact",
            allow_redirects=False,
            headers={"Accept": "text/html"}
        )
        assert response.status_code == 307, f"Expected 307, got {response.status_code}"
        location = response.headers.get('Location', '')
        assert 'previewHostRecovered=1' in location, f"Expected previewHostRecovered=1 in Location, got {location}"
        
        # Check recovery header
        wrapper_header = response.headers.get('x-rac-wrapper-path-recovered', '')
        assert wrapper_header == '/s/test-artifact', f"Expected x-rac-wrapper-path-recovered=/s/test-artifact, got {wrapper_header}"


class TestNormalRoutesNoRegression:
    """Tests to ensure normal routes are not affected by wrapper recovery"""
    
    def test_root_route_returns_200(self):
        """Test / returns 200 (no redirect)"""
        response = requests.get(
            f"{BASE_URL}/",
            allow_redirects=False,
            headers={"Accept": "text/html"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_verify_route_returns_200(self):
        """Test /verify returns 200 (no redirect)"""
        response = requests.get(
            f"{BASE_URL}/verify",
            allow_redirects=False,
            headers={"Accept": "text/html"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_api_health_working(self):
        """Test /api/health returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get('status') == 'healthy', f"Expected healthy status, got {data}"


class TestPreviewHealthEndpoint:
    """Tests for _preview/health endpoint"""
    
    def test_preview_health_returns_ok(self):
        """Test /_preview/health returns ok with expected fields"""
        response = requests.get(f"{BASE_URL}/_preview/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get('ok') == True, f"Expected ok=true, got {data}"
        assert 'has_dist' in data, "Expected has_dist field"
        assert 'expected_preview_host' in data, "Expected expected_preview_host field"
        assert 'backend_port' in data, "Expected backend_port field"
    
    def test_preview_health_expected_host_matches_request(self):
        """Test expected_preview_host reflects current request host"""
        response = requests.get(
            f"{BASE_URL}/_preview/health",
            headers={"Host": "subscription-gated-2.preview.emergentagent.com"}
        )
        assert response.status_code == 200
        data = response.json()
        
        expected_host = data.get('expected_preview_host', '')
        # Should contain preview.emergentagent.com
        assert 'preview.emergentagent.com' in expected_host, f"Expected preview host, got {expected_host}"


class TestRecoveryMarkerPreservation:
    """Tests for recovery marker query parameter handling"""
    
    def test_root_with_recovery_marker_returns_200(self):
        """Test /?previewHostRecovered=1 returns 200"""
        response = requests.get(
            f"{BASE_URL}/?previewHostRecovered=1",
            allow_redirects=False,
            headers={"Accept": "text/html"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_welcome_with_recovery_marker_returns_200(self):
        """Test /welcome?previewHostRecovered=1 returns 200"""
        response = requests.get(
            f"{BASE_URL}/welcome?previewHostRecovered=1",
            allow_redirects=False,
            headers={"Accept": "text/html"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
