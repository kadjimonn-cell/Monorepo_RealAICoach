import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


def build_certificate_history_query(
    *,
    range_value: str,
    start_at: Optional[str],
    end_at: Optional[str],
    issuer: Optional[str],
    run_id: Optional[str],
    parse_iso_datetime,
):
    query: Dict[str, Any] = {}
    normalized_range = str(range_value or "all").lower().strip()
    issued_at_query: Dict[str, Any] = {}
    now = datetime.now(timezone.utc)

    if normalized_range == "24h":
        issued_at_query["$gte"] = (now - timedelta(hours=24)).isoformat()
    elif normalized_range == "7d":
        issued_at_query["$gte"] = (now - timedelta(days=7)).isoformat()
    elif normalized_range == "custom":
        parsed_start = parse_iso_datetime(start_at) if start_at else None
        parsed_end = parse_iso_datetime(end_at) if end_at else None
        if not parsed_start or not parsed_end:
            raise ValueError("Custom range requires valid start_at and end_at")
        if parsed_end < parsed_start:
            raise ValueError("end_at must be >= start_at")
        issued_at_query["$gte"] = parsed_start.isoformat()
        issued_at_query["$lte"] = parsed_end.isoformat()
    elif normalized_range != "all":
        raise ValueError("range must be one of: all, 24h, 7d, custom")

    if issued_at_query:
        query["issued_at"] = issued_at_query

    if issuer and issuer.strip():
        query["issued_by"] = {"$regex": re.escape(issuer.strip()), "$options": "i"}

    if run_id and run_id.strip():
        pattern = re.escape(run_id.strip())
        query["$or"] = [
            {"baseline_run_id": {"$regex": pattern, "$options": "i"}},
            {"latest_run_id": {"$regex": pattern, "$options": "i"}},
        ]

    return normalized_range, query


def build_completion_audit_query(
    *,
    blocked_only: bool,
    range_value: str,
    start_at: Optional[str],
    end_at: Optional[str],
    parse_iso_datetime,
):
    query: Dict[str, Any] = {}
    if blocked_only:
        query["blocked"] = True

    now = datetime.now(timezone.utc)
    normalized_range = str(range_value or "all").lower().strip()
    ts_query: Dict[str, Any] = {}

    if normalized_range == "24h":
        ts_query["$gte"] = now - timedelta(hours=24)
    elif normalized_range == "7d":
        ts_query["$gte"] = now - timedelta(days=7)
    elif normalized_range == "custom":
        parsed_start = parse_iso_datetime(start_at) if start_at else None
        parsed_end = parse_iso_datetime(end_at) if end_at else None
        if not parsed_start or not parsed_end:
            raise ValueError("Custom range requires valid start_at and end_at ISO datetimes")
        if parsed_end < parsed_start:
            raise ValueError("end_at must be greater than or equal to start_at")
        ts_query["$gte"] = parsed_start
        ts_query["$lte"] = parsed_end
    elif normalized_range != "all":
        raise ValueError("range must be one of: all, 24h, 7d, custom")

    if ts_query:
        query["timestamp"] = ts_query

    return normalized_range, query


def build_perf_trends_payload(audits: list) -> dict:
    timestamps = [a.get("audited_at", "") for a in audits]
    return {
        "data_points": len(audits),
        "timestamps": timestamps,
        "trends": {
            "api_latency_ms": [a.get("api_overall_avg_ms", 0) for a in audits],
            "bundle_size_mb": [a.get("bundle_size_mb", 0) for a in audits],
            "memory_usage_mb": [a.get("memory_usage_mb", 0) for a in audits],
            "alert_count": [a.get("alert_count", 0) for a in audits],
        },
        "audits": audits,
    }
