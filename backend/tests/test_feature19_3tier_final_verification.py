"""
Feature 19 (Bill Generator) - Final 3-Tier Entitlement Verification
=====================================================================
This test verifies that all 3 tiers (Free/Basic/Premium) are fully working
for Feature 19 Bill Generator.

Test credentials:
- Free: feature21.test.1781234530@example.com / Feature21Test#2026Aa
- Basic: f21.basic.1781338672@example.com / F21Basic#2026Aa
- Admin: admin@realaicoach.app / NewAdminPass2026!
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
FREE_USER = {
    "email": "feature21.test.1781234530@example.com",
    "password": "Feature21Test#2026Aa"
}

BASIC_USER = {
    "email": "f21.basic.1781338672@example.com",
    "password": "F21Basic#2026Aa"
}

ADMIN_USER = {
    "email": "admin@realaicoach.app",
    "password": "NewAdminPass2026!"
}

# Expected entitlement values per tier
EXPECTED_ENTITLEMENTS = {
    "free": {
        "plan": "free",
        "scope_label": "Limited access",
        "limits": {
            "ai_draft": 3,
            "create_bill": 5,
            "pdf_export": 3,
            "status_update": 20,
            "catalog_manage": 25,
            "create_schedule": 2,
            "run_schedule": 4,
            "reminder_message": 20,
            "approval_action": 20
        }
    },
    "basic": {
        "plan": "basic",
        "scope_label": "Almost unlimited access",
        "limits": {
            "ai_draft": 120,
            "create_bill": 220,
            "pdf_export": 120,
            "status_update": 500,
            "catalog_manage": 500,
            "create_schedule": 80,
            "run_schedule": 300,
            "reminder_message": 600,
            "approval_action": 600
        }
    },
    "premium": {
        "plan": "premium",
        "scope_label": "Full unlimited access",
        "limits": {
            "ai_draft": -1,
            "create_bill": -1,
            "pdf_export": -1,
            "status_update": -1,
            "catalog_manage": -1,
            "create_schedule": -1,
            "run_schedule": -1,
            "reminder_message": -1,
            "approval_action": -1
        }
    }
}


class TestFeature19HealthEndpoint:
    """Test Feature 19 health endpoint"""
    
    def test_health_endpoint_returns_healthy(self):
        """Health endpoint should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/bill-generator/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["feature"] == "bill-generator"
        assert data["feature_number"] == 19
        print(f"✓ Health endpoint: status={data['status']}, feature={data['feature']}, feature_number={data['feature_number']}")


class TestFeature19UnauthenticatedAccess:
    """Test unauthenticated access behavior"""
    
    def test_bootstrap_unauthenticated_returns_401(self):
        """Bootstrap without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 401
        print("✓ Unauthenticated bootstrap returns 401 as expected")
    
    def test_bootstrap_guest_mode_with_valid_id(self):
        """Bootstrap with valid guest ID should return free plan"""
        response = requests.get(
            f"{BASE_URL}/api/bill-generator/bootstrap",
            params={"fallback_user_id": "user_test12345678901234"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "free"
        assert data["scope_label"] == "Limited access"
        print(f"✓ Guest mode with valid ID: plan={data['plan']}, scope_label={data['scope_label']}")
    
    def test_bootstrap_guest_mode_with_invalid_id(self):
        """Bootstrap with invalid guest ID should return 400"""
        response = requests.get(
            f"{BASE_URL}/api/bill-generator/bootstrap",
            params={"fallback_user_id": "invalid"}
        )
        assert response.status_code == 400
        print("✓ Guest mode with invalid ID returns 400 as expected")


class TestFeature19FreeTierEntitlement:
    """Test Free tier entitlement for Feature 19"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as free user"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=FREE_USER
        )
        if response.status_code != 200:
            pytest.skip(f"Free user login failed: {response.status_code} - {response.text}")
        
        print("✓ Free user logged in successfully")
    
    def test_free_tier_bootstrap_plan(self):
        """Free tier should return plan=free"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        data = response.json()
        
        expected = EXPECTED_ENTITLEMENTS["free"]
        assert data["plan"] == expected["plan"], f"Expected plan={expected['plan']}, got {data['plan']}"
        assert data["scope_label"] == expected["scope_label"], f"Expected scope_label={expected['scope_label']}, got {data['scope_label']}"
        
        print(f"✓ Free tier bootstrap: plan={data['plan']}, scope_label={data['scope_label']}")
    
    def test_free_tier_limits(self):
        """Free tier should have correct limits"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        data = response.json()
        
        expected_limits = EXPECTED_ENTITLEMENTS["free"]["limits"]
        actual_limits = data.get("limits", {})
        
        for action, expected_limit in expected_limits.items():
            actual_limit = actual_limits.get(action)
            assert actual_limit == expected_limit, f"Free tier limit for {action}: expected {expected_limit}, got {actual_limit}"
        
        print(f"✓ Free tier limits verified: ai_draft={actual_limits.get('ai_draft')}, create_bill={actual_limits.get('create_bill')}, pdf_export={actual_limits.get('pdf_export')}")
    
    def test_free_tier_access_control_session(self):
        """Free tier access control session should return effective_plan=free"""
        response = self.session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("effective_plan") == "free", f"Expected effective_plan=free, got {data.get('effective_plan')}"
        print(f"✓ Free tier access control session: effective_plan={data.get('effective_plan')}")


