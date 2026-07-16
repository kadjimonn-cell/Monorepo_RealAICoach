"""System Health Dashboard & Developer Workspace API — Platform monitoring, API console, database viewer."""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
import os
import logging
import psutil

from .db import db, require_admin
from utils.email_service import is_email_configured

router = APIRouter(prefix="/system")
logger = logging.getLogger(__name__)


# ── System Health ──


@router.get("/health/detailed")
async def detailed_health(request: Request):
    """Comprehensive system health check."""
    await require_admin(request)

    # System metrics
    cpu_pct = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # MongoDB health
    try:
        db_stats = await db.command("dbStats")
        db_healthy = True
        db_size_mb = round(db_stats.get("dataSize", 0) / 1024 / 1024, 2)
        db_collections = db_stats.get("collections", 0)
        db_indexes = db_stats.get("indexes", 0)
    except Exception:
        db_healthy = False
        db_size_mb = 0
        db_collections = 0
        db_indexes = 0

    # API latency (self-ping)
    import time

    start = time.time()
    await db.users.find_one({}, {"_id": 1})
    db_latency_ms = round((time.time() - start) * 1000, 1)

    # Active sessions
    active_sessions = await db.sessions.count_documents({}) if "sessions" in await db.list_collection_names() else 0

    # Error count (from security events)
    now = datetime.now(timezone.utc)
    hour_ago = (now - timedelta(hours=1)).isoformat()
    recent_errors = (
        await db.security_events.count_documents({"timestamp": {"$gte": hour_ago}})
        if "security_events" in await db.list_collection_names()
        else 0
    )

    # Background jobs
    jobs_info = []
    try:
        from scheduler import scheduler

        for job in scheduler.get_jobs():
            jobs_info.append({"id": job.id, "next_run": str(job.next_run_time)})
    except Exception:
        pass

    # WebSocket connections
    ws_info = {"active_connections": 0, "unique_users": 0}
    try:
        from utils.ws_manager import ws_manager

        ws_info["active_connections"] = sum(len(c) for c in ws_manager.connections.values())
        ws_info["unique_users"] = len(ws_manager.connections)
    except Exception:
        pass

    # Email service (last 24h)
    email_sent_24h = await db.email_logs.count_documents({"created_at": {"$gte": hour_ago}})

    # Hiring system metrics
    active_pipelines = await db.hiring_pipeline.count_documents({"current_stage": {"$ne": "offer_recommendation"}})
    active_video_rooms = await db.interview_rooms.count_documents({"status": {"$in": ["waiting", "active"]}})
    pending_interviews = await db.interview_bookings.count_documents({"status": {"$in": ["scheduled", "confirmed"]}})
    fairness_flags = await db.fairness_flags.count_documents({"status": "pending"})

    # LLM integration
    llm_configured = bool(os.environ.get("EMERGENT_LLM_KEY", ""))

    return {
        "status": "healthy" if db_healthy and cpu_pct < 90 else "degraded",
        "timestamp": now.isoformat(),
        "system": {
            "cpu_percent": cpu_pct,
            "memory": {
                "total_gb": round(mem.total / 1024**3, 2),
                "used_gb": round(mem.used / 1024**3, 2),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / 1024**3, 2),
                "used_gb": round(disk.used / 1024**3, 2),
                "percent": round(disk.percent, 1),
            },
        },
        "database": {
            "healthy": db_healthy,
            "latency_ms": db_latency_ms,
            "size_mb": db_size_mb,
            "collections": db_collections,
            "indexes": db_indexes,
        },
        "api": {"recent_errors": recent_errors, "active_sessions": active_sessions},
        "background_jobs": jobs_info,
        "websocket": ws_info,
        "email_service": {"sent_24h": email_sent_24h},
        "hiring_system": {
            "active_pipelines": active_pipelines,
            "active_video_rooms": active_video_rooms,
            "pending_interviews": pending_interviews,
            "pending_fairness_flags": fairness_flags,
        },
        "integrations": {
            "llm": "active" if llm_configured else "not_configured",
            "email": "active" if is_email_configured() else "not_configured",
        },
    }


# ── API Console ──


@router.get("/api/routes")
async def list_api_routes(request: Request):
    """List all registered API routes."""
    await require_admin(request)

    from server import app

    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            routes.append({"path": route.path, "methods": list(route.methods or []), "name": route.name or ""})
        elif hasattr(route, "routes"):
            for sub in route.routes:
                if hasattr(sub, "path") and hasattr(sub, "methods"):
                    prefix = getattr(route, "prefix", "")
                    routes.append(
                        {"path": f"{prefix}{sub.path}", "methods": list(sub.methods or []), "name": sub.name or ""}
                    )

    return {"routes": sorted(routes, key=lambda r: r["path"]), "total": len(routes)}


# ── Database Viewer ──


@router.get("/db/collections")
async def list_collections(request: Request):
    """List all database collections with stats."""
    await require_admin(request)

    names = await db.list_collection_names()
    collections = []
    for name in sorted(names):
        count = await db[name].count_documents({})
        indexes = [idx["name"] for idx in await db[name].list_indexes().to_list(50) if idx["name"] != "_id_"]
        collections.append({"name": name, "documents": count, "indexes": indexes, "index_count": len(indexes)})

    total_docs = sum(c["documents"] for c in collections)
    return {"collections": collections, "total_collections": len(collections), "total_documents": total_docs}


