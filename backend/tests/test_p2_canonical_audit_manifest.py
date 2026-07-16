"""
P2 Canonical Audit & Manifest Endpoints Tests
Tests for:
- GET /api/features/canonical-audit (admin-only)
- GET /api/features/canonical-order-manifest (admin-only)
- GET /api/features/canonical-order-manifest.json (admin-only)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # Fallback for local testing
    BASE_URL = "https://coach-web-preview.preview.emergentagent.com"

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestCanonicalAuditEndpoint:
    """Tests for GET /api/features/canonical-audit"""

    def test_canonical_audit_unauth_returns_401(self):
        """Unauthenticated request should return 401"""
        response = requests.get(f"{BASE_URL}/api/features/canonical-audit")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: GET /api/features/canonical-audit unauth returns 401")

    def test_canonical_audit_admin_auth_returns_200(self):
        """Admin authenticated request should return 200 with summary and manifest.download_endpoint"""
        # Login as admin
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.status_code} - {login_response.text}"
        
        # Request canonical audit
        response = session.get(f"{BASE_URL}/api/features/canonical-audit")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify summary exists
        assert "summary" in data, "Response should contain 'summary' field"
        summary = data["summary"]
        assert "status" in summary, "Summary should contain 'status'"
        assert "registry_feature_count" in summary, "Summary should contain 'registry_feature_count'"
        
        # Verify manifest.download_endpoint exists
        assert "manifest" in data, "Response should contain 'manifest' field"
        manifest = data["manifest"]
        assert "download_endpoint" in manifest, "Manifest should contain 'download_endpoint'"
        assert manifest["download_endpoint"] == "/api/features/canonical-order-manifest", \
            f"Expected download_endpoint to be '/api/features/canonical-order-manifest', got {manifest['download_endpoint']}"
        
        print(f"PASS: GET /api/features/canonical-audit admin auth returns 200 with summary (status={summary['status']}) and manifest.download_endpoint")


class TestCanonicalOrderManifestEndpoint:
    """Tests for GET /api/features/canonical-order-manifest"""

    def test_canonical_order_manifest_unauth_returns_401(self):
        """Unauthenticated request should return 401"""
        response = requests.get(f"{BASE_URL}/api/features/canonical-order-manifest")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: GET /api/features/canonical-order-manifest unauth returns 401")

    def test_canonical_order_manifest_admin_auth_returns_200_with_content_disposition(self):
        """Admin authenticated request should return 200 with Content-Disposition header"""
        # Login as admin
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.status_code} - {login_response.text}"
        
        # Request canonical order manifest
        response = session.get(f"{BASE_URL}/api/features/canonical-order-manifest")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify Content-Disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "canonical_order_manifest.json" in content_disposition, \
            f"Expected Content-Disposition to contain 'canonical_order_manifest.json', got: {content_disposition}"
        
        # Verify response is valid JSON
        data = response.json()
        assert "manifest_name" in data, "Response should contain 'manifest_name'"
        assert data["manifest_name"] == "canonical_order_manifest.json", \
            f"Expected manifest_name to be 'canonical_order_manifest.json', got {data['manifest_name']}"
        assert "items" in data, "Response should contain 'items'"
        assert isinstance(data["items"], list), "Items should be a list"
        
        print("PASS: GET /api/features/canonical-order-manifest admin auth returns 200 with Content-Disposition filename canonical_order_manifest.json")


class TestCanonicalOrderManifestJsonEndpoint:
    """Tests for GET /api/features/canonical-order-manifest.json"""

    def test_canonical_order_manifest_json_unauth_returns_401(self):
        """Unauthenticated request should return 401"""
        response = requests.get(f"{BASE_URL}/api/features/canonical-order-manifest.json")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: GET /api/features/canonical-order-manifest.json unauth returns 401")

    def test_canonical_order_manifest_json_admin_auth_returns_200_with_content_disposition(self):
        """Admin authenticated request should return 200 with Content-Disposition header"""
        # Login as admin
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert login_response.status_code == 200, f"Admin login failed: {login_response.status_code} - {login_response.text}"
        
        # Request canonical order manifest JSON alias
        response = session.get(f"{BASE_URL}/api/features/canonical-order-manifest.json")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify Content-Disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "canonical_order_manifest.json" in content_disposition, \
            f"Expected Content-Disposition to contain 'canonical_order_manifest.json', got: {content_disposition}"
        
        # Verify response is valid JSON
        data = response.json()
        assert "manifest_name" in data, "Response should contain 'manifest_name'"
        assert "canonical_order_version" in data, "Response should contain 'canonical_order_version'"
        assert "locked_feature_count" in data, "Response should contain 'locked_feature_count'"
        
        print("PASS: GET /api/features/canonical-order-manifest.json admin auth returns 200 with Content-Disposition filename canonical_order_manifest.json")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
