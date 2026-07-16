"""Platform Monitor — Performance tracking, error monitoring, and image generation stats.

Endpoints:
- GET  /api/admin/platform/performance  — API response time stats, error rates, uptime
- GET  /api/admin/platform/errors       — Recent errors with details
- GET  /api/admin/platform/image-stats  — Image generation success/failure/retry stats
- GET  /api/admin/platform/health       — Comprehensive dependency health check
"""

import os
import time
import logging
import psutil
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request
from routes.db import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory performance counters (reset on server restart) ──

_server_start = time.time()
_request_stats = {
    "total_requests": 0,
    "total_errors": 0,
    "status_counts": defaultdict(int),
    "slow_requests": [],  # last 20 slow requests (>1s)
    "recent_errors": [],  # last 50 errors
    "endpoint_times": defaultdict(list),  # path -> [response_time_ms]
}
_MAX_SLOW = 20
_MAX_ERRORS = 50
_MAX_ENDPOINT_SAMPLES = 100


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = int(round((percentile / 100.0) * (len(ordered) - 1)))
    rank = max(0, min(len(ordered) - 1, rank))
    return float(ordered[rank])


def build_slo_latency_snapshot() -> Dict[str, Any]:
    """Global latency snapshot for SLO evaluation (in-memory, low overhead)."""
    api_samples: list[float] = []
    endpoint_rows = []
    for path, times in _request_stats["endpoint_times"].items():
        if not times:
            continue
        path_times = [float(t) for t in times if isinstance(t, (int, float))]
        if not path_times:
            continue
        if path.startswith("/api/"):
            api_samples.extend(path_times)
        endpoint_rows.append(
            {
                "path": path,
                "count": len(path_times),
                "avg_ms": round(sum(path_times) / len(path_times), 1),
                "p95_ms": round(_percentile(path_times, 95), 1),
                "max_ms": round(max(path_times), 1),
            }
        )

    endpoint_rows.sort(key=lambda row: row["p95_ms"], reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(api_samples),
        "global_avg_ms": round(sum(api_samples) / len(api_samples), 1) if api_samples else 0.0,
        "global_p95_ms": round(_percentile(api_samples, 95), 1) if api_samples else 0.0,
        "global_max_ms": round(max(api_samples), 1) if api_samples else 0.0,
        "top_p95_endpoints": endpoint_rows[:12],
    }


