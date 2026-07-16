"""Autonomous Engine mandatory tests gate — durable offline platform invariants.

Fast (<5s), no network, no external env. This suite is the DEFAULT_TEST_GATE_SUITE
for the Autonomous Engine pipeline; keep it green and keep it offline.
"""

import sys

import pytest

sys.path.insert(0, "/app/backend")


class TestWorkflowEngineInvariants:
    def test_all_step_types_validate(self):
        from agent_framework.engine import validate_workflow_steps

        validate_workflow_steps([
            {"type": "agent", "step_id": "s1", "agent_key": "x"},
            {"type": "tool", "step_id": "s2", "tool_name": "template_render"},
            {"type": "condition", "step_id": "s3", "condition": {}, "then_steps": [], "else_steps": []},
            {"type": "parallel", "step_id": "s4", "branches": []},
            {"type": "human_approval", "step_id": "s5"},
            {"type": "delegate", "step_id": "s6"},
            {"type": "collaborate", "step_id": "s7", "agent_keys": ["a"]},
        ])

    def test_invalid_step_rejected(self):
        from agent_framework.engine import validate_workflow_steps

        with pytest.raises(ValueError):
            validate_workflow_steps([{"type": "nonsense", "step_id": "x"}])


class TestAgentCatalogInvariants:
    def test_catalog_has_200_plus_agents(self):
        from agent_framework.catalog import DEFAULT_AGENTS

        assert len(DEFAULT_AGENTS) >= 200
        keys = [a["agent_key"] for a in DEFAULT_AGENTS]
        assert len(keys) == len(set(keys)), "agent_key values must be unique"

    def test_routing_scorer_is_deterministic(self):
        from agent_framework.router_service import score_agent, _tokenize

        agent = {"agent_key": "a", "name": "Resume Coach", "role": "resume expert",
                 "category": "Career", "description": "resume help", "tags": ["resume"],
                 "feature_mappings": ["resume_builder"], "status": "active"}
        words = _tokenize("improve my resume")
        s1 = score_agent(agent, words, "resume_builder", None)
        s2 = score_agent(agent, words, "resume_builder", None)
        assert s1 == s2 and s1 > 50


class TestEmailTemplateCatalogInvariants:
    def test_critical_templates_registered_and_wrapped(self):
        from utils.email_templates import TEMPLATE_CATALOG

        for key in ("autonomous_engine_report", "security_runbook_monitor_report",
                    "career_offer_letters_review", "admin_outbound"):
            entry = TEMPLATE_CATALOG.get(key)
            assert entry, f"{key} missing from TEMPLATE_CATALOG"

    def test_catalog_builders_not_cross_wired(self):
        from utils.email_templates import TEMPLATE_CATALOG

        assert TEMPLATE_CATALOG["admin_outbound"]["builder"].__name__ == "build_admin_outbound_email"
        assert TEMPLATE_CATALOG["autonomous_engine_report"]["builder"].__name__ == "build_autonomous_engine_report_email"


class TestOfferLetterInvariants:
    def test_variant_mapping_complete(self):
        from routes.careers_offers import _variant_for_offer

        assert _variant_for_offer({"state": "expired"}) == "expired"
        assert _variant_for_offer({"state": "rescinded"}) == "rescinded"
        assert _variant_for_offer({"state": "declined"}) == "declined"
        assert _variant_for_offer({"state": "accepted"}) == "accepted"
        assert _variant_for_offer({"state": "sent"}) == "original"


class TestA11yAutoFixerSafety:
    def test_never_corrupts_generics_or_arrows(self):
        from routes.accessibility_audit import _safe_insert_label

        assert _safe_insert_label("const r = useRef<TextInput>(null);", "TextInput", "X") is None
        out = _safe_insert_label('<TouchableOpacity onPress={() => go()} style={s.b}>', "TouchableOpacity", "B")
        assert "=>" in out and '= accessibilityLabel' not in out.replace('} accessibilityLabel', '')


class TestAnalyticsInvariants:
    def test_cost_estimation_monotonic(self):
        from agent_framework.analytics import estimate_cost

        assert estimate_cost("gpt-4o", 0, 0) == 0.0
        assert estimate_cost("gpt-4o", 2000, 2000) > estimate_cost("gpt-4o", 1000, 1000)
