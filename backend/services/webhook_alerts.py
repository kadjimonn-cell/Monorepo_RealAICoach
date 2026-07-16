"""Slack + Teams webhook alerts for V7/UIEM/theme-drift regressions.

Configuration is stored in `db.webhook_alerts_config` (single doc with `config_id="webhook_alerts"`)
and contains:
  - slack_webhook_url: str (optional)
  - teams_webhook_url: str (optional)
  - enabled_events: list[str] — subset of {"v7_violation", "uiem_violation", "theme_drift_regression"}
  - min_severity: str — "info" | "warning" | "critical"
  - updated_at, updated_by

Events are POSTed asynchronously via httpx. Each alert is also mirrored to
`db.webhook_alerts_log` for audit.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CONFIG_ID = "webhook_alerts"
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

_SEV_COLOR_SLACK = {"info": "#3B82F6", "warning": "#F59E0B", "critical": "#EF4444"}
_SEV_COLOR_TEAMS = {"info": "2563EB", "warning": "B45309", "critical": "B91C1C"}

DEFAULT_CONFIG: dict[str, Any] = {
    "config_id": CONFIG_ID,
    "slack_webhook_url": "",
    "teams_webhook_url": "",
    "enabled_events": ["v7_violation", "uiem_violation", "theme_drift_regression",
                        "career_interview_confirmed", "career_interview_reschedule_requested",
                        "admin_route_regression",
                        "admin_health_digest",
                        "apscheduler_job_error",
                        "apscheduler_job_missed"],
    "min_severity": "warning",
    "updated_at": None,
    "updated_by": None,
}


async def get_config() -> dict[str, Any]:
    from routes.db import db
    doc = await db.webhook_alerts_config.find_one({"config_id": CONFIG_ID}, {"_id": 0})
    if not doc:
        return DEFAULT_CONFIG.copy()
    # Merge with defaults so new keys roll through
    merged = {**DEFAULT_CONFIG, **doc}
    return merged


async def save_config(partial: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
    from routes.db import db
    current = await get_config()
    updated = {**current, **{k: v for k, v in partial.items() if v is not None}}
    updated["config_id"] = CONFIG_ID
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    if updated_by:
        updated["updated_by"] = updated_by
    await db.webhook_alerts_config.update_one(
        {"config_id": CONFIG_ID}, {"$set": updated}, upsert=True
    )
    return {k: v for k, v in updated.items() if k != "_id"}


def _build_slack_payload(event_type: str, severity: str, title: str, summary: str, fields: dict[str, Any], url: str | None) -> dict[str, Any]:
    field_blocks = [
        {"type": "mrkdwn", "text": f"*{k}*\n{v}"} for k, v in list(fields.items())[:10]
    ]
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"[{severity.upper()}] {title}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
    ]
    if field_blocks:
        blocks.append({"type": "section", "fields": field_blocks})
    if url:
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "Open Admin Console"},
                "url": url,
            }],
        })
    return {
        "text": f"[{severity.upper()}] {title}",
        "attachments": [{"color": _SEV_COLOR_SLACK.get(severity, "#64748B"), "blocks": blocks}],
        "metadata": {"event_type": event_type},
    }


def _build_teams_payload(event_type: str, severity: str, title: str, summary: str, fields: dict[str, Any], url: str | None) -> dict[str, Any]:
    facts = [{"name": k, "value": str(v)} for k, v in list(fields.items())[:10]]
    actions = []
    if url:
        actions.append({"@type": "OpenUri", "name": "Open Admin Console",
                        "targets": [{"os": "default", "uri": url}]})
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": _SEV_COLOR_TEAMS.get(severity, "64748B"),
        "summary": title,
        "title": f"[{severity.upper()}] {title}",
        "sections": [{"activityTitle": summary, "facts": facts, "markdown": True}],
        "potentialAction": actions,
        "_meta": {"event_type": event_type},
    }


async def _post_webhook(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.post(url, json=payload)
        return {"ok": 200 <= r.status_code < 300, "status": r.status_code, "body": (r.text or "")[:200]}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)[:200]}


async def send_alert(
    event_type: str,
    severity: str,
    title: str,
    summary: str,
    fields: dict[str, Any] | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Dispatch an alert to configured Slack + Teams webhooks (if severity/event passes filters)."""
    from routes.db import db

    cfg = await get_config()
    fields = fields or {}

    # Filter: event type enabled
    if event_type not in cfg.get("enabled_events", []):
        return {"dispatched": False, "reason": "event_disabled", "event_type": event_type}

    # Filter: severity threshold
    min_rank = SEVERITY_RANK.get(cfg.get("min_severity", "warning"), 1)
    if SEVERITY_RANK.get(severity, 0) < min_rank:
        return {"dispatched": False, "reason": "below_min_severity", "severity": severity}

    slack_url = cfg.get("slack_webhook_url") or ""
    teams_url = cfg.get("teams_webhook_url") or ""
    results: dict[str, Any] = {}

    if slack_url:
        results["slack"] = await _post_webhook(slack_url, _build_slack_payload(event_type, severity, title, summary, fields, url))
    if teams_url:
        results["teams"] = await _post_webhook(teams_url, _build_teams_payload(event_type, severity, title, summary, fields, url))

    dispatched = any((r or {}).get("ok") for r in results.values())

    # Audit log (best-effort)
    try:
        await db.webhook_alerts_log.insert_one({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "severity": severity,
            "title": title,
            "summary": summary,
            "fields": fields,
            "url": url,
            "dispatched": dispatched,
            "results": results,
        })
    except Exception:
        pass

    if dispatched:
        logger.info(f"[webhook-alerts] event={event_type} severity={severity} dispatched=True slack={bool(slack_url)} teams={bool(teams_url)}")
    return {"dispatched": dispatched, "results": results}


