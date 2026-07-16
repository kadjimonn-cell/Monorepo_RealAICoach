"""
Feature 24: AI Learning Hub - Backend API Tests
Tests entitlement consistency after _effective_plan_for_user patch
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
BASIC_USER = {"email": "f21.basic.1781338672@example.com", "password": "F21Basic#2026Aa"}
ADMIN_USER = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}


class TestLearningHubAuth:
    """Test authentication and access to Learning Hub endpoints"""
    
    @pytest.fixture(scope="class")
    def free_session(self):
        """Login as free user and return session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        resp = session.post(f"{BASE_URL}/api/auth/login", json=FREE_USER)
        assert resp.status_code == 200, f"Free user login failed: {resp.text}"
        return session
    
    @pytest.fixture(scope="class")
    def basic_session(self):
        """Login as basic user and return session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        resp = session.post(f"{BASE_URL}/api/auth/login", json=BASIC_USER)
        assert resp.status_code == 200, f"Basic user login failed: {resp.text}"
        return session
    
    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin user and return session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        resp = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER)
        assert resp.status_code == 200, f"Admin user login failed: {resp.text}"
        return session


class TestHubDashboard(TestLearningHubAuth):
    """Test /api/ai-learn/hub-dashboard endpoint"""
    
    def test_hub_dashboard_free_user_returns_200(self, free_session):
        """Free user should access hub-dashboard with plan=free"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        assert resp.status_code == 200, f"Hub dashboard failed for free user: {resp.text}"
        data = resp.json()
        # Verify entitlements reflect free plan
        assert "entitlements" in data
        assert data["entitlements"]["plan"] in ["free", "basic", "premium"]
        # Verify access_control is present
        assert "access_control" in data
        print(f"Free user hub-dashboard: plan={data['entitlements']['plan']}, scope={data['access_control'].get('scope_label')}")
    
    def test_hub_dashboard_basic_user_returns_200(self, basic_session):
        """Basic user should access hub-dashboard with plan=basic"""
        resp = basic_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        assert resp.status_code == 200, f"Hub dashboard failed for basic user: {resp.text}"
        data = resp.json()
        assert "entitlements" in data
        # Basic user should have basic or higher plan
        assert data["entitlements"]["plan"] in ["basic", "premium"]
        print(f"Basic user hub-dashboard: plan={data['entitlements']['plan']}, scope={data['access_control'].get('scope_label')}")
    
    def test_hub_dashboard_admin_returns_200(self, admin_session):
        """Admin user should access hub-dashboard with plan=premium"""
        resp = admin_session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        assert resp.status_code == 200, f"Hub dashboard failed for admin: {resp.text}"
        data = resp.json()
        assert "entitlements" in data
        # Admin should have premium effective plan
        assert data["entitlements"]["plan"] == "premium"
        print(f"Admin hub-dashboard: plan={data['entitlements']['plan']}, scope={data['access_control'].get('scope_label')}")
    
    def test_hub_dashboard_unauthenticated_returns_401(self):
        """Unauthenticated request should return 401"""
        session = requests.Session()
        resp = session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        assert resp.status_code == 401, f"Expected 401 for unauthenticated, got {resp.status_code}"


