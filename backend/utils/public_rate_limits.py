from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse

from utils.rate_limit import check_rate_limit


# Endpoint-specific public limits (requests/window)
PUBLIC_RATE_LIMIT_RULES: Dict[str, Tuple[int, int]] = {
    "system_vanity_metrics": (120, 60),
    "system_live_metrics": (180, 60),
    "config_global": (300, 60),
    "features_registry": (260, 60),
    "vitals_report": (320, 60),
    "certificate_engagement": (30, 60),
}


_stats_lock = Lock()
_public_rate_stats: Dict[str, Dict[str, object]] = defaultdict(
    lambda: {
        "allowed_count": 0,
        "blocked_count": 0,
        "last_seen_at": None,
        "last_blocked_at": None,
    }
)


def _get_client_ip(request: Request | None) -> str:
    if not request:
        return "unknown"
    forwarded = (request.headers.get("x-forwarded-for", "") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    real_ip = (request.headers.get("x-real-ip", "") or "").strip()
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return "unknown"


def _resolve_rule(endpoint_key: str, default_limit: int, default_window: int) -> tuple[int, int]:
    return PUBLIC_RATE_LIMIT_RULES.get(endpoint_key, (default_limit, default_window))


def enforce_public_rate_limit(
    request: Request | None,
    endpoint_key: str,
    default_limit: int,
    default_window: int,
):
    """Returns JSONResponse(429) when blocked, else None."""
    limit, window = _resolve_rule(endpoint_key, default_limit, default_window)
    client_ip = _get_client_ip(request)
    now_iso = datetime.now(timezone.utc).isoformat()

    allowed = check_rate_limit(f"public_endpoint:{endpoint_key}:{client_ip}", limit, window)

    with _stats_lock:
        stats = _public_rate_stats[endpoint_key]
        stats["last_seen_at"] = now_iso
        if allowed:
            stats["allowed_count"] = int(stats["allowed_count"] or 0) + 1
        else:
            stats["blocked_count"] = int(stats["blocked_count"] or 0) + 1
            stats["last_blocked_at"] = now_iso

    if allowed:
        return None

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again shortly.",
            "retry_after_seconds": window,
            "endpoint": endpoint_key,
        },
        headers={
            "Retry-After": str(window),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Window": str(window),
            "X-RateLimit-Endpoint": endpoint_key,
        },
    )


def get_public_rate_limit_stats() -> list[dict]:
    with _stats_lock:
        output = []
        for endpoint, stats in _public_rate_stats.items():
            allowed = int(stats.get("allowed_count") or 0)
            blocked = int(stats.get("blocked_count") or 0)
            total = allowed + blocked
            block_rate = round((blocked / total) * 100, 2) if total else 0.0
            limit, window = PUBLIC_RATE_LIMIT_RULES.get(endpoint, (0, 0))
            output.append(
                {
                    "endpoint": endpoint,
                    "limit": limit,
                    "window_seconds": window,
                    "allowed_count": allowed,
                    "blocked_count": blocked,
                    "block_rate_percent": block_rate,
                    "last_seen_at": stats.get("last_seen_at"),
                    "last_blocked_at": stats.get("last_blocked_at"),
                }
            )
        return sorted(output, key=lambda row: row.get("blocked_count", 0), reverse=True)
