"""
Feature 27 (ID Checker) Enterprise Hardening Tests.

Covers:
1) User workflow status contract (entitlements/sla/id_checker fields)
2) Admin access control on queue + metrics endpoints
3) Admin operations & conversion metrics endpoint schema
4) User experience summary contract
"""

import os
import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def admin_session():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if login.status_code != 200:
        pytest.skip(f"Admin login failed: {login.status_code} - {login.text[:200]}")
    return session


@pytest.fixture(scope="module")
def free_session():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_EMAIL, "password": FREE_PASSWORD},
    )
    if login.status_code != 200:
        pytest.skip(f"Free user login failed: {login.status_code} - {login.text[:200]}")
    return session


class TestFeature27UserContracts:
    def test_kyc_status_includes_enterprise_contract_fields(self, free_session):
        response = free_session.get(f"{BASE_URL}/api/id-checker/kyc/status")
        assert response.status_code == 200, response.text
        data = response.json()

        assert "kyc" in data
        assert "entitlements" in data
        assert "sla" in data
        assert "id_checker" in data

        entitlements = data["entitlements"]
        assert entitlements.get("plan") in ["free", "basic", "premium", "admin"]
        assert isinstance(entitlements.get("service_lane"), str)
        assert isinstance(entitlements.get("expected_sla_hours"), int)

        id_checker = data["id_checker"]
        assert isinstance(id_checker.get("workflow_state"), str)
        assert isinstance(id_checker.get("states"), list)
        assert isinstance(id_checker.get("required_documents"), list)
        assert isinstance(id_checker.get("uploaded_documents"), list)
        assert isinstance(id_checker.get("missing_documents"), list)
        assert isinstance(id_checker.get("documents_complete"), bool)
        assert isinstance(id_checker.get("timeline"), dict)
        assert isinstance(id_checker.get("timeline", {}).get("milestones"), list)
        assert isinstance(id_checker.get("timeline", {}).get("recent_events"), list)

        experience_summary = data.get("experience_summary")
        assert isinstance(experience_summary, dict)
        assert isinstance(experience_summary.get("trust_readiness_score"), int)
        assert isinstance(experience_summary.get("nudges"), list)

    def test_experience_summary_returns_contract_schema(self, free_session):
        response = free_session.get(f"{BASE_URL}/api/id-checker/experience-summary")
        assert response.status_code == 200, response.text
        data = response.json()

        assert "generated_at" in data
        assert data.get("plan") in ["free", "basic", "premium", "admin"]
        assert isinstance(data.get("service_lane"), str)
        assert isinstance(data.get("workflow_state"), str)
        assert isinstance(data.get("progress"), dict)
        assert isinstance(data.get("sla"), dict)
        assert isinstance(data.get("trust_readiness_score"), int)
        assert isinstance(data.get("nudges"), list)


class TestFeature27AdminContracts:
    def test_admin_queue_blocks_non_admin(self, free_session):
        response = free_session.get(
            f"{BASE_URL}/api/id-checker/admin/queue",
            params={"status": "ALL", "risk_level": "all", "country": "all", "limit": 20},
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"

    def test_admin_queue_contains_enterprise_fields(self, admin_session):
        response = admin_session.get(
            f"{BASE_URL}/api/id-checker/admin/queue",
            params={"status": "ALL", "risk_level": "all", "country": "all", "limit": 30},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "queue" in data
        queue = data.get("queue", [])
        if queue:
            sample = queue[0]
            assert "service_lane" in sample
            assert "subscription_plan" in sample
            assert "sla_due_at" in sample
            assert "sla_breached" in sample
            assert "sla_hours_remaining" in sample

    def test_admin_operations_kpis_schema(self, admin_session):
        response = admin_session.get(
            f"{BASE_URL}/api/id-checker/admin/operations-kpis",
            params={"lookback_days": 30},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        required = [
            "lookback_days",
            "generated_at",
            "total_cases",
            "approval_rate_pct",
            "rejection_rate_pct",
            "pending_rate_pct",
            "document_completion_rate_pct",
            "sla_breach_cases",
            "state_counts",
            "service_lane_counts",
            "docs_missing_cases",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_admin_conversion_funnel_schema(self, admin_session):
        response = admin_session.get(
            f"{BASE_URL}/api/id-checker/admin/conversion-funnel",
            params={"lookback_days": 30},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "funnel" in data
        assert "conversion_rates_pct" in data
        assert "dropoff" in data
        assert "insights" in data
        assert isinstance(data["insights"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
