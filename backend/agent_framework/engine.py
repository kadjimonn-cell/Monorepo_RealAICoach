"""Native workflow engine — sequential, parallel, conditional, human-in-the-loop.

Execution lifecycle: running → completed | failed | rejected | waiting_human (resumable).
Step types: agent | tool | condition | parallel | human_approval.
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_framework.agents import get_agent, execute_agent
from agent_framework.audit import log_audit
from agent_framework.policy import get_policy, clamp_retries, clamp_timeout, check_tool_allowed
from agent_framework.tools import tool_registry

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_path(context: Dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in str(path).split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def interpolate(template: str, context: Dict[str, Any]) -> str:
    def _sub(match):
        value = resolve_path(context, match.group(1).strip())
        return str(value) if value is not None else match.group(0)

    return re.sub(r"\{\{([^{}]+)\}\}", _sub, template or "")


def eval_condition(condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
    field = condition.get("field", "")
    op = condition.get("op", "exists")
    expected = condition.get("value")
    actual = resolve_path(context, field)
    if op == "exists":
        return actual is not None
    if op == "not_exists":
        return actual is None
    if op == "equals":
        return str(actual) == str(expected)
    if op == "not_equals":
        return str(actual) != str(expected)
    if op == "contains":
        return str(expected).lower() in str(actual or "").lower()
    if op == "gt":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    if op == "lt":
        try:
            return float(actual) < float(expected)
        except (TypeError, ValueError):
            return False
    raise ValueError(f"Unknown condition operator '{op}'")


def count_steps(steps: List[Dict[str, Any]]) -> int:
    total = 0
    for step in steps or []:
        total += 1
        step_type = step.get("type")
        if step_type == "parallel":
            for branch in step.get("branches", []):
                total += count_steps(branch)
        elif step_type == "condition":
            total += count_steps(step.get("then_steps", []))
            total += count_steps(step.get("else_steps", []))
    return total


def validate_workflow_steps(steps: List[Dict[str, Any]], top_level: bool = True) -> None:
    valid_types = {"agent", "tool", "condition", "parallel", "human_approval", "delegate", "collaborate"}
    for step in steps or []:
        step_type = step.get("type")
        if step_type not in valid_types:
            raise ValueError(f"Invalid step type '{step_type}'")
        if not step.get("step_id"):
            raise ValueError("Every step requires a step_id")
        if step_type == "human_approval" and not top_level:
            raise ValueError("human_approval steps are only allowed at the top level of a workflow")
        if step_type == "tool" and not step.get("tool_name"):
            raise ValueError(f"Step '{step.get('step_id')}' of type 'tool' requires a non-empty tool_name")
        if step_type == "agent" and not step.get("agent_key"):
            raise ValueError(f"Step '{step.get('step_id')}' of type 'agent' requires a non-empty agent_key")
        if step_type == "collaborate" and not step.get("agent_keys"):
            raise ValueError(f"Step '{step.get('step_id')}' of type 'collaborate' requires a non-empty agent_keys list")
        if step_type == "parallel":
            for branch in step.get("branches", []):
                validate_workflow_steps(branch, top_level=False)
        if step_type == "condition":
            validate_workflow_steps(step.get("then_steps", []), top_level=False)
            validate_workflow_steps(step.get("else_steps", []), top_level=False)


async def _execute_single_step(
    step: Dict[str, Any], context: Dict[str, Any], policy: Dict[str, Any], user_id: Optional[str]
) -> Dict[str, Any]:
    step_type = step.get("type")
    timeout = clamp_timeout(step.get("timeout_seconds"), policy)
    retries = clamp_retries(step.get("retries"), policy)

    last_error: Optional[str] = None
    for attempt in range(retries + 1):
        try:
            if step_type == "agent":
                agent = await get_agent(step.get("agent_key", ""))
                if not agent:
                    raise ValueError(f"Agent '{step.get('agent_key')}' not found")
                if not agent.get("enabled", True):
                    raise ValueError(f"Agent '{agent['agent_key']}' is disabled")
                user_input = interpolate(step.get("input_template", "{{input}}"), context)
                result = await execute_agent(
                    agent, user_input, session_id=step.get("session_id"),
                    user_id=user_id, timeout_seconds=timeout,
                )
                return {"status": "ok", "output": result["output"], "attempts": attempt + 1}

            if step_type == "tool":
                tool_name = step.get("tool_name", "")
                agent_key = step.get("agent_key")
                if agent_key:
                    agent = await get_agent(agent_key)
                    if agent and not check_tool_allowed(agent, tool_name):
                        raise PermissionError(f"Tool '{tool_name}' not allowed for agent '{agent_key}'")
                args = {
                    k: (interpolate(v, context) if isinstance(v, str) else v)
                    for k, v in (step.get("args") or {}).items()
                }
                output = await asyncio.wait_for(
                    tool_registry.execute(tool_name, args, context), timeout=timeout
                )
                return {"status": "ok", "output": output, "attempts": attempt + 1}

            if step_type == "condition":
                branch_taken = eval_condition(step.get("condition") or {}, context)
                branch_steps = step.get("then_steps" if branch_taken else "else_steps", [])
                await _run_inline_steps(branch_steps, context, policy, user_id)
                return {"status": "ok", "output": {"branch": "then" if branch_taken else "else"}, "attempts": attempt + 1}

            if step_type == "parallel":
                branches = step.get("branches", [])[: int(policy["max_parallel_branches"])]
                results = await asyncio.gather(
                    *[_run_inline_steps(branch, context, policy, user_id) for branch in branches],
                    return_exceptions=True,
                )
                errors = [str(r) for r in results if isinstance(r, Exception)]
                if errors:
                    raise RuntimeError(f"Parallel branch failure(s): {'; '.join(errors)}")
                return {"status": "ok", "output": {"branches_completed": len(branches)}, "attempts": attempt + 1}

            if step_type == "delegate":
                from agent_framework.orchestration_v2 import execute_delegate

                output = await execute_delegate(step, context, policy, user_id, timeout)
                return {"status": "ok", "output": output, "attempts": attempt + 1}

            if step_type == "collaborate":
                from agent_framework.orchestration_v2 import execute_collaborate

                output = await execute_collaborate(step, context, policy, user_id, timeout)
                return {"status": "ok", "output": output, "attempts": attempt + 1}

            raise ValueError(f"Unsupported step type '{step_type}'")

        except Exception as exc:
            last_error = str(exc)
            logger.warning("Step '%s' attempt %s failed: %s", step.get("step_id"), attempt + 1, exc)

    return {"status": "error", "error": last_error, "attempts": retries + 1}


async def _run_inline_steps(
    steps: List[Dict[str, Any]], context: Dict[str, Any], policy: Dict[str, Any], user_id: Optional[str]
) -> None:
    """Run nested steps (branch bodies) sequentially, recording results into shared context."""
    for step in steps:
        result = await _execute_single_step(step, context, policy, user_id)
        context["steps"][step["step_id"]] = result
        if result["status"] == "error" and not step.get("continue_on_error"):
            raise RuntimeError(f"Step '{step['step_id']}' failed: {result.get('error')}")


async def _persist_execution(execution_id: str, updates: Dict[str, Any]) -> None:
    from routes.db import db

    updates["updated_at"] = _now()
    await db.af_executions.update_one({"execution_id": execution_id}, {"$set": updates})


async def run_workflow_steps(execution_id: str, start_index: int = 0) -> None:
    """Core sequential runner. Pauses at human_approval; resumable via resume_execution."""
    from routes.db import db

    execution = await db.af_executions.find_one({"execution_id": execution_id}, {"_id": 0})
    if not execution:
        return
    policy = await get_policy()
    steps: List[Dict[str, Any]] = execution["steps"]
    context: Dict[str, Any] = execution.get("context") or {"input": execution.get("trigger_input", ""), "steps": {}}
    user_id = execution.get("started_by")

    try:
        for index in range(start_index, len(steps)):
            step = steps[index]
            if step.get("type") == "human_approval":
                await _persist_execution(execution_id, {
                    "status": "waiting_human",
                    "paused_at_index": index,
                    "context": context,
                    "pending_approval": {
                        "step_id": step["step_id"],
                        "prompt": interpolate(step.get("prompt", "Approval required to continue."), context),
                    },
                })
                await log_audit("execution_paused_for_approval", user_id, "execution", execution_id,
                                {"step_id": step["step_id"]})
                return

            result = await _execute_single_step(step, context, policy, user_id)
            context["steps"][step["step_id"]] = result
            await _persist_execution(execution_id, {"context": context, "current_index": index})

            if result["status"] == "error" and not step.get("continue_on_error"):
                await _persist_execution(execution_id, {
                    "status": "failed", "error": result.get("error"),
                    "finished_at": _now(), "context": context,
                })
                await log_audit("execution_failed", user_id, "execution", execution_id,
                                {"step_id": step["step_id"], "error": result.get("error")})
                return

        await _persist_execution(execution_id, {"status": "completed", "finished_at": _now(), "context": context})
        await log_audit("execution_completed", user_id, "execution", execution_id)
    except Exception as exc:
        logger.exception("Workflow execution %s crashed", execution_id)
        await _persist_execution(execution_id, {"status": "failed", "error": str(exc), "finished_at": _now()})


async def start_execution(workflow: Dict[str, Any], trigger_input: str, user_id: Optional[str]) -> Dict[str, Any]:
    from routes.db import db

    policy = await get_policy()
    steps = workflow.get("steps", [])
    if count_steps(steps) > int(policy["max_steps_per_workflow"]):
        raise ValueError(f"Workflow exceeds max steps policy ({policy['max_steps_per_workflow']})")
    validate_workflow_steps(steps)

    execution_id = str(uuid.uuid4())
    doc = {
        "execution_id": execution_id,
        "workflow_id": workflow["workflow_id"],
        "workflow_name": workflow.get("name", ""),
        "workflow_version": workflow.get("version", 1),
        "steps": steps,
        "trigger_input": trigger_input,
        "context": {"input": trigger_input, "steps": {}},
        "status": "running",
        "started_by": user_id,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.af_executions.insert_one(doc)
    await log_audit("execution_started", user_id, "execution", execution_id, {"workflow_id": workflow["workflow_id"]})

    asyncio.create_task(run_workflow_steps(execution_id, 0))
    return {"execution_id": execution_id, "status": "running"}


async def resume_execution(execution_id: str, approved: bool, admin_id: str, note: str = "") -> Dict[str, Any]:
    from routes.db import db
    from fastapi import HTTPException

    execution = await db.af_executions.find_one({"execution_id": execution_id}, {"_id": 0})
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.get("status") != "waiting_human":
        raise HTTPException(status_code=409, detail=f"Execution is not awaiting approval (status={execution.get('status')})")

    paused_index = int(execution.get("paused_at_index", 0))
    step = execution["steps"][paused_index]
    context = execution.get("context") or {"input": execution.get("trigger_input", ""), "steps": {}}
    decision = "approved" if approved else "rejected"
    context["steps"][step["step_id"]] = {
        "status": "ok" if approved else "rejected",
        "output": {"decision": decision, "by": admin_id, "note": note},
    }
    await log_audit(f"execution_{decision}", admin_id, "execution", execution_id, {"step_id": step["step_id"], "note": note})

    if not approved:
        await _persist_execution(execution_id, {
            "status": "rejected", "context": context, "finished_at": _now(), "pending_approval": None,
        })
        return {"execution_id": execution_id, "status": "rejected"}

    await _persist_execution(execution_id, {"status": "running", "context": context, "pending_approval": None})
    asyncio.create_task(run_workflow_steps(execution_id, paused_index + 1))
    return {"execution_id": execution_id, "status": "running"}
