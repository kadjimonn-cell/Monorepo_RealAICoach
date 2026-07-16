"""Admin pricing-mismatch alert routes extracted from payments.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from .db import db, require_admin
from .payments_pricing_guard import format_pricing_mismatch_event, pricing_mismatch_event_query


router = APIRouter()


@router.get("/admin/pricing-mismatch-alerts")
async def get_pricing_mismatch_alerts(
    request: Request,
    hours: int = Query(168, ge=1, le=8760),
    limit: int = Query(50, ge=1, le=500),
    only_open: bool = Query(False),
):
    await require_admin(request)
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    base_query: dict[str, Any] = {"created_at": {"$gte": since_iso}}
    events_query = dict(base_query)
    if only_open:
        events_query["status"] = {"$ne": "acknowledged"}

    projection = {
        "_id": 1,
        "alert_id": 1,
        "context": 1,
        "reason": 1,
        "plan_id": 1,
        "billing_period": 1,
        "expected_amount": 1,
        "actual_amount": 1,
        "payment_id": 1,
        "user_id": 1,
        "currency": 1,
        "status": 1,
        "created_at": 1,
        "acked_at": 1,
        "acked_by": 1,
    }
    rows = await db.pricing_mismatch_alert_events.find(events_query, projection).sort("created_at", -1).limit(limit).to_list(limit)
    total_recent = await db.pricing_mismatch_alert_events.count_documents(base_query)
    open_recent = await db.pricing_mismatch_alert_events.count_documents({**base_query, "status": {"$ne": "acknowledged"}})
    acknowledged_recent = await db.pricing_mismatch_alert_events.count_documents({**base_query, "status": "acknowledged"})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": hours,
        "limit": limit,
        "only_open": only_open,
        "summary": {
            "total_recent": int(total_recent),
            "open_recent": int(open_recent),
            "acknowledged_recent": int(acknowledged_recent),
        },
        "events": [format_pricing_mismatch_event(row) for row in rows],
    }


@router.post("/admin/pricing-mismatch-alerts/{event_id}/ack")
async def acknowledge_pricing_mismatch_alert(event_id: str, request: Request):
    admin = await require_admin(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    event_query = pricing_mismatch_event_query(event_id)

    existing = await db.pricing_mismatch_alert_events.find_one(
        event_query,
        {"_id": 1, "alert_id": 1, "status": 1, "acked_at": 1},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Pricing mismatch alert event not found")

    status_now = str(existing.get("status") or "").strip().lower()
    if status_now != "acknowledged":
        await db.pricing_mismatch_alert_events.update_one(
            {"_id": existing.get("_id")},
            {
                "$set": {
                    "status": "acknowledged",
                    "acked_at": now_iso,
                    "acked_by": getattr(admin, "user_id", ""),
                }
            },
        )

    resolved_id = str(existing.get("alert_id") or existing.get("_id") or "")
    return {
        "success": True,
        "event_id": resolved_id,
        "status": "acknowledged",
        "acked_at": now_iso,
    }


@router.post("/admin/pricing-mismatch-alerts/ack-all")
async def acknowledge_all_pricing_mismatch_alerts(
    request: Request,
    hours: int = Query(720, ge=1, le=8760),
):
    admin = await require_admin(request)
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    query = {
        "created_at": {"$gte": since_iso},
        "status": {"$ne": "acknowledged"},
    }
    result = await db.pricing_mismatch_alert_events.update_many(
        query,
        {
            "$set": {
                "status": "acknowledged",
                "acked_at": now_iso,
                "acked_by": getattr(admin, "user_id", ""),
            }
        },
    )

    return {
        "success": True,
        "window_hours": hours,
        "matched_count": int(result.matched_count),
        "modified_count": int(result.modified_count),
        "acked_at": now_iso,
    }


@router.post("/admin/pricing-mismatch-alerts/clear")
async def clear_pricing_mismatch_alerts(
    request: Request,
    scope: str = Query("acked", regex="^(acked|all)$"),
    hours: int = Query(720, ge=1, le=8760),
):
    await require_admin(request)
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query: dict[str, Any] = {"created_at": {"$gte": since_iso}}
    if scope == "acked":
        query["status"] = "acknowledged"

    result = await db.pricing_mismatch_alert_events.delete_many(query)
    return {
        "success": True,
        "scope": scope,
        "window_hours": hours,
        "deleted_count": int(result.deleted_count),
    }