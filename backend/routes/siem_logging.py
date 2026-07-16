"""SIEM / Centralized Logging — admin endpoints for security event management."""

from fastapi import APIRouter, Query, Request
import re
from datetime import datetime, timezone, timedelta
from routes.db import db, require_admin
import uuid
import os
from collections import Counter
import httpx
import ipaddress

router = APIRouter(prefix="/admin/siem", tags=["SIEM Logging"])

DEFAULT_SIEM_RULES = [
    {
        "rule_id": "rule_failed_login_spike",
        "name": "Failed Login Spike",
        "event_type": "failed_login",
        "threshold": 10,
        "window_minutes": 10,
        "severity": "high",
    },
    {
        "rule_id": "rule_jwt_invalid_spike",
        "name": "JWT Invalid Spike",
        "event_type": "jwt_invalid",
        "threshold": 8,
        "window_minutes": 10,
        "severity": "high",
    },
    {
        "rule_id": "rule_query_token_usage",
        "name": "Query Token Authentication Usage",
        "event_type": "query_token_auth_used",
        "threshold": 3,
        "window_minutes": 5,
        "severity": "critical",
    },
]


async def _ensure_default_siem_rules() -> None:
    for rule in DEFAULT_SIEM_RULES:
        existing = await db.siem_alert_rules.find_one({"rule_id": rule["rule_id"]}, {"_id": 1})
        if existing:
            continue
        doc = {
            **rule,
            "enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
        }
        await db.siem_alert_rules.insert_one(doc)


