"""AI Incident Auto-Detection — Monitors metrics and auto-triggers remediation.

Runs every 60s via APScheduler. Detects anomalies in CPU, memory, disk, API latency.
Auto-triggers AI remediation when thresholds are breached.

Admin-only endpoints:
- GET  /api/admin/auto-detect/status       — Current monitoring status + live metrics
- GET  /api/admin/auto-detect/incidents     — Detected incidents
- POST /api/admin/auto-detect/config        — Update thresholds & toggle
- GET  /api/admin/auto-detect/config        — Get current config
- POST /api/admin/auto-detect/acknowledge   — Acknowledge an incident
"""

import time
import uuid
import logging
import psutil
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from routes.db import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/auto-detect", tags=["AI Auto-Detection"])

# Default thresholds
DEFAULT_CONFIG = {
    "enabled": True,
    "check_interval_seconds": 60,
    "thresholds": {
        "cpu_percent": 90,
        "memory_percent": 85,
        "disk_percent": 90,
        "api_latency_ms": 5000,
    },
    "auto_remediate": True,
    "cooldown_minutes": 10,
    "notify_email": True,
}


async def _get_config() -> dict:
    """Get monitoring config from DB, or create default."""
    config = await db.auto_detect_config.find_one({"_id": "config"})
    if not config:
        config = {**DEFAULT_CONFIG, "_id": "config"}
        await db.auto_detect_config.insert_one(config)
    config.pop("_id", None)
    return config


