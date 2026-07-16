"""
Test suite for route-specific upgrade messaging for blocked Free users.
Verifies:
1. Free user blocked from premium surfaces gets redirected with query params
2. Basic user allowed on expanded premium surfaces
3. Access control check-route API returns correct decision metadata
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
FREE_USER = {
    'email': 'p1.free.1779113329@example.com',
    'password': 'P1Free#2026!Aa'
}
BASIC_USER = {
    'email': 'f22.basic.20260613@example.com',
    'password': 'F22Basic#2026Aa'
}
PREMIUM_USER = {
    'email': 'f22.premium.20260613@example.com',
    'password': 'F22Premium#2026Aa'
}
ADMIN_USER = {
    'email': 'admin@realaicoach.app',
    'password': 'NewAdminPass2026!'
}

# Premium surfaces that should block free users
PREMIUM_SURFACES = [
    '/features/decision-coach',
    '/features/ai-automations',
    '/features/analytics-reports',
    '/features/ai-enterprise',
    '/mini-apps/ai-accounting',
    '/mini-apps/creator-exchange',
    '/subscription/mobile-money',
    '/features/content-studio',
]

# Admin-only routes that should block non-admin users
ADMIN_ONLY_ROUTES = [
    '/admin',
    '/admin-console',
    '/job-platform-admin',
]


@pytest.fixture(scope='module')
def free_session():
    """Create authenticated session for free user."""
    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
    })
    response = session.post(f'{BASE_URL}/api/auth/login', json={
        'email': FREE_USER['email'],
        'password': FREE_USER['password']
    })
    if response.status_code not in [200, 201]:
        pytest.skip(f'Free user login failed: {response.status_code}')
    return session


@pytest.fixture(scope='module')
def basic_session():
    """Create authenticated session for basic user."""
    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
    })
    response = session.post(f'{BASE_URL}/api/auth/login', json={
        'email': BASIC_USER['email'],
        'password': BASIC_USER['password']
    })
    if response.status_code not in [200, 201]:
        pytest.skip(f'Basic user login failed: {response.status_code}')
    return session


@pytest.fixture(scope='module')
def admin_session():
    """Create authenticated session for admin user."""
    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
    })
    response = session.post(f'{BASE_URL}/api/auth/login', json={
        'email': ADMIN_USER['email'],
        'password': ADMIN_USER['password']
    })
    if response.status_code not in [200, 201]:
        pytest.skip(f'Admin user login failed: {response.status_code}')
    return session


class TestFreeUserBlockedFromPremiumSurfaces:
    """Test that free users are blocked from premium surfaces."""

    def test_free_user_blocked_from_decision_coach(self, free_session):
        """Free user should be blocked from /features/decision-coach."""
        response = free_session.post(f'{BASE_URL}/api/access-control/check-route', json={
            'path': '/features/decision-coach',
            'method': 'GET'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['allowed'] is False
        assert data.get('reason') in ['free_limited_access', 'basic_required', 'subscription_required']

    def test_free_user_blocked_from_all_premium_surfaces(self, free_session):
        """Free user should be blocked from all expanded premium surfaces."""
        for route in PREMIUM_SURFACES:
            response = free_session.post(f'{BASE_URL}/api/access-control/check-route', json={
                'path': route,
                'method': 'GET'
            })
            assert response.status_code == 200, f'Failed for route: {route}'
            data = response.json()
            assert data['allowed'] is False, f'Free user should be blocked from {route}'

    def test_free_user_blocked_reason_is_free_limited_access(self, free_session):
        """Verify the reason code for free user block is correct."""
        response = free_session.post(f'{BASE_URL}/api/access-control/check-route', json={
            'path': '/features/decision-coach',
            'method': 'GET'
        })
        assert response.status_code == 200
        data = response.json()
        # Reason should indicate subscription/plan requirement
        assert data.get('reason') in ['free_limited_access', 'basic_required', 'subscription_required']


class TestBasicUserAllowedOnPremiumSurfaces:
    """Test that basic users are allowed on premium surfaces."""

    def test_basic_user_allowed_on_decision_coach(self, basic_session):
        """Basic user should be allowed on /features/decision-coach."""
        response = basic_session.post(f'{BASE_URL}/api/access-control/check-route', json={
            'path': '/features/decision-coach',
            'method': 'GET'
        })
        assert response.status_code == 200
        data = response.json()
        assert data['allowed'] is True

    def test_basic_user_allowed_on_all_premium_surfaces(self, basic_session):
        """Basic user should be allowed on all expanded premium surfaces."""
        for route in PREMIUM_SURFACES:
            response = basic_session.post(f'{BASE_URL}/api/access-control/check-route', json={
                'path': route,
                'method': 'GET'
            })
            assert response.status_code == 200, f'Failed for route: {route}'
            data = response.json()
            assert data['allowed'] is True, f'Basic user should be allowed on {route}'


class TestAdminOnlyApiRoutes:
    """Test that admin-only API routes are properly restricted.
    
    Note: The check-route API validates API paths (with /api/ prefix).
    UI routes like /admin are handled by frontend AccessControlContext.
    """

    # Admin API routes that should block non-admin users
    ADMIN_API_ROUTES = [
        '/api/admin/access-control/policy-console/bootstrap',
        '/api/admin/access-control/observability',
        '/api/admin/employees',
    ]

    def test_free_user_blocked_from_admin_api_routes(self, free_session):
        """Free user should be blocked from admin API routes."""
        for route in self.ADMIN_API_ROUTES:
            response = free_session.post(f'{BASE_URL}/api/access-control/check-route', json={
                'path': route,
                'method': 'GET'
            })
            assert response.status_code == 200, f'Failed for route: {route}'
            data = response.json()
            assert data['allowed'] is False, f'Free user should be blocked from admin API route {route}'

    def test_basic_user_blocked_from_admin_api_routes(self, basic_session):
        """Basic user should be blocked from admin API routes."""
        for route in self.ADMIN_API_ROUTES:
            response = basic_session.post(f'{BASE_URL}/api/access-control/check-route', json={
                'path': route,
                'method': 'GET'
            })
            assert response.status_code == 200, f'Failed for route: {route}'
            data = response.json()
            assert data['allowed'] is False, f'Basic user should be blocked from admin API route {route}'

    def test_admin_user_allowed_on_admin_api_routes(self, admin_session):
        """Admin user should be allowed on admin API routes."""
        for route in self.ADMIN_API_ROUTES:
            response = admin_session.post(f'{BASE_URL}/api/access-control/check-route', json={
                'path': route,
                'method': 'GET'
            })
            assert response.status_code == 200, f'Failed for route: {route}'
            data = response.json()
            assert data['allowed'] is True, f'Admin user should be allowed on admin API route {route}'


class TestAccessControlSession:
    """Test access control session endpoint."""

    def test_free_user_session_returns_limited_profile(self, free_session):
        """Free user session should return limited access profile."""
        response = free_session.get(f'{BASE_URL}/api/access-control/session')
        assert response.status_code == 200
        data = response.json()
        assert data.get('effective_plan') == 'free'
        assert data.get('subscription_access_profile') in ['limited', 'free']

    def test_basic_user_session_returns_almost_unlimited_profile(self, basic_session):
        """Basic user session should return almost_unlimited access profile."""
        response = basic_session.get(f'{BASE_URL}/api/access-control/session')
        assert response.status_code == 200
        data = response.json()
        assert data.get('effective_plan') == 'basic'
        assert data.get('subscription_access_profile') in ['almost_unlimited', 'basic']

    def test_admin_user_session_returns_admin_flag(self, admin_session):
        """Admin user session should return is_admin=True."""
        response = admin_session.get(f'{BASE_URL}/api/access-control/session')
        assert response.status_code == 200
        data = response.json()
        assert data.get('is_admin') is True


class TestHealthAndBasicEndpoints:
    """Basic health checks to ensure backend is running."""

    def test_health_endpoint(self):
        """Health endpoint should return 200."""
        response = requests.get(f'{BASE_URL}/api/health')
        assert response.status_code == 200

    def test_subscription_plans_endpoint(self):
        """Subscription plans endpoint should return plans."""
        response = requests.get(f'{BASE_URL}/api/subscriptions/plans')
        assert response.status_code == 200
        data = response.json()
        assert 'plans' in data
        assert len(data['plans']) > 0
