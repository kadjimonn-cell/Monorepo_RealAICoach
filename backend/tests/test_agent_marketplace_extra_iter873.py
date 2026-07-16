"""Supplemental AI Marketplace validation (iteration 873).

Covers items not exercised by test_agent_marketplace.py:
    - additional catalog filters (q, status, availability, tag, feature)
    - catalog sort/order combos
    - GET /agents/{key} + /agents/{key}/versions detail endpoints
    - POST /agents upsert with the new marketplace fields (create + delete)
    - readiness "9 passing checks" contract
    - portfolio has by_status / by_availability / by_health / avg_quality_score
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}


@pytest.fixture(scope="module")
def admin():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited during login")
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return sess


class TestMarketplaceExtendedFilters:
    def test_catalog_search_q(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?q=career", timeout=60)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items, "expected at least one hit for q=career"
        # every returned item should mention 'career' somewhere searchable
        # search may include name, description, agent_key, category, subcategory, tags, role
        for i in items:
            haystack = " ".join([
                str(i.get("name", "")), str(i.get("description", "")),
                str(i.get("agent_key", "")), str(i.get("category", "")),
                str(i.get("subcategory", "")), str(i.get("role", "")),
                " ".join(i.get("tags", [])),
            ]).lower()
            assert "career" in haystack, f"agent {i.get('agent_key')} lacks 'career' in searchable fields"

    def test_catalog_status_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?status=active&page_size=50",
                      timeout=60)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and all(i["status"] == "active" for i in items)

    def test_catalog_availability_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?availability=global&page_size=50",
                      timeout=60)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and all(i["availability"] == "global" for i in items)

    def test_catalog_feature_filter(self, admin):
        feature = "money-strategy-hub"
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?feature={feature}&page_size=50",
                      timeout=60)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and all(feature in i["feature_mappings"] for i in items)

    def test_catalog_tag_filter_returns_tag_matches(self, admin):
        # find a valid tag from the first page and re-query
        page = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?page_size=5", timeout=60).json()
        tag = next((t for a in page["items"] for t in a.get("tags", [])), None)
        assert tag, "no tags present in catalog sample"
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?tag={tag}&page_size=50",
                      timeout=60)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and all(tag in i.get("tags", []) for i in items)

    def test_catalog_sort_name_desc(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?sort=name&order=desc&page_size=20",
                      timeout=60)
        assert r.status_code == 200
        names = [i["name"] for i in r.json()["items"]]
        assert names == sorted(names, reverse=True)

    def test_catalog_sort_name_asc(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?sort=name&order=asc&page_size=20",
                      timeout=60)
        assert r.status_code == 200
        names = [i["name"] for i in r.json()["items"]]
        assert names == sorted(names)


class TestPortfolioShape:
    def test_portfolio_has_breakdowns(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/portfolio", timeout=60)
        assert r.status_code == 200
        data = r.json()
        for k in ("by_status", "by_availability", "by_health", "avg_quality_score", "coverage"):
            assert k in data, f"portfolio missing '{k}'"
        assert isinstance(data["by_status"], dict) and data["by_status"]
        assert isinstance(data["by_availability"], dict) and data["by_availability"]
        assert 0 <= data["avg_quality_score"] <= 100

    def test_readiness_9_checks_all_pass(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/readiness", timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["ready"] is True
        assert len(data["checks"]) >= 9
        failing = [c for c in data["checks"] if not c["passed"]]
        assert not failing, f"failing readiness checks: {failing}"


class TestRecommendationsScoring:
    def test_recommendations_fitness(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/recommendations/fitness-planner-pro",
                      timeout=60)
        assert r.status_code == 200
        recs = r.json()["recommendations"]
        assert recs, "expected recommendations for fitness-planner-pro"
        scores = [rec["score"] for rec in recs]
        assert scores == sorted(scores, reverse=True), "recommendations should be score-desc"


class TestAgentDetailAndVersions:
    def test_agent_detail_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/agents/software_engineer", timeout=30)
        assert r.status_code == 200
        agent = r.json()
        # unwrap if wrapped
        if "agent" in agent:
            agent = agent["agent"]
        for k in ("agent_key", "name", "role", "category", "system_prompt"):
            assert k in agent, f"detail missing '{k}'"

    def test_agent_versions_history(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/agents/software_engineer/versions", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "versions" in data or isinstance(data, list)


class TestUpsertZeroRegression:
    """Create a temp agent using the NEW marketplace fields, then delete it."""

    KEY = "TEST_marketplace_upsert_iter873"

    def _cleanup(self, admin):
        admin.delete(f"{BASE_URL}/api/agent-framework/agents/{self.KEY}", timeout=30)

    def test_upsert_with_marketplace_fields(self, admin):
        self._cleanup(admin)
        payload = {
            "agent_key": self.KEY,
            "name": "Iter873 Regression Agent",
            "role": "regression-check",
            "category": "Career & Job Search",
            "subcategory": "Career Coaching",
            "description": "Temporary agent for testing marketplace upsert regression.",
            "system_prompt": "You are a temporary regression agent.",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "allowed_tools": ["template_render"],
            "tags": ["regression", "temp"],
            "feature_mappings": ["career-coach-pro"],
            "permissions": ["admin"],
            "availability": "workspace",
            "status": "experimental",
            "dependencies": [],
            "config_profile": {"temperature": 0.2},
        }
        r = admin.post(f"{BASE_URL}/api/agent-framework/agents", json=payload, timeout=30)
        assert r.status_code in (200, 201), f"upsert failed: {r.status_code} {r.text[:200]}"

        # verify GET reflects new fields
        r2 = admin.get(f"{BASE_URL}/api/agent-framework/agents/{self.KEY}", timeout=30)
        assert r2.status_code == 200
        got = r2.json()
        if "agent" in got:
            got = got["agent"]
        assert got["subcategory"] == "Career Coaching"
        assert got["status"] == "experimental"
        assert got["availability"] == "workspace"
        assert "career-coach-pro" in got["feature_mappings"]

        # cleanup
        d = admin.delete(f"{BASE_URL}/api/agent-framework/agents/{self.KEY}", timeout=30)
        assert d.status_code in (200, 204)

        # confirm gone
        r3 = admin.get(f"{BASE_URL}/api/agent-framework/agents/{self.KEY}", timeout=30)
        assert r3.status_code == 404
