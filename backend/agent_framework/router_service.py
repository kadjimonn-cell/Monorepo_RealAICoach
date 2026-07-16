"""Intelligent routing: auto-select the best agent or multi-agent team for an
intent + feature context. Reusable shared service for every platform feature."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_framework.marketplace import effective_status, quality_score, agent_stats_map, health_status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> set:
    return {w for w in "".join(c if c.isalnum() else " " for c in (text or "").lower()).split() if len(w) > 2}


def score_agent(agent: Dict[str, Any], intent_words: set, feature_key: str, stats: Optional[Dict[str, Any]]) -> float:
    score = 0.0
    if feature_key and feature_key in (agent.get("feature_mappings") or []):
        score += 50
    text = " ".join([
        agent.get("name", ""), agent.get("role", ""), agent.get("category", ""),
        agent.get("subcategory", ""), agent.get("description", ""), " ".join(agent.get("tags") or []),
    ])
    agent_words = _tokenize(text)
    score += 4 * len(intent_words & agent_words)
    score += quality_score(agent, stats) / 20.0
    if agent.get("status") == "active":
        score += 3
    if health_status(stats) == "degraded":
        score -= 10
    return score


async def route_intent(
    intent: str, feature_key: str = "", team_size: int = 3,
    user_id: Optional[str] = None, log: bool = True,
) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    stats = await agent_stats_map()
    agents = await db.af_agents.find({}, {"_id": 0, "system_prompt": 0}).to_list(length=1000)
    intent_words = _tokenize(intent)
    scored = []
    for agent in agents:
        if effective_status(agent) == "disabled":
            continue
        s = score_agent(agent, intent_words, feature_key, stats.get(agent["agent_key"]))
        if s > 0:
            scored.append((s, agent))
    scored.sort(key=lambda p: (-p[0], p[1]["name"]))

    def brief(a: Dict[str, Any], s: float) -> Dict[str, Any]:
        return {
            "agent_key": a["agent_key"], "name": a["name"], "role": a.get("role", ""),
            "category": a.get("category", ""), "status": effective_status(a), "score": round(s, 2),
        }

    selected = brief(scored[0][1], scored[0][0]) if scored else None
    team: List[Dict[str, Any]] = []
    seen_categories = set()
    for s, a in scored:
        cat = a.get("category") or "Uncategorized"
        if cat in seen_categories:
            continue
        seen_categories.add(cat)
        team.append(brief(a, s))
        if len(team) >= max(1, min(team_size, 8)):
            break

    result = {
        "intent": intent[:500],
        "feature_key": feature_key,
        "selected_agent": selected,
        "team": team,
        "candidates_evaluated": len(scored),
        "routed_at": _now(),
    }
    if log:
        await db.af_routing_log.insert_one({
            "routing_id": str(uuid.uuid4()),
            "intent": intent[:500],
            "feature_key": feature_key,
            "selected_agent_key": (selected or {}).get("agent_key"),
            "team_keys": [t["agent_key"] for t in team],
            "user_id": user_id,
            "created_at": _now(),
        })
    return result


async def routing_log(limit: int = 50) -> List[Dict[str, Any]]:
    from routes.db import db

    limit = min(max(limit, 1), 200)
    return await (
        db.af_routing_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
    )


async def capability_discovery() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded
    from agent_framework.providers import provider_registry
    from agent_framework.tools import tool_registry
    from agent_framework.knowledge import CONNECTOR_TYPES

    await ensure_agents_seeded()
    permissions = await db.af_agents.distinct("permissions")
    categories = await db.af_agents.distinct("category")
    return {
        "step_types": ["agent", "tool", "condition", "parallel", "human_approval", "delegate", "collaborate"],
        "resolution_strategies": ["synthesize", "first_success", "all"],
        "providers": provider_registry.list_names(),
        "tools": [t["name"] for t in tool_registry.list_tools()],
        "permissions": sorted(permissions),
        "categories": sorted(c for c in categories if c),
        "knowledge_connector_types": sorted(CONNECTOR_TYPES),
        "routing": {"endpoint": "/api/agent-framework/route", "signals": ["feature_mapping", "intent_keywords", "quality_score", "health", "status"]},
        "generated_at": _now(),
    }
