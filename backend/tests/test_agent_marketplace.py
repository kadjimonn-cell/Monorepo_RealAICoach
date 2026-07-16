"""AI Marketplace Architecture validation — 200+ native agents, coverage, lifecycle.

Checks catalog integrity offline plus live marketplace endpoints with admin auth.
"""

import os
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

from agent_framework.catalog import DEFAULT_AGENTS, AGENT_CATEGORIES  # noqa: E402
from agent_framework.marketplace import (  # noqa: E402
    VALID_STATUSES, VALID_AVAILABILITY, health_status, quality_score,
)
from utils.access_control_engine import CANONICAL_FEATURE_METERS  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}

FEATURE_KEYS = {m["feature_key"] for m in CANONICAL_FEATURE_METERS}
KNOWN_TOOLS = {"template_render", "db_read", "http_fetch"}
KNOWN_PROVIDERS = {"openai", "anthropic", "google"}


# ── Offline catalog integrity ──

class TestCatalogIntegrity:
    def test_catalog_has_200_plus_agents(self):
        assert len(DEFAULT_AGENTS) >= 200, f"Catalog has only {len(DEFAULT_AGENTS)} agents"

    def test_agent_keys_unique(self):
        keys = [a["agent_key"] for a in DEFAULT_AGENTS]
        assert len(keys) == len(set(keys)), "Duplicate agent keys in catalog"

    def test_required_marketplace_fields_present(self):
        required = (
            "agent_key", "name", "role", "category", "subcategory", "description",
            "system_prompt", "provider", "model", "allowed_tools", "tags",
            "feature_mappings", "permissions", "availability", "status",
            "dependencies", "config_profile",
        )
        for agent in DEFAULT_AGENTS:
            for field in required:
                assert field in agent, f"{agent['agent_key']} missing '{field}'"
            assert agent["system_prompt"].strip(), f"{agent['agent_key']} empty prompt"
            assert agent["description"].strip(), f"{agent['agent_key']} empty description"

    def test_statuses_and_availability_valid(self):
        for agent in DEFAULT_AGENTS:
            assert agent["status"] in VALID_STATUSES, agent["agent_key"]
            assert agent["availability"] in VALID_AVAILABILITY, agent["agent_key"]

    def test_providers_and_tools_valid(self):
        for agent in DEFAULT_AGENTS:
            assert agent["provider"] in KNOWN_PROVIDERS, agent["agent_key"]
            for tool in agent["allowed_tools"]:
                assert tool in KNOWN_TOOLS or tool == "*", f"{agent['agent_key']} unknown tool {tool}"

    def test_feature_mappings_reference_canonical_features(self):
        for agent in DEFAULT_AGENTS:
            for fk in agent["feature_mappings"]:
                assert fk in FEATURE_KEYS, f"{agent['agent_key']} maps unknown feature '{fk}'"

    def test_all_37_features_covered_by_catalog(self):
        covered = set()
        for agent in DEFAULT_AGENTS:
            if agent["status"] != "disabled":
                covered.update(agent["feature_mappings"])
        missing = FEATURE_KEYS - covered
        assert not missing, f"Uncovered features: {sorted(missing)}"

    def test_dependencies_resolve_within_catalog(self):
        keys = {a["agent_key"] for a in DEFAULT_AGENTS}
        for agent in DEFAULT_AGENTS:
            for dep in agent["dependencies"]:
                assert dep in keys, f"{agent['agent_key']} dangling dependency '{dep}'"

    def test_categories_registered(self):
        cats = {a["category"] for a in DEFAULT_AGENTS}
        assert cats <= set(AGENT_CATEGORIES)
        assert len(AGENT_CATEGORIES) >= 20


class TestHealthAndQuality:
    def test_health_status(self):
        assert health_status(None) == "idle"
        assert health_status({"executions": 10, "errors": 0}) == "healthy"
        assert health_status({"executions": 10, "errors": 5}) == "degraded"

    def test_quality_score_bounds(self):
        for agent in DEFAULT_AGENTS[:20]:
            score = quality_score(agent, {"executions": 5, "errors": 0})
            assert 0 <= score <= 100


# ── Live API validation ──

@pytest.fixture(scope="module")
def admin():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited during login")
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return sess