def send_alert_fire_and_forget(event_type: str, severity: str, title: str, summary: str,
                               fields: dict[str, Any] | None = None, url: str | None = None) -> None:
    """Sync-callable shim that schedules `send_alert` without awaiting.
    Safe to call from places that aren't already inside an async task.
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if loop.is_running():
        loop.create_task(send_alert(event_type, severity, title, summary, fields, url))


# ── Weekly Digest ──────────────────────────────────────────────────────────
async def build_weekly_digest_payload(now: datetime | None = None) -> dict[str, Any]:
    """Aggregate a 7-day snapshot of V7 / UIEM / theme-drift / LLM signals."""
    from datetime import timedelta
    from routes.db import db

    now = now or datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    cutoff = week_ago.isoformat()

    # V7 violations
    v7_count = await db.v7_violations.count_documents({"created_at": {"$gte": cutoff}})

    # UIEM violations + top component
    uiem_count = await db.uiem_violations.count_documents({"created_at": {"$gte": cutoff}})
    uiem_top_component = "—"
    async for d in db.uiem_violations.aggregate([
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$component", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 1},
    ]):
        uiem_top_component = f"{d.get('_id', 'unknown')} ({d.get('n', 0)}×)"

    # Theme-drift regressions (audit runs with regression flag)
    theme_regressions = await db["platform_perf_alerts"].count_documents({
        "kind": "theme_visibility_regression_email",
        "created_at": {"$gte": cutoff},
    })

    # Latest theme audit grade
    current_grade = "—"
    current_fails = 0
    async for d in db.theme_audit_history.find({}, {"_id": 0}).sort("ran_at", -1).limit(1):
        current_grade = d.get("grade") or "—"
        current_fails = int(d.get("total_fails") or 0)

    # LLM 7-day cost
    llm_cost_7d = 0.0
    llm_calls_7d = 0
    async for d in db.llm_usage_log.aggregate([
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": None, "cost": {"$sum": "$cost_usd"}, "calls": {"$sum": 1}}},
    ]):
        llm_cost_7d = float(d.get("cost") or 0.0)
        llm_calls_7d = int(d.get("calls") or 0)

    # Severity derivation
    if uiem_count >= 10 or v7_count >= 20 or theme_regressions >= 2:
        severity = "critical"
    elif uiem_count > 0 or v7_count > 0 or theme_regressions > 0:
        severity = "warning"
    else:
        severity = "info"

    return {
        "week_start": week_ago.strftime("%Y-%m-%d"),
        "week_end": now.strftime("%Y-%m-%d"),
        "v7_count": v7_count,
        "uiem_count": uiem_count,
        "uiem_top_component": uiem_top_component,
        "theme_regressions": theme_regressions,
        "current_grade": current_grade,
        "current_fails": current_fails,
        "llm_cost_7d": round(llm_cost_7d, 2),
        "llm_calls_7d": llm_calls_7d,
        "severity": severity,
    }


async def send_weekly_digest(trigger: str = "scheduled_weekly") -> dict[str, Any]:
    """Post the weekly digest to configured Slack/Teams webhooks. Always dispatches
    regardless of min_severity so admins get a consistent rhythm."""
    payload = await build_weekly_digest_payload()
    severity = payload["severity"]
    title = f"Weekly platform quality digest ({payload['week_start']} → {payload['week_end']})"
    summary = (
        f"Past 7 days: *V7 violations* {payload['v7_count']} · *UIEM violations* {payload['uiem_count']} · "
        f"*theme regressions* {payload['theme_regressions']} · latest theme grade *{payload['current_grade']}* "
        f"({payload['current_fails']} fails). LLM spend: *${payload['llm_cost_7d']:,.2f}* across {payload['llm_calls_7d']:,} calls."
    )
    fields = {
        "V7 Violations": str(payload["v7_count"]),
        "UIEM Violations": str(payload["uiem_count"]),
        "Top UIEM Component": payload["uiem_top_component"],
        "Theme Regressions": str(payload["theme_regressions"]),
        "Current Theme Grade": f"{payload['current_grade']} ({payload['current_fails']} fails)",
        "LLM Spend (7d)": f"${payload['llm_cost_7d']:,.2f} / {payload['llm_calls_7d']:,} calls",
    }

    # Bypass min_severity filter — weekly digest should always send if channels configured
    cfg = await get_config()
    # Temporarily override by calling the post helpers directly
    from routes.db import db
    slack_url = cfg.get("slack_webhook_url") or ""
    teams_url = cfg.get("teams_webhook_url") or ""
    results: dict[str, Any] = {}
    if slack_url:
        results["slack"] = await _post_webhook(slack_url, _build_slack_payload("weekly_digest", severity, title, summary, fields, None))
    if teams_url:
        results["teams"] = await _post_webhook(teams_url, _build_teams_payload("weekly_digest", severity, title, summary, fields, None))
    dispatched = any((r or {}).get("ok") for r in results.values())

    try:
        await db.webhook_alerts_log.insert_one({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "event_type": "weekly_digest",
            "severity": severity,
            "title": title,
            "summary": summary,
            "fields": fields,
            "url": None,
            "dispatched": dispatched,
            "results": results,
            "trigger": trigger,
        })
    except Exception:
        pass

    logger.info(f"[webhook-alerts] weekly_digest trigger={trigger} dispatched={dispatched} v7={payload['v7_count']} uiem={payload['uiem_count']}")
    return {"dispatched": dispatched, "results": results, "payload": payload, "trigger": trigger}
