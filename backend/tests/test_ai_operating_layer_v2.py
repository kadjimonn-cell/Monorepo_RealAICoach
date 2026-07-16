"""AI Operating Layer v2 validation — intelligent routing, event-driven
orchestration, knowledge management, analytics, plus zero-regression checks."""

import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, "/app/backend")

from agent_framework.engine import validate_workflow_steps, count_steps  # noqa: E402
from agent_framework.analytics import estimate_cost  # noqa: E402
from agent_framework.orchestration_v2 import RESOLUTION_STRATEGIES  # noqa: E402

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


# ── Offline engine v2 validation ──

class TestEngineV2:
    def test_new_step_types_valid(self):
        steps = [
            {"type": "delegate", "step_id": "d1", "input_template": "{{input}}"},
            {"type": "collaborate", "step_id": "c1", "agent_keys": ["a", "b"], "resolution": "synthesize"},
        ]
        validate_workflow_steps(steps)

    def test_collaborate_requires_agent_keys(self):
        with pytest.raises(ValueError):
            validate_workflow_steps([{"type": "collaborate", "step_id": "c1"}])

    def test_legacy_step_types_unchanged(self):
        steps = [
            {"type": "agent", "step_id": "s1", "agent_key": "x"},
            {"type": "tool", "step_id": "s2", "tool_name": "template_render"},
            {"type": "condition", "step_id": "s3", "condition": {}, "then_steps": [], "else_steps": []},
            {"type": "parallel", "step_id": "s4", "branches": []},
            {"type": "human_approval", "step_id": "s5"},
        ]
        validate_workflow_steps(steps)
        assert count_steps(steps) == 5

    def test_resolution_strategies(self):
        assert RESOLUTION_STRATEGIES == {"synthesize", "first_success", "all"}

    def test_cost_estimation(self):
        assert estimate_cost("gpt-4o", 1000, 1000) == 0.02
        assert estimate_cost("gpt-4o-mini", 1000, 1000) == 0.003
        assert estimate_cost("unknown-model", 0, 0) == 0.0


# ── Intelligent routing ──

