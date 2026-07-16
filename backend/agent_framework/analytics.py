"""Agent Performance Analytics v2: cost tracking, daily trends, satisfaction,
feature adoption, execution history, optimization recommendations, health alerts."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

MODEL_RATES = {  # USD per 1K tokens (input, output)
    "gpt-4o-mini": (0.0006, 0.0024),
    "gpt-4o": (0.005, 0.015),
    "claude": (0.003, 0.015),
    "gemini": (0.001, 0.004),
}
DEFAULT_RATE = (0.002, 0.008)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    rate = DEFAULT_RATE
    model_lower = (model or "").lower()
    for prefix in sorted(MODEL_RATES, key=len, reverse=True):
        if model_lower.startswith(prefix):
            rate = MODEL_RATES[prefix]
            break
    return round((in_tokens / 1000) * rate[0] + (out_tokens / 1000) * rate[1], 6)


async def record_daily_usage(
    agent_key: str, latency_ms: int, success: bool,
    input_chars: int = 0, output_chars: int = 0, model: str = "",
) -> None:
    from routes.db import db

    in_tokens = input_chars // 4
    out_tokens = output_chars // 4
    cost = estimate_cost(model, in_tokens, out_tokens)
    await db.af_agent_daily_stats.update_one(
        {"agent_key": agent_key, "date": _today()},
        {
            "$inc": {
                "executions": 1, "errors": 0 if success else 1,
                "total_latency_ms": latency_ms,
                "est_input_tokens": in_tokens, "est_output_tokens": out_tokens,
                "est_cost_usd": cost,
            },
            "$set": {"updated_at": _now()},
        },
        upsert=True,
    )


# ── Satisfaction ──

async def record_feedback(agent_key: str, rating: int, comment: str, actor_id: str) -> Dict[str, Any]:
    from routes.db import db

    doc = {
        "feedback_id": str(uuid.uuid4()),
        "agent_key": agent_key,
        "rating": max(1, min(int(rating), 5)),
        "comment": (comment or "")[:1000],
        "actor_id": actor_id,
        "created_at": _now(),
    }
    await db.af_agent_feedback.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def satisfaction_map() -> Dict[str, Dict[str, Any]]:
    from routes.db import db

    rows = await db.af_agent_feedback.aggregate([
        {"$group": {"_id": "$agent_key", "avg_rating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]).to_list(length=1000)
    return {r["_id"]: {"avg_rating": round(r["avg_rating"], 2), "count": r["count"]} for r in rows}


# ── Overview / trends / history ──

async def analytics_overview() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.marketplace import agent_stats_map

    stats = await agent_stats_map()
    executions = sum(int(s.get("executions", 0)) for s in stats.values())
    errors = sum(int(s.get("errors", 0)) for s in stats.values())
    latency_total = sum(int(s.get("total_latency_ms", 0)) for s in stats.values())
    cost_rows = await db.af_agent_daily_stats.aggregate([
        {"$group": {"_id": None, "cost": {"$sum": "$est_cost_usd"},
                    "in_tokens": {"$sum": "$est_input_tokens"}, "out_tokens": {"$sum": "$est_output_tokens"}}}
    ]).to_list(length=1)
    cost = cost_rows[0] if cost_rows else {}
    satisfaction = await satisfaction_map()
    ratings = [v["avg_rating"] for v in satisfaction.values()]
    top = sorted(stats.items(), key=lambda kv: -int(kv[1].get("executions", 0)))[:8]
    return {
        "executions_total": executions,
        "errors_total": errors,
        "success_rate_percent": round((1 - errors / max(1, executions)) * 100, 1),
        "avg_latency_ms": int(latency_total / max(1, executions)),
        "est_cost_usd_total": round(float(cost.get("cost") or 0), 4),
        "est_tokens_total": int((cost.get("in_tokens") or 0) + (cost.get("out_tokens") or 0)),
        "avg_satisfaction": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "feedback_count": sum(v["count"] for v in satisfaction.values()),
        "top_agents": [{"agent_key": k, "executions": int(v.get("executions", 0))} for k, v in top],
        "generated_at": _now(),
    }


async def trend_report(days: int = 30) -> Dict[str, Any]:
    from routes.db import db

    days = min(max(days, 1), 90)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = await db.af_agent_daily_stats.aggregate([
        {"$match": {"date": {"$gte": since}}},
        {"$group": {
            "_id": "$date",
            "executions": {"$sum": "$executions"},
            "errors": {"$sum": "$errors"},
            "total_latency_ms": {"$sum": "$total_latency_ms"},
            "est_cost_usd": {"$sum": "$est_cost_usd"},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(length=100)
    return {
        "days": days,
        "series": [{
            "date": r["_id"],
            "executions": r["executions"],
            "errors": r["errors"],
            "avg_latency_ms": int(r["total_latency_ms"] / max(1, r["executions"])),
            "est_cost_usd": round(r["est_cost_usd"], 4),
        } for r in rows],
        "generated_at": _now(),
    }


async def agent_history(agent_key: str, limit: int = 30) -> Dict[str, Any]:
    from routes.db import db

    limit = min(max(limit, 1), 100)
    events = await (
        db.af_audit_log.find({"entity_type": "agent", "entity_id": agent_key}, {"_id": 0})
        .sort("created_at", -1).limit(limit).to_list(length=limit)
    )
    daily = await (
        db.af_agent_daily_stats.find({"agent_key": agent_key}, {"_id": 0})
        .sort("date", -1).limit(30).to_list(length=30)
    )
    stats = await db.af_agent_stats.find_one({"agent_key": agent_key}, {"_id": 0})
    return {"agent_key": agent_key, "stats": stats, "daily": daily, "events": events}


# ── Feature adoption ──

async def feature_adoption() -> Dict[str, Any]:
    from routes.db import db

    routing = await db.af_routing_log.aggregate([
        {"$match": {"feature_key": {"$ne": ""}}},
        {"$group": {"_id": "$feature_key", "routes": {"$sum": 1}}},
        {"$sort": {"routes": -1}}, {"$limit": 40},
    ]).to_list(length=40)
    strip = await db.specialist_strip_events.aggregate([
        {"$group": {"_id": "$feature_key", "clicks": {"$sum": 1}}},
        {"$sort": {"clicks": -1}}, {"$limit": 40},
    ]).to_list(length=40)
    strip_map = {r["_id"]: r["clicks"] for r in strip}
    features = {r["_id"]: {"feature_key": r["_id"], "routes": r["routes"], "strip_clicks": strip_map.get(r["_id"], 0)} for r in routing}
    for key, clicks in strip_map.items():
        if key not in features:
            features[key] = {"feature_key": key, "routes": 0, "strip_clicks": clicks}
    rows = sorted(features.values(), key=lambda r: -(r["routes"] + r["strip_clicks"]))
    return {"features": rows, "generated_at": _now()}


# ── Optimization recommendations ──

async def optimization_recommendations() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.agents import ensure_agents_seeded
    from agent_framework.marketplace import agent_stats_map, effective_status

    await ensure_agents_seeded()
    stats = await agent_stats_map()
    agents = await db.af_agents.find(
        {}, {"_id": 0, "agent_key": 1, "name": 1, "enabled": 1, "status": 1,
             "feature_mappings": 1, "description": 1, "model": 1}
    ).to_list(length=1000)
    recs: List[Dict[str, Any]] = []
    for agent in agents:
        key = agent["agent_key"]
        st = stats.get(key) or {}
        executions = int(st.get("executions", 0))
        errors = int(st.get("errors", 0))
        if executions >= 5 and errors / executions > 0.2:
            recs.append({"agent_key": key, "name": agent["name"], "severity": "high",
                         "type": "high_error_rate",
                         "recommendation": f"Error rate {round(errors * 100 / executions)}% — review system prompt, increase retries, or check provider health."})
        if executions and int(st.get("total_latency_ms", 0)) / executions > 20000:
            recs.append({"agent_key": key, "name": agent["name"], "severity": "medium",
                         "type": "high_latency",
                         "recommendation": "Average latency exceeds 20s — consider a faster model or lower max_tokens."})
        if effective_status(agent) == "active" and not (agent.get("feature_mappings") or []):
            recs.append({"agent_key": key, "name": agent["name"], "severity": "low",
                         "type": "unmapped_agent",
                         "recommendation": "Active agent has no feature mappings — map it to features so routing and recommendations can surface it."})
        if not (agent.get("description") or "").strip():
            recs.append({"agent_key": key, "name": agent["name"], "severity": "low",
                         "type": "missing_description",
                         "recommendation": "Add a description to improve intent-routing keyword matching quality."})
    severity_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: (severity_order[r["severity"]], r["agent_key"]))
    return {"recommendations": recs[:100], "total": len(recs), "generated_at": _now()}


# ── Health alerts ──

async def health_alerts() -> Dict[str, Any]:
    from routes.db import db
    from agent_framework.marketplace import agent_stats_map

    stats = await agent_stats_map()
    alerts: List[Dict[str, Any]] = []
    for key, st in stats.items():
        executions = int(st.get("executions", 0))
        errors = int(st.get("errors", 0))
        if executions >= 5 and errors / executions > 0.2:
            alerts.append({
                "alert_type": "agent_degraded", "entity_id": key, "severity": "high",
                "message": f"Agent '{key}' degraded: {errors}/{executions} executions failed.",
            })
    stale = await db.af_knowledge_sources.find(
        {"sync_status": "error"}, {"_id": 0, "source_id": 1, "name": 1, "sync_error": 1}
    ).to_list(length=50)
    for src in stale:
        alerts.append({
            "alert_type": "knowledge_sync_error", "entity_id": src["source_id"], "severity": "medium",
            "message": f"Knowledge source '{src['name']}' failed to sync: {src.get('sync_error', '')[:120]}",
        })
    now = _now()
    for alert in alerts:
        await db.af_alerts.update_one(
            {"alert_type": alert["alert_type"], "entity_id": alert["entity_id"], "resolved": {"$ne": True}},
            {"$set": {**alert, "updated_at": now}, "$setOnInsert": {"alert_id": str(uuid.uuid4()), "created_at": now, "resolved": False}},
            upsert=True,
        )
    active = await db.af_alerts.find({"resolved": {"$ne": True}}, {"_id": 0}).sort("updated_at", -1).to_list(length=100)
    return {"alerts": active, "active_count": len(active), "generated_at": now}
