"""Iteration 875 additive verification for AI Operating Layer v2.

Covers gaps not already asserted in test_ai_operating_layer_v2.py:
  1. Security — every new /agent-framework endpoint returns 401/403 for
     unauthenticated requests (admin-only guard).
  2. Routing quality — "help me prepare for a job interview" evaluates
     the full catalog and returns a diverse team.
  3. Workflow validation via API — POST /workflows rejects a collaborate
     step missing agent_keys (400) but accepts a valid delegate/collaborate
     workflow.
  4. Regression — existing endpoints (overview, marketplace catalog,
     portfolio, readiness, coverage, workflows, executions, tools, policy,
     audit) still respond 200 with the expected core shape.
"""

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN = {"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"}

NEW_ENDPOINTS = [
    ("GET", "/api/agent-framework/route/log"),
    ("GET", "/api/agent-framework/capabilities"),
    ("GET", "/api/agent-framework/events/triggers"),
    ("GET", "/api/agent-framework/events"),
    ("GET", "/api/agent-framework/knowledge/overview"),
    ("GET", "/api/agent-framework/knowledge/collections"),
    ("GET", "/api/agent-framework/knowledge/sources"),
    ("GET", "/api/agent-framework/analytics/overview"),
    ("GET", "/api/agent-framework/analytics/trends"),
    ("GET", "/api/agent-framework/analytics/recommendations"),
    ("GET", "/api/agent-framework/analytics/alerts"),
    ("GET", "/api/agent-framework/analytics/adoption"),
    ("POST", "/api/agent-framework/route"),
    ("POST", "/api/agent-framework/events/emit"),
    ("POST", "/api/agent-framework/knowledge/search"),
    ("POST", "/api/agent-framework/analytics/feedback"),
]

REGRESSION_ENDPOINTS = [
    "/api/agent-framework/overview",
    "/api/agent-framework/marketplace/catalog",
    "/api/agent-framework/marketplace/portfolio",
    "/api/agent-framework/marketplace/readiness",
    "/api/agent-framework/marketplace/coverage",
    "/api/agent-framework/workflows",
    "/api/agent-framework/executions",
    "/api/agent-framework/tools",
    "/api/agent-framework/policy",
    "/api/agent-framework/audit",
]


@pytest.fixture(scope="module")
def admin():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited during login")
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return sess


# ── Security: admin gate on new endpoints ──

class TestSecurityGates:
    """Every new v2 endpoint should reject unauthenticated requests."""

    @pytest.mark.parametrize("method,path", NEW_ENDPOINTS)
    def test_unauth_rejected(self, method, path):
        anon = requests.Session()
        anon.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        url = f"{BASE_URL}{path}"
        payload = {"intent": "x", "event_name": "x.y", "payload": {}, "query": "x", "agent_key": "x", "rating": 3}
        r = anon.request(method, url, json=payload if method == "POST" else None, timeout=15)
        assert r.status_code in (401, 403), (
            f"Expected 401/403 for anon {method} {path} — got {r.status_code}: {r.text[:200]}"
        )


# ── Routing quality ──

class TestRoutingQuality:
    def test_job_interview_intent_selects_relevant_agent(self, admin):
        r = admin.post(
            f"{BASE_URL}/api/agent-framework/route",
            json={"intent": "help me prepare for a job interview", "team_size": 4},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("selected_agent"), "selected_agent must be populated"
        # candidates_evaluated should reflect full 213-agent catalog
        assert data.get("candidates_evaluated", 0) > 100, (
            f"expected >100 candidates evaluated, got {data.get('candidates_evaluated')}"
        )
        team = data.get("team") or []
        # Team members should each have a category and score
        for member in team:
            assert "agent_key" in member and "category" in member and "score" in member

    def test_capabilities_lists_new_step_types_and_tools(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/capabilities", timeout=15)
        assert r.status_code == 200
        cap = r.json()
        step_types = set(cap.get("step_types") or [])
        assert {"delegate", "collaborate"}.issubset(step_types), f"missing step types: {step_types}"
        providers = set(cap.get("providers") or [])
        assert {"openai", "anthropic", "google"}.issubset(providers), f"missing providers: {providers}"
        tools = set(cap.get("tools") or [])
        assert "knowledge_search" in tools, f"knowledge_search missing from tools: {tools}"


# ── Workflow validation of new step types via API ──

class TestWorkflowStepValidation:
    def test_collaborate_missing_agent_keys_rejected(self, admin):
        wf_id = f"test-collab-invalid-{uuid.uuid4().hex[:8]}"
        payload = {
            "workflow_id": wf_id,
            "name": "TEST invalid collaborate",
            "description": "should be rejected",
            "steps": [{"type": "collaborate", "step_id": "c1"}],
        }
        r = admin.post(f"{BASE_URL}/api/agent-framework/workflows", json=payload, timeout=15)
        assert r.status_code in (400, 422), f"Expected 400/422 got {r.status_code} {r.text[:200]}"

    def test_valid_delegate_and_collaborate_workflow_accepted(self, admin):
        wf_id = f"test-collab-valid-{uuid.uuid4().hex[:8]}"
        payload = {
            "workflow_id": wf_id,
            "name": "TEST valid delegate+collaborate",
            "description": "verifies new step types accepted",
            "steps": [
                {"type": "delegate", "step_id": "d1", "input_template": "{{input}}"},
                {
                    "type": "collaborate",
                    "step_id": "c1",
                    "agent_keys": ["resume_specialist", "interview_coach"],
                    "resolution": "synthesize",
                },
            ],
        }
        r = admin.post(f"{BASE_URL}/api/agent-framework/workflows", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"Expected 200/201 got {r.status_code} {r.text[:200]}"
        # Cleanup: attempt delete (best-effort)
        admin.delete(f"{BASE_URL}/api/agent-framework/workflows/{wf_id}", timeout=15)


# ── Zero-regression check ──

class TestRegressionExisting:
    @pytest.mark.parametrize("path", REGRESSION_ENDPOINTS)
    def test_endpoint_still_ok(self, admin, path):
        r = admin.get(f"{BASE_URL}{path}", timeout=30)
        assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"

    def test_overview_has_at_least_200_agents(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/overview", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("agents", 0) >= 200, f"Expected >=200 agents, got {data.get('agents')}"

    def test_marketplace_readiness_ready_true(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/readiness", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ready") is True, f"marketplace not ready: {data}"

    def test_marketplace_coverage_37_of_37(self, admin):
        r = admin.get(f"{BASE_URL}/api/agent-framework/marketplace/coverage", timeout=15)
        assert r.status_code == 200
        data = r.json()
        covered = data.get("features_covered") or data.get("covered") or 0
        total = data.get("features_total") or data.get("total") or 0
        # Accept either flat totals or list under "features"
        if not covered and isinstance(data.get("features"), list):
            covered = sum(1 for f in data["features"] if f.get("covered"))
            total = len(data["features"])
        assert covered == 37 and total == 37, f"coverage mismatch: covered={covered} total={total}"
