from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
import re

from routes.db import db, require_admin


router = APIRouter(prefix="/auth-compliance", tags=["Auth Compliance"])


class RouteBlockEventRequest(BaseModel):
    path: str
    reason: str = "unauthenticated_route_block"
    source: str = "frontend-route-guard"
    referrer: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
        if ip:
            return ip

    for key in ("cf-connecting-ip", "x-real-ip"):
        ip = request.headers.get(key, "").strip()
        if ip:
            return ip

    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def _safe_path(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "/unknown"
    if not value.startswith("/"):
        value = f"/{value}"
    return value[:220]


def _safe_text(raw: str, default: str, max_len: int = 120) -> str:
    value = (raw or "").strip()
    if not value:
        return default
    return value[:max_len]


@router.post("/route-block")
async def log_route_block_event(request: Request, payload: RouteBlockEventRequest):
    """Public endpoint: logs blocked route access attempts for security compliance analytics."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    minute_bucket = now.strftime("%Y-%m-%dT%H:%M")
    day_bucket = now.date().isoformat()

    path = _safe_path(payload.path)
    reason = _safe_text(payload.reason, "unauthenticated_route_block")
    source = _safe_text(payload.source, "frontend-route-guard")
    referrer = _safe_text(payload.referrer or "", "", max_len=300)

    user_agent = _safe_text(request.headers.get("user-agent", "unknown"), "unknown", max_len=240)
    ip_address = _extract_ip(request)
    country_code = _safe_text(request.headers.get("cf-ipcountry", "UNK"), "UNK", max_len=8).upper()

    fingerprint_raw = f"{ip_address}|{user_agent[:140]}"
    fingerprint_hash = sha256(fingerprint_raw.encode()).hexdigest()
    event_key = sha256(f"{fingerprint_hash}|{path}|{reason}|{minute_bucket}".encode()).hexdigest()

    await db.auth_route_block_events.update_one(
        {"event_key": event_key},
        {
            "$setOnInsert": {
                "event_id": f"auth_block_{uuid.uuid4().hex[:12]}",
                "event_key": event_key,
                "path": path,
                "reason": reason,
                "source": source,
                "fingerprint_hash": fingerprint_hash,
                "ip_address": ip_address,
                "country_code": country_code,
                "user_agent": user_agent,
                "day_bucket": day_bucket,
                "minute_bucket": minute_bucket,
                "created_at": now_iso,
                "first_seen_at": now_iso,
            },
            "$set": {
                "last_seen_at": now_iso,
                "updated_at": now_iso,
                "latest_referrer": referrer,
            },
            "$inc": {"hit_count": 1},
        },
        upsert=True,
    )

    return {"ok": True, "logged_at": now_iso}


@router.get("/admin/overview")
async def auth_compliance_overview(
    request: Request,
    time_range: str = Query("24h"),
    route_prefix: str = Query(""),
    country: str = Query(""),
    fingerprint: str = Query(""),
):
    await require_admin(request)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    cutoff_1h = (now - timedelta(hours=1)).isoformat()

    base_rows = await db.auth_route_block_events.find(
        {"created_at": {"$gte": cutoff_7d}},
        {"_id": 0},
    ).sort("last_seen_at", -1).limit(8000).to_list(8000)

    rows_24h = [row for row in base_rows if str(row.get("created_at", "")) >= cutoff_24h]

    range_map = {
        "1h": (now - timedelta(hours=1)).isoformat(),
        "24h": cutoff_24h,
        "7d": cutoff_7d,
        "30d": cutoff_30d,
    }
    range_labels = {
        "1h": "last 1 hour",
        "24h": "last 24 hours",
        "7d": "last 7 days",
        "30d": "last 30 days",
    }
    selected_range = (time_range or "24h").strip().lower()
    if selected_range not in range_map:
        selected_range = "24h"

    filter_query: Dict[str, Any] = {"created_at": {"$gte": range_map[selected_range]}}
    cleaned_route_prefix = _safe_text(route_prefix, "", max_len=160)
    cleaned_country = _safe_text(country, "", max_len=12).upper()
    cleaned_fingerprint = _safe_text(fingerprint, "", max_len=64).lower()

    if cleaned_route_prefix:
        filter_query["path"] = {"$regex": f"^{re.escape(cleaned_route_prefix)}"}
    if cleaned_country:
        filter_query["country_code"] = cleaned_country
    if cleaned_fingerprint:
        filter_query["fingerprint_hash"] = {"$regex": f"^{re.escape(cleaned_fingerprint)}"}

    filtered_rows = await db.auth_route_block_events.find(
        filter_query,
        {"_id": 0},
    ).sort("last_seen_at", -1).limit(12000).to_list(12000)

    filtered_rows_1h = [row for row in filtered_rows if str(row.get("created_at", "")) >= cutoff_1h]

    def hits(items: List[Dict[str, Any]]) -> int:
        return sum(int(item.get("hit_count", 0) or 0) for item in items)

    total_hits_24h = hits(rows_24h)
    total_hits_7d = hits(base_rows)
    filtered_hits = hits(filtered_rows)

    unique_fingerprints_24h = len({row.get("fingerprint_hash") for row in rows_24h if row.get("fingerprint_hash")})
    unique_fingerprints_7d = len({row.get("fingerprint_hash") for row in base_rows if row.get("fingerprint_hash")})
    filtered_unique_fingerprints = len({row.get("fingerprint_hash") for row in filtered_rows if row.get("fingerprint_hash")})

    route_map: Dict[str, int] = {}
    for row in filtered_rows:
        route = str(row.get("path") or "/unknown")
        route_map[route] = route_map.get(route, 0) + int(row.get("hit_count", 0) or 0)
    top_routes = [
        {"path": path, "hits": count}
        for path, count in sorted(route_map.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    geo_map: Dict[str, int] = {}
    for row in filtered_rows:
        country = str(row.get("country_code") or "UNK")
        geo_map[country] = geo_map.get(country, 0) + int(row.get("hit_count", 0) or 0)
    geo_summary = [
        {"country_code": country, "hits": count}
        for country, count in sorted(geo_map.items(), key=lambda x: x[1], reverse=True)[:12]
    ]

    spike_map: Dict[str, Dict[str, Any]] = {}
    for row in filtered_rows_1h:
        fp = str(row.get("fingerprint_hash") or "unknown")
        item = spike_map.setdefault(
            fp,
            {
                "fingerprint_hash": fp,
                "hits": 0,
                "sample_path": row.get("path", "/unknown"),
                "country_code": row.get("country_code", "UNK"),
                "latest_seen_at": row.get("last_seen_at"),
            },
        )
        item["hits"] += int(row.get("hit_count", 0) or 0)
        item["latest_seen_at"] = max(str(item.get("latest_seen_at") or ""), str(row.get("last_seen_at") or ""))

    suspicious_spikes = [
        item for item in sorted(spike_map.values(), key=lambda x: x["hits"], reverse=True)
        if int(item.get("hits", 0)) >= 5
    ][:8]

    latest_events = [
        {
            "event_id": row.get("event_id"),
            "path": row.get("path"),
            "hits": int(row.get("hit_count", 0) or 0),
            "reason": row.get("reason"),
            "country_code": row.get("country_code"),
            "last_seen_at": row.get("last_seen_at"),
            "fingerprint_hash": str(row.get("fingerprint_hash") or "")[:18],
        }
        for row in filtered_rows[:30]
    ]

    if filtered_hits <= 20:
        status = "healthy"
    elif filtered_hits <= 120:
        status = "warning"
    else:
        status = "critical"

    return {
        "generated_at": now_iso,
        "status": status,
        "window_definitions": {
            "window_24h": "last 24 hours",
            "window_7d": "last 7 days",
            "window_1h": "last 1 hour",
            "window_30d": "last 30 days",
        },
        "overview": {
            "unauthorized_route_blocks_24h": total_hits_24h,
            "unauthorized_route_blocks_7d": total_hits_7d,
            "unique_fingerprints_24h": unique_fingerprints_24h,
            "unique_fingerprints_7d": unique_fingerprints_7d,
            "suspicious_retry_spikes_1h": len(suspicious_spikes),
        },
        "applied_filters": {
            "time_range": selected_range,
            "time_range_label": range_labels[selected_range],
            "route_prefix": cleaned_route_prefix,
            "country": cleaned_country,
            "fingerprint": cleaned_fingerprint,
        },
        "filtered_overview": {
            "window": selected_range,
            "window_label": range_labels[selected_range],
            "unauthorized_route_blocks": filtered_hits,
            "unique_fingerprints": filtered_unique_fingerprints,
            "suspicious_retry_spikes_1h": len(suspicious_spikes),
            "records_considered": len(filtered_rows),
        },
        "top_blocked_routes": top_routes,
        "geo_summary": geo_summary,
        "suspicious_spikes": suspicious_spikes,
        "latest_events": latest_events,
    }
