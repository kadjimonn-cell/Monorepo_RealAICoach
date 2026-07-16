"""Admin Routes Sentinel — 5-minute synthetic check of the 3 ADMIN-section
routes highlighted by the user (Team Management, Executive Console,
Operations Console).

For each route we hit the 1–2 backend endpoints that route depends on
with a short-lived synthetic admin JWT (minted in-process via
``routes.critical_journey_monitor._mint_synthetic_admin_session``).

We store the last status per route in ``db.admin_routes_sentinel_state``
and dispatch a Slack/Teams webhook alert via
``services.webhook_alerts.send_alert`` ONLY on state transitions
(healthy → unhealthy or vice-versa). This keeps Slack quiet during
sustained outages and ensures the team is paged the instant any route
first regresses AND the instant it recovers.

Register in ``scheduler.py``::

    scheduler.add_job(
        run_admin_routes_sentinel,
        IntervalTrigger(minutes=5),
        id="admin_routes_sentinel",
        replace_existing=True,
    )
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Route → list of backend probes. Each probe MUST return 2xx for the
# route to be considered healthy. These were selected from the actual
# `api.get(...)` calls the corresponding React Native Web components
# fire on mount (verified in team-management.tsx,
# executive-dashboard.tsx, OperationsConsoleView.tsx).
ADMIN_ROUTE_PROBES: dict[str, dict[str, Any]] = {
    "team-management": {
        "ui_path": "/team-management",
        "label": "Team Management",
        "endpoints": [
            "/api/admin/employees",
            "/api/admin/employees/roles-config",
        ],
    },
    "executive-dashboard": {
        "ui_path": "/executive-dashboard",
        "label": "Executive Console",
        "endpoints": [
            "/api/admin/executive/overview",
        ],
    },
    "admin-console": {
        "ui_path": "/admin-console?category=people&tab=career-applications",
        "label": "Operations Console",
        "endpoints": [
            "/api/admin/notifications/live?limit=12",
            "/api/admin/live-activity/alerts",
        ],
    },
}

STATE_COLLECTION = "admin_routes_sentinel_state"


def _base_url() -> str:
    # For in-pod probing the local supervisor-managed backend is always
    # the fastest + most honest target. Fall back to the external URL.
    return (
        "http://localhost:8001"
        if os.environ.get("ADMIN_ROUTES_SENTINEL_LOCAL", "1") == "1"
        else (
            os.environ.get("FRONTEND_BASE_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "http://localhost:8001"
        ).rstrip("/")
    )


async def _mint_admin_token() -> str:
    """Fetch a short-lived admin JWT. Reuses the exact same synthetic
    session minter the Critical Journey Monitor uses."""
    try:
        from routes.critical_journey_monitor import _mint_synthetic_admin_session
        return await _mint_synthetic_admin_session()
    except Exception as exc:
        logger.warning(f"[admin-routes-sentinel] token mint failed: {exc}")
        return ""


async def _probe_endpoint(
    client: httpx.AsyncClient, base: str, endpoint: str, token: str
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}" if token else "",
        "X-Requested-With": "XMLHttpRequest",
        "X-Synthetic-Monitor": "admin-routes-sentinel",
    }
    try:
        r = await client.get(f"{base}{endpoint}", headers=headers, timeout=6.0)
        return {
            "endpoint": endpoint,
            "status": r.status_code,
            "ok": 200 <= r.status_code < 400,
        }
    except Exception as exc:
        return {"endpoint": endpoint, "status": 0, "ok": False, "error": str(exc)[:160]}


async def _load_prev_state(route_key: str) -> str | None:
    from routes.db import db

    doc = await db[STATE_COLLECTION].find_one(
        {"route_key": route_key}, {"_id": 0, "status": 1}
    )
    return doc.get("status") if doc else None


async def _save_state(route_key: str, status: str, detail: dict[str, Any]) -> None:
    from routes.db import db

    await db[STATE_COLLECTION].update_one(
        {"route_key": route_key},
        {
            "$set": {
                "route_key": route_key,
                "status": status,
                "detail": detail,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )


async def _notify_state_change(
    route_key: str,
    ui_path: str,
    label: str,
    prev: str | None,
    curr: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch Slack/Teams alert ONLY on state transitions."""
    from services.webhook_alerts import send_alert

    severity = "critical" if curr == "unhealthy" else "info"
    action = "regressed" if curr == "unhealthy" else "recovered"
    title = f"Admin route {label} {action}"
    summary = (
        f"Admin route `{ui_path}` transitioned `{prev or 'unknown'}` → `{curr}`. "
        + (
            "The page will likely white-screen or ErrorBoundary for admins."
            if curr == "unhealthy"
            else "The page is rendering normally again."
        )
    )
    fields: dict[str, Any] = {
        "Route": label,
        "UI path": ui_path,
        "Previous status": prev or "unknown",
        "Current status": curr,
    }
    # Attach the first failing endpoint (if any) for fast triage.
    failed = [p for p in detail.get("probes", []) if not p.get("ok")]
    if failed:
        f0 = failed[0]
        fields["First failure"] = f"{f0.get('endpoint')} → HTTP {f0.get('status')}"
    return await send_alert(
        event_type="admin_route_regression",
        severity=severity,
        title=title,
        summary=summary,
        fields=fields,
        url=f"{(os.environ.get('FRONTEND_BASE_URL') or '').rstrip('/')}{ui_path}",
    )


