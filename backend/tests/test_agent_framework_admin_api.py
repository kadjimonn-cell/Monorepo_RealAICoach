"""End-to-end pytest suite for the AI Agent Framework admin API.

Covers the review scenarios: auth guards, overview, agent CRUD w/ versioning,
agent execution + memory, prompts, tools, workflow validation, workflow E2E
with parallel/condition/HITL approve+reject, policy, and audit trail.
"""

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

XRW = {"X-Requested-With": "XMLHttpRequest"}


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", **XRW})
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    try:
        return _login(FREE_EMAIL, FREE_PASSWORD)
    except AssertionError:
        pytest.skip("free user login unavailable")


# ── Auth guards ──────────────────────────────────────────────────────────

class TestAuthGuards:
    def test_unauthenticated_overview_returns_401_or_403(self):
        r = requests.get(f"{API}/agent-framework/overview", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_non_admin_overview_returns_403(self, free_session):
        r = free_session.get(f"{API}/agent-framework/overview", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 for free user, got {r.status_code}"

    def test_non_admin_agents_returns_403(self, free_session):
        r = free_session.get(f"{API}/agent-framework/agents", timeout=15)
        assert r.status_code in (401, 403)


# ── Overview & directories ─────────────────────────────────────────────

class TestOverview:
    def test_overview_shape(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/overview", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["agents"] >= 10, f"expected at least 10 seeded agents, got {data['agents']}"
        assert data["tools"] >= 3
        assert set(data["providers"]) == {"openai", "anthropic", "google"}
        assert isinstance(data["policy"], dict) and data["policy"].get("max_steps_per_workflow")

    def test_agents_seeded(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/agents", timeout=15)
        assert r.status_code == 200
        agents = r.json()["agents"]
        keys = {a["agent_key"] for a in agents}
        expected = {
            "security_auditor", "software_engineer", "solution_architect",
            "qa_engineer", "data_analyst", "devops_engineer", "product_manager",
            "researcher", "doc_writer", "career_coach",
        }
        missing = expected - keys
        assert not missing, f"missing seeded agents: {missing}"

    def test_tools_list(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/tools", timeout=15)
        assert r.status_code == 200
        names = {t["name"] for t in r.json()["tools"]}
        assert {"template_render", "db_read", "http_fetch"} <= names

    def test_prompts_seeded(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/prompts", timeout=15)
        assert r.status_code == 200
        keys = {p["prompt_key"] for p in r.json()["prompts"]}
        expected = {"code_review", "security_audit", "career_advice", "doc_summary"}
        assert expected <= keys, f"missing prompt keys: {expected - keys}"


# ── Agent CRUD + versioning ────────────────────────────────────────────

class TestAgentCrud:
    key = f"test_qa_agent_{uuid.uuid4().hex[:8]}"

    def test_reject_invalid_provider(self, admin_session):
        payload = {
            "agent_key": f"{self.key}_bad",
            "name": "Bad Provider Agent",
            "system_prompt": "hi",
            "provider": "bogus_ai",
        }
        r = admin_session.post(f"{API}/agent-framework/agents", json=payload, timeout=15)
        assert r.status_code == 400, f"expected 400 for invalid provider, got {r.status_code}: {r.text[:200]}"

    def test_create_update_version_delete(self, admin_session):
        payload = {
            "agent_key": self.key,
            "name": "QA Test Agent",
            "role": "qa",
            "description": "temp",
            "system_prompt": "You are a QA helper.",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "allowed_tools": [],
            "tags": ["test"],
        }
        r1 = admin_session.post(f"{API}/agent-framework/agents", json=payload, timeout=15)
        assert r1.status_code == 200, r1.text[:300]
        created = r1.json()
        assert created["agent_key"] == self.key
        assert int(created.get("version", 1)) == 1

        payload["name"] = "QA Test Agent v2"
        r2 = admin_session.post(f"{API}/agent-framework/agents", json=payload, timeout=15)
        assert r2.status_code == 200
        assert int(r2.json().get("version", 0)) == 2

        rv = admin_session.get(f"{API}/agent-framework/agents/{self.key}/versions", timeout=15)
        assert rv.status_code == 200
        versions = rv.json()["versions"]
        assert len(versions) >= 1, "expected at least one archived snapshot"

        rd = admin_session.delete(f"{API}/agent-framework/agents/{self.key}", timeout=15)
        assert rd.status_code == 200
        assert rd.json().get("deleted") is True

        rg = admin_session.get(f"{API}/agent-framework/agents/{self.key}", timeout=15)
        assert rg.status_code == 404


# ── Agent execution + memory ───────────────────────────────────────────

class TestAgentExecution:
    def test_career_coach_execute_with_memory(self, admin_session):
        session_id = f"test-qa-{uuid.uuid4().hex[:8]}"

        r1 = admin_session.post(
            f"{API}/agent-framework/agents/career_coach/execute",
            json={"input": "one short tip for a new dev", "session_id": session_id},
            timeout=90,
        )
        assert r1.status_code == 200, f"first exec failed: {r1.status_code} {r1.text[:400]}"
        out1 = r1.json()
        assert isinstance(out1.get("output", ""), str) and len(out1["output"]) > 5, out1

        r2 = admin_session.post(
            f"{API}/agent-framework/agents/career_coach/execute",
            json={"input": "what did I just ask?", "session_id": session_id},
            timeout=90,
        )
        assert r2.status_code == 200, r2.text[:300]
        out2 = r2.json()
        assert isinstance(out2.get("output", ""), str) and len(out2["output"]) > 5


# ── Prompt render ──────────────────────────────────────────────────────

class TestPromptRender:
    def test_render_prompt(self, admin_session):
        r = admin_session.post(
            f"{API}/agent-framework/prompts/career_advice/render",
            json={"variables": {"goal": "get promoted", "context": "senior engineer"}},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:300]
        rendered = r.json().get("rendered", "")
        assert "get promoted" in rendered or "senior engineer" in rendered, rendered


# ── Workflow validation ────────────────────────────────────────────────

class TestWorkflowValidation:
    def _post(self, session, steps, name="invalid-wf"):
        return session.post(
            f"{API}/agent-framework/workflows",
            json={"name": name, "description": "", "steps": steps, "enabled": True},
            timeout=15,
        )

    def test_invalid_step_type(self, admin_session):
        r = self._post(admin_session, [{"step_id": "a", "type": "bogus"}])
        assert r.status_code == 400

    def test_missing_step_id(self, admin_session):
        r = self._post(admin_session, [{"type": "agent"}])
        assert r.status_code == 400

    def test_human_approval_inside_parallel_rejected(self, admin_session):
        steps = [{
            "step_id": "p", "type": "parallel",
            "branches": [[{"step_id": "h", "type": "human_approval"}]],
        }]
        r = self._post(admin_session, steps)
        assert r.status_code == 400


# ── Policy ─────────────────────────────────────────────────────────────

class TestPolicy:
    def test_get_and_update_policy(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/policy", timeout=15)
        assert r.status_code == 200
        pol = r.json()
        assert pol.get("max_steps_per_workflow") == 25

        u = admin_session.put(
            f"{API}/agent-framework/policy",
            json={"changes": {"max_executions_per_hour": 150}},
            timeout=15,
        )
        assert u.status_code == 200
        assert u.json().get("max_executions_per_hour") == 150


# ── Audit ──────────────────────────────────────────────────────────────

class TestAudit:
    def test_audit_has_entries(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/audit?limit=200", timeout=15)
        assert r.status_code == 200
        entries = r.json()["audit"]
        actions = {e.get("action") for e in entries}
        # At least agent-related audit entries should exist by now
        assert any(a in actions for a in ("agent_executed", "workflow_created", "policy_updated")), \
            f"no expected audit actions found; saw: {actions}"


# ── Workflow E2E: parallel + condition + HITL approve ─────────────────

WF_STEPS = [
    {
        "step_id": "s1",
        "type": "agent",
        "agent_key": "doc_writer",
        "input_template": "{{input}}",
    },
    {
        "step_id": "s2",
        "type": "parallel",
        "branches": [
            [{"step_id": "b1", "type": "tool", "tool_name": "template_render",
              "args": {"template": "branch-a-{{input}}", "variables": {"input": "{{input}}"}}}],
            [{"step_id": "b2", "type": "tool", "tool_name": "template_render",
              "args": {"template": "branch-b-{{input}}", "variables": {"input": "{{input}}"}}}],
        ],
    },
    {
        "step_id": "s3",
        "type": "condition",
        "condition": {"field": "steps.s1.output", "op": "exists"},
        "then_steps": [{
            "step_id": "s3a", "type": "tool", "tool_name": "template_render",
            "args": {"template": "cond-ok", "variables": {}},
        }],
        "else_steps": [],
    },
    {"step_id": "s4", "type": "human_approval"},
    {
        "step_id": "s5",
        "type": "tool",
        "tool_name": "template_render",
        "args": {"template": "final:{{steps.s1.output}}", "variables": {"steps.s1.output": "{{steps.s1.output}}"}},
    },
]


def _poll(session, exec_id, want_status, max_wait=90):
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        r = session.get(f"{API}/agent-framework/executions/{exec_id}", timeout=15)
        if r.status_code == 200:
            last = r.json()
            if last.get("status") == want_status:
                return last
            if last.get("status") in ("failed", "rejected") and want_status != last["status"]:
                return last
        time.sleep(2)
    return last


class TestWorkflowE2E:
    @pytest.fixture(scope="class")
    def workflow_id(self, admin_session):
        r = admin_session.post(
            f"{API}/agent-framework/workflows",
            json={"name": f"QA E2E WF {uuid.uuid4().hex[:6]}", "description": "e2e", "steps": WF_STEPS, "enabled": True},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:400]
        wid = r.json()["workflow_id"]
        yield wid
        admin_session.delete(f"{API}/agent-framework/workflows/{wid}", timeout=15)

    def test_execute_pauses_at_human_approval_then_approves_to_completed(self, admin_session, workflow_id):
        r = admin_session.post(
            f"{API}/agent-framework/workflows/{workflow_id}/execute",
            json={"input": "release-note draft"},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        exec_id = r.json()["execution_id"]
        assert r.json().get("status") in ("running", "waiting_human", "queued")

        waiting = _poll(admin_session, exec_id, "waiting_human", max_wait=90)
        assert waiting and waiting.get("status") == "waiting_human", \
            f"execution did not reach waiting_human: {waiting}"
        assert waiting.get("pending_approval"), "pending_approval field should be populated"

        # Parallel + condition should have completed OK before pause
        steps_ctx = (waiting.get("context") or {}).get("steps") or {}
        for sid in ("s2", "s3"):
            assert steps_ctx.get(sid, {}).get("status") == "ok", \
                f"step {sid} not ok: {steps_ctx.get(sid)}"

        ap = admin_session.post(
            f"{API}/agent-framework/executions/{exec_id}/approve",
            json={"note": "ok"},
            timeout=15,
        )
        assert ap.status_code == 200, ap.text[:300]

        completed = _poll(admin_session, exec_id, "completed", max_wait=90)
        assert completed and completed.get("status") == "completed", f"never completed: {completed}"

        steps_ctx = (completed.get("context") or {}).get("steps") or {}
        final = steps_ctx.get("s5", {})
        assert final.get("status") == "ok"
        assert "final:" in str(final.get("output", "")), f"final template not interpolated: {final}"

    def test_execute_reject_path(self, admin_session, workflow_id):
        r = admin_session.post(
            f"{API}/agent-framework/workflows/{workflow_id}/execute",
            json={"input": "release-note draft 2"},
            timeout=30,
        )
        assert r.status_code == 200
        exec_id = r.json()["execution_id"]

        waiting = _poll(admin_session, exec_id, "waiting_human", max_wait=90)
        assert waiting and waiting.get("status") == "waiting_human"

        rj = admin_session.post(
            f"{API}/agent-framework/executions/{exec_id}/reject",
            json={"note": "nope"},
            timeout=15,
        )
        assert rj.status_code == 200

        final = _poll(admin_session, exec_id, "rejected", max_wait=30)
        assert final and final.get("status") == "rejected", final


# ── Regression: pre-existing endpoint ─────────────────────────────────

class TestRegression:
    def test_email_templates_audit_admin(self, admin_session):
        r = admin_session.get(f"{API}/email-notifications/templates/audit", timeout=15)
        assert r.status_code == 200, f"regression: email templates audit broke: {r.status_code} {r.text[:200]}"
