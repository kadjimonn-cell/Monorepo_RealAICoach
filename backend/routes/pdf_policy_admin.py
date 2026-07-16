"""Admin APIs for global PDF policy observability."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from routes.db import db, require_admin
from services.pdf_export_registry import (
    CANONICAL_NAMING_POLICY,
    CANONICAL_THEME_POLICY,
    build_pdf_export_registry,
    collect_pdf_export_registry_health,
)

router = APIRouter(prefix="/admin/pdf-policy", tags=["PDF Policy Admin"])


def _safe_theme_mode_counts(raw: dict[str, Any] | None) -> dict[str, int]:
    src = raw or {}
    return {
        "already_themed": int(src.get("already_themed") or 0),
        "metadata_stamped": int(src.get("metadata_stamped") or 0),
        "passthrough_error": int(src.get("passthrough_error") or 0),
        "theme_passthrough_error": int(src.get("theme_passthrough_error") or 0),
        "blocked_theme_passthrough_error": int(src.get("blocked_theme_passthrough_error") or 0),
        "blocked_non_pdf": int(src.get("blocked_non_pdf") or 0),
        "non_pdf": int(src.get("non_pdf") or 0),
    }


@router.get("/overview")
async def pdf_policy_overview(
    request: Request,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(20, ge=5, le=100),
):
    await require_admin(request)

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    try:
        recent_events = await db.pdf_policy_events.find(
            {"enforced_at": {"$gte": since}},
            {
                "_id": 0,
                "route_path": 1,
                "method": 1,
                "status": 1,
                "mode": 1,
                "theme_mode": 1,
                "original_header": 1,
                "normalized_header": 1,
                "enforced_at": 1,
            },
        ).sort("enforced_at", -1).limit(limit).to_list(limit)

        top_endpoints = await db.pdf_policy_counters.find(
            {},
            {
                "_id": 0,
                "route_path": 1,
                "method": 1,
                "total": 1,
                "theme_mode_counts": 1,
                "last_seen_at": 1,
                "last_theme_mode": 1,
                "last_status": 1,
            },
        ).sort("total", -1).limit(limit).to_list(limit)

        pipeline = [
            {"$group": {
                "_id": None,
                "total": {"$sum": {"$ifNull": ["$total", 0]}},
                "already_themed": {"$sum": {"$ifNull": ["$theme_mode_counts.already_themed", 0]}},
                "metadata_stamped": {"$sum": {"$ifNull": ["$theme_mode_counts.metadata_stamped", 0]}},
                "passthrough_error": {"$sum": {"$ifNull": ["$theme_mode_counts.passthrough_error", 0]}},
                "theme_passthrough_error": {"$sum": {"$ifNull": ["$theme_mode_counts.theme_passthrough_error", 0]}},
                "blocked_theme_passthrough_error": {"$sum": {"$ifNull": ["$theme_mode_counts.blocked_theme_passthrough_error", 0]}},
                "blocked_non_pdf": {"$sum": {"$ifNull": ["$theme_mode_counts.blocked_non_pdf", 0]}},
                "non_pdf": {"$sum": {"$ifNull": ["$theme_mode_counts.non_pdf", 0]}},
            }}
        ]
        totals_rows = await db.pdf_policy_counters.aggregate(pipeline).to_list(1)
        totals = totals_rows[0] if totals_rows else {
            "total": 0,
            "already_themed": 0,
            "metadata_stamped": 0,
            "passthrough_error": 0,
            "theme_passthrough_error": 0,
            "blocked_theme_passthrough_error": 0,
            "blocked_non_pdf": 0,
            "non_pdf": 0,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load PDF policy metrics: {exc}")

    formatted_endpoints = []
    for row in top_endpoints:
        formatted_endpoints.append(
            {
                "route_path": row.get("route_path") or "",
                "method": row.get("method") or "",
                "total": int(row.get("total") or 0),
                "theme_mode_counts": _safe_theme_mode_counts(row.get("theme_mode_counts")),
                "last_seen_at": row.get("last_seen_at"),
                "last_theme_mode": row.get("last_theme_mode") or "",
                "last_status": int(row.get("last_status") or 0),
            }
        )

    return {
        "policy": {
            "pdf_version_normalization": "disabled",
            "pdf_theme_policy": "enforced-v15",
            "strict_theme_mode": str(os.environ.get("PDF_THEME_STRICT_MODE", "true")).strip().lower() not in {"0", "false", "no", "off"},
            "enabled": True,
        },
        "window_hours": hours,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "total": int(totals.get("total") or 0),
            "already_themed": int(totals.get("already_themed") or 0),
            "metadata_stamped": int(totals.get("metadata_stamped") or 0),
            "passthrough_error": int(totals.get("passthrough_error") or 0),
            "theme_passthrough_error": int(totals.get("theme_passthrough_error") or 0),
            "blocked_theme_passthrough_error": int(totals.get("blocked_theme_passthrough_error") or 0),
            "blocked_non_pdf": int(totals.get("blocked_non_pdf") or 0),
            "non_pdf": int(totals.get("non_pdf") or 0),
        },
        "top_endpoints": formatted_endpoints,
        "recent_events": recent_events,
    }


@router.get("/export-registry")
async def pdf_export_registry(request: Request):
    await require_admin(request)
    registry = build_pdf_export_registry()
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for row in registry:
        by_doc.setdefault(row["doc_type"], []).append(row)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_version": "v1",
        "naming_policy": CANONICAL_NAMING_POLICY,
        "theme_policy": CANONICAL_THEME_POLICY,
        "total_exports": len(registry),
        "registry": registry,
        "doc_type_map": by_doc,
    }


@router.get("/export-registry/health")
async def pdf_export_registry_health(request: Request):
    await require_admin(request)
    health = collect_pdf_export_registry_health()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "naming_policy": CANONICAL_NAMING_POLICY,
        "theme_policy": CANONICAL_THEME_POLICY,
        **health,
    }


@router.get("/blocked-alerts")
async def blocked_theme_alerts(
    request: Request,
    minutes: int = Query(240, ge=5, le=10080),
    limit: int = Query(100, ge=1, le=500),
):
    await require_admin(request)
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    since_iso = since.isoformat()

    recent_events = await db.pdf_policy_alert_events.find(
        {"triggered_at": {"$gte": since_iso}},
        {
            "_id": 0,
            "alert_key": 1,
            "route_path": 1,
            "method": 1,
            "blocked_mode": 1,
            "detail": 1,
            "triggered_at": 1,
            "notified": 1,
        },
    ).sort("triggered_at", -1).limit(limit).to_list(limit)

    active_states = await db.pdf_policy_alert_state.find(
        {},
        {
            "_id": 0,
            "alert_key": 1,
            "last_mode": 1,
            "last_seen_at": 1,
            "last_sent_at": 1,
            "notify_count": 1,
            "suppressed_count": 1,
            "total": 1,
            "last_notify_result": 1,
        },
    ).sort("last_seen_at", -1).limit(limit).to_list(limit)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "minutes": minutes,
        "limit": limit,
        "event_count": len(recent_events),
        "state_count": len(active_states),
        "events": recent_events,
        "states": active_states,
    }
