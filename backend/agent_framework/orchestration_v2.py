"""Orchestration v2: hierarchical delegation, collaborative multi-agent steps
with conflict resolution, and event-driven workflow triggers."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

RESOLUTION_STRATEGIES = {"synthesize", "first_success", "all"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Hierarchical delegation ──

async def execute_delegate(
    step: Dict[str, Any], context: Dict[str, Any], policy: Dict[str, Any],
    user_id: Optional[str], timeout: float,
) -> Dict[str, Any]:
    """Supervisor step: routes the task to the best-fit sub-agent and executes it."""
    from agent_framework.engine import interpolate
    from agent_framework.agents import get_agent, execute_agent
    from agent_framework.router_service import route_intent
    from agent_framework.audit import log_audit

    task = interpolate(step.get("input_template", "{{input}}"), context)
    candidates = step.get("candidate_keys") or []
    routed = await route_intent(task, feature_key=step.get("feature_key", ""), team_size=3, user_id=user_id, log=False)
    chosen_key = None
    if candidates:
        candidate_set = set(candidates)
        for member in ([routed.get("selected_agent")] if routed.get("selected_agent") else []) + routed.get("team", []):
            if member and member["agent_key"] in candidate_set:
                chosen_key = member["agent_key"]
                break
        if not chosen_key:
            chosen_key = candidates[0]
    elif routed.get("selected_agent"):
        chosen_key = routed["selected_agent"]["agent_key"]
    if not chosen_key:
        raise ValueError("Delegation failed: no eligible sub-agent found")
    agent = await get_agent(chosen_key)
    if not agent:
        raise ValueError(f"Delegated agent '{chosen_key}' not found")
    if not agent.get("enabled", True):
        raise ValueError(f"Delegated agent '{chosen_key}' is disabled")
    result = await execute_agent(agent, task, user_id=user_id, timeout_seconds=timeout)
    await log_audit("task_delegated", user_id, "agent", chosen_key,
                    {"step_id": step.get("step_id"), "candidates": candidates[:10]})
    return {"delegated_to": chosen_key, "agent_name": agent.get("name", ""), "output": result["output"]}


# ── Collaborative execution with conflict resolution ──

async def execute_collaborate(
    step: Dict[str, Any], context: Dict[str, Any], policy: Dict[str, Any],
    user_id: Optional[str], timeout: float,
) -> Dict[str, Any]:
    from agent_framework.engine import interpolate
    from agent_framework.agents import get_agent, execute_agent
    from agent_framework.audit import log_audit

    agent_keys = (step.get("agent_keys") or [])[: int(policy["max_parallel_branches"])]
    strategy = step.get("resolution", "synthesize")
    if strategy not in RESOLUTION_STRATEGIES:
        strategy = "synthesize"
    task = interpolate(step.get("input_template", "{{input}}"), context)

    async def _run(key: str) -> Dict[str, Any]:
        agent = await get_agent(key)
        if not agent:
            raise ValueError(f"Agent '{key}' not found")
        if not agent.get("enabled", True):
            raise ValueError(f"Agent '{key}' is disabled")
        result = await execute_agent(agent, task, user_id=user_id, timeout_seconds=timeout)
        return {"agent_key": key, "name": agent.get("name", ""), "output": result["output"]}

    results = await asyncio.gather(*[_run(k) for k in agent_keys], return_exceptions=True)
    contributions = [r for r in results if isinstance(r, dict)]
    failures = [{"agent_key": agent_keys[i], "error": str(r)}
                for i, r in enumerate(results) if isinstance(r, Exception)]
    if not contributions:
        raise RuntimeError(f"All collaborators failed: {'; '.join(f['error'] for f in failures)}")

    if strategy == "first_success":
        resolved = contributions[0]["output"]
    elif strategy == "all":
        resolved = "\n\n".join(f"[{c['name']}]\n{c['output']}" for c in contributions)
    else:  # synthesize (conflict resolution via arbiter)
        arbiter_key = step.get("arbiter_key")
        combined = "\n\n".join(f"--- Contribution from {c['name']} ({c['agent_key']}) ---\n{c['output']}" for c in contributions)
        if arbiter_key:
            arbiter = await get_agent(arbiter_key)
            if arbiter and arbiter.get("enabled", True):
                arb_prompt = (
                    f"Task: {task}\n\nMultiple specialist agents produced the contributions below. "
                    f"Resolve any conflicts and synthesize one final, coherent answer.\n\n{combined}"
                )
                arb_result = await execute_agent(arbiter, arb_prompt, user_id=user_id, timeout_seconds=timeout)
                resolved = arb_result["output"]
            else:
                resolved = combined
        else:
            resolved = combined

    await log_audit("agents_collaborated", user_id, "workflow_step", step.get("step_id", ""),
                    {"agents": agent_keys, "strategy": strategy, "failures": len(failures)})
    return {
        "strategy": strategy,
        "contributors": [c["agent_key"] for c in contributions],
        "failures": failures,
        "contributions": contributions,
        "resolution": resolved,
        "output": resolved,
    }


# ── Event-driven triggers ──

async def list_triggers() -> List[Dict[str, Any]]:
    from routes.db import db

    return await db.af_event_triggers.find({}, {"_id": 0}).sort("event_name", 1).to_list(length=200)


async def upsert_trigger(payload: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.audit import log_audit

    workflow = await db.af_workflows.find_one({"workflow_id": payload["workflow_id"]}, {"_id": 0, "workflow_id": 1, "name": 1})
    if not workflow:
        raise KeyError("Workflow not found")
    trigger_id = payload.get("trigger_id") or str(uuid.uuid4())
    now = _now()
    doc = {
        "trigger_id": trigger_id,
        "event_name": payload["event_name"].strip().lower(),
        "workflow_id": payload["workflow_id"],
        "workflow_name": workflow.get("name", ""),
        "description": payload.get("description", ""),
        "enabled": bool(payload.get("enabled", True)),
        "updated_at": now,
        "updated_by": actor_id,
    }
    await db.af_event_triggers.update_one(
        {"trigger_id": trigger_id}, {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True
    )
    await log_audit("event_trigger_upserted", actor_id, "event_trigger", trigger_id, {"event_name": doc["event_name"]})
    return await db.af_event_triggers.find_one({"trigger_id": trigger_id}, {"_id": 0})


async def delete_trigger(trigger_id: str, actor_id: str) -> bool:
    from routes.db import db
    from agent_framework.audit import log_audit

    result = await db.af_event_triggers.delete_one({"trigger_id": trigger_id})
    if result.deleted_count:
        await log_audit("event_trigger_deleted", actor_id, "event_trigger", trigger_id)
        return True
    return False


async def emit_event(event_name: str, payload: Dict[str, Any], actor_id: Optional[str]) -> Dict[str, Any]:
    """Fire an event: every enabled trigger starts its workflow with the payload as input."""
    from routes.db import db
    from agent_framework.engine import start_execution
    from agent_framework.policy import check_execution_quota
    from agent_framework.audit import log_audit

    event_name = event_name.strip().lower()
    triggers = await db.af_event_triggers.find(
        {"event_name": event_name, "enabled": True}, {"_id": 0}
    ).to_list(length=50)
    started, errors = [], []
    if triggers:
        await check_execution_quota()
    trigger_input = json.dumps({"event": event_name, "payload": payload}, default=str)[:20000]
    for trigger in triggers:
        workflow = await db.af_workflows.find_one({"workflow_id": trigger["workflow_id"]}, {"_id": 0})
        if not workflow or not workflow.get("enabled", True):
            errors.append({"trigger_id": trigger["trigger_id"], "error": "workflow missing or disabled"})
            continue
        try:
            execution = await start_execution(workflow, trigger_input, actor_id)
            started.append({"trigger_id": trigger["trigger_id"], "execution_id": execution["execution_id"]})
        except Exception as exc:
            errors.append({"trigger_id": trigger["trigger_id"], "error": str(exc)})
    event_doc = {
        "event_id": str(uuid.uuid4()),
        "event_name": event_name,
        "payload": payload,
        "triggers_matched": len(triggers),
        "executions_started": [s["execution_id"] for s in started],
        "errors": errors,
        "emitted_by": actor_id,
        "created_at": _now(),
    }
    await db.af_agent_events.insert_one(dict(event_doc))
    await log_audit("event_emitted", actor_id, "event", event_name,
                    {"triggers_matched": len(triggers), "started": len(started)})
    return event_doc


async def list_events(limit: int = 50) -> List[Dict[str, Any]]:
    from routes.db import db

    limit = min(max(limit, 1), 200)
    return await db.af_agent_events.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
