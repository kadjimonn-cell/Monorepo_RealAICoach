"""Unit tests for the native AI Agent Framework core logic (no LLM calls)."""

import pytest

from agent_framework.engine import (
    resolve_path, interpolate, eval_condition, count_steps, validate_workflow_steps,
)
from agent_framework.prompts import render_template
from agent_framework.policy import clamp_timeout, clamp_retries, check_tool_allowed, DEFAULT_POLICY
from agent_framework.providers import provider_registry
from agent_framework.tools import tool_registry


def test_resolve_path():
    ctx = {"input": "hello", "steps": {"s1": {"output": "world", "list": [1, 2]}}}
    assert resolve_path(ctx, "input") == "hello"
    assert resolve_path(ctx, "steps.s1.output") == "world"
    assert resolve_path(ctx, "steps.s1.list.1") == 2
    assert resolve_path(ctx, "steps.missing.output") is None


def test_interpolate():
    ctx = {"input": "goal", "steps": {"s1": {"output": "OK"}}}
    assert interpolate("Do {{input}} after {{steps.s1.output}}", ctx) == "Do goal after OK"
    assert interpolate("Keep {{unknown.path}}", ctx) == "Keep {{unknown.path}}"


def test_render_template():
    assert render_template("Hi {{name}}!", {"name": "Ada"}) == "Hi Ada!"
    assert render_template("Hi {{missing}}!", {}) == "Hi {{missing}}!"


@pytest.mark.parametrize("cond,expected", [
    ({"field": "steps.s1.output", "op": "contains", "value": "CRIT"}, True),
    ({"field": "steps.s1.output", "op": "equals", "value": "critical issue"}, True),
    ({"field": "steps.s1.output", "op": "not_equals", "value": "x"}, True),
    ({"field": "steps.s1.score", "op": "gt", "value": 5}, True),
    ({"field": "steps.s1.score", "op": "lt", "value": 5}, False),
    ({"field": "steps.s1.missing", "op": "exists"}, False),
    ({"field": "steps.s1.output", "op": "exists"}, True),
])
def test_eval_condition(cond, expected):
    ctx = {"steps": {"s1": {"output": "critical issue", "score": 9}}}
    assert eval_condition(cond, ctx) is expected


def test_eval_condition_unknown_op():
    with pytest.raises(ValueError):
        eval_condition({"field": "a", "op": "regex", "value": "x"}, {})


def test_count_steps_nested():
    steps = [
        {"step_id": "a", "type": "agent"},
        {"step_id": "b", "type": "parallel", "branches": [
            [{"step_id": "b1", "type": "tool"}],
            [{"step_id": "b2", "type": "tool"}, {"step_id": "b3", "type": "agent"}],
        ]},
        {"step_id": "c", "type": "condition",
         "then_steps": [{"step_id": "c1", "type": "tool"}], "else_steps": []},
    ]
    assert count_steps(steps) == 7


def test_validate_workflow_steps():
    validate_workflow_steps([
        {"step_id": "a", "type": "agent", "agent_key": "x"},
        {"step_id": "h", "type": "human_approval"},
    ])
    with pytest.raises(ValueError):
        validate_workflow_steps([{"step_id": "a", "type": "bogus"}])
    with pytest.raises(ValueError):
        validate_workflow_steps([{"type": "agent", "agent_key": "x"}])
    with pytest.raises(ValueError):
        validate_workflow_steps([{"step_id": "t", "type": "tool"}])
    with pytest.raises(ValueError):
        validate_workflow_steps([{"step_id": "a", "type": "agent"}])
    with pytest.raises(ValueError):
        validate_workflow_steps([{
            "step_id": "p", "type": "parallel",
            "branches": [[{"step_id": "h", "type": "human_approval"}]],
        }])


def test_policy_clamps():
    assert clamp_timeout(None, DEFAULT_POLICY) == 45.0
    assert clamp_timeout(999, DEFAULT_POLICY) == 120.0
    assert clamp_timeout(0.1, DEFAULT_POLICY) == 1.0
    assert clamp_retries(None, DEFAULT_POLICY) == 1
    assert clamp_retries(99, DEFAULT_POLICY) == 3
    assert clamp_retries(-5, DEFAULT_POLICY) == 0


def test_check_tool_allowed():
    assert check_tool_allowed({"allowed_tools": ["db_read"]}, "db_read")
    assert not check_tool_allowed({"allowed_tools": ["db_read"]}, "http_fetch")
    assert check_tool_allowed({"allowed_tools": ["*"]}, "anything")
    assert not check_tool_allowed({}, "db_read")


def test_provider_registry():
    assert set(provider_registry.list_names()) == {"openai", "anthropic", "google"}
    assert provider_registry.get("openai").name == "openai"
    with pytest.raises(KeyError):
        provider_registry.get("bogus")


def test_tool_registry_builtins():
    names = [t["name"] for t in tool_registry.list_tools()]
    assert {"template_render", "db_read", "http_fetch"} <= set(names)
    with pytest.raises(KeyError):
        tool_registry.get("bogus")


def test_default_agent_catalog():
    from agent_framework.catalog import DEFAULT_AGENTS, AGENT_CATEGORIES
    from agent_framework.tools import tool_registry as tr

    assert len(DEFAULT_AGENTS) >= 55
    keys = [a["agent_key"] for a in DEFAULT_AGENTS]
    assert len(keys) == len(set(keys)), "duplicate agent_key in catalog"
    valid_tools = {t["name"] for t in tr.list_tools()}
    for agent in DEFAULT_AGENTS:
        assert agent["category"] in AGENT_CATEGORIES, agent["agent_key"]
        assert len(agent["system_prompt"]) > 40, agent["agent_key"]
        assert agent["provider"] == "openai"
        assert set(agent["allowed_tools"]) <= valid_tools, agent["agent_key"]
    # original 10 must remain present with unchanged keys
    original = {"security_auditor", "software_engineer", "solution_architect", "qa_engineer",
                "data_analyst", "devops_engineer", "product_manager", "researcher",
                "doc_writer", "career_coach"}
    assert original <= set(keys)


def test_default_prompt_catalog():
    from agent_framework.prompts import DEFAULT_PROMPTS

    assert len(DEFAULT_PROMPTS) >= 8
    keys = [p["prompt_key"] for p in DEFAULT_PROMPTS]
    assert len(keys) == len(set(keys))


@pytest.mark.asyncio
async def test_template_render_tool():
    result = await tool_registry.execute(
        "template_render", {"template": "A {{x}} B", "variables": {"x": "1"}}, {}
    )
    assert result == "A 1 B"


@pytest.mark.asyncio
async def test_http_fetch_rejects_non_https():
    with pytest.raises(ValueError):
        await tool_registry.execute("http_fetch", {"url": "http://insecure.example"}, {})


@pytest.mark.asyncio
async def test_db_read_rejects_unlisted_collection():
    with pytest.raises(PermissionError):
        await tool_registry.execute("db_read", {"collection": "users"}, {})