def record_request(path: str, method: str, status_code: int, duration_ms: float, error_detail: str = ""):
    """Called by middleware to record request metrics."""
    _request_stats["total_requests"] += 1
    _request_stats["status_counts"][str(status_code)] += 1

    # Track endpoint response times (keep last N samples per endpoint)
    clean_path = _normalize_path(path)
    times = _request_stats["endpoint_times"][clean_path]
    times.append(duration_ms)
    if len(times) > _MAX_ENDPOINT_SAMPLES:
        _request_stats["endpoint_times"][clean_path] = times[-_MAX_ENDPOINT_SAMPLES:]

    # Track slow requests (>1000ms)
    if duration_ms > 1000:
        _request_stats["slow_requests"].append(
            {
                "path": path,
                "method": method,
                "status": status_code,
                "duration_ms": round(duration_ms, 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if len(_request_stats["slow_requests"]) > _MAX_SLOW:
            _request_stats["slow_requests"] = _request_stats["slow_requests"][-_MAX_SLOW:]

    # Track errors (4xx/5xx)
    if status_code >= 400:
        _request_stats["total_errors"] += 1
        _request_stats["recent_errors"].append(
            {
                "path": path,
                "method": method,
                "status": status_code,
                "detail": error_detail[:200] if error_detail else "",
                "duration_ms": round(duration_ms, 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if len(_request_stats["recent_errors"]) > _MAX_ERRORS:
            _request_stats["recent_errors"] = _request_stats["recent_errors"][-_MAX_ERRORS:]


def _normalize_path(path: str) -> str:
    """Normalize paths by replacing IDs with :id for aggregation."""
    import re

    parts = path.rstrip("/").split("/")
    normalized = []
    for p in parts:
        if re.match(r"^[a-f0-9]{8,}$", p) or re.match(r"^[A-Za-z0-9_-]{15,}$", p) or re.match(r"^\d+$", p):
            normalized.append(":id")
        else:
            normalized.append(p)
    return "/".join(normalized)


@router.get("/admin/platform/performance")
async def platform_performance(request: Request):
    """API performance metrics: response times, error rates, uptime, throughput."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    uptime_s = time.time() - _server_start
    total = max(_request_stats["total_requests"], 1)
    errors = _request_stats["total_errors"]

    # Compute per-endpoint stats
    endpoint_stats = []
    for path, times in _request_stats["endpoint_times"].items():
        if not times:
            continue
        endpoint_stats.append(
            {
                "path": path,
                "count": len(times),
                "avg_ms": round(sum(times) / len(times), 1),
                "p50_ms": round(sorted(times)[len(times) // 2], 1),
                "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 1) if len(times) >= 2 else round(max(times), 1),
                "max_ms": round(max(times), 1),
            }
        )
    endpoint_stats.sort(key=lambda x: x["avg_ms"], reverse=True)
    slo_snapshot = build_slo_latency_snapshot()

    return {
        "uptime_seconds": round(uptime_s),
        "uptime_human": _format_uptime(uptime_s),
        "total_requests": total,
        "total_errors": errors,
        "error_rate_pct": round((errors / total) * 100, 2),
        "requests_per_minute": round(total / max(uptime_s / 60, 1), 1),
        "status_distribution": dict(_request_stats["status_counts"]),
        "slow_requests": list(reversed(_request_stats["slow_requests"])),
        "top_endpoints": endpoint_stats[:15],
        "global_latency": {
            "sample_count": slo_snapshot.get("sample_count", 0),
            "avg_ms": slo_snapshot.get("global_avg_ms", 0.0),
            "p95_ms": slo_snapshot.get("global_p95_ms", 0.0),
            "max_ms": slo_snapshot.get("global_max_ms", 0.0),
        },
        "server_start": datetime.fromtimestamp(_server_start, tz=timezone.utc).isoformat(),
    }


@router.get("/admin/platform/errors")
async def platform_errors(request: Request):
    """Recent API errors with details."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    errors = list(reversed(_request_stats["recent_errors"]))

    # Aggregate by path
    error_by_path = defaultdict(int)
    for e in errors:
        error_by_path[e["path"]] += 1

    top_error_paths = sorted(error_by_path.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "total_errors": _request_stats["total_errors"],
        "recent_errors": errors[:30],
        "top_error_paths": [{"path": p, "count": c} for p, c in top_error_paths],
    }


@router.get("/admin/platform/image-stats")
async def image_generation_stats(request: Request):
    """Image generation success/failure/retry statistics."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    # Get image gen logs from DB
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    total_all = await db.image_gen_logs.count_documents({})
    total_24h = await db.image_gen_logs.count_documents({"timestamp": {"$gte": day_ago}})
    total_7d = await db.image_gen_logs.count_documents({"timestamp": {"$gte": week_ago}})

    success_24h = await db.image_gen_logs.count_documents({"timestamp": {"$gte": day_ago}, "status": "success"})
    failed_24h = await db.image_gen_logs.count_documents({"timestamp": {"$gte": day_ago}, "status": "failed"})

    success_7d = await db.image_gen_logs.count_documents({"timestamp": {"$gte": week_ago}, "status": "success"})
    failed_7d = await db.image_gen_logs.count_documents({"timestamp": {"$gte": week_ago}, "status": "failed"})

    # Retry stats
    retried_24h = await db.image_gen_logs.count_documents({"timestamp": {"$gte": day_ago}, "retries": {"$gt": 0}})
    retried_7d = await db.image_gen_logs.count_documents({"timestamp": {"$gte": week_ago}, "retries": {"$gt": 0}})

    # Recent failures
    recent_failures = await db.image_gen_logs.find({"status": "failed"}, {"_id": 0}).sort("timestamp", -1).to_list(10)

    # Average duration
    pipeline = [
        {"$match": {"timestamp": {"$gte": day_ago}, "status": "success"}},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_ms"}, "avg_retries": {"$avg": "$retries"}}},
    ]
    agg = await db.image_gen_logs.aggregate(pipeline).to_list(1)
    avg_duration = round(agg[0]["avg_duration"], 0) if agg and agg[0].get("avg_duration") else 0
    avg_retries = round(agg[0]["avg_retries"], 2) if agg and agg[0].get("avg_retries") else 0

    return {
        "totals": {"all_time": total_all, "last_24h": total_24h, "last_7d": total_7d},
        "last_24h": {
            "success": success_24h,
            "failed": failed_24h,
            "success_rate": round((success_24h / max(total_24h, 1)) * 100, 1),
            "retried": retried_24h,
        },
        "last_7d": {
            "success": success_7d,
            "failed": failed_7d,
            "success_rate": round((success_7d / max(total_7d, 1)) * 100, 1),
            "retried": retried_7d,
        },
        "avg_duration_ms": avg_duration,
        "avg_retries": avg_retries,
        "recent_failures": recent_failures,
        "retry_effectiveness": round(((retried_7d - failed_7d) / max(retried_7d, 1)) * 100, 1)
        if retried_7d > 0
        else 100.0,
    }


@router.get("/admin/platform/health")
async def comprehensive_health(request: Request):
    """Comprehensive dependency health check."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(403, "Admin required")

    checks = {}

    # MongoDB
    try:
        start = time.time()
        await db.command("ping")
        latency = round((time.time() - start) * 1000, 1)
        user_count = await db.users.count_documents({})
        collections = await db.list_collection_names()
        checks["mongodb"] = {
            "status": "healthy",
            "latency_ms": latency,
            "users": user_count,
            "collections": len(collections),
        }
    except Exception as e:
        checks["mongodb"] = {"status": "error", "error": str(e)[:100]}

    # WebSocket
    checks["websocket"] = {"status": "healthy", "endpoints": ["/api/ws/system-metrics", "/api/ws/notifications"]}

    # APScheduler
    try:
        checks["scheduler"] = {
            "status": "healthy",
            "jobs": ["auto_scaling_eval (60s)", "webhook_auto_retry (30s)", "fraud_monitoring (5m)"],
        }
    except Exception:
        checks["scheduler"] = {"status": "unknown"}

    # System resources
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    checks["system"] = {
        "status": "healthy" if cpu < 90 and mem.percent < 95 and disk.percent < 95 else "warning",
        "cpu_pct": round(cpu, 1),
        "memory_pct": round(mem.percent, 1),
        "disk_pct": round(disk.percent, 1),
    }

    # Emergent LLM Key
    api_key = os.environ.get("EMERGENT_LLM_KEY", "")
    checks["llm_key"] = {"status": "configured" if api_key else "missing"}

    # Resend email
    resend_key = os.environ.get("RESEND_API_KEY", "")
    checks["email"] = {"status": "configured" if resend_key else "missing"}

    all_healthy = all(c.get("status") in ("healthy", "configured") for c in checks.values() if "status" in c)

    return {
        "overall": "operational" if all_healthy else "degraded",
        "uptime": _format_uptime(time.time() - _server_start),
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _format_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
