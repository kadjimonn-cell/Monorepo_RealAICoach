"""Auto-Scaling Infrastructure — Rate limiting, connection pooling metrics, performance monitoring.

API:
- GET /api/admin/infra/metrics — Infrastructure metrics dashboard
- GET /api/admin/infra/rate-limits — Current rate limit config and usage
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import logging
import time

from routes.db import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory rate limit tracking
_request_counts = defaultdict(lambda: {"count": 0, "window_start": time.time()})
_endpoint_stats = defaultdict(lambda: {"calls": 0, "total_ms": 0, "errors": 0})

RATE_LIMITS = {
    "default": {"requests": 100, "window_seconds": 60},
    "auth": {"requests": 20, "window_seconds": 60},
    "ai-chat": {"requests": 30, "window_seconds": 60},
    "admin": {"requests": 200, "window_seconds": 60},
}


def check_rate_limit(user_id: str, endpoint_category: str = "default") -> dict:
    """Check if a user has exceeded their rate limit. Returns status."""
    limits = RATE_LIMITS.get(endpoint_category, RATE_LIMITS["default"])
    key = f"{user_id}:{endpoint_category}"
    now = time.time()

    entry = _request_counts[key]
    if now - entry["window_start"] > limits["window_seconds"]:
        _request_counts[key] = {"count": 1, "window_start": now}
        return {"allowed": True, "remaining": limits["requests"] - 1, "limit": limits["requests"]}

    entry["count"] += 1
    remaining = max(0, limits["requests"] - entry["count"])
    allowed = entry["count"] <= limits["requests"]
    return {"allowed": allowed, "remaining": remaining, "limit": limits["requests"]}


def record_endpoint_call(endpoint: str, latency_ms: float, error: bool = False):
    """Record an API call for performance tracking."""
    _endpoint_stats[endpoint]["calls"] += 1
    _endpoint_stats[endpoint]["total_ms"] += latency_ms
    if error:
        _endpoint_stats[endpoint]["errors"] += 1


@router.get("/admin/infra/metrics")
async def infra_metrics(request: Request):
    """Infrastructure metrics for executive dashboard."""
    user = await get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    twenty_four_h = (now - timedelta(hours=24)).isoformat()

    # API call metrics
    total_api_calls_24h = await db.usage_analytics.count_documents({"timestamp": {"$gte": twenty_four_h}})
    total_api_calls_1h = await db.usage_analytics.count_documents({"timestamp": {"$gte": one_hour_ago}})

    # Active connections (from sessions)
    active_sessions = await db.user_sessions.count_documents({"expires_at": {"$gte": now}})

    # Endpoint performance (from in-memory stats)
    endpoint_perf = []
    for ep, stats in sorted(_endpoint_stats.items(), key=lambda x: -x[1]["calls"]):
        avg_ms = round(stats["total_ms"] / max(stats["calls"], 1), 1)
        endpoint_perf.append(
            {
                "endpoint": ep,
                "calls": stats["calls"],
                "avg_latency_ms": avg_ms,
                "errors": stats["errors"],
                "error_rate": round((stats["errors"] / max(stats["calls"], 1)) * 100, 1),
            }
        )

    # Rate limit status
    active_limits = 0
    throttled = 0
    for key, entry in _request_counts.items():
        if time.time() - entry["window_start"] <= 60:
            active_limits += 1
            category = key.split(":")[-1] if ":" in key else "default"
            limit = RATE_LIMITS.get(category, RATE_LIMITS["default"])["requests"]
            if entry["count"] > limit:
                throttled += 1

    # Database connection pool (estimated)
    try:
        server_status = await db.command("serverStatus")
        current_conns = server_status.get("connections", {}).get("current", 0)
        available_conns = server_status.get("connections", {}).get("available", 0)
    except Exception:
        current_conns = 0
        available_conns = 0

    return {
        "api_metrics": {
            "calls_1h": total_api_calls_1h,
            "calls_24h": total_api_calls_24h,
            "active_sessions": active_sessions,
        },
        "rate_limiting": {
            "config": RATE_LIMITS,
            "active_trackers": active_limits,
            "throttled_users": throttled,
        },
        "connection_pool": {
            "current_connections": current_conns,
            "available_connections": available_conns,
        },
        "endpoint_performance": endpoint_perf[:20],
        "timestamp": now.isoformat(),
    }
