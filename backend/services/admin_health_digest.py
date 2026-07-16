"""Admin Health Digest — daily one-line Slack/Teams status ping.

Runs once per day (via APScheduler — see ``scheduler.py``) and dispatches
a single digest message summarizing:

1. The current health state of every admin route tracked by
   ``services.admin_routes_sentinel``.
2. The top N crashing admin panels over the last 24 hours, sourced
   from the same collection that powers ``GET /api/errors/client/top``.

The digest ALWAYS dispatches (severity="warning") so the "all clear"
branch is visible — that's the whole point: a morning trust-signal
instead of a silent void when nothing's broken. When there are actual
crashes, severity is bumped to "critical" so pager-style rules can fire.

Every digest is persisted to ``db.admin_health_digest_log`` for audit.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

DIGEST_EVENT_TYPE = "admin_health_digest"
# We cap the list in the Slack/Teams message so it stays a single pane.
TOP_PANELS_IN_MESSAGE = 3


async def _gather_top_broken_panels(hours: int = 24, limit: int = 5) -> dict[str, Any]:
    """Mirror of ``routes.client_errors.top_broken`` but callable server-side."""
    from routes.db import db
    from routes.client_errors import COLLECTION

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {
            "$group": {
                "_id": "$panel_id",
                "count": {"$sum": 1},
                "panel_name": {"$last": "$panel_name"},
                "last_message": {"$last": "$message"},
                "last_seen": {"$max": "$created_at"},
                "unique_clients": {"$addToSet": "$client_id"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    items: list[dict[str, Any]] = []
    try:
        async for row in db[COLLECTION].aggregate(pipeline):
            items.append(
                {
                    "panel_id": row.get("_id") or "unknown",
                    "panel_name": row.get("panel_name") or "",
                    "count": int(row.get("count") or 0),
                    "last_message": (row.get("last_message") or "")[:200],
                    "unique_clients": len(
                        [c for c in (row.get("unique_clients") or []) if c]
                    ),
                }
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[health-digest] top_broken aggregate failed: {exc}")
    try:
        total = await db[COLLECTION].count_documents(
            {"created_at": {"$gte": since}}
        )
    except Exception:
        total = sum(i["count"] for i in items)
    return {"total_errors": total, "top": items, "window_hours": hours}


async def _gather_sentinel_state() -> dict[str, Any]:
    """Read the latest sentinel state per admin route from DB."""
    from routes.db import db
    from services.admin_routes_sentinel import ADMIN_ROUTE_PROBES

    states: list[dict[str, Any]] = []
    unhealthy: list[str] = []
    for route_key, cfg in ADMIN_ROUTE_PROBES.items():
        doc = await db.admin_route_state.find_one(
            {"route_key": route_key}, {"_id": 0}
        )
        status = (doc or {}).get("status") or "unknown"
        states.append(
            {
                "route_key": route_key,
                "label": cfg["label"],
                "ui_path": cfg["ui_path"],
                "status": status,
            }
        )
        if status == "unhealthy":
            unhealthy.append(cfg["label"])
    return {"routes": states, "unhealthy_labels": unhealthy}


def _build_message(
    top_panels: dict[str, Any],
    sentinel: dict[str, Any],
) -> tuple[str, str, dict[str, Any], str]:
    """Return (severity, title, fields, summary)."""
    total_errors = top_panels["total_errors"]
    top_list = top_panels["top"]
    unhealthy = sentinel["unhealthy_labels"]
    total_routes = len(sentinel["routes"])
    healthy_count = total_routes - len(unhealthy)

    if total_errors == 0 and not unhealthy:
        title = "Admin console all-clear"
        summary = (
            f"All {total_routes} admin routes healthy and zero panel crashes "
            f"reported in the last 24 hours."
        )
        fields: dict[str, Any] = {
            "Healthy routes": f"{healthy_count} / {total_routes}",
            "Panel crashes (24h)": "0",
        }
        return "warning", title, fields, summary

    # Broken-state digest
    title_bits: list[str] = []
    if unhealthy:
        title_bits.append(
            f"{len(unhealthy)} admin route(s) unhealthy"
        )
    if total_errors > 0:
        title_bits.append(f"{total_errors} panel crash event(s) in 24h")
    title = "Admin console health: " + "; ".join(title_bits)

    summary_parts: list[str] = []
    if unhealthy:
        summary_parts.append(
            f"Unhealthy routes: {', '.join(unhealthy)}."
        )
    if top_list:
        top_line = "; ".join(
            f"{(p['panel_name'] or p['panel_id'])} ({p['count']})"
            for p in top_list[:TOP_PANELS_IN_MESSAGE]
        )
        summary_parts.append(f"Top crashing panels: {top_line}.")
    summary = " ".join(summary_parts) or (
        "No sentinel/route detail available for this cycle."
    )

    fields = {
        "Healthy routes": f"{healthy_count} / {total_routes}",
        "Panel crashes (24h)": str(total_errors),
        "Unique broken panels (24h)": str(len(top_list)),
    }
    for i, p in enumerate(top_list[:TOP_PANELS_IN_MESSAGE], 1):
        fields[f"#{i} {p['panel_name'] or p['panel_id']}"] = (
            f"{p['count']} crash(es), {p['unique_clients']} user(s)"
        )

    severity = "critical" if unhealthy else "warning"
    return severity, title, fields, summary


async def run_admin_health_digest() -> dict[str, Any]:
    """Compose and dispatch the daily admin-health digest.

    Returns a JSON-safe dict with the computed state so callers (admin
    trigger endpoints, tests) can assert behavior without re-parsing
    Slack payloads.
    """
    from routes.db import db
    from services.webhook_alerts import send_alert

    top_panels = await _gather_top_broken_panels(hours=24, limit=5)
    sentinel = await _gather_sentinel_state()
    severity, title, fields, summary = _build_message(top_panels, sentinel)

    frontend_base = (os.environ.get("FRONTEND_BASE_URL") or "").rstrip("/")
    url = (
        f"{frontend_base}/admin-console?category=dev&tab=code-health"
        if frontend_base
        else None
    )

    dispatch_res: dict[str, Any] = {}
    try:
        dispatch_res = await send_alert(
            event_type=DIGEST_EVENT_TYPE,
            severity=severity,
            title=title,
            summary=summary,
            fields=fields,
            url=url,
        )
    except Exception as exc:
        logger.warning(f"[health-digest] send_alert failed: {exc}")
        dispatch_res = {"dispatched": False, "error": str(exc)[:200]}

    # ── Email channel ────────────────────────────────────────────
    # The Slack/Teams webhook may not be configured; email always is,
    # so the digest is the useful signal even for pre-webhook setups.
    email_res: dict[str, Any] = {"sent": False, "skipped": True}
    admin_email = (
        os.environ.get("ADMIN_DIGEST_EMAIL")
        or os.environ.get("ADMIN_EMAIL")
        or "admin@realaicoach.app"
    )
    try:
        from utils.email_service import send_email
        from utils.email_templates import build_admin_health_digest_email

        template = build_admin_health_digest_email(
            severity=severity,
            title=title,
            summary=summary,
            total_errors_24h=top_panels["total_errors"],
            healthy_routes=len(sentinel["routes"]) - len(sentinel["unhealthy_labels"]),
            total_routes=len(sentinel["routes"]),
            unhealthy_routes=sentinel["unhealthy_labels"],
            top_panels=top_panels["top"],
            generated_at=datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC"),
        )
        email_res = await send_email(
            recipient_email=admin_email,
            subject=template.subject,
            content=template.html,
            content_text=template.text,
            template_key="admin_health_digest",
        )
    except Exception as exc:
        logger.warning(f"[health-digest] email dispatch failed: {exc}")
        email_res = {"sent": False, "error": str(exc)[:200]}

    # Snapshot V2 theme audit so the digest history can render a trend
    # sparkline of `files_with_violations` over the last N days.
    theme_audit_snapshot: dict[str, Any] = {}
    try:
        from routes.code_health import _v2_theme_audit_snapshot
        snap = await _v2_theme_audit_snapshot()
        theme_audit_snapshot = {
            "files_scanned": snap.get("files_scanned", 0),
            "files_with_violations": snap.get("files_with_violations", 0),
            "files_theme_compliant": snap.get("files_theme_compliant", 0),
            "p0_violations": snap.get("p0_violations", 0),
            "status": snap.get("status", "unknown"),
        }
    except Exception as exc:
        logger.warning(f"[health-digest] theme audit snapshot failed: {exc}")
        theme_audit_snapshot = {"status": "unknown", "error": str(exc)[:200]}

    record = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "title": title,
        "summary": summary,
        "fields": fields,
        "total_errors_24h": top_panels["total_errors"],
        "top_panels": top_panels["top"],
        "unhealthy_routes": sentinel["unhealthy_labels"],
        "healthy_routes": len(sentinel["routes"]) - len(sentinel["unhealthy_labels"]),
        "total_routes": len(sentinel["routes"]),
        "dispatched": bool(dispatch_res.get("dispatched")),
        "email_sent": bool(email_res.get("success") or email_res.get("sent")),
        "email_recipient": admin_email,
        "theme_audit": theme_audit_snapshot,
    }
    try:
        await db.admin_health_digest_log.insert_one({**record})
    except Exception as exc:
        logger.warning(f"[health-digest] log persist failed: {exc}")

    logger.info(
        "[health-digest] severity=%s dispatched=%s email=%s broken_routes=%d crashes24h=%d",
        severity,
        record["dispatched"],
        record["email_sent"],
        len(sentinel["unhealthy_labels"]),
        top_panels["total_errors"],
    )
    return record
