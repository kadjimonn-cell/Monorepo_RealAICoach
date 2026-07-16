"""Advanced Analytics Reporting — Export analytics as CSV/PDF with date filters.

User-facing reporting endpoints:
  - Generate on-demand CSV/PDF reports
  - Schedule automated report delivery via email
  - View report generation history
"""

import csv
import io
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from routes.db import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])


class ScheduleReportRequest(BaseModel):
    report_type: str  # "usage", "conversations", "features", "subscription"
    frequency: str  # "weekly", "monthly"
    email: Optional[str] = None


REPORT_TYPES = {
    "usage": {"name": "Usage Summary", "description": "Daily AI usage, conversations, exports"},
    "conversations": {"name": "Conversation History", "description": "All AI coaching conversations with timestamps"},
    "features": {"name": "Feature Usage", "description": "Which features you've used and how often"},
    "subscription": {"name": "Subscription & Billing", "description": "Payment history, plan changes, renewal dates"},
}


async def _gather_usage_data(user_id: str, start_date: str, end_date: str):
    """Gather usage analytics data for CSV export."""
    rows = []
    # Get progress/usage data
    progress_docs = await db.progress.find(
        {"user_id": user_id}, {"_id": 0}
    ).to_list(100)

    for doc in progress_docs:
        rows.append({
            "Date": doc.get("last_conversation_date", "N/A"),
            "Daily Conversations": doc.get("daily_conversations", 0),
            "Total Conversations": doc.get("total_conversations", 0),
            "Streak Days": doc.get("streak", 0),
            "Topics Explored": doc.get("topics_explored", 0),
        })

    if not rows:
        rows.append({
            "Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "Daily Conversations": 0,
            "Total Conversations": 0,
            "Streak Days": 0,
            "Topics Explored": 0,
        })
    return rows


async def _gather_conversation_data(user_id: str, start_date: str, end_date: str):
    """Gather conversation history for CSV export."""
    convos = await db.conversations.find(
        {
            "user_id": user_id,
            "created_at": {"$gte": start_date, "$lte": end_date},
        },
        {"_id": 0, "conversation_id": 1, "topic": 1, "created_at": 1, "message_count": 1, "status": 1},
    ).sort("created_at", -1).to_list(500)

    rows = []
    for c in convos:
        rows.append({
            "Conversation ID": c.get("conversation_id", ""),
            "Topic": c.get("topic", "General"),
            "Messages": c.get("message_count", 0),
            "Status": c.get("status", "active"),
            "Date": c.get("created_at", "")[:10],
        })

    if not rows:
        rows.append({"Conversation ID": "No conversations in this period", "Topic": "", "Messages": 0, "Status": "", "Date": ""})
    return rows


async def _gather_feature_data(user_id: str, start_date: str, end_date: str):
    """Gather feature usage data for CSV export."""
    actions = await db.user_actions.find(
        {
            "user_id": user_id,
            "timestamp": {"$gte": start_date, "$lte": end_date},
        },
        {"_id": 0},
    ).sort("timestamp", -1).to_list(1000)

    # Aggregate by feature
    feature_counts = {}
    for a in actions:
        feat = a.get("feature_key", a.get("action", "unknown"))
        feature_counts[feat] = feature_counts.get(feat, 0) + 1

    rows = [{"Feature": k, "Usage Count": v} for k, v in sorted(feature_counts.items(), key=lambda x: -x[1])]
    if not rows:
        rows.append({"Feature": "No feature usage in this period", "Usage Count": 0})
    return rows


