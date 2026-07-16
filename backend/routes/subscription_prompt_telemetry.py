"""Telemetry endpoints for subscription upgrade prompt observability."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from routes.db import db, get_current_user, require_admin


router = APIRouter(tags=["Subscription Prompt Telemetry"])


REAL_USER_EXCLUDE_EMAIL_REGEX = r"(^e2e\.|^test\.|^qa\.|^dev\.|@example\.com$|@example\.org$|@localhost$|\.local$)"


def _conversion_base_query(*, since_iso: str, audience: str) -> dict[str, Any]:
    base_query: dict[str, Any] = {"created_at": {"$gte": since_iso}}
    if audience != "real_users_only":
        return base_query

    base_query["is_admin"] = {"$ne": True}
    base_query["user_email"] = {"$exists": True, "$type": "string", "$nin": [""]}
    base_query["$and"] = [
        {"user_email": {"$not": {"$regex": REAL_USER_EXCLUDE_EMAIL_REGEX, "$options": "i"}}},
        {
            "$or": [
                {"role": {"$exists": False}},
                {"role": {"$not": {"$regex": "admin", "$options": "i"}}},
            ]
        },
    ]
    return base_query


def _sanitize_non_finite_numbers(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize_non_finite_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_non_finite_numbers(v) for v in value]
    return value


class SubscriptionPromptTelemetryIn(BaseModel):
    session_key: str = Field(..., min_length=3, max_length=220)
    current_plan: str = Field(default="free", max_length=40)
    required_plan: str = Field(default="basic", max_length=40)
    source: str = Field(default="auto_api", max_length=80)
    endpoint: str | None = Field(default=None, max_length=300)
    route: str | None = Field(default=None, max_length=200)


class SubscriptionConversionTelemetryIn(BaseModel):
    session_key: str = Field(..., min_length=3, max_length=220)
    event_type: Literal["plan_card_view", "plan_cta_click", "subscribe_success"]
    plan_id: str | None = Field(default=None, max_length=80)
    billing_period: str | None = Field(default=None, max_length=20)
    role: str | None = Field(default=None, max_length=40)
    device_bucket: str | None = Field(default=None, max_length=40)
    route: str | None = Field(default=None, max_length=220)
    source: str | None = Field(default="subscription_plans", max_length=80)


@router.post("/subscription-prompt/telemetry")
async def ingest_subscription_prompt_telemetry(payload: SubscriptionPromptTelemetryIn, request: Request):
    user = await get_current_user(request)
    now_iso = datetime.now(timezone.utc).isoformat()

    doc: dict[str, Any] = {
        "session_key": str(payload.session_key)[:220],
        "user_id": getattr(user, "user_id", None),
        "user_email": getattr(user, "email", None),
        "current_plan": str(payload.current_plan or "free").lower()[:40],
        "required_plan": str(payload.required_plan or "basic").lower()[:40],
        "source": str(payload.source or "auto_api")[:80],
        "endpoint": (str(payload.endpoint)[:300] if payload.endpoint else None),
        "route": (str(payload.route)[:200] if payload.route else None),
        "created_at": now_iso,
    }

    await db.subscription_prompt_telemetry.insert_one(doc)
    return {"ok": True, "created_at": now_iso}


@router.get("/admin/subscription-prompt/telemetry")
async def get_subscription_prompt_telemetry(request: Request, hours: int = 24):
    await require_admin(request)
    safe_hours = max(1, min(int(hours), 24 * 14))
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=safe_hours)).isoformat()

    base_query = {"created_at": {"$gte": since_iso}}

    total_events = await db.subscription_prompt_telemetry.count_documents(base_query)

    by_plan_raw = await db.subscription_prompt_telemetry.aggregate(
        [
            {"$match": base_query},
            {"$group": {"_id": "$current_plan", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
    ).to_list(20)

    by_source_raw = await db.subscription_prompt_telemetry.aggregate(
        [
            {"$match": base_query},
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
    ).to_list(20)

    top_endpoints_raw = await db.subscription_prompt_telemetry.aggregate(
        [
            {"$match": base_query},
            {"$group": {"_id": "$endpoint", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 8},
        ]
    ).to_list(8)

    unique_sessions = await db.subscription_prompt_telemetry.distinct("session_key", base_query)

    latest = await db.subscription_prompt_telemetry.find(base_query, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)

    monitor_state = await db.subscription_prompt_telemetry_monitor_state.find_one(
        {"key": "subscription_prompt_telemetry_monitor"},
        {"_id": 0},
    )
    monitor_events = await db.subscription_prompt_telemetry_monitor_events.find(
        {},
        {"_id": 0},
    ).sort("created_at", -1).limit(10).to_list(10)

    monitor_state = _sanitize_non_finite_numbers(monitor_state)
    monitor_events = _sanitize_non_finite_numbers(monitor_events)

    return {
        "hours": safe_hours,
        "since_iso": since_iso,
        "total_events": int(total_events),
        "unique_sessions": len(unique_sessions),
        "by_plan": [{"plan": row.get("_id") or "unknown", "count": int(row.get("count") or 0)} for row in by_plan_raw],
        "by_source": [{"source": row.get("_id") or "unknown", "count": int(row.get("count") or 0)} for row in by_source_raw],
        "top_endpoints": [
            {"endpoint": row.get("_id") or "(none)", "count": int(row.get("count") or 0)} for row in top_endpoints_raw
        ],
        "latest_events": latest,
        "monitor_state": monitor_state,
        "monitor_recent_alerts": monitor_events,
    }


@router.post("/subscription-conversion/telemetry")
async def ingest_subscription_conversion_telemetry(payload: SubscriptionConversionTelemetryIn, request: Request):
    user = await get_current_user(request)
    now_iso = datetime.now(timezone.utc).isoformat()

    doc: dict[str, Any] = {
        "session_key": str(payload.session_key)[:220],
        "user_id": getattr(user, "user_id", None),
        "user_email": getattr(user, "email", None),
        "is_admin": bool(getattr(user, "is_admin", False)),
        "event_type": str(payload.event_type),
        "plan_id": (str(payload.plan_id).lower()[:80] if payload.plan_id else None),
        "billing_period": (str(payload.billing_period).lower()[:20] if payload.billing_period else None),
        "role": (str(payload.role).lower()[:40] if payload.role else None),
        "device_bucket": (str(payload.device_bucket).lower()[:40] if payload.device_bucket else None),
        "route": (str(payload.route)[:220] if payload.route else None),
        "source": (str(payload.source or "subscription_plans")[:80]),
        "created_at": now_iso,
    }

    await db.subscription_conversion_telemetry.insert_one(doc)
    return {"ok": True, "created_at": now_iso}


@router.get("/admin/subscription-conversion/summary")
async def get_subscription_conversion_summary(
    request: Request,
    hours: int = 24 * 7,
    audience: str = Query(default="all", pattern="^(all|real_users_only)$"),
):
    await require_admin(request)
    safe_hours = max(1, min(int(hours), 24 * 30))
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=safe_hours)).isoformat()

    base_query = _conversion_base_query(since_iso=since_iso, audience=str(audience or "all"))

    total_events = await db.subscription_conversion_telemetry.count_documents(base_query)

    event_counts_raw = await db.subscription_conversion_telemetry.aggregate(
        [
            {"$match": base_query},
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
    ).to_list(20)

    by_plan_raw = await db.subscription_conversion_telemetry.aggregate(
        [
            {"$match": base_query},
            {
                "$group": {
                    "_id": {"plan_id": "$plan_id", "event_type": "$event_type"},
                    "count": {"$sum": 1},
                }
            },
        ]
    ).to_list(200)

    by_role_raw = await db.subscription_conversion_telemetry.aggregate(
        [
            {"$match": base_query},
            {"$group": {"_id": {"role": "$role", "event_type": "$event_type"}, "count": {"$sum": 1}}},
        ]
    ).to_list(120)

    by_device_raw = await db.subscription_conversion_telemetry.aggregate(
        [
            {"$match": base_query},
            {
                "$group": {
                    "_id": {"device_bucket": "$device_bucket", "event_type": "$event_type"},
                    "count": {"$sum": 1},
                }
            },
        ]
    ).to_list(120)

    latest_events = await db.subscription_conversion_telemetry.find(
        base_query,
        {"_id": 0},
    ).sort("created_at", -1).limit(30).to_list(30)

    events_map = {str(row.get("_id") or "unknown"): int(row.get("count") or 0) for row in event_counts_raw}
    views = int(events_map.get("plan_card_view", 0))
    clicks = int(events_map.get("plan_cta_click", 0))
    success = int(events_map.get("subscribe_success", 0))

    def _rate(num: int, den: int) -> float:
        if den <= 0:
            return 0.0
        return round((num / den) * 100.0, 2)

    by_plan_map: dict[str, dict[str, int | float | str]] = {}
    for row in by_plan_raw:
        key = row.get("_id") or {}
        plan_id = str(key.get("plan_id") or "unknown")
        event_type = str(key.get("event_type") or "unknown")
        if plan_id not in by_plan_map:
            by_plan_map[plan_id] = {
                "plan_id": plan_id,
                "views": 0,
                "clicks": 0,
                "success": 0,
                "click_through_rate": 0.0,
                "checkout_success_rate": 0.0,
            }
        count = int(row.get("count") or 0)
        if event_type == "plan_card_view":
            by_plan_map[plan_id]["views"] = count
        elif event_type == "plan_cta_click":
            by_plan_map[plan_id]["clicks"] = count
        elif event_type == "subscribe_success":
            by_plan_map[plan_id]["success"] = count

    by_plan = []
    for row in by_plan_map.values():
        row["click_through_rate"] = _rate(int(row["clicks"]), int(row["views"]))
        row["checkout_success_rate"] = _rate(int(row["success"]), int(row["clicks"]))
        by_plan.append(row)
    by_plan.sort(key=lambda r: int(r.get("clicks") or 0), reverse=True)

    def _reshape_segment(raw_rows: list[dict[str, Any]], segment_key: str) -> list[dict[str, Any]]:
        bucket: dict[str, dict[str, int | str]] = {}
        for row in raw_rows:
            key = row.get("_id") or {}
            segment_value = str(key.get(segment_key) or "unknown")
            event_type = str(key.get("event_type") or "unknown")
            if segment_value not in bucket:
                bucket[segment_value] = {
                    segment_key: segment_value,
                    "plan_card_view": 0,
                    "plan_cta_click": 0,
                    "subscribe_success": 0,
                }
            bucket[segment_value][event_type] = int(row.get("count") or 0)
        out = list(bucket.values())
        out.sort(key=lambda item: int(item.get("plan_cta_click") or 0), reverse=True)
        return out

    return {
        "hours": safe_hours,
        "since_iso": since_iso,
        "audience": str(audience or "all"),
        "total_events": int(total_events),
        "funnel": {
            "plan_card_view": views,
            "plan_cta_click": clicks,
            "subscribe_success": success,
            "click_through_rate": _rate(clicks, views),
            "checkout_success_rate": _rate(success, clicks),
        },
        "event_counts": events_map,
        "by_plan": by_plan,
        "by_role": _reshape_segment(by_role_raw, "role"),
        "by_device_bucket": _reshape_segment(by_device_raw, "device_bucket"),
        "latest_events": latest_events,
    }
