"""Daily LLM Spend + Budget Burn Digest.

Aggregates the prior UTC day's LLM usage from `db.llm_usage_log` plus MTD spend and
budget posture from `db.llm_billing_config`, and emails a digest to every admin.

Scheduled at 08:00 UTC daily via `scheduler.py` (see `daily_llm_spend_digest`).
Also manually triggerable via `POST /api/admin/llm-billing/send-digest-now` for previews.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

BUDGET_CONFIG_ID = "llm_billing_budget"
DEFAULT_MONTHLY_BUDGET_USD = 500.0


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def _aggregate_digest_payload(now: datetime | None = None) -> dict[str, Any]:
    """Collect the metrics that populate the digest email. Pure data layer."""
    from routes.db import db

    now = now or datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    d30_ago = now - timedelta(days=30)

    async def _sum(q: dict) -> dict[str, float]:
        pipe = [
            {"$match": q},
            {"$group": {"_id": None,
                        "cost": {"$sum": "$cost_usd"},
                        "tokens": {"$sum": "$total_tokens"},
                        "calls": {"$sum": 1}}},
        ]
        async for d in db.llm_usage_log.aggregate(pipe):
            return {"cost": float(d.get("cost") or 0.0),
                    "tokens": int(d.get("tokens") or 0),
                    "calls": int(d.get("calls") or 0)}
        return {"cost": 0.0, "tokens": 0, "calls": 0}

    yday = await _sum({"timestamp": {"$gte": _iso(yesterday_start), "$lt": _iso(today_start)}})
    mtd = await _sum({"timestamp": {"$gte": _iso(month_start)}})

    # Top model + feature over trailing 30d
    async def _top(group_field: str) -> tuple[str, float]:
        async for d in db.llm_usage_log.aggregate([
            {"$match": {"timestamp": {"$gte": _iso(d30_ago)}}},
            {"$group": {"_id": f"${group_field}", "cost": {"$sum": "$cost_usd"}}},
            {"$sort": {"cost": -1}},
            {"$limit": 1},
        ]):
            return (d.get("_id") or "unknown", float(d.get("cost") or 0.0))
        return ("—", 0.0)

    top_model, top_model_cost = await _top("model")
    top_feature, top_feature_cost = await _top("feature")

    # Error rate + latency (30d)
    total_30d = await db.llm_usage_log.count_documents({"timestamp": {"$gte": _iso(d30_ago)}})
    err_30d = await db.llm_usage_log.count_documents(
        {"timestamp": {"$gte": _iso(d30_ago)}, "success": False}
    )
    error_rate_pct = round((err_30d / total_30d * 100), 2) if total_30d else 0.0
    avg_latency_ms = 0
    async for d in db.llm_usage_log.aggregate([
        {"$match": {"timestamp": {"$gte": _iso(d30_ago)}, "latency_ms": {"$type": "number"}}},
        {"$group": {"_id": None, "avg": {"$avg": "$latency_ms"}}},
    ]):
        avg_latency_ms = int(d.get("avg") or 0)

    # Budget + burn
    budget_doc = await db.llm_billing_config.find_one({"config_id": BUDGET_CONFIG_ID}, {"_id": 0})
    monthly_budget = float((budget_doc or {}).get("monthly_budget_usd") or DEFAULT_MONTHLY_BUDGET_USD)
    burn_pct = round(min(100.0, (mtd["cost"] / max(monthly_budget, 0.01)) * 100), 1)

    # Projection
    days_into_month = max((now - month_start).total_seconds() / 86400.0, 0.0001)
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)
    days_in_month = (next_month - month_start).total_seconds() / 86400.0
    projected = round((mtd["cost"] / days_into_month) * days_in_month, 2) if mtd["cost"] else 0.0

    return {
        "date_label": yesterday_start.strftime("%Y-%m-%d"),
        "yesterday_cost_usd": round(yday["cost"], 4),
        "yesterday_calls": yday["calls"],
        "yesterday_tokens": yday["tokens"],
        "mtd_cost_usd": round(mtd["cost"], 2),
        "monthly_budget_usd": monthly_budget,
        "burn_pct": burn_pct,
        "projected_month_end_usd": projected,
        "top_model": top_model,
        "top_model_cost_usd": round(top_model_cost, 2),
        "top_feature": top_feature,
        "top_feature_cost_usd": round(top_feature_cost, 2),
        "error_rate_pct": error_rate_pct,
        "avg_latency_ms": avg_latency_ms,
    }


async def send_daily_llm_digest(trigger: str = "scheduled") -> dict[str, Any]:
    """Send the daily LLM digest to every admin. Returns a small summary."""
    from routes.db import db
    from utils.email_service import send_catalog_template, is_email_configured

    payload = await _aggregate_digest_payload()
    admins: list[dict[str, Any]] = []
    async for u in db.users.find({"is_admin": True}, {"_id": 0, "email": 1, "name": 1}):
        email = (u or {}).get("email")
        if email:
            admins.append({"email": email, "name": (u or {}).get("name") or "Admin"})

    if not admins:
        logger.warning("[llm-daily-digest] No admins found — nothing to send (trigger=%s)", trigger)
        return {"sent": 0, "recipients": 0, "reason": "no_admins", "trigger": trigger, "payload": payload}

    if not is_email_configured():
        logger.warning("[llm-daily-digest] Email service not configured (RESEND_API_KEY missing) — skipping send (trigger=%s)", trigger)
        return {"sent": 0, "recipients": len(admins), "reason": "email_not_configured", "trigger": trigger, "payload": payload}

    sent = 0
    errors: list[str] = []
    for admin in admins:
        try:
            res = await send_catalog_template(admin["email"], "admin_llm_daily_digest", recipient_name=admin["name"], **payload)
            if res.get("success"):
                sent += 1
            else:
                errors.append(f"{admin['email']}: {res.get('error')}")
        except Exception as e:
            errors.append(f"{admin['email']}: {e}")

    logger.info("[llm-daily-digest] trigger=%s sent=%d/%d burn=%.1f%% yday=$%.2f",
                trigger, sent, len(admins), payload["burn_pct"], payload["yesterday_cost_usd"])

    # Audit log (best-effort)
    try:
        await db.llm_digest_log.insert_one({
            "created_at": _iso(datetime.now(timezone.utc)),
            "trigger": trigger,
            "sent": sent,
            "recipients": len(admins),
            "payload": payload,
            "errors": errors[:10],
        })
    except Exception:
        pass

    return {
        "sent": sent,
        "recipients": len(admins),
        "trigger": trigger,
        "burn_pct": payload["burn_pct"],
        "yesterday_cost_usd": payload["yesterday_cost_usd"],
        "errors": errors[:10],
    }
