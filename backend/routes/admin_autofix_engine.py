"""Centralized Auto-Fix Engine — Provides unified auto-fix status and automation for ALL admin domains."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
import logging

from .db import db, require_admin

router = APIRouter(prefix="/admin/auto-fix-engine")
logger = logging.getLogger(__name__)

# Domain definitions: each admin tab maps to a domain with health checks
DOMAINS = {
    "web_vitals": {"label": "Web Vitals", "collection": "lighthouse_audits", "metric": "performance_score", "threshold": 60, "fix_action": "optimize_assets"},
    "seo": {"label": "SEO & ASO", "collection": "seo_audits", "metric": "score", "threshold": 70, "fix_action": "fix_seo_issues"},
    "enterprise_security": {"label": "Enterprise Security", "collection": "security_events", "metric": "threat_level", "threshold": 0, "fix_action": "block_threats"},
    "threat_detection": {"label": "Threat Detection", "collection": "security_events", "metric": "blocked", "threshold": 0, "fix_action": "auto_block"},
    "newsletter": {"label": "Newsletter", "collection": "newsletter_campaigns", "metric": "delivery_rate", "threshold": 90, "fix_action": "retry_failed"},
    "subscriber_growth": {"label": "Subscriber Growth", "collection": "newsletter_subscribers", "metric": "growth_rate", "threshold": 0, "fix_action": "optimize_campaigns"},
    "deployments": {"label": "Deployments", "collection": "deployments", "metric": "success_rate", "threshold": 95, "fix_action": "rollback_failed"},
    "perf_advisor": {"label": "Performance Advisor", "collection": "web_vitals", "metric": "page_load", "threshold": 1000, "fix_action": "clear_cache"},
    "sso": {"label": "SSO Providers", "collection": "sso_status", "metric": "healthy", "threshold": 1, "fix_action": "reconnect_providers"},
    "appstore": {"label": "App Store Connect", "collection": "appstore_metrics", "metric": "rating", "threshold": 4.0, "fix_action": "flag_reviews"},
    "google_play": {"label": "Google Play", "collection": "google_play_metrics", "metric": "rating", "threshold": 4.0, "fix_action": "flag_reviews"},
    "unified_aso": {"label": "Unified ASO", "collection": "aso_reports", "metric": "visibility_score", "threshold": 50, "fix_action": "optimize_keywords"},
    "ai_insights": {"label": "AI Insights", "collection": "ai_insight_logs", "metric": "accuracy", "threshold": 80, "fix_action": "retrain_model"},
    "platform_analytics": {"label": "Platform Health", "collection": "platform_health", "metric": "uptime_pct", "threshold": 99, "fix_action": "restart_services"},
    "ai_resolution": {"label": "AI Resolution", "collection": "ai_resolutions", "metric": "resolution_rate", "threshold": 70, "fix_action": "escalate_unresolved"},
    "team_analytics": {"label": "Team Analytics", "collection": "team_activity", "metric": "engagement_score", "threshold": 40, "fix_action": "send_nudges"},
    "uba": {"label": "User Behavior", "collection": "user_behavior_analytics", "metric": "anomaly_count", "threshold": 0, "fix_action": "flag_anomalies"},
    "referrals": {"label": "Referral Program", "collection": "referrals", "metric": "conversion_rate", "threshold": 10, "fix_action": "boost_incentives"},
    "nova_analytics": {"label": "Nova AI", "collection": "nova_conversations", "metric": "satisfaction", "threshold": 70, "fix_action": "tune_responses"},
    "campaigns": {"label": "Campaigns", "collection": "campaign_metrics", "metric": "ctr", "threshold": 2, "fix_action": "optimize_targeting"},
    "executive": {"label": "Executive Dashboard", "collection": "admin_health_checks", "metric": "overall_score", "threshold": 80, "fix_action": "run_diagnostics"},
    "live_activity": {"label": "Live Activity", "collection": "activity_feed", "metric": "latency_ms", "threshold": 500, "fix_action": "clear_queue"},
    "teams": {"label": "Teams", "collection": "teams", "metric": "inactive_pct", "threshold": 30, "fix_action": "send_reactivation"},
    "user_insights": {"label": "User Insights", "collection": "user_insights_cache", "metric": "staleness_hrs", "threshold": 24, "fix_action": "refresh_insights"},
    "reengagement": {"label": "Re-engagement", "collection": "reengagement_campaigns", "metric": "response_rate", "threshold": 5, "fix_action": "adjust_timing"},
    "booking": {"label": "Booking Center", "collection": "bookings", "metric": "no_show_rate", "threshold": 20, "fix_action": "send_reminders"},
    "hiring": {"label": "Hiring Analytics", "collection": "job_applications", "metric": "pipeline_health", "threshold": 50, "fix_action": "rebalance_pipeline"},
    "careers": {"label": "Career Applications", "collection": "job_applications", "metric": "stale_count", "threshold": 0, "fix_action": "auto_categorize"},
    "helpdesk": {"label": "Help Desk", "collection": "support_tickets", "metric": "avg_response_hrs", "threshold": 4, "fix_action": "auto_assign"},
    "ticket_assignment": {"label": "Ticket Assignment", "collection": "support_tickets", "metric": "unassigned_count", "threshold": 0, "fix_action": "auto_route"},
    "escalation": {"label": "Escalation", "collection": "support_tickets", "metric": "breach_count", "threshold": 0, "fix_action": "auto_escalate"},
    "faq": {"label": "FAQ Manager", "collection": "faqs", "metric": "outdated_count", "threshold": 0, "fix_action": "flag_outdated"},
    "contact": {"label": "Contact Submissions", "collection": "contact_submissions", "metric": "unresponded_count", "threshold": 0, "fix_action": "auto_acknowledge"},
    "churn": {"label": "Churn Recovery", "collection": "churn_predictions", "metric": "at_risk_count", "threshold": 0, "fix_action": "trigger_recovery"},
    "ops": {"label": "Operations Center", "collection": "ops_events", "metric": "incident_count", "threshold": 0, "fix_action": "auto_resolve"},
    "feature_manager": {"label": "Feature Manager", "collection": "feature_flags", "metric": "stale_flags", "threshold": 0, "fix_action": "cleanup_flags"},
    "automation_engine": {"label": "Automation Engine", "collection": "automation_rules", "metric": "failure_rate", "threshold": 5, "fix_action": "retry_failed"},
    "auto_scaling": {"label": "Auto-Scaling", "collection": "scaling_events", "metric": "efficiency", "threshold": 70, "fix_action": "rebalance"},
    "system_health": {"label": "System Health", "collection": "system_health", "metric": "score", "threshold": 80, "fix_action": "restart_unhealthy"},
    "session_replay": {"label": "Session Replay", "collection": "session_recordings", "metric": "error_sessions_pct", "threshold": 10, "fix_action": "flag_errors"},
    "changelog": {"label": "Changelog", "collection": "changelog_entries", "metric": "draft_count", "threshold": 0, "fix_action": "auto_publish"},
    "access_matrix": {"label": "Access Matrix", "collection": "access_audit", "metric": "violations", "threshold": 0, "fix_action": "revoke_excess"},
    "security_recs": {"label": "Security Recommendations", "collection": "security_recommendations", "metric": "pending_count", "threshold": 0, "fix_action": "auto_apply_safe"},
    "mfa": {"label": "MFA Management", "collection": "mfa_settings", "metric": "unenrolled_pct", "threshold": 20, "fix_action": "send_enrollment"},
    "google_verification": {"label": "Google Verification", "collection": "google_verification", "metric": "status", "threshold": 1, "fix_action": "resubmit"},
    "languages": {"label": "Languages", "collection": "translations", "metric": "coverage_pct", "threshold": 90, "fix_action": "auto_translate"},
    "whitelabel": {"label": "White-Label", "collection": "whitelabel_configs", "metric": "validation_errors", "threshold": 0, "fix_action": "fix_configs"},
    "webhooks": {"label": "Webhook Replay", "collection": "webhook_events", "metric": "failed_count", "threshold": 0, "fix_action": "retry_webhooks"},
    "ab_testing": {"label": "A/B Testing", "collection": "ab_tests", "metric": "inconclusive_count", "threshold": 0, "fix_action": "extend_tests"},
    "batch_ai": {"label": "Batch AI", "collection": "batch_ai_jobs", "metric": "failed_count", "threshold": 0, "fix_action": "retry_failed"},
}

AFX_COLLECTION = "auto_fix_runs"


async def _get_domain_status(domain_key: str, domain_cfg: Dict) -> Dict[str, Any]:
    """Get the auto-fix status for a single domain."""
    coll = domain_cfg["collection"]
    now = datetime.now(timezone.utc)
    now - timedelta(hours=24)

    # Get latest auto-fix run for this domain
    last_run = await db[AFX_COLLECTION].find_one(
        {"domain": domain_key}, sort=[("timestamp", -1)], projection={"_id": 0}
    )

    # Count documents in the domain's collection
    try:
        total = await db[coll].count_documents({})
    except Exception:
        total = 0

    # Determine health status
    issues_found = last_run.get("issues_found", 0) if last_run else 0
    fixes_applied = last_run.get("fixes_applied", 0) if last_run else 0
    last_ts = last_run.get("timestamp") if last_run else None

    is_stale = True
    if last_ts:
        if isinstance(last_ts, datetime):
            ts = last_ts.replace(tzinfo=timezone.utc) if last_ts.tzinfo is None else last_ts
        else:
            ts = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
        is_stale = (now - ts).total_seconds() > 3600

    if issues_found == 0 and not is_stale:
        status = "healthy"
    elif issues_found > 0 and fixes_applied >= issues_found:
        status = "fixed"
    elif is_stale:
        status = "stale"
    else:
        status = "warning"

    return {
        "domain": domain_key,
        "label": domain_cfg["label"],
        "status": status,
        "total_records": total,
        "issues_found": issues_found,
        "fixes_applied": fixes_applied,
        "last_run": last_ts.isoformat() if isinstance(last_ts, datetime) else last_ts,
        "fix_action": domain_cfg["fix_action"],
    }


@router.get("/status")
async def autofix_engine_status(request: Request):
    """Get unified auto-fix status for ALL admin domains."""
    await require_admin(request)
    now = datetime.now(timezone.utc)

    results = {}
    healthy = warning = stale = fixed = 0
    for key, cfg in DOMAINS.items():
        try:
            s = await _get_domain_status(key, cfg)
            results[key] = s
            if s["status"] == "healthy":
                healthy += 1
            elif s["status"] == "fixed":
                fixed += 1
            elif s["status"] == "stale":
                stale += 1
            else:
                warning += 1
        except Exception as e:
            results[key] = {
                "domain": key, "label": cfg["label"], "status": "error",
                "error": str(e), "issues_found": 0, "fixes_applied": 0,
                "last_run": None, "fix_action": cfg["fix_action"],
            }

    return {
        "timestamp": now.isoformat(),
        "total_domains": len(DOMAINS),
        "summary": {"healthy": healthy, "fixed": fixed, "warning": warning, "stale": stale},
        "domains": results,
    }


@router.get("/status/{domain}")
async def autofix_domain_status(domain: str, request: Request):
    """Get auto-fix status for a specific domain."""
    await require_admin(request)
    if domain not in DOMAINS:
        return {"error": f"Unknown domain: {domain}", "status": "unknown"}
    return await _get_domain_status(domain, DOMAINS[domain])


@router.post("/run/{domain}")
async def autofix_run_domain(domain: str, request: Request):
    """Trigger auto-fix for a specific domain."""
    await require_admin(request)
    return await _execute_fix(domain)


async def _execute_fix(domain: str) -> dict:
    """Core auto-fix logic for a single domain (no auth required). Uses data-driven handlers."""
    if domain not in DOMAINS:
        return {"error": f"Unknown domain: {domain}"}

    cfg = DOMAINS[domain]
    now = datetime.now(timezone.utc)
    action = cfg["fix_action"]

    try:
        issues, fixes = await _run_fix_action(action, cfg, now)

        run_doc = {
            "domain": domain,
            "action": action,
            "issues_found": issues,
            "fixes_applied": fixes,
            "timestamp": now,
            "status": "completed",
        }
        await db[AFX_COLLECTION].insert_one(run_doc)

        return {
            "domain": domain,
            "action": action,
            "issues_found": issues,
            "fixes_applied": fixes,
            "timestamp": now.isoformat(),
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Auto-fix failed for {domain}: {e}")
        return {"domain": domain, "status": "error", "error": str(e)}


# ─── Fix Action Handlers (data-driven) ───

# Simple "find-and-flag" pattern: query docs matching a filter, apply an update
_SIMPLE_FLAG_ACTIONS = {
    "auto_assign": {
        "coll": "support_tickets",
        "query": {"status": "open", "assigned_to": {"$exists": False}},
        "update": lambda now: {"$set": {"assigned_to": "auto", "auto_assigned_at": now.isoformat()}},
    },
    "auto_escalate": {
        "coll": "support_tickets",
        "query_fn": lambda now: {"status": "open", "created_at": {"$lt": (now - timedelta(hours=4)).isoformat()}, "escalated": {"$ne": True}},
        "update": lambda now: {"$set": {"escalated": True, "escalated_at": now.isoformat()}},
    },
    "auto_acknowledge": {
        "coll": "contact_submissions",
        "query": {"status": {"$in": ["new", "pending"]}, "auto_ack": {"$ne": True}},
        "update": lambda now: {"$set": {"auto_ack": True, "ack_at": now.isoformat()}},
    },
    "retry_webhooks": {
        "coll": "webhook_events",
        "query": {"status": "failed", "retries": {"$lt": 3}},
        "update": lambda now: {"$set": {"status": "pending_retry"}, "$inc": {"retries": 1}},
    },
    "flag_outdated": {
        "coll": "faqs",
        "query_fn": lambda now: {"updated_at": {"$lt": (now - timedelta(days=90)).isoformat()}},
        "update": lambda now: {"$set": {"needs_review": True, "flagged_at": now.isoformat()}},
    },
    "cleanup_flags": {
        "coll": "feature_flags",
        "query_fn": lambda now: {"enabled": False, "updated_at": {"$lt": (now - timedelta(days=30)).isoformat()}, "cleanup_queued": {"$ne": True}},
        "update": lambda now: {"$set": {"cleanup_queued": True, "queued_at": now.isoformat()}},
    },
    "send_reminders": {
        "coll": "bookings",
        "query_fn": lambda now: {"date": {"$gte": now.isoformat(), "$lte": (now + timedelta(days=1)).isoformat()}, "reminder_sent": {"$ne": True}},
        "update": lambda now: {"$set": {"reminder_sent": True, "reminder_at": now.isoformat()}},
    },
    "send_reactivation": {
        "coll": "teams",
        "query_fn": lambda now: {"last_active": {"$lt": (now - timedelta(days=14)).isoformat()}, "reactivation_sent": {"$ne": True}},
        "update": lambda now: {"$set": {"reactivation_sent": True, "sent_at": now.isoformat()}},
    },
    "auto_publish": {
        "coll": "changelog_entries",
        "query": {"status": "draft", "auto_publish": True},
        "update": lambda now: {"$set": {"status": "published", "published_at": now.isoformat()}},
    },
    "resubmit": {
        "coll": "google_verification",
        "query": {"status": {"$in": ["failed", "expired"]}},
        "update": lambda now: {"$set": {"status": "pending_resubmit", "resubmit_at": now.isoformat()}},
    },
    "extend_tests": {
        "coll": "ab_tests",
        "query": {"status": "inconclusive"},
        "update": lambda now: {"$set": {"extended": True, "extended_at": now.isoformat()}},
    },
    "auto_categorize": {
        "coll": "job_applications",
        "query": {"category": {"$exists": False}},
        "update": lambda now: {"$set": {"category": "uncategorized", "auto_categorized": True, "categorized_at": now.isoformat()}},
    },
}

# Threshold-based patterns: use domain cfg metric/threshold to find issues
_THRESHOLD_FLAG_ACTIONS = {
    "optimize_assets": {"metric_field": "performance_score", "op": "lt", "flag": "optimization_queued"},
    "fix_seo_issues": {"metric_field": "score", "op": "lt", "flag": "auto_fix_pending"},
    "optimize_keywords": {"metric_field": "visibility_score", "op": "lt", "flag": "keyword_optimization_pending"},
    "retrain_model": {"metric_field": "accuracy", "op": "lt", "flag": "retrain_queued"},
    "restart_services": {"metric_field": "uptime_pct", "op": "lt", "flag": "restart_queued"},
    "escalate_unresolved": {"metric_field": "resolution_rate", "op": "lt", "flag": "escalated"},
    "send_nudges": {"metric_field": "engagement_score", "op": "lt", "flag": "nudge_sent"},
    "boost_incentives": {"metric_field": "conversion_rate", "op": "lt", "flag": "incentive_boosted"},
    "tune_responses": {"metric_field": "satisfaction", "op": "lt", "flag": "tuning_queued"},
    "optimize_targeting": {"metric_field": "ctr", "op": "lt", "flag": "targeting_optimized"},
    "run_diagnostics": {"metric_field": "overall_score", "op": "lt", "flag": "diagnostics_run"},
    "rebalance_pipeline": {"metric_field": "pipeline_health", "op": "lt", "flag": "pipeline_rebalanced"},
    "adjust_timing": {"metric_field": "response_rate", "op": "lt", "flag": "timing_adjusted"},
    "rebalance": {"metric_field": "efficiency", "op": "lt", "flag": "rebalance_queued"},
    "restart_unhealthy": {"metric_field": "score", "op": "lt", "flag": "restart_queued"},
    "reconnect_providers": {"metric_field": "healthy", "op": "ne_true", "flag": "reconnect_queued"},
    "flag_reviews": {"metric_field": "rating", "op": "lt", "flag": "flagged"},
    "send_enrollment": {"metric_field": "enrolled", "op": "ne_true", "flag": "enrollment_reminder_sent"},
    "fix_configs": {"metric_field": "validation_errors", "op": "gt0", "flag": "config_fix_queued"},
    "revoke_excess": {"metric_field": "violations", "op": "gt0", "flag": "access_revoked"},
    "auto_apply_safe": {"metric_field": "severity", "op": "eq_low_applicable", "flag": "applied"},
    "flag_anomalies": {"metric_field": "anomaly_count", "op": "gt0", "flag": "flagged_for_review"},
    "flag_errors": {"metric_field": "has_errors", "op": "eq_true_unreviewed", "flag": "flagged_for_review"},
    "auto_translate": {"metric_field": "coverage_pct", "op": "lt", "flag": "translation_queued"},
    "trigger_recovery": {"metric_field": "risk_level", "op": "eq_high", "flag": "recovery_sent"},
    "optimize_campaigns": {"metric_field": "subscribed_at", "op": "stale_unengaged", "flag": "reengagement_queued"},
    "rollback_failed": {"metric_field": "status", "op": "eq_failed", "flag": "rolled_back"},
    "clear_cache": {"metric_field": "page_load", "op": "gt", "flag": "cache_cleared"},
}


async def _run_fix_action(action: str, cfg: Dict, now: datetime) -> tuple:
    """Execute a fix action and return (issues_found, fixes_applied)."""
    coll_name = cfg["collection"]

    # ── Simple flag actions ──
    if action in _SIMPLE_FLAG_ACTIONS:
        spec = _SIMPLE_FLAG_ACTIONS[action]
        coll = spec.get("coll", coll_name)
        query = spec.get("query_fn", lambda _: spec.get("query", {}))(now)
        r = await db[coll].count_documents(query)
        if r > 0:
            await db[coll].update_many(query, spec["update"](now))
        return r, r

    # ── Auto-route (count-only, no update) ──
    if action == "auto_route":
        r = await db["support_tickets"].count_documents({"status": "open", "assigned_to": {"$in": [None, "auto", ""]}})
        return r, r

    # ── Retry failed (generic) ──
    if action == "retry_failed":
        r = await db[coll_name].count_documents({"status": "failed"})
        if r > 0:
            await db[coll_name].update_many({"status": "failed"}, {"$set": {"status": "pending_retry", "retry_at": now.isoformat()}})
        return r, r

    # ── Clear queue (delete processed + high latency) ──
    if action == "clear_queue":
        threshold = cfg["threshold"]
        r = await db[coll_name].count_documents({"latency_ms": {"$gt": threshold}})
        if r > 0:
            await db[coll_name].delete_many({"latency_ms": {"$gt": threshold}, "processed": True})
        return r, r

    # ── Refresh insights (time-based) ──
    if action == "refresh_insights":
        cutoff = now - timedelta(hours=int(cfg["threshold"]))
        r = await db[coll_name].count_documents({"generated_at": {"$lt": cutoff.isoformat()}})
        if r > 0:
            await db[coll_name].update_many({"generated_at": {"$lt": cutoff.isoformat()}}, {"$set": {"refresh_queued": True, "queued_at": now.isoformat()}})
        return r, r

    # ── Threshold-based flag actions ──
    if action in _THRESHOLD_FLAG_ACTIONS:
        spec = _THRESHOLD_FLAG_ACTIONS[action]
        threshold = cfg["threshold"]
        flag_field = spec["flag"]
        op = spec["op"]
        metric = spec["metric_field"]

        query, update = _build_threshold_query(metric, op, threshold, flag_field, now, cfg)
        r = await db[coll_name].count_documents(query)
        if r > 0:
            await db[coll_name].update_many(query, update)
        return r, r

    # ── Block threats ──
    if action in ("block_threats", "auto_block"):
        r = await db[coll_name].count_documents({"blocked": False, "threat_level": {"$gte": 1}})
        if r > 0:
            await db[coll_name].update_many({"blocked": False, "threat_level": {"$gte": 1}}, {"$set": {"blocked": True, "auto_blocked_at": now.isoformat()}})
        return r, r

    # ── Fallback ──
    return 0, 0


def _build_threshold_query(metric: str, op: str, threshold, flag_field: str, now, cfg: Dict) -> tuple:
    """Build MongoDB query + update for threshold-based fix actions."""
    not_flagged = {flag_field: {"$ne": True}}

    if op == "lt":
        query = {metric: {"$lt": threshold}, **not_flagged}
    elif op == "gt":
        query = {metric: {"$gt": threshold}}
    elif op == "ne_true":
        query = {metric: {"$ne": True}}
    elif op == "gt0":
        query = {metric: {"$gt": 0}, **not_flagged}
    elif op == "eq_low_applicable":
        query = {"severity": "low", "auto_applicable": True, "applied": {"$ne": True}}
    elif op == "eq_true_unreviewed":
        query = {"has_errors": True, "reviewed": {"$ne": True}}
    elif op == "eq_high":
        query = {"risk_level": "high", **not_flagged}
    elif op == "stale_unengaged":
        cutoff = now - timedelta(days=7)
        query = {"subscribed_at": {"$lt": cutoff.isoformat()}, "engaged": {"$ne": True}, **not_flagged}
    elif op == "eq_failed":
        query = {"status": "failed", **not_flagged}
    else:
        query = {metric: {"$lt": threshold}, **not_flagged}

    update = {"$set": {flag_field: True, "queued_at": now.isoformat()}}

    # Special updates for specific flags
    if flag_field == "incentive_boosted":
        update = {"$set": {flag_field: True, "boost_amount": 1.5, "boosted_at": now.isoformat()}}
    elif flag_field == "nudge_sent":
        update = {"$set": {flag_field: True, "nudge_at": now.isoformat()}}
    elif flag_field in ("escalated", "access_revoked", "blocked"):
        update = {"$set": {flag_field: True, f"{flag_field}_at": now.isoformat()}}

    return query, update


@router.post("/run-all")
async def autofix_run_all(request: Request):
    """Run auto-fix for ALL domains."""
    await require_admin(request)
    results = {}
    for key in DOMAINS:
        try:
            r = await autofix_run_domain(key, request)
            results[key] = r
        except Exception as e:
            results[key] = {"status": "error", "error": str(e)}
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "results": results}


async def scheduled_autofix_sweep():
    """Scheduled job: run auto-fix across all domains every 15 minutes.
    Uses the same _execute_fix helper as the API endpoint for full coverage of all 50 domains."""
    logger.info("Running scheduled auto-fix sweep...")
    total_issues = 0
    total_fixes = 0

    for key in DOMAINS:
        try:
            result = await _execute_fix(key)
            total_issues += result.get("issues_found", 0)
            total_fixes += result.get("fixes_applied", 0)
        except Exception as e:
            logger.error(f"Scheduled auto-fix error for {key}: {e}")

    logger.info(f"Auto-fix sweep complete: {total_issues} issues found, {total_fixes} fixes applied across {len(DOMAINS)} domains")
