"""Admin Auto-Response Rules — automated actions triggered by session anomalies."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from routes.db import db, require_admin
import os
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/sessions/auto-response", tags=["Auto-Response"])

TRIGGER_TYPES = ["rapid_fire_ip", "session_flood", "ip_hopping"]
ACTION_TYPES = ["block_ip", "revoke_sessions", "lock_account", "notify_admin"]


@router.get("/rules")
async def list_rules(request: Request):
    await require_admin(request)
    rules = await db.auto_response_rules.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"rules": rules}


@router.post("/rules")
async def create_rule(request: Request):
    await require_admin(request)
    body = await request.json()

    name = body.get("name", "").strip()
    trigger = body.get("trigger_type", "")
    action = body.get("action", "")
    threshold = body.get("threshold", 5)
    cooldown_minutes = body.get("cooldown_minutes", 15)
    enabled = body.get("enabled", True)

    if not name:
        return JSONResponse(status_code=400, content={"error": "Rule name is required"})
    if trigger not in TRIGGER_TYPES:
        return JSONResponse(
            status_code=400, content={"error": f"Invalid trigger_type. Must be one of: {TRIGGER_TYPES}"}
        )
    if action not in ACTION_TYPES:
        return JSONResponse(status_code=400, content={"error": f"Invalid action. Must be one of: {ACTION_TYPES}"})

    rule = {
        "rule_id": f"rule_{uuid.uuid4().hex[:12]}",
        "name": name,
        "trigger_type": trigger,
        "action": action,
        "threshold": max(1, int(threshold)),
        "cooldown_minutes": max(1, int(cooldown_minutes)),
        "enabled": enabled,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_triggered": None,
        "trigger_count": 0,
    }
    await db.auto_response_rules.insert_one(rule)
    rule.pop("_id", None)
    return {"rule": rule}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, request: Request):
    await require_admin(request)
    body = await request.json()

    update = {}
    if "enabled" in body:
        update["enabled"] = bool(body["enabled"])
    if "name" in body:
        update["name"] = body["name"].strip()
    if "threshold" in body:
        update["threshold"] = max(1, int(body["threshold"]))
    if "cooldown_minutes" in body:
        update["cooldown_minutes"] = max(1, int(body["cooldown_minutes"]))
    if "trigger_type" in body and body["trigger_type"] in TRIGGER_TYPES:
        update["trigger_type"] = body["trigger_type"]
    if "action" in body and body["action"] in ACTION_TYPES:
        update["action"] = body["action"]

    if not update:
        return JSONResponse(status_code=400, content={"error": "No valid fields to update"})

    await db.auto_response_rules.update_one({"rule_id": rule_id}, {"$set": update})
    updated = await db.auto_response_rules.find_one({"rule_id": rule_id}, {"_id": 0})
    return {"rule": updated}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, request: Request):
    await require_admin(request)
    result = await db.auto_response_rules.delete_one({"rule_id": rule_id})
    return {"deleted": result.deleted_count > 0}


@router.get("/log")
async def get_action_log(request: Request, limit: int = 30):
    await require_admin(request)
    logs = await db.auto_response_log.find({}, {"_id": 0}).sort("executed_at", -1).to_list(min(limit, 100))
    return {"logs": logs, "count": len(logs)}


@router.post("/execute")
async def execute_auto_responses(request: Request):
    """Run anomaly detection and execute matching auto-response rules."""
    await require_admin(request)
    result = await _execute_scan(db)
    return result


@router.get("/scheduler")
async def get_scheduler_config(request: Request):
    await require_admin(request)
    config = await db.auto_response_config.find_one({"config_id": "scheduler"}, {"_id": 0})
    if not config:
        config = {"config_id": "scheduler", "enabled": False, "interval_minutes": 5, "last_run": None}
    return config


@router.put("/scheduler")
async def update_scheduler_config(request: Request):
    await require_admin(request)
    body = await request.json()
    update = {}
    if "enabled" in body:
        update["enabled"] = bool(body["enabled"])
    if "interval_minutes" in body:
        update["interval_minutes"] = max(1, min(60, int(body["interval_minutes"])))

    await db.auto_response_config.update_one(
        {"config_id": "scheduler"},
        {"$set": {**update, "config_id": "scheduler"}},
        upsert=True,
    )
    config = await db.auto_response_config.find_one({"config_id": "scheduler"}, {"_id": 0})
    return config


async def _execute_scan(database) -> dict:
    """Core scan logic — used by both the API and the scheduler job."""
    rules = await database.auto_response_rules.find({"enabled": True}, {"_id": 0}).to_list(100)
    if not rules:
        return {"executed": 0, "message": "No active rules"}

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    recent = await database.user_sessions.find(
        {"created_at": {"$gte": cutoff}},
        {"_id": 0, "user_id": 1, "ip_address": 1, "created_at": 1, "session_id": 1},
    ).to_list(5000)

    if not recent:
        return {"executed": 0, "message": "No recent sessions"}

    # Build anomaly data
    ip_times: dict[str, list] = defaultdict(list)
    user_sessions_map: dict[str, list] = defaultdict(list)
    for s in recent:
        ip = s.get("ip_address", "")
        if ip:
            ip_times[ip].append(s)
        user_sessions_map[s["user_id"]].append(s)
    # Detect anomalies per type
    anomalies_by_type: dict[str, list] = defaultdict(list)

    # Rapid-fire IP
    for ip, sessions in ip_times.items():
        sessions.sort(key=lambda s: s["created_at"])
        times = [s["created_at"] for s in sessions]
        for i in range(len(times)):
            window_end = times[i] + timedelta(seconds=60)
            burst = [t for t in times[i:] if t <= window_end]
            if len(burst) >= 5:
                anomalies_by_type["rapid_fire_ip"].append(
                    {
                        "ip": ip,
                        "count": len(burst),
                        "session_ids": [s.get("session_id", "") for s in sessions if s.get("session_id")],
                        "user_ids": list({s["user_id"] for s in sessions}),
                    }
                )
                break

    # Session flood
    for uid, sessions in user_sessions_map.items():
        if len(sessions) >= 10:
            anomalies_by_type["session_flood"].append(
                {
                    "user_id": uid,
                    "count": len(sessions),
                    "session_ids": [s.get("session_id", "") for s in sessions],
                }
            )

    # IP hopping
    for uid, sessions in user_sessions_map.items():
        unique_ips = list({s.get("ip_address", "") for s in sessions if s.get("ip_address")})
        if len(unique_ips) >= 3:
            anomalies_by_type["ip_hopping"].append(
                {
                    "user_id": uid,
                    "ips": unique_ips,
                    "count": len(unique_ips),
                    "session_ids": [s.get("session_id", "") for s in sessions],
                }
            )

    # Lookup emails
    all_uids = set()
    for anomalies in anomalies_by_type.values():
        for a in anomalies:
            all_uids.update(a.get("user_ids", []))
            if "user_id" in a:
                all_uids.add(a["user_id"])
    email_map = {}
    if all_uids:
        users = await database.users.find(
            {"user_id": {"$in": list(all_uids)}}, {"_id": 0, "user_id": 1, "email": 1}
        ).to_list(500)
        email_map = {u["user_id"]: u.get("email", "") for u in users}

    # Execute matching rules
    now = datetime.now(timezone.utc)
    executed = []
    for rule in rules:
        trigger = rule["trigger_type"]
        matching = anomalies_by_type.get(trigger, [])

        for anomaly in matching:
            count = anomaly.get("count", 0)
            if count < rule.get("threshold", 5):
                continue

            # Check cooldown
            last = rule.get("last_triggered")
            if last:
                last_dt = datetime.fromisoformat(last) if isinstance(last, str) else last
                if (now - last_dt).total_seconds() < rule["cooldown_minutes"] * 60:
                    continue

            # Execute action
            action = rule["action"]
            result = await _execute_action(action, anomaly, email_map, database)

            log_entry = {
                "log_id": f"arlog_{uuid.uuid4().hex[:12]}",
                "rule_id": rule["rule_id"],
                "rule_name": rule["name"],
                "trigger_type": trigger,
                "action": action,
                "anomaly_detail": _safe_anomaly_detail(anomaly),
                "result": result,
                "executed_at": now.isoformat(),
            }
            await database.auto_response_log.insert_one(log_entry)
            log_entry.pop("_id", None)
            executed.append(log_entry)

            # Update rule trigger info
            await database.auto_response_rules.update_one(
                {"rule_id": rule["rule_id"]},
                {"$set": {"last_triggered": now.isoformat()}, "$inc": {"trigger_count": 1}},
            )

    # Update last_run timestamp
    await database.auto_response_config.update_one(
        {"config_id": "scheduler"},
        {"$set": {"last_run": now.isoformat()}},
        upsert=True,
    )

    return {"executed": len(executed), "actions": executed}


def _safe_anomaly_detail(anomaly: dict) -> dict:
    """Return a JSON-safe subset of anomaly data for logging."""
    return {k: v for k, v in anomaly.items() if k in ("ip", "user_id", "count", "ips", "user_ids")}


async def _execute_action(action: str, anomaly: dict, email_map: dict, database=None) -> dict:
    """Execute a single auto-response action. Returns result dict."""
    if database is None:
        database = db
    try:
        if action == "block_ip":
            ip = anomaly.get("ip", "")
            if ip:
                await database.blocked_ips.update_one(
                    {"ip": ip},
                    {
                        "$set": {
                            "ip": ip,
                            "blocked_at": datetime.now(timezone.utc).isoformat(),
                            "reason": "auto-response",
                        }
                    },
                    upsert=True,
                )
                return {"success": True, "detail": f"Blocked IP {ip}"}
            return {"success": False, "detail": "No IP to block"}

        elif action == "revoke_sessions":
            session_ids = anomaly.get("session_ids", [])
            if session_ids:
                result = await database.user_sessions.delete_many({"session_id": {"$in": session_ids[:50]}})
                return {"success": True, "detail": f"Revoked {result.deleted_count} sessions"}
            return {"success": False, "detail": "No sessions to revoke"}

        elif action == "lock_account":
            user_ids = anomaly.get("user_ids", [])
            uid = anomaly.get("user_id")
            if uid:
                user_ids = [uid]
            if user_ids:
                await database.users.update_many(
                    {"user_id": {"$in": user_ids}},
                    {
                        "$set": {
                            "account_locked": True,
                            "locked_at": datetime.now(timezone.utc).isoformat(),
                            "lock_reason": "auto-response",
                        }
                    },
                )
                return {"success": True, "detail": f"Locked {len(user_ids)} account(s)"}
            return {"success": False, "detail": "No accounts to lock"}

        elif action == "notify_admin":
            try:
                from utils.email_service import is_email_configured, render_email_header_panel

                if not is_email_configured():
                    return {"success": True, "detail": "Notification logged (email not configured)"}

                event_count = anomaly.get("count", 0)
                detail = f"Auto-response triggered: {event_count} events detected"
                header_html = render_email_header_panel(
                    title="Auto-Response Alert",
                    subtitle=detail,
                    variant="security",
                    accent="#F59E0B",
                    meta_label="Events",
                    meta_value=f"{event_count} detected",
                )
                f'''<div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#F8FAFC">
<div style="border-radius:20px;overflow:hidden;margin-bottom:20px">{header_html}</div>
<div class="em-force-light-card" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:20px 24px;">
  <p class="em-force-dark-text" style="color:#0F172A;font-size:15px;font-weight:700;margin:0 0 8px">Automated Action Taken</p>
  <p class="em-force-muted-text" style="color:#475569;font-size:14px;line-height:1.6;margin:0">{detail}. The system has automatically executed the configured response action. Review the activity log for full details.</p>
</div>
<p style="margin-top:20px;text-align:center"><a href="{os.environ.get("FRONTEND_BASE_URL", "")}/admin-activity-log" class="email-primary-cta" style="display:inline-block;background:#F59E0B;color:#0F172A;padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:800;font-size:14px;letter-spacing:0.3px;-webkit-text-fill-color:#0F172A;">View Activity Log</a></p>
<p class="em-force-muted-text" style="color:#64748B;font-size:11px;text-align:center;margin-top:16px">RealAICoach Auto-Response System</p>
</div>'''
                from utils.email_service import send_catalog_template
                await send_catalog_template(
                    "admin@realaicoach.app",
                    "system_alert_admin",
                    alert_type="Auto-Response Alert",
                    severity="WARNING",
                    description=f"{detail}. The system has automatically executed the configured response action.",
                    component="Auto-Response System",
                )
                return {"success": True, "detail": "Admin notified via email"}
            except Exception as e:
                logger.warning(f"Notify admin failed: {e}")
                return {"success": True, "detail": "Notification logged (email delivery attempted)"}

        return {"success": False, "detail": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"Auto-response action error: {e}")
        return {"success": False, "detail": str(e)}
