"""
Single-Admin Team Management Approval Tests
Tests: Verify Team Management high-risk mutations use single-admin approval
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_CREDS = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}
FREE_CREDS = {"email": "tv.free.test@realaicoach.app", "password": "TvFree#2026!Aa"}


class TestSession:
    """Shared session for authenticated requests"""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.tokens = {}
    
    def login(self, creds: dict, role: str) -> str:
        """Login and store token"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json=creds)
        if response.status_code == 200:
            data = response.json()
            token = data.get("session_token") or data.get("token")
            self.tokens[role] = token
            return token
        return ""
    
    def get_auth_headers(self, role: str) -> dict:
        """Get headers with auth token"""
        token = self.tokens.get(role, "")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# Module-level session
_session = TestSession()


@pytest.fixture(scope="module")
def session():
    """Module-scoped session fixture"""
    return _session


@pytest.fixture(scope="module", autouse=True)
def setup_auth(session):
    """Setup authentication for all tests"""
    admin_token = session.login(ADMIN_CREDS, "admin")
    free_token = session.login(FREE_CREDS, "free")
    assert admin_token, "Admin login failed"
    assert free_token, "Free user login failed"


class TestSingleAdminBulkUpdateRole:
    """Verify bulk-update-role uses single-admin approval"""
    
    def test_admin_bulk_update_role_returns_200(self, session):
        """POST /api/admin/employees/bulk-update-role as admin should return 200"""
        headers = session.get_auth_headers("admin")
        
        # First get valid roles
        config_response = requests.get(f"{BASE_URL}/api/admin/employees/roles-config", headers=headers)
        assert config_response.status_code == 200, f"roles-config failed: {config_response.status_code}"
        roles = config_response.json().get("roles", [])
        assert len(roles) > 0, "Expected at least one platform role"
        
        # Test bulk-update-role should succeed in single-admin mode
        response = requests.post(
            f"{BASE_URL}/api/admin/employees/bulk-update-role",
            headers=headers,
            json={"user_ids": ["nonexistent_user_id"], "platform_role": roles[0]}
        )
        
        assert response.status_code == 200, f"Expected 200 (single-admin), got {response.status_code}"
        
        data = response.json()
        assert "updated_count" in data, f"Expected bulk update response, got: {data}"
        assert "skipped_count" in data, f"Expected bulk update response, got: {data}"
        print(f"PASS: bulk-update-role returns 200 with single-admin approval (updated={data['updated_count']}, skipped={data['skipped_count']})")
    
    def test_non_admin_bulk_update_role_returns_403(self, session):
        """POST /api/admin/employees/bulk-update-role as non-admin should return 403"""
        headers = session.get_auth_headers("free")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/employees/bulk-update-role",
            headers=headers,
            json={"user_ids": ["test_user_id"], "platform_role": "Manager"}
        )
        
        assert response.status_code == 403, f"Non-admin should get 403, got {response.status_code}"
        print(f"PASS: Non-admin denied bulk-update-role (status={response.status_code})")


class TestSingleAdminBulkUpdatePremium:
    """Verify bulk-update-premium uses single-admin approval"""
    
    def test_admin_bulk_update_premium_returns_200(self, session):
        """POST /api/admin/employees/bulk-update-premium as admin should return 200"""
        headers = session.get_auth_headers("admin")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/employees/bulk-update-premium",
            headers=headers,
            json={"user_ids": ["nonexistent_user_id"], "premium_access": True}
        )
        
        assert response.status_code == 200, f"Expected 200 (single-admin), got {response.status_code}"
        
        data = response.json()
        assert "updated_count" in data
        print("PASS: bulk-update-premium returns 200 with single-admin approval")
    
    def test_non_admin_bulk_update_premium_returns_403(self, session):
        """POST /api/admin/employees/bulk-update-premium as non-admin should return 403"""
        headers = session.get_auth_headers("free")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/employees/bulk-update-premium",
            headers=headers,
            json={"user_ids": ["test_user_id"], "premium_access": True}
        )
        
        assert response.status_code == 403, f"Non-admin should get 403, got {response.status_code}"
        print(f"PASS: Non-admin denied bulk-update-premium (status={response.status_code})")


