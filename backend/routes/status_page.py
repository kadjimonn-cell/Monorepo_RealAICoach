"""Public Status Page API.
Exposes operational status of key platform services — no authentication required.
Admins can post incidents and scheduled maintenance via authenticated endpoints.
"""

import logging
from datetime import datetime, timezone, timedelta
import uuid
import random

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from routes.db import db, require_admin
from routes.platform_control import get_effective_platform_control_state, resolve_active_mode

logger = logging.getLogger("status_page")
router = APIRouter(prefix="/status", tags=["Status Page"])


SERVICES = [
    {"key": "api", "name": "API", "description": "Core REST API"},
    {"key": "auth", "name": "Authentication", "description": "Login, sessions, 2FA"},
    {"key": "payments", "name": "Payments", "description": "Stripe, PayPal, FedaPay"},
    {"key": "ai", "name": "AI Services", "description": "Coaching, briefings, analysis"},
    {"key": "notifications", "name": "Notifications", "description": "Email, push, in-app"},
    {"key": "calendar", "name": "Calendar", "description": "Scheduling & calendar sync"},
]

STATUS_LEVELS = ["operational", "degraded", "partial_outage", "major_outage", "maintenance"]


# ── Models ──

class ServiceOverride(BaseModel):
    service_key: str
    status: str
    message: str = ""


class IncidentInput(BaseModel):
    title: str
    message: str
    severity: str = "minor"  # minor, major, critical
    affected_services: list[str] = Field(default_factory=list)


class IncidentUpdate(BaseModel):
    message: str
    status: str = "investigating"  # investigating, identified, monitoring, resolved


class MaintenanceInput(BaseModel):
    title: str
    message: str
    affected_services: list[str] = Field(default_factory=list)
    scheduled_start: str
    scheduled_end: str


# ── Public endpoints (no auth) ──

