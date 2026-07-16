"""AI Feature Alerting — Real-time alerts for engagement drops & usage spikes.

Scheduled job runs every 5 minutes, checks thresholds, creates alerts,
and pushes real-time notifications to admin users via WebSocket.

Endpoints:
- GET /api/admin/ai-alerts — List active alerts
- PUT /api/admin/ai-alerts/{alert_id}/acknowledge — Acknowledge an alert
- GET /api/admin/ai-alerts/config — Get alert thresholds
- PUT /api/admin/ai-alerts/config — Update alert thresholds
- POST /api/admin/ai-alerts/check-now — Trigger immediate alert check
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import uuid

from routes.db import db, get_current_user
from utils.ws_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_CONFIG = {
    "engagement_drop_pct": 30,
    "usage_spike_multiplier": 3.0,
    "min_requests_for_spike": 10,
    "check_window_hours": 6,
    "comparison_window_days": 7,
    "enabled": True,
}

AI_FEATURES = {
    "ai-life-coach": {"name": "AI Life Coach", "collection": "ai_coach_conversations"},
    "ai-coaching-team": {"name": "AI Coaching Team", "collection": "coaching_team_sessions"},
    "ai-learning-hub": {"name": "AI Learning Hub", "collection": "learn_lessons"},
    "ai-goal-tracker": {"name": "AI Goal Tracker", "collection": "ai_goals"},
    "ai-doc-analyzer": {"name": "AI Doc Analyzer", "collection": "doc_analyses"},
    "daily-briefing": {"name": "Daily Briefing", "collection": "ai_briefings"},
    "mock-interview": {"name": "Mock Interview", "collection": "mock_interviews"},
}


async def _get_config() -> dict:
    cfg = await db.ai_alert_config.find_one({"_id": "global"}, {"_id": 0})
    return {**DEFAULT_CONFIG, **(cfg or {})}


async def _count_in_window(collection_name: str, hours: float) -> int:
    if not collection_name:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    coll = db[collection_name]
    return await coll.count_documents(
        {
            "$or": [
                {"created_at": {"$gte": cutoff}},
                {"submitted_at": {"$gte": cutoff}},
                {"started_at": {"$gte": cutoff}},
            ]
        }
    )


async def run_alert_check():
    """Scheduled job: check for engagement drops and usage spikes."""
    cfg = await _get_config()
    if not cfg.get("enabled"):
        return 0

    now = datetime.now(timezone.utc)
    window_h = cfg["check_window_hours"]
    comparison_days = cfg["comparison_window_days"]
    alerts_created = 0

    for fid, fmeta in AI_FEATURES.items():
        coll_name = fmeta.get("collection")
        if not coll_name:
            continue

        # Current window count
        current = await _count_in_window(coll_name, window_h)

        # Historical average for same window
        total_hist = 0
        for d in range(1, comparison_days + 1):
            cutoff_start = (now - timedelta(days=d, hours=window_h)).isoformat()
            cutoff_end = (now - timedelta(days=d)).isoformat()
            coll = db[coll_name]
            cnt = await coll.count_documents(
                {
                    "$or": [
                        {"created_at": {"$gte": cutoff_start, "$lte": cutoff_end}},
                        {"submitted_at": {"$gte": cutoff_start, "$lte": cutoff_end}},
                        {"started_at": {"$gte": cutoff_start, "$lte": cutoff_end}},
                    ]
                }
            )
            total_hist += cnt
        avg_hist = total_hist / max(comparison_days, 1)

        # Check engagement drop
        if avg_hist > 2 and current < avg_hist * (1 - cfg["engagement_drop_pct"] / 100):
            drop_pct = round((1 - current / avg_hist) * 100)
            alert = {
                "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
                "type": "engagement_drop",
                "severity": "warning" if drop_pct < 50 else "critical",
                "feature_id": fid,
                "feature_name": fmeta["name"],
                "message": f"{fmeta['name']} engagement dropped {drop_pct}% vs {comparison_days}-day avg",
                "detail": f"Current: {current} (last {window_h}h) vs Avg: {round(avg_hist, 1)}",
                "current_value": current,
                "baseline_value": round(avg_hist, 1),
                "drop_pct": drop_pct,
                "created_at": now.isoformat(),
                "acknowledged": False,
            }
            await db.ai_alerts.insert_one(alert)
            alerts_created += 1
            await _notify_admins(alert)

        # Check usage spike
        if (
            current >= cfg["min_requests_for_spike"]
            and avg_hist > 0
            and current > avg_hist * cfg["usage_spike_multiplier"]
        ):
            spike_x = round(current / avg_hist, 1)
            alert = {
                "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
                "type": "usage_spike",
                "severity": "info" if spike_x < 5 else "warning",
                "feature_id": fid,
                "feature_name": fmeta["name"],
                "message": f"{fmeta['name']} usage spiked {spike_x}x above {comparison_days}-day avg",
                "detail": f"Current: {current} (last {window_h}h) vs Avg: {round(avg_hist, 1)}",
                "current_value": current,
                "baseline_value": round(avg_hist, 1),
                "spike_multiplier": spike_x,
                "created_at": now.isoformat(),
                "acknowledged": False,
            }
            await db.ai_alerts.insert_one(alert)
            alerts_created += 1
            await _notify_admins(alert)

    # Also check overall platform usage spike
    total_current = 0
    total_hist_overall = 0
    for fid, fmeta in AI_FEATURES.items():
        if fmeta.get("collection"):
            total_current += await _count_in_window(fmeta["collection"], window_h)
    if total_current >= cfg["min_requests_for_spike"] * 2:
        for d in range(1, comparison_days + 1):
            for fid, fmeta in AI_FEATURES.items():
                coll_name = fmeta.get("collection")
                if not coll_name:
                    continue
                cutoff_start = (now - timedelta(days=d, hours=window_h)).isoformat()
                cutoff_end = (now - timedelta(days=d)).isoformat()
                cnt = await db[coll_name].count_documents(
                    {
                        "$or": [
                            {"created_at": {"$gte": cutoff_start, "$lte": cutoff_end}},
                            {"submitted_at": {"$gte": cutoff_start, "$lte": cutoff_end}},
                        ]
                    }
                )
                total_hist_overall += cnt
        avg_overall = total_hist_overall / max(comparison_days, 1)
        if avg_overall > 0 and total_current > avg_overall * cfg["usage_spike_multiplier"]:
            spike_x = round(total_current / avg_overall, 1)
            alert = {
                "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
                "type": "platform_spike",
                "severity": "warning",
                "feature_id": "platform",
                "feature_name": "All AI Features",
                "message": f"Overall AI platform usage spiked {spike_x}x above average",
                "detail": f"Total current: {total_current} vs Avg: {round(avg_overall, 1)}",
                "current_value": total_current,
                "baseline_value": round(avg_overall, 1),
                "spike_multiplier": spike_x,
                "created_at": now.isoformat(),
                "acknowledged": False,
            }
            await db.ai_alerts.insert_one(alert)
            alerts_created += 1
            await _notify_admins(alert)

    if alerts_created:
        logger.info(f"AI Alerting: {alerts_created} alerts created")
    return alerts_created


async def _notify_admins(alert: dict):
    """Push real-time alert to all connected admin users."""
    admins = await db.users.find({"is_admin": True}, {"user_id": 1, "_id": 0}).to_list(50)
    admin_ids = [a["user_id"] for a in admins]
    payload = {
        "type": "ai_alert",
        "alert": {k: v for k, v in alert.items() if k != "_id"},
    }
    await ws_manager.send_to_admins(payload, admin_ids)


@router.get("/admin/ai-alerts")
async def list_alerts(request: Request, status: str = "all", limit: int = 50):
    """List AI alerts. status: all|active|acknowledged"""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    query: dict = {}
    if status == "active":
        query["acknowledged"] = False
    elif status == "acknowledged":
        query["acknowledged"] = True

    alerts = await db.ai_alerts.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    active_count = await db.ai_alerts.count_documents({"acknowledged": False})
    return {"alerts": alerts, "active_count": active_count, "total": len(alerts)}


@router.put("/admin/ai-alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: Request):
    """Acknowledge/dismiss an alert."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.ai_alerts.update_one(
        {"alert_id": alert_id},
        {
            "$set": {
                "acknowledged": True,
                "acknowledged_by": user.email,
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "acknowledged", "alert_id": alert_id}


class AlertConfigUpdate(BaseModel):
    engagement_drop_pct: Optional[int] = None
    usage_spike_multiplier: Optional[float] = None
    min_requests_for_spike: Optional[int] = None
    check_window_hours: Optional[int] = None
    comparison_window_days: Optional[int] = None
    enabled: Optional[bool] = None


@router.get("/admin/ai-alerts/config")
async def get_alert_config(request: Request):
    """Get current alert thresholds."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    cfg = await _get_config()
    return {"config": cfg}


@router.put("/admin/ai-alerts/config")
async def update_alert_config(body: AlertConfigUpdate, request: Request):
    """Update alert thresholds."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    await db.ai_alert_config.update_one({"_id": "global"}, {"$set": updates}, upsert=True)
    cfg = await _get_config()
    return {"config": cfg}


@router.post("/admin/ai-alerts/check-now")
async def trigger_check_now(request: Request):
    """Trigger immediate alert check."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    count = await run_alert_check()
    return {"alerts_created": count, "checked_at": datetime.now(timezone.utc).isoformat()}
