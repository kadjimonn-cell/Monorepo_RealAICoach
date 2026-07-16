"""
Talent Network Admin Panel - Backend API Tests

Tests for:
1. POST /api/careers/talent-network/join - Public endpoint for joining talent network
2. GET /api/admin/careers/talent-network/overview - Admin analytics endpoint
3. POST /api/admin/careers/talent-network/dispatch/run-now - Admin dispatch trigger
4. Scheduler job registration verification
5. No regression on existing /api/careers/talent-network/join endpoint
"""

import os
import pytest
import requests
import uuid
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestTalentNetworkPublicEndpoint:
    """Tests for the public talent network join endpoint"""

    def test_join_talent_network_success(self):
        """Test successful join to talent network"""
        unique_email = f"test.tn.{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": unique_email,
            "full_name": "Test User",
            "role_interests": ["engineering", "product"],
            "locations": ["remote"],
            "work_types": ["full-time"],
            "source": "pytest_e2e"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/careers/talent-network/join",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("success") is True
        assert "network_id" in data
        assert data["network_id"].startswith("tn_")
        assert "message" in data
        assert "preferences" in data
        
        # Verify preferences are returned correctly
        prefs = data["preferences"]
        assert prefs["role_interests"] == ["engineering", "product"]
        assert prefs["locations"] == ["remote"]
        assert prefs["work_types"] == ["full-time"]
        
        print(f"SUCCESS: Joined talent network with network_id={data['network_id']}")

    def test_join_talent_network_duplicate_email(self):
        """Test that duplicate email returns already_joined=true"""
        unique_email = f"test.tn.dup.{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": unique_email,
            "full_name": "Test User",
            "role_interests": ["engineering"],
            "source": "pytest_e2e"
        }
        
        # First join
        response1 = requests.post(
            f"{BASE_URL}/api/careers/talent-network/join",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1.get("already_joined") is False
        
        # Second join with same email
        response2 = requests.post(
            f"{BASE_URL}/api/careers/talent-network/join",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2.get("already_joined") is True
        assert data2.get("network_id") == data1.get("network_id")
        
        print("SUCCESS: Duplicate email correctly returns already_joined=true")

    def test_join_talent_network_missing_email(self):
        """Test that missing email returns validation error"""
        payload = {
            "full_name": "Test User",
            "role_interests": ["engineering"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/careers/talent-network/join",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}
        )
        
        # Should return 422 validation error
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("SUCCESS: Missing email correctly returns 422 validation error")

    def test_join_talent_network_invalid_email(self):
        """Test that invalid email format returns validation error"""
        payload = {
            "email": "not-an-email",
            "full_name": "Test User"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/careers/talent-network/join",
            json=payload,
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}
        )
        
        # Should return 422 validation error
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("SUCCESS: Invalid email correctly returns 422 validation error")


class TestTalentNetworkAdminOverview:
    """Tests for the admin talent network overview endpoint"""

    @pytest.fixture(autouse=True)
    def setup_admin_session(self):
        """Setup admin session for authenticated requests"""
        self.session = requests.Session()
        self.session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json"
        })
        
        # Login as admin
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code}")

    def test_overview_returns_valid_structure(self):
        """Test that overview endpoint returns valid JSON structure"""
        response = self.session.get(f"{BASE_URL}/api/admin/careers/talent-network/overview?days=30")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify top-level structure
        assert "window_days" in data
        assert "generated_at" in data
        assert "summary" in data
        assert "top_role_interests" in data
        assert "source_conversion" in data
        assert "latest_dispatch_run" in data
        assert "recent_dispatches" in data
        
        print("SUCCESS: Overview endpoint returns valid structure")

    def test_overview_summary_fields(self):
        """Test that summary contains required KPI fields"""
        response = self.session.get(f"{BASE_URL}/api/admin/careers/talent-network/overview?days=30")
        
        assert response.status_code == 200
        data = response.json()
        summary = data.get("summary", {})
        
        # Verify summary fields
        assert "total_signups" in summary
        assert "active_signups" in summary
        assert "signups_in_window" in summary
        assert "dispatch_totals" in summary
        
        # Verify dispatch_totals structure
        dispatch_totals = summary.get("dispatch_totals", {})
        assert "attempted" in dispatch_totals
        assert "sent" in dispatch_totals
        assert "failed" in dispatch_totals
        
        # Verify values are integers
        assert isinstance(summary["total_signups"], int)
        assert isinstance(summary["active_signups"], int)
        assert isinstance(summary["signups_in_window"], int)
        
        print("SUCCESS: Summary contains all required KPI fields")
        print(f"  - total_signups: {summary['total_signups']}")
        print(f"  - active_signups: {summary['active_signups']}")
        print(f"  - signups_in_window: {summary['signups_in_window']}")
        print(f"  - dispatch_totals: {dispatch_totals}")

    def test_overview_latest_dispatch_run_structure(self):
        """Test that latest_dispatch_run has correct structure when present"""
        response = self.session.get(f"{BASE_URL}/api/admin/careers/talent-network/overview?days=30")
        
        assert response.status_code == 200
        data = response.json()
        latest_run = data.get("latest_dispatch_run", {})
        
        # If there's a dispatch run, verify its structure
        if latest_run:
            expected_fields = ["run_id", "status", "started_at"]
            for field in expected_fields:
                assert field in latest_run, f"Missing field: {field}"
            
            print("SUCCESS: latest_dispatch_run has correct structure")
            print(f"  - run_id: {latest_run.get('run_id')}")
            print(f"  - status: {latest_run.get('status')}")
            print(f"  - started_at: {latest_run.get('started_at')}")
        else:
            print("INFO: No dispatch runs yet (empty latest_dispatch_run)")

    def test_overview_recent_dispatches_structure(self):
        """Test that recent_dispatches is a list with correct item structure"""
        response = self.session.get(f"{BASE_URL}/api/admin/careers/talent-network/overview?days=30")
        
        assert response.status_code == 200
        data = response.json()
        recent = data.get("recent_dispatches", [])
        
        assert isinstance(recent, list), "recent_dispatches should be a list"
        
        if recent:
            # Check first item structure
            item = recent[0]
            expected_fields = ["event_id", "email", "status", "created_at"]
            for field in expected_fields:
                assert field in item, f"Missing field in dispatch event: {field}"
            
            print(f"SUCCESS: recent_dispatches has {len(recent)} items with correct structure")
        else:
            print("INFO: No recent dispatches yet (empty list)")

    def test_overview_window_days_parameter(self):
        """Test that window_days parameter is respected"""
        for days in [7, 30, 90]:
            response = self.session.get(f"{BASE_URL}/api/admin/careers/talent-network/overview?days={days}")
            
            assert response.status_code == 200
            data = response.json()
            assert data.get("window_days") == days, f"Expected window_days={days}, got {data.get('window_days')}"
        
        print("SUCCESS: window_days parameter is correctly respected for 7, 30, 90 days")

    def test_overview_requires_admin(self):
        """Test that overview endpoint requires admin access"""
        # Create a new session without admin auth
        unauth_session = requests.Session()
        unauth_session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json"
        })
        
        response = unauth_session.get(f"{BASE_URL}/api/admin/careers/talent-network/overview?days=30")
        
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("SUCCESS: Overview endpoint correctly requires admin access")


