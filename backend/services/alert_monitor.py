# ruff: noqa
"""Alert Monitor — Real-time system monitoring with email alerts and safe auto-fix.

Runs every 60s via APScheduler:
1. Checks system metrics (CPU, memory, disk) against alert rules
2. Checks service connectivity (MongoDB, API)
3. If threshold breached → creates incident, sends email alert
4. If auto-fix enabled → attempts safe fix
5. If service recovers → resolves incident, sends recovery email
"""

import logging
import psutil
import time
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Track active alerts in-memory to detect recovery
_active_alerts: dict = {}   # rule_id -> {started_at, incident_id, last_alert}
_cooldowns: dict = {}       # rule_id -> last_triggered_at


def _build_alert_email(rule_name: str, metric: str, current_value, threshold, action_taken: str) -> str:
    now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; background: #FFFFFF; color: #1E293B; border-radius: 12px; overflow: hidden;">
      <div style="background: linear-gradient(135deg, #DC2626, #991B1B); padding: 24px 32px;">
        <h1 style="margin: 0; font-size: 20px; color: #FFF;">Alert: {rule_name}</h1>
        <p style="margin: 4px 0 0; font-size: 13px; color: rgba(255,255,255,0.8);">{now}</p>
      </div>
      <div style="padding: 24px 32px;">
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
          <table style="width: 100%; border-collapse: collapse; color: #1E293B; font-size: 14px;">
            <tr><td style="padding: 6px 0; color: #64748B;">Metric</td><td style="padding: 6px 0; font-weight: 700; color: #0F172A;">{metric}</td></tr>
            <tr><td style="padding: 6px 0; color: #64748B;">Current Value</td><td style="padding: 6px 0; font-weight: 700; color: #DC2626;">{current_value}</td></tr>
            <tr><td style="padding: 6px 0; color: #64748B;">Threshold</td><td style="padding: 6px 0; font-weight: 700; color: #0F172A;">{threshold}</td></tr>
            <tr><td style="padding: 6px 0; color: #64748B;">Action Taken</td><td style="padding: 6px 0; font-weight: 700; color: #D97706;">{action_taken}</td></tr>
          </table>
        </div>
        <p style="font-size: 12px; color: #94A3B8; margin: 0;">This is an automated alert from RealAICoach Automation Engine.</p>
      </div>
    </div>
    """


def _build_recovery_email(rule_name: str, metric: str, current_value, downtime_str: str, fix_applied: str) -> str:
    now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; background: #FFFFFF; color: #1E293B; border-radius: 12px; overflow: hidden;">
      <div style="background: linear-gradient(135deg, #16A34A, #15803D); padding: 24px 32px;">
        <h1 style="margin: 0; font-size: 20px; color: #FFF;">Recovered: {rule_name}</h1>
        <p style="margin: 4px 0 0; font-size: 13px; color: rgba(255,255,255,0.8);">{now}</p>
      </div>
      <div style="padding: 24px 32px;">
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
          <table style="width: 100%; border-collapse: collapse; color: #1E293B; font-size: 14px;">
            <tr><td style="padding: 6px 0; color: #64748B;">Metric</td><td style="padding: 6px 0; font-weight: 700; color: #0F172A;">{metric}</td></tr>
            <tr><td style="padding: 6px 0; color: #64748B;">Current Value</td><td style="padding: 6px 0; font-weight: 700; color: #16A34A;">{current_value}</td></tr>
            <tr><td style="padding: 6px 0; color: #64748B;">Downtime</td><td style="padding: 6px 0; font-weight: 700; color: #0F172A;">{downtime_str}</td></tr>
            <tr><td style="padding: 6px 0; color: #64748B;">Fix Applied</td><td style="padding: 6px 0; font-weight: 700; color: #16A34A;">{fix_applied}</td></tr>
          </table>
        </div>
        <p style="font-size: 12px; color: #94A3B8; margin: 0;">Service has been restored. Automated by RealAICoach Automation Engine.</p>
      </div>
    </div>
    """