async def _dispatch_incident_webhook(incident: dict) -> None:
    webhook_url = str(os.environ.get("SIEM_INCIDENT_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return

    payload = {
        "type": "siem_incident",
        "incident_id": incident.get("incident_id"),
        "severity": incident.get("severity"),
        "status": incident.get("status"),
        "rule_id": incident.get("rule_id"),
        "event_type": incident.get("event_type"),
        "event_count": incident.get("event_count"),
        "ts": incident.get("ts"),
        "message": incident.get("message"),
    }
    sent_at = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(webhook_url, json=payload)
        await db.siem_incident_webhook_log.insert_one(
            {
                "incident_id": incident.get("incident_id"),
                "status_code": int(response.status_code),
                "ok": bool(200 <= int(response.status_code) < 300),
                "sent_at": sent_at,
            }
        )
    except Exception as exc:
        await db.siem_incident_webhook_log.insert_one(
            {
                "incident_id": incident.get("incident_id"),
                "ok": False,
                "error": str(exc),
                "sent_at": sent_at,
            }
        )


async def _open_security_incident_for_alert(alert_doc: dict) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    rule_id = str(alert_doc.get("rule_id") or "")
    existing = await db.security_incidents.find_one(
        {
            "source": "siem",
            "rule_id": rule_id,
            "status": {"$in": ["open", "active", "investigating"]},
        },
        {"_id": 0},
    )
    if existing:
        return existing

    incident = {
        "incident_id": f"siem_inc_{uuid.uuid4().hex[:12]}",
        "source": "siem",
        "rule_id": rule_id,
        "severity": alert_doc.get("severity", "medium"),
        "status": "open",
        "event_type": alert_doc.get("event_type"),
        "event_count": int(alert_doc.get("actual_count") or 0),
        "message": f"SIEM rule triggered: {alert_doc.get('name') or rule_id}",
        "ts": now_iso,
        "created_at": now_iso,
        "details": {
            "threshold": alert_doc.get("threshold"),
            "window_minutes": alert_doc.get("window_minutes"),
            "alert_id": alert_doc.get("alert_id"),
        },
    }
    await db.security_incidents.insert_one(incident)
    await _dispatch_incident_webhook(incident)
    safe_incident = dict(incident)
    safe_incident.pop("_id", None)
    return safe_incident


async def _apply_containment_for_alert(rule: dict, event_query: dict, alert_doc: dict) -> None:
    # Containment-only policy: temporary IP block for repeated hostile patterns.
    # No destructive actions (no global session revocation here).
    if str(rule.get("event_type") or "") not in {"failed_login", "jwt_invalid", "query_token_auth_used"}:
        return

    docs = await db.security_events.find(event_query, {"_id": 0, "ip_address": 1}).to_list(200)
    ips = [str(d.get("ip_address") or "").strip() for d in docs if str(d.get("ip_address") or "").strip()]
    if not ips:
        return

    top_ip, count = Counter(ips).most_common(1)[0]
    try:
        ip_obj = ipaddress.ip_address(top_ip)
        if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_reserved:
            return
    except Exception:
        return

    if count < 3:
        return

    now = datetime.now(timezone.utc)
    blocked_until = now + timedelta(minutes=30)
    await db.blocked_ips.update_one(
        {"ip": top_ip},
        {
            "$set": {
                "ip": top_ip,
                "reason": f"siem_auto_containment:{rule.get('rule_id')}",
                "blocked_at": now,
                "expires_at": blocked_until,
                "source": "siem_auto",
            }
        },
        upsert=True,
    )

    await db.siem_remediation_actions.insert_one(
        {
            "action_id": f"siem_act_{uuid.uuid4().hex[:12]}",
            "rule_id": rule.get("rule_id"),
            "alert_id": alert_doc.get("alert_id"),
            "type": "temporary_ip_block",
            "target_ip": top_ip,
            "event_count": count,
            "created_at": now.isoformat(),
            "expires_at": blocked_until.isoformat(),
        }
    )


@router.get("/overview")
async def siem_overview(req: Request):
    await require_admin(req)
    now = datetime.now(timezone.utc)
    day_str = (now - timedelta(days=1)).isoformat()
    week_str = (now - timedelta(days=7)).isoformat()

    total_events = await db.security_events.count_documents({})
    events_24h = await db.security_events.count_documents({"timestamp": {"$gte": day_str}})
    events_7d = await db.security_events.count_documents({"timestamp": {"$gte": week_str}})
    critical_24h = await db.security_events.count_documents({"timestamp": {"$gte": day_str}, "risk_level": "critical"})
    high_24h = await db.security_events.count_documents({"timestamp": {"$gte": day_str}, "risk_level": "high"})

    severity = {
        doc["_id"]: doc["count"]
        async for doc in db.security_events.aggregate(
            [
                {"$match": {"timestamp": {"$gte": week_str}}},
                {"$group": {"_id": "$risk_level", "count": {"$sum": 1}}},
            ]
        )
    }

    types = [
        {"type": doc["_id"], "count": doc["count"]}
        async for doc in db.security_events.aggregate(
            [
                {"$match": {"timestamp": {"$gte": week_str}}},
                {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ]
        )
    ]

    critical_events = []
    async for doc in (
        db.security_events.find(
            {"risk_level": {"$in": ["critical", "high"]}, "timestamp": {"$gte": week_str}}, {"_id": 0}
        )
        .sort("timestamp", -1)
        .limit(10)
    ):
        critical_events.append(doc)

    active_alerts = await db.security_alerts.count_documents({"status": {"$in": ["active", "open", "pending"]}})

    return {
        "total_events": total_events,
        "events_24h": events_24h,
        "events_7d": events_7d,
        "critical_24h": critical_24h,
        "high_24h": high_24h,
        "active_alerts": active_alerts,
        "severity_breakdown": severity,
        "event_types": types,
        "critical_events": critical_events,
    }


@router.get("/events")
async def siem_events(
    req: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    event_type: str = Query(None),
    risk_level: str = Query(None),
    user_id: str = Query(None),
    search: str = Query(None),
    days: int = Query(7, ge=1, le=90),
):
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query: dict = {"timestamp": {"$gte": cutoff}}
    if event_type:
        query["event_type"] = event_type
    if risk_level:
        query["risk_level"] = risk_level
    if user_id:
        query["user_id"] = user_id
    if search:
        query["$or"] = [
            {"event_type": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"user_id": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]

    total = await db.security_events.count_documents(query)
    skip = (page - 1) * limit
    events = []
    async for doc in db.security_events.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit):
        events.append(doc)

    return {"events": events, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@router.get("/timeline")
async def siem_timeline(req: Request, days: int = Query(7, ge=1, le=30)):
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    raw = {}
    async for doc in db.security_events.aggregate(
        [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$addFields": {"day": {"$substr": ["$timestamp", 0, 10]}}},
            {"$group": {"_id": {"day": "$day", "risk": "$risk_level"}, "count": {"$sum": 1}}},
            {"$sort": {"_id.day": 1}},
        ]
    ):
        day = doc["_id"]["day"]
        risk = doc["_id"].get("risk") or "unknown"
        if day not in raw:
            raw[day] = {"day": day, "low": 0, "medium": 0, "high": 0, "critical": 0}
        if risk in raw[day]:
            raw[day][risk] = doc["count"]

    hourly = [
        {"hour": doc["_id"], "count": doc["count"]}
        async for doc in db.security_events.aggregate(
            [
                {"$match": {"timestamp": {"$gte": cutoff}}},
                {"$addFields": {"hour": {"$substr": ["$timestamp", 11, 2]}}},
                {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        )
    ]

    return {"daily": list(raw.values()), "hourly": hourly}


@router.get("/audit-log")
async def siem_audit_log(
    req: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    action: str = Query(None),
    days: int = Query(7, ge=1, le=90),
):
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query: dict = {"created_at": {"$gte": cutoff}}
    if action:
        query["action"] = {"$regex": re.escape(str(action)), "$options": "i"}

    total = await db.admin_audit_logs.count_documents(query)
    skip = (page - 1) * limit
    logs = []
    async for doc in db.admin_audit_logs.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit):
        logs.append(doc)

    return {"logs": logs, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@router.get("/alert-rules")
async def siem_alert_rules(req: Request):
    await require_admin(req)
    await _ensure_default_siem_rules()
    rules = []
    async for doc in db.siem_alert_rules.find({}, {"_id": 0}):
        rules.append(doc)
    return {"rules": rules}


@router.post("/alert-rules")
async def create_alert_rule(req: Request, body: dict):
    user = await require_admin(req)
    rule = {
        "rule_id": f"rule_{uuid.uuid4().hex[:12]}",
        "name": body.get("name", "Untitled Rule"),
        "event_type": body.get("event_type", "login_failed"),
        "threshold": body.get("threshold", 5),
        "window_minutes": body.get("window_minutes", 10),
        "severity": body.get("severity", "high"),
        "enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": getattr(user, "user_id", ""),
    }
    await db.siem_alert_rules.insert_one(rule)
    rule.pop("_id", None)
    return rule


@router.delete("/alert-rules/{rule_id}")
async def delete_alert_rule(rule_id: str, req: Request):
    await require_admin(req)
    result = await db.siem_alert_rules.delete_one({"rule_id": rule_id})
    return {"deleted": result.deleted_count > 0}


# --- Auto-Alert Evaluation Engine ---


@router.get("/alerts")
async def siem_alerts(req: Request, page: int = Query(1, ge=1), limit: int = Query(30, ge=1, le=100)):
    """Get triggered alert history."""
    await require_admin(req)
    total = await db.siem_triggered_alerts.count_documents({})
    skip = (page - 1) * limit
    alerts = []
    async for doc in db.siem_triggered_alerts.find({}, {"_id": 0}).sort("triggered_at", -1).skip(skip).limit(limit):
        alerts.append(doc)
    return {"alerts": alerts, "total": total, "page": page}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, req: Request):
    """Resolve a triggered alert."""
    await require_admin(req)
    result = await db.siem_triggered_alerts.update_one(
        {"alert_id": alert_id}, {"$set": {"status": "resolved", "resolved_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"resolved": result.modified_count > 0}


@router.post("/evaluate-rules")
async def evaluate_rules_now(req: Request):
    """Manually trigger alert rule evaluation."""
    await require_admin(req)
    triggered = await _evaluate_alert_rules()
    return {"triggered": triggered}


@router.post("/incidents/{incident_id}/dispatch-webhook")
async def dispatch_incident_webhook(req: Request, incident_id: str):
    """Manually dispatch incident payload to configured SIEM incident webhook."""
    await require_admin(req)
    incident = await db.security_incidents.find_one({"incident_id": incident_id}, {"_id": 0})
    if not incident:
        return {"sent": False, "reason": "incident_not_found", "incident_id": incident_id}
    await _dispatch_incident_webhook(incident)
    return {"sent": True, "incident_id": incident_id}


async def _evaluate_alert_rules():
    """Core alert evaluation logic — check rules against recent events."""
    await _ensure_default_siem_rules()
    rules = []
    async for rule in db.siem_alert_rules.find({"enabled": True}, {"_id": 0}):
        rules.append(rule)

    triggered = 0
    now = datetime.now(timezone.utc)

    for rule in rules:
        window = timedelta(minutes=rule.get("window_minutes", 10))
        cutoff = (now - window).isoformat()
        event_type = rule.get("event_type", "")
        threshold = rule.get("threshold", 5)
        event_query = {
            "timestamp": {"$gte": cutoff},
            "event_type": event_type,
        }

        count = await db.security_events.count_documents(event_query)

        if count >= threshold:
            # Check if already triggered recently (within window) to avoid duplicates
            recent = await db.siem_triggered_alerts.find_one(
                {
                    "rule_id": rule["rule_id"],
                    "triggered_at": {"$gte": cutoff},
                    "status": {"$ne": "resolved"},
                }
            )
            if not recent:
                alert_doc = {
                    "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
                    "rule_id": rule["rule_id"],
                    "rule_name": rule.get("name", ""),
                    "event_type": event_type,
                    "threshold": threshold,
                    "actual_count": count,
                    "window_minutes": rule.get("window_minutes", 10),
                    "severity": rule.get("severity", "high"),
                    "status": "active",
                    "triggered_at": now.isoformat(),
                }
                await db.siem_triggered_alerts.insert_one(alert_doc)
                alert_doc.pop("_id", None)
                await _open_security_incident_for_alert(alert_doc)
                await _apply_containment_for_alert(rule, event_query, alert_doc)
                triggered += 1

    return triggered


# --- Performance Monitoring Endpoints ---


@router.get("/perf/history")
async def perf_history(req: Request, minutes: int = Query(30, ge=5, le=120)):
    """Get historical performance metrics."""
    await require_admin(req)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    metrics = []
    async for doc in db.perf_metrics_history.find({"timestamp": {"$gte": cutoff}}, {"_id": 0}).sort("timestamp", 1):
        metrics.append(doc)
    return {"metrics": metrics, "count": len(metrics)}