class TestFeature19BasicTierEntitlement:
    """Test Basic tier entitlement for Feature 19"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as basic user"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=BASIC_USER
        )
        if response.status_code != 200:
            pytest.skip(f"Basic user login failed: {response.status_code} - {response.text}")
        
        print("✓ Basic user logged in successfully")
    
    def test_basic_tier_bootstrap_plan(self):
        """Basic tier should return plan=basic"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        data = response.json()
        
        expected = EXPECTED_ENTITLEMENTS["basic"]
        assert data["plan"] == expected["plan"], f"Expected plan={expected['plan']}, got {data['plan']}"
        assert data["scope_label"] == expected["scope_label"], f"Expected scope_label={expected['scope_label']}, got {data['scope_label']}"
        
        print(f"✓ Basic tier bootstrap: plan={data['plan']}, scope_label={data['scope_label']}")
    
    def test_basic_tier_limits(self):
        """Basic tier should have correct limits"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        data = response.json()
        
        expected_limits = EXPECTED_ENTITLEMENTS["basic"]["limits"]
        actual_limits = data.get("limits", {})
        
        for action, expected_limit in expected_limits.items():
            actual_limit = actual_limits.get(action)
            assert actual_limit == expected_limit, f"Basic tier limit for {action}: expected {expected_limit}, got {actual_limit}"
        
        print(f"✓ Basic tier limits verified: ai_draft={actual_limits.get('ai_draft')}, create_bill={actual_limits.get('create_bill')}, pdf_export={actual_limits.get('pdf_export')}")
    
    def test_basic_tier_access_control_session(self):
        """Basic tier access control session should return effective_plan=basic"""
        response = self.session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("effective_plan") == "basic", f"Expected effective_plan=basic, got {data.get('effective_plan')}"
        print(f"✓ Basic tier access control session: effective_plan={data.get('effective_plan')}")


class TestFeature19PremiumTierEntitlement:
    """Test Premium tier entitlement for Feature 19 (Admin user)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin user"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=ADMIN_USER
        )
        if response.status_code != 200:
            pytest.skip(f"Admin user login failed: {response.status_code} - {response.text}")
        
        print("✓ Admin user logged in successfully")
    
    def test_premium_tier_bootstrap_plan(self):
        """Premium tier should return plan=premium"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        data = response.json()
        
        expected = EXPECTED_ENTITLEMENTS["premium"]
        assert data["plan"] == expected["plan"], f"Expected plan={expected['plan']}, got {data['plan']}"
        assert data["scope_label"] == expected["scope_label"], f"Expected scope_label={expected['scope_label']}, got {data['scope_label']}"
        
        print(f"✓ Premium tier bootstrap: plan={data['plan']}, scope_label={data['scope_label']}")
    
    def test_premium_tier_limits(self):
        """Premium tier should have unlimited (-1) limits"""
        response = self.session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
        assert response.status_code == 200
        data = response.json()
        
        expected_limits = EXPECTED_ENTITLEMENTS["premium"]["limits"]
        actual_limits = data.get("limits", {})
        
        for action, expected_limit in expected_limits.items():
            actual_limit = actual_limits.get(action)
            assert actual_limit == expected_limit, f"Premium tier limit for {action}: expected {expected_limit}, got {actual_limit}"
        
        print(f"✓ Premium tier limits verified: ai_draft={actual_limits.get('ai_draft')}, create_bill={actual_limits.get('create_bill')}, pdf_export={actual_limits.get('pdf_export')}")
    
    def test_premium_tier_access_control_session(self):
        """Premium tier access control session should return effective_plan=premium and is_admin=true"""
        response = self.session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("effective_plan") == "premium", f"Expected effective_plan=premium, got {data.get('effective_plan')}"
        assert data.get("is_admin") == True, f"Expected is_admin=True, got {data.get('is_admin')}"
        print(f"✓ Premium tier access control session: effective_plan={data.get('effective_plan')}, is_admin={data.get('is_admin')}")


class TestFeature19ExportEndpoint:
    """Test export endpoint functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin user for export tests"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        # Login
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=ADMIN_USER
        )
        if response.status_code != 200:
            pytest.skip(f"Admin user login failed: {response.status_code} - {response.text}")
    
    def test_export_payload_format(self):
        """Export with payload format should work"""
        response = self.session.get(
            f"{BASE_URL}/api/bill-generator/export",
            params={"format": "payload"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("export_format") == "payload"
        assert "bills" in data
        assert "clients" in data
        assert "catalog_items" in data
        print(f"✓ Export payload format works: export_format={data.get('export_format')}")
    
    def test_export_json_format(self):
        """Export with json format should work"""
        response = self.session.get(
            f"{BASE_URL}/api/bill-generator/export",
            params={"format": "json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("export_format") == "json"
        print(f"✓ Export json format works: export_format={data.get('export_format')}")
    
    def test_export_csv_format(self):
        """Export with csv format should work"""
        response = self.session.get(
            f"{BASE_URL}/api/bill-generator/export",
            params={"format": "csv"}
        )
        assert response.status_code == 200
        # CSV format returns text/csv content type
        print(f"✓ Export csv format works: status_code={response.status_code}")


class TestFeature19ThreeTierSummary:
    """Summary test to verify all 3 tiers in one test"""
    
    def test_all_three_tiers_working(self):
        """Verify all 3 tiers return correct entitlements"""
        results = {}
        
        # Test Free tier
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=FREE_USER)
        if login_resp.status_code == 200:
            bootstrap_resp = session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
            if bootstrap_resp.status_code == 200:
                data = bootstrap_resp.json()
                results["free"] = {
                    "plan": data.get("plan"),
                    "scope_label": data.get("scope_label"),
                    "ai_draft_limit": data.get("limits", {}).get("ai_draft"),
                    "working": data.get("plan") == "free"
                }
        
        # Test Basic tier
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=BASIC_USER)
        if login_resp.status_code == 200:
            bootstrap_resp = session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
            if bootstrap_resp.status_code == 200:
                data = bootstrap_resp.json()
                results["basic"] = {
                    "plan": data.get("plan"),
                    "scope_label": data.get("scope_label"),
                    "ai_draft_limit": data.get("limits", {}).get("ai_draft"),
                    "working": data.get("plan") == "basic"
                }
        
        # Test Premium tier
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER)
        if login_resp.status_code == 200:
            bootstrap_resp = session.get(f"{BASE_URL}/api/bill-generator/bootstrap")
            if bootstrap_resp.status_code == 200:
                data = bootstrap_resp.json()
                results["premium"] = {
                    "plan": data.get("plan"),
                    "scope_label": data.get("scope_label"),
                    "ai_draft_limit": data.get("limits", {}).get("ai_draft"),
                    "working": data.get("plan") == "premium"
                }
        
        # Print summary
        print("\n" + "="*60)
        print("FEATURE 19 (BILL GENERATOR) - 3-TIER ENTITLEMENT SUMMARY")
        print("="*60)
        
        for tier, data in results.items():
            status = "✓ WORKING" if data.get("working") else "✗ NOT WORKING"
            print(f"\n{tier.upper()} TIER: {status}")
            print(f"  - plan: {data.get('plan')}")
            print(f"  - scope_label: {data.get('scope_label')}")
            print(f"  - ai_draft_limit: {data.get('ai_draft_limit')}")
        
        print("\n" + "="*60)
        
        # Assert all tiers are working
        assert results.get("free", {}).get("working"), "Free tier not working correctly"
        assert results.get("basic", {}).get("working"), "Basic tier not working correctly"
        assert results.get("premium", {}).get("working"), "Premium tier not working correctly"
        
        print("\n✓ ALL 3 TIERS ARE FULLY WORKING FOR FEATURE 19 (BILL GENERATOR)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
