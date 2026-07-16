"""Slack / Teams webhook alerts for high-severity theme drift tickets."""
import logging
import aiohttp
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def send_slack_alert(webhook_url: str, ticket: Dict[str, Any], dashboard_url: str) -> Dict[str, Any]:
    """Send a Slack webhook alert for a high-severity drift ticket."""
    severity = str(ticket.get("severity", "high")).upper()
    ticket_id = ticket.get("ticket_id", "unknown")
    file_path = ticket.get("file", "unknown")
    rule = ticket.get("rule", "unknown")
    message = ticket.get("message", "Theme drift detected")
    hits = ticket.get("occurrence_count", 1)
    line = ticket.get("line", 0)

    color = "#DC2626" if severity == "HIGH" else "#F59E0B"
    payload = {
        "text": f":rotating_light: *[{severity}] Theme Drift Ticket Created*",
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{ticket_id}*\n{message}"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*File:*\n`{file_path}:{line}`"},
                            {"type": "mrkdwn", "text": f"*Rule:*\n{rule}"},
                            {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                            {"type": "mrkdwn", "text": f"*Hits:*\n{hits}"},
                        ],
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Open Dashboard"},
                                "url": dashboard_url,
                                "style": "primary",
                            }
                        ],
                    },
                ],
            }
        ],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ok = resp.status in (200, 201, 204)
                body = await resp.text()
                if ok:
                    logger.info("Slack alert sent for %s: %s", ticket_id, resp.status)
                else:
                    logger.warning("Slack alert failed for %s: %s %s", ticket_id, resp.status, body[:100])
                return {"provider": "slack", "ticket_id": ticket_id, "status": resp.status, "ok": ok}
    except Exception as exc:
        logger.error("Slack alert error for %s: %s", ticket_id, exc)
        return {"provider": "slack", "ticket_id": ticket_id, "error": str(exc)[:120], "ok": False}


async def send_teams_alert(webhook_url: str, ticket: Dict[str, Any], dashboard_url: str) -> Dict[str, Any]:
    """Send a Microsoft Teams webhook alert for a high-severity drift ticket."""
    severity = str(ticket.get("severity", "high")).upper()
    ticket_id = ticket.get("ticket_id", "unknown")
    file_path = ticket.get("file", "unknown")
    rule = ticket.get("rule", "unknown")
    message = ticket.get("message", "Theme drift detected")
    hits = ticket.get("occurrence_count", 1)
    line = ticket.get("line", 0)
    theme_color = "DC2626" if severity == "HIGH" else "F59E0B"

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": theme_color,
        "summary": f"[{severity}] Theme Drift: {ticket_id}",
        "sections": [
            {
                "activityTitle": f"[{severity}] Theme Drift Ticket Created",
                "activitySubtitle": ticket_id,
                "facts": [
                    {"name": "File", "value": f"`{file_path}:{line}`"},
                    {"name": "Rule", "value": rule},
                    {"name": "Severity", "value": severity},
                    {"name": "Occurrences", "value": str(hits)},
                    {"name": "Message", "value": message},
                ],
                "markdown": True,
            }
        ],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Open Dashboard",
                "targets": [{"os": "default", "uri": dashboard_url}],
            }
        ],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ok = resp.status in (200, 201, 204)
                body = await resp.text()
                if ok:
                    logger.info("Teams alert sent for %s: %s", ticket_id, resp.status)
                else:
                    logger.warning("Teams alert failed for %s: %s %s", ticket_id, resp.status, body[:100])
                return {"provider": "teams", "ticket_id": ticket_id, "status": resp.status, "ok": ok}
    except Exception as exc:
        logger.error("Teams alert error for %s: %s", ticket_id, exc)
        return {"provider": "teams", "ticket_id": ticket_id, "error": str(exc)[:120], "ok": False}


async def dispatch_drift_alerts(
    tickets: List[Dict[str, Any]],
    config: Dict[str, Any],
    dashboard_url: str,
) -> List[Dict[str, Any]]:
    """Send alerts for high-severity tickets based on configured webhooks."""
    results: List[Dict[str, Any]] = []
    slack_url = str(config.get("slack_webhook_url") or "").strip()
    teams_url = str(config.get("teams_webhook_url") or "").strip()
    min_severity = str(config.get("alert_min_severity") or "high").lower()

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    min_level = severity_order.get(min_severity, 1)

    eligible = [t for t in tickets if severity_order.get(str(t.get("severity", "")).lower(), 3) <= min_level]
    if not eligible:
        return results

    for ticket in eligible[:20]:
        if slack_url:
            r = await send_slack_alert(slack_url, ticket, dashboard_url)
            results.append(r)
        if teams_url:
            r = await send_teams_alert(teams_url, ticket, dashboard_url)
            results.append(r)

    return results
