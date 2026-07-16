"""Unified Observability Center APIs (real-data only)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from fastapi import APIRouter, Request

from routes.db import db, require_admin

router = APIRouter(prefix="/admin/observability", tags=["Observability Center"])


def _safe_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


@router.get("/overview")
async def observability_overview(request: Request):
    await require_admin(request)

    now = datetime.now(timezone.utc)
    one_hour = now - timedelta(hours=1)
    twenty_four_hours = now - timedelta(hours=24)

    metrics_doc = await db.system_metrics.find_one(sort=[("created_at", -1)], projection={"_id": 0})
    web_vitals_pipe = [
        {"$match": {"timestamp": {"$gte": twenty_four_hours}}},
        {
            "$group": {
                "_id": None,
                "samples": {"$sum": 1},
                "avg_lcp": {"$avg": "$lcp"},
                "avg_cls": {"$avg": "$cls"},
                "avg_inp": {"$avg": "$inp"},
                "avg_ttfb": {"$avg": "$ttfb"},
            }
        },
    ]
    web_vitals_rows = await db.web_vitals.aggregate(web_vitals_pipe).to_list(1)
    web_vitals = web_vitals_rows[0] if web_vitals_rows else {"samples": 0, "avg_lcp": 0, "avg_cls": 0, "avg_inp": 0, "avg_ttfb": 0}

    api_requests_1h = await db.perf_snapshots.count_documents({"timestamp": {"$gte": one_hour.isoformat()}})
    perf_alerts_24h = await db.performance_alerts.count_documents({"timestamp": {"$gte": twenty_four_hours.isoformat()}})
    siem_alerts_open = await db.siem_triggered_alerts.count_documents({"status": {"$ne": "resolved"}})
    client_errors_24h = await db.client_errors.count_documents({"created_at": {"$gte": twenty_four_hours}})
    security_events_24h = await db.security_events.count_documents({"timestamp": {"$gte": twenty_four_hours.isoformat()}})

    gps_health = await db.gps_runtime_incidents.find_one(sort=[("created_at", -1)], projection={"_id": 0, "created_at": 1, "component": 1, "error": 1})
    if gps_health:
        gps_health = {
            **gps_health,
            "severity": "critical",
        }

    shell_total_24h = await db.shell_health_events.count_documents({"timestamp": {"$gte": twenty_four_hours}})
    shell_with_trace_24h = await db.shell_health_events.count_documents({
        "timestamp": {"$gte": twenty_four_hours},
        "trace_id": {"$exists": True, "$nin": ["", None]},
    })

    return {
        "timestamp": now.isoformat(),
        "system": {
            "latest_snapshot": metrics_doc or {},
        },
        "application": {
            "api_snapshots_1h": int(api_requests_1h),
            "perf_alerts_24h": int(perf_alerts_24h),
            "client_errors_24h": int(client_errors_24h),
            "security_events_24h": int(security_events_24h),
        },
        "frontend_experience": {
            "samples_24h": int(web_vitals.get("samples") or 0),
            "avg_lcp": round(float(web_vitals.get("avg_lcp") or 0.0), 3),
            "avg_cls": round(float(web_vitals.get("avg_cls") or 0.0), 4),
            "avg_inp": round(float(web_vitals.get("avg_inp") or 0.0), 1),
            "avg_ttfb": round(float(web_vitals.get("avg_ttfb") or 0.0), 3),
        },
        "alerts": {
            "siem_open": int(siem_alerts_open),
            "performance_24h": int(perf_alerts_24h),
        },
        "gps_health": gps_health or {},
        "correlation": {
            "shell_events_24h": int(shell_total_24h),
            "shell_events_with_trace_24h": int(shell_with_trace_24h),
            "shell_trace_coverage_pct": _safe_pct(shell_with_trace_24h, shell_total_24h),
        },
    }


@router.get("/correlation-audit")
async def correlation_audit(request: Request):
    await require_admin(request)

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    collections = [
        ("web_vitals", "timestamp"),
        ("page_perf_metrics", "timestamp"),
        ("shell_health_events", "timestamp"),
        ("realtime_connection_health_events", "timestamp"),
        ("preview_shell_health_events", "timestamp"),
        ("client_errors", "created_at"),
        ("session_replay_events", "timestamp"),
    ]

    rows = []
    for name, ts_field in collections:
        time_filter = since.isoformat() if name == "session_replay_events" else since
        query = {ts_field: {"$gte": time_filter}}
        total = await db[name].count_documents(query)
        trace_count = await db[name].count_documents({
            **query,
            "trace_id": {"$exists": True, "$nin": ["", None]},
        })
        corr_count = await db[name].count_documents({
            **query,
            "correlation_id": {"$exists": True, "$nin": ["", None]},
        })

        rows.append(
            {
                "collection": name,
                "window_hours": 24,
                "total": int(total),
                "with_trace_id": int(trace_count),
                "with_correlation_id": int(corr_count),
                "trace_coverage_pct": _safe_pct(trace_count, total),
                "correlation_coverage_pct": _safe_pct(corr_count, total),
            }
        )

    return {
        "timestamp": now.isoformat(),
        "rows": rows,
    }


@router.get("/recent-logs")
async def recent_structured_logs(request: Request, limit: int = 50):
    await require_admin(request)
    safe_limit = max(1, min(int(limit or 50), 200))

    log_file = Path("/var/log/supervisor/backend.err.log")
    if not log_file.exists():
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "logs": []}

    lines = log_file.read_text(errors="ignore").splitlines()
    rows = []
    for line in reversed(lines):
        text = line.strip()
        if not text:
            continue
        if not text.startswith("{"):
            continue
        try:
            parsed = json.loads(text)
            rows.append(parsed)
        except Exception:
            continue
        if len(rows) >= safe_limit:
            break

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "logs": rows,
    }


@router.get("/recent-traces")
async def recent_trace_samples(request: Request, limit: int = 40):
    await require_admin(request)
    safe_limit = max(1, min(int(limit or 40), 150))

    pipelines = [
        ("shell_health_events", "timestamp", "shell_health"),
        ("client_errors", "created_at", "client_error"),
        ("page_perf_metrics", "timestamp", "page_performance"),
    ]
    samples = []

    for collection_name, ts_field, source in pipelines:
        docs = await db[collection_name].find(
            {"trace_id": {"$exists": True, "$nin": ["", None]}},
            {
                "_id": 0,
                ts_field: 1,
                "trace_id": 1,
                "span_id": 1,
                "correlation_id": 1,
                "session_id": 1,
                "pathname": 1,
                "route": 1,
                "page": 1,
                "message": 1,
            },
        ).sort(ts_field, -1).limit(safe_limit).to_list(safe_limit)

        for doc in docs:
            timestamp_val = doc.get(ts_field)
            if isinstance(timestamp_val, datetime):
                timestamp_iso = timestamp_val.isoformat()
            else:
                timestamp_iso = str(timestamp_val or "")
            samples.append(
                {
                    "source": source,
                    "timestamp": timestamp_iso,
                    "trace_id": doc.get("trace_id"),
                    "span_id": doc.get("span_id"),
                    "correlation_id": doc.get("correlation_id"),
                    "session_id": doc.get("session_id"),
                    "route": doc.get("pathname") or doc.get("route") or doc.get("page") or "",
                    "message": doc.get("message") or "",
                }
            )

    samples.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    samples = samples[:safe_limit]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "samples": samples,
    }
