"""Client-side crash/error reporter.

Receives `componentDidCatch` payloads from the React ErrorBoundary so we can
rank the noisiest admin panels in the Operations Console (top N in last 24h).

Intentionally unauthenticated on ingest — any anon browser can POST a crash
before we know who they are. We strictly bound payload size / string length
and drop anything that looks like a bot probe.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from observability.request_context import extract_request_observability_context
from routes.db import db, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MSG_LEN = 1024
MAX_STACK_LEN = 8192
MAX_PANEL_LEN = 120
COLLECTION = "client_errors"


def _trim(val: Optional[str], limit: int) -> str:
    if not val:
        return ""
    s = str(val)
    return s[:limit]


class ClientErrorReport(BaseModel):
    panel_id: Optional[str] = Field(default=None, description="Stable panel tab id, e.g. 'webhook-replay'")
    panel_name: Optional[str] = Field(default=None, description="Human-readable panel label")
    message: str = Field(..., description="Error.message")
    stack: Optional[str] = Field(default=None, description="Error.stack (best-effort)")
    component_stack: Optional[str] = Field(default=None, description="React componentStack from ErrorInfo")
    pathname: Optional[str] = Field(default=None, description="window.location.pathname at crash time")
    user_agent: Optional[str] = Field(default=None)
    release: Optional[str] = Field(default=None, description="Client build id if available")
    client_id: Optional[str] = Field(default=None)


@router.post("/errors/client")
async def ingest_client_error(payload: ClientErrorReport, request: Request):
    """Best-effort client crash ingest. Never raises 5xx on bad payloads."""
    msg = _trim(payload.message, MAX_MSG_LEN).strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message is required")

    obs_ctx = extract_request_observability_context(request)

    doc: dict[str, Any] = {
        "error_id": f"err_{uuid.uuid4().hex[:12]}",
        "panel_id": _trim(payload.panel_id, MAX_PANEL_LEN) or "unknown",
        "panel_name": _trim(payload.panel_name, MAX_PANEL_LEN) or "",
        "message": msg,
        "stack": _trim(payload.stack, MAX_STACK_LEN),
        "component_stack": _trim(payload.component_stack, MAX_STACK_LEN),
        "pathname": _trim(payload.pathname, 512),
        "user_agent": _trim(payload.user_agent, 512),
        "release": _trim(payload.release, 64),
        "client_id": _trim(payload.client_id, 64),
        "ip": (request.client.host if request.client else "unknown"),
        "correlation_id": str(getattr(request.state, "correlation_id", "") or obs_ctx.get("correlation_id") or ""),
        "trace_id": str(getattr(request.state, "trace_id", "") or obs_ctx.get("trace_id") or ""),
        "span_id": str(getattr(request.state, "span_id", "") or obs_ctx.get("span_id") or ""),
        "session_id": str(getattr(request.state, "session_id", "") or obs_ctx.get("session_id") or ""),
        "created_at": datetime.now(timezone.utc),
    }

    try:
        await db[COLLECTION].insert_one(doc)
    except Exception as exc:  # pragma: no cover — mongo down should not 500 the client
        logger.warning("client_errors.insert_failed", extra={"error": str(exc)})
        return {"ok": False, "stored": False}

    return {"ok": True, "stored": True, "error_id": doc["error_id"]}


@router.get("/errors/client/top")
async def top_broken_panels(request: Request, hours: int = 24, limit: int = 5):
    """Admin-only: top N panels by crash count in the last `hours` window."""
    await require_admin(request)

    hours = max(1, min(int(hours or 24), 168))  # clamp 1h..7d
    limit = max(1, min(int(limit or 5), 25))

    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {
            "$addFields": {
                "panel_key": {
                    "$cond": [
                        {"$or": [{"$eq": ["$panel_id", "unknown"]}, {"$eq": ["$panel_id", ""]}]},
                        {
                            "$concat": [
                                "route:",
                                {
                                    "$cond": [
                                        {"$or": [{"$eq": ["$pathname", None]}, {"$eq": ["$pathname", ""]}]},
                                        "unknown",
                                        "$pathname",
                                    ]
                                },
                            ]
                        },
                        "$panel_id",
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": "$panel_key",
                "count": {"$sum": 1},
                "panel_name": {"$last": "$panel_name"},
                "last_message": {"$last": "$message"},
                "last_seen": {"$max": "$created_at"},
                "first_seen": {"$min": "$created_at"},
                "unique_clients": {"$addToSet": "$client_id"},
                "last_pathname": {"$last": "$pathname"},
                "last_release": {"$last": "$release"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]

    items: list[dict[str, Any]] = []
    try:
        async for row in db[COLLECTION].aggregate(pipeline):
            items.append(
                {
                    "panel_id": row.get("_id") or "unknown",
                    "panel_name": row.get("panel_name") or "",
                    "count": int(row.get("count") or 0),
                    "last_message": row.get("last_message") or "",
                    "last_seen": (row.get("last_seen").isoformat() if row.get("last_seen") else None),
                    "first_seen": (row.get("first_seen").isoformat() if row.get("first_seen") else None),
                    "unique_clients": len([c for c in (row.get("unique_clients") or []) if c]),
                    "pathname": row.get("last_pathname") or "",
                    "release": row.get("last_release") or "",
                }
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("client_errors.top_aggregate_failed", extra={"error": str(exc)})

    total = 0
    try:
        total = await db[COLLECTION].count_documents({"created_at": {"$gte": since}})
    except Exception:
        total = sum(i["count"] for i in items)

    return {
        "window_hours": hours,
        "total_errors": total,
        "top": items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }



@router.post("/admin/health-digest/trigger")
async def trigger_admin_health_digest(request: Request):
    """Admin-only: run the daily admin health digest on demand.

    Useful for verifying Slack/Teams payload rendering without waiting
    for the 8 AM UTC cron, and for ops to kick a fresh morning ping
    right after deploying a fix.
    """
    await require_admin(request)
    from services.admin_health_digest import run_admin_health_digest

    record = await run_admin_health_digest()
    # Strip any Mongo-y keys that could have sneaked back in.
    record.pop("_id", None)
    return {"ok": True, "digest": record}


@router.get("/admin/health-digest/history")
async def admin_health_digest_history(request: Request, days: int = 7, limit: int = 30):
    """Return the last N days of admin-health digest log entries.

    Used by the in-console "7-day digest history" widget so the morning
    email and the live admin view tell the same story.
    """
    await require_admin(request)
    from datetime import datetime, timedelta, timezone
    from routes.db import db as _db

    days = max(1, min(days, 30))
    limit = max(1, min(limit, 60))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows: list[dict] = []
    try:
        cursor = _db.admin_health_digest_log.find(
            {"generated_at": {"$gte": since}},
            {
                "_id": 0,
                "generated_at": 1,
                "severity": 1,
                "title": 1,
                "summary": 1,
                "total_errors_24h": 1,
                "healthy_routes": 1,
                "total_routes": 1,
                "unhealthy_routes": 1,
                "top_panels": 1,
                "dispatched": 1,
                "email_sent": 1,
                "theme_audit": 1,
            },
        ).sort("generated_at", -1).limit(limit)
        async for doc in cursor:
            # Guard against ObjectId refs inside nested lists.
            doc.pop("_id", None)
            rows.append(doc)
    except Exception as exc:
        logger.warning(f"[health-digest] history query failed: {exc}")

    return {
        "days": days,
        "count": len(rows),
        "history": rows,
    }

