"""
P2-03: Admin list endpoints pagination API tests
Tests that admin endpoints return proper pagination envelope: { data, total_count, page, page_size }
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    # Login as admin
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if login_resp.status_code != 200:
        pytest.skip(f"Admin login failed: {login_resp.status_code} - {login_resp.text[:200]}")
    
    return session


class TestReferralsChallengesPagination:
    """Test /api/referrals/admin/challenges pagination envelope."""
    
    def test_challenges_default_pagination(self, admin_session):
        """Challenges endpoint returns pagination envelope with default params."""
        resp = admin_session.get(f"{BASE_URL}/api/referrals/admin/challenges")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        # Verify pagination envelope keys
        assert "data" in data, "Missing 'data' key in response"
        assert "total_count" in data, "Missing 'total_count' key in response"
        assert "page" in data, "Missing 'page' key in response"
        assert "page_size" in data, "Missing 'page_size' key in response"
        
        # Verify types
        assert isinstance(data["data"], list), "'data' should be a list"
        assert isinstance(data["total_count"], int), "'total_count' should be int"
        assert isinstance(data["page"], int), "'page' should be int"
        assert isinstance(data["page_size"], int), "'page_size' should be int"
        
        # Verify default values
        assert data["page"] == 1, "Default page should be 1"
        assert data["page_size"] == 20, "Default page_size should be 20"
        print(f"✓ Challenges pagination: page={data['page']}, page_size={data['page_size']}, total_count={data['total_count']}")
    
    def test_challenges_custom_pagination(self, admin_session):
        """Challenges endpoint respects custom page/page_size params."""
        resp = admin_session.get(f"{BASE_URL}/api/referrals/admin/challenges?page=2&page_size=5")
        assert resp.status_code == 200
        
        data = resp.json()
        assert data["page"] == 2, "Page should be 2"
        assert data["page_size"] == 5, "Page size should be 5"
        print(f"✓ Challenges custom pagination: page={data['page']}, page_size={data['page_size']}")


class TestReferralsFraudAlertsPagination:
    """Test /api/referrals/admin/fraud-alerts pagination envelope."""
    
    def test_fraud_alerts_default_pagination(self, admin_session):
        """Fraud alerts endpoint returns pagination envelope with default params."""
        resp = admin_session.get(f"{BASE_URL}/api/referrals/admin/fraud-alerts")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        # Verify pagination envelope keys
        assert "data" in data, "Missing 'data' key in response"
        assert "total_count" in data, "Missing 'total_count' key in response"
        assert "page" in data, "Missing 'page' key in response"
        assert "page_size" in data, "Missing 'page_size' key in response"
        
        # Verify types
        assert isinstance(data["data"], list), "'data' should be a list"
        assert isinstance(data["total_count"], int), "'total_count' should be int"
        
        # Verify default values
        assert data["page"] == 1, "Default page should be 1"
        assert data["page_size"] == 25, "Default page_size should be 25"
        
        # Verify summary metadata is preserved
        assert "total_open" in data, "Missing 'total_open' summary metadata"
        assert "total_resolved" in data, "Missing 'total_resolved' summary metadata"
        assert "severity_counts" in data, "Missing 'severity_counts' summary metadata"
        print(f"✓ Fraud alerts pagination: page={data['page']}, page_size={data['page_size']}, total_count={data['total_count']}")
        print(f"  Summary: open={data.get('total_open')}, resolved={data.get('total_resolved')}")
    
    def test_fraud_alerts_custom_pagination(self, admin_session):
        """Fraud alerts endpoint respects custom page/page_size params."""
        resp = admin_session.get(f"{BASE_URL}/api/referrals/admin/fraud-alerts?page=1&page_size=10")
        assert resp.status_code == 200
        
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
        print(f"✓ Fraud alerts custom pagination: page={data['page']}, page_size={data['page_size']}")


class TestSupportFAQAdminListPagination:
    """Test /api/support/faq/admin/list pagination envelope."""
    
    def test_faq_list_default_pagination(self, admin_session):
        """FAQ admin list endpoint returns pagination envelope with default params."""
        resp = admin_session.get(f"{BASE_URL}/api/support/faq/admin/list")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        # Verify pagination envelope keys
        assert "data" in data, "Missing 'data' key in response"
        assert "total_count" in data, "Missing 'total_count' key in response"
        assert "page" in data, "Missing 'page' key in response"
        assert "page_size" in data, "Missing 'page_size' key in response"
        
        # Verify types
        assert isinstance(data["data"], list), "'data' should be a list"
        assert isinstance(data["total_count"], int), "'total_count' should be int"
        
        # Verify default values
        assert data["page"] == 1, "Default page should be 1"
        assert data["page_size"] == 25, "Default page_size should be 25"
        print(f"✓ FAQ list pagination: page={data['page']}, page_size={data['page_size']}, total_count={data['total_count']}")
    
    def test_faq_list_custom_pagination(self, admin_session):
        """FAQ admin list endpoint respects custom page/page_size params."""
        resp = admin_session.get(f"{BASE_URL}/api/support/faq/admin/list?page=1&page_size=10&lang=en")
        assert resp.status_code == 200
        
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
        print(f"✓ FAQ list custom pagination: page={data['page']}, page_size={data['page_size']}")


class TestAdminSubmissionsPagination:
    """Test /api/admin/submissions pagination envelope."""
    
    def test_submissions_default_pagination(self, admin_session):
        """Admin submissions endpoint returns pagination envelope with default params."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/submissions")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        
        data = resp.json()
        # Verify pagination envelope keys
        assert "data" in data, "Missing 'data' key in response"
        assert "total_count" in data, "Missing 'total_count' key in response"
        assert "page" in data, "Missing 'page' key in response"
        assert "page_size" in data, "Missing 'page_size' key in response"
        
        # Verify types
        assert isinstance(data["data"], list), "'data' should be a list"
        assert isinstance(data["total_count"], int), "'total_count' should be int"
        
        # Verify default values
        assert data["page"] == 1, "Default page should be 1"
        assert data["page_size"] == 50, "Default page_size should be 50"
        print(f"✓ Submissions pagination: page={data['page']}, page_size={data['page_size']}, total_count={data['total_count']}")
    
    def test_submissions_custom_pagination(self, admin_session):
        """Admin submissions endpoint respects custom page/page_size params."""
        resp = admin_session.get(f"{BASE_URL}/api/admin/submissions?page=1&page_size=20")
        assert resp.status_code == 200
        
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 20
        print(f"✓ Submissions custom pagination: page={data['page']}, page_size={data['page_size']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
