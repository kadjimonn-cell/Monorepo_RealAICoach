"""Admin endpoints for Slack/Teams webhook alert configuration + audit log."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.db import db, get_current_user
from services.webhook_alerts import (
    get_config, save_config, send_alert, SEVERITY_RANK,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _require_admin(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _redact(cfg: dict[str, Any]) -> dict[str, Any]:
    """Never return the full webhook URL to the client — only a masked hint."""
    out = {k: v for k, v in cfg.items() if k != "_id"}
    for field in ("slack_webhook_url", "teams_webhook_url"):
        v = (out.get(field) or "")
        out[f"{field}_configured"] = bool(v)
        out[f"{field}_hint"] = (v[:24] + "…" + v[-6:]) if len(v) > 40 else ("" if not v else "•••")
        out.pop(field, None)
    return out


class WebhookConfigUpdate(BaseModel):
    slack_webhook_url: str | None = None
    teams_webhook_url: str | None = None
    enabled_events: list[str] | None = None
    min_severity: str | None = Field(default=None, description="info | warning | critical")


@router.get("/admin/webhook-alerts/config")
async def webhook_alerts_get_config(request: Request):
    await _require_admin(request)
    return _redact(await get_config())


@router.put("/admin/webhook-alerts/config")
async def webhook_alerts_update_config(request: Request, body: WebhookConfigUpdate):
    user = await _require_admin(request)
    partial: dict[str, Any] = {}
    if body.slack_webhook_url is not None:
        partial["slack_webhook_url"] = body.slack_webhook_url.strip()
    if body.teams_webhook_url is not None:
        partial["teams_webhook_url"] = body.teams_webhook_url.strip()
    if body.enabled_events is not None:
        valid = {"v7_violation", "uiem_violation", "theme_drift_regression"}
        partial["enabled_events"] = [e for e in body.enabled_events if e in valid]
    if body.min_severity is not None:
        if body.min_severity not in SEVERITY_RANK:
            raise HTTPException(status_code=400, detail=f"min_severity must be one of {list(SEVERITY_RANK)}")
        partial["min_severity"] = body.min_severity
    updated = await save_config(partial, updated_by=getattr(user, "email", None))
    return _redact(updated)


@router.post("/admin/webhook-alerts/test")
async def webhook_alerts_test(request: Request):
    """Fire a synthetic 'info' alert to both configured webhooks so admins can verify wiring."""
    await _require_admin(request)
    # Temporarily bypass min_severity filter by coercing severity from config
    cfg = await get_config()
    sev = cfg.get("min_severity") or "warning"
    return await send_alert(
        event_type="v7_violation",  # any event is fine — user chose to test
        severity=sev,
        title="Webhook alert test — RealAICoach",
        summary="This is a test alert triggered from the Platform Integrations page.",
        fields={"Source": "Admin / Platform Integrations", "Severity threshold": sev},
        url=None,
    )


@router.get("/admin/webhook-alerts/recent")
async def webhook_alerts_recent(request: Request, limit: int = 25):
    await _require_admin(request)
    limit = max(1, min(limit, 200))
    items: list[dict[str, Any]] = []
    async for d in db.webhook_alerts_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit):
        items.append(d)
    return {"items": items, "count": len(items)}


@router.get("/admin/webhook-alerts/weekly-preview")
async def webhook_alerts_weekly_preview(request: Request):
    """Return the payload that would be posted for this week's digest without sending."""
    await _require_admin(request)
    from services.webhook_alerts import build_weekly_digest_payload
    return await build_weekly_digest_payload()


@router.post("/admin/webhook-alerts/send-weekly-digest-now")
async def webhook_alerts_send_weekly_digest_now(request: Request):
    """Immediately post the weekly digest to configured Slack/Teams webhooks."""
    await _require_admin(request)
    from services.webhook_alerts import send_weekly_digest
    return await send_weekly_digest(trigger="manual_admin")
