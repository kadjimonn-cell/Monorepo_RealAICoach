"""AI Model Management endpoints — admin-only model registry, config, usage, and testing."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import uuid
import logging

from .db import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/models")

# Default model registry
DEFAULT_MODELS = [
    {
        "model_id": "gpt-4o",
        "provider": "openai",
        "name": "GPT-4o",
        "version": "gpt-4o",
        "description": "OpenAI's flagship multimodal model. Fast, accurate, and cost-effective.",
        "capabilities": ["text", "json", "code", "analysis"],
        "status": "active",
        "is_default": True,
        "config": {"temperature": 0.7, "max_tokens": 4000, "top_p": 1.0},
        "cost_per_1k_input": 0.0025,
        "cost_per_1k_output": 0.01,
    },
    {
        "model_id": "gpt-4o-mini",
        "provider": "openai",
        "name": "GPT-4o Mini",
        "version": "gpt-4o-mini",
        "description": "Lightweight version for quick tasks. Lower cost, faster response.",
        "capabilities": ["text", "json", "code"],
        "status": "inactive",
        "is_default": False,
        "config": {"temperature": 0.7, "max_tokens": 2000, "top_p": 1.0},
        "cost_per_1k_input": 0.00015,
        "cost_per_1k_output": 0.0006,
    },
    {
        "model_id": "claude-sonnet-4",
        "provider": "anthropic",
        "name": "Claude Sonnet 4",
        "version": "claude-sonnet-4-20250514",
        "description": "Anthropic's balanced model. Strong reasoning and safety alignment.",
        "capabilities": ["text", "json", "code", "analysis"],
        "status": "inactive",
        "is_default": False,
        "config": {"temperature": 0.7, "max_tokens": 4096, "top_p": 1.0},
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
    },
    {
        "model_id": "gemini-2.0-flash",
        "provider": "google",
        "name": "Gemini 2.0 Flash",
        "version": "gemini-2.0-flash",
        "description": "Google's fast multimodal model. Optimized for speed and efficiency.",
        "capabilities": ["text", "json", "code", "vision"],
        "status": "inactive",
        "is_default": False,
        "config": {"temperature": 0.7, "max_tokens": 8192, "top_p": 1.0},
        "cost_per_1k_input": 0.0001,
        "cost_per_1k_output": 0.0004,
    },
]


async def _ensure_models_seeded():
    """Seed default models if collection is empty."""
    count = await db.ai_models.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc).isoformat()
        for m in DEFAULT_MODELS:
            m["created_at"] = now
            m["updated_at"] = now
        await db.ai_models.insert_many(DEFAULT_MODELS)
        logger.info(f"Seeded {len(DEFAULT_MODELS)} AI models")


@router.get("")
async def list_models(request: Request):
    """List all registered AI models with their status and config."""
    await require_admin(request)
    await _ensure_models_seeded()
    models = await db.ai_models.find({}, {"_id": 0}).to_list(100)
    return {"models": models, "count": len(models)}


@router.get("/logs/recent")
async def get_recent_logs(request: Request, limit: int = 50):
    """Get recent AI API call logs."""
    await require_admin(request)
    logs = await db.ai_usage_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"logs": logs, "count": len(logs)}


@router.get("/usage/dashboard")
async def usage_dashboard(request: Request, range: str = "7d"):
    """Aggregated AI usage dashboard with time-series data."""
    await require_admin(request)

    now = datetime.now(timezone.utc)
    range_map = {"7d": 7, "30d": 30, "90d": 90}
    days = range_map.get(range, 7)
    since = (now - timedelta(days=days)).isoformat()

    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {
            "$facet": {
                "summary": [
                    {
                        "$group": {
                            "_id": None,
                            "total_requests": {"$sum": 1},
                            "total_input_tokens": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
                            "total_output_tokens": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
                            "total_cost": {"$sum": {"$ifNull": ["$cost", 0]}},
                            "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                        }
                    }
                ],
                "by_model": [
                    {
                        "$group": {
                            "_id": "$model_id",
                            "requests": {"$sum": 1},
                            "input_tokens": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
                            "output_tokens": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
                            "cost": {"$sum": {"$ifNull": ["$cost", 0]}},
                            "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                            "avg_latency": {"$avg": {"$ifNull": ["$latency_ms", 0]}},
                        }
                    },
                    {"$sort": {"requests": -1}},
                ],
                "daily": [
                    {
                        "$group": {
                            "_id": {"$substr": ["$created_at", 0, 10]},
                            "requests": {"$sum": 1},
                            "tokens": {
                                "$sum": {
                                    "$add": [{"$ifNull": ["$input_tokens", 0]}, {"$ifNull": ["$output_tokens", 0]}]
                                }
                            },
                            "cost": {"$sum": {"$ifNull": ["$cost", 0]}},
                            "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ],
                "by_feature": [
                    {"$group": {"_id": "$feature", "count": {"$sum": 1}, "cost": {"$sum": {"$ifNull": ["$cost", 0]}}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 10},
                ],
            }
        },
    ]

    result = await db.ai_usage_log.aggregate(pipeline).to_list(1)
    data = result[0] if result else {}

    s = data.get("summary", [{}])
    summary = s[0] if s else {}
    summary.pop("_id", None)
    total_req = summary.get("total_requests", 0)

    return {
        "range": range,
        "days": days,
        "summary": {
            "total_requests": total_req,
            "total_tokens": summary.get("total_input_tokens", 0) + summary.get("total_output_tokens", 0),
            "input_tokens": summary.get("total_input_tokens", 0),
            "output_tokens": summary.get("total_output_tokens", 0),
            "total_cost": round(summary.get("total_cost", 0), 4),
            "errors": summary.get("errors", 0),
            "error_rate": round(summary.get("errors", 0) / total_req * 100, 1) if total_req else 0,
        },
        "by_model": [
            {
                **m,
                "model_id": m.pop("_id"),
                "avg_latency": round(m.get("avg_latency", 0)),
                "cost": round(m.get("cost", 0), 4),
            }
            for m in data.get("by_model", [])
        ],
        "daily": [{**d, "date": d.pop("_id"), "cost": round(d.get("cost", 0), 4)} for d in data.get("daily", [])],
        "by_feature": [
            {**f, "feature": f.pop("_id"), "cost": round(f.get("cost", 0), 4)} for f in data.get("by_feature", [])
        ],
    }


@router.post("/usage/seed-demo")
async def seed_demo_usage(request: Request):
    """Seed demo usage data for the dashboard (admin-only). Idempotent — skips if data exists."""
    await require_admin(request)

    import random

    count = await db.ai_usage_log.count_documents({})
    if count > 50:
        return {"message": "Demo data already exists", "count": count}

    now = datetime.now(timezone.utc)
    models_config = [
        ("gpt-4o", "openai", 0.0025, 0.01),
        ("gpt-4o-mini", "openai", 0.00015, 0.0006),
        ("claude-sonnet-4", "anthropic", 0.003, 0.015),
        ("gemini-2.0-flash", "google", 0.0001, 0.0004),
    ]
    features = ["ai-coach", "medimate", "ai-writer", "ai-copywriter", "career-advisor", "code-assist", "ai-chat"]
    statuses = ["success"] * 19 + ["error"]  # 5% error rate
    docs = []

    for day_offset in range(30):
        date = now - timedelta(days=day_offset)
        daily_count = random.randint(8, 40) if day_offset < 7 else random.randint(3, 20)
        for _ in range(daily_count):
            mid, provider, cost_in, cost_out = random.choice(models_config)
            inp_tok = random.randint(50, 2000)
            out_tok = random.randint(20, 1500)
            cost = round(inp_tok / 1000 * cost_in + out_tok / 1000 * cost_out, 6)
            hour = random.randint(0, 23)
            minute = random.randint(0, 59)
            ts = date.replace(hour=hour, minute=minute, second=random.randint(0, 59))
            docs.append(
                {
                    "log_id": f"log_{uuid.uuid4().hex[:12]}",
                    "model_id": mid,
                    "provider": provider,
                    "feature": random.choice(features),
                    "user_id": f"user_{uuid.uuid4().hex[:10]}",
                    "input_tokens": inp_tok,
                    "output_tokens": out_tok,
                    "cost": cost,
                    "latency_ms": random.randint(200, 3000),
                    "status": random.choice(statuses),
                    "created_at": ts.isoformat(),
                }
            )

    if docs:
        await db.ai_usage_log.insert_many(docs)

    return {"message": f"Seeded {len(docs)} demo usage logs", "count": len(docs)}


class AddModelRequest(BaseModel):
    model_id: str
    provider: str
    name: str
    version: str
    description: Optional[str] = ""
    capabilities: Optional[list] = ["text"]
    config: Optional[Dict[str, Any]] = None
    cost_per_1k_input: Optional[float] = 0
    cost_per_1k_output: Optional[float] = 0


@router.post("/add")
async def add_model(payload: AddModelRequest, request: Request):
    """Add a new AI model to the registry."""
    admin = await require_admin(request)

    existing = await db.ai_models.find_one({"model_id": payload.model_id})
    if existing:
        raise HTTPException(status_code=409, detail="Model with this ID already exists")

    now = datetime.now(timezone.utc).isoformat()
    model = {
        "model_id": payload.model_id,
        "provider": payload.provider,
        "name": payload.name,
        "version": payload.version,
        "description": payload.description,
        "capabilities": payload.capabilities,
        "status": "inactive",
        "is_default": False,
        "config": payload.config or {"temperature": 0.7, "max_tokens": 4000, "top_p": 1.0},
        "cost_per_1k_input": payload.cost_per_1k_input,
        "cost_per_1k_output": payload.cost_per_1k_output,
        "created_at": now,
        "updated_at": now,
    }

    await db.ai_models.insert_one(model)
    model.pop("_id", None)

    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"ai_model_add_{uuid.uuid4().hex[:10]}",
            "user_id": admin.user_id,
            "action": "ai_model_add",
            "target": payload.model_id,
            "created_at": now,
        }
    )

    return {"model": model, "success": True}


# ────────── Budget & Cost Alerts ──────────

DEFAULT_BUDGETS = {
    "global": {"monthly_limit": 50.0, "warn_at": 80, "critical_at": 95},
    "per_model": {
        "gpt-4o": {"monthly_limit": 25.0, "warn_at": 80, "critical_at": 95},
        "gpt-4o-mini": {"monthly_limit": 10.0, "warn_at": 80, "critical_at": 95},
        "claude-sonnet-4": {"monthly_limit": 25.0, "warn_at": 80, "critical_at": 95},
        "gemini-2.0-flash": {"monthly_limit": 10.0, "warn_at": 80, "critical_at": 95},
    },
}


async def _ensure_budgets():
    existing = await db.ai_budgets.find_one({"type": "global"}, {"_id": 0})
    if not existing:
        now = datetime.now(timezone.utc).isoformat()
        await db.ai_budgets.insert_one(
            {
                "type": "global",
                "monthly_limit": 50.0,
                "warn_at": 80,
                "critical_at": 95,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        for mid, cfg in DEFAULT_BUDGETS["per_model"].items():
            await db.ai_budgets.insert_one(
                {
                    "type": "model",
                    "model_id": mid,
                    "monthly_limit": cfg["monthly_limit"],
                    "warn_at": cfg["warn_at"],
                    "critical_at": cfg["critical_at"],
                    "enabled": True,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        logger.info("Seeded default AI budgets")


@router.get("/budgets")
async def get_budgets(request: Request):
    await require_admin(request)
    await _ensure_budgets()
    budgets = await db.ai_budgets.find({}, {"_id": 0}).to_list(50)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    g_res = await db.ai_usage_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": month_start}}},
            {"$group": {"_id": None, "cost": {"$sum": {"$ifNull": ["$cost", 0]}}, "req": {"$sum": 1}}},
        ]
    ).to_list(1)
    g_spend = g_res[0]["cost"] if g_res else 0
    g_req = g_res[0]["req"] if g_res else 0
    m_res = await db.ai_usage_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": month_start}}},
            {"$group": {"_id": "$model_id", "cost": {"$sum": {"$ifNull": ["$cost", 0]}}, "req": {"$sum": 1}}},
        ]
    ).to_list(50)
    m_spend = {m["_id"]: {"cost": round(m["cost"], 4), "requests": m["req"]} for m in m_res}
    enriched = []
    for b in budgets:
        if b["type"] == "global":
            spend, requests = round(g_spend, 4), g_req
        else:
            ms = m_spend.get(b.get("model_id", ""), {"cost": 0, "requests": 0})
            spend, requests = ms["cost"], ms["requests"]
        limit = b.get("monthly_limit", 0)
        pct = round(spend / limit * 100, 1) if limit > 0 else 0
        status = "critical" if pct >= b.get("critical_at", 95) else "warning" if pct >= b.get("warn_at", 80) else "ok"
        enriched.append({**b, "current_spend": spend, "current_requests": requests, "usage_pct": pct, "status": status})
    alerts = await db.ai_budget_alerts.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"budgets": enriched, "alerts": alerts, "month": now.strftime("%Y-%m")}


class BudgetUpdate(BaseModel):
    monthly_limit: Optional[float] = None
    warn_at: Optional[int] = None
    critical_at: Optional[int] = None
    enabled: Optional[bool] = None


@router.put("/budgets/global")
async def update_global_budget(payload: BudgetUpdate, request: Request):
    admin = await require_admin(request)
    await _ensure_budgets()
    update: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.monthly_limit is not None:
        if payload.monthly_limit < 0:
            raise HTTPException(status_code=400, detail="Limit must be >= 0")
        update["monthly_limit"] = payload.monthly_limit
    if payload.warn_at is not None:
        update["warn_at"] = payload.warn_at
    if payload.critical_at is not None:
        update["critical_at"] = payload.critical_at
    if payload.enabled is not None:
        update["enabled"] = payload.enabled
    await db.ai_budgets.update_one({"type": "global"}, {"$set": update})
    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"budget_upd_{uuid.uuid4().hex[:10]}",
            "user_id": admin.user_id,
            "action": "ai_budget_update",
            "target": "global",
            "changes": update,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    updated = await db.ai_budgets.find_one({"type": "global"}, {"_id": 0})
    return {"budget": updated, "success": True}


@router.put("/budgets/model/{model_id}")
async def update_model_budget(model_id: str, payload: BudgetUpdate, request: Request):
    admin = await require_admin(request)
    await _ensure_budgets()
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.ai_budgets.find_one({"type": "model", "model_id": model_id}, {"_id": 0})
    update: Dict[str, Any] = {"updated_at": now}
    if payload.monthly_limit is not None:
        if payload.monthly_limit < 0:
            raise HTTPException(status_code=400, detail="Limit must be >= 0")
        update["monthly_limit"] = payload.monthly_limit
    if payload.warn_at is not None:
        update["warn_at"] = payload.warn_at
    if payload.critical_at is not None:
        update["critical_at"] = payload.critical_at
    if payload.enabled is not None:
        update["enabled"] = payload.enabled
    if existing:
        await db.ai_budgets.update_one({"type": "model", "model_id": model_id}, {"$set": update})
    else:
        await db.ai_budgets.insert_one(
            {
                "type": "model",
                "model_id": model_id,
                "monthly_limit": payload.monthly_limit or 25.0,
                "warn_at": payload.warn_at or 80,
                "critical_at": payload.critical_at or 95,
                "enabled": True if payload.enabled is None else payload.enabled,
                "created_at": now,
                "updated_at": now,
            }
        )
    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"budget_upd_{uuid.uuid4().hex[:10]}",
            "user_id": admin.user_id,
            "action": "ai_budget_update",
            "target": model_id,
            "changes": update,
            "created_at": now,
        }
    )
    updated = await db.ai_budgets.find_one({"type": "model", "model_id": model_id}, {"_id": 0})
    return {"budget": updated, "success": True}


@router.post("/budgets/check")
async def check_budgets(request: Request):
    await require_admin(request)
    await _ensure_budgets()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    budgets = await db.ai_budgets.find({"enabled": True}, {"_id": 0}).to_list(50)
    new_alerts = []
    for b in budgets:
        if b["type"] == "global":
            pipeline = [
                {"$match": {"created_at": {"$gte": month_start}}},
                {"$group": {"_id": None, "cost": {"$sum": {"$ifNull": ["$cost", 0]}}}},
            ]
            label = "Global Budget"
        else:
            mid = b.get("model_id", "")
            pipeline = [
                {"$match": {"model_id": mid, "created_at": {"$gte": month_start}}},
                {"$group": {"_id": None, "cost": {"$sum": {"$ifNull": ["$cost", 0]}}}},
            ]
            label = f"Model: {mid}"
        result = await db.ai_usage_log.aggregate(pipeline).to_list(1)
        spend = result[0]["cost"] if result else 0
        limit = b.get("monthly_limit", 0)
        pct = round(spend / limit * 100, 1) if limit > 0 else 0
        level = "critical" if pct >= b.get("critical_at", 95) else "warning" if pct >= b.get("warn_at", 80) else None
        if level:
            recent = await db.ai_budget_alerts.find_one(
                {
                    "target": b.get("model_id", "global"),
                    "level": level,
                    "created_at": {"$gte": (now - timedelta(hours=1)).isoformat()},
                }
            )
            if not recent:
                alert = {
                    "alert_id": f"alert_{uuid.uuid4().hex[:10]}",
                    "target": b.get("model_id", "global"),
                    "label": label,
                    "level": level,
                    "spend": round(spend, 4),
                    "limit": limit,
                    "usage_pct": pct,
                    "message": f"{label} at {pct}% of ${limit}/mo (${round(spend, 2)} spent)",
                    "created_at": now.isoformat(),
                    "acknowledged": False,
                }
                await db.ai_budget_alerts.insert_one(alert)
                del alert["_id"]
                new_alerts.append(alert)
    return {"checked": len(budgets), "new_alerts": new_alerts, "alert_count": len(new_alerts)}


@router.post("/budgets/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: Request):
    await require_admin(request)
    result = await db.ai_budget_alerts.update_one(
        {"alert_id": alert_id},
        {"$set": {"acknowledged": True, "acknowledged_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True}


@router.get("/reports")
async def get_reports(request: Request, limit: int = 10):
    await require_admin(request)
    reports = await db.ai_budget_reports.find({}, {"_id": 0}).sort("generated_at", -1).limit(limit).to_list(limit)
    return {"reports": reports, "count": len(reports)}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, request: Request):
    await require_admin(request)
    report = await db.ai_budget_reports.find_one({"report_id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/reports/generate")
async def trigger_report(request: Request):
    await require_admin(request)
    report = await generate_weekly_budget_report()
    return {"success": True, "report_id": report["report_id"]}


# ────────── Model-specific routes (must be LAST) ──────────


@router.get("/{model_id}")
async def get_model(model_id: str, request: Request):
    """Get details for a specific model."""
    await require_admin(request)
    model = await db.ai_models.find_one({"model_id": model_id}, {"_id": 0})
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"model": model}


@router.get("/{model_id}/stats")
async def get_model_stats(model_id: str, request: Request):
    """Get usage stats for a specific model."""
    await require_admin(request)

    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    pipeline = [
        {"$match": {"model_id": model_id}},
        {
            "$facet": {
                "total": [{"$count": "count"}],
                "last_24h": [{"$match": {"created_at": {"$gte": day_ago}}}, {"$count": "count"}],
                "last_7d": [{"$match": {"created_at": {"$gte": week_ago}}}, {"$count": "count"}],
                "last_30d": [{"$match": {"created_at": {"$gte": month_ago}}}, {"$count": "count"}],
                "tokens": [
                    {"$group": {"_id": None, "input": {"$sum": "$input_tokens"}, "output": {"$sum": "$output_tokens"}}}
                ],
                "errors": [{"$match": {"status": "error"}}, {"$count": "count"}],
                "by_feature": [{"$group": {"_id": "$feature", "count": {"$sum": 1}}}],
                "daily": [
                    {"$match": {"created_at": {"$gte": week_ago}}},
                    {"$group": {"_id": {"$substr": ["$created_at", 0, 10]}, "count": {"$sum": 1}}},
                    {"$sort": {"_id": 1}},
                ],
            }
        },
    ]

    result = await db.ai_usage_log.aggregate(pipeline).to_list(1)
    data = result[0] if result else {}

    total_list = data.get("total", [])
    total = total_list[0].get("count", 0) if total_list else 0
    errors_list = data.get("errors", [])
    errors = errors_list[0].get("count", 0) if errors_list else 0
    tokens_list = data.get("tokens", [])
    tokens = tokens_list[0] if tokens_list else {}

    return {
        "model_id": model_id,
        "calls": {
            "total": total,
            "last_24h": (data.get("last_24h", [{}])[0].get("count", 0)) if data.get("last_24h") else 0,
            "last_7d": (data.get("last_7d", [{}])[0].get("count", 0)) if data.get("last_7d") else 0,
            "last_30d": (data.get("last_30d", [{}])[0].get("count", 0)) if data.get("last_30d") else 0,
        },
        "tokens": {
            "input": tokens.get("input", 0),
            "output": tokens.get("output", 0),
            "total": tokens.get("input", 0) + tokens.get("output", 0),
        },
        "errors": errors,
        "error_rate": round(errors / total * 100, 1) if total else 0,
        "by_feature": sorted(data.get("by_feature", []), key=lambda x: -x["count"]),
        "daily_trend": data.get("daily", []),
    }


class ModelConfigUpdate(BaseModel):
    status: Optional[str] = None  # active, inactive
    is_default: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


@router.put("/{model_id}/config")
async def update_model_config(model_id: str, payload: ModelConfigUpdate, request: Request):
    """Update model configuration (status, default, parameters)."""
    admin = await require_admin(request)

    model = await db.ai_models.find_one({"model_id": model_id}, {"_id": 0})
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    update: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if payload.status is not None:
        if payload.status not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="Status must be 'active' or 'inactive'")
        update["status"] = payload.status

    if payload.is_default is True:
        # Unset any existing default
        await db.ai_models.update_many({"is_default": True}, {"$set": {"is_default": False}})
        update["is_default"] = True
        update["status"] = "active"  # Default model must be active

    if payload.config is not None:
        # Validate config params
        cfg = payload.config
        if "temperature" in cfg and not (0 <= cfg["temperature"] <= 2):
            raise HTTPException(status_code=400, detail="Temperature must be 0-2")
        if "max_tokens" in cfg and not (100 <= cfg["max_tokens"] <= 128000):
            raise HTTPException(status_code=400, detail="Max tokens must be 100-128000")
        update["config"] = {**model.get("config", {}), **cfg}

    await db.ai_models.update_one({"model_id": model_id}, {"$set": update})

    # Audit log
    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"ai_model_{uuid.uuid4().hex[:10]}",
            "user_id": admin.user_id,
            "action": "ai_model_config_update",
            "target": model_id,
            "changes": {k: v for k, v in update.items() if k != "updated_at"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    updated = await db.ai_models.find_one({"model_id": model_id}, {"_id": 0})
    return {"model": updated, "success": True}


class ModelTestRequest(BaseModel):
    prompt: Optional[str] = "Say 'Hello from {model_name}!' in one sentence."


@router.post("/{model_id}/test")
async def test_model(model_id: str, payload: ModelTestRequest, request: Request):
    """Test model connectivity and response."""
    await require_admin(request)

    model = await db.ai_models.find_one({"model_id": model_id}, {"_id": 0})
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    import time

    start = time.time()

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.db import EMERGENT_LLM_KEY

        prompt = payload.prompt.replace("{model_name}", model["name"])
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"model-test-{model_id}-{uuid.uuid4().hex[:6]}",
            system_message="You are a helpful assistant. Respond concisely.",
        ).with_model(model["provider"], model["version"])

        response = await chat.send_message(UserMessage(text=prompt))
        elapsed = round((time.time() - start) * 1000)
        text = response.text if hasattr(response, "text") else str(response)

        return {
            "success": True,
            "model_id": model_id,
            "response": text[:500],
            "latency_ms": elapsed,
            "provider": model["provider"],
        }
    except Exception as e:
        elapsed = round((time.time() - start) * 1000)
        logger.error(f"Model test failed for {model_id}: {e}")
        return {
            "success": False,
            "model_id": model_id,
            "error": str(e)[:300],
            "latency_ms": elapsed,
            "provider": model["provider"],
        }


@router.delete("/{model_id}")
async def delete_model(model_id: str, request: Request):
    """Remove a model from the registry."""
    admin = await require_admin(request)

    model = await db.ai_models.find_one({"model_id": model_id}, {"_id": 0})
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.get("is_default"):
        raise HTTPException(status_code=400, detail="Cannot delete the default model")

    await db.ai_models.delete_one({"model_id": model_id})

    await db.admin_audit_logs.insert_one(
        {
            "event_id": f"ai_model_del_{uuid.uuid4().hex[:10]}",
            "user_id": admin.user_id,
            "action": "ai_model_delete",
            "target": model_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    return {"success": True, "deleted": model_id}


# ────────── Weekly Budget Reports ──────────


async def generate_weekly_budget_report():
    """Generate a weekly AI spend report and store it + send as in-app notification to admins."""
    now = datetime.now(timezone.utc)
    week_end = now
    week_start = now - timedelta(days=7)
    prev_start = week_start - timedelta(days=7)

    async def _get_period_data(since: str, until: str):
        pipeline = [
            {"$match": {"created_at": {"$gte": since, "$lte": until}}},
            {
                "$facet": {
                    "summary": [
                        {
                            "$group": {
                                "_id": None,
                                "total_requests": {"$sum": 1},
                                "total_cost": {"$sum": {"$ifNull": ["$cost", 0]}},
                                "total_tokens": {
                                    "$sum": {
                                        "$add": [{"$ifNull": ["$input_tokens", 0]}, {"$ifNull": ["$output_tokens", 0]}]
                                    }
                                },
                                "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                            }
                        }
                    ],
                    "by_model": [
                        {
                            "$group": {
                                "_id": "$model_id",
                                "requests": {"$sum": 1},
                                "cost": {"$sum": {"$ifNull": ["$cost", 0]}},
                                "tokens": {
                                    "$sum": {
                                        "$add": [{"$ifNull": ["$input_tokens", 0]}, {"$ifNull": ["$output_tokens", 0]}]
                                    }
                                },
                            }
                        },
                        {"$sort": {"cost": -1}},
                    ],
                    "by_feature": [
                        {
                            "$group": {
                                "_id": "$feature",
                                "count": {"$sum": 1},
                                "cost": {"$sum": {"$ifNull": ["$cost", 0]}},
                            }
                        },
                        {"$sort": {"count": -1}},
                        {"$limit": 5},
                    ],
                }
            },
        ]
        result = await db.ai_usage_log.aggregate(pipeline).to_list(1)
        data = result[0] if result else {}
        s = data.get("summary", [{}])
        summary = s[0] if s else {}
        summary.pop("_id", None)
        return {
            "total_requests": summary.get("total_requests", 0),
            "total_cost": round(summary.get("total_cost", 0), 4),
            "total_tokens": summary.get("total_tokens", 0),
            "errors": summary.get("errors", 0),
            "by_model": [
                {**m, "model_id": m.pop("_id"), "cost": round(m.get("cost", 0), 4)} for m in data.get("by_model", [])
            ],
            "by_feature": [
                {**f, "feature": f.pop("_id"), "cost": round(f.get("cost", 0), 4)} for f in data.get("by_feature", [])
            ],
        }

    current = await _get_period_data(week_start.isoformat(), week_end.isoformat())
    previous = await _get_period_data(prev_start.isoformat(), week_start.isoformat())

    # Compute week-over-week trends
    def _trend(curr, prev):
        if prev == 0:
            return 100.0 if curr > 0 else 0.0
        return round((curr - prev) / prev * 100, 1)

    trends = {
        "requests": _trend(current["total_requests"], previous["total_requests"]),
        "cost": _trend(current["total_cost"], previous["total_cost"]),
        "tokens": _trend(current["total_tokens"], previous["total_tokens"]),
    }

    # Budget status
    await _ensure_budgets()
    budgets_raw = await db.ai_budgets.find({"enabled": True}, {"_id": 0}).to_list(50)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    g_res = await db.ai_usage_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": month_start}}},
            {"$group": {"_id": None, "cost": {"$sum": {"$ifNull": ["$cost", 0]}}}},
        ]
    ).to_list(1)
    global_spend = g_res[0]["cost"] if g_res else 0
    m_res = await db.ai_usage_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": month_start}}},
            {"$group": {"_id": "$model_id", "cost": {"$sum": {"$ifNull": ["$cost", 0]}}}},
        ]
    ).to_list(50)
    model_spend_map = {m["_id"]: round(m["cost"], 4) for m in m_res}

    budget_status = []
    for b in budgets_raw:
        spend = round(global_spend, 4) if b["type"] == "global" else model_spend_map.get(b.get("model_id", ""), 0)
        limit = b.get("monthly_limit", 0)
        pct = round(spend / limit * 100, 1) if limit > 0 else 0
        status = "critical" if pct >= b.get("critical_at", 95) else "warning" if pct >= b.get("warn_at", 80) else "ok"
        budget_status.append(
            {
                "type": b["type"],
                "model_id": b.get("model_id"),
                "spend": spend,
                "limit": limit,
                "pct": pct,
                "status": status,
            }
        )

    # Active alerts count
    active_alerts = await db.ai_budget_alerts.count_documents({"acknowledged": False})

    report = {
        "report_id": f"rpt_{uuid.uuid4().hex[:12]}",
        "type": "weekly_ai_budget",
        "period_start": week_start.isoformat(),
        "period_end": week_end.isoformat(),
        "generated_at": now.isoformat(),
        "current_week": current,
        "previous_week": previous,
        "trends": trends,
        "budget_status": budget_status,
        "active_alerts": active_alerts,
        "month": now.strftime("%Y-%m"),
    }

    await db.ai_budget_reports.insert_one({**report})
    report.pop("_id", None)

    # Create in-app notifications for all admin users
    admin_users = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(50)
    warnings = [b for b in budget_status if b["status"] in ("warning", "critical")]
    alert_text = f" ({len(warnings)} budget alerts)" if warnings else ""

    for admin in admin_users:
        notif = {
            "id": f"notif_{uuid.uuid4().hex[:12]}",
            "user_id": admin["user_id"],
            "type": "weekly_ai_report",
            "title": f"Weekly AI Spend Report{alert_text}",
            "message": f"This week: {current['total_requests']} requests, ${current['total_cost']:.2f} cost ({trends['cost']:+.1f}% vs last week). MTD budget: ${round(global_spend, 2)} of ${budget_status[0]['limit'] if budget_status else 50}.",
            "data": {"report_id": report["report_id"]},
            "read": False,
            "created_at": now.isoformat(),
        }
        await db.notifications.insert_one(notif)

    logger.info(
        f"Weekly AI budget report generated: {report['report_id']} — {current['total_requests']} requests, ${current['total_cost']:.4f}"
    )
    return report
