"""Anomaly Alert Digest — Detects anomaly spikes, triggers auto-fix, sends email digests."""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_CONFIG = {
    "enabled": True,
    "daily_digest": True,
    "weekly_digest": True,
    "spike_threshold": 10,        # issues in 1h to trigger immediate alert
    "daily_threshold": 50,        # issues in 24h to flag in daily digest
    "weekly_threshold": 200,      # issues in 7d to flag in weekly digest
    "auto_fix_on_spike": True,    # auto-trigger fix engine on spike
    "recipients": [],             # admin emails; falls back to all admins
    "digest_hour": 8,             # hour of day for daily digest (UTC)
    "digest_day": 0,              # day of week for weekly digest (0=Mon)
}

ALERT_CONFIG_COLLECTION = "anomaly_alert_config"
ALERT_HISTORY_COLLECTION = "anomaly_alert_history"
ALERT_RUNTIME_STATE_COLLECTION = "anomaly_alert_runtime_state"
SPIKE_ALERT_STATE_DOC_ID = "spike_alert_state"


async def _get_config(db) -> dict:
    doc = await db[ALERT_CONFIG_COLLECTION].find_one({"_id": "global"})
    if doc:
        cfg = {**DEFAULT_CONFIG}
        for k in DEFAULT_CONFIG:
            if k in doc:
                cfg[k] = doc[k]
        return cfg
    return {**DEFAULT_CONFIG}


async def _get_admin_emails(db, cfg: dict) -> list:
    if cfg.get("recipients"):
        return cfg["recipients"]
    cursor = db["users"].find({"role": "admin"}, {"email": 1, "_id": 0})
    admins = await cursor.to_list(length=50)
    return [a["email"] for a in admins if a.get("email")]


async def _count_issues(db, since: datetime) -> dict:
    pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {
            "_id": "$domain",
            "issues": {"$sum": "$issues_found"},
            "fixes": {"$sum": "$fixes_applied"},
            "runs": {"$sum": 1},
        }},
        {"$sort": {"issues": -1}},
    ]
    results = await db["auto_fix_runs"].aggregate(pipeline).to_list(length=100)
    total_issues = sum(r["issues"] for r in results)
    total_fixes = sum(r["fixes"] for r in results)
    top_domains = [{"domain": r["_id"], "issues": r["issues"], "fixes": r["fixes"]} for r in results[:10] if r["issues"] > 0]
    return {"total_issues": total_issues, "total_fixes": total_fixes, "top_domains": top_domains}