class TestMarketplaceAPI:
    def test_catalog_search_pagination(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?page=1&page_size=30",
                         timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 200
        assert len(data["items"]) == 30
        assert data["pages"] >= 7

    def test_catalog_filters(self, admin):
        r = admin.get(
            f"{BASE_URL}/api/agent-framework/marketplace/catalog?category=Finance%20%26%20Investment",
            timeout=60)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and all(i["category"] == "Finance & Investment" for i in items)

    def test_categories_summary(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/categories",
                         timeout=60)
        assert r.status_code == 200
        assert len(r.json()["categories"]) >= 20

    def test_coverage_all_features(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/coverage",
                         timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["features_total"] == 37
        assert data["uncovered_features"] == []
        assert data["coverage_percent"] == 100.0

    def test_recommendations(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/recommendations/money-strategy-hub",
                         timeout=60)
        assert r.status_code == 200
        recs = r.json()["recommendations"]
        assert recs and recs[0]["score"] >= 50

    def test_recommendations_unknown_feature_404(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/recommendations/not-a-feature",
                         timeout=60)
        assert r.status_code == 404

    def test_dependency_graph_no_dangling(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/dependencies",
                         timeout=60)
        assert r.status_code == 200
        assert r.json()["dangling"] == []

    def test_portfolio_overview(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/portfolio",
                         timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["agents_total"] >= 200
        assert data["coverage"]["coverage_percent"] == 100.0

    def test_readiness_report(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/readiness",
                         timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["ready"] is True, [c for c in data["checks"] if not c["passed"]]

    def test_templates(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/templates",
                         timeout=60)
        assert r.status_code == 200
        assert len(r.json()["templates"]) >= 20

    def test_stats_report(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/stats",
                         timeout=60)
        assert r.status_code == 200
        rows = r.json()["stats"]
        assert len(rows) >= 200
        assert all("health" in row and "quality_score" in row for row in rows[:5])

    def test_clone_export_import_bulk_lifecycle(self, admin):
        clone_key = "software_engineer_clone_pytest"
        admin.delete(f"{BASE_URL}/api/agent-framework/agents/{clone_key}",
                        timeout=30)
        r = admin.post(
            f"{BASE_URL}/api/agent-framework/marketplace/agents/software_engineer/clone",
            json={"new_key": clone_key, "new_name": "SE Clone (pytest)"},
            timeout=60)
        assert r.status_code == 200
        assert r.json()["status"] == "experimental"
        # duplicate clone rejected
        r2 = admin.post(
            f"{BASE_URL}/api/agent-framework/marketplace/agents/software_engineer/clone",
            json={"new_key": clone_key}, timeout=60)
        assert r2.status_code == 409
        # bulk status
        r3 = admin.post(
            f"{BASE_URL}/api/agent-framework/marketplace/bulk-status",
            json={"agent_keys": [clone_key], "changes": {"status": "beta"}},
            timeout=60)
        assert r3.status_code == 200 and r3.json()["modified"] == 1
        # export
        r4 = admin.post(
            f"{BASE_URL}/api/agent-framework/marketplace/export",
            json={"agent_keys": [clone_key]}, timeout=60)
        assert r4.status_code == 200
        exported = r4.json()
        assert exported["count"] == 1 and exported["agents"][0]["status"] == "beta"
        # cleanup then re-import
        admin.delete(f"{BASE_URL}/api/agent-framework/agents/{clone_key}",
                        timeout=30)
        r5 = admin.post(
            f"{BASE_URL}/api/agent-framework/marketplace/import",
            json={"agents": exported["agents"], "overwrite": False},
            timeout=60)
        assert r5.status_code == 200 and clone_key in r5.json()["imported"]
        # final cleanup
        admin.delete(f"{BASE_URL}/api/agent-framework/agents/{clone_key}",
                        timeout=30)

    def test_bulk_invalid_status_rejected(self, admin):
        r = admin.post(
            f"{BASE_URL}/api/agent-framework/marketplace/bulk-status",
            json={"agent_keys": ["software_engineer"], "changes": {"status": "bogus"}},
            timeout=60)
        assert r.status_code == 400

    def test_marketplace_requires_admin(self):
        anon = requests.Session()
        r = anon.get(f"{BASE_URL}/api/agent-framework/marketplace/portfolio", timeout=30)
        assert r.status_code in (401, 403)


class TestZeroRegression:
    def test_legacy_agents_endpoint_still_works(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/agents", timeout=60)
        assert r.status_code == 200
        agents = r.json()["agents"]
        assert len(agents) >= 200
        keys = {a["agent_key"] for a in agents}
        assert "software_engineer" in keys and "career_coach" in keys

    def test_legacy_overview_still_works(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/overview", timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["agents"] >= 200 and data["tools"] >= 3

    def test_legacy_workflows_tools_endpoints(self, admin):
        for path in ("workflows", "tools", "executions", "prompts", "policy", "audit"):
            r = admin.get(f"{BASE_URL}/api/agent-framework/{path}", timeout=60)
            assert r.status_code == 200, f"{path} regressed: {r.status_code}"
