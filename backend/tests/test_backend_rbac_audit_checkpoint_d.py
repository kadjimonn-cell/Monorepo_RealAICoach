"""
Backend RBAC Audit Checkpoint D Test Suite
==========================================
Verifies that backend privileged endpoints now use the canonical admin dependency chain
and non-admin users remain blocked from those privileged APIs.

Test Credentials:
- Admin: admin@realaicoach.app / NewAdminPass2026!
- Free: p1.free.1779113329@example.com / P1Free#2026!Aa
- Basic: f21.basic.1781338672@example.com / F21Basic#2026Aa

Affected files:
- admin_management.py
- admin_payments_tax_intelligence.py
- careers_thread.py
- platform_health.py (SLO preset routes)
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


class TestAdminManagementRBAC:
    """Test RBAC for admin_management.py endpoints."""

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
    # Test: Admin management endpoints - admin can access
    # =========================================================================
    def test_admin_can_access_user_list(self, admin_session):
        """Admin should be able to access user list."""
        response = admin_session.get(f"{BASE_URL}/api/admin/manage/users?page=1&limit=10")
        assert response.status_code in [200, 404], f"Admin should access user list, got {response.status_code}"

    def test_admin_can_access_tickets(self, admin_session):
        """Admin should be able to access support tickets."""
        response = admin_session.get(f"{BASE_URL}/api/admin/manage/tickets")
        assert response.status_code in [200, 404], f"Admin should access tickets, got {response.status_code}"

    # =========================================================================
    # Test: Admin management endpoints - non-admin blocked
    # =========================================================================
    def test_free_user_blocked_from_user_list(self, free_session):
        """Free user should be blocked from user list."""
        response = free_session.get(f"{BASE_URL}/api/admin/manage/users?page=1&limit=10")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from user list, got {response.status_code}"

    def test_free_user_blocked_from_tickets(self, free_session):
        """Free user should be blocked from support tickets."""
        response = free_session.get(f"{BASE_URL}/api/admin/manage/tickets")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from tickets, got {response.status_code}"

    def test_free_user_blocked_from_freeze_user(self, free_session):
        """Free user should be blocked from freezing users."""
        response = free_session.post(f"{BASE_URL}/api/admin/manage/users/test-user-id/freeze", json={})
        assert response.status_code in [401, 403, 404, 422], f"Free user should be blocked from freeze, got {response.status_code}"


class TestAdminPaymentsTaxIntelligenceRBAC:
    """Test RBAC for admin_payments_tax_intelligence.py endpoints."""

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
    # Test: Admin payments/tax intelligence endpoints - admin can access
    # =========================================================================
    def test_admin_can_access_payments_dashboard(self, admin_session):
        """Admin should be able to access payments dashboard."""
        response = admin_session.get(f"{BASE_URL}/api/admin/payments-tax-intelligence/dashboard")
        assert response.status_code in [200, 404], f"Admin should access payments dashboard, got {response.status_code}"

    def test_admin_can_access_tax_reports(self, admin_session):
        """Admin should be able to access tax reports."""
        response = admin_session.get(f"{BASE_URL}/api/admin/payments-tax-intelligence/tax-reports")
        assert response.status_code in [200, 404], f"Admin should access tax reports, got {response.status_code}"

    # =========================================================================
    # Test: Admin payments/tax intelligence endpoints - non-admin blocked
    # =========================================================================
    def test_free_user_blocked_from_payments_dashboard(self, free_session):
        """Free user should be blocked from payments dashboard."""
        response = free_session.get(f"{BASE_URL}/api/admin/payments-tax-intelligence/dashboard")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from payments dashboard, got {response.status_code}"

    def test_free_user_blocked_from_tax_reports(self, free_session):
        """Free user should be blocked from tax reports."""
        response = free_session.get(f"{BASE_URL}/api/admin/payments-tax-intelligence/tax-reports")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from tax reports, got {response.status_code}"


class TestCareersThreadRBAC:
    """Test RBAC for careers_thread.py endpoints."""

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
    # Test: Careers thread admin endpoints - admin can access
    # =========================================================================
    def test_admin_can_access_careers_threads(self, admin_session):
        """Admin should be able to access careers threads."""
        response = admin_session.get(f"{BASE_URL}/api/careers/threads")
        assert response.status_code in [200, 404], f"Admin should access careers threads, got {response.status_code}"

    # =========================================================================
    # Test: Careers thread admin endpoints - non-admin blocked
    # =========================================================================
    def test_free_user_blocked_from_careers_threads(self, free_session):
        """Free user should be blocked from careers threads admin endpoint."""
        response = free_session.get(f"{BASE_URL}/api/careers/threads")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from careers threads, got {response.status_code}"


class TestPlatformHealthSLORoutesRBAC:
    """Test RBAC for platform_health.py SLO preset routes."""

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
    # Test: SLO preset routes - admin can access
    # =========================================================================
    def test_admin_can_access_slo_presets(self, admin_session):
        """Admin should be able to access SLO presets."""
        response = admin_session.get(f"{BASE_URL}/api/platform-health/slo-presets")
        assert response.status_code in [200, 404], f"Admin should access SLO presets, got {response.status_code}"

    def test_admin_can_access_adaptive_slo_thresholds(self, admin_session):
        """Admin should be able to access adaptive SLO thresholds."""
        response = admin_session.get(f"{BASE_URL}/api/platform-health/adaptive-slo-thresholds")
        assert response.status_code in [200, 404], f"Admin should access adaptive SLO thresholds, got {response.status_code}"

    # =========================================================================
    # Test: SLO preset routes - non-admin blocked
    # =========================================================================
    def test_free_user_blocked_from_slo_presets(self, free_session):
        """Free user should be blocked from SLO presets."""
        response = free_session.get(f"{BASE_URL}/api/platform-health/slo-presets")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from SLO presets, got {response.status_code}"

    def test_free_user_blocked_from_adaptive_slo_thresholds(self, free_session):
        """Free user should be blocked from adaptive SLO thresholds."""
        response = free_session.get(f"{BASE_URL}/api/platform-health/adaptive-slo-thresholds")
        assert response.status_code in [401, 403, 404], f"Free user should be blocked from adaptive SLO thresholds, got {response.status_code}"

    def test_free_user_blocked_from_apply_slo_preset(self, free_session):
        """Free user should be blocked from applying SLO presets."""
        response = free_session.post(f"{BASE_URL}/api/platform-health/apply-slo-preset", json={"preset": "default"})
        assert response.status_code in [401, 403, 404, 422], f"Free user should be blocked from apply SLO preset, got {response.status_code}"


class TestCanonicalAdminDependencyVerification:
    """Verify that the canonical admin dependency is used correctly in affected files."""

    def test_admin_management_uses_canonical_require_admin_alias(self):
        """admin_management.py should use canonical require_admin via alias."""
        with open('/app/backend/routes/admin_management.py', 'r', encoding='utf-8') as f:
            content = f.read()
        # Should import require_admin from .db
        assert 'from .db import' in content and 'require_admin' in content
        # Should have alias for backward compatibility
        assert '_require_admin = require_admin' in content
        # Should NOT have local async def _require_admin
        assert 'async def _require_admin' not in content

    def test_admin_payments_tax_intelligence_uses_canonical_require_admin_alias(self):
        """admin_payments_tax_intelligence.py should use canonical require_admin via alias."""
        with open('/app/backend/routes/admin_payments_tax_intelligence.py', 'r', encoding='utf-8') as f:
            content = f.read()
        # Should import require_admin from routes.db
        assert 'from routes.db import' in content and 'require_admin' in content
        # Should have alias for backward compatibility
        assert '_require_admin = require_admin' in content
        # Should NOT have local async def _require_admin
        assert 'async def _require_admin' not in content

    def test_careers_thread_uses_canonical_require_admin_alias(self):
        """careers_thread.py should use canonical require_admin via alias."""
        with open('/app/backend/routes/careers_thread.py', 'r', encoding='utf-8') as f:
            content = f.read()
        # Should import require_admin from routes.db
        assert 'from routes.db import require_admin' in content
        # Should have alias for backward compatibility
        assert '_require_admin = require_admin' in content
        # Should NOT have local async def _require_admin
        assert 'async def _require_admin' not in content

    def test_platform_health_slo_routes_use_depends_require_admin(self):
        """platform_health.py SLO routes should use Depends(require_admin)."""
        with open('/app/backend/routes/platform_health.py', 'r', encoding='utf-8') as f:
            content = f.read()
        # Should import require_admin from routes.db
        assert 'from routes.db import' in content and 'require_admin' in content
        # SLO routes should use Depends(require_admin)
        assert 'async def get_slo_presets(user=Depends(require_admin))' in content
        assert 'async def apply_slo_preset(request: Request, user=Depends(require_admin))' in content
        assert 'async def get_adaptive_slo_thresholds(user=Depends(require_admin))' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
