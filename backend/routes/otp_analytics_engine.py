"""Enterprise OTP Delivery Tracking & Analytics Engine.

Provides real-time monitoring of OTP email delivery: success/failure rates,
latency tracking, trend analysis, and per-recipient audit logs.
Data sources: db.otp_logs (generation events) and db.email_logs (delivery events).
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Query
import re
from routes.db import db

logger = logging.getLogger("routes.otp_analytics_engine")
router = APIRouter(prefix="/otp-analytics", tags=["OTP Analytics"])


async def _get_webhook_stats(cutoff: str) -> dict:
    """Get Resend webhook delivery confirmation stats for the given window."""
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$internal_status", "count": {"$sum": 1}}},
    ]
    breakdown = {}
    async for doc in db.email_delivery_events.aggregate(pipeline):
        breakdown[doc["_id"]] = doc["count"]
    total = sum(breakdown.values())
    delivered = breakdown.get("delivered", 0)
    bounced = breakdown.get("bounced", 0)
    opened = breakdown.get("opened", 0)
    return {
        "total_events": total,
        "confirmed_delivered": delivered,
        "bounced": bounced,
        "opened": opened,
        "complained": breakdown.get("complained", 0),
        "delivery_confirmation_rate": round((delivered / max(total, 1)) * 100, 1),
        "open_rate": round((opened / max(delivered, 1)) * 100, 1),
        "bounce_rate": round((bounced / max(total, 1)) * 100, 1),
        "breakdown": breakdown,
    }


@router.get("/stats")
async def get_otp_stats(days: int = Query(default=30, ge=1, le=365)):
    """Aggregate OTP delivery statistics over the given window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    pipeline_otp = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }
        },
    ]
    otp_status = {}
    async for doc in db.otp_logs.aggregate(pipeline_otp):
        otp_status[doc["_id"]] = doc["count"]

    pipeline_email = [
        {"$match": {"email_type": "otp", "created_at": {"$gte": cutoff}}},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }
        },
    ]
    email_status = {}
    async for doc in db.email_logs.aggregate(pipeline_email):
        email_status[doc["_id"]] = doc["count"]

    total_generated = sum(otp_status.values())
    total_sent = email_status.get("sent", 0)
    total_failed = email_status.get("failed", 0)
    total_rate_limited = email_status.get("rate_limited", 0)
    delivery_rate = round((total_sent / max(total_generated, 1)) * 100, 1)

    # Purpose breakdown
    purpose_pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$purpose", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    purposes = {}
    async for doc in db.otp_logs.aggregate(purpose_pipeline):
        purposes[doc["_id"] or "unknown"] = doc["count"]

    # Unique recipients
    unique_recipients = await db.email_logs.distinct("email", {"email_type": "otp", "created_at": {"$gte": cutoff}})

    return {
        "window_days": days,
        "total_generated": total_generated,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total_rate_limited": total_rate_limited,
        "delivery_rate": delivery_rate,
        "unique_recipients": len(unique_recipients),
        "otp_status_breakdown": otp_status,
        "email_status_breakdown": email_status,
        "purpose_breakdown": purposes,
        "webhook_tracking": await _get_webhook_stats(cutoff),
    }