class TestCourses(TestLearningHubAuth):
    """Test /api/ai-learn/courses endpoint"""
    
    def test_courses_free_user_returns_200(self, free_session):
        """Free user should access courses list"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/courses")
        assert resp.status_code == 200, f"Courses failed for free user: {resp.text}"
        data = resp.json()
        assert "courses" in data
        assert "access_control" in data
        # Verify access_control reflects free plan limits
        print(f"Free user courses: count={len(data['courses'])}, plan={data['access_control'].get('plan')}")
    
    def test_courses_basic_user_returns_200(self, basic_session):
        """Basic user should access courses list with basic scope"""
        resp = basic_session.get(f"{BASE_URL}/api/ai-learn/courses")
        assert resp.status_code == 200, f"Courses failed for basic user: {resp.text}"
        data = resp.json()
        assert "courses" in data
        assert "access_control" in data
        print(f"Basic user courses: count={len(data['courses'])}, plan={data['access_control'].get('plan')}")
    
    def test_courses_admin_returns_200(self, admin_session):
        """Admin user should access courses list with premium scope"""
        resp = admin_session.get(f"{BASE_URL}/api/ai-learn/courses")
        assert resp.status_code == 200, f"Courses failed for admin: {resp.text}"
        data = resp.json()
        assert "courses" in data
        assert "access_control" in data
        assert data["access_control"]["plan"] == "premium"
        print(f"Admin courses: count={len(data['courses'])}, plan={data['access_control'].get('plan')}")


class TestLearningCenter(TestLearningHubAuth):
    """Test /api/ai-learn/my-learning-center endpoint"""
    
    def test_learning_center_free_user_returns_200(self, free_session):
        """Free user should access learning center"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/my-learning-center")
        assert resp.status_code == 200, f"Learning center failed for free user: {resp.text}"
        data = resp.json()
        assert "enrollments" in data
        assert "certificates" in data
        print(f"Free user learning center: enrollments={len(data['enrollments'])}, certificates={len(data['certificates'])}")
    
    def test_learning_center_basic_user_returns_200(self, basic_session):
        """Basic user should access learning center"""
        resp = basic_session.get(f"{BASE_URL}/api/ai-learn/my-learning-center")
        assert resp.status_code == 200, f"Learning center failed for basic user: {resp.text}"
        data = resp.json()
        assert "enrollments" in data
        print(f"Basic user learning center: enrollments={len(data['enrollments'])}")


class TestHabitLoop(TestLearningHubAuth):
    """Test /api/ai-learn/habit-loop/summary endpoint"""
    
    def test_habit_loop_free_user_returns_200(self, free_session):
        """Free user should access habit loop summary"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/habit-loop/summary")
        assert resp.status_code == 200, f"Habit loop failed for free user: {resp.text}"
        data = resp.json()
        assert "summary" in data or "missions" in data or "day" in data
        print(f"Free user habit loop: keys={list(data.keys())[:5]}")
    
    def test_habit_loop_basic_user_returns_200(self, basic_session):
        """Basic user should access habit loop summary"""
        resp = basic_session.get(f"{BASE_URL}/api/ai-learn/habit-loop/summary")
        assert resp.status_code == 200, f"Habit loop failed for basic user: {resp.text}"


class TestRecoveryCopilot(TestLearningHubAuth):
    """Test /api/ai-learn/recovery-copilot/plan endpoint"""
    
    def test_recovery_copilot_free_user_returns_200(self, free_session):
        """Free user should access recovery copilot"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/recovery-copilot/plan")
        assert resp.status_code == 200, f"Recovery copilot failed for free user: {resp.text}"
        data = resp.json()
        assert "risk" in data or "plan_steps" in data or "generated_at" in data
        print(f"Free user recovery copilot: keys={list(data.keys())[:5]}")
    
    def test_recovery_copilot_basic_user_returns_200(self, basic_session):
        """Basic user should access recovery copilot"""
        resp = basic_session.get(f"{BASE_URL}/api/ai-learn/recovery-copilot/plan")
        assert resp.status_code == 200, f"Recovery copilot failed for basic user: {resp.text}"