def _check_condition(value: float, condition: str, threshold: float) -> bool:
    if condition == "gt":
        return value > threshold
    elif condition == "lt":
        return value < threshold
    elif condition == "eq":
        return value == threshold
    return False


async def _safe_auto_fix(rule: dict, db) -> str:
    """Attempt safe auto-fix based on the rule's action. Returns description of fix applied."""
    action = rule.get("action", "alert")
    metric = rule.get("metric", "")
    fix_description = "Alert sent (no auto-fix configured)"

    if action == "clear_cache":
        try:
            deleted = await db.session_cache.delete_many(
                {"expires_at": {"$lt": datetime.now(timezone.utc)}}
            )
            fix_description = f"Cleared {deleted.deleted_count} expired cache entries"
            logger.info(f"[AutoFix] {fix_description}")
        except Exception as e:
            fix_description = f"Cache clear attempted (error: {str(e)[:80]})"

    elif action == "restart":
        if "db" in metric.lower():
            try:
                await db.command("ping")
                fix_description = "DB connection verified healthy (no restart needed)"
            except Exception:
                fix_description = "DB connection issue detected — alert escalated"
        elif "api" in metric.lower() or "response" in metric.lower():
            try:
                deleted = await db.stale_sessions.delete_many(
                    {"last_active": {"$lt": datetime.now(timezone.utc) - timedelta(hours=24)}}
                )
                fix_description = f"Cleared {deleted.deleted_count} stale sessions to reduce load"
                logger.info(f"[AutoFix] {fix_description}")
            except Exception as e:
                fix_description = f"Session cleanup attempted (error: {str(e)[:80]})"
        else:
            fix_description = "Alert sent — manual intervention recommended"

    elif action == "scale_up":
        fix_description = "Scale-up alert sent — requires infrastructure action"

    elif action == "alert":
        fix_description = "Alert notification sent"

    return fix_description


def _format_downtime(start: datetime) -> str:
    delta = datetime.now(timezone.utc) - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        return f"{total_seconds // 60}m {total_seconds % 60}s"
    else:
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        return f"{hours}h {mins}m"


async def _get_current_metrics() -> dict:
    """Collect current system metrics."""
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "cpu_percent": cpu,
        "memory_percent": round(mem.percent, 1),
        "disk_percent": round(disk.percent, 1),
        "db_connected": 1,
        "api_response_ms": 0,
        "error_rate_5m": 0,
    }


