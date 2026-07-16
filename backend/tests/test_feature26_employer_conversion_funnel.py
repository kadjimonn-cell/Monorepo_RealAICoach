"""
Feature 26 Employer Conversion Funnel Endpoint Tests

Tests for the new /api/hiring/v2/admin/employer-conversion-funnel endpoint:
1. Schema validation - response contains expected fields
2. Admin access required - non-admin users get 403
3. Regression - existing feature26 tests remain green
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_session(api_client):
    """Get authenticated admin session"""
    login_response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text}")
    
    # Session cookies should be set automatically
    return api_client


@pytest.fixture(scope="module")
def free_user_session():
    """Get authenticated free user session (non-admin)"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
    )
    if login_response.status_code != 200:
        pytest.skip(f"Free user login failed: {login_response.status_code} - {login_response.text}")
    
    return session


class TestEmployerConversionFunnelEndpoint:
    """Tests for /api/hiring/v2/admin/employer-conversion-funnel"""

    def test_funnel_endpoint_returns_200_for_admin(self, admin_session):
        """Admin user should get 200 response from funnel endpoint"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/employer-conversion-funnel",
            params={"lookback_days": 30},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Admin gets 200 from employer-conversion-funnel endpoint")

    def test_funnel_endpoint_schema_validation(self, admin_session):
        """Response should contain expected schema fields"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/employer-conversion-funnel",
            params={"lookback_days": 30},
        )
        assert response.status_code == 200
        data = response.json()

        # Top-level fields
        assert "generated_at" in data, "Missing 'generated_at' field"
        assert "lookback_days" in data, "Missing 'lookback_days' field"
        assert "funnel" in data, "Missing 'funnel' field"
        assert "conversion_rates_pct" in data, "Missing 'conversion_rates_pct' field"
        assert "dropoff" in data, "Missing 'dropoff' field"
        assert "insights" in data, "Missing 'insights' field"

        # Funnel sub-fields
        funnel = data["funnel"]
        assert "trial_started" in funnel, "Missing 'funnel.trial_started' field"
        assert "approved_employer" in funnel, "Missing 'funnel.approved_employer' field"
        assert "first_hire" in funnel, "Missing 'funnel.first_hire' field"

        # Conversion rates sub-fields
        rates = data["conversion_rates_pct"]
        assert "trial_to_approved" in rates, "Missing 'conversion_rates_pct.trial_to_approved' field"
        assert "approved_to_first_hire" in rates, "Missing 'conversion_rates_pct.approved_to_first_hire' field"
        assert "trial_to_first_hire" in rates, "Missing 'conversion_rates_pct.trial_to_first_hire' field"

        # Dropoff sub-fields
        dropoff = data["dropoff"]
        assert "trial_to_approved" in dropoff, "Missing 'dropoff.trial_to_approved' field"
        assert "approved_to_first_hire" in dropoff, "Missing 'dropoff.approved_to_first_hire' field"

        # Type validations
        assert isinstance(data["lookback_days"], int), "lookback_days should be int"
        assert isinstance(funnel["trial_started"], int), "trial_started should be int"
        assert isinstance(funnel["approved_employer"], int), "approved_employer should be int"
        assert isinstance(funnel["first_hire"], int), "first_hire should be int"
        assert isinstance(rates["trial_to_approved"], (int, float)), "trial_to_approved should be numeric"
        assert isinstance(rates["approved_to_first_hire"], (int, float)), "approved_to_first_hire should be numeric"
        assert isinstance(rates["trial_to_first_hire"], (int, float)), "trial_to_first_hire should be numeric"
        assert isinstance(data["insights"], list), "insights should be a list"

        print("PASS: Schema validation complete - all expected fields present with correct types")
        print(f"  Funnel: trial={funnel['trial_started']}, approved={funnel['approved_employer']}, first_hire={funnel['first_hire']}")
        print(f"  Rates: trial→approved={rates['trial_to_approved']}%, approved→hire={rates['approved_to_first_hire']}%")

    def test_funnel_endpoint_lookback_days_parameter(self, admin_session):
        """Lookback days parameter should be respected"""
        for days in [7, 30, 90]:
            response = admin_session.get(
                f"{BASE_URL}/api/hiring/v2/admin/employer-conversion-funnel",
                params={"lookback_days": days},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["lookback_days"] == days, f"Expected lookback_days={days}, got {data['lookback_days']}"
        
        print("PASS: lookback_days parameter correctly respected for values 7, 30, 90")

    def test_funnel_endpoint_default_lookback_days(self, admin_session):
        """Default lookback_days should be 30"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/employer-conversion-funnel",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["lookback_days"] == 30, f"Expected default lookback_days=30, got {data['lookback_days']}"
        print("PASS: Default lookback_days is 30")


class TestEmployerConversionFunnelAccessControl:
    """Tests for admin access control on funnel endpoint"""

    def test_funnel_endpoint_requires_admin_access(self, free_user_session):
        """Non-admin user should get 403 from funnel endpoint"""
        response = free_user_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/employer-conversion-funnel",
            params={"lookback_days": 30},
        )
        assert response.status_code == 403, f"Expected 403 for non-admin, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "admin" in str(data.get("detail", "")).lower(), "Error message should mention admin access"
        print("PASS: Non-admin user correctly gets 403 with admin access required message")

    def test_funnel_endpoint_requires_authentication(self):
        """Unauthenticated request should get 401"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        response = session.get(
            f"{BASE_URL}/api/hiring/v2/admin/employer-conversion-funnel",
            params={"lookback_days": 30},
        )
        # Should be 401 or 403 for unauthenticated
        assert response.status_code in [401, 403], f"Expected 401/403 for unauthenticated, got {response.status_code}"
        print(f"PASS: Unauthenticated request correctly rejected with {response.status_code}")