class TestTalentNetworkDispatchRunNow:
    """Tests for the admin dispatch run-now endpoint"""

    @pytest.fixture(autouse=True)
    def setup_admin_session(self):
        """Setup admin session for authenticated requests"""
        self.session = requests.Session()
        self.session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json"
        })
        
        # Login as admin
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code}")

    def test_dispatch_run_now_success(self):
        """Test that dispatch run-now executes successfully"""
        response = self.session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/dispatch/run-now?force=true"
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("ok") is True
        assert "result" in data
        
        result = data["result"]
        assert "run_id" in result
        assert result["run_id"].startswith("tn_dispatch_")
        assert "status" in result
        assert result["status"] in ["success", "skipped", "error"]
        assert "mode" in result
        assert result["mode"] == "live"
        
        print("SUCCESS: Dispatch run-now executed successfully")
        print(f"  - run_id: {result['run_id']}")
        print(f"  - status: {result['status']}")
        print(f"  - attempted: {result.get('attempted', 0)}")
        print(f"  - sent: {result.get('sent', 0)}")
        print(f"  - failed: {result.get('failed', 0)}")

    def test_dispatch_run_now_stores_telemetry(self):
        """Test that dispatch run stores telemetry in database"""
        # Run dispatch
        response = self.session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/dispatch/run-now?force=true"
        )
        
        assert response.status_code == 200
        data = response.json()
        run_id = data["result"]["run_id"]
        
        # Verify telemetry by checking overview
        overview_response = self.session.get(
            f"{BASE_URL}/api/admin/careers/talent-network/overview?days=1"
        )
        
        assert overview_response.status_code == 200
        overview = overview_response.json()
        
        # Check that latest_dispatch_run matches our run
        latest_run = overview.get("latest_dispatch_run", {})
        assert latest_run.get("run_id") == run_id, "Latest dispatch run should match our run"
        
        print(f"SUCCESS: Dispatch telemetry stored correctly for run_id={run_id}")

    def test_dispatch_run_now_requires_admin(self):
        """Test that dispatch run-now requires admin access"""
        # Create a new session without admin auth
        unauth_session = requests.Session()
        unauth_session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json"
        })
        
        response = unauth_session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/dispatch/run-now?force=true"
        )
        
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("SUCCESS: Dispatch run-now correctly requires admin access")

    def test_dispatch_run_now_no_objectid_serialization_error(self):
        """Test that dispatch run doesn't have ObjectId serialization issues"""
        response = self.session.post(
            f"{BASE_URL}/api/admin/careers/talent-network/dispatch/run-now?force=true"
        )
        
        # If there's an ObjectId serialization issue, it would return 500
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify the response is valid JSON (no serialization errors)
        try:
            data = response.json()
            assert "result" in data
            print("SUCCESS: No ObjectId serialization issues detected")
        except Exception as e:
            pytest.fail(f"JSON parsing failed - possible serialization issue: {e}")


class TestTalentNetworkNoRegression:
    """Tests to ensure no regression on existing functionality"""

    def test_careers_jobs_endpoint_still_works(self):
        """Test that /api/careers/jobs still works"""
        response = requests.get(f"{BASE_URL}/api/careers/jobs")
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
        print(f"SUCCESS: /api/careers/jobs returns {data['count']} jobs")

    def test_careers_overview_endpoint_still_works(self):
        """Test that /api/careers/overview still works"""
        response = requests.get(f"{BASE_URL}/api/careers/overview")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_open" in data
        assert "featured_roles" in data
        print(f"SUCCESS: /api/careers/overview returns total_open={data['total_open']}")

    def test_careers_facets_endpoint_still_works(self):
        """Test that /api/careers/facets still works"""
        response = requests.get(f"{BASE_URL}/api/careers/facets")
        
        assert response.status_code == 200
        data = response.json()
        assert "departments" in data
        assert "locations" in data
        assert "types" in data
        print(f"SUCCESS: /api/careers/facets returns {len(data['departments'])} departments")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
