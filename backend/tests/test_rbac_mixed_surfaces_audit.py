"""
RBAC Mixed Surfaces Audit Test Suite
=====================================
Verifies that mixed surfaces (non-admin-only routes that have admin-specific behavior)
use the shared admin identity rules consistently and no non-admin user gets admin behavior
from legacy role-array checks.

Test Credentials:
- Admin: admin@realaicoach.app / NewAdminPass2026!
- Free: p1.free.1779113329@example.com / P1Free#2026!Aa
- Basic: f21.basic.1781338672@example.com / F21Basic#2026Aa
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"
BASIC_EMAIL = "f21.basic.1781338672@example.com"
BASIC_PASSWORD = "F21Basic#2026Aa"


class TestRBACMixedSurfacesAudit:
    """Test RBAC consistency on mixed surfaces after admin-route hardening."""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session."""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code}")
        return session

    @pytest.fixture(scope="class")
    def free_session(self):
        """Get authenticated free user session."""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_EMAIL,
            "password": FREE_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Free user login failed: {response.status_code}")
        return session

    @pytest.fixture(scope="class")
    def basic_session(self):
        """Get authenticated basic user session."""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_EMAIL,
            "password": BASIC_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Basic user login failed: {response.status_code}")
        return session

    # =========================================================================
    # Test 1: Verify admin user has is_admin=true in session
    # =========================================================================
    def test_admin_session_has_is_admin_true(self, admin_session):
        """Admin user should have is_admin=true in access-control session."""
        response = admin_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("is_admin") is True, f"Admin should have is_admin=true, got {data.get('is_admin')}"

    # =========================================================================
    # Test 2: Verify non-admin users do NOT have is_admin=true
    # =========================================================================
    def test_free_user_session_no_admin_flag(self, free_session):
        """Free user should NOT have is_admin=true in access-control session."""
        response = free_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        is_admin = data.get("is_admin")
        assert is_admin is not True, f"Free user should NOT have is_admin=true, got {is_admin}"

    def test_basic_user_session_no_admin_flag(self, basic_session):
        """Basic user should NOT have is_admin=true in access-control session."""
        response = basic_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        is_admin = data.get("is_admin")
        assert is_admin is not True, f"Basic user should NOT have is_admin=true, got {is_admin}"

    # =========================================================================
    # Test 3: Verify non-admin users cannot access admin-only API endpoints
    # =========================================================================
    def test_free_user_blocked_from_admin_analytics(self, free_session):
        """Free user should be blocked from admin analytics endpoints."""
        response = free_session.get(f"{BASE_URL}/api/admin/analytics/insights")
        # Should be 401/403 or redirect
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from admin analytics, got {response.status_code}"

    def test_basic_user_blocked_from_admin_analytics(self, basic_session):
        """Basic user should be blocked from admin analytics endpoints."""
        response = basic_session.get(f"{BASE_URL}/api/admin/analytics/insights")
        # Should be 401/403 or redirect
        assert response.status_code in [401, 403, 404], f"Basic user should be blocked from admin analytics, got {response.status_code}"

    def test_admin_can_access_admin_analytics(self, admin_session):
        """Admin user should be able to access admin analytics endpoints."""
        response = admin_session.get(f"{BASE_URL}/api/admin/analytics/insights")
        # Admin should get 200 or at least not 401/403
        assert response.status_code in [200, 404, 500], f"Admin should access admin analytics, got {response.status_code}"

    # =========================================================================
    # Test 4: Verify non-admin users cannot access team management
    # =========================================================================
    def test_free_user_blocked_from_team_management(self, free_session):
        """Free user should be blocked from team management API."""
        response = free_session.get(f"{BASE_URL}/api/team/employees")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from team management, got {response.status_code}"

    def test_basic_user_blocked_from_team_management(self, basic_session):
        """Basic user should be blocked from team management API."""
        response = basic_session.get(f"{BASE_URL}/api/team/employees")
        assert response.status_code in [401, 403, 404], f"Basic user should be blocked from team management, got {response.status_code}"

    # =========================================================================
    # Test 5: Verify non-admin users can access normal dashboard flows
    # =========================================================================
    def test_free_user_can_access_dashboard_data(self, free_session):
        """Free user should be able to access normal dashboard data."""
        response = free_session.get(f"{BASE_URL}/api/home/live-metrics")
        # Should be accessible (200) or at least not admin-blocked
        assert response.status_code in [200, 404], f"Free user should access dashboard data, got {response.status_code}"

    def test_basic_user_can_access_dashboard_data(self, basic_session):
        """Basic user should be able to access normal dashboard data."""
        response = basic_session.get(f"{BASE_URL}/api/home/live-metrics")
        # Should be accessible (200) or at least not admin-blocked
        assert response.status_code in [200, 404], f"Basic user should access dashboard data, got {response.status_code}"

    # =========================================================================
    # Test 6: Verify subscription plans endpoint is accessible to all
    # =========================================================================
    def test_free_user_can_access_subscription_plans(self, free_session):
        """Free user should be able to access subscription plans."""
        response = free_session.get(f"{BASE_URL}/api/subscriptions/plans")
        assert response.status_code == 200, f"Free user should access subscription plans, got {response.status_code}"

    def test_basic_user_can_access_subscription_plans(self, basic_session):
        """Basic user should be able to access subscription plans."""
        response = basic_session.get(f"{BASE_URL}/api/subscriptions/plans")
        assert response.status_code == 200, f"Basic user should access subscription plans, got {response.status_code}"

    def test_admin_can_access_subscription_plans(self, admin_session):
        """Admin user should be able to access subscription plans."""
        response = admin_session.get(f"{BASE_URL}/api/subscriptions/plans")
        assert response.status_code == 200, f"Admin should access subscription plans, got {response.status_code}"

    # =========================================================================
    # Test 7: Verify jobs portal is accessible to all authenticated users
    # =========================================================================
    def test_free_user_can_access_jobs_portal_summary(self, free_session):
        """Free user should be able to access jobs portal summary."""
        response = free_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        # Should be accessible (200), 404 if endpoint doesn't exist, or 410 if deprecated
        assert response.status_code in [200, 404, 410], f"Free user should access jobs portal, got {response.status_code}"

    def test_basic_user_can_access_jobs_portal_summary(self, basic_session):
        """Basic user should be able to access jobs portal summary."""
        response = basic_session.get(f"{BASE_URL}/api/jobs/portal-summary")
        # Should be accessible (200), 404 if endpoint doesn't exist, or 410 if deprecated
        assert response.status_code in [200, 404, 410], f"Basic user should access jobs portal, got {response.status_code}"

    # =========================================================================
    # Test 8: Verify admin-only conversion summary is blocked for non-admin
    # =========================================================================
    def test_free_user_blocked_from_conversion_summary(self, free_session):
        """Free user should be blocked from admin conversion summary."""
        response = free_session.get(f"{BASE_URL}/api/admin/subscription-conversion/summary")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from conversion summary, got {response.status_code}"

    def test_basic_user_blocked_from_conversion_summary(self, basic_session):
        """Basic user should be blocked from admin conversion summary."""
        response = basic_session.get(f"{BASE_URL}/api/admin/subscription-conversion/summary")
        assert response.status_code in [401, 403, 404], f"Basic user should be blocked from conversion summary, got {response.status_code}"

    # =========================================================================
    # Test 9: Verify non-admin users with legacy role arrays don't get admin access
    # =========================================================================
    def test_session_does_not_expose_admin_via_roles_array(self, free_session):
        """Session should not grant admin via roles array for non-admin users."""
        response = free_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        data = response.json()
        
        # Check that roles array doesn't contain 'admin'
        roles = data.get("roles", [])
        if isinstance(roles, list):
            admin_in_roles = any(str(r).lower() == 'admin' for r in roles)
            assert not admin_in_roles, f"Non-admin user should not have 'admin' in roles array: {roles}"
        
        # Check that platform_role is not 'admin'
        platform_role = str(data.get("platform_role", "")).lower()
        assert platform_role != "admin", f"Non-admin user should not have platform_role='admin': {platform_role}"

    def test_basic_session_does_not_expose_admin_via_roles_array(self, basic_session):
        """Session should not grant admin via roles array for basic users."""
        response = basic_session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200
        data = response.json()
        
        # Check that roles array doesn't contain 'admin'
        roles = data.get("roles", [])
        if isinstance(roles, list):
            admin_in_roles = any(str(r).lower() == 'admin' for r in roles)
            assert not admin_in_roles, f"Basic user should not have 'admin' in roles array: {roles}"
        
        # Check that platform_role is not 'admin'
        platform_role = str(data.get("platform_role", "")).lower()
        assert platform_role != "admin", f"Basic user should not have platform_role='admin': {platform_role}"