async def _gather_subscription_data(user_id: str, start_date: str, end_date: str):
    """Gather subscription and billing data for CSV export."""
    payments = await db.payment_transactions.find(
        {
            "user_id": user_id,
            "created_at": {"$gte": start_date, "$lte": end_date},
        },
        {"_id": 0, "payment_id": 1, "plan_id": 1, "amount_usd": 1, "status": 1, "payment_method": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(100)

    rows = []
    for p in payments:
        rows.append({
            "Payment ID": p.get("payment_id", ""),
            "Plan": p.get("plan_id", "").title(),
            "Amount (USD)": f"${p.get('amount_usd', 0):.2f}",
            "Status": p.get("status", ""),
            "Method": p.get("payment_method", ""),
            "Date": p.get("created_at", "")[:10],
        })

    if not rows:
        rows.append({"Payment ID": "No payments in this period", "Plan": "", "Amount (USD)": "", "Status": "", "Method": "", "Date": ""})
    return rows


GATHERERS = {
    "usage": _gather_usage_data,
    "conversations": _gather_conversation_data,
    "features": _gather_feature_data,
    "subscription": _gather_subscription_data,
}


@router.get("/types")
async def get_report_types():
    """Return available report types."""
    return {"report_types": REPORT_TYPES}


@router.get("/export/{report_type}")
async def export_report_csv(
    report_type: str,
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Export a report as CSV with optional date range."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid report type. Valid: {list(REPORT_TYPES.keys())}")

    now = datetime.now(timezone.utc)
    if not start_date:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")

    gatherer = GATHERERS[report_type]
    rows = await gatherer(user.user_id, start_date, end_date)

    # Generate CSV
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    # Log the export
    await db.report_exports.insert_one({
        "export_id": f"rpt_{uuid.uuid4().hex[:12]}",
        "user_id": user.user_id,
        "report_type": report_type,
        "format": "csv",
        "start_date": start_date,
        "end_date": end_date,
        "rows": len(rows),
        "created_at": now.isoformat(),
    })

    filename = f"realaicoach_{report_type}_{start_date}_to_{end_date}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/{report_type}/json")
async def export_report_json(
    report_type: str,
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Export a report as JSON (for frontend rendering)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid report type.")

    now = datetime.now(timezone.utc)
    if not start_date:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")

    gatherer = GATHERERS[report_type]
    rows = await gatherer(user.user_id, start_date, end_date)

    return {
        "report_type": report_type,
        "report_name": REPORT_TYPES[report_type]["name"],
        "start_date": start_date,
        "end_date": end_date,
        "rows": rows,
        "row_count": len(rows),
        "generated_at": now.isoformat(),
    }


@router.post("/schedule")
async def schedule_report(req: ScheduleReportRequest, request: Request):
    """Schedule automated report delivery via email."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if req.report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid report type")
    if req.frequency not in ("weekly", "monthly"):
        raise HTTPException(status_code=400, detail="Frequency must be 'weekly' or 'monthly'")

    email = req.email or user.email
    schedule_id = f"sched_{uuid.uuid4().hex[:12]}"

    await db.scheduled_reports.update_one(
        {"user_id": user.user_id, "report_type": req.report_type},
        {"$set": {
            "schedule_id": schedule_id,
            "user_id": user.user_id,
            "report_type": req.report_type,
            "frequency": req.frequency,
            "email": email,
            "active": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    return {
        "success": True,
        "schedule_id": schedule_id,
        "message": f"{REPORT_TYPES[req.report_type]['name']} will be emailed {req.frequency} to {email}",
    }


@router.get("/schedules")
async def get_scheduled_reports(request: Request):
    """Get user's scheduled report deliveries."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    schedules = await db.scheduled_reports.find(
        {"user_id": user.user_id, "active": True}, {"_id": 0}
    ).to_list(20)
    return {"schedules": schedules}


@router.delete("/schedule/{report_type}")
async def cancel_scheduled_report(report_type: str, request: Request):
    """Cancel a scheduled report delivery."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.scheduled_reports.update_one(
        {"user_id": user.user_id, "report_type": report_type},
        {"$set": {"active": False}},
    )
    return {"success": True}


@router.get("/history")
async def get_export_history(request: Request, limit: int = 20):
    """Get user's report export history."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    exports = await db.report_exports.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"exports": exports}
