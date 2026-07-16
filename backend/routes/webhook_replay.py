"""Webhook Event Replay – Admin-only executive dashboard API.

Endpoints:
  GET  /api/admin/webhook-replay/stats        – aggregate KPIs
  GET  /api/admin/webhook-replay/events       – list + filter events
  GET  /api/admin/webhook-replay/events/{eid} – single event detail + replay history
  POST /api/admin/webhook-replay/events/{eid}/replay  – replay one event
  POST /api/admin/webhook-replay/bulk-replay  – replay many events
  POST /api/admin/webhook-replay/events/{eid}/resolve – mark event resolved
  GET  /api/admin/webhook-replay/retry-rules  – list retry rules
  POST /api/admin/webhook-replay/retry-rules  – create/update a retry rule
  DELETE /api/admin/webhook-replay/retry-rules/{integration_id} – delete rule
  GET  /api/admin/webhook-replay/retry-queue  – queue status
  POST /api/admin/webhook-replay/retry-queue/trigger – manually trigger retry cycle
  POST /api/admin/webhook-replay/retry-queue/clear   – clear exhausted items
"""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
import re
from pydantic import BaseModel
from typing import List, Optional
from routes.db import db, require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/webhook-replay", tags=["Webhook Replay"])

COL = "webhook_events"


