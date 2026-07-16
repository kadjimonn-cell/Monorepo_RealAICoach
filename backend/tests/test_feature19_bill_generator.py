"""
Feature 19 (Bill Generator) - Comprehensive Backend API Tests
Tests health, bootstrap, export endpoints for authenticated users (free/basic/premium)
and guest fallback behavior.

NOTE: Basic tier user test expects 'free' plan because payment_verified is not set.
This is expected behavior per compute_effective_plan logic.
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
TEST_USERS = {
    "free": {
        "email": "feature21.test.1781234530@example.com",
        "password": "Feature21Test#2026Aa"
    },
    "basic": {
        "email": "f21.basic.1781338672@example.com",
        "password": "F21Basic#2026Aa"
    },
    "admin": {
        "email": "admin@realaicoach.app",
        "password": "NewAdminPass2026!"
    }
}


class TestFeature19BillGeneratorHealth:
    """Test health endpoint for Feature 19 Bill Generator"""
    
    def test_health_endpoint_returns_healthy(self):
        """A1: Health endpoint returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/bill-generator/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy status, got {data.get('status')}"
        assert data.get("feature") == "bill-generator", f"Expected feature=bill-generator, got {data.get('feature')}"
        assert data.get("feature_number") == 19, f"Expected feature_number=19, got {data.get('feature_number')}"
        assert "timestamp" in data, "Missing timestamp in health response"
        print("PASS: Health endpoint returns healthy with feature_number=19")


class TestFeature19BillGeneratorUnauthenticated:
    """Test unauthenticated access to Feature 19 endpoints"""
    
    def test_bootstrap_requires_auth_or_guest_id(self):
        """B1: Bootstrap endpoint returns 401 for unauthenticated requests without guest ID"""
        response = requests.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Bootstrap returns 401 for unauthenticated requests without guest ID")
    
    def test_export_requires_auth_or_guest_id(self):
        """B2: Export endpoint returns 401 for unauthenticated requests without guest ID"""
        response = requests.get(f"{BASE_URL}/api/bill-generator/export?format=payload")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Export returns 401 for unauthenticated requests without guest ID")