async def _collect_metrics() -> dict:
    """Collect real system metrics."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # Measure API latency
    api_latency_ms = -1
    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get("http://127.0.0.1:8001/api/health")
        api_latency_ms = round((time.monotonic() - start) * 1000, 1)
    except Exception:
        api_latency_ms = 99999

    return {
        "cpu_percent": cpu,
        "memory_percent": round(mem.percent, 1),
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "disk_percent": round(disk.percent, 1),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "api_latency_ms": api_latency_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def run_detection_cycle():
    """Called by APScheduler every check_interval_seconds. Core detection loop."""
    config = await _get_config()
    if not config.get("enabled"):
        return

    metrics = await _collect_metrics()
    thresholds = config.get("thresholds", {})
    breaches = []

    # Check each threshold
    if metrics["cpu_percent"] > thresholds.get("cpu_percent", 90):
        breaches.append({
            "metric": "cpu_percent",
            "value": metrics["cpu_percent"],
            "threshold": thresholds["cpu_percent"],
            "severity": "critical" if metrics["cpu_percent"] > 95 else "high",
            "message": f"CPU usage at {metrics['cpu_percent']}% (threshold: {thresholds['cpu_percent']}%)",
        })

    if metrics["memory_percent"] > thresholds.get("memory_percent", 85):
        breaches.append({
            "metric": "memory_percent",
            "value": metrics["memory_percent"],
            "threshold": thresholds["memory_percent"],
            "severity": "critical" if metrics["memory_percent"] > 95 else "high",
            "message": f"Memory usage at {metrics['memory_percent']}% (threshold: {thresholds['memory_percent']}%)",
        })

    if metrics["disk_percent"] > thresholds.get("disk_percent", 90):
        breaches.append({
            "metric": "disk_percent",
            "value": metrics["disk_percent"],
            "threshold": thresholds["disk_percent"],
            "severity": "critical" if metrics["disk_percent"] > 95 else "high",
            "message": f"Disk usage at {metrics['disk_percent']}% (threshold: {thresholds['disk_percent']}%)",
        })

    if metrics["api_latency_ms"] > thresholds.get("api_latency_ms", 5000):
        breaches.append({
            "metric": "api_latency_ms",
            "value": metrics["api_latency_ms"],
            "threshold": thresholds["api_latency_ms"],
            "severity": "critical" if metrics["api_latency_ms"] > 10000 else "high",
            "message": f"API latency at {metrics['api_latency_ms']}ms (threshold: {thresholds['api_latency_ms']}ms)",
        })

    # Store metrics snapshot
    await db.auto_detect_metrics.insert_one({
        **metrics, "breaches_count": len(breaches),
    })

    if not breaches:
        return

    # Check cooldown — avoid re-triggering for the same issue
    cooldown = config.get("cooldown_minutes", 10)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown)
    for breach in breaches:
        recent = await db.auto_detect_incidents.find_one({
            "breach.metric": breach["metric"],
            "detected_at": {"$gte": cutoff},
            "status": {"$in": ["detected", "remediating"]},
        })
        if recent:
            continue  # Skip — still in cooldown

        incident_id = f"inc_{uuid.uuid4().hex[:12]}"
        incident = {
            "incident_id": incident_id,
            "breach": breach,
            "metrics_snapshot": metrics,
            "status": "detected",
            "detected_at": datetime.now(timezone.utc),
            "acknowledged": False,
            "remediation_id": None,
        }
        await db.auto_detect_incidents.insert_one(incident)
        incident.pop("_id", None)

        logger.warning(f"Auto-detect: Incident {incident_id} — {breach['message']}")

        # Auto-remediate if enabled
        if config.get("auto_remediate"):
            try:
                from routes.ai_remediation import analyze_incident, IncidentReport
                rem_result = await analyze_incident(
                    request=None,
                    incident=IncidentReport(
                        title=f"Auto-detected: {breach['message']}",
                        description=f"Automated monitoring detected {breach['metric']} breached threshold. Current value: {breach['value']}, Threshold: {breach['threshold']}. Severity: {breach['severity']}.",
                        severity=breach["severity"],
                        affected_services=["system"],
                    ),
                )
                rem_id = rem_result.get("remediation_id") if isinstance(rem_result, dict) else None
                await db.auto_detect_incidents.update_one(
                    {"incident_id": incident_id},
                    {"$set": {"status": "remediating", "remediation_id": rem_id}},
                )
                logger.info(f"Auto-detect: Triggered remediation {rem_id} for {incident_id}")
            except Exception as e:
                logger.error(f"Auto-detect: Remediation trigger failed: {e}")
                await db.auto_detect_incidents.update_one(
                    {"incident_id": incident_id},
                    {"$set": {"status": "remediation_failed", "error": str(e)}},
                )

        # Send email notification
        if config.get("notify_email"):
            try:
                from utils.email_service import send_catalog_template
                await send_catalog_template(
                    recipient_email="admin@realaicoach.app",
                    template_key="system_alert_admin",
                    alert_type=f"Auto-Detect: {breach['metric']}",
                    severity=breach['severity'].upper(),
                    description=breach['message'],
                    component=breach.get('metric', 'System'),
                )
            except Exception as e:
                logger.warning(f"Auto-detect: Email notification failed: {e}")


@router.get("/status")
async def detection_status(request: Request):
    """Current monitoring status with live metrics."""
    config = await _get_config()
    metrics = await _collect_metrics()

    # Count incidents
    total_incidents = await db.auto_detect_incidents.count_documents({})
    active_incidents = await db.auto_detect_incidents.count_documents({"status": {"$in": ["detected", "remediating"]}})
    resolved_incidents = await db.auto_detect_incidents.count_documents({"status": "resolved"})

    # Recent metrics (last 10)
    recent_metrics = await db.auto_detect_metrics.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(10).to_list(10)

    return {
        "monitoring_enabled": config.get("enabled", False),
        "auto_remediate": config.get("auto_remediate", False),
        "thresholds": config.get("thresholds", {}),
        "live_metrics": metrics,
        "incidents": {
            "total": total_incidents,
            "active": active_incidents,
            "resolved": resolved_incidents,
        },
        "recent_metrics": recent_metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/incidents")
async def list_incidents(request: Request, limit: int = 30, status: Optional[str] = None):
    """List detected incidents."""
    query = {}
    if status:
        query["status"] = status
    docs = await db.auto_detect_incidents.find(
        query, {"_id": 0}
    ).sort("detected_at", -1).limit(limit).to_list(limit)
    for d in docs:
        if hasattr(d.get("detected_at"), "isoformat"):
            d["detected_at"] = d["detected_at"].isoformat()
    return {"incidents": docs, "count": len(docs)}


@router.get("/config")
async def get_config(request: Request):
    """Get current monitoring configuration."""
    return await _get_config()


class ConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    auto_remediate: Optional[bool] = None
    notify_email: Optional[bool] = None
    cooldown_minutes: Optional[int] = None
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    api_latency_ms: Optional[float] = None


@router.post("/config")
async def update_config(request: Request, body: ConfigUpdate):
    """Update monitoring configuration."""
    await _get_config()
    updates = {}
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if body.auto_remediate is not None:
        updates["auto_remediate"] = body.auto_remediate
    if body.notify_email is not None:
        updates["notify_email"] = body.notify_email
    if body.cooldown_minutes is not None:
        updates["cooldown_minutes"] = body.cooldown_minutes
    if body.cpu_percent is not None:
        updates["thresholds.cpu_percent"] = body.cpu_percent
    if body.memory_percent is not None:
        updates["thresholds.memory_percent"] = body.memory_percent
    if body.disk_percent is not None:
        updates["thresholds.disk_percent"] = body.disk_percent
    if body.api_latency_ms is not None:
        updates["thresholds.api_latency_ms"] = body.api_latency_ms

    if updates:
        await db.auto_detect_config.update_one({"_id": "config"}, {"$set": updates})

    return await _get_config()


class AcknowledgeBody(BaseModel):
    incident_id: str
    resolution_note: Optional[str] = None


@router.post("/acknowledge")
async def acknowledge_incident(request: Request, body: AcknowledgeBody):
    """Acknowledge/resolve an incident."""
    result = await db.auto_detect_incidents.update_one(
        {"incident_id": body.incident_id},
        {"$set": {
            "status": "resolved",
            "acknowledged": True,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "resolution_note": body.resolution_note,
        }},
    )
    if result.matched_count == 0:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Incident not found"}, status_code=404)
    return {"status": "resolved", "incident_id": body.incident_id}