class TestFeature26RegressionGuard:
    """Regression tests to ensure existing Feature 26 endpoints still work"""

    def test_hiring_v2_health_endpoint(self, api_client):
        """Health endpoint should still work"""
        response = api_client.get(f"{BASE_URL}/api/hiring/v2/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert data.get("feature_number") == 26
        print("PASS: /api/hiring/v2/health endpoint working")

    def test_admin_canary_controls_endpoint(self, admin_session):
        """Admin canary controls endpoint should still work"""
        response = admin_session.get(f"{BASE_URL}/api/hiring/v2/admin/canary-controls")
        assert response.status_code == 200
        data = response.json()
        assert "controls" in data or "defaults" in data
        print("PASS: /api/hiring/v2/admin/canary-controls endpoint working")

    def test_admin_deprecation_telemetry_endpoint(self, admin_session):
        """Admin deprecation telemetry endpoint should still work"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/deprecation-telemetry",
            params={"lookback_days": 14, "limit": 100},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_events" in data
        assert "migration_progress_pct" in data
        print("PASS: /api/hiring/v2/admin/deprecation-telemetry endpoint working")

    def test_admin_legacy_retirement_readiness_endpoint(self, admin_session):
        """Admin legacy retirement readiness endpoint should still work"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/legacy-retirement-readiness",
            params={"lookback_hours": 72},
        )
        assert response.status_code == 200
        data = response.json()
        assert "retirement_phase" in data
        assert "family_readiness" in data
        print("PASS: /api/hiring/v2/admin/legacy-retirement-readiness endpoint working")

    def test_admin_workflow_events_endpoint(self, admin_session):
        """Admin workflow events endpoint should still work"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/workflow-events",
            params={"limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        print("PASS: /api/hiring/v2/admin/workflow-events endpoint working")

    def test_admin_premium_conversion_cohorts_endpoint(self, admin_session):
        """Admin premium conversion cohorts endpoint should still work"""
        response = admin_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/premium-conversion-cohorts",
            params={"lookback_days": 30},
        )
        assert response.status_code == 200
        data = response.json()
        # Should have cohort-related fields
        assert "total_events" in data or "repeat_rate_pct" in data or "activation_users" in data
        print("PASS: /api/hiring/v2/admin/premium-conversion-cohorts endpoint working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
