"""Centralized configuration and policy enforcement for the agent framework."""

from datetime import datetime, timezone
from typing import Any, Dict

DEFAULT_POLICY: Dict[str, Any] = {
    "config_key": "agent_framework_policy",
    "max_steps_per_workflow": 25,
    "max_parallel_branches": 5,
    "default_step_timeout_seconds": 45,
    "max_step_timeout_seconds": 120,
    "default_step_retries": 1,
    "max_step_retries": 3,
    "max_memory_messages": 20,
    "max_executions_per_hour": 100,
    "enforcement_enabled": True,
}


async def get_policy() -> Dict[str, Any]:
    from routes.db import db

    doc = await db.af_config.find_one({"config_key": "agent_framework_policy"}, {"_id": 0})
    if not doc:
        return dict(DEFAULT_POLICY)
    merged = dict(DEFAULT_POLICY)
    merged.update(doc)
    return merged


async def update_policy(changes: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.audit import log_audit

    allowed = {k: v for k, v in changes.items() if k in DEFAULT_POLICY and k != "config_key"}
    allowed["updated_at"] = datetime.now(timezone.utc).isoformat()
    allowed["updated_by"] = actor_id
    await db.af_config.update_one(
        {"config_key": "agent_framework_policy"}, {"$set": allowed}, upsert=True
    )
    await log_audit("policy_updated", actor_id, "policy", "agent_framework_policy", allowed)
    return await get_policy()


def clamp_timeout(requested: Any, policy: Dict[str, Any]) -> float:
    try:
        value = float(requested)
    except (TypeError, ValueError):
        return float(policy["default_step_timeout_seconds"])
    return max(1.0, min(value, float(policy["max_step_timeout_seconds"])))


def clamp_retries(requested: Any, policy: Dict[str, Any]) -> int:
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return int(policy["default_step_retries"])
    return max(0, min(value, int(policy["max_step_retries"])))


def check_tool_allowed(agent: Dict[str, Any], tool_name: str) -> bool:
    allowed = agent.get("allowed_tools") or []
    return "*" in allowed or tool_name in allowed


async def check_execution_quota() -> None:
    from routes.db import db
    from datetime import timedelta
    from fastapi import HTTPException

    policy = await get_policy()
    if not policy.get("enforcement_enabled", True):
        return
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    count = await db.af_executions.count_documents({"created_at": {"$gte": since}})
    if count >= int(policy["max_executions_per_hour"]):
        raise HTTPException(status_code=429, detail="Agent execution quota exceeded (hourly limit)")