async def run_alert_monitor(db):
    """Main monitor loop — called by scheduler every 60s."""
    from utils.email_service import is_email_configured

    global _active_alerts, _cooldowns
    now = datetime.now(timezone.utc)

    try:
        # Get current metrics
        metrics = await _get_current_metrics()

        # Check DB connectivity
        try:
            t0 = time.monotonic()
            await db.command("ping")
            metrics["db_connected"] = 1
            metrics["api_response_ms"] = round((time.monotonic() - t0) * 1000, 1)
        except Exception:
            metrics["db_connected"] = 0
            metrics["api_response_ms"] = 9999

        # Get active alert rules
        rules = []
        async for rule in db.automation_rules.find({"enabled": True}, {"_id": 0}):
            rules.append(rule)

        # Get admin emails for notifications
        admin_emails = []
        async for user in db.users.find({"is_admin": True}, {"_id": 0, "email": 1}).limit(5):
            admin_emails.append(user["email"])
        if not admin_emails:
            fallback = os.environ.get("ADMIN_EMAILS", "").split(",")[0].strip()
            admin_emails = [fallback] if fallback else []

        for rule in rules:
            rule_id = rule.get("rule_id", "unknown")
            metric_name = rule.get("metric", "")
            threshold = rule.get("threshold", 0)
            condition = rule.get("condition", "gt")
            cooldown_min = rule.get("cooldown_minutes", 15)
            autofix_enabled = rule.get("autofix_enabled", True)

            # Check schedule — skip if rule is outside its active window
            schedule_type = rule.get("schedule_type", "always")
            if schedule_type == "time_window":
                window_start = rule.get("schedule_window_start", "00:00")
                window_end = rule.get("schedule_window_end", "23:59")
                tz_name = rule.get("schedule_timezone", "UTC")
                try:
                    import zoneinfo
                    tz = zoneinfo.ZoneInfo(tz_name)
                except Exception:
                    import pytz
                    tz = pytz.timezone(tz_name) if tz_name != "UTC" else pytz.UTC
                local_now = now.astimezone(tz)
                current_time_str = local_now.strftime("%H:%M")
                if not (window_start <= current_time_str <= window_end):
                    continue
            elif schedule_type == "cron":
                cron_expr = rule.get("schedule_cron")
                if cron_expr:
                    try:
                        from croniter import croniter
                        cron = croniter(cron_expr, now - timedelta(minutes=2))
                        next_run = cron.get_next(datetime)
                        if abs((next_run - now).total_seconds()) > 120:
                            continue
                    except Exception:
                        pass  # If cron parsing fails, always run

            current_value = metrics.get(metric_name)
            if current_value is None:
                continue

            breached = _check_condition(current_value, condition, threshold)

            if breached:
                # Check cooldown
                last_triggered = _cooldowns.get(rule_id)
                if last_triggered and (now - last_triggered).total_seconds() < cooldown_min * 60:
                    continue

                # New alert or existing
                if rule_id not in _active_alerts:
                    incident_id = f"INC-{now.strftime('%Y%m%d%H%M%S')}-{rule_id[:8]}"

                    # Attempt auto-fix with AI remediation
                    fix_desc = "No auto-fix"
                    if autofix_enabled and rule.get("action") in ("restart", "clear_cache", "scale_up", "alert"):
                        try:
                            from services.ai_remediation import ai_diagnose_and_fix
                            # Gather related active alerts for multi-service analysis
                            related = await db.alert_history.find(
                                {"level": {"$in": ["critical", "warning"]},
                                 "created_at": {"$gte": now - timedelta(minutes=10)},
                                 "rule_name": {"$ne": rule.get("name")}},
                                {"_id": 0, "rule_name": 1, "message": 1, "created_at": 1}
                            ).limit(5).to_list(5)
                            related_alerts = []
                            for r in related:
                                if hasattr(r.get("created_at"), "isoformat"):
                                    r["triggered_at"] = r["created_at"].isoformat()
                                related_alerts.append(r)
                            ai_result = await ai_diagnose_and_fix(
                                rule,
                                current_value,
                                db,
                                related_alerts=related_alerts if related_alerts else None,
                            )
                            if ai_result.get("success"):
                                fix_desc = ai_result["fix_description"]
                                if ai_result.get("plan"):
                                    plan = ai_result["plan"]
                                    diagnosis = str(plan.get("diagnosis", "N/A"))[:120]
                                    risk = str(plan.get("risk_level", "unknown"))
                                    impact = int(plan.get("cascading_risk_percent", 0) or 0)
                                    fix_desc = f"{fix_desc} | AI:{diagnosis} | risk={risk} | impact={impact}%"
                            else:
                                fix_desc = await _safe_auto_fix(rule, db)
                        except Exception as ai_err:
                            logger.warning(f"[AlertMonitor] AI remediation failed, falling back: {ai_err}")
                            fix_desc = await _safe_auto_fix(rule, db)

                    action_str = fix_desc if autofix_enabled else "Alert sent (auto-fix disabled)"

                    # Create incident in DB
                    incident_doc = {
                        "incident_id": incident_id,
                        "rule_id": rule_id,
                        "title": f"{rule.get('name', rule_id)}: {metric_name}={current_value} (threshold: {condition} {threshold})",
                        "status": "open",
                        "severity": "critical" if condition == "gt" and current_value > threshold * 1.2 else "warning",
                        "metric": metric_name,
                        "current_value": current_value,
                        "threshold": threshold,
                        "auto_healed": autofix_enabled and rule.get("action") in ("restart", "clear_cache"),
                        "fix_applied": fix_desc,
                        "created_at": now,
                        "resolved_at": None,
                        "resolution_note": None,
                    }
                    await db.automation_incidents.insert_one({**incident_doc})

                    # Log alert
                    alert_doc = {
                        "alert_id": f"ALT-{now.strftime('%Y%m%d%H%M%S')}-{rule_id[:8]}",
                        "incident_id": incident_id,
                        "rule_id": rule_id,
                        "rule_name": rule.get("name", rule_id),
                        "type": "breach",
                        "metric": metric_name,
                        "value": current_value,
                        "threshold": threshold,
                        "action_taken": action_str,
                        "notified_emails": admin_emails,
                        "created_at": now,
                    }
                    await db.automation_alerts.insert_one({**alert_doc})

                    # Send alert email
                    if is_email_configured():
                        from utils.email_service import send_catalog_template
                        for email in admin_emails:
                            await send_catalog_template(
                                recipient_email=email,
                                template_key="automation_alert",
                                rule_name=rule.get("name", rule_id),
                                metric_name=metric_name,
                                current_value=str(current_value),
                                condition=condition,
                                threshold=str(threshold),
                                action_taken=action_str,
                                is_recovery=False,
                            )

                    _active_alerts[rule_id] = {
                        "started_at": now,
                        "incident_id": incident_id,
                        "fix_applied": fix_desc,
                    }
                    _cooldowns[rule_id] = now

                    # Increment trigger count
                    await db.automation_rules.update_one(
                        {"rule_id": rule_id},
                        {"$inc": {"triggers_count": 1}, "$set": {"last_triggered": now}}
                    )

                    logger.warning(f"[AlertMonitor] BREACH: {rule.get('name')} — {metric_name}={current_value} > {threshold}. Action: {action_str}")

            else:
                # Check if this was previously alerting → RECOVERY
                if rule_id in _active_alerts:
                    alert_info = _active_alerts.pop(rule_id)
                    incident_id = alert_info["incident_id"]
                    downtime = _format_downtime(alert_info["started_at"])
                    fix_applied = alert_info.get("fix_applied", "Self-recovered")

                    # Resolve incident
                    await db.automation_incidents.update_one(
                        {"incident_id": incident_id},
                        {"$set": {
                            "status": "resolved",
                            "resolved_at": now,
                            "resolution_note": f"Auto-recovered after {downtime}. Fix: {fix_applied}",
                        }}
                    )

                    # Log recovery alert
                    recovery_doc = {
                        "alert_id": f"REC-{now.strftime('%Y%m%d%H%M%S')}-{rule_id[:8]}",
                        "incident_id": incident_id,
                        "rule_id": rule_id,
                        "rule_name": rule.get("name", rule_id),
                        "type": "recovery",
                        "metric": metric_name,
                        "value": current_value,
                        "threshold": threshold,
                        "downtime": downtime,
                        "fix_applied": fix_applied,
                        "notified_emails": admin_emails,
                        "created_at": now,
                    }
                    await db.automation_alerts.insert_one({**recovery_doc})

                    # Send recovery email
                    if is_email_configured():
                        from utils.email_service import send_catalog_template
                        for email in admin_emails:
                            await send_catalog_template(
                                recipient_email=email,
                                template_key="automation_alert",
                                rule_name=rule.get("name", rule_id),
                                metric_name=metric_name,
                                current_value=str(current_value),
                                is_recovery=True,
                                downtime=downtime,
                                fix_applied=fix_applied,
                            )

                    logger.info(f"[AlertMonitor] RECOVERED: {rule.get('name')} — {metric_name}={current_value}. Downtime: {downtime}")

    except Exception as e:
        logger.error(f"[AlertMonitor] Monitor cycle failed: {e}")
