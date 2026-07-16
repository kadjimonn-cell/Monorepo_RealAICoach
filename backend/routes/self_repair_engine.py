"""Autonomous Self-Repair Engine — Health monitoring, auto-fix, self-healing.

Monitors backend services, DB connectivity, scheduler status.
Auto-restarts failed schedulers, clears stale sessions, fixes common issues.

API:
- GET  /api/admin/system/health-deep  — Deep health check with auto-repair status
- POST /api/admin/system/self-repair  — Manually trigger self-repair cycle
- GET  /api/admin/system/repair-history — View repair history with metrics
- POST /api/admin/system/repair-config — Configure repair intervals and alerts
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import psutil

from routes.db import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_REPAIR_CONFIG = {
    "enabled": True,
    "interval_minutes": 30,
    "alert_on_repair": True,
    "auto_clear_stale_sessions": True,
    "auto_fix_missing_fields": True,
    "auto_purge_old_notifications": True,
    "auto_repair_indexes": True,
    "auto_clear_rate_limits": True,
    "stale_session_hours": 24,
    "old_notification_days": 30,
}


async def _get_repair_config():
    config = await db.repair_config.find_one({"config_id": "main"}, {"_id": 0})
    return config or DEFAULT_REPAIR_CONFIG


async def run_self_repair():
    """Background job: check system health and auto-repair issues."""
    now = datetime.now(timezone.utc)
    config = await _get_repair_config()
    repairs = []
    before_metrics = {}

    # 1. Clear stale sessions
    if config.get("auto_clear_stale_sessions", True):
        before_metrics["stale_sessions"] = await db.user_sessions.count_documents({"expires_at": {"$lt": now}})
        stale_result = await db.user_sessions.delete_many({"expires_at": {"$lt": now}})
        if stale_result.deleted_count > 0:
            repairs.append({"type": "stale_sessions_cleared", "count": stale_result.deleted_count, "severity": "low"})

    # 2. Clear orphaned notification read markers
    if config.get("auto_purge_old_notifications", True):
        old_days = config.get("old_notification_days", 30)
        old_notif_cutoff = (now - timedelta(days=old_days)).isoformat()
        before_metrics["old_notifications"] = await db.notifications.count_documents(
            {"read": True, "created_at": {"$lt": old_notif_cutoff}}
        )
        old_notifs = await db.notifications.delete_many({"read": True, "created_at": {"$lt": old_notif_cutoff}})
        if old_notifs.deleted_count > 0:
            repairs.append({"type": "old_notifications_purged", "count": old_notifs.deleted_count, "severity": "low"})

    # 3. Fix users with missing subscription_plan
    if config.get("auto_fix_missing_fields", True):
        before_metrics["missing_plans"] = await db.users.count_documents({"subscription_plan": {"$exists": False}})
        fix_plan = await db.users.update_many(
            {"subscription_plan": {"$exists": False}}, {"$set": {"subscription_plan": "free"}}
        )
        if fix_plan.modified_count > 0:
            repairs.append({"type": "missing_plans_fixed", "count": fix_plan.modified_count, "severity": "medium"})

        # Fix users with missing is_admin
        fix_admin = await db.users.update_many({"is_admin": {"$exists": False}}, {"$set": {"is_admin": False}})
        if fix_admin.modified_count > 0:
            repairs.append(
                {"type": "missing_admin_flag_fixed", "count": fix_admin.modified_count, "severity": "medium"}
            )

    # 4. Fix tickets with missing status
    if config.get("auto_fix_missing_fields", True):
        fix_tickets = await db.support_submissions.update_many(
            {"status": {"$exists": False}}, {"$set": {"status": "open"}}
        )
        if fix_tickets.modified_count > 0:
            repairs.append({"type": "ticket_status_fixed", "count": fix_tickets.modified_count, "severity": "medium"})

    # 5. Index health check
    if config.get("auto_repair_indexes", True):
        indexes_created = 0
        try:
            await db.users.create_index("user_id", unique=True, background=True)
            await db.users.create_index("email", unique=True, background=True)
            await db.user_sessions.create_index("refresh_token", background=True)
            await db.user_sessions.create_index("expires_at", background=True)
            await db.usage_analytics.create_index([("user_id", 1), ("timestamp", -1)], background=True)
            await db.usage_analytics.create_index([("feature_id", 1), ("timestamp", -1)], background=True)
            await db.fraud_reports.create_index("user_id", unique=True, background=True)
            await db.ai_support_log.create_index([("ticket_id", 1), ("created_at", -1)], background=True)
            await db.support_submissions.create_index([("status", 1), ("created_at", -1)], background=True)
            await db.security_events.create_index([("user_id", 1), ("timestamp", -1)], background=True)
            indexes_created = 10
        except Exception:
            pass
        if indexes_created > 0:
            repairs.append({"type": "indexes_verified", "count": indexes_created, "severity": "low"})

    # 6. Clear expired rate limit entries
    if config.get("auto_clear_rate_limits", True):
        try:
            cutoff_rl = (now - timedelta(minutes=10)).isoformat()
            rl_result = await db.rate_limits.delete_many({"window_start": {"$lt": cutoff_rl}})
            if rl_result.deleted_count > 0:
                repairs.append(
                    {"type": "rate_limit_cache_cleared", "count": rl_result.deleted_count, "severity": "low"}
                )
        except Exception:
            pass

    # 7. Fix orphaned DB references (tickets referencing deleted users)
    try:
        all_user_ids = set(await db.users.distinct("user_id"))
        orphaned_tickets = await db.support_submissions.find(
            {"user_id": {"$nin": list(all_user_ids)}}, {"_id": 0, "submission_id": 1}
        ).to_list(100)
        if orphaned_tickets:
            orphan_ids = [t["submission_id"] for t in orphaned_tickets]
            await db.support_submissions.update_many(
                {"submission_id": {"$in": orphan_ids}},
                {"$set": {"status": "orphaned", "orphan_note": "User no longer exists"}},
            )
            repairs.append({"type": "orphaned_tickets_flagged", "count": len(orphan_ids), "severity": "medium"})
    except Exception:
        pass

    # 8. Clear stale error logs (older than 7 days)
    try:
        old_err_cutoff = (now - timedelta(days=7)).isoformat()
        err_result = await db.error_logs.delete_many({"timestamp": {"$lt": old_err_cutoff}})
        if err_result.deleted_count > 0:
            repairs.append({"type": "old_error_logs_cleared", "count": err_result.deleted_count, "severity": "low"})
    except Exception:
        pass

    # System metrics after repair
    after_metrics = {
        "active_sessions": await db.user_sessions.count_documents({"expires_at": {"$gte": now}}),
        "total_users": await db.users.count_documents({}),
        "open_tickets": await db.support_submissions.count_documents({"status": {"$in": ["open", "pending", "new"]}}),
    }

    # Log repair cycle
    log_entry = {
        "timestamp": now.isoformat(),
        "repairs": repairs,
        "total_repairs": len(repairs),
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "config_used": {k: v for k, v in config.items() if k != "config_id"},
    }
    await db.self_repair_log.insert_one(log_entry)

    # Send alert if configured and repairs were made
    if config.get("alert_on_repair", True) and len(repairs) > 0:
        try:
            from routes.notification_engine import emit_notification

            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(5)
            repair_summary = ", ".join([f"{r['type']}({r['count']})" for r in repairs[:4]])
            for admin in admins:
                await emit_notification(
                    user_id=admin["user_id"],
                    notif_type="self_repair",
                    title=f"Self-Repair: {len(repairs)} fixes applied",
                    body=f"Repairs: {repair_summary}",
                    action_url="/admin-console",
                    metadata={"repairs": len(repairs)},
                )
        except Exception:
            pass

    logger.info(f"Self-repair: {len(repairs)} repairs applied")
    return {"repairs": repairs, "total": len(repairs), "before_metrics": before_metrics, "after_metrics": after_metrics}


@router.get("/admin/system/health-deep")
async def deep_health_check(request: Request):
    """Deep system health check with diagnostics."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)

    # Database connectivity
    db_ok = False
    db_latency = 0
    try:
        import time

        start = time.time()
        await db.command("ping")
        db_latency = round((time.time() - start) * 1000, 1)
        db_ok = True
    except Exception:
        pass

    # Database stats
    try:
        stats = await db.command("dbstats")
        db_size_mb = round(stats.get("dataSize", 0) / 1024 / 1024, 2)
        db_collections = stats.get("collections", 0)
        db_objects = stats.get("objects", 0)
    except Exception:
        db_size_mb = 0
        db_collections = 0
        db_objects = 0

    # Collection sizes
    collection_stats = {}
    for col_name in [
        "users",
        "user_sessions",
        "support_tickets",
        "usage_analytics",
        "notifications",
        "direct_conversations",
        "direct_messages",
        "payments",
        "fraud_risk_profiles",
    ]:
        try:
            count = await db[col_name].count_documents({})
            collection_stats[col_name] = count
        except Exception:
            collection_stats[col_name] = -1

    # System resources
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        sys_resources = {
            "cpu_percent": cpu_pct,
            "memory_used_pct": memory.percent,
            "memory_used_mb": round(memory.used / 1024 / 1024),
            "memory_total_mb": round(memory.total / 1024 / 1024),
            "disk_used_pct": disk.percent,
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
        }
    except Exception:
        sys_resources = {"cpu_percent": -1, "memory_used_pct": -1, "disk_used_pct": -1}

    # Active sessions
    active_sessions = await db.user_sessions.count_documents({"expires_at": {"$gte": now}})
    stale_sessions = await db.user_sessions.count_documents({"expires_at": {"$lt": now}})

    # Scheduler health (check last SLA run)
    last_sla = await db.self_repair_log.find_one({}, sort=[("timestamp", -1)])
    last_repair_at = last_sla.get("timestamp") if last_sla else None

    # Recent errors
    recent_errors = []
    err_cursor = db.error_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(5)
    async for e in err_cursor:
        recent_errors.append(e)

    # Overall health score
    health_score = 100
    issues = []
    if not db_ok:
        health_score -= 50
        issues.append("Database connectivity failed")
    if db_latency > 500:
        health_score -= 10
        issues.append(f"High DB latency: {db_latency}ms")
    if sys_resources.get("cpu_percent", 0) > 90:
        health_score -= 15
        issues.append(f"High CPU: {sys_resources['cpu_percent']}%")
    if sys_resources.get("memory_used_pct", 0) > 90:
        health_score -= 15
        issues.append(f"High memory: {sys_resources['memory_used_pct']}%")
    if sys_resources.get("disk_used_pct", 0) > 90:
        health_score -= 10
        issues.append(f"Low disk: {sys_resources['disk_used_pct']}% used")
    if stale_sessions > 100:
        health_score -= 5
        issues.append(f"Stale sessions: {stale_sessions}")

    health_status = "healthy" if health_score >= 90 else "degraded" if health_score >= 60 else "critical"

    return {
        "health_score": max(0, health_score),
        "health_status": health_status,
        "issues": issues,
        "database": {
            "connected": db_ok,
            "latency_ms": db_latency,
            "size_mb": db_size_mb,
            "collections": db_collections,
            "objects": db_objects,
            "collection_stats": collection_stats,
        },
        "system": sys_resources,
        "sessions": {"active": active_sessions, "stale": stale_sessions},
        "last_repair": last_repair_at,
        "recent_errors": recent_errors,
        "timestamp": now.isoformat(),
    }


