"""Iter868 — AI Agent Framework catalog expansion (55 agents, 7 categories) + panel.

Covers the review scenarios:
- Overview shape & category counts
- Agent seeding (55, category populated, spot checks for new + original keys)
- Seed idempotency (count stable across calls; admin edits survive)
- Prompts (8 keys incl. 4 new; render substitutes variables)
- Live LLM execute of a new agent (interview_coach)
- AgentUpsert accepts 'category' (create, verify, delete)
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

XRW = {"X-Requested-With": "XMLHttpRequest"}

VALID_PROVIDERS = {"openai", "anthropic", "google"}

EXPECTED_CATEGORIES = {
    "Engineering": 13,
    "Security & Compliance": 6,
    "Quality": 5,
    "Data & AI": 9,
    "Business & Growth": 9,
    "Content & Communication": 7,
    "Coaching": 6,
}

NEW_AGENT_KEYS = [
    "frontend_developer", "penetration_tester", "prompt_engineer",
    "interview_coach", "seo_specialist", "nlp_specialist",
    "analytics_engineer", "resume_specialist",
]

ORIGINAL_AGENT_KEYS = [
    "security_auditor", "career_coach", "software_engineer", "solution_architect",
    "qa_engineer", "data_analyst", "devops_engineer", "product_manager",
    "researcher", "doc_writer",
]

NEW_PROMPT_KEYS = {"bug_triage", "api_design", "seo_audit", "incident_postmortem"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", **XRW})
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return s


# ── Overview ──────────────────────────────────────────────────────────

class TestOverviewExpanded:
    def test_overview_returns_55_and_seven_categories(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/overview", timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()

        assert data["agents"] == 55, f"expected 55 agents, got {data['agents']}"

        cats = data.get("categories")
        assert isinstance(cats, dict), f"categories must be a dict, got {type(cats)}"
        assert set(cats.keys()) == set(EXPECTED_CATEGORIES.keys()), (
            f"category set mismatch: got {set(cats.keys())}"
        )
        for name, expected in EXPECTED_CATEGORIES.items():
            assert cats[name] == expected, f"{name}: expected {expected}, got {cats[name]}"

        assert "Uncategorized" not in cats, "no Uncategorized bucket expected"


# ── Agent catalog ─────────────────────────────────────────────────────

class TestAgentCatalog:
    def test_55_agents_and_metadata(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/agents", timeout=15)
        assert r.status_code == 200
        agents = r.json()["agents"]
        assert len(agents) == 55, f"expected 55 agents, got {len(agents)}"

        for a in agents:
            assert a.get("category"), f"agent {a.get('agent_key')} missing category"
            assert a.get("system_prompt"), f"agent {a.get('agent_key')} missing system_prompt"
            assert a.get("provider") in VALID_PROVIDERS, (
                f"agent {a.get('agent_key')} invalid provider {a.get('provider')}"
            )

    def test_new_and_original_keys_present(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/agents", timeout=15)
        keys = {a["agent_key"] for a in r.json()["agents"]}
        missing_new = [k for k in NEW_AGENT_KEYS if k not in keys]
        assert not missing_new, f"missing new agents: {missing_new}"
        missing_orig = [k for k in ORIGINAL_AGENT_KEYS if k not in keys]
        assert not missing_orig, f"missing original agents: {missing_orig}"


# ── Seeding idempotency + admin-edit preservation ─────────────────────

class TestSeedingIdempotency:
    def test_double_call_stable_count_and_edit_persists(self, admin_session):
        r1 = admin_session.get(f"{API}/agent-framework/agents", timeout=15)
        assert r1.status_code == 200
        count1 = len(r1.json()["agents"])

        r2 = admin_session.get(f"{API}/agent-framework/agents", timeout=15)
        count2 = len(r2.json()["agents"])
        assert count1 == count2 == 55, f"count changed: {count1} -> {count2}"

        # Grab interview_coach current record and edit description
        rc = admin_session.get(f"{API}/agent-framework/agents/interview_coach", timeout=15)
        assert rc.status_code == 200, rc.text[:200]
        original = rc.json()
        original_desc = original.get("description", "")

        edited_desc = f"EDITED-IDEMPOTENCY-TEST-{uuid.uuid4().hex[:6]}"
        payload = {
            "agent_key": "interview_coach",
            "name": original.get("name", "Interview Coach"),
            "role": original.get("role", "Interview Preparation"),
            "category": original.get("category", "Coaching"),
            "description": edited_desc,
            "system_prompt": original.get("system_prompt", ""),
            "provider": original.get("provider", "openai"),
            "model": original.get("model", "gpt-4o"),
            "allowed_tools": original.get("allowed_tools", []),
            "tags": original.get("tags", []),
        }
        ru = admin_session.post(f"{API}/agent-framework/agents", json=payload, timeout=20)
        assert ru.status_code == 200, ru.text[:300]

        # After edit, re-fetch — must remain edited (seeder must NOT overwrite)
        rc2 = admin_session.get(f"{API}/agent-framework/agents/interview_coach", timeout=15)
        assert rc2.status_code == 200
        assert rc2.json().get("description") == edited_desc, (
            "admin edit was overwritten (or not persisted)"
        )

        # Restore original description to avoid contaminating future runs
        payload["description"] = original_desc
        admin_session.post(f"{API}/agent-framework/agents", json=payload, timeout=20)

        # Count still 55 after edits
        r3 = admin_session.get(f"{API}/agent-framework/agents", timeout=15)
        assert len(r3.json()["agents"]) == 55


# ── Prompts ───────────────────────────────────────────────────────────

class TestPrompts:
    def test_prompts_include_new_templates(self, admin_session):
        r = admin_session.get(f"{API}/agent-framework/prompts", timeout=15)
        assert r.status_code == 200
        keys = {p["prompt_key"] for p in r.json()["prompts"]}
        assert len(keys) >= 8, f"expected >=8 prompts, got {len(keys)}"
        missing = NEW_PROMPT_KEYS - keys
        assert not missing, f"missing new prompts: {missing}"

    def test_render_bug_triage_substitutes_variables(self, admin_session):
        r = admin_session.post(
            f"{API}/agent-framework/prompts/bug_triage/render",
            json={"variables": {"report": "login fails", "area": "auth"}},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:300]
        rendered = r.json().get("rendered", "")
        assert "login fails" in rendered, f"'report' not substituted in: {rendered[:200]}"
        assert "auth" in rendered, f"'area' not substituted in: {rendered[:200]}"


# ── Live execute a NEW agent ──────────────────────────────────────────

class TestNewAgentExecute:
    def test_interview_coach_execute_live(self, admin_session):
        r = admin_session.post(
            f"{API}/agent-framework/agents/interview_coach/execute",
            json={"input": "Give me one short interview tip"},
            timeout=90,
        )
        assert r.status_code == 200, f"execute failed: {r.status_code} {r.text[:300]}"
        out = r.json().get("output", "")
        assert isinstance(out, str) and len(out.strip()) > 5, f"empty/short output: {out!r}"


# ── AgentUpsert with 'category' field ─────────────────────────────────

class TestAgentUpsertCategory:
    def test_create_with_category_then_delete(self, admin_session):
        key = f"test_upsert_cat_{uuid.uuid4().hex[:8]}"
        payload = {
            "agent_key": key,
            "name": "Category Field Test Agent",
            "role": "Engineering",
            "category": "Engineering",
            "description": "temp agent to verify category upsert",
            "system_prompt": "You are a test agent.",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "allowed_tools": [],
            "tags": ["test"],
        }
        try:
            rc = admin_session.post(f"{API}/agent-framework/agents", json=payload, timeout=20)
            assert rc.status_code == 200, rc.text[:300]

            rg = admin_session.get(f"{API}/agent-framework/agents/{key}", timeout=15)
            assert rg.status_code == 200
            body = rg.json()
            assert body.get("category") == "Engineering", (
                f"category field not persisted: {body}"
            )
        finally:
            admin_session.delete(f"{API}/agent-framework/agents/{key}", timeout=15)
            rgone = admin_session.get(f"{API}/agent-framework/agents/{key}", timeout=15)
            assert rgone.status_code == 404, "cleanup delete failed"