async def run_admin_routes_sentinel() -> dict[str, Any]:
    """One synthetic sweep. Returns a structured summary used by tests + the
    scheduler log line."""
    base = _base_url()
    token = await _mint_admin_token()

    summary: dict[str, Any] = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "had_admin_token": bool(token),
        "routes": [],
        "transitions": 0,
        "dispatched": 0,
    }

    async with httpx.AsyncClient() as client:
        for route_key, cfg in ADMIN_ROUTE_PROBES.items():
            probes = [
                await _probe_endpoint(client, base, ep, token)
                for ep in cfg["endpoints"]
            ]
            status = "healthy" if all(p["ok"] for p in probes) else "unhealthy"
            detail = {"probes": probes}

            prev = await _load_prev_state(route_key)
            await _save_state(route_key, status, detail)

            route_summary = {
                "route_key": route_key,
                "label": cfg["label"],
                "ui_path": cfg["ui_path"],
                "status": status,
                "previous_status": prev,
                "probes": probes,
                "transitioned": prev is not None and prev != status,
            }
            summary["routes"].append(route_summary)

            if route_summary["transitioned"]:
                summary["transitions"] += 1
                res = await _notify_state_change(
                    route_key, cfg["ui_path"], cfg["label"], prev, status, detail
                )
                if res.get("dispatched"):
                    summary["dispatched"] += 1

                # Auto-remediation hook: when a route flips to unhealthy,
                # immediately kick off a code-health auto-fix sweep so we
                # try to repair before the next scheduled 24h cycle. We
                # only fire on the healthy → unhealthy edge so recovery
                # transitions don't trigger needless ruff runs.
                if status == "unhealthy":
                    try:
                        from routes.code_health import auto_fix_check

                        fix_res = await auto_fix_check(
                            source="admin_routes_sentinel",
                            context={
                                "route_key": route_key,
                                "label": cfg["label"],
                                "ui_path": cfg["ui_path"],
                                "previous_status": prev,
                                "first_failure": next(
                                    (
                                        f"{p.get('endpoint')} → HTTP {p.get('status')}"
                                        for p in probes
                                        if not p.get("ok")
                                    ),
                                    None,
                                ),
                            },
                        )
                        summary.setdefault("auto_fix_runs", []).append(
                            {
                                "route_key": route_key,
                                "total_fixed": fix_res.get("total_fixed", 0),
                                "before": fix_res.get("before_issues", 0),
                                "after": fix_res.get("after_issues", 0),
                            }
                        )
                    except Exception as exc:
                        logger.warning(
                            f"[admin-routes-sentinel] auto-fix hook failed "
                            f"for {route_key}: {exc}"
                        )

    # Summary log — stays quiet when all is well.
    if summary["transitions"] or any(r["status"] == "unhealthy" for r in summary["routes"]):
        unhealthy = [r["label"] for r in summary["routes"] if r["status"] == "unhealthy"]
        logger.warning(
            f"[admin-routes-sentinel] transitions={summary['transitions']} "
            f"dispatched={summary['dispatched']} unhealthy={unhealthy}"
        )
    return summary