@router.get("/trends")
async def get_otp_trends(days: int = Query(default=14, ge=1, le=90)):
    """Daily OTP volume and success/failure trend data for charting."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Build date-keyed results
    results = {}
    for i in range(days):
        d = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        results[d] = {"date": d, "generated": 0, "sent": 0, "failed": 0, "rate_limited": 0}

    # OTP generation counts per day
    async for doc in db.otp_logs.find({"created_at": {"$gte": cutoff}}, {"_id": 0, "created_at": 1}):
        day = doc["created_at"][:10]
        if day in results:
            results[day]["generated"] += 1

    # Email delivery counts per day
    async for doc in db.email_logs.find(
        {"email_type": "otp", "created_at": {"$gte": cutoff}},
        {"_id": 0, "created_at": 1, "status": 1},
    ):
        day = doc["created_at"][:10]
        if day in results:
            st = doc.get("status", "")
            if st == "sent":
                results[day]["sent"] += 1
            elif st == "failed":
                results[day]["failed"] += 1
            elif st == "rate_limited":
                results[day]["rate_limited"] += 1

    return {"days": days, "trends": list(results.values())}


@router.get("/logs")
async def get_otp_logs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
):
    """Paginated OTP email delivery logs with optional filtering."""
    query: dict = {"email_type": "otp"}
    if status:
        query["status"] = status
    if email:
        query["email"] = {"$regex": re.escape(str(email)), "$options": "i"}

    total = await db.email_logs.count_documents(query)
    skip = (page - 1) * limit
    logs = []
    cursor = db.email_logs.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    async for doc in cursor:
        logs.append(doc)

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, -(-total // limit)),
    }


@router.get("/health")
async def get_otp_health():
    """Real-time OTP system health: recent success rate, last failure, avg gap."""
    now = datetime.now(timezone.utc)
    one_hour = (now - timedelta(hours=1)).isoformat()
    six_hours = (now - timedelta(hours=6)).isoformat()
    twenty_four_hours = (now - timedelta(hours=24)).isoformat()

    # Last 1h stats
    h1_sent = await db.email_logs.count_documents(
        {"email_type": "otp", "status": "sent", "created_at": {"$gte": one_hour}}
    )
    h1_failed = await db.email_logs.count_documents(
        {"email_type": "otp", "status": "failed", "created_at": {"$gte": one_hour}}
    )
    h1_total = h1_sent + h1_failed
    h1_rate = round((h1_sent / max(h1_total, 1)) * 100, 1)

    # Last 6h stats
    h6_sent = await db.email_logs.count_documents(
        {"email_type": "otp", "status": "sent", "created_at": {"$gte": six_hours}}
    )
    h6_failed = await db.email_logs.count_documents(
        {"email_type": "otp", "status": "failed", "created_at": {"$gte": six_hours}}
    )
    h6_total = h6_sent + h6_failed
    h6_rate = round((h6_sent / max(h6_total, 1)) * 100, 1)

    # Last 24h stats
    h24_sent = await db.email_logs.count_documents(
        {"email_type": "otp", "status": "sent", "created_at": {"$gte": twenty_four_hours}}
    )
    h24_failed = await db.email_logs.count_documents(
        {"email_type": "otp", "status": "failed", "created_at": {"$gte": twenty_four_hours}}
    )
    h24_total = h24_sent + h24_failed
    h24_rate = round((h24_sent / max(h24_total, 1)) * 100, 1)

    # Last failure
    last_failure = await db.email_logs.find_one(
        {"email_type": "otp", "status": "failed"},
        {"_id": 0, "email": 1, "error": 1, "created_at": 1},
        sort=[("created_at", -1)],
    )

    # Last successful send
    last_success = await db.email_logs.find_one(
        {"email_type": "otp", "status": "sent"},
        {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    )

    # Determine health status
    if h1_total == 0 and h6_total == 0:
        health = "idle"
    elif h1_rate >= 95:
        health = "healthy"
    elif h1_rate >= 80:
        health = "degraded"
    else:
        health = "critical"

    return {
        "health": health,
        "windows": {
            "1h": {"sent": h1_sent, "failed": h1_failed, "total": h1_total, "rate": h1_rate},
            "6h": {"sent": h6_sent, "failed": h6_failed, "total": h6_total, "rate": h6_rate},
            "24h": {"sent": h24_sent, "failed": h24_failed, "total": h24_total, "rate": h24_rate},
        },
        "last_failure": last_failure,
        "last_success_at": last_success.get("created_at") if last_success else None,
    }


@router.get("/hourly")
async def get_otp_hourly():
    """Hourly OTP volume for the last 24 hours."""
    now = datetime.now(timezone.utc)
    hours = []
    for i in range(24):
        h_start = now - timedelta(hours=23 - i)
        h_end = h_start + timedelta(hours=1)
        start_iso = h_start.isoformat()
        end_iso = h_end.isoformat()
        sent = await db.email_logs.count_documents(
            {
                "email_type": "otp",
                "status": "sent",
                "created_at": {"$gte": start_iso, "$lt": end_iso},
            }
        )
        failed = await db.email_logs.count_documents(
            {
                "email_type": "otp",
                "status": "failed",
                "created_at": {"$gte": start_iso, "$lt": end_iso},
            }
        )
        hours.append(
            {
                "hour": h_start.strftime("%H:%M"),
                "sent": sent,
                "failed": failed,
            }
        )
    return {"hours": hours}
