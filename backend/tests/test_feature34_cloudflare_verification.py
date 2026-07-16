"""
Feature 34 (Book Meeting / My Agenda) - Cloudflare Verification & API Health Tests
Tests backend API health and validates Feature 34 routes remain functional.
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
BASIC_USER_EMAIL = "f22.basic.20260613@example.com"
BASIC_USER_PASSWORD = "F22Basic#2026Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestFeature34BackendHealth:
    """Feature 34 backend API health verification"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_health_endpoint(self):
        """Test backend health endpoint is accessible"""
        response = self.session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"Health check: {data}")
    
    def test_basic_user_login(self):
        """Test basic user can login successfully"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_USER_EMAIL,
            "password": BASIC_USER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("user_id") is not None
        assert data.get("subscription_plan") == "basic"
        print(f"Basic user login: user_id={data.get('user_id')}, plan={data.get('subscription_plan')}")
        return data.get("user_id")
    
    def test_admin_user_login(self):
        """Test admin user can login successfully"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("user_id") is not None
        assert data.get("is_admin") == True
        print(f"Admin user login: user_id={data.get('user_id')}, is_admin={data.get('is_admin')}")
        return data.get("user_id")


class TestFeature34CalendarCoreRoutes:
    """Feature 34 calendar core routes (calendar_core.py)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session for basic user"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as basic user
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_USER_EMAIL,
            "password": BASIC_USER_PASSWORD
        })
        assert response.status_code == 200
        self.user_id = response.json().get("user_id")
    
    def test_calendar_status(self):
        """Test GET /api/calendar/status returns valid response"""
        response = self.session.get(f"{BASE_URL}/api/calendar/status")
        assert response.status_code == 200
        data = response.json()
        assert "google_available" in data
        assert "google_connected" in data
        assert "sync_mode" in data
        print(f"Calendar status: google_connected={data.get('google_connected')}, sync_mode={data.get('sync_mode')}")
    
    def test_calendar_events(self):
        """Test GET /api/calendar/events/{user_id} returns events list"""
        response = self.session.get(f"{BASE_URL}/api/calendar/events/{self.user_id}")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        print(f"Calendar events: count={len(data.get('events', []))}")
    
    def test_calendar_upcoming(self):
        """Test GET /api/calendar/upcoming/{user_id} returns upcoming events"""
        response = self.session.get(f"{BASE_URL}/api/calendar/upcoming/{self.user_id}?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data or isinstance(data, list)
        print("Upcoming events retrieved successfully")


class TestFeature34ReliabilityRoutes:
    """Feature 34 reliability routes (calendar_reliability.py)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session for basic user"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as basic user
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_USER_EMAIL,
            "password": BASIC_USER_PASSWORD
        })
        assert response.status_code == 200
        self.user_id = response.json().get("user_id")
    
    def test_reliability_snapshot(self):
        """Test GET /api/calendar/reliability/{user_id} returns metrics"""
        response = self.session.get(f"{BASE_URL}/api/calendar/reliability/{self.user_id}")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert data.get("user_id") == self.user_id
        assert "plan_scope" in data
        assert "sync_mode" in data
        assert "metrics" in data
        
        # Verify metrics structure
        metrics = data.get("metrics", {})
        required_metrics = [
            "conflict_events_30d", "conflicts_current_7d", "conflicts_previous_7d",
            "bookings_7d", "booking_pages_active", "booking_views_7d",
            "bookings_confirmed_7d", "reminder_success_rate_7d", "error_rate_7d",
            "booking_conversion_7d", "sync_total_7d", "sync_error_rate_7d", "sync_latency_p95_ms"
        ]
        for metric in required_metrics:
            assert metric in metrics, f"Missing metric: {metric}"
        
        print(f"Reliability snapshot: plan={data.get('plan_scope')}, sync_mode={data.get('sync_mode')}")
        print(f"Metrics: conflicts_30d={metrics.get('conflict_events_30d')}, error_rate={metrics.get('error_rate_7d')}")
    
    def test_observability_endpoint(self):
        """Test GET /api/calendar/observability/{user_id} returns combined data"""
        response = self.session.get(f"{BASE_URL}/api/calendar/observability/{self.user_id}")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("feature") == "book-meeting"
        assert "summary" in data
        assert "reliability" in data
        print(f"Observability endpoint: feature={data.get('feature')}")
    
    def test_release_gate_standard_profile(self):
        """Test GET /api/calendar/release-gate/{user_id}?profile=standard"""
        response = self.session.get(f"{BASE_URL}/api/calendar/release-gate/{self.user_id}?profile=standard")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("feature") == "book-meeting"
        assert data.get("user_id") == self.user_id
        assert data.get("profile") == "standard"
        assert "snapshot" in data
        assert "gate" in data
        
        gate = data.get("gate", {})
        assert "decision" in gate
        assert gate.get("decision") in ["go", "no-go"]
        assert "checks" in gate
        assert "thresholds" in gate
        
        print(f"Release gate (standard): decision={gate.get('decision')}, checks={gate.get('checks')}")
    
    def test_release_gate_strict_profile(self):
        """Test GET /api/calendar/release-gate/{user_id}?profile=strict"""
        response = self.session.get(f"{BASE_URL}/api/calendar/release-gate/{self.user_id}?profile=strict")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("profile") == "strict"
        gate = data.get("gate", {})
        thresholds = gate.get("thresholds", {})
        
        # Strict profile should have tighter thresholds
        assert thresholds.get("max_conflicts_30d") == 4
        assert thresholds.get("min_reminder_success_rate") == 0.985
        print(f"Release gate (strict): thresholds={thresholds}")
    
    def test_release_gate_lenient_profile(self):
        """Test GET /api/calendar/release-gate/{user_id}?profile=lenient"""
        response = self.session.get(f"{BASE_URL}/api/calendar/release-gate/{self.user_id}?profile=lenient")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("profile") == "lenient"
        gate = data.get("gate", {})
        thresholds = gate.get("thresholds", {})
        
        # Lenient profile should have relaxed thresholds
        assert thresholds.get("max_conflicts_30d") == 16
        assert thresholds.get("min_reminder_success_rate") == 0.9
        print(f"Release gate (lenient): thresholds={thresholds}")


