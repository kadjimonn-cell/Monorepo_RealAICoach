"""
Custom Admin Notification Rules — CRUD API for configurable alert thresholds.
Admins can create, update, toggle, and delete custom rules that override hardcoded defaults.
"""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
from routes.db import db, require_admin

logger = logging.getLogger("notification_rules")

router = APIRouter(prefix="/admin/notification-rules", tags=["admin-notification-rules"])

# ──────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────

VALID_METRICS = [
    "errors", "signups", "payments_success", "payments_failed",
    "tickets", "ttfb", "sessions", "security_events"
]
VALID_OPERATORS = [">=", ">", "==", "<", "<="]
VALID_SEVERITIES = ["critical", "warning", "info"]


class RuleCondition(BaseModel):
    metric: str = Field(..., description="Metric to monitor")
    operator: str = Field(default=">=", description="Comparison operator")
    threshold: float = Field(..., description="Threshold value to trigger alert")
    time_window_minutes: int = Field(default=5, description="Time window in minutes")


class CreateRuleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    condition: RuleCondition
    severity: str = Field(default="warning")
    cooldown_minutes: int = Field(default=5, ge=1, le=1440)
    enabled: bool = Field(default=True)


class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    condition: Optional[RuleCondition] = None
    severity: Optional[str] = None
    cooldown_minutes: Optional[int] = None
    enabled: Optional[bool] = None


# ──────────────────────────────────────────────────────────
# Default rules (seeded on first access if collection empty)
# ──────────────────────────────────────────────────────────

DEFAULT_RULES = [
    {
        "name": "Error Spike",
        "condition": {"metric": "errors", "operator": ">=", "threshold": 5, "time_window_minutes": 5},
        "severity": "critical",
        "cooldown_minutes": 2,
        "is_default": True,
    },
    {
        "name": "New User Signup",
        "condition": {"metric": "signups", "operator": ">", "threshold": 0, "time_window_minutes": 5},
        "severity": "info",
        "cooldown_minutes": 2,
        "is_default": True,
    },
    {
        "name": "Payment Received",
        "condition": {"metric": "payments_success", "operator": ">", "threshold": 0, "time_window_minutes": 5},
        "severity": "info",
        "cooldown_minutes": 2,
        "is_default": True,
    },
    {
        "name": "Payment Failure",
        "condition": {"metric": "payments_failed", "operator": ">", "threshold": 0, "time_window_minutes": 5},
        "severity": "warning",
        "cooldown_minutes": 2,
        "is_default": True,
    },
    {
        "name": "Support Ticket Surge",
        "condition": {"metric": "tickets", "operator": ">=", "threshold": 5, "time_window_minutes": 60},
        "severity": "warning",
        "cooldown_minutes": 10,
        "is_default": True,
    },
    {
        "name": "Slow API Response",
        "condition": {"metric": "ttfb", "operator": ">=", "threshold": 2000, "time_window_minutes": 5},
        "severity": "warning",
        "cooldown_minutes": 5,
        "is_default": True,
    },
    {
        "name": "High Active Sessions",
        "condition": {"metric": "sessions", "operator": ">=", "threshold": 50, "time_window_minutes": 0},
        "severity": "info",
        "cooldown_minutes": 10,
        "is_default": True,
    },
    {
        "name": "Security Alert",
        "condition": {"metric": "security_events", "operator": ">=", "threshold": 3, "time_window_minutes": 5},
        "severity": "critical",
        "cooldown_minutes": 2,
        "is_default": True,
    },
]


async def _get_db():
    return db


async def _seed_defaults_if_empty(database):
    """Seed default rules if collection is empty."""
    count = await database.notification_rules.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc).isoformat()
        for rule in DEFAULT_RULES:
            await database.notification_rules.insert_one({
                "rule_id": f"rule_{uuid.uuid4().hex[:12]}",
                **rule,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            })
        logger.info(f"Seeded {len(DEFAULT_RULES)} default notification rules")


# ──────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────

@router.get("")
async def list_rules(req: Request):
    """List all notification rules."""
    await require_admin(req)
    await _seed_defaults_if_empty(db)

    rules = await db.notification_rules.find(
        {}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)

    return {
        "rules": rules,
        "total": len(rules),
        "valid_metrics": VALID_METRICS,
        "valid_operators": VALID_OPERATORS,
        "valid_severities": VALID_SEVERITIES,
    }


