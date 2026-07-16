"""
Feature 26 Final Verification Closure Tests (Locked Protocol)

Goal:
- Close remaining Pending Verification items for Feature 26:
  - E2E Free / Basic / Premium
  - Final role-gated admin-block proof
  - Locked metadata proof (feature_number=26, feature_id=jobs-portal)
"""

import os
import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}
BASIC_USER = {"email": "f21.basic.1781338672@example.com", "password": "F21Basic#2026Aa"}
PREMIUM_ADMIN = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}
APPROVED_EMPLOYER = {
    "email": "feature26.approved.employer.e2e@realaicoach.app",
    "password": "Feature26Approved#2026!",
}


def _login_session(creds: dict[str, str]) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    resp = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert resp.status_code == 200, f"Login failed for {creds.get('email')}: {resp.status_code} {resp.text[:200]}"
    return s


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    return _login_session(FREE_USER)


@pytest.fixture(scope="module")
def basic_session() -> requests.Session:
    return _login_session(BASIC_USER)


@pytest.fixture(scope="module")
def premium_session() -> requests.Session:
    return _login_session(PREMIUM_ADMIN)


@pytest.fixture(scope="module")
def employer_session() -> requests.Session:
    return _login_session(APPROVED_EMPLOYER)


class TestFeature26LockedMetadata:
    def test_health_contract_metadata(self, premium_session: requests.Session):
        resp = premium_session.get(f"{BASE_URL}/api/hiring/v2/health", timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("feature_number") == 26
        assert data.get("feature_id") == "jobs-portal"
        assert data.get("version") == "v2"


class TestFeature26TierE2E:
    def test_free_tier_e2e(self, free_session: requests.Session):
        summary = free_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary", timeout=30)
        assert summary.status_code == 200

        search = free_session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search?page=1&limit=5", timeout=30)
        assert search.status_code == 200

        admin_block = free_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=5", timeout=30)
        assert admin_block.status_code == 403

        boost = free_session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/boost-profile",
            json={"boost_hours": 24},
            timeout=30,
        )
        assert boost.status_code == 403

    def test_basic_tier_e2e(self, basic_session: requests.Session):
        summary = basic_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary", timeout=30)
        assert summary.status_code == 200

        search = basic_session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search?page=1&limit=5", timeout=30)
        assert search.status_code == 200

        admin_block = basic_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=5", timeout=30)
        assert admin_block.status_code == 403

        # Basic should be allowed for this commercial action in current Feature 26 contract.
        boost = basic_session.post(
            f"{BASE_URL}/api/hiring/v2/candidate/boost-profile",
            json={"boost_hours": 24},
            timeout=30,
        )
        assert boost.status_code == 200

    def test_premium_tier_e2e(self, premium_session: requests.Session):
        summary = premium_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary", timeout=30)
        assert summary.status_code == 200

        search = premium_session.get(f"{BASE_URL}/api/hiring/v2/candidate/jobs/search?page=1&limit=5", timeout=30)
        assert search.status_code == 200

        admin_allowed = premium_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=5", timeout=30)
        assert admin_allowed.status_code == 200

        funnel = premium_session.get(
            f"{BASE_URL}/api/hiring/v2/admin/employer-conversion-funnel?lookback_days=30",
            timeout=30,
        )
        assert funnel.status_code == 200

    def test_approved_employer_guardrails(self, employer_session: requests.Session):
        summary = employer_session.get(f"{BASE_URL}/api/hiring/v2/dashboard/summary", timeout=30)
        assert summary.status_code == 200

        admin_block = employer_session.get(f"{BASE_URL}/api/hiring/v2/admin/workflow-events?limit=5", timeout=30)
        assert admin_block.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