class TestFeature34AdminRoutes:
    """Feature 34 admin routes (calendar_reliability.py)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session for admin user"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin user
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        self.user_id = response.json().get("user_id")
    
    def test_admin_release_gate_profile_get(self):
        """Test GET /api/admin/calendar/release-gate/profile"""
        response = self.session.get(f"{BASE_URL}/api/admin/calendar/release-gate/profile")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("success") == True
        assert data.get("feature") == "book-meeting"
        assert "active_profile" in data
        assert data.get("active_profile") in ["strict", "standard", "lenient"]
        assert "profiles" in data
        
        print(f"Admin release gate profile: active={data.get('active_profile')}")
    
    def test_admin_release_gate_evaluate(self):
        """Test GET /api/admin/calendar/release-gate/evaluate"""
        response = self.session.get(f"{BASE_URL}/api/admin/calendar/release-gate/evaluate")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("feature") == "book-meeting"
        assert "profile" in data
        assert "decision" in data
        assert data.get("decision") in ["go", "no-go"]
        assert "go_rate" in data
        assert "summary" in data
        
        summary = data.get("summary", {})
        assert "users_evaluated" in summary
        assert "go_count" in summary
        assert "no_go_count" in summary
        
        print(f"Admin release gate evaluate: decision={data.get('decision')}, go_rate={data.get('go_rate')}")
    
    def test_admin_reliability_dashboard(self):
        """Test GET /api/admin/calendar/reliability"""
        response = self.session.get(f"{BASE_URL}/api/admin/calendar/reliability")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("feature") == "book-meeting"
        assert "profile" in data
        assert "summary" in data
        assert "rows" in data
        
        summary = data.get("summary", {})
        assert "users_evaluated" in summary
        assert "go_count" in summary
        assert "no_go_count" in summary
        assert "go_rate" in summary
        
        print(f"Admin reliability dashboard: users_evaluated={summary.get('users_evaluated')}, go_rate={summary.get('go_rate')}")


class TestFeature34AIRoutes:
    """Feature 34 AI routes (calendar_ai.py)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session for basic user"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as basic user
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_USER_EMAIL,
            "password": BASIC_USER_PASSWORD
        })
        assert response.status_code == 200
        self.user_id = response.json().get("user_id")
    
    def test_smart_suggestions(self):
        """Test GET /api/calendar/smart-suggestions/{user_id}"""
        response = self.session.get(f"{BASE_URL}/api/calendar/smart-suggestions/{self.user_id}")
        # May return 200 or 403 depending on tier
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            print(f"Smart suggestions: {data}")
        else:
            print("Smart suggestions: tier-gated (403)")


class TestFeature34CrossUserProtection:
    """Feature 34 cross-user protection tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session for basic user"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as basic user
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_USER_EMAIL,
            "password": BASIC_USER_PASSWORD
        })
        assert response.status_code == 200
        self.user_id = response.json().get("user_id")
    
    def test_cross_user_events_blocked(self):
        """Test cross-user access to events is blocked"""
        other_user_id = "user_other_test_12345"
        response = self.session.get(f"{BASE_URL}/api/calendar/events/{other_user_id}")
        assert response.status_code == 403
        print("Cross-user events access: correctly blocked (403)")
    
    def test_cross_user_reliability_blocked(self):
        """Test cross-user access to reliability is blocked"""
        other_user_id = "user_other_test_12345"
        response = self.session.get(f"{BASE_URL}/api/calendar/reliability/{other_user_id}")
        assert response.status_code == 403
        print("Cross-user reliability access: correctly blocked (403)")
    
    def test_cross_user_release_gate_blocked(self):
        """Test cross-user access to release-gate is blocked"""
        other_user_id = "user_other_test_12345"
        response = self.session.get(f"{BASE_URL}/api/calendar/release-gate/{other_user_id}")
        assert response.status_code == 403
        print("Cross-user release-gate access: correctly blocked (403)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