@router.get("/admin/self-repair/status")
async def self_repair_status_alias(request: Request):
    """Compatibility alias for legacy self-repair status checks."""
    return await deep_health_check(request)


@router.post("/admin/system/self-repair")
async def trigger_self_repair(request: Request):
    """Manually trigger a self-repair cycle."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await run_self_repair()
    return {"success": True, **result}


class RepairConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = None
    alert_on_repair: Optional[bool] = None
    auto_clear_stale_sessions: Optional[bool] = None
    auto_fix_missing_fields: Optional[bool] = None
    auto_purge_old_notifications: Optional[bool] = None
    auto_repair_indexes: Optional[bool] = None
    auto_clear_rate_limits: Optional[bool] = None
    stale_session_hours: Optional[int] = None
    old_notification_days: Optional[int] = None


@router.get("/admin/system/repair-history")
async def repair_history(request: Request):
    """View repair history with metrics."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    history = await db.self_repair_log.find({}, {"_id": 0}).sort("timestamp", -1).limit(20).to_list(20)
    config = await _get_repair_config()

    # Aggregate repair stats
    total_cycles = await db.self_repair_log.count_documents({})
    total_repairs = 0
    repair_types: dict = {}
    for h in history:
        for r in h.get("repairs", []):
            total_repairs += r.get("count", 0)
            rt = r.get("type", "unknown")
            repair_types[rt] = repair_types.get(rt, 0) + r.get("count", 0)

    return {
        "history": history,
        "stats": {
            "total_cycles": total_cycles,
            "total_repairs": total_repairs,
            "repair_types": repair_types,
        },
        "config": {k: v for k, v in config.items() if k != "config_id"},
    }


@router.post("/admin/system/repair-config")
async def update_repair_config(request: Request, body: RepairConfigUpdate):
    """Configure self-repair settings."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    update = {k: v for k, v in body.dict().items() if v is not None}
    if update:
        await db.repair_config.update_one(
            {"config_id": "main"},
            {"$set": update},
            upsert=True,
        )
    config = await _get_repair_config()
    return {"success": True, "config": config}