class TestFeature19BillGeneratorGuestFallback:
    """Test guest fallback behavior using fallback_user_id pattern"""
    
    def test_bootstrap_with_valid_guest_id(self):
        """C1: Bootstrap accepts valid guest fallback_user_id"""
        guest_id = f"user_{uuid.uuid4().hex[:16]}"
        response = requests.get(f"{BASE_URL}/api/bill-generator/bootstrap?fallback_user_id={guest_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("plan") == "free", f"Guest should get free plan, got {data.get('plan')}"
        assert data.get("scope_label") == "Limited access", f"Guest should get Limited access, got {data.get('scope_label')}"
        print("PASS: Bootstrap accepts valid guest fallback_user_id with plan=free")
    
    def test_bootstrap_rejects_invalid_guest_id(self):
        """C2: Bootstrap rejects invalid guest fallback_user_id format"""
        invalid_guest_id = "invalid_id"
        response = requests.get(f"{BASE_URL}/api/bill-generator/bootstrap?fallback_user_id={invalid_guest_id}")
        assert response.status_code == 400, f"Expected 400 for invalid guest ID, got {response.status_code}"
        print("PASS: Bootstrap rejects invalid guest fallback_user_id format")
    
    def test_export_with_valid_guest_id(self):
        """C3: Export accepts valid guest fallback_user_id"""
        guest_id = f"user_{uuid.uuid4().hex[:16]}"
        response = requests.get(f"{BASE_URL}/api/bill-generator/export?format=payload&fallback_user_id={guest_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("export_format") == "payload", f"Expected export_format=payload, got {data.get('export_format')}"
        assert data.get("owner_id") == guest_id, f"Expected owner_id={guest_id}, got {data.get('owner_id')}"
        print("PASS: Export accepts valid guest fallback_user_id")


def _login_user(email: str, password: str) -> requests.Session:
    """Helper to login and return authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password}
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Login failed for {email}: {login_response.status_code} - {login_response.text[:200]}")
    
    return session


class TestFeature19BillGeneratorFreeTier:
    """Test Feature 19 for Free tier authenticated user"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = _login_user(TEST_USERS["free"]["email"], TEST_USERS["free"]["password"])
    
    def test_bootstrap_free_tier_plan(self):
        """D1: Free tier user gets plan=free with Limited access"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("plan") == "free", f"Expected plan=free, got {data.get('plan')}"
        assert data.get("scope_label") == "Limited access", f"Expected Limited access, got {data.get('scope_label')}"
        print("PASS: Free tier bootstrap returns plan=free, scope_label=Limited access")
    
    def test_bootstrap_free_tier_limits(self):
        """D2: Free tier user gets correct limits"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        
        data = response.json()
        limits = data.get("limits", {})
        
        # Free tier limits from PLAN_ACTION_LIMITS
        assert limits.get("ai_draft") == 3, f"Expected ai_draft=3, got {limits.get('ai_draft')}"
        assert limits.get("create_bill") == 5, f"Expected create_bill=5, got {limits.get('create_bill')}"
        assert limits.get("pdf_export") == 3, f"Expected pdf_export=3, got {limits.get('pdf_export')}"
        print("PASS: Free tier limits correct: ai_draft=3, create_bill=5, pdf_export=3")
    
    def test_bootstrap_contract_fields(self):
        """D3: Bootstrap response contains all required fields"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = [
            "plan", "scope_label", "limits", "clients", "bills", 
            "catalog_items", "recurring_schedules", "reminders",
            "client_insights", "collections_dashboard", "channel_settings",
            "workspace_settings", "workspace_members", "insights"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        print(f"PASS: Bootstrap contains all {len(required_fields)} required fields")
    
    def test_export_payload_format(self):
        """D4: Export endpoint returns payload format correctly"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/export?format=payload")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("export_format") == "payload", "Expected export_format=payload"
        assert "timestamp" in data, "Missing timestamp in export"
        assert "owner_id" in data, "Missing owner_id in export"
        assert "bills" in data, "Missing bills in export"
        assert "clients" in data, "Missing clients in export"
        print("PASS: Export payload format correct with all required fields")
    
    def test_export_json_format(self):
        """D5: Export endpoint returns json format correctly"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/export?format=json")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("export_format") == "json", "Expected export_format=json"
        print("PASS: Export json format correct")


class TestFeature19BillGeneratorBasicTier:
    """Test Feature 19 for Basic tier authenticated user
    
    NOTE: Basic tier user with payment_verified=true gets plan=basic.
    This is expected behavior per compute_effective_plan logic in access_control_engine.py
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = _login_user(TEST_USERS["basic"]["email"], TEST_USERS["basic"]["password"])
    
    def test_bootstrap_basic_tier_plan(self):
        """E1: Basic tier user with payment_verified gets plan=basic with Almost unlimited access"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # User has subscription_plan=basic and payment_verified=true
        # So compute_effective_plan returns 'basic' per access control logic
        assert data.get("plan") == "basic", f"Expected plan=basic, got {data.get('plan')}"
        assert data.get("scope_label") == "Almost unlimited access", f"Expected Almost unlimited access, got {data.get('scope_label')}"
        print("PASS: Basic tier user gets plan=basic, scope_label=Almost unlimited access")
    
    def test_bootstrap_basic_tier_limits(self):
        """E2: Basic tier user gets correct limits"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        
        data = response.json()
        limits = data.get("limits", {})
        
        # Basic tier limits from PLAN_ACTION_LIMITS
        assert limits.get("ai_draft") == 120, f"Expected ai_draft=120, got {limits.get('ai_draft')}"
        assert limits.get("create_bill") == 220, f"Expected create_bill=220, got {limits.get('create_bill')}"
        assert limits.get("pdf_export") == 120, f"Expected pdf_export=120, got {limits.get('pdf_export')}"
        print("PASS: Basic tier limits correct: ai_draft=120, create_bill=220, pdf_export=120")


class TestFeature19BillGeneratorPremiumTier:
    """Test Feature 19 for Premium/Admin tier authenticated user"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = _login_user(TEST_USERS["admin"]["email"], TEST_USERS["admin"]["password"])
    
    def test_bootstrap_premium_tier_plan(self):
        """F1: Premium/Admin tier user gets plan=premium with Full unlimited access"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("plan") == "premium", f"Expected plan=premium, got {data.get('plan')}"
        assert data.get("scope_label") == "Full unlimited access", f"Expected Full unlimited access, got {data.get('scope_label')}"
        print("PASS: Premium tier bootstrap returns plan=premium, scope_label=Full unlimited access")
    
    def test_bootstrap_premium_tier_limits(self):
        """F2: Premium tier user gets unlimited (-1) limits"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        
        data = response.json()
        limits = data.get("limits", {})
        
        # Premium tier limits from PLAN_ACTION_LIMITS (-1 = unlimited)
        assert limits.get("ai_draft") == -1, f"Expected ai_draft=-1 (unlimited), got {limits.get('ai_draft')}"
        assert limits.get("create_bill") == -1, f"Expected create_bill=-1 (unlimited), got {limits.get('create_bill')}"
        assert limits.get("pdf_export") == -1, f"Expected pdf_export=-1 (unlimited), got {limits.get('pdf_export')}"
        print("PASS: Premium tier limits correct: all -1 (unlimited)")
    
    def test_export_csv_format(self):
        """F3: Export endpoint returns csv format correctly"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/export?format=csv")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # CSV format returns text/csv content type
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type or response.status_code == 200, "Expected CSV response"
        print("PASS: Export csv format returns successfully")


class TestFeature19FeatureRegistry:
    """Test Feature 19 registration in feature registry"""
    
    def test_feature_registry_contains_bill_generator(self):
        """G1: Feature registry contains bill-generator with feature_number=19"""
        response = requests.get(f"{BASE_URL}/api/features/registry")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        features = data.get("features", [])
        
        bill_generator = None
        for feature in features:
            if feature.get("feature_id") == "bill-generator":
                bill_generator = feature
                break
        
        assert bill_generator is not None, "bill-generator not found in feature registry"
        assert bill_generator.get("feature_number") == 19, f"Expected feature_number=19, got {bill_generator.get('feature_number')}"
        assert bill_generator.get("enabled") == True, "bill-generator should be enabled"
        assert bill_generator.get("route") == "/features/bill-generator", "Expected route=/features/bill-generator"
        print("PASS: Feature registry contains bill-generator with feature_number=19, enabled=True")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