def _build_digest_html(period: str, stats: dict, auto_fix_triggered: bool) -> str:
    fix_rate = round(stats["total_fixes"] / max(stats["total_issues"], 1) * 100, 1)
    auto_fix_badge = '<span style="background:#10B981;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">AUTO-FIX ACTIVE</span>' if auto_fix_triggered else ''

    domain_rows = ""
    for d in stats["top_domains"]:
        dr = round(d["fixes"] / max(d["issues"], 1) * 100, 1)
        color = "#10B981" if dr >= 90 else "#F59E0B" if dr >= 50 else "#EF4444"
        domain_rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#0F172A;font-size:13px;">{d['domain'].replace('_', ' ').title()}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#D97706;font-size:13px;text-align:center;">{d['issues']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#059669;font-size:13px;text-align:center;">{d['fixes']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:{color};font-size:13px;text-align:center;">{dr}%</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#FFFFFF;border-radius:12px;border:1px solid #E2E8F0;font-family:Arial,sans-serif;">
      <tr><td style="padding:24px 24px 16px;">
        <table width="100%"><tr>
          <td><span style="font-size:20px;font-weight:800;color:#0F172A;">Anomaly Detection</span></td>
          <td style="text-align:right;">{auto_fix_badge}</td>
        </tr></table>
        <p style="color:#64748B;font-size:13px;margin:4px 0 0;">{period} Digest — {datetime.now(timezone.utc).strftime('%B %d, %Y')}</p>
      </td></tr>

      <tr><td style="padding:0 24px 16px;">
        <table width="100%" cellspacing="8"><tr>
          <td style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:8px;padding:16px;text-align:center;width:33%;">
            <p style="color:#64748B;font-size:11px;margin:0;text-transform:uppercase;">Issues</p>
            <p style="color:#D97706;font-size:28px;font-weight:800;margin:4px 0 0;">{stats['total_issues']}</p>
          </td>
          <td style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:8px;padding:16px;text-align:center;width:33%;">
            <p style="color:#64748B;font-size:11px;margin:0;text-transform:uppercase;">Fixes</p>
            <p style="color:#059669;font-size:28px;font-weight:800;margin:4px 0 0;">{stats['total_fixes']}</p>
          </td>
          <td style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:8px;padding:16px;text-align:center;width:33%;">
            <p style="color:#64748B;font-size:11px;margin:0;text-transform:uppercase;">Fix Rate</p>
            <p style="color:{'#059669' if fix_rate >= 90 else '#D97706' if fix_rate >= 50 else '#DC2626'};font-size:28px;font-weight:800;margin:4px 0 0;">{fix_rate}%</p>
          </td>
        </tr></table>
      </td></tr>

      <tr><td style="padding:0 24px 16px;">
        <p style="color:#0F172A;font-size:14px;font-weight:700;margin:0 0 8px;">Top Affected Domains</p>
        <table width="100%" style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;border-collapse:collapse;">
          <tr>
            <th style="padding:10px 12px;color:#64748B;font-size:11px;text-align:left;text-transform:uppercase;border-bottom:1px solid #E2E8F0;">Domain</th>
            <th style="padding:10px 12px;color:#64748B;font-size:11px;text-align:center;text-transform:uppercase;border-bottom:1px solid #E2E8F0;">Issues</th>
            <th style="padding:10px 12px;color:#64748B;font-size:11px;text-align:center;text-transform:uppercase;border-bottom:1px solid #E2E8F0;">Fixes</th>
            <th style="padding:10px 12px;color:#64748B;font-size:11px;text-align:center;text-transform:uppercase;border-bottom:1px solid #E2E8F0;">Fix Rate</th>
          </tr>
          {domain_rows if domain_rows else '<tr><td colspan="4" style="padding:16px;color:#94A3B8;text-align:center;">No issues detected</td></tr>'}
        </table>
      </td></tr>

      <tr><td style="padding:16px 24px 24px;text-align:center;">
        <p style="color:#94A3B8;font-size:11px;margin:0;">RealAICoach Enterprise — Anomaly Detection Engine</p>
      </td></tr>
    </table>"""


async def check_spike_and_autofix(db):
    """Called every 15 minutes. Checks for issue spikes and triggers auto-fix if configured."""
    cfg = await _get_config(db)
    if not cfg.get("enabled"):
        return

    now = datetime.now(timezone.utc)
    since_1h = now - timedelta(hours=1)
    stats = await _count_issues(db, since_1h)
    spike_threshold = int(cfg.get("spike_threshold", 10) or 10)

    if stats["total_issues"] < spike_threshold:
        await db[ALERT_RUNTIME_STATE_COLLECTION].update_one(
            {"_id": SPIKE_ALERT_STATE_DOC_ID},
            {
                "$set": {
                    "_id": SPIKE_ALERT_STATE_DOC_ID,
                    "active": False,
                    "last_clear_at": now,
                    "last_observed_issues": int(stats.get("total_issues") or 0),
                    "threshold": spike_threshold,
                }
            },
            upsert=True,
        )
        return

    spike_state = await db[ALERT_RUNTIME_STATE_COLLECTION].find_one({"_id": SPIKE_ALERT_STATE_DOC_ID}, {"_id": 0}) or {}
    if bool(spike_state.get("active")):
        logger.info("Spike alert suppressed: active incident already notified (incident_id=%s)", spike_state.get("incident_id"))
        return

    incident_id = f"spike_{now.strftime('%Y%m%d%H%M%S')}"
    await db[ALERT_RUNTIME_STATE_COLLECTION].update_one(
        {"_id": SPIKE_ALERT_STATE_DOC_ID},
        {
            "$set": {
                "_id": SPIKE_ALERT_STATE_DOC_ID,
                "active": True,
                "incident_id": incident_id,
                "opened_at": now,
                "last_observed_issues": int(stats.get("total_issues") or 0),
                "threshold": spike_threshold,
            }
        },
        upsert=True,
    )

    if stats["total_issues"] >= spike_threshold:
        logger.warning(f"Anomaly spike detected: {stats['total_issues']} issues in last hour (threshold: {cfg['spike_threshold']})")

        auto_fix_triggered = False
        if cfg.get("auto_fix_on_spike"):
            try:
                from routes.admin_autofix_engine import scheduled_autofix_sweep
                await scheduled_autofix_sweep()
                auto_fix_triggered = True
                logger.info("Auto-fix engine triggered by anomaly spike")
            except Exception as e:
                logger.error(f"Auto-fix trigger failed: {e}")

        # Send immediate spike alert
        try:
            from utils.email_service import is_email_configured
            if is_email_configured():
                recipients = await _get_admin_emails(db, cfg)
                from utils.email_service import send_catalog_template
                dedupe_seed = f"anomaly-spike-alert:{incident_id}"
                for email in recipients:
                    await send_catalog_template(email, "anomaly_digest", period="SPIKE ALERT", total_issues=stats["total_issues"], total_fixes=stats["total_fixes"], top_domains=stats["top_domains"][:5], auto_fix_triggered=auto_fix_triggered, dedupe_key=dedupe_seed)

                await db[ALERT_HISTORY_COLLECTION].insert_one({
                    "type": "spike",
                    "timestamp": now,
                    "issues": stats["total_issues"],
                    "fixes": stats["total_fixes"],
                    "auto_fix_triggered": auto_fix_triggered,
                    "recipients": recipients,
                    "top_domains": stats["top_domains"][:5],
                    "incident_id": incident_id,
                })
                logger.info(f"Spike alert sent to {len(recipients)} admins")
        except Exception as e:
            logger.error(f"Spike alert email failed: {e}")
            await db[ALERT_RUNTIME_STATE_COLLECTION].update_one(
                {"_id": SPIKE_ALERT_STATE_DOC_ID},
                {
                    "$set": {
                        "active": False,
                        "last_error_at": datetime.now(timezone.utc),
                        "last_error": str(e),
                    }
                },
                upsert=True,
            )


async def send_daily_digest(db):
    """Scheduled daily: send digest if issues exceed daily threshold."""
    cfg = await _get_config(db)
    if not cfg.get("enabled") or not cfg.get("daily_digest"):
        return

    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    stats = await _count_issues(db, since_24h)

    # Always send if there are issues above threshold, or if there are any issues at all (for visibility)
    if stats["total_issues"] < cfg.get("daily_threshold", 50) and stats["total_issues"] == 0:
        logger.info(f"Daily digest: {stats['total_issues']} issues (below threshold {cfg['daily_threshold']}), skipping")
        return

    auto_fix_triggered = False
    if cfg.get("auto_fix_on_spike") and stats["total_issues"] >= cfg.get("daily_threshold", 50):
        try:
            from routes.admin_autofix_engine import scheduled_autofix_sweep
            await scheduled_autofix_sweep()
            auto_fix_triggered = True
        except Exception as e:
            logger.error(f"Daily auto-fix trigger failed: {e}")

    try:
        from utils.email_service import is_email_configured
        if is_email_configured():
            recipients = await _get_admin_emails(db, cfg)
            from utils.email_service import send_catalog_template
            for email in recipients:
                await send_catalog_template(email, "anomaly_digest", period="Daily", total_issues=stats["total_issues"], total_fixes=stats["total_fixes"], top_domains=stats["top_domains"][:5], auto_fix_triggered=auto_fix_triggered)

            await db[ALERT_HISTORY_COLLECTION].insert_one({
                "type": "daily",
                "timestamp": now,
                "issues": stats["total_issues"],
                "fixes": stats["total_fixes"],
                "auto_fix_triggered": auto_fix_triggered,
                "recipients": recipients,
                "top_domains": stats["top_domains"][:5],
            })
            logger.info(f"Daily digest sent to {len(recipients)} admins: {stats['total_issues']} issues")
    except Exception as e:
        logger.error(f"Daily digest email failed: {e}")


async def send_weekly_digest(db):
    """Scheduled weekly: send comprehensive 7-day digest."""
    cfg = await _get_config(db)
    if not cfg.get("enabled") or not cfg.get("weekly_digest"):
        return

    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    stats = await _count_issues(db, since_7d)

    try:
        from utils.email_service import is_email_configured
        if is_email_configured():
            recipients = await _get_admin_emails(db, cfg)
            from utils.email_service import send_catalog_template
            for email in recipients:
                await send_catalog_template(email, "anomaly_digest", period="Weekly", total_issues=stats["total_issues"], total_fixes=stats["total_fixes"], top_domains=stats["top_domains"][:5], auto_fix_triggered=False)

            await db[ALERT_HISTORY_COLLECTION].insert_one({
                "type": "weekly",
                "timestamp": now,
                "issues": stats["total_issues"],
                "fixes": stats["total_fixes"],
                "auto_fix_triggered": False,
                "recipients": recipients,
                "top_domains": stats["top_domains"][:5],
            })
            logger.info(f"Weekly digest sent to {len(recipients)} admins: {stats['total_issues']} issues in 7d")
    except Exception as e:
        logger.error(f"Weekly digest email failed: {e}")