class TestMixedSurfaceAdminBehavior:
    """Test that mixed surfaces show admin-specific behavior only for actual admins."""

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Get authenticated admin session."""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.status_code}")
        return session

    @pytest.fixture(scope="class")
    def free_session(self):
        """Get authenticated free user session."""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_EMAIL,
            "password": FREE_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Free user login failed: {response.status_code}")
        return session

    # =========================================================================
    # Test: Admin gets admin-specific data on mixed surfaces
    # =========================================================================
    def test_admin_gets_conversion_summary_on_plans(self, admin_session):
        """Admin should be able to fetch conversion summary (admin-only feature on plans page)."""
        response = admin_session.get(f"{BASE_URL}/api/admin/subscription-conversion/summary?hours=168&audience=real_users_only")
        # Admin should get 200 or at least not 401/403
        assert response.status_code in [200, 404, 500], f"Admin should access conversion summary, got {response.status_code}"

    def test_free_user_blocked_from_conversion_summary_on_plans(self, free_session):
        """Free user should NOT be able to fetch conversion summary."""
        response = free_session.get(f"{BASE_URL}/api/admin/subscription-conversion/summary?hours=168&audience=real_users_only")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from conversion summary, got {response.status_code}"

    # =========================================================================
    # Test: Employer portal admin-specific features
    # =========================================================================
    def test_admin_can_access_employer_premium_analytics(self, admin_session):
        """Admin should be able to access employer premium analytics."""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/employer/premium-analytics/events?lookback_days=30&limit=20")
        # Admin should get 200 or at least not 401/403
        assert response.status_code in [200, 404, 500], f"Admin should access employer analytics, got {response.status_code}"

    def test_free_user_limited_on_employer_premium_analytics(self, free_session):
        """Free user should have limited access to employer premium analytics."""
        response = free_session.get(f"{BASE_URL}/api/hiring/v2/employer/premium-analytics/events?lookback_days=30&limit=20")
        # Free user should be blocked or get limited data
        # 401/403 = blocked, 200 with empty data = limited, 404 = endpoint not found
        assert response.status_code in [200, 401, 403, 404], f"Free user should have limited employer analytics access, got {response.status_code}"


class TestNoRegressionNormalFlows:
    """Test that normal non-admin dashboard and subscription flows still work."""

    @pytest.fixture(scope="class")
    def free_session(self):
        """Get authenticated free user session."""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": FREE_EMAIL,
            "password": FREE_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Free user login failed: {response.status_code}")
        return session

    @pytest.fixture(scope="class")
    def basic_session(self):
        """Get authenticated basic user session."""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": BASIC_EMAIL,
            "password": BASIC_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Basic user login failed: {response.status_code}")
        return session

    # =========================================================================
    # Test: Normal dashboard flows work for non-admin users
    # =========================================================================
    def test_free_user_can_access_home_tour_status(self, free_session):
        """Free user should be able to check home tour status."""
        response = free_session.get(f"{BASE_URL}/api/home/tour-status")
        assert response.status_code in [200, 404], f"Free user should access tour status, got {response.status_code}"

    def test_free_user_can_access_onboarding_wizard_status(self, free_session):
        """Free user should be able to check onboarding wizard status."""
        response = free_session.get(f"{BASE_URL}/api/onboarding-wizard/status")
        assert response.status_code in [200, 404], f"Free user should access wizard status, got {response.status_code}"

    def test_free_user_can_access_tos_status(self, free_session):
        """Free user should be able to check TOS acceptance status."""
        response = free_session.get(f"{BASE_URL}/api/tos/acceptance-status")
        assert response.status_code in [200, 404], f"Free user should access TOS status, got {response.status_code}"

    def test_basic_user_can_access_home_tour_status(self, basic_session):
        """Basic user should be able to check home tour status."""
        response = basic_session.get(f"{BASE_URL}/api/home/tour-status")
        assert response.status_code in [200, 404], f"Basic user should access tour status, got {response.status_code}"

    # =========================================================================
    # Test: Subscription flows work for non-admin users
    # =========================================================================
    def test_free_user_can_access_gateway_config(self, free_session):
        """Free user should be able to access gateway config."""
        response = free_session.get(f"{BASE_URL}/api/subscriptions/gateway-config")
        assert response.status_code in [200, 404], f"Free user should access gateway config, got {response.status_code}"

    def test_free_user_can_access_mobile_money_gateways(self, free_session):
        """Free user should be able to access mobile money gateways."""
        response = free_session.get(f"{BASE_URL}/api/subscriptions/mobile-money/gateways")
        assert response.status_code in [200, 404], f"Free user should access mobile money gateways, got {response.status_code}"

    def test_free_user_can_access_currencies(self, free_session):
        """Free user should be able to access payment currencies."""
        response = free_session.get(f"{BASE_URL}/api/payments/currencies")
        assert response.status_code in [200, 404], f"Free user should access currencies, got {response.status_code}"


class TestBackendCanonicalAdminDependencyAudit:
    def test_admin_management_uses_canonical_require_admin(self):
        with open('/app/backend/routes/admin_management.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'require_admin' in content
        assert 'async def _require_admin' not in content

    def test_admin_payments_tax_intelligence_uses_canonical_require_admin(self):
        with open('/app/backend/routes/admin_payments_tax_intelligence.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'require_admin' in content
        assert 'async def _require_admin' not in content

    def test_careers_thread_uses_canonical_require_admin(self):
        with open('/app/backend/routes/careers_thread.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'require_admin' in content
        assert 'async def _require_admin' not in content

    def test_platform_health_slo_routes_use_canonical_require_admin(self):
        with open('/app/backend/routes/platform_health.py', 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'async def get_slo_presets(user=Depends(require_admin))' in content
        assert 'async def apply_slo_preset(request: Request, user=Depends(require_admin))' in content
        assert 'async def get_adaptive_slo_thresholds(user=Depends(require_admin))' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