class TestSingleAdminBulkRemove:
    """Verify bulk-remove uses single-admin approval"""
    
    def test_admin_bulk_remove_returns_200(self, session):
        """POST /api/admin/employees/bulk-remove as admin should return 200"""
        headers = session.get_auth_headers("admin")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/employees/bulk-remove",
            headers=headers,
            json={"user_ids": ["nonexistent_user_id"]}
        )
        
        assert response.status_code == 200, f"Expected 200 (single-admin), got {response.status_code}"
        
        data = response.json()
        assert "removed_count" in data
        print("PASS: bulk-remove returns 200 with single-admin approval")
    
    def test_non_admin_bulk_remove_returns_403(self, session):
        """POST /api/admin/employees/bulk-remove as non-admin should return 403"""
        headers = session.get_auth_headers("free")
        
        response = requests.post(
            f"{BASE_URL}/api/admin/employees/bulk-remove",
            headers=headers,
            json={"user_ids": ["test_user_id"]}
        )
        
        assert response.status_code == 403, f"Non-admin should get 403, got {response.status_code}"
        print(f"PASS: Non-admin denied bulk-remove (status={response.status_code})")


class TestRolesConfigEndpoint:
    """Verify roles-config endpoint access"""
    
    def test_admin_roles_config_returns_200(self, session):
        """GET /api/admin/employees/roles-config as admin should return 200"""
        headers = session.get_auth_headers("admin")
        
        response = requests.get(f"{BASE_URL}/api/admin/employees/roles-config", headers=headers)
        
        assert response.status_code == 200, f"Admin should get 200, got {response.status_code}"
        data = response.json()
        assert "roles" in data, "Response should contain roles"
        assert "all_features" in data, "Response should contain all_features"
        assert "all_permissions" in data, "Response should contain all_permissions"
        print(f"PASS: Admin can access roles-config (roles={len(data.get('roles', []))})")
    
    def test_non_admin_roles_config_returns_403(self, session):
        """GET /api/admin/employees/roles-config as non-admin should return 403"""
        headers = session.get_auth_headers("free")
        
        response = requests.get(f"{BASE_URL}/api/admin/employees/roles-config", headers=headers)
        
        assert response.status_code == 403, f"Non-admin should get 403, got {response.status_code}"
        print(f"PASS: Non-admin denied roles-config (status={response.status_code})")


class TestRegressionOtherAdminRoutes:
    """Regression: Verify other admin routes still deny non-admin"""
    
    def test_non_admin_denied_admin_employees_list(self, session):
        """GET /api/admin/employees as non-admin should return 403"""
        headers = session.get_auth_headers("free")
        
        response = requests.get(f"{BASE_URL}/api/admin/employees", headers=headers)
        
        assert response.status_code == 403, f"Non-admin should get 403, got {response.status_code}"
        print(f"PASS: Non-admin denied /api/admin/employees (status={response.status_code})")
    
    def test_non_admin_denied_audit_log(self, session):
        """GET /api/admin/access-control/audit as non-admin should return 403"""
        headers = session.get_auth_headers("free")
        
        response = requests.get(f"{BASE_URL}/api/admin/access-control/audit", headers=headers)
        
        assert response.status_code == 403, f"Non-admin should get 403, got {response.status_code}"
        print(f"PASS: Non-admin denied /api/admin/access-control/audit (status={response.status_code})")
    
    def test_non_admin_denied_break_glass_status(self, session):
        """GET /api/admin/access-control/break-glass/status as non-admin should return 403"""
        headers = session.get_auth_headers("free")
        
        response = requests.get(f"{BASE_URL}/api/admin/access-control/break-glass/status", headers=headers)
        
        assert response.status_code == 403, f"Non-admin should get 403, got {response.status_code}"
        print(f"PASS: Non-admin denied /api/admin/access-control/break-glass/status (status={response.status_code})")
    
    def test_admin_allowed_admin_employees_list(self, session):
        """GET /api/admin/employees as admin should return 200"""
        headers = session.get_auth_headers("admin")
        
        response = requests.get(f"{BASE_URL}/api/admin/employees", headers=headers)
        
        assert response.status_code == 200, f"Admin should get 200, got {response.status_code}"
        data = response.json()
        assert "employees" in data, "Response should contain employees"
        print(f"PASS: Admin allowed /api/admin/employees (employees={len(data.get('employees', []))})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
