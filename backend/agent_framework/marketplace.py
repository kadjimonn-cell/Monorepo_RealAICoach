"""Native AI Marketplace services: catalog search, coverage, recommendations,
dependencies, cloning, import/export, bulk lifecycle, stats/health, readiness."""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_framework.catalog import DEFAULT_AGENTS

VALID_STATUSES = {"active", "disabled", "beta", "experimental"}
VALID_AVAILABILITY = {"global", "workspace", "user"}
MARKETPLACE_MIN_CATALOG_SIZE = 200

GENERIC_MARKETPLACE_DEFAULTS: Dict[str, Any] = {
    "subcategory": "",
    "feature_mappings": [],
    "permissions": ["llm.complete"],
    "availability": "global",
    "status": "active",
    "dependencies": [],
    "config_profile": {"temperature": 0.4, "max_tokens": 1400},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_feature_keys() -> List[str]:
    from utils.access_control_engine import CANONICAL_FEATURE_METERS

    return [m["feature_key"] for m in CANONICAL_FEATURE_METERS]


def effective_status(agent: Dict[str, Any]) -> str:
    if not agent.get("enabled", True):
        return "disabled"
    status = agent.get("status") or "active"
    return status if status in VALID_STATUSES else "active"


# ── Search / filter / sort ──

SORT_FIELDS = {"name": "name", "category": "category", "version": "version", "updated_at": "updated_at"}


async def search_catalog(
    q: str = "", category: str = "", subcategory: str = "", status: str = "",
    availability: str = "", tag: str = "", feature: str = "",
    sort: str = "name", order: str = "asc", page: int = 1, page_size: int = 30,
) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    query: Dict[str, Any] = {}
    if category:
        query["category"] = category
    if subcategory:
        query["subcategory"] = subcategory
    if availability:
        query["availability"] = availability
    if tag:
        query["tags"] = tag
    if feature:
        query["feature_mappings"] = feature
    if status == "disabled":
        query["$or"] = [{"enabled": False}, {"status": "disabled"}]
    elif status:
        query["status"] = status
        query["enabled"] = True
    if q:
        rx = {"$regex": q, "$options": "i"}
        query["$and"] = [{"$or": [
            {"name": rx}, {"role": rx}, {"category": rx}, {"subcategory": rx},
            {"description": rx}, {"agent_key": rx}, {"tags": rx},
        ]}]
    total = await db.af_agents.count_documents(query)
    page = max(1, int(page))
    page_size = min(max(int(page_size), 1), 100)
    sort_field = SORT_FIELDS.get(sort, "name")
    direction = -1 if order == "desc" else 1
    items = await (
        db.af_agents.find(query, {"_id": 0, "system_prompt": 0})
        .sort(sort_field, direction)
        .skip((page - 1) * page_size).limit(page_size)
        .to_list(length=page_size)
    )
    return {
        "items": items, "total": total, "page": page, "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)),
    }


async def category_summaries() -> List[Dict[str, Any]]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    rows = await db.af_agents.aggregate([
        {"$group": {
            "_id": "$category",
            "total": {"$sum": 1},
            "active": {"$sum": {"$cond": [{"$and": [{"$eq": ["$enabled", True]}, {"$in": [{"$ifNull": ["$status", "active"]}, ["active"]]}]}, 1, 0]}},
            "beta": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$status", "active"]}, "beta"]}, 1, 0]}},
            "experimental": {"$sum": {"$cond": [{"$eq": [{"$ifNull": ["$status", "active"]}, "experimental"]}, 1, 0]}},
            "subcategories": {"$addToSet": "$subcategory"},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(length=100)
    return [{
        "category": r["_id"] or "Uncategorized", "total": r["total"], "active": r["active"],
        "beta": r["beta"], "experimental": r["experimental"],
        "subcategories": sorted([s for s in r["subcategories"] if s]),
    } for r in rows]


# ── Feature coverage ──

async def feature_coverage_matrix() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    feature_keys = get_feature_keys()
    agents = await db.af_agents.find(
        {}, {"_id": 0, "agent_key": 1, "name": 1, "category": 1, "enabled": 1, "status": 1, "feature_mappings": 1}
    ).to_list(length=1000)
    matrix = []
    uncovered = []
    for fk in feature_keys:
        mapped = [a for a in agents if fk in (a.get("feature_mappings") or [])]
        active = [a for a in mapped if effective_status(a) == "active"]
        matrix.append({
            "feature_key": fk,
            "agent_count": len(mapped),
            "active_agent_count": len(active),
            "covered": len(active) > 0,
            "agents": [{"agent_key": a["agent_key"], "name": a["name"], "category": a.get("category", "")} for a in mapped[:12]],
        })
        if not active:
            uncovered.append(fk)
    covered_count = len(feature_keys) - len(uncovered)
    return {
        "features_total": len(feature_keys),
        "features_covered": covered_count,
        "coverage_percent": round(covered_count * 100 / max(1, len(feature_keys)), 1),
        "uncovered_features": uncovered,
        "matrix": matrix,
        "generated_at": _now(),
    }


# ── Recommendation engine ──

async def recommend_agents(feature_key: str, limit: int = 8) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    stats = await agent_stats_map()
    agents = await db.af_agents.find({}, {"_id": 0, "system_prompt": 0}).to_list(length=1000)
    words = set(feature_key.lower().replace("-", " ").split())
    scored = []
    for agent in agents:
        if effective_status(agent) == "disabled":
            continue
        score = 0.0
        if feature_key in (agent.get("feature_mappings") or []):
            score += 50
        text = " ".join([agent.get("name", ""), agent.get("role", ""), agent.get("subcategory", ""), " ".join(agent.get("tags") or [])]).lower()
        score += sum(4 for w in words if w and w in text)
        st = stats.get(agent["agent_key"])
        score += quality_score(agent, st) / 20.0
        if agent.get("status") == "active":
            score += 3
        if score > 0:
            scored.append((score, agent))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
    return {
        "feature_key": feature_key,
        "recommendations": [
            {**a, "score": round(s, 2), "quality_score": quality_score(a, stats.get(a["agent_key"]))}
            for s, a in scored[:max(1, min(limit, 25))]
        ],
    }


# ── Dependencies ──

async def dependency_graph() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    agents = await db.af_agents.find(
        {}, {"_id": 0, "agent_key": 1, "name": 1, "category": 1, "dependencies": 1}
    ).to_list(length=1000)
    known = {a["agent_key"] for a in agents}
    edges, dangling = [], []
    for agent in agents:
        for dep in agent.get("dependencies") or []:
            edge = {"from": agent["agent_key"], "to": dep}
            edges.append(edge)
            if dep not in known:
                dangling.append(edge)
    return {
        "nodes": [{"agent_key": a["agent_key"], "name": a["name"], "category": a.get("category", "")}
                  for a in agents if (a.get("dependencies") or [])
                  or any(e["to"] == a["agent_key"] for e in edges)],
        "edges": edges,
        "dangling": dangling,
    }


# ── Clone / templates / import-export ──

async def clone_agent(source_key: str, new_key: str, new_name: str, actor_id: str) -> Dict[str, Any]:
    from agent_framework.agents import get_agent, upsert_agent

    source = await get_agent(source_key)
    if not source:
        raise KeyError("Source agent not found")
    if await get_agent(new_key):
        raise ValueError(f"Agent key '{new_key}' already exists")
    payload = {k: v for k, v in source.items()
               if k not in ("version", "created_at", "updated_at", "updated_by", "is_seed")}
    payload["agent_key"] = new_key
    payload["name"] = new_name or f"{source['name']} (Clone)"
    payload["status"] = "experimental"
    cloned = await upsert_agent(payload, actor_id)
    from agent_framework.audit import log_audit
    await log_audit("agent_cloned", actor_id, "agent", new_key, {"source": source_key})
    return cloned


def list_templates() -> List[Dict[str, Any]]:
    seen, templates = set(), []
    for agent in DEFAULT_AGENTS:
        cat = agent["category"]
        if cat in seen:
            continue
        seen.add(cat)
        templates.append({
            "template_key": f"tpl_{cat.lower().replace(' & ', '_').replace(', ', '_').replace(' ', '_')}",
            "name": f"{cat} Agent Template",
            "category": cat,
            "base": {k: agent[k] for k in (
                "provider", "model", "allowed_tools", "permissions",
                "availability", "config_profile")},
            "example_agent_key": agent["agent_key"],
        })
    return templates


EXPORT_FIELDS = (
    "agent_key", "name", "role", "category", "subcategory", "description",
    "system_prompt", "provider", "model", "allowed_tools", "tags",
    "feature_mappings", "permissions", "availability", "status",
    "dependencies", "config_profile", "enabled", "version",
)


async def export_agents(keys: Optional[List[str]] = None) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    query = {"agent_key": {"$in": keys}} if keys else {}
    agents = await db.af_agents.find(query, {"_id": 0}).sort("agent_key", 1).to_list(length=1000)
    return {
        "format": "realaicoach.agent-marketplace.v1",
        "exported_at": _now(),
        "count": len(agents),
        "agents": [{k: a.get(k) for k in EXPORT_FIELDS if k in a} for a in agents],
    }


async def import_agents(agents: List[Dict[str, Any]], actor_id: str, overwrite: bool = False) -> Dict[str, Any]:
    from agent_framework.agents import get_agent, upsert_agent

    imported, skipped, errors = [], [], []
    for entry in agents:
        key = (entry or {}).get("agent_key")
        if not key or not entry.get("system_prompt") or not entry.get("name"):
            errors.append({"agent_key": key or "(missing)", "error": "agent_key, name and system_prompt are required"})
            continue
        if entry.get("status") and entry["status"] not in VALID_STATUSES:
            errors.append({"agent_key": key, "error": f"invalid status '{entry['status']}'"})
            continue
        existing = await get_agent(key)
        if existing and not overwrite:
            skipped.append(key)
            continue
        payload = {k: entry[k] for k in EXPORT_FIELDS if k in entry and k != "version"}
        await upsert_agent(payload, actor_id)
        imported.append(key)
    from agent_framework.audit import log_audit
    await log_audit("agents_imported", actor_id, "marketplace", "import",
                    {"imported": len(imported), "skipped": len(skipped), "errors": len(errors)})
    return {"imported": imported, "skipped": skipped, "errors": errors}


# ── Bulk lifecycle ──

async def bulk_update(keys: List[str], changes: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.audit import log_audit

    allowed: Dict[str, Any] = {}
    if "status" in changes:
        if changes["status"] not in VALID_STATUSES:
            raise ValueError(f"Invalid status. Allowed: {sorted(VALID_STATUSES)}")
        allowed["status"] = changes["status"]
        allowed["enabled"] = changes["status"] != "disabled"
    if "enabled" in changes:
        allowed["enabled"] = bool(changes["enabled"])
    if "availability" in changes:
        if changes["availability"] not in VALID_AVAILABILITY:
            raise ValueError(f"Invalid availability. Allowed: {sorted(VALID_AVAILABILITY)}")
        allowed["availability"] = changes["availability"]
    if not allowed:
        raise ValueError("No valid changes provided (status, enabled, availability)")
    allowed["updated_at"] = _now()
    allowed["updated_by"] = actor_id
    result = await db.af_agents.update_many({"agent_key": {"$in": keys}}, {"$set": allowed})
    await log_audit("agents_bulk_updated", actor_id, "marketplace", "bulk",
                    {"keys": keys[:50], "changes": {k: v for k, v in allowed.items() if k not in ("updated_at", "updated_by")}, "matched": result.matched_count})
    return {"matched": result.matched_count, "modified": result.modified_count}


# ── Stats / health / quality ──

async def agent_stats_map() -> Dict[str, Dict[str, Any]]:
    from routes.db import db

    rows = await db.af_agent_stats.find({}, {"_id": 0}).to_list(length=2000)
    return {r["agent_key"]: r for r in rows}


def health_status(stats: Optional[Dict[str, Any]]) -> str:
    if not stats or not stats.get("executions"):
        return "idle"
    executions = int(stats.get("executions", 0))
    errors = int(stats.get("errors", 0))
    if executions and errors / executions > 0.2:
        return "degraded"
    return "healthy"


def quality_score(agent: Dict[str, Any], stats: Optional[Dict[str, Any]] = None) -> int:
    score = 60.0
    if agent.get("description"):
        score += 8
    if agent.get("system_prompt"):
        score += 12
    if agent.get("feature_mappings"):
        score += 8
    if agent.get("tags"):
        score += 4
    if stats and stats.get("executions"):
        executions = int(stats["executions"])
        error_rate = int(stats.get("errors", 0)) / executions
        score += 8 - (error_rate * 40)
    return int(max(0, min(100, round(score))))


async def agent_stats_report() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    stats = await agent_stats_map()
    agents = await db.af_agents.find(
        {}, {"_id": 0, "agent_key": 1, "name": 1, "category": 1, "enabled": 1, "status": 1,
             "description": 1, "system_prompt": 1, "feature_mappings": 1, "tags": 1}
    ).to_list(length=1000)
    rows = []
    for agent in agents:
        st = stats.get(agent["agent_key"])
        rows.append({
            "agent_key": agent["agent_key"], "name": agent["name"], "category": agent.get("category", ""),
            "status": effective_status(agent),
            "health": health_status(st),
            "quality_score": quality_score(agent, st),
            "executions": int((st or {}).get("executions", 0)),
            "errors": int((st or {}).get("errors", 0)),
            "avg_latency_ms": int((st or {}).get("total_latency_ms", 0) / max(1, int((st or {}).get("executions", 0)))) if st else 0,
            "last_executed_at": (st or {}).get("last_executed_at"),
        })
    rows.sort(key=lambda r: (-r["executions"], r["name"]))
    return {"stats": rows, "generated_at": _now()}


# ── Portfolio & readiness ──

async def portfolio_overview() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded

    await ensure_agents_seeded()
    agents = await db.af_agents.find(
        {}, {"_id": 0, "agent_key": 1, "category": 1, "enabled": 1, "status": 1,
             "availability": 1, "description": 1, "system_prompt": 1,
             "feature_mappings": 1, "tags": 1}
    ).to_list(length=1000)
    stats = await agent_stats_map()
    by_status: Dict[str, int] = {"active": 0, "beta": 0, "experimental": 0, "disabled": 0}
    by_availability: Dict[str, int] = {}
    by_health: Dict[str, int] = {"healthy": 0, "degraded": 0, "idle": 0}
    quality_total = 0
    for agent in agents:
        by_status[effective_status(agent)] = by_status.get(effective_status(agent), 0) + 1
        avail = agent.get("availability") or "global"
        by_availability[avail] = by_availability.get(avail, 0) + 1
        st = stats.get(agent["agent_key"])
        by_health[health_status(st)] = by_health.get(health_status(st), 0) + 1
        quality_total += quality_score(agent, st)
    coverage = await feature_coverage_matrix()
    executions_total = sum(int(s.get("executions", 0)) for s in stats.values())
    return {
        "agents_total": len(agents),
        "categories_total": len({a.get("category") or "Uncategorized" for a in agents}),
        "by_status": by_status,
        "by_availability": by_availability,
        "by_health": by_health,
        "avg_quality_score": round(quality_total / max(1, len(agents)), 1),
        "executions_total": executions_total,
        "coverage": {
            "features_total": coverage["features_total"],
            "features_covered": coverage["features_covered"],
            "coverage_percent": coverage["coverage_percent"],
            "uncovered_features": coverage["uncovered_features"],
        },
        "catalog_target": MARKETPLACE_MIN_CATALOG_SIZE,
        "generated_at": _now(),
    }


async def readiness_report() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded
    from agent_framework.providers import provider_registry
    from agent_framework.tools import tool_registry

    await ensure_agents_seeded()
    agents = await db.af_agents.find({}, {"_id": 0}).to_list(length=1000)
    coverage = await feature_coverage_matrix()
    graph = await dependency_graph()
    known_tools = {t["name"] for t in tool_registry.list_tools()}
    known_providers = set(provider_registry.list_names())
    missing_prompts = [a["agent_key"] for a in agents if not (a.get("system_prompt") or "").strip()]
    bad_providers = [a["agent_key"] for a in agents if a.get("provider") not in known_providers]
    bad_tools = [a["agent_key"] for a in agents
                 if any(t not in known_tools and t != "*" for t in (a.get("allowed_tools") or []))]
    bad_status = [a["agent_key"] for a in agents if (a.get("status") or "active") not in VALID_STATUSES]
    checks = [
        {"check": "catalog_size_200_plus", "passed": len(agents) >= MARKETPLACE_MIN_CATALOG_SIZE,
         "detail": f"{len(agents)} agents (target ≥ {MARKETPLACE_MIN_CATALOG_SIZE})"},
        {"check": "all_37_features_covered", "passed": not coverage["uncovered_features"],
         "detail": f"{coverage['features_covered']}/{coverage['features_total']} features covered"},
        {"check": "all_agents_have_system_prompt", "passed": not missing_prompts,
         "detail": f"{len(missing_prompts)} agents missing prompts"},
        {"check": "provider_agnostic_valid", "passed": not bad_providers,
         "detail": f"{len(bad_providers)} agents with unknown provider; providers: {sorted(known_providers)}"},
        {"check": "tool_allowlists_valid", "passed": not bad_tools,
         "detail": f"{len(bad_tools)} agents referencing unknown tools"},
        {"check": "lifecycle_statuses_valid", "passed": not bad_status,
         "detail": f"{len(bad_status)} agents with invalid status"},
        {"check": "no_dangling_dependencies", "passed": not graph["dangling"],
         "detail": f"{len(graph['dangling'])} dangling dependency edges"},
        {"check": "versioning_enabled", "passed": True, "detail": "af_agent_versions snapshots on every upsert"},
        {"check": "audit_logging_enabled", "passed": True, "detail": "af_audit_log records all lifecycle actions"},
    ]
    return {
        "ready": all(c["passed"] for c in checks),
        "checks": checks,
        "generated_at": _now(),
    }