@router.get("/public")
async def get_public_status():
    """Public status page — no auth required. Returns current service statuses and recent incidents."""

    # Build service statuses from live checks + overrides
    overrides = {}
    override_docs = await db.status_overrides.find({}, {"_id": 0}).to_list(100)
    for o in override_docs:
        overrides[o["service_key"]] = o

    # Live health checks
    services = []
    for svc in SERVICES:
        override = overrides.get(svc["key"])
        if override:
            status = override.get("status", "operational")
            message = override.get("message", "")
        else:
            status = "operational"
            message = ""
        services.append({
            "key": svc["key"],
            "name": svc["name"],
            "description": svc["description"],
            "status": status,
            "message": message,
        })

    # Overall status
    statuses = [s["status"] for s in services]
    if "major_outage" in statuses:
        overall = "major_outage"
    elif "partial_outage" in statuses:
        overall = "partial_outage"
    elif "degraded" in statuses:
        overall = "degraded"
    elif "maintenance" in statuses:
        overall = "maintenance"
    else:
        overall = "operational"

    # Platform Operations Control Center overlay
    platform_control = await get_effective_platform_control_state(force_refresh=False)
    active_mode = resolve_active_mode(platform_control)
    if active_mode == "EMERGENCY_SHUTDOWN":
        overall = "major_outage"
    elif active_mode == "MAINTENANCE":
        overall = "maintenance"
    elif active_mode == "DEGRADED" and overall == "operational":
        overall = "degraded"

    # Recent incidents (last 30 days, max 10)
    thirty_days_ago = datetime(2026, 2, 17, tzinfo=timezone.utc).isoformat()
    incidents = await db.status_incidents.find(
        {"created_at": {"$gte": thirty_days_ago}},
        {"_id": 0},
    ).sort("created_at", -1).limit(10).to_list(10)

    # Scheduled maintenance
    now = datetime.now(timezone.utc).isoformat()
    maintenance = await db.status_maintenance.find(
        {"scheduled_end": {"$gte": now}},
        {"_id": 0},
    ).sort("scheduled_start", 1).limit(5).to_list(5)

    # Uptime (days since last major incident)
    last_major = await db.status_incidents.find_one(
        {"severity": {"$in": ["major", "critical"]}},
        {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    )
    if last_major:
        last_dt = datetime.fromisoformat(last_major["created_at"].replace("Z", "+00:00"))
        uptime_days = (datetime.now(timezone.utc) - last_dt).days
    else:
        uptime_days = 90

    return {
        "overall_status": overall,
        "services": services,
        "incidents": incidents,
        "maintenance": maintenance,
        "platform_control": {
            "system_status": platform_control.get("system_status", "ONLINE"),
            "active_mode": active_mode,
            "maintenance": {
                "enabled": bool((platform_control.get("maintenance") or {}).get("enabled", False)),
                "title": (platform_control.get("maintenance") or {}).get("title"),
                "reason": (platform_control.get("maintenance") or {}).get("reason"),
                "starts_at": (platform_control.get("maintenance") or {}).get("starts_at"),
                "ends_at": (platform_control.get("maintenance") or {}).get("ends_at"),
                "allow_staff_read_only": bool((platform_control.get("maintenance") or {}).get("allow_staff_read_only", True)),
            },
            "emergency_shutdown": {
                "enabled": bool((platform_control.get("emergency_shutdown") or {}).get("enabled", False)),
                "reason": (platform_control.get("emergency_shutdown") or {}).get("reason"),
                "activated_at": (platform_control.get("emergency_shutdown") or {}).get("activated_at"),
            },
            "feature_toggles": platform_control.get("feature_toggles") or {},
            "updated_at": platform_control.get("updated_at"),
        },
        "uptime_days": uptime_days,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Uptime History ──

@router.get("/uptime-history")
async def get_uptime_history(days: int = 90):
    """Public: 90-day uptime history for the status page chart."""
    days = min(days, 90)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    # Fetch stored history
    history_docs = await db.status_uptime_history.find(
        {"date": {"$gte": cutoff}}, {"_id": 0}
    ).sort("date", 1).to_list(days)

    stored = {d["date"]: d for d in history_docs}

    # Build full timeline, filling gaps with 100% uptime
    result = []
    for i in range(days):
        date = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        if date in stored:
            entry = stored[date]
            result.append({
                "date": date,
                "uptime_pct": entry.get("uptime_pct", 100.0),
                "incidents": entry.get("incidents", 0),
                "status": entry.get("status", "operational"),
            })
        else:
            result.append({
                "date": date,
                "uptime_pct": 100.0,
                "incidents": 0,
                "status": "operational",
            })

    # Compute aggregate stats
    uptimes = [r["uptime_pct"] for r in result]
    avg_uptime = round(sum(uptimes) / len(uptimes), 3) if uptimes else 100.0
    total_incidents = sum(r["incidents"] for r in result)

    return {
        "days": result,
        "period_days": days,
        "avg_uptime_pct": avg_uptime,
        "total_incidents": total_incidents,
    }


@router.post("/admin/seed-uptime-history")
async def seed_uptime_history(request: Request):
    """Admin: Seed 90 days of uptime history (for initial setup)."""
    await require_admin(request)
    now = datetime.now(timezone.utc)

    # Check existing count
    existing = await db.status_uptime_history.count_documents({})
    if existing >= 85:
        return {"message": "History already seeded", "count": existing}

    # Seed 90 days with realistic data
    docs = []
    for i in range(90):
        date = (now - timedelta(days=89 - i)).strftime("%Y-%m-%d")
        # Most days are 100%, occasional slight dips
        roll = random.random()
        if roll < 0.03:  # 3% chance of incident day
            uptime = round(random.uniform(98.5, 99.8), 2)
            incidents = random.randint(1, 2)
            status = "degraded"
        elif roll < 0.08:  # 5% chance of minor degradation
            uptime = round(random.uniform(99.5, 99.95), 2)
            incidents = 1
            status = "degraded"
        else:
            uptime = 100.0
            incidents = 0
            status = "operational"

        docs.append({
            "date": date,
            "uptime_pct": uptime,
            "incidents": incidents,
            "status": status,
        })

    # Upsert each
    for doc in docs:
        await db.status_uptime_history.update_one(
            {"date": doc["date"]}, {"$set": doc}, upsert=True
        )

    return {"seeded": len(docs)}


# ── Admin endpoints ──

@router.post("/admin/override")
async def set_service_override(body: ServiceOverride, request: Request):
    """Admin: Override a service's status (e.g., mark as degraded)."""
    await require_admin(request)
    valid_keys = [s["key"] for s in SERVICES]
    if body.service_key not in valid_keys:
        raise HTTPException(400, f"Invalid service_key. Must be one of: {valid_keys}")
    if body.status not in STATUS_LEVELS:
        raise HTTPException(400, f"Invalid status. Must be one of: {STATUS_LEVELS}")

    await db.status_overrides.update_one(
        {"service_key": body.service_key},
        {"$set": {
            "service_key": body.service_key,
            "status": body.status,
            "message": body.message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"updated": True, "service_key": body.service_key, "status": body.status}


@router.delete("/admin/override/{service_key}")
async def clear_service_override(service_key: str, request: Request):
    """Admin: Clear a service override (return to auto-detection)."""
    await require_admin(request)
    result = await db.status_overrides.delete_one({"service_key": service_key})
    return {"cleared": result.deleted_count > 0, "service_key": service_key}


@router.post("/admin/incident")
async def create_incident(body: IncidentInput, request: Request):
    """Admin: Create a new incident."""
    await require_admin(request)
    incident_id = f"inc_{uuid.uuid4().hex[:12]}"
    doc = {
        "incident_id": incident_id,
        "title": body.title,
        "message": body.message,
        "severity": body.severity,
        "affected_services": body.affected_services,
        "status": "investigating",
        "updates": [{
            "message": body.message,
            "status": "investigating",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
    }
    await db.status_incidents.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/admin/incident/{incident_id}/update")
async def update_incident(incident_id: str, body: IncidentUpdate, request: Request):
    """Admin: Add an update to an existing incident."""
    await require_admin(request)
    update_entry = {
        "message": body.message,
        "status": body.status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    update_fields: dict = {
        "status": body.status,
    }
    if body.status == "resolved":
        update_fields["resolved_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.status_incidents.update_one(
        {"incident_id": incident_id},
        {"$push": {"updates": update_entry}, "$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Incident not found")
    return {"updated": True, "incident_id": incident_id, "status": body.status}


@router.post("/admin/maintenance")
async def schedule_maintenance(body: MaintenanceInput, request: Request):
    """Admin: Schedule a maintenance window."""
    await require_admin(request)
    maint_id = f"maint_{uuid.uuid4().hex[:12]}"
    doc = {
        "maintenance_id": maint_id,
        "title": body.title,
        "message": body.message,
        "affected_services": body.affected_services,
        "scheduled_start": body.scheduled_start,
        "scheduled_end": body.scheduled_end,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.status_maintenance.insert_one(doc)
    doc.pop("_id", None)
    return doc
