"""Live Activity Feed — Real-time admin activity tracking and WebSocket streaming.

Tracks user logins, feature usage, page views, completions, and system events.
Broadcasts events via WebSocket to admin dashboards in real-time.
"""

from fastapi import APIRouter, Request, Depends
from datetime import datetime, timezone
from typing import Optional
import logging
from utils.pdf_v15_filename import build_pdf_v15_filename

logger = logging.getLogger("routes.live_activity")

router = APIRouter(prefix="/api/admin/live-activity", tags=["Live Activity Feed"])


async def _get_db():
    from routes.db import db
    return db


async def _require_admin(request: Request):
    from routes.auth import get_current_user
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin only")
    return user


ACTIVITY_COLLECTION = "live_activity_events"


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise RuntimeError(f"pdf-v15-enterprise-enforcement-failed:{context}:{mode}")
    return themed


async def log_activity(db, event_type: str, user_id: str = "", user_email: str = "",
                       detail: str = "", metadata: dict = None):
    """Log an activity event and broadcast to admin WebSocket listeners."""
    event = {
        "event_type": event_type,
        "user_id": user_id,
        "user_email": user_email,
        "detail": detail,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db[ACTIVITY_COLLECTION].insert_one(event)
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

    # Broadcast to admin activity WebSocket listeners
    try:
        from utils.ws_manager import ws_manager
        broadcast_event = {k: v for k, v in event.items() if k != "_id"}
        await ws_manager.broadcast_admin_activity(broadcast_event)
    except Exception as e:
        logger.debug(f"Activity broadcast skipped: {e}")


@router.get("/feed")
async def get_activity_feed(
    limit: int = 50,
    offset: int = 0,
    event_type: Optional[str] = None,
    admin=Depends(_require_admin),
    db=Depends(_get_db),
):
    """Get recent activity feed with pagination and optional type filter."""
    query = {}
    if event_type:
        query["event_type"] = event_type

    total = await db[ACTIVITY_COLLECTION].count_documents(query)
    cursor = db[ACTIVITY_COLLECTION].find(query, {"_id": 0}).sort("timestamp", -1).skip(offset).limit(limit)
    events = await cursor.to_list(length=limit)

    # Get event type counts for the last 24h
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    type_counts = {}
    async for doc in db[ACTIVITY_COLLECTION].aggregate(pipeline):
        type_counts[doc["_id"]] = doc["count"]

    return {
        "events": events,
        "total": total,
        "type_counts": type_counts,
        "event_types": [
            "login", "logout", "feature_usage", "page_view",
            "completion", "error", "upgrade", "api_call", "admin_action",
        ],
    }


@router.post("/log-event")
async def log_event_from_client(
    request: Request,
    db=Depends(_get_db),
):
    """Log an activity event from the frontend. Any authenticated user can log."""
    from routes.auth import get_current_user
    user = await get_current_user(request)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    await log_activity(
        db,
        event_type=body.get("event_type", "page_view"),
        user_id=getattr(user, "user_id", ""),
        user_email=getattr(user, "email", ""),
        detail=body.get("detail", ""),
        metadata=body.get("metadata", {}),
    )
    return {"ok": True}


@router.get("/stats")
async def get_activity_stats(
    admin=Depends(_require_admin),
    db=Depends(_get_db),
):
    """Get activity statistics for the dashboard."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_1h = (now - timedelta(hours=1)).isoformat()

    total_24h = await db[ACTIVITY_COLLECTION].count_documents({"timestamp": {"$gte": cutoff_24h}})
    total_1h = await db[ACTIVITY_COLLECTION].count_documents({"timestamp": {"$gte": cutoff_1h}})

    # Unique users in last 24h
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff_24h}, "user_id": {"$ne": ""}}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "unique_users"},
    ]
    unique_result = await db[ACTIVITY_COLLECTION].aggregate(pipeline).to_list(1)
    unique_users = unique_result[0]["unique_users"] if unique_result else 0

    # Hourly breakdown (last 24 hours)
    hourly_pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff_24h}}},
        {"$addFields": {"hour": {"$substr": ["$timestamp", 11, 2]}}},
        {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    hourly = {}
    async for doc in db[ACTIVITY_COLLECTION].aggregate(hourly_pipeline):
        hourly[doc["_id"]] = doc["count"]

    return {
        "events_24h": total_24h,
        "events_1h": total_1h,
        "unique_users_24h": unique_users,
        "events_per_hour": hourly,
    }


@router.get("/export/{fmt}")
@router.get("/export")
async def export_activity_feed(
    request: Request,
    fmt: str = "csv",
    export_format: str = "csv",
    event_type: Optional[str] = None,
    hours: int = 24,
    admin=Depends(_require_admin),
    db=Depends(_get_db),
):
    """Export activity feed as CSV, PDF or JSON. Admin only."""
    from datetime import timedelta
    from fastapi.responses import Response
    # Use path param first, then query param fallback
    actual_format = fmt if fmt != "csv" else (export_format if export_format != "csv" else (request.query_params.get("format") or "csv"))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query: dict = {"timestamp": {"$gte": cutoff}}
    if event_type:
        query["event_type"] = event_type

    cursor = db[ACTIVITY_COLLECTION].find(query, {"_id": 0}).sort("timestamp", -1)
    events = await cursor.to_list(length=5000)

    if actual_format == "json":
        import json
        content = json.dumps(events, indent=2, default=str)
        return Response(content=content, media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=activity_feed.json"})

    if actual_format == "pdf":
        return _generate_pdf_export(events, event_type, hours)

    # CSV export (default)
    import io
    import csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "event_type", "user_email", "detail", "user_id"])
    for e in events:
        writer.writerow([e.get("timestamp", ""), e.get("event_type", ""), e.get("user_email", ""),
                         e.get("detail", ""), e.get("user_id", "")])
    csv_content = output.getvalue()
    return Response(content=csv_content, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=activity_feed.csv",
                             "Cache-Control": "no-cache, no-store, must-revalidate"})


def _sanitize_text(text: str) -> str:
    """Replace unicode characters that FPDF Helvetica can't handle."""
    replacements = {'—': '-', '–': '-', '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u00a0': ' '}
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', 'replace').decode('latin-1')


def _generate_pdf_export(events: list, event_type: str = None, hours: int = 24):
    """Generate a PDF report of activity feed events."""
    from fastapi.responses import Response
    from fpdf import FPDF
    import io
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "RealAICoach Activity Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    filter_text = f"Event Type: {event_type}" if event_type else "All Events"
    pdf.cell(0, 6, _sanitize_text(f"{filter_text} | Last {hours} hours | {len(events)} events"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Table header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(249, 250, 251)
    col_widths = [38, 25, 50, 77]
    headers = ["Timestamp", "Type", "User", "Detail"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, fill=True)
    pdf.ln()

    # Table rows
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(0, 0, 0)
    for e in events[:500]:
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        etype = _sanitize_text(e.get("event_type", "")[:12])
        email = _sanitize_text(e.get("user_email", "")[:25])
        detail = _sanitize_text(e.get("detail", "")[:45])
        pdf.cell(col_widths[0], 6, ts, border=1)
        pdf.cell(col_widths[1], 6, etype, border=1)
        pdf.cell(col_widths[2], 6, email, border=1)
        pdf.cell(col_widths[3], 6, detail, border=1)
        pdf.ln()

    buf = io.BytesIO()
    pdf.output(buf)
    composed_pdf = compose_pdf_v15_helper_layout(
        buf.getvalue(),
        title="Activity Feed Report",
        subtitle="Live operations telemetry export",
        right_primary=f"Events: {len(events)}",
        right_secondary=f"Window: {hours}h",
        badge_text="LIVE ACTIVITY OPERATIONS",
        badge_status="INFO",
        footer_text="RealAICoach Live Activity • Enterprise profile",
        summary_title="Filters",
        summary_rows=[
            ("Event Type", event_type or "All"),
            ("Hours", str(hours)),
            ("Rows", str(min(len(events), 500))),
        ],
        callout_title="Feed Coverage",
        callout_subtitle="Export fidelity",
        callout_detail="This report contains the latest normalized activity feed entries for admin review.",
        callout_status="INFO",
    )
    enforced_pdf = _enforce_pdf_v15_enterprise(composed_pdf, "live_activity_export")
    return Response(content=enforced_pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("activity-feed", "admin")}"',
                             "Cache-Control": "no-cache, no-store, must-revalidate"})


@router.get("/alerts")
async def get_activity_alerts(
    admin=Depends(_require_admin),
    db=Depends(_get_db),
):
    """Get critical activity alerts for admin push notifications."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff_1h = (now - timedelta(hours=1)).isoformat()
    cutoff_5m = (now - timedelta(minutes=5)).isoformat()

    # Error spike detection
    error_count_1h = await db[ACTIVITY_COLLECTION].count_documents(
        {"event_type": "error", "timestamp": {"$gte": cutoff_1h}}
    )
    error_count_5m = await db[ACTIVITY_COLLECTION].count_documents(
        {"event_type": "error", "timestamp": {"$gte": cutoff_5m}}
    )

    # Login spike (unusual activity)
    login_count_5m = await db[ACTIVITY_COLLECTION].count_documents(
        {"event_type": "login", "timestamp": {"$gte": cutoff_5m}}
    )

    # Total events last hour for rate calculation
    total_1h = await db[ACTIVITY_COLLECTION].count_documents({"timestamp": {"$gte": cutoff_1h}})

    alerts = []
    if error_count_5m >= 5:
        alerts.append({"level": "critical", "type": "error_spike",
                       "message": f"{error_count_5m} errors in last 5 minutes",
                       "timestamp": now.isoformat()})
    if error_count_1h >= 10:
        alerts.append({"level": "warning", "type": "error_elevated",
                       "message": f"{error_count_1h} errors in last hour",
                       "timestamp": now.isoformat()})
    if login_count_5m >= 20:
        alerts.append({"level": "info", "type": "login_spike",
                       "message": f"{login_count_5m} logins in last 5 minutes — possible surge",
                       "timestamp": now.isoformat()})

    return {
        "alerts": alerts,
        "metrics": {
            "errors_1h": error_count_1h,
            "errors_5m": error_count_5m,
            "logins_5m": login_count_5m,
            "total_1h": total_1h,
        },
    }


@router.get("/summary")
async def get_activity_summary(
    admin=Depends(_require_admin),
    db=Depends(_get_db),
):
    """Get executive summary of activity for dashboard widget."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_prev_24h = (now - timedelta(hours=48)).isoformat()

    # Current period
    current_total = await db[ACTIVITY_COLLECTION].count_documents({"timestamp": {"$gte": cutoff_24h}})

    # Previous period for comparison
    prev_total = await db[ACTIVITY_COLLECTION].count_documents({
        "timestamp": {"$gte": cutoff_prev_24h, "$lt": cutoff_24h}
    })

    # Top event types
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff_24h}}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    top_types = []
    async for doc in db[ACTIVITY_COLLECTION].aggregate(pipeline):
        top_types.append({"type": doc["_id"], "count": doc["count"]})

    # Most active users
    user_pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff_24h}, "user_email": {"$ne": ""}}},
        {"$group": {"_id": "$user_email", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    active_users = []
    async for doc in db[ACTIVITY_COLLECTION].aggregate(user_pipeline):
        active_users.append({"email": doc["_id"], "count": doc["count"]})

    # Recent events
    recent = await db[ACTIVITY_COLLECTION].find({}, {"_id": 0}).sort("timestamp", -1).to_list(5)

    # Trend
    change_pct = ((current_total - prev_total) / max(prev_total, 1)) * 100

    return {
        "current_total": current_total,
        "previous_total": prev_total,
        "change_percent": round(change_pct, 1),
        "trend": "up" if change_pct > 5 else "down" if change_pct < -5 else "stable",
        "top_event_types": top_types,
        "most_active_users": active_users,
        "recent_events": recent,
    }
