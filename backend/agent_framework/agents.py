"""Role-based agent registry with versioning and provider-agnostic execution."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_framework.providers import provider_registry
from agent_framework.memory import load_memory, append_memory, render_memory_context
from agent_framework.policy import get_policy, clamp_timeout
from agent_framework.catalog import DEFAULT_AGENTS


MARKETPLACE_FIELDS = (
    "subcategory", "feature_mappings", "permissions", "availability",
    "status", "dependencies", "config_profile",
)

_marketplace_backfill_done = False


async def _backfill_marketplace_fields() -> None:
    """One-time (per process) backfill of marketplace fields for agents created
    before the marketplace schema existed. Only sets fields that are absent."""
    global _marketplace_backfill_done
    if _marketplace_backfill_done:
        return
    from routes.db import db
    from agent_framework.marketplace import GENERIC_MARKETPLACE_DEFAULTS

    for agent in DEFAULT_AGENTS:
        defaults = {k: agent[k] for k in MARKETPLACE_FIELDS}
        await db.af_agents.update_one(
            {"agent_key": agent["agent_key"], "feature_mappings": {"$exists": False}},
            {"$set": defaults},
        )
    # Custom (non-catalog) agents get generic defaults
    await db.af_agents.update_many(
        {"feature_mappings": {"$exists": False}},
        {"$set": dict(GENERIC_MARKETPLACE_DEFAULTS)},
    )
    _marketplace_backfill_done = True


async def ensure_agents_seeded() -> None:
    """Per-key idempotent seeding: new catalog entries auto-appear on existing
    deployments; admin-edited agents are never overwritten ($setOnInsert only)."""
    from routes.db import db

    existing_keys = set(await db.af_agents.distinct("agent_key"))
    missing = [a for a in DEFAULT_AGENTS if a["agent_key"] not in existing_keys]
    now = datetime.now(timezone.utc).isoformat()
    for agent in missing:
        await db.af_agents.update_one(
            {"agent_key": agent["agent_key"]},
            {"$setOnInsert": {**agent, "version": 1, "enabled": True, "created_at": now, "updated_at": now, "is_seed": True}},
            upsert=True,
        )
    await _backfill_marketplace_fields()


async def list_agents() -> List[Dict[str, Any]]:
    from routes.db import db

    await ensure_agents_seeded()
    return await db.af_agents.find({}, {"_id": 0}).sort("name", 1).to_list(length=500)


async def get_agent(agent_key: str) -> Optional[Dict[str, Any]]:
    from routes.db import db

    await ensure_agents_seeded()
    return await db.af_agents.find_one({"agent_key": agent_key}, {"_id": 0})


async def upsert_agent(payload: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.audit import log_audit

    provider_registry.get(payload.get("provider", "openai"))  # validates provider exists
    now = datetime.now(timezone.utc).isoformat()
    agent_key = payload["agent_key"]
    existing = await get_agent(agent_key)
    if existing:
        await db.af_agent_versions.insert_one({
            "version_id": str(uuid.uuid4()), "agent_key": agent_key,
            "snapshot": existing, "archived_at": now, "archived_by": actor_id,
        })
        version = int(existing.get("version", 1)) + 1
    else:
        version = 1
    doc = {
        "agent_key": agent_key,
        "name": payload.get("name", agent_key),
        "role": payload.get("role", ""),
        "category": payload.get("category", ""),
        "description": payload.get("description", ""),
        "system_prompt": payload.get("system_prompt", ""),
        "provider": payload.get("provider", "openai"),
        "model": payload.get("model", "gpt-4o"),
        "allowed_tools": payload.get("allowed_tools", []),
        "tags": payload.get("tags", []),
        "subcategory": payload.get("subcategory", ""),
        "feature_mappings": payload.get("feature_mappings", []),
        "permissions": payload.get("permissions", ["llm.complete"]),
        "availability": payload.get("availability", "global"),
        "status": payload.get("status", "active"),
        "dependencies": payload.get("dependencies", []),
        "config_profile": payload.get("config_profile", {"temperature": 0.4, "max_tokens": 1400}),
        "enabled": bool(payload.get("enabled", True)),
        "version": version,
        "updated_at": now,
        "updated_by": actor_id,
    }
    if not existing:
        doc["created_at"] = now
    await db.af_agents.update_one({"agent_key": agent_key}, {"$set": doc}, upsert=True)
    await log_audit("agent_upserted", actor_id, "agent", agent_key, {"version": version})
    return await get_agent(agent_key)


async def delete_agent(agent_key: str, actor_id: str) -> bool:
    from routes.db import db
    from agent_framework.audit import log_audit

    result = await db.af_agents.delete_one({"agent_key": agent_key})
    if result.deleted_count:
        await log_audit("agent_deleted", actor_id, "agent", agent_key)
        return True
    return False


async def get_agent_versions(agent_key: str, limit: int = 20) -> List[Dict[str, Any]]:
    from routes.db import db

    return await (
        db.af_agent_versions.find({"agent_key": agent_key}, {"_id": 0})
        .sort("archived_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )


async def _record_stats(
    agent_key: str, started_at: datetime, success: bool,
    input_chars: int = 0, output_chars: int = 0, model: str = "",
) -> None:
    from routes.db import db
    from agent_framework.analytics import record_daily_usage

    latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    await db.af_agent_stats.update_one(
        {"agent_key": agent_key},
        {
            "$inc": {"executions": 1, "errors": 0 if success else 1, "total_latency_ms": latency_ms},
            "$set": {"last_executed_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )
    await record_daily_usage(agent_key, latency_ms, success, input_chars, output_chars, model)


async def execute_agent(
    agent: Dict[str, Any],
    user_input: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    extra_context: str = "",
    timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Run a single agent turn through the provider abstraction with memory."""
    from agent_framework.audit import log_audit

    policy = await get_policy()
    session_id = session_id or f"af-{agent['agent_key']}-{uuid.uuid4()}"
    timeout = clamp_timeout(timeout_seconds, policy)

    memory = await load_memory(agent["agent_key"], session_id, int(policy["max_memory_messages"]))
    prompt = render_memory_context(memory) + (extra_context or "") + user_input

    provider = provider_registry.get(agent.get("provider", "openai"))
    t0 = datetime.now(timezone.utc)
    try:
        output = await provider.complete(
            model=agent.get("model", "gpt-4o"),
            system_message=agent.get("system_prompt", ""),
            prompt=prompt,
            session_id=session_id,
            timeout_seconds=timeout,
            feature=f"agent:{agent['agent_key']}",
            user_id=user_id,
        )
    except Exception:
        await _record_stats(agent["agent_key"], t0, success=False,
                            input_chars=len(prompt), model=agent.get("model", ""))
        raise
    await _record_stats(agent["agent_key"], t0, success=True,
                        input_chars=len(prompt), output_chars=len(output or ""), model=agent.get("model", ""))

    max_mem = int(policy["max_memory_messages"])
    await append_memory(agent["agent_key"], session_id, "user", user_input, max_mem)
    await append_memory(agent["agent_key"], session_id, "assistant", output, max_mem)
    await log_audit("agent_executed", user_id, "agent", agent["agent_key"], {"session_id": session_id})

    return {"agent_key": agent["agent_key"], "session_id": session_id, "output": output}