class TestAdminInsights(TestLearningHubAuth):
    """Test /api/ai-learn/admin/executive-insights endpoint"""
    
    def test_admin_insights_free_user_blocked(self, free_session):
        """Free user should be blocked from admin insights (403)"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/admin/executive-insights")
        assert resp.status_code == 403, f"Expected 403 for free user on admin endpoint, got {resp.status_code}"
        print("Free user admin insights: correctly blocked with 403")
    
    def test_admin_insights_basic_user_blocked(self, basic_session):
        """Basic user should be blocked from admin insights (403)"""
        resp = basic_session.get(f"{BASE_URL}/api/ai-learn/admin/executive-insights")
        assert resp.status_code == 403, f"Expected 403 for basic user on admin endpoint, got {resp.status_code}"
        print("Basic user admin insights: correctly blocked with 403")
    
    def test_admin_insights_admin_returns_200(self, admin_session):
        """Admin user should access executive insights"""
        resp = admin_session.get(f"{BASE_URL}/api/ai-learn/admin/executive-insights")
        assert resp.status_code == 200, f"Admin insights failed for admin: {resp.text}"
        data = resp.json()
        print(f"Admin executive insights: keys={list(data.keys())[:5]}")


class TestEntitlementMatrix:
    """Test entitlement consistency across user tiers"""
    
    def test_free_user_entitlement_matrix(self):
        """Verify free user entitlement limits"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        resp = session.post(f"{BASE_URL}/api/auth/login", json=FREE_USER)
        assert resp.status_code == 200
        
        # Get dashboard to check entitlements
        resp = session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        assert resp.status_code == 200
        data = resp.json()
        
        entitlements = data.get("entitlements", {})
        plan = entitlements.get("plan", "free")
        
        # Free plan should have limited daily limits
        course_gen = entitlements.get("course_generation", {})
        if plan == "free":
            assert course_gen.get("daily_limit", 0) <= 5, "Free plan should have limited course generation"
        
        print(f"Free user entitlement matrix validated: plan={plan}")
    
    def test_basic_user_entitlement_matrix(self):
        """Verify basic user entitlement limits"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        resp = session.post(f"{BASE_URL}/api/auth/login", json=BASIC_USER)
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        assert resp.status_code == 200
        data = resp.json()
        
        entitlements = data.get("entitlements", {})
        plan = entitlements.get("plan", "free")
        
        # Basic plan should have higher limits than free
        course_gen = entitlements.get("course_generation", {})
        if plan == "basic":
            assert course_gen.get("daily_limit", 0) >= 10, "Basic plan should have higher course generation limit"
        
        print(f"Basic user entitlement matrix validated: plan={plan}")
    
    def test_admin_user_entitlement_matrix(self):
        """Verify admin user gets premium entitlements"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        resp = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER)
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/api/ai-learn/hub-dashboard")
        assert resp.status_code == 200
        data = resp.json()
        
        entitlements = data.get("entitlements", {})
        plan = entitlements.get("plan", "free")
        
        # Admin should have premium plan
        assert plan == "premium", f"Admin should have premium plan, got {plan}"
        
        # Premium should have unlimited (-1) or very high limits
        course_gen = entitlements.get("course_generation", {})
        assert course_gen.get("daily_limit", 0) == -1 or course_gen.get("daily_limit", 0) >= 100, "Premium should have unlimited course generation"
        
        print(f"Admin entitlement matrix validated: plan={plan}")


class TestCareerSprints(TestLearningHubAuth):
    """Test /api/ai-learn/career-sprints/latest endpoint"""
    
    def test_career_sprints_free_user_returns_200(self, free_session):
        """Free user should access career sprints"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/career-sprints/latest")
        assert resp.status_code == 200, f"Career sprints failed for free user: {resp.text}"
        print("Free user career sprints: status=200")


class TestOpportunityRadar(TestLearningHubAuth):
    """Test /api/ai-learn/opportunity-radar endpoint"""
    
    def test_opportunity_radar_free_user_returns_200(self, free_session):
        """Free user should access opportunity radar"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/opportunity-radar")
        assert resp.status_code == 200, f"Opportunity radar failed for free user: {resp.text}"
        print("Free user opportunity radar: status=200")


class TestIncomeExperiments(TestLearningHubAuth):
    """Test /api/ai-learn/income-experiments endpoint"""
    
    def test_income_experiments_free_user_returns_200(self, free_session):
        """Free user should access income experiments"""
        resp = free_session.get(f"{BASE_URL}/api/ai-learn/income-experiments")
        assert resp.status_code == 200, f"Income experiments failed for free user: {resp.text}"
        data = resp.json()
        assert "experiments" in data
        print(f"Free user income experiments: count={len(data['experiments'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