@router.post("")
async def create_rule(body: CreateRuleRequest, req: Request):
    """Create a new custom notification rule."""
    await require_admin(req)

    if body.condition.metric not in VALID_METRICS:
        raise HTTPException(400, f"Invalid metric. Must be one of: {VALID_METRICS}")
    if body.condition.operator not in VALID_OPERATORS:
        raise HTTPException(400, f"Invalid operator. Must be one of: {VALID_OPERATORS}")
    if body.severity not in VALID_SEVERITIES:
        raise HTTPException(400, f"Invalid severity. Must be one of: {VALID_SEVERITIES}")

    now = datetime.now(timezone.utc).isoformat()
    rule = {
        "rule_id": f"rule_{uuid.uuid4().hex[:12]}",
        "name": body.name,
        "condition": body.condition.dict(),
        "severity": body.severity,
        "cooldown_minutes": body.cooldown_minutes,
        "enabled": body.enabled,
        "is_default": False,
        "created_at": now,
        "updated_at": now,
    }

    await db.notification_rules.insert_one(rule)
    rule.pop("_id", None)

    logger.info(f"Created notification rule: {rule['name']} ({rule['rule_id']})")
    return {"message": "Rule created", "rule": rule}


@router.put("/{rule_id}")
async def update_rule(rule_id: str, body: UpdateRuleRequest, req: Request):
    """Update an existing notification rule."""
    await require_admin(req)

    if body.condition and body.condition.metric not in VALID_METRICS:
        raise HTTPException(400, f"Invalid metric. Must be one of: {VALID_METRICS}")
    if body.condition and body.condition.operator not in VALID_OPERATORS:
        raise HTTPException(400, f"Invalid operator. Must be one of: {VALID_OPERATORS}")
    if body.severity and body.severity not in VALID_SEVERITIES:
        raise HTTPException(400, f"Invalid severity. Must be one of: {VALID_SEVERITIES}")

    existing = await db.notification_rules.find_one({"rule_id": rule_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Rule not found")

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.name is not None:
        update["name"] = body.name
    if body.condition is not None:
        update["condition"] = body.condition.dict()
    if body.severity is not None:
        update["severity"] = body.severity
    if body.cooldown_minutes is not None:
        update["cooldown_minutes"] = body.cooldown_minutes
    if body.enabled is not None:
        update["enabled"] = body.enabled

    await db.notification_rules.update_one({"rule_id": rule_id}, {"$set": update})
    updated = await db.notification_rules.find_one({"rule_id": rule_id}, {"_id": 0})

    logger.info(f"Updated notification rule: {rule_id}")
    return {"message": "Rule updated", "rule": updated}


@router.put("/{rule_id}/toggle")
async def toggle_rule(rule_id: str, req: Request):
    """Toggle a rule enabled/disabled."""
    await require_admin(req)

    existing = await db.notification_rules.find_one({"rule_id": rule_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Rule not found")

    new_state = not existing.get("enabled", True)
    await db.notification_rules.update_one(
        {"rule_id": rule_id},
        {"$set": {"enabled": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    logger.info(f"Toggled rule {rule_id}: enabled={new_state}")
    return {"message": f"Rule {'enabled' if new_state else 'disabled'}", "enabled": new_state}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str, req: Request):
    """Delete a notification rule."""
    await require_admin(req)

    existing = await db.notification_rules.find_one({"rule_id": rule_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Rule not found")

    await db.notification_rules.delete_one({"rule_id": rule_id})
    logger.info(f"Deleted notification rule: {rule_id}")
    return {"message": "Rule deleted"}


@router.post("/test/{rule_id}")
async def test_rule(rule_id: str, req: Request):
    """Test a notification rule by checking current data against its condition."""
    await require_admin(req)

    rule = await db.notification_rules.find_one({"rule_id": rule_id}, {"_id": 0})
    if not rule:
        raise HTTPException(404, "Rule not found")

    condition = rule.get("condition", {})
    metric = condition.get("metric", "")
    threshold = condition.get("threshold", 0)
    time_window = condition.get("time_window_minutes", 5)
    operator = condition.get("operator", ">=")

    current_value = await _get_metric_value(db, metric, time_window)
    triggered = _evaluate_condition(current_value, operator, threshold)

    return {
        "rule": rule,
        "current_value": current_value,
        "threshold": threshold,
        "operator": operator,
        "triggered": triggered,
        "message": f"Rule would {'FIRE' if triggered else 'NOT fire'} — {metric} = {current_value} {operator} {threshold}",
    }


# ──────────────────────────────────────────────────────────
# Core engine: read rules from DB and evaluate
# ──────────────────────────────────────────────────────────

# Cooldown tracker per rule_id
_rule_cooldowns: dict = {}


async def evaluate_custom_rules():
    """
    Called by scheduler — reads all enabled rules from DB and evaluates them.
    """
    try:
        from utils.ws_manager import ws_manager

        await _seed_defaults_if_empty(db)

        rules = await db.notification_rules.find(
            {"enabled": True}, {"_id": 0}
        ).to_list(100)

        now = datetime.now(timezone.utc)
        alerts = []

        for rule in rules:
            rule_id = rule.get("rule_id", "")
            condition = rule.get("condition", {})
            metric = condition.get("metric", "")
            threshold = condition.get("threshold", 0)
            time_window = condition.get("time_window_minutes", 5)
            operator = condition.get("operator", ">=")
            cooldown = rule.get("cooldown_minutes", 5)

            # Check cooldown
            last_fire = _rule_cooldowns.get(rule_id)
            if last_fire and (now - last_fire).total_seconds() < cooldown * 60:
                continue

            current_value = await _get_metric_value(db, metric, time_window)
            if _evaluate_condition(current_value, operator, threshold):
                _rule_cooldowns[rule_id] = now
                alerts.append({
                    "type": "admin_alert",
                    "severity": rule.get("severity", "warning"),
                    "alert_type": f"custom_{metric}",
                    "title": rule.get("name", "Custom Alert"),
                    "message": f"{rule.get('name', 'Alert')}: {metric} = {current_value} (threshold: {operator} {threshold})",
                    "timestamp": now.isoformat(),
                    "rule_id": rule_id,
                    "current_value": current_value,
                })

        if alerts:
            admin_users = await db.users.find(
                {"is_admin": True}, {"_id": 0, "user_id": 1}
            ).to_list(50)
            admin_ids = [u["user_id"] for u in admin_users]

            for alert in alerts:
                try:
                    await ws_manager.send_to_admins(alert, admin_ids)
                    logger.info(f"Custom rule fired: {alert['title']}")
                except Exception as e:
                    logger.warning(f"Failed to push custom alert: {e}")

                try:
                    await db.admin_push_notifications.insert_one({
                        "type": alert["alert_type"],
                        "severity": alert["severity"],
                        "title": alert["title"],
                        "message": alert["message"],
                        "timestamp": now.isoformat(),
                        "read": False,
                        "rule_id": alert.get("rule_id"),
                    })
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Custom rule evaluation error: {e}")


async def _get_metric_value(db, metric: str, time_window_minutes: int) -> float:
    """Get current metric value from the database."""
    now = datetime.now(timezone.utc)
    window_start = now - __import__("datetime").timedelta(minutes=max(time_window_minutes, 1))
    window_iso = window_start.isoformat()

    try:
        if metric == "errors":
            return await db.live_activity_events.count_documents({
                "event_type": "error",
                "timestamp": {"$gte": window_iso}
            })
        elif metric == "signups":
            return await db.users.count_documents({
                "created_at": {"$gte": window_iso}
            })
        elif metric == "payments_success":
            return await db.payments.count_documents({
                "created_at": {"$gte": window_iso},
                "status": {"$in": ["completed", "succeeded", "active"]}
            })
        elif metric == "payments_failed":
            return await db.payments.count_documents({
                "created_at": {"$gte": window_iso},
                "status": {"$in": ["failed", "declined", "cancelled"]}
            })
        elif metric == "tickets":
            return await db.support_tickets.count_documents({
                "created_at": {"$gte": window_iso},
                "status": {"$in": ["open", "pending"]}
            })
        elif metric == "ttfb":
            vitals = await db.web_vitals.find(
                {"metric": "TTFB", "timestamp": {"$gte": window_iso}},
                {"_id": 0, "value": 1}
            ).to_list(100)
            if vitals:
                return sum(v.get("value", 0) for v in vitals) / len(vitals)
            return 0
        elif metric == "sessions":
            return await db.user_sessions.count_documents({
                "expires_at": {"$gt": now.isoformat()}
            })
        elif metric == "security_events":
            return await db.security_events.count_documents({
                "event_type": {"$in": ["failed_login", "suspicious_login", "brute_force"]},
                "created_at": {"$gte": window_iso}
            })
    except Exception as e:
        logger.warning(f"Failed to get metric {metric}: {e}")

    return 0


def _evaluate_condition(value: float, operator: str, threshold: float) -> bool:
    """Evaluate a condition."""
    if operator == ">=":
        return value >= threshold
    elif operator == ">":
        return value > threshold
    elif operator == "==":
        return value == threshold
    elif operator == "<":
        return value < threshold
    elif operator == "<=":
        return value <= threshold
    return False
