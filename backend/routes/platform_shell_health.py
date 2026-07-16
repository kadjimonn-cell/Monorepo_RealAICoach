from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request
from observability.request_context import extract_request_observability_context

router = APIRouter(prefix="/platform-shell-health", tags=["Platform Shell Health"])

SHELL_HEALTH_COLLECTION = "shell_health_events"
REALTIME_HEALTH_COLLECTION = "realtime_connection_health_events"
PREVIEW_HEALTH_COLLECTION = "preview_shell_health_events"


async def _get_db():
    from routes.db import db
    return db


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _extract_host(url: str) -> str:
    if not isinstance(url, str) or not url:
        return ""
    try:
        if "//" in url:
            host_part = url.split("//", 1)[1]
            return host_part.split("/", 1)[0].lower()
        return ""
    except Exception:
        return ""


@router.post("/ingest")
async def ingest_shell_health(request: Request):
    """Best-effort client-side shell resilience telemetry ingest."""
    db = await _get_db()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    counters = payload.get("counters") if isinstance(payload.get("counters"), dict) else {}
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    sanitized_events = []
    for item in events[:25]:
        if not isinstance(item, dict):
            continue
        sanitized_events.append({
            "metric": str(item.get("metric") or "unknown"),
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "pathname": str(item.get("pathname") or payload.get("pathname") or ""),
            "timestamp": str(item.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        })

    obs_ctx = extract_request_observability_context(request)

    doc = {
        "timestamp": datetime.now(timezone.utc),
        "client_id": str(payload.get("client_id") or "unknown"),
        "pathname": str(payload.get("pathname") or ""),
        "user_agent": str(payload.get("user_agent") or request.headers.get("user-agent", ""))[:300],
        "captured_at": str(payload.get("captured_at") or datetime.now(timezone.utc).isoformat()),
        "correlation_id": str(getattr(request.state, "correlation_id", "") or obs_ctx.get("correlation_id") or ""),
        "trace_id": str(getattr(request.state, "trace_id", "") or obs_ctx.get("trace_id") or ""),
        "span_id": str(getattr(request.state, "span_id", "") or obs_ctx.get("span_id") or ""),
        "session_id": str(getattr(request.state, "session_id", "") or obs_ctx.get("session_id") or ""),
        "counters": {
            "dedupe_hits": int(counters.get("dedupe_hits") or 0),
            "fallback_activations": int(counters.get("fallback_activations") or 0),
            "route_recoveries": int(counters.get("route_recoveries") or 0),
            "rate_limit_429s": int(counters.get("rate_limit_429s") or 0),
        },
        "events": sanitized_events,
    }
    await db[SHELL_HEALTH_COLLECTION].insert_one(doc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    await db[SHELL_HEALTH_COLLECTION].delete_many({"timestamp": {"$lt": cutoff}})
    return {"ok": True}


@router.post("/realtime-ingest")
async def ingest_realtime_health(request: Request):
    """Best-effort websocket reconnect/backoff telemetry ingest for admin observability."""
    db = await _get_db()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    raw_events = payload.get("events") if isinstance(payload.get("events"), list) else []
    sanitized_events = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for item in raw_events[:30]:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        sanitized_events.append(
            {
                "event_type": str(item.get("event_type") or "unknown")[:60],
                "timestamp": str(item.get("timestamp") or now_iso),
                "connected": bool(item.get("connected") is True),
                "reconnect_attempt": int(item.get("reconnect_attempt") or 0),
                "backoff_ms": int(item.get("backoff_ms") or 0),
                "consecutive_failures": int(item.get("consecutive_failures") or 0),
                "metadata": {
                    "close_code": int(metadata.get("close_code") or 0) if str(metadata.get("close_code") or "").isdigit() else metadata.get("close_code"),
                    "close_reason": str(metadata.get("close_reason") or "")[:200],
                    "next_backoff_ms": int(metadata.get("next_backoff_ms") or 0),
                    "opened_at": str(metadata.get("opened_at") or "")[:80],
                    "message": str(metadata.get("message") or "")[:200],
                },
            }
        )

    obs_ctx = extract_request_observability_context(request)

    doc = {
        "timestamp": datetime.now(timezone.utc),
        "captured_at": str(payload.get("captured_at") or now_iso),
        "client_id": str(payload.get("client_id") or "unknown")[:120],
        "user_id": str(payload.get("user_id") or "")[:80],
        "pathname": str(payload.get("pathname") or "")[:200],
        "user_agent": str(request.headers.get("user-agent", ""))[:300],
        "correlation_id": str(getattr(request.state, "correlation_id", "") or obs_ctx.get("correlation_id") or ""),
        "trace_id": str(getattr(request.state, "trace_id", "") or obs_ctx.get("trace_id") or ""),
        "span_id": str(getattr(request.state, "span_id", "") or obs_ctx.get("span_id") or ""),
        "session_id": str(getattr(request.state, "session_id", "") or obs_ctx.get("session_id") or ""),
        "events": sanitized_events,
    }

    await db[REALTIME_HEALTH_COLLECTION].insert_one(doc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    await db[REALTIME_HEALTH_COLLECTION].delete_many({"timestamp": {"$lt": cutoff}})
    return {"ok": True, "events_ingested": len(sanitized_events)}


@router.post("/preview-ingest")
async def ingest_preview_shell_health(request: Request):
    """Capture preview/iframe render telemetry for black-screen investigations."""
    db = await _get_db()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    render = payload.get("render") if isinstance(payload.get("render"), dict) else {}
    challenge = payload.get("challenge_signals") if isinstance(payload.get("challenge_signals"), dict) else {}

    obs_ctx = extract_request_observability_context(request)

    doc = {
        "timestamp": datetime.now(timezone.utc),
        "captured_at": str(payload.get("captured_at") or datetime.now(timezone.utc).isoformat()),
        "event_type": str(payload.get("event_type") or "layout_mounted")[:80],
        "client_id": str(payload.get("client_id") or "unknown")[:120],
        "pathname": str(payload.get("pathname") or "")[:300],
        "href": str(payload.get("href") or "")[:600],
        "host": str(payload.get("host") or "")[:200],
        "referrer": str(payload.get("referrer") or "")[:600],
        "referrer_host": str(payload.get("referrer_host") or _extract_host(str(payload.get("referrer") or "")))[:200],
        "embedded": bool(payload.get("embedded") is True),
        "visibility_state": str(payload.get("visibility_state") or "")[:40],
        "ready_state": str(payload.get("ready_state") or "")[:40],
        "cookie_enabled": bool(payload.get("cookie_enabled") is True),
        "user_agent": str(payload.get("user_agent") or request.headers.get("user-agent", ""))[:300],
        "correlation_id": str(getattr(request.state, "correlation_id", "") or obs_ctx.get("correlation_id") or ""),
        "trace_id": str(getattr(request.state, "trace_id", "") or obs_ctx.get("trace_id") or ""),
        "span_id": str(getattr(request.state, "span_id", "") or obs_ctx.get("span_id") or ""),
        "session_id": str(getattr(request.state, "session_id", "") or obs_ctx.get("session_id") or ""),
        "challenge_signals": {
            "has_cf_challenge_script": bool(challenge.get("has_cf_challenge_script") is True),
            "has_cf_turnstile_iframe": bool(challenge.get("has_cf_turnstile_iframe") is True),
            "contains_checking_browser_text": bool(challenge.get("contains_checking_browser_text") is True),
            "contains_enable_js_text": bool(challenge.get("contains_enable_js_text") is True),
        },
        "render": {
            "root_present": bool(render.get("root_present") is True),
            "app_ready": bool(render.get("app_ready") is True),
            "element_count": _safe_int(render.get("element_count"), 0),
            "text_length": _safe_int(render.get("text_length"), 0),
        },
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }

    await db[PREVIEW_HEALTH_COLLECTION].insert_one(doc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    await db[PREVIEW_HEALTH_COLLECTION].delete_many({"timestamp": {"$lt": cutoff}})
    return {"ok": True}


@router.get("/admin/preview-summary")
async def admin_preview_shell_health_summary(request: Request, hours: int = 24, limit: int = 2000):
    """Admin summary for preview black-screen telemetry and challenge correlation."""
    from routes.db import require_admin

    await require_admin(request)
    db = await _get_db()

    h = max(1, min(hours, 168))
    lim = max(100, min(limit, 10000))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=h)

    rows = await db[PREVIEW_HEALTH_COLLECTION].find(
        {"timestamp": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("timestamp", -1).limit(lim).to_list(lim)

    total = len(rows)
    embedded = 0
    challenge = 0
    blank_suspected = 0
    by_host = {}
    by_event_type = {}

    for row in rows:
        host = str(row.get("host") or "unknown")
        event_type = str(row.get("event_type") or "unknown")
        by_host[host] = by_host.get(host, 0) + 1
        by_event_type[event_type] = by_event_type.get(event_type, 0) + 1

        is_embedded = bool(row.get("embedded") is True)
        if is_embedded:
            embedded += 1

        challenge_signals = row.get("challenge_signals") or {}
        has_challenge = bool(
            challenge_signals.get("has_cf_challenge_script")
            or challenge_signals.get("has_cf_turnstile_iframe")
            or challenge_signals.get("contains_checking_browser_text")
            or challenge_signals.get("contains_enable_js_text")
        )
        if has_challenge:
            challenge += 1

        render = row.get("render") or {}
        app_ready = bool(render.get("app_ready") is True)
        low_content = _safe_int(render.get("element_count"), 0) < 25 and _safe_int(render.get("text_length"), 0) < 30
        if is_embedded and has_challenge and (not app_ready or low_content):
            blank_suspected += 1

    return {
        "hours": h,
        "rows_analyzed": total,
        "embedded_events": embedded,
        "challenge_signal_events": challenge,
        "blank_screen_suspected_events": blank_suspected,
        "by_host": by_host,
        "by_event_type": by_event_type,
        "latest_samples": rows[:20],
    }