@router.get("/db/query/{collection}")
async def query_collection(collection: str, request: Request, limit: int = 20, skip: int = 0):
    """Query a collection (admin read-only)."""
    await require_admin(request)

    names = await db.list_collection_names()
    if collection not in names:
        raise HTTPException(status_code=404, detail="Collection not found")

    docs = await db[collection].find({}, {"_id": 0}).skip(skip).to_list(limit)
    total = await db[collection].count_documents({})
    return {"collection": collection, "documents": docs, "total": total, "limit": limit, "skip": skip}


# ── Logs Center ──


@router.get("/logs/backend")
async def get_backend_logs(request: Request, lines: int = 50):
    """Get recent backend logs."""
    await require_admin(request)

    logs = {"stdout": [], "stderr": []}
    for log_type, filename in [
        ("stdout", "/var/log/supervisor/backend.out.log"),
        ("stderr", "/var/log/supervisor/backend.err.log"),
    ]:
        try:
            with open(filename, "r") as f:
                all_lines = f.readlines()
                logs[log_type] = [line.strip() for line in all_lines[-lines:]]
        except FileNotFoundError:
            logs[log_type] = ["Log file not found"]

    return {"logs": logs, "lines_requested": lines}


@router.get("/logs/errors")
async def get_error_logs(request: Request, lines: int = 30):
    """Get recent error logs only."""
    await require_admin(request)

    errors = []
    try:
        with open("/var/log/supervisor/backend.err.log", "r") as f:
            for line in f.readlines()[-200:]:
                line = line.strip()
                if any(kw in line for kw in ["ERROR", "Exception", "Traceback", "CRITICAL", "Failed"]):
                    errors.append(line)
    except FileNotFoundError:
        pass

    return {"errors": errors[-lines:], "total_errors": len(errors)}


# ── Platform Stats ──


@router.get("/stats/platform")
async def platform_stats(request: Request):
    """Comprehensive platform statistics."""
    await require_admin(request)

    total_users = await db.users.count_documents({})
    active_users = await db.users.count_documents({"subscription_plan": {"$ne": "free"}})
    admin_users = await db.users.count_documents({"is_admin": True})

    # Content stats
    total_content = await db.video_pro_content.count_documents({})
    total_platform_txs = await db.platform_transactions.count_documents({})
    total_payments = await db.payments.count_documents({})
    total_actions = await db.action_history.count_documents({})

    # Collection sizes
    collections = await db.list_collection_names()
    total_collections = len(collections)
    total_docs = 0
    for col in collections:
        total_docs += await db[col].count_documents({})

    return {
        "users": {"total": total_users, "paid": active_users, "admins": admin_users},
        "content": {
            "video_pro": total_content,
            "platform_txs": total_platform_txs,
            "payments": total_payments,
            "actions_logged": total_actions,
        },
        "database": {"collections": total_collections, "total_documents": total_docs},
    }


# ── AI Model Management ──


@router.get("/ai/models")
async def ai_model_management(request: Request):
    """AI Model Management: active models, usage tracking, configuration."""
    await require_admin(request)

    from datetime import timedelta

    now = datetime.now(timezone.utc)
    seven_days = (now - timedelta(days=7)).isoformat()
    (now - timedelta(days=30)).isoformat()

    # Active AI models
    models = [
        {
            "id": "gpt-4o",
            "provider": "OpenAI (via Emergent LLM)",
            "type": "text-generation",
            "status": "active",
            "key_configured": bool(os.environ.get("EMERGENT_LLM_KEY")),
            "used_in": [
                "AI Chat",
                "Content Studio",
                "Fraud Detection",
                "KYC Analysis",
                "Predictions",
                "Recommendations",
            ],
        },
    ]

    # AI usage stats from ai_feedback
    total_ai_calls = await db.ai_feedback.count_documents({})
    recent_ai_calls = await db.ai_feedback.count_documents({"created_at": {"$gte": seven_days}})

    # Feature usage breakdown
    feature_pipe = [
        {"$group": {"_id": "$feature_key", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
    ]
    feature_usage = await db.ai_feedback.aggregate(feature_pipe).to_list(15)

    # AI access control stats
    ai_usage_total = (
        await db.ai_usage_tracking.count_documents({}) if "ai_usage_tracking" in await db.list_collection_names() else 0
    )

    # Tier usage
    tier_pipe = [
        {"$group": {"_id": "$feature", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    tier_usage = (
        await db.ai_usage_tracking.aggregate(tier_pipe).to_list(20)
        if "ai_usage_tracking" in await db.list_collection_names()
        else []
    )

    return {
        "models": models,
        "usage": {
            "total_ai_calls": total_ai_calls,
            "recent_7d": recent_ai_calls,
            "ai_tracking_total": ai_usage_total,
        },
        "feature_usage": feature_usage,
        "tier_usage": tier_usage,
    }


# ── Test Runner ──


@router.post("/tests/run")
async def run_platform_tests(request: Request):
    """Admin: Run the full platform test suite."""
    await require_admin(request)

    import subprocess

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_full_platform.py", "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app/backend",
        )
        passed = result.stdout.count(" PASSED")
        failed = result.stdout.count(" FAILED")
        errors = result.stdout.count(" ERROR")

        return {
            "success": result.returncode == 0,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": passed + failed + errors,
            "output": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Test suite timed out (120s limit)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