class TestRouting:
    def test_route_selects_agent(self, admin):
        r = admin.post(f"{BASE_URL}/api/agent-framework/route",
                       json={"intent": "help me prepare for a job interview and improve my resume"}, timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["selected_agent"] is not None
        assert data["candidates_evaluated"] > 100
        assert len(data["team"]) >= 1
        categories = [t["category"] for t in data["team"]]
        assert len(categories) == len(set(categories)), "Team must span distinct categories"

    def test_route_logged(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/route/log?limit=5", timeout=30)
        assert r.status_code == 200
        assert len(r.json()["routing_log"]) >= 1

    def test_capabilities_discovery(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/capabilities", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "delegate" in data["step_types"] and "collaborate" in data["step_types"]
        assert "knowledge_search" in data["tools"]
        assert set(data["providers"]) == {"openai", "anthropic", "google"}

    def test_route_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/agent-framework/route",
                          json={"intent": "x"}, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=30)
        assert r.status_code in (401, 403)


# ── Event-driven orchestration ──

class TestEventTriggers:
    def test_trigger_crud_and_emit(self, admin):
        wf = admin.post(f"{BASE_URL}/api/agent-framework/workflows", json={
            "name": "V2 Event Test Workflow",
            "steps": [{"type": "tool", "step_id": "t1", "tool_name": "template_render",
                       "args": {"template": "event: {{input}}", "variables": {}}}],
        }, timeout=30)
        assert wf.status_code == 200
        workflow_id = wf.json()["workflow_id"]
        event_name = f"test.event.{uuid.uuid4().hex[:6]}"
        try:
            tr = admin.post(f"{BASE_URL}/api/agent-framework/events/triggers", json={
                "event_name": event_name, "workflow_id": workflow_id, "description": "test",
            }, timeout=30)
            assert tr.status_code == 200
            trigger_id = tr.json()["trigger_id"]

            lst = admin.get(f"{BASE_URL}/api/agent-framework/events/triggers", timeout=30)
            assert any(t["trigger_id"] == trigger_id for t in lst.json()["triggers"])

            em = admin.post(f"{BASE_URL}/api/agent-framework/events/emit", json={
                "event_name": event_name, "payload": {"source": "pytest"},
            }, timeout=60)
            assert em.status_code == 200
            emitted = em.json()
            assert emitted["triggers_matched"] == 1
            assert len(emitted["executions_started"]) == 1

            ev = admin.get(f"{BASE_URL}/api/agent-framework/events?limit=5", timeout=30)
            assert any(e["event_name"] == event_name for e in ev.json()["events"])

            dr = admin.delete(f"{BASE_URL}/api/agent-framework/events/triggers/{trigger_id}", timeout=30)
            assert dr.status_code == 200
        finally:
            admin.delete(f"{BASE_URL}/api/agent-framework/workflows/{workflow_id}", timeout=30)

    def test_trigger_rejects_unknown_workflow(self, admin):
        r = admin.post(f"{BASE_URL}/api/agent-framework/events/triggers", json={
            "event_name": "bad.event", "workflow_id": "nonexistent",
        }, timeout=30)
        assert r.status_code == 404


# ── Knowledge management ──

class TestKnowledge:
    key = f"pytest_kb_{uuid.uuid4().hex[:6]}"

    def test_collection_source_search_lifecycle(self, admin):
        c = admin.post(f"{BASE_URL}/api/agent-framework/knowledge/collections", json={
            "collection_key": self.key, "name": "Pytest KB",
            "governance": {"review_required": True, "retention_days": 30},
        }, timeout=30)
        assert c.status_code == 200
        assert c.json()["governance"]["review_required"] is True

        src = admin.post(f"{BASE_URL}/api/agent-framework/knowledge/sources", json={
            "collection_key": self.key, "name": "Goal Setting Basics", "source_type": "manual",
            "content": "SMART goals are Specific Measurable Achievable Relevant and Timebound. "
                       "Review progress weekly and adjust milestones for motivation.",
        }, timeout=30)
        assert src.status_code == 200
        source = src.json()
        assert source["sync_status"] == "synced"
        source_id = source["source_id"]

        sr = admin.post(f"{BASE_URL}/api/agent-framework/knowledge/search", json={
            "query": "how to set measurable goals", "collection_key": self.key,
        }, timeout=30)
        assert sr.status_code == 200
        results = sr.json()["results"]
        assert len(results) >= 1
        assert results[0]["citation"].startswith("[Goal Setting Basics#")
        assert results[0]["snippet"]

        sync = admin.post(f"{BASE_URL}/api/agent-framework/knowledge/sources/{source_id}/sync", timeout=30)
        assert sync.status_code == 200
        assert sync.json()["version"] >= 2

        ov = admin.get(f"{BASE_URL}/api/agent-framework/knowledge/overview", timeout=30)
        assert ov.status_code == 200
        data = ov.json()
        assert data["collections_total"] >= 1
        assert data["citations_total"] >= 1
        assert "retrieval_quality" in data

        d1 = admin.delete(f"{BASE_URL}/api/agent-framework/knowledge/sources/{source_id}", timeout=30)
        assert d1.status_code == 200
        d2 = admin.delete(f"{BASE_URL}/api/agent-framework/knowledge/collections/{self.key}", timeout=30)
        assert d2.status_code == 200

    def test_source_requires_existing_collection(self, admin):
        r = admin.post(f"{BASE_URL}/api/agent-framework/knowledge/sources", json={
            "collection_key": "does_not_exist", "name": "x", "source_type": "manual", "content": "y",
        }, timeout=30)
        assert r.status_code == 404

    def test_invalid_source_type_rejected(self, admin):
        admin.post(f"{BASE_URL}/api/agent-framework/knowledge/collections", json={
            "collection_key": f"{self.key}_b", "name": "B"}, timeout=30)
        r = admin.post(f"{BASE_URL}/api/agent-framework/knowledge/sources", json={
            "collection_key": f"{self.key}_b", "name": "x", "source_type": "ftp", "content": "y",
        }, timeout=30)
        assert r.status_code == 400
        admin.delete(f"{BASE_URL}/api/agent-framework/knowledge/collections/{self.key}_b", timeout=30)


# ── Analytics ──

class TestAnalytics:
    def test_overview(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/analytics/overview", timeout=60)
        assert r.status_code == 200
        data = r.json()
        for field in ("executions_total", "success_rate_percent", "est_cost_usd_total", "top_agents"):
            assert field in data

    def test_trends(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/analytics/trends?days=30", timeout=30)
        assert r.status_code == 200
        assert r.json()["days"] == 30

    def test_recommendations(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/analytics/recommendations", timeout=60)
        assert r.status_code == 200
        for rec in r.json()["recommendations"][:5]:
            assert rec["severity"] in ("high", "medium", "low")

    def test_alerts(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/analytics/alerts", timeout=60)
        assert r.status_code == 200
        assert "alerts" in r.json()

    def test_adoption(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/analytics/adoption", timeout=30)
        assert r.status_code == 200

    def test_feedback_and_history(self, admin):
        f = admin.post(f"{BASE_URL}/api/agent-framework/analytics/feedback", json={
            "agent_key": "resume_specialist", "rating": 5, "comment": "pytest feedback",
        }, timeout=30)
        assert f.status_code == 200
        assert f.json()["rating"] == 5
        h = admin.get(f"{BASE_URL}/api/agent-framework/analytics/agents/resume_specialist/history", timeout=30)
        assert h.status_code == 200
        assert h.json()["agent_key"] == "resume_specialist"


# ── Zero-regression checks on existing framework endpoints ──

class TestNoRegression:
    def test_existing_overview_unchanged(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/overview", timeout=60)
        assert r.status_code == 200
        assert r.json()["agents"] >= 200

    def test_marketplace_catalog_unchanged(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/catalog?page=1&page_size=5", timeout=60)
        assert r.status_code == 200
        assert r.json()["total"] >= 200

    def test_marketplace_readiness_still_ready(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/readiness", timeout=60)
        assert r.status_code == 200
        assert r.json()["ready"] is True

    def test_workflows_endpoint_unchanged(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/workflows", timeout=30)
        assert r.status_code == 200

    def test_tools_include_legacy_and_new(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/tools", timeout=30)
        names = {t["name"] for t in r.json()["tools"]}
        assert {"template_render", "db_read", "http_fetch", "knowledge_search"} <= names
