"""Admin LLM Usage & Billing Dashboard.

Endpoints:
- GET    /api/admin/llm-billing/overview       — KPIs, trend, by-model, by-feature, top users
- GET    /api/admin/llm-billing/recent         — recent call log (last N)
- GET    /api/admin/llm-billing/budget         — current monthly budget + burn %
- PUT    /api/admin/llm-billing/budget         — update monthly budget ceiling
- GET    /api/admin/llm-billing/pricing        — pricing table used for cost estimation
- POST   /api/admin/llm-billing/seed-demo      — (admin) seed a handful of calls for demo

All endpoints are admin-only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.db import db, get_current_user
from services.llm_usage_logger import MODEL_PRICING

logger = logging.getLogger(__name__)
router = APIRouter()

BUDGET_CONFIG_ID = "llm_billing_budget"
DEFAULT_MONTHLY_BUDGET_USD = 500.0


async def _require_admin(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def _get_budget_doc() -> dict[str, Any]:
    doc = await db.llm_billing_config.find_one({"config_id": BUDGET_CONFIG_ID}, {"_id": 0})
    if not doc:
        doc = {
            "config_id": BUDGET_CONFIG_ID,
            "monthly_budget_usd": DEFAULT_MONTHLY_BUDGET_USD,
            "updated_at": _iso(datetime.now(timezone.utc)),
            "updated_by": None,
        }
        await db.llm_billing_config.insert_one({**doc})
        doc.pop("_id", None)
    return doc


# ──────────────────────────────────────────────────────────────────────────
# Overview
# ──────────────────────────────────────────────────────────────────────────
@router.get("/admin/llm-billing/overview")
async def llm_billing_overview(request: Request):
    await _require_admin(request)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    d7_ago = now - timedelta(days=7)
    d30_ago = now - timedelta(days=30)

    async def _sum(q: dict) -> dict[str, float]:
        pipe = [
            {"$match": q},
            {"$group": {
                "_id": None,
                "cost": {"$sum": "$cost_usd"},
                "tokens": {"$sum": "$total_tokens"},
                "calls": {"$sum": 1},
            }},
        ]
        async for d in db.llm_usage_log.aggregate(pipe):
            return {"cost": round(d.get("cost") or 0, 4),
                    "tokens": int(d.get("tokens") or 0),
                    "calls": int(d.get("calls") or 0)}
        return {"cost": 0.0, "tokens": 0, "calls": 0}

    kpi_today = await _sum({"timestamp": {"$gte": _iso(today_start)}})
    kpi_mtd = await _sum({"timestamp": {"$gte": _iso(month_start)}})
    kpi_7d = await _sum({"timestamp": {"$gte": _iso(d7_ago)}})
    kpi_30d = await _sum({"timestamp": {"$gte": _iso(d30_ago)}})

    # Daily trend (last 14 days)
    trend: list[dict[str, Any]] = []
    for i in range(13, -1, -1):
        day = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = day + timedelta(days=1)
        s = await _sum({"timestamp": {"$gte": _iso(day), "$lt": _iso(end)}})
        trend.append({"date": day.strftime("%Y-%m-%d"), **s})

    # By model (30d)
    by_model: list[dict[str, Any]] = []
    pipe_m = [
        {"$match": {"timestamp": {"$gte": _iso(d30_ago)}}},
        {"$group": {
            "_id": "$model",
            "cost": {"$sum": "$cost_usd"},
            "tokens": {"$sum": "$total_tokens"},
            "calls": {"$sum": 1},
        }},
        {"$sort": {"cost": -1}},
    ]
    async for d in db.llm_usage_log.aggregate(pipe_m):
        by_model.append({
            "model": d["_id"] or "unknown",
            "cost": round(d.get("cost") or 0, 4),
            "tokens": int(d.get("tokens") or 0),
            "calls": int(d.get("calls") or 0),
        })

    # By feature (30d)
    by_feature: list[dict[str, Any]] = []
    pipe_f = [
        {"$match": {"timestamp": {"$gte": _iso(d30_ago)}}},
        {"$group": {
            "_id": "$feature",
            "cost": {"$sum": "$cost_usd"},
            "tokens": {"$sum": "$total_tokens"},
            "calls": {"$sum": 1},
        }},
        {"$sort": {"cost": -1}},
        {"$limit": 15},
    ]
    async for d in db.llm_usage_log.aggregate(pipe_f):
        by_feature.append({
            "feature": d["_id"] or "unknown",
            "cost": round(d.get("cost") or 0, 4),
            "tokens": int(d.get("tokens") or 0),
            "calls": int(d.get("calls") or 0),
        })

    # Top users (30d)
    top_users: list[dict[str, Any]] = []
    pipe_u = [
        {"$match": {"timestamp": {"$gte": _iso(d30_ago)}}},
        {"$group": {
            "_id": "$user_id",
            "cost": {"$sum": "$cost_usd"},
            "calls": {"$sum": 1},
        }},
        {"$sort": {"cost": -1}},
        {"$limit": 10},
    ]
    async for d in db.llm_usage_log.aggregate(pipe_u):
        top_users.append({
            "user_id": d["_id"] or "anonymous",
            "cost": round(d.get("cost") or 0, 4),
            "calls": int(d.get("calls") or 0),
        })

    # Error rate (30d)
    total_30d = kpi_30d["calls"] or 0
    err_30d = await db.llm_usage_log.count_documents(
        {"timestamp": {"$gte": _iso(d30_ago)}, "success": False}
    )
    error_rate = round((err_30d / total_30d * 100), 2) if total_30d else 0.0

    # Average latency (30d)
    pipe_lat = [
        {"$match": {"timestamp": {"$gte": _iso(d30_ago)}, "latency_ms": {"$type": "number"}}},
        {"$group": {"_id": None, "avg": {"$avg": "$latency_ms"}}},
    ]
    avg_latency_ms = 0
    async for d in db.llm_usage_log.aggregate(pipe_lat):
        avg_latency_ms = int(d.get("avg") or 0)

    # Budget
    budget = await _get_budget_doc()
    monthly_budget = float(budget.get("monthly_budget_usd") or DEFAULT_MONTHLY_BUDGET_USD)
    burn_pct = round(min(100.0, (kpi_mtd["cost"] / max(monthly_budget, 0.01)) * 100), 1)

    # Projected month-end cost (linear extrapolation)
    days_into_month = (now - month_start).total_seconds() / 86400.0 or 0.0001
    # total days in current month
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)
    days_in_month = (next_month - month_start).total_seconds() / 86400.0
    projected_month = round((kpi_mtd["cost"] / days_into_month) * days_in_month, 2) if kpi_mtd["cost"] else 0.0

    return {
        "kpi": {
            "today": kpi_today,
            "mtd": kpi_mtd,
            "last_7d": kpi_7d,
            "last_30d": kpi_30d,
            "error_rate_pct_30d": error_rate,
            "avg_latency_ms_30d": avg_latency_ms,
        },
        "budget": {
            "monthly_budget_usd": monthly_budget,
            "mtd_cost_usd": kpi_mtd["cost"],
            "burn_pct": burn_pct,
            "projected_month_end_usd": projected_month,
            "over_budget": projected_month > monthly_budget,
        },
        "trend_14d": trend,
        "by_model": by_model,
        "by_feature": by_feature,
        "top_users": top_users,
        "generated_at": _iso(now),
    }


# ──────────────────────────────────────────────────────────────────────────
# Recent log
# ──────────────────────────────────────────────────────────────────────────
@router.get("/admin/llm-billing/recent")
async def llm_billing_recent(request: Request, limit: int = 50):
    await _require_admin(request)
    limit = max(1, min(limit, 500))
    items: list[dict[str, Any]] = []
    async for d in db.llm_usage_log.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit):
        items.append(d)
    return {"items": items, "count": len(items)}


# ──────────────────────────────────────────────────────────────────────────
# Budget
# ──────────────────────────────────────────────────────────────────────────
class BudgetUpdate(BaseModel):
    monthly_budget_usd: float = Field(..., gt=0, le=1_000_000)


@router.get("/admin/llm-billing/budget")
async def get_budget(request: Request):
    await _require_admin(request)
    return await _get_budget_doc()


@router.put("/admin/llm-billing/budget")
async def update_budget(request: Request, body: BudgetUpdate):
    user = await _require_admin(request)
    now = _iso(datetime.now(timezone.utc))
    await db.llm_billing_config.update_one(
        {"config_id": BUDGET_CONFIG_ID},
        {"$set": {
            "monthly_budget_usd": float(body.monthly_budget_usd),
            "updated_at": now,
            "updated_by": getattr(user, "email", None) or getattr(user, "user_id", None),
        }},
        upsert=True,
    )
    return await _get_budget_doc()


# ──────────────────────────────────────────────────────────────────────────
# Pricing
# ──────────────────────────────────────────────────────────────────────────
@router.get("/admin/llm-billing/pricing")
async def get_pricing(request: Request):
    await _require_admin(request)
    return {"models": MODEL_PRICING}


# ──────────────────────────────────────────────────────────────────────────
# Demo seeding — populates small sample so dashboard isn't empty on fresh installs
# ──────────────────────────────────────────────────────────────────────────
@router.post("/admin/llm-billing/seed-demo")
async def seed_demo(request: Request):
    await _require_admin(request)
    # Only seed if collection has fewer than 5 docs.
    existing = await db.llm_usage_log.count_documents({})
    if existing >= 5:
        return {"seeded": False, "existing": existing, "reason": "already has data"}

    now = datetime.now(timezone.utc)
    import random
    features = ["ai-lifecoach", "ai-resume", "ai-daily-brief", "ai-chatbot", "ai-copywriter"]
    models = ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4.5", "gemini-3-flash"]
    docs: list[dict[str, Any]] = []
    for d_ago in range(13, -1, -1):
        day = now - timedelta(days=d_ago)
        calls = random.randint(4, 18)
        for _ in range(calls):
            model = random.choice(models)
            pricing = MODEL_PRICING[model]
            it = random.randint(200, 1800)
            ot = random.randint(80, 1200)
            cost = round(
                (it / 1000) * pricing.get("input_per_1k", 0)
                + (ot / 1000) * pricing.get("output_per_1k", 0),
                6,
            )
            docs.append({
                "timestamp": _iso(day - timedelta(minutes=random.randint(0, 1400))),
                "model": model,
                "provider": "openai" if model.startswith("gpt") else ("anthropic" if "claude" in model else "google"),
                "feature": random.choice(features),
                "user_id": f"demo-user-{random.randint(1, 6)}",
                "session_id": None,
                "input_tokens": it,
                "output_tokens": ot,
                "total_tokens": it + ot,
                "cost_usd": cost,
                "latency_ms": random.randint(420, 2800),
                "success": random.random() > 0.04,
                "error": None,
            })
    if docs:
        await db.llm_usage_log.insert_many(docs)
    return {"seeded": True, "inserted": len(docs)}



# ──────────────────────────────────────────────────────────────────────────
# Daily Digest (manual trigger + preview)
# ──────────────────────────────────────────────────────────────────────────
@router.post("/admin/llm-billing/send-digest-now")
async def llm_billing_send_digest_now(request: Request):
    """Immediately send the daily LLM digest to every admin. Useful for preview & testing."""
    await _require_admin(request)
    from services.llm_daily_digest import send_daily_llm_digest
    return await send_daily_llm_digest(trigger="manual_admin")


@router.get("/admin/llm-billing/digest-preview")
async def llm_billing_digest_preview(request: Request):
    """Return the payload that would be injected into today's digest without sending."""
    await _require_admin(request)
    from services.llm_daily_digest import _aggregate_digest_payload
    return await _aggregate_digest_payload()