async def _admin_guard(request: Request):
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ── Stats ─────────────────────────────────────────────
@router.get("/stats")
async def replay_stats(request: Request):
    await _admin_guard(request)
    col = db[COL]
    total = await col.count_documents({})
    failed = await col.count_documents({"status": {"$in": ["failed", "error"]}})
    replayed = await col.count_documents({"replay_count": {"$gte": 1}})
    resolved = await col.count_documents({"resolution_status": "resolved"})
    pending = await col.count_documents({"status": "received", "resolution_status": {"$ne": "resolved"}})

    # Per-integration breakdown
    pipe = [
        {
            "$group": {
                "_id": "$integration_id",
                "total": {"$sum": 1},
                "failed": {"$sum": {"$cond": [{"$in": ["$status", ["failed", "error"]]}, 1, 0]}},
                "replayed": {"$sum": {"$cond": [{"$gte": ["$replay_count", 1]}, 1, 0]}},
            }
        },
        {"$sort": {"total": -1}},
    ]
    integrations = await col.aggregate(pipe).to_list(20)

    # Event type breakdown
    type_pipe = [
        {
            "$group": {
                "_id": "$event_type",
                "count": {"$sum": 1},
                "failed": {"$sum": {"$cond": [{"$in": ["$status", ["failed", "error"]]}, 1, 0]}},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    event_types = await col.aggregate(type_pipe).to_list(10)

    # Recent 7-day trend
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    daily_pipe = [
        {"$match": {"created_at": {"$gte": week_ago}}},
        {"$addFields": {"day": {"$substr": ["$created_at", 0, 10]}}},
        {
            "$group": {
                "_id": "$day",
                "count": {"$sum": 1},
                "failed": {"$sum": {"$cond": [{"$in": ["$status", ["failed", "error"]]}, 1, 0]}},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    daily_trend = await col.aggregate(daily_pipe).to_list(7)

    return {
        "total": total,
        "failed": failed,
        "replayed": replayed,
        "resolved": resolved,
        "pending": pending,
        "success_rate": round((1 - failed / max(total, 1)) * 100, 1),
        "integrations": [
            {"id": i["_id"], "total": i["total"], "failed": i["failed"], "replayed": i["replayed"]}
            for i in integrations
        ],
        "event_types": [{"type": e["_id"], "count": e["count"], "failed": e["failed"]} for e in event_types],
        "daily_trend": [{"date": d["_id"], "count": d["count"], "failed": d["failed"]} for d in daily_trend],
    }


# ── List Events ───────────────────────────────────────
@router.get("/events")
async def list_events(
    request: Request,
    integration_id: Optional[str] = None,
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    resolution: Optional[str] = None,
    search: Optional[str] = None,
    days: int = 30,
    page: int = 1,
    limit: int = 25,
):
    await _admin_guard(request)
    query: dict = {}
    if integration_id:
        query["integration_id"] = integration_id
    if status:
        query["status"] = status
    if event_type:
        query["event_type"] = event_type
    if resolution:
        query["resolution_status"] = resolution
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        query["created_at"] = {"$gte": cutoff}
    if search:
        query["$or"] = [
            {"event_id": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"event_type": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]

    total = await db[COL].count_documents(query)
    skip = (page - 1) * limit
    events = await db[COL].find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {
        "events": events,
        "total": total,
        "page": page,
        "pages": max(1, -(-total // limit)),
    }


# ── Event Detail ──────────────────────────────────────
@router.get("/events/{event_id}")
async def event_detail(request: Request, event_id: str):
    await _admin_guard(request)
    event = await db[COL].find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


# ── Replay Single Event ──────────────────────────────
@router.post("/events/{event_id}/replay")
async def replay_event(request: Request, event_id: str):
    user = await _admin_guard(request)
    event = await db[COL].find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    now = datetime.now(timezone.utc).isoformat()
    replay_entry = {
        "replayed_at": now,
        "replayed_by": user.email,
        "previous_status": event.get("status", "unknown"),
    }

    # Simulate re-processing the event
    new_status = "replayed"
    try:
        await _process_webhook_event(event)
        new_status = "replayed"
        replay_entry["result"] = "success"
    except Exception as e:
        new_status = "replay_failed"
        replay_entry["result"] = "failed"
        replay_entry["error"] = str(e)
        logger.error(f"Replay failed for {event_id}: {e}")

    await db[COL].update_one(
        {"event_id": event_id},
        {
            "$set": {"status": new_status, "last_replayed_at": now},
            "$inc": {"replay_count": 1},
            "$push": {"replay_history": replay_entry},
        },
    )

    # Push real-time notification
    try:
        from utils.ws_manager import push_admin_alert

        await push_admin_alert(
            "webhook_replay",
            f"Event Replayed: {event_id}",
            f"{event.get('event_type')} from {event.get('integration_id')} — {new_status}",
            "info" if new_status == "replayed" else "warning",
            {"event_id": event_id},
        )
    except Exception:
        pass

    updated = await db[COL].find_one({"event_id": event_id}, {"_id": 0})
    return {"success": True, "event": updated}


# ── Bulk Replay ───────────────────────────────────────
class BulkReplayRequest(BaseModel):
    event_ids: List[str]


@router.post("/bulk-replay")
async def bulk_replay(request: Request, body: BulkReplayRequest):
    user = await _admin_guard(request)
    if len(body.event_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 events per bulk replay")

    results = []
    for eid in body.event_ids:
        event = await db[COL].find_one({"event_id": eid}, {"_id": 0})
        if not event:
            results.append({"event_id": eid, "result": "not_found"})
            continue

        now = datetime.now(timezone.utc).isoformat()
        replay_entry = {
            "replayed_at": now,
            "replayed_by": user.email,
            "previous_status": event.get("status", "unknown"),
        }
        try:
            await _process_webhook_event(event)
            replay_entry["result"] = "success"
            new_status = "replayed"
        except Exception as e:
            replay_entry["result"] = "failed"
            replay_entry["error"] = str(e)
            new_status = "replay_failed"

        await db[COL].update_one(
            {"event_id": eid},
            {
                "$set": {"status": new_status, "last_replayed_at": now},
                "$inc": {"replay_count": 1},
                "$push": {"replay_history": replay_entry},
            },
        )
        results.append({"event_id": eid, "result": replay_entry["result"], "status": new_status})

    succeeded = sum(1 for r in results if r["result"] == "success")
    return {
        "success": True,
        "total": len(body.event_ids),
        "succeeded": succeeded,
        "failed": len(body.event_ids) - succeeded,
        "results": results,
    }


# ── Resolve Event ─────────────────────────────────────
class ResolveRequest(BaseModel):
    note: Optional[str] = None


@router.post("/events/{event_id}/resolve")
async def resolve_event(request: Request, event_id: str, body: ResolveRequest):
    user = await _admin_guard(request)
    event = await db[COL].find_one({"event_id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    now = datetime.now(timezone.utc).isoformat()
    await db[COL].update_one(
        {"event_id": event_id},
        {
            "$set": {
                "resolution_status": "resolved",
                "resolved_at": now,
                "resolved_by": user.email,
                "resolution_note": body.note or "",
            }
        },
    )
    updated = await db[COL].find_one({"event_id": event_id}, {"_id": 0})
    return {"success": True, "event": updated}


# ── Internal: process/replay a webhook event ──────────
async def _process_webhook_event(event: dict):
    """Re-process a webhook event through the integration handler.
    This simulates what happens when FedaPay/Greenhouse/Lever/Workday sends a webhook.
    """
    integration = event.get("integration_id", "")
    event_type = event.get("event_type", "")
    payload = event.get("payload", {})

    logger.info(f"Replaying webhook: {integration}/{event_type} (id={event.get('event_id')})")

    # For ATS/HRIS integrations, trigger the sync handler
    if integration in ("greenhouse", "lever", "workday"):
        # Re-trigger the event processing pipeline
        await db.webhook_replay_log.insert_one(
            {
                "event_id": event.get("event_id"),
                "integration_id": integration,
                "event_type": event_type,
                "payload": payload,
                "replayed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    elif integration == "fedapay":
        # For payment webhooks, log the replay
        await db.webhook_replay_log.insert_one(
            {
                "event_id": event.get("event_id"),
                "integration_id": "fedapay",
                "event_type": event_type,
                "payload": payload,
                "replayed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    else:
        await db.webhook_replay_log.insert_one(
            {
                "event_id": event.get("event_id"),
                "integration_id": integration or "unknown",
                "event_type": event_type,
                "replayed_at": datetime.now(timezone.utc).isoformat(),
            }
        )


# ═══════════════════════════════════════════════════════
# RETRY RULES CRUD + QUEUE MANAGEMENT
# ═══════════════════════════════════════════════════════

RULES_COL = "webhook_retry_rules"
QUEUE_COL = "webhook_retry_queue"


class RetryRuleBody(BaseModel):
    integration_id: str
    enabled: bool = True
    max_retries: int = 3
    backoff_strategy: str = "exponential"  # exponential, linear, fixed
    initial_delay_seconds: int = 60
    max_delay_seconds: int = 3600
    backoff_multiplier: float = 2.0
    retry_on_statuses: List[str] = ["failed", "error"]


# ── List Retry Rules ──
@router.get("/retry-rules")
async def list_retry_rules(request: Request):
    await _admin_guard(request)
    rules = await db[RULES_COL].find({}, {"_id": 0}).sort("integration_id", 1).to_list(50)
    return {"rules": rules}


# ── Create / Update Retry Rule ──
@router.post("/retry-rules")
async def upsert_retry_rule(request: Request, body: RetryRuleBody):
    user = await _admin_guard(request)

    if body.backoff_strategy not in ("exponential", "linear", "fixed"):
        raise HTTPException(status_code=400, detail="Invalid backoff_strategy. Use: exponential, linear, fixed")
    if body.max_retries < 1 or body.max_retries > 10:
        raise HTTPException(status_code=400, detail="max_retries must be 1-10")
    if body.initial_delay_seconds < 10:
        raise HTTPException(status_code=400, detail="initial_delay_seconds must be >= 10")

    now = datetime.now(timezone.utc).isoformat()
    doc = body.dict()
    doc["updated_at"] = now
    doc["updated_by"] = user.email

    existing = await db[RULES_COL].find_one({"integration_id": body.integration_id})
    if existing:
        await db[RULES_COL].update_one({"integration_id": body.integration_id}, {"$set": doc})
        action = "updated"
    else:
        doc["created_at"] = now
        doc["created_by"] = user.email
        await db[RULES_COL].insert_one(doc)
        action = "created"

    rule = await db[RULES_COL].find_one({"integration_id": body.integration_id}, {"_id": 0})
    return {"success": True, "action": action, "rule": rule}


# ── Delete Retry Rule ──
@router.delete("/retry-rules/{integration_id}")
async def delete_retry_rule(request: Request, integration_id: str):
    await _admin_guard(request)
    result = await db[RULES_COL].delete_one({"integration_id": integration_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"success": True, "deleted": integration_id}


# ── Retry Queue Status ──
@router.get("/retry-queue")
async def get_retry_queue(request: Request, status: Optional[str] = None, limit: int = 50):
    await _admin_guard(request)
    from routes.webhook_retry_engine import get_retry_queue_stats

    query: dict = {}
    if status:
        query["status"] = status
    items = await db[QUEUE_COL].find(query, {"_id": 0}).sort("next_retry_at", 1).limit(limit).to_list(limit)
    stats = await get_retry_queue_stats()
    return {"queue": items, "stats": stats}


# ── Manual Trigger: run retry cycle now ──
@router.post("/retry-queue/trigger")
async def trigger_retry_cycle(request: Request):
    await _admin_guard(request)
    from routes.webhook_retry_engine import run_retry_cycle

    await run_retry_cycle()
    from routes.webhook_retry_engine import get_retry_queue_stats

    stats = await get_retry_queue_stats()
    return {"success": True, "message": "Retry cycle triggered", "stats": stats}


# ── Clear exhausted queue items ──
@router.post("/retry-queue/clear")
async def clear_exhausted(request: Request):
    await _admin_guard(request)
    result = await db[QUEUE_COL].delete_many(
        {"status": {"$in": ["exhausted", "success", "not_found", "resolved_skip"]}}
    )
    return {"success": True, "cleared": result.deleted_count}
