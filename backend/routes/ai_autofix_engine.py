"""AI Auto-Fix Engine v2 — Two-phase approach with GPT-4o confidence scoring.

Phase 1: Each fixer PROPOSES fixes (gathers context, doesn't apply)
Phase 2: GPT-4o evaluates all proposals with confidence scores
Phase 3: High-confidence (>=80%) fixes auto-applied; low-confidence flagged for review
"""

import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ai-autofix", tags=["ai-autofix"])

CONFIDENCE_THRESHOLD = 80


async def _get_db():
    from routes.db import db
    return db


async def _require_admin(request: Request):
    from routes.db import require_admin
    await require_admin(request)


def _proposal(engine: str, action_id: str, action: str, details: str, apply_fn: str, context: dict = None):
    """Create a fix proposal (not yet applied)."""
    return {
        "engine": engine,
        "action_id": action_id,
        "action": action,
        "details": details,
        "apply_fn": apply_fn,
        "context": context or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


LEGACY_APPLY_FN_BY_ACTION = {
    "auto_escalate": "sla_escalate",
    "auto_assign": "sla_assign",
    "auto_close": "sla_close_stale",
    "configure_modal": "conv_modal_config",
    "seed_funnel": "conv_seed_funnel",
    "configure_nudge": "conv_nudge",
    "seed_steps": "ob_seed_steps",
    "create_progress": "ob_create_progress",
    "enable_config": "ob_enable",
    "configure_tracking": "nl_config",
    "seed_analytics": "nl_seed_analytics",
    "create_campaign": "nl_welcome_campaign",
    "auto_subscribe": "nl_auto_subscribe",
    "clean_sessions": "sec_clean_sessions",
    "clean_blocklist": "sec_clean_ips",
    "recommend_2fa": "sec_2fa_flag",
    "configure_policy": "sec_policy",
    "flag_at_risk": "churn_flag",
    "configure_retention": "churn_retention",
    "clean_metrics": "perf_clean",
    "clean_system_history": "perf_clean_sys",
    "configure_monitoring": "perf_config",
    "clean_flags": "fraud_clean",
    "configure_detection": "fraud_config",
}


def _resolve_apply_fn(item: dict) -> str | None:
    apply_fn = item.get("apply_fn")
    if apply_fn:
        return apply_fn

    action = item.get("action")
    if action in LEGACY_APPLY_FN_BY_ACTION:
        return LEGACY_APPLY_FN_BY_ACTION[action]

    action_id = item.get("action_id", "")
    if action_id in LEGACY_APPLY_FN_BY_ACTION.values():
        return action_id

    if action_id.startswith("sla_escalate_"):
        return "sla_escalate"
    if action_id.startswith("sla_assign_"):
        return "sla_assign"

    return None


# ── Phase 1: Proposers (gather context, don't apply) ────────────────────────

async def propose_sla(db) -> list:
    """Propose SLA fixes without applying."""
    proposals = []
    now = datetime.now(timezone.utc)
    config = await db.app_config.find_one({"key": "sla_config"}, {"_id": 0}) or {}
    escalation_hours = config.get("escalation_hours", 24)
    cutoff = (now - timedelta(hours=escalation_hours * 0.8)).isoformat()

    at_risk = await db.support_tickets.find(
        {"status": {"$in": ["open", "pending"]}, "created_at": {"$lte": cutoff}, "sla_escalated": {"$ne": True}},
        {"_id": 0, "ticket_id": 1, "subject": 1, "status": 1, "priority": 1, "category": 1}
    ).to_list(50)

    for t in at_risk:
        proposals.append(_proposal("SLA", f"sla_escalate_{t['ticket_id']}", "auto_escalate",
            f"Escalate ticket {t['ticket_id']} ({t.get('subject', 'N/A')[:40]}) to urgent — approaching SLA breach",
            "sla_escalate", {"ticket_id": t["ticket_id"]}))

    unassigned = await db.support_tickets.find(
        {"status": "open", "assigned_to": {"$in": [None, ""]}},
        {"_id": 0, "ticket_id": 1, "category": 1}
    ).to_list(30)

    agents = await db.users.find({"role": {"$in": ["admin", "support_agent"]}}, {"_id": 0, "user_id": 1, "name": 1}).to_list(10)
    for i, t in enumerate(unassigned):
        agent = agents[i % len(agents)] if agents else {"user_id": "unknown", "name": "system"}
        proposals.append(_proposal("SLA", f"sla_assign_{t['ticket_id']}", "auto_assign",
            f"Assign unassigned ticket {t['ticket_id']} to {agent.get('name', 'agent')}",
            "sla_assign", {"ticket_id": t["ticket_id"], "agent_id": agent["user_id"], "agent_name": agent.get("name", "")}))

    close_cutoff = (now - timedelta(hours=48)).isoformat()
    stale_count = await db.support_tickets.count_documents(
        {"status": "resolved", "resolved_at": {"$lte": close_cutoff}, "auto_closed": {"$ne": True}})
    if stale_count > 0:
        proposals.append(_proposal("SLA", "sla_close_stale", "auto_close",
            f"Close {stale_count} stale resolved tickets (resolved >48h ago)",
            "sla_close_stale", {"count": stale_count}))

    return proposals


async def propose_conversion(db) -> list:
    proposals = []
    datetime.now(timezone.utc)

    modal_config = await db.app_config.find_one({"key": "modal_analytics"}, {"_id": 0})
    if not modal_config:
        proposals.append(_proposal("Conversion", "conv_modal_config", "configure_modal",
            "Configure signup modal: 5s delay, shown on home/pricing/features",
            "conv_modal_config", {}))

    funnel_count = await db.conversion_events.count_documents({})
    if funnel_count == 0:
        proposals.append(_proposal("Conversion", "conv_seed_funnel", "seed_funnel",
            "Create 7-stage conversion funnel tracking (page_visit through premium_upgrade)",
            "conv_seed_funnel", {}))

    nudge_config = await db.app_config.find_one({"key": "trial_nudge"}, {"_id": 0})
    if not nudge_config:
        proposals.append(_proposal("Conversion", "conv_nudge", "configure_nudge",
            "Configure trial-to-premium nudge (triggers on day 5 of trial)",
            "conv_nudge", {}))

    return proposals


async def propose_onboarding(db) -> list:
    proposals = []
    datetime.now(timezone.utc)

    steps_count = await db.onboarding_steps.count_documents({})
    if steps_count == 0:
        proposals.append(_proposal("Onboarding", "ob_seed_steps", "seed_steps",
            "Create 5 default onboarding steps (Welcome, Profile, First Session, Goals, Explore)",
            "ob_seed_steps", {}))

    users_without = await db.users.find({"role": {"$ne": "admin"}}, {"_id": 0, "user_id": 1}).to_list(500)
    existing = set()
    async for p in db.onboarding_progress.find({}, {"_id": 0, "user_id": 1}):
        existing.add(p.get("user_id"))
    missing = [u for u in users_without if u.get("user_id") and u["user_id"] not in existing]
    if missing:
        proposals.append(_proposal("Onboarding", "ob_create_progress", "create_progress",
            f"Create onboarding progress for {len(missing)} users (first 2 steps pre-completed)",
            "ob_create_progress", {"user_ids": [u["user_id"] for u in missing[:100]]}))

    ob_config = await db.app_config.find_one({"key": "onboarding_config"}, {"_id": 0})
    if not ob_config or not ob_config.get("enabled"):
        proposals.append(_proposal("Onboarding", "ob_enable", "enable_config",
            "Enable onboarding flow for all new users (auto-start on first login)",
            "ob_enable", {}))

    return proposals


async def propose_newsletter(db) -> list:
    proposals = []
    datetime.now(timezone.utc)

    nl_config = await db.app_config.find_one({"key": "newsletter_config"}, {"_id": 0})
    if not nl_config:
        proposals.append(_proposal("Newsletter", "nl_config", "configure_tracking",
            "Enable newsletter open/click tracking",
            "nl_config", {}))

    analytics_count = await db.newsletter_analytics.count_documents({})
    if analytics_count == 0:
        proposals.append(_proposal("Newsletter", "nl_seed_analytics", "seed_analytics",
            "Initialize newsletter analytics tracking baseline",
            "nl_seed_analytics", {}))

    campaign_count = await db.newsletter_campaigns.count_documents({})
    if campaign_count == 0:
        proposals.append(_proposal("Newsletter", "nl_welcome_campaign", "create_campaign",
            "Create 'Welcome to RealAICoach' draft email campaign",
            "nl_welcome_campaign", {}))

    active_users = await db.users.find({"role": {"$ne": "admin"}, "email": {"$exists": True}}, {"_id": 0, "email": 1, "name": 1}).to_list(500)
    existing_subs = set()
    async for s in db.newsletter_subscribers.find({}, {"_id": 0, "email": 1}):
        existing_subs.add(s.get("email"))
    new_subs = [u for u in active_users if u.get("email") and u["email"] not in existing_subs]
    if new_subs:
        proposals.append(_proposal("Newsletter", "nl_auto_subscribe", "auto_subscribe",
            f"Add {len(new_subs)} active users to newsletter subscriber list",
            "nl_auto_subscribe", {"emails": [u["email"] for u in new_subs[:200]]}))

    return proposals


async def propose_security(db) -> list:
    proposals = []
    now = datetime.now(timezone.utc)

    session_cutoff = (now - timedelta(days=30)).isoformat()
    expired_count = await db.user_sessions.count_documents({"created_at": {"$lte": session_cutoff}})
    if expired_count > 0:
        proposals.append(_proposal("Security", "sec_clean_sessions", "clean_sessions",
            f"Clean {expired_count} expired sessions (>30 days old)",
            "sec_clean_sessions", {}))

    ip_cutoff = (now - timedelta(days=90)).isoformat()
    stale_ips = await db.ip_blocklist.count_documents({"blocked_at": {"$lte": ip_cutoff}})
    if stale_ips > 0:
        proposals.append(_proposal("Security", "sec_clean_ips", "clean_blocklist",
            f"Remove {stale_ips} stale IP blocks (>90 days old)",
            "sec_clean_ips", {}))

    admins_no_2fa = await db.users.count_documents({"role": "admin", "two_factor_enabled": {"$ne": True}})
    if admins_no_2fa > 0:
        proposals.append(_proposal("Security", "sec_2fa_flag", "recommend_2fa",
            f"Flag {admins_no_2fa} admin accounts for 2FA activation",
            "sec_2fa_flag", {}))

    sec_config = await db.app_config.find_one({"key": "security_config"}, {"_id": 0})
    if not sec_config:
        proposals.append(_proposal("Security", "sec_policy", "configure_policy",
            "Configure security policy: 90d event retention, auto-block after 10 failures, 24h session timeout",
            "sec_policy", {}))

    return proposals


async def propose_churn(db) -> list:
    proposals = []
    now = datetime.now(timezone.utc)
    thirty_days = (now - timedelta(days=30)).isoformat()

    recent_sessions = set()
    async for s in db.user_sessions.find({"created_at": {"$gte": thirty_days}}, {"_id": 0, "user_id": 1}):
        recent_sessions.add(s.get("user_id"))

    premium = await db.users.find(
        {"subscription_plan": {"$nin": [None, "free", ""]}, "subscription_status": "active"},
        {"_id": 0, "user_id": 1, "email": 1, "subscription_plan": 1}
    ).to_list(500)
    inactive = [u for u in premium if u.get("user_id") not in recent_sessions]

    unflagged = 0
    for u in inactive[:50]:
        existing = await db.churn_risk_flags.find_one({"user_id": u["user_id"], "status": "active"}, {"_id": 0})
        if not existing:
            unflagged += 1

    if unflagged > 0:
        proposals.append(_proposal("Churn", "churn_flag", "flag_at_risk",
            f"Flag {unflagged} inactive premium users as churn risk (no activity in 30+ days)",
            "churn_flag", {"user_ids": [u["user_id"] for u in inactive[:50]]}))

    retention_config = await db.app_config.find_one({"key": "retention_config"}, {"_id": 0})
    if not retention_config:
        proposals.append(_proposal("Churn", "churn_retention", "configure_retention",
            "Configure retention policy: 14-day inactivity trigger, re-engagement email, 20% discount offer",
            "churn_retention", {}))

    return proposals


async def propose_performance(db) -> list:
    proposals = []
    now = datetime.now(timezone.utc)

    perf_cutoff = (now - timedelta(days=30)).isoformat()
    stale = await db.page_performance_metrics.count_documents({"timestamp": {"$lte": perf_cutoff}})
    if stale > 0:
        proposals.append(_proposal("Performance", "perf_clean", "clean_metrics",
            f"Clean {stale} stale performance records (>30 days old)",
            "perf_clean", {}))

    sys_stale = await db.system_performance_history.count_documents({"timestamp": {"$lte": perf_cutoff}})
    if sys_stale > 0:
        proposals.append(_proposal("Performance", "perf_clean_sys", "clean_system_history",
            f"Clean {sys_stale} old system metrics (>30 days old)",
            "perf_clean_sys", {}))

    perf_config = await db.app_config.find_one({"key": "performance_config"}, {"_id": 0})
    if not perf_config:
        proposals.append(_proposal("Performance", "perf_config", "configure_monitoring",
            "Configure performance monitoring: 3s alert threshold, 2s P95 target, auto-cache optimization",
            "perf_config", {}))

    return proposals


async def propose_fraud(db) -> list:
    proposals = []
    now = datetime.now(timezone.utc)

    fraud_cutoff = (now - timedelta(days=60)).isoformat()
    old_flags = await db.fraud_flags.count_documents(
        {"status": {"$in": ["resolved", "dismissed"]}, "resolved_at": {"$lte": fraud_cutoff}})
    if old_flags > 0:
        proposals.append(_proposal("Fraud", "fraud_clean", "clean_flags",
            f"Clean {old_flags} resolved fraud flags (>60 days old)",
            "fraud_clean", {}))

    fraud_config = await db.app_config.find_one({"key": "fraud_config"}, {"_id": 0})
    if not fraud_config:
        proposals.append(_proposal("Fraud", "fraud_config", "configure_detection",
            "Configure fraud detection: 6h scan interval, 5-failure threshold, geo-anomaly enabled",
            "fraud_config", {}))

    return proposals


# ── Phase 2: GPT-4o Confidence Evaluation ────────────────────────────────────

async def evaluate_confidence(proposals: list) -> list:
    """Ask GPT-4o to evaluate each proposed fix with a confidence score."""
    if not proposals:
        return []

    from routes.db import EMERGENT_LLM_KEY
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    proposal_summaries = [
        {"id": p["action_id"], "engine": p["engine"], "action": p["action"], "details": p["details"]}
        for p in proposals
    ]

    prompt = f"""You are a platform safety evaluator. Evaluate these proposed auto-fix actions for an AI coaching SaaS platform.

For each action, assign:
- confidence: 0-100 (how safe and appropriate this fix is)
- risk: "none", "low", "medium", "high"
- reasoning: 1 sentence explaining your score
- auto_apply: true if confidence >= {CONFIDENCE_THRESHOLD} and risk is none/low, false otherwise

PROPOSED ACTIONS:
{json.dumps(proposal_summaries, indent=2)}

Return JSON array:
[
  {{"id": "<action_id>", "confidence": <0-100>, "risk": "<none|low|medium|high>", "reasoning": "<1 sentence>", "auto_apply": true|false}}
]

Be strict: only mark auto_apply=true for clearly safe, reversible, non-destructive actions. Configuration changes, data cleanup of old records, and status updates are generally safe. Deleting user data or sending emails to users require higher scrutiny."""

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"autofix-eval-{uuid.uuid4().hex[:8]}",
            system_message="You are a strict safety evaluator. Always return valid JSON only.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        evaluations = json.loads(text.strip())

        # Merge evaluations back into proposals
        eval_map = {e["id"]: e for e in evaluations}
        for p in proposals:
            ev = eval_map.get(p["action_id"], {})
            p["confidence"] = ev.get("confidence", 50)
            p["risk"] = ev.get("risk", "medium")
            p["reasoning"] = ev.get("reasoning", "No evaluation available")
            p["auto_apply"] = ev.get("auto_apply", False)

    except Exception as e:
        logger.error(f"GPT-4o confidence evaluation failed: {e}")
        # Fallback: apply safe defaults based on action type
        safe_actions = {"clean_sessions", "clean_blocklist", "clean_flags", "clean_metrics",
                        "clean_system_history", "configure_policy", "configure_monitoring",
                        "configure_tracking", "configure_detection", "seed_steps", "seed_funnel",
                        "seed_analytics", "enable_config", "configure_modal", "configure_nudge",
                        "configure_retention", "auto_close"}
        for p in proposals:
            if p["action"] in safe_actions:
                p["confidence"] = 90
                p["risk"] = "none"
                p["reasoning"] = "Standard safe maintenance action (fallback evaluation)"
                p["auto_apply"] = True
            else:
                p["confidence"] = 65
                p["risk"] = "low"
                p["reasoning"] = "Requires GPT-4o evaluation (fallback)"
                p["auto_apply"] = False

    return proposals


# ── Phase 3: Apply approved fixes ────────────────────────────────────────────

async def apply_fix(db, proposal: dict) -> dict:
    """Apply a single approved fix and return the result."""
    now = datetime.now(timezone.utc)
    fn = proposal["apply_fn"]
    ctx = proposal.get("context", {})

    try:
        if fn == "sla_escalate":
            await db.support_tickets.update_one(
                {"ticket_id": ctx["ticket_id"]},
                {"$set": {"sla_escalated": True, "priority": "urgent", "sla_escalated_at": now.isoformat(),
                          "auto_fix_note": "Auto-escalated by AI Auto-Fix Engine"}})

        elif fn == "sla_assign":
            await db.support_tickets.update_one(
                {"ticket_id": ctx["ticket_id"]},
                {"$set": {"assigned_to": ctx["agent_id"], "status": "in_progress",
                          "auto_fix_note": f"Auto-assigned to {ctx.get('agent_name', 'agent')}"}})

        elif fn == "sla_close_stale":
            close_cutoff = (now - timedelta(hours=48)).isoformat()
            await db.support_tickets.update_many(
                {"status": "resolved", "resolved_at": {"$lte": close_cutoff}, "auto_closed": {"$ne": True}},
                {"$set": {"status": "closed", "auto_closed": True, "closed_at": now.isoformat()}})

        elif fn == "conv_modal_config":
            await db.app_config.update_one({"key": "modal_analytics"},
                {"$set": {"enabled": True, "display_delay_seconds": 5, "show_on_pages": ["home", "pricing", "features"],
                          "dismiss_cooldown_hours": 24, "auto_configured": True}}, upsert=True)

        elif fn == "conv_seed_funnel":
            stages = ["page_visit", "signup_modal_view", "signup_click", "registration_complete", "trial_start", "first_session", "premium_upgrade"]
            for stage in stages:
                await db.conversion_events.insert_one({"stage": stage, "count": 0, "tracked_since": now.isoformat(), "auto_seeded": True})

        elif fn == "conv_nudge":
            await db.app_config.update_one({"key": "trial_nudge"},
                {"$set": {"enabled": True, "trigger_day": 5, "message": "Upgrade to Premium for unlimited access.", "auto_configured": True}}, upsert=True)

        elif fn == "ob_seed_steps":
            steps = [
                {"step_id": "welcome", "title": "Welcome Tour", "order": 1, "required": True},
                {"step_id": "profile_setup", "title": "Complete Your Profile", "order": 2, "required": True},
                {"step_id": "first_session", "title": "Start First Session", "order": 3, "required": True},
                {"step_id": "set_goals", "title": "Set Your Goals", "order": 4, "required": False},
                {"step_id": "explore_features", "title": "Explore Features", "order": 5, "required": False},
            ]
            for s in steps:
                s["created_at"] = now.isoformat()
                s["auto_seeded"] = True
            await db.onboarding_steps.insert_many(steps)

        elif fn == "ob_create_progress":
            records = []
            for uid in ctx.get("user_ids", []):
                records.append({"user_id": uid, "completed_steps": ["welcome", "profile_setup"],
                                "current_step": "first_session", "started_at": now.isoformat(), "completed": False, "auto_created": True})
            if records:
                await db.onboarding_progress.insert_many(records)

        elif fn == "ob_enable":
            await db.app_config.update_one({"key": "onboarding_config"},
                {"$set": {"enabled": True, "show_for_new_users": True, "auto_start": True, "auto_configured": True}}, upsert=True)

        elif fn == "nl_config":
            await db.app_config.update_one({"key": "newsletter_config"},
                {"$set": {"enabled": True, "track_opens": True, "track_clicks": True, "auto_configured": True}}, upsert=True)

        elif fn == "nl_seed_analytics":
            await db.newsletter_analytics.insert_one({"period": "baseline", "sent": 0, "opens": 0, "clicks": 0, "auto_seeded": True})

        elif fn == "nl_welcome_campaign":
            await db.newsletter_campaigns.insert_one({
                "campaign_id": f"auto_welcome_{now.strftime('%Y%m%d')}", "name": "Welcome to RealAICoach",
                "subject": "Welcome — Your AI Coaching Journey Starts Here", "type": "welcome",
                "status": "draft", "created_at": now.isoformat(), "auto_created": True})

        elif fn == "nl_auto_subscribe":
            subs = [{"email": e, "status": "active", "subscribed_at": now.isoformat(), "source": "auto_fix"} for e in ctx.get("emails", [])]
            if subs:
                await db.newsletter_subscribers.insert_many(subs)

        elif fn == "sec_clean_sessions":
            cutoff = (now - timedelta(days=30)).isoformat()
            await db.user_sessions.delete_many({"created_at": {"$lte": cutoff}})

        elif fn == "sec_clean_ips":
            cutoff = (now - timedelta(days=90)).isoformat()
            await db.ip_blocklist.delete_many({"blocked_at": {"$lte": cutoff}})

        elif fn == "sec_2fa_flag":
            await db.users.update_many({"role": "admin", "two_factor_enabled": {"$ne": True}},
                {"$set": {"security_recommendation": "Enable 2FA", "security_recommendation_at": now.isoformat()}})

        elif fn == "sec_policy":
            await db.app_config.update_one({"key": "security_config"},
                {"$set": {"event_retention_days": 90, "auto_block_after_failures": 10, "session_timeout_hours": 24, "auto_configured": True}}, upsert=True)

        elif fn == "churn_flag":
            for uid in ctx.get("user_ids", []):
                existing = await db.churn_risk_flags.find_one({"user_id": uid, "status": "active"})
                if not existing:
                    await db.churn_risk_flags.insert_one({"user_id": uid, "risk_level": "high", "reason": "No activity 30d+", "status": "active", "auto_flagged": True, "flagged_at": now.isoformat()})

        elif fn == "churn_retention":
            await db.app_config.update_one({"key": "retention_config"},
                {"$set": {"enabled": True, "inactivity_threshold_days": 14, "send_reengagement_email": True, "offer_discount": True, "discount_pct": 20, "auto_configured": True}}, upsert=True)

        elif fn == "perf_clean":
            cutoff = (now - timedelta(days=30)).isoformat()
            await db.page_performance_metrics.delete_many({"timestamp": {"$lte": cutoff}})

        elif fn == "perf_clean_sys":
            cutoff = (now - timedelta(days=30)).isoformat()
            await db.system_performance_history.delete_many({"timestamp": {"$lte": cutoff}})

        elif fn == "perf_config":
            await db.app_config.update_one({"key": "performance_config"},
                {"$set": {"monitoring_enabled": True, "alert_threshold_ms": 3000, "p95_target_ms": 2000, "auto_configured": True}}, upsert=True)

        elif fn == "fraud_clean":
            cutoff = (now - timedelta(days=60)).isoformat()
            await db.fraud_flags.delete_many({"status": {"$in": ["resolved", "dismissed"]}, "resolved_at": {"$lte": cutoff}})

        elif fn == "fraud_config":
            await db.app_config.update_one({"key": "fraud_config"},
                {"$set": {"enabled": True, "auto_scan_interval_hours": 6, "suspicious_login_threshold": 5, "geo_anomaly_detection": True, "auto_configured": True}}, upsert=True)

        return {"status": "applied", "action_id": proposal["action_id"]}

    except Exception as e:
        logger.error(f"Apply fix {fn} failed: {e}")
        return {"status": "failed", "action_id": proposal["action_id"], "error": str(e)}


# ── Master Orchestrator ──────────────────────────────────────────────────────

ALL_PROPOSERS = [
    ("SLA", propose_sla),
    ("Conversion", propose_conversion),
    ("Onboarding", propose_onboarding),
    ("Newsletter", propose_newsletter),
    ("Security", propose_security),
    ("Churn", propose_churn),
    ("Performance", propose_performance),
    ("Fraud", propose_fraud),
]


async def run_all_fixes() -> dict:
    """Two-phase auto-fix: propose -> evaluate -> apply."""
    db = await _get_db()
    now = datetime.now(timezone.utc)

    # Phase 1: Gather all proposals
    all_proposals = []
    engine_proposal_counts = {}
    for engine_name, proposer in ALL_PROPOSERS:
        try:
            proposals = await proposer(db)
            all_proposals.extend(proposals)
            engine_proposal_counts[engine_name] = len(proposals)
        except Exception as e:
            logger.error(f"Proposer {engine_name} failed: {e}")
            engine_proposal_counts[engine_name] = 0

    if not all_proposals:
        result = {
            "success": True, "run_at": now.isoformat(),
            "total_proposed": 0, "total_applied": 0, "total_flagged": 0,
            "engines_processed": len(ALL_PROPOSERS),
            "engine_results": {name: {"proposed": 0, "applied": 0, "flagged": 0} for name, _ in ALL_PROPOSERS},
            "fixes": [{"engine": "System", "action": "no_action", "details": "All systems healthy — nothing to fix",
                        "confidence": 100, "risk": "none", "status": "skipped", "impact": "neutral", "timestamp": now.isoformat()}],
        }
        await db.ai_autofix_history.insert_one({**result})
        return result

    # Phase 2: GPT-4o confidence evaluation
    evaluated_proposals = await evaluate_confidence(all_proposals)

    # Phase 3: Apply approved fixes, flag the rest
    applied = []
    flagged = []
    engine_results = {name: {"proposed": 0, "applied": 0, "flagged": 0} for name, _ in ALL_PROPOSERS}

    # Load configurable threshold from DB
    config = await db.ai_autofix_config.find_one({"_id": "autofix_settings"})
    threshold = config.get("confidence_threshold", CONFIDENCE_THRESHOLD) if config else CONFIDENCE_THRESHOLD

    for p in evaluated_proposals:
        eng = p["engine"]
        engine_results[eng]["proposed"] += 1

        fix_record = {
            "engine": p["engine"],
            "action": p["action"],
            "action_id": p["action_id"],
            "apply_fn": p.get("apply_fn"),
            "context": p.get("context", {}),
            "details": p["details"],
            "confidence": p.get("confidence", 0),
            "risk": p.get("risk", "unknown"),
            "reasoning": p.get("reasoning", ""),
            "timestamp": p["timestamp"],
        }

        if p.get("auto_apply", False) and p.get("confidence", 0) >= threshold:
            result = await apply_fix(db, p)
            fix_record["status"] = "applied"
            fix_record["impact"] = "positive"
            applied.append(fix_record)
            engine_results[eng]["applied"] += 1
        else:
            fix_record["status"] = "flagged_for_review"
            fix_record["impact"] = "pending"
            flagged.append(fix_record)
            engine_results[eng]["flagged"] += 1

    all_fixes = applied + flagged

    run_record = {
        "success": True,
        "run_at": now.isoformat(),
        "total_proposed": len(all_proposals),
        "total_applied": len(applied),
        "total_flagged": len(flagged),
        "engines_processed": len(ALL_PROPOSERS),
        "confidence_threshold": threshold,
        "engine_results": engine_results,
        "fixes": all_fixes,
    }
    await db.ai_autofix_history.insert_one({**run_record})

    # Save flagged items for manual review
    if flagged:
        now_iso = now.isoformat()
        await db.ai_autofix_review_queue.delete_many({"review_status": "pending"})
        for fix in flagged:
            await db.ai_autofix_review_queue.insert_one({
                **fix,
                "review_status": "pending",
                "created_at": now_iso,
                "updated_at": now_iso,
            })

    return run_record


@router.post("/run")
async def run_autofix(request: Request):
    """Run the full AI Auto-Fix Engine with confidence scoring."""
    await _require_admin(request)
    result = await run_all_fixes()
    return result


@router.get("/history")
async def get_autofix_history(request: Request):
    """Get recent auto-fix run history."""
    await _require_admin(request)
    db = await _get_db()
    runs = await db.ai_autofix_history.find({}, {"_id": 0}).sort("run_at", -1).to_list(20)
    return {"runs": runs}


@router.get("/latest")
async def get_latest_autofix(request: Request):
    """Get the latest auto-fix run results."""
    await _require_admin(request)
    db = await _get_db()
    latest = await db.ai_autofix_history.find_one({}, {"_id": 0}, sort=[("run_at", -1)])
    if not latest:
        return {"status": "no_runs", "message": "No auto-fix runs yet."}
    return latest


@router.get("/review-queue")
async def get_review_queue(request: Request):
    """Get items flagged for manual review."""
    await _require_admin(request)
    db = await _get_db()
    raw_items = await db.ai_autofix_review_queue.find(
        {"review_status": "pending"}, {"_id": 0}
    ).sort([("updated_at", -1), ("created_at", -1)]).to_list(200)

    items = []
    seen_action_ids = set()
    for item in raw_items:
        action_id = item.get("action_id")
        if not action_id or action_id in seen_action_ids:
            continue
        seen_action_ids.add(action_id)
        items.append(item)
        if len(items) >= 50:
            break

    return {"items": items, "total": len(items)}


@router.post("/review-queue/{action_id}/approve")
async def approve_review_item(action_id: str, request: Request):
    """Manually approve a flagged fix."""
    await _require_admin(request)
    db = await _get_db()
    item = await db.ai_autofix_review_queue.find_one({"action_id": action_id, "review_status": "pending"}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")

    apply_fn = _resolve_apply_fn(item)
    if not apply_fn:
        raise HTTPException(status_code=500, detail="Unable to resolve the auto-fix action for this review item")

    result = await apply_fix(db, {**item, "apply_fn": apply_fn, "context": item.get("context", {})})
    if result.get("status") != "applied":
        raise HTTPException(status_code=500, detail=result.get("error") or "Failed to apply review item")

    await db.ai_autofix_review_queue.update_many(
        {"action_id": action_id},
        {"$set": {"review_status": "approved", "approved_at": datetime.now(timezone.utc).isoformat(), "apply_result": result}}
    )
    return {"success": True, "action_id": action_id, "status": "approved_and_applied", "result": result}


@router.post("/review-queue/{action_id}/dismiss")
async def dismiss_review_item(action_id: str, request: Request):
    """Dismiss a flagged fix (skip it)."""
    await _require_admin(request)
    db = await _get_db()
    result = await db.ai_autofix_review_queue.update_many(
        {"action_id": action_id, "review_status": "pending"},
        {"$set": {"review_status": "dismissed", "dismissed_at": datetime.now(timezone.utc).isoformat()}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Review item not found")

    return {"success": True, "action_id": action_id, "status": "dismissed"}


@router.post("/reset")
async def reset_autofix_state(request: Request):
    """Reset all data created by the auto-fix engine so it can be re-tested."""
    await _require_admin(request)
    db = await _get_db()
    counts = {}

    # Remove auto-configured app_config entries
    r = await db.app_config.delete_many({"auto_configured": True})
    counts["app_config"] = r.deleted_count

    # Remove auto-seeded onboarding steps
    r = await db.onboarding_steps.delete_many({"auto_seeded": True})
    counts["onboarding_steps"] = r.deleted_count

    # Remove auto-created onboarding progress
    r = await db.onboarding_progress.delete_many({"auto_created": True})
    counts["onboarding_progress"] = r.deleted_count

    # Remove auto-seeded conversion events
    r = await db.conversion_events.delete_many({"auto_seeded": True})
    counts["conversion_events"] = r.deleted_count

    # Remove auto-seeded newsletter analytics
    r = await db.newsletter_analytics.delete_many({"auto_seeded": True})
    counts["newsletter_analytics"] = r.deleted_count

    # Remove auto-created newsletter campaigns
    r = await db.newsletter_campaigns.delete_many({"auto_created": True})
    counts["newsletter_campaigns"] = r.deleted_count

    # Remove auto-subscribed newsletter subscribers
    r = await db.newsletter_subscribers.delete_many({"source": "auto_fix"})
    counts["newsletter_subscribers"] = r.deleted_count

    # Remove auto-flagged churn risk entries
    r = await db.churn_risk_flags.delete_many({"auto_flagged": True})
    counts["churn_risk_flags"] = r.deleted_count

    # Clear autofix history and review queue
    r = await db.ai_autofix_history.delete_many({})
    counts["ai_autofix_history"] = r.deleted_count

    r = await db.ai_autofix_review_queue.delete_many({})
    counts["ai_autofix_review_queue"] = r.deleted_count

    # Remove security recommendations added by auto-fix
    r = await db.users.update_many(
        {"security_recommendation": {"$exists": True}},
        {"$unset": {"security_recommendation": "", "security_recommendation_at": ""}}
    )
    counts["users_security_rec_cleared"] = r.modified_count

    total = sum(counts.values())
    return {"success": True, "total_reset": total, "details": counts}


# ── Feature 1: Configurable Confidence Threshold ──────────────────────


@router.get("/config")
async def get_autofix_config(request: Request):
    """Get current auto-fix configuration including confidence threshold."""
    await _require_admin(request)
    db = await _get_db()
    defaults = {"confidence_threshold": CONFIDENCE_THRESHOLD, "auto_run_enabled": True, "run_interval_minutes": 30}
    config = await db.ai_autofix_config.find_one({"_id": "autofix_settings"})
    if config:
        config.pop("_id", None)
        defaults.update(config)
    return defaults


@router.put("/config")
async def update_autofix_config(request: Request):
    """Update auto-fix configuration (confidence threshold, auto-run, etc.)."""
    await _require_admin(request)
    db = await _get_db()
    body = await request.json()

    update = {}
    if "confidence_threshold" in body:
        val = int(body["confidence_threshold"])
        if val < 0 or val > 100:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Confidence threshold must be 0-100")
        update["confidence_threshold"] = val
    if "auto_run_enabled" in body:
        update["auto_run_enabled"] = bool(body["auto_run_enabled"])
    if "run_interval_minutes" in body:
        update["run_interval_minutes"] = max(5, int(body["run_interval_minutes"]))

    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.ai_autofix_config.update_one(
        {"_id": "autofix_settings"},
        {"$set": update},
        upsert=True
    )
    config = await db.ai_autofix_config.find_one({"_id": "autofix_settings"})
    config.pop("_id", None)
    return {"success": True, **config}


# ── Feature 2: Audit Trail Export (CSV/PDF) ───────────────────────────

import csv
import io


@router.get("/export/csv")
async def export_audit_trail_csv(request: Request):
    """Export auto-fix audit trail as CSV."""
    await _require_admin(request)
    db = await _get_db()
    runs = await db.ai_autofix_history.find({}, {"_id": 0}).sort("run_at", -1).to_list(100)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Run Date", "Engine", "Action", "Details", "Confidence %", "Risk", "Status", "Reasoning"])

    for run in runs:
        run_date = run.get("run_at", "")
        for fix in run.get("fixes", []):
            writer.writerow([
                run_date,
                fix.get("engine", ""),
                fix.get("action", ""),
                fix.get("details", ""),
                fix.get("confidence", ""),
                fix.get("risk", ""),
                fix.get("status", ""),
                fix.get("reasoning", ""),
            ])

    from starlette.responses import Response

    # Notify user via email that export is ready
    from utils.email_service import notify_export_ready
    user = getattr(request.state, "user", None)
    if user and getattr(user, "email", None):
        import asyncio
        asyncio.ensure_future(notify_export_ready(user.email, getattr(user, "name", ""), "Auto-Fix Audit Trail", "CSV"))

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=autofix_audit_trail.csv"}
    )


@router.get("/export/pdf")
async def export_audit_trail_pdf(request: Request):
    """Export auto-fix audit trail as a formatted text report (PDF-like)."""
    await _require_admin(request)
    db = await _get_db()
    runs = await db.ai_autofix_history.find({}, {"_id": 0}).sort("run_at", -1).to_list(50)

    lines = []
    lines.append("=" * 80)
    lines.append("AI AUTO-FIX ENGINE — AUDIT TRAIL REPORT")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 80)
    lines.append("")

    for i, run in enumerate(runs):
        run_date = run.get("run_at", "N/A")
        lines.append(f"--- Run #{i+1}: {run_date} ---")
        lines.append(f"  Proposed: {run.get('total_proposed', 0)} | Applied: {run.get('total_applied', 0)} | Flagged: {run.get('total_flagged', 0)}")
        lines.append(f"  Confidence Threshold: {run.get('confidence_threshold', CONFIDENCE_THRESHOLD)}%")
        lines.append("")

        for fix in run.get("fixes", []):
            status_icon = "[OK]" if fix.get("status") == "applied" else "[!!]" if fix.get("status") == "flagged_for_review" else "[--]"
            lines.append(f"  {status_icon} [{fix.get('engine', '')}] {fix.get('action', '')}")
            lines.append(f"      Details: {fix.get('details', '')}")
            lines.append(f"      Confidence: {fix.get('confidence', 'N/A')}% | Risk: {fix.get('risk', 'N/A')} | Status: {fix.get('status', '')}")
            if fix.get("reasoning"):
                lines.append(f"      AI Reasoning: {fix.get('reasoning', '')}")
            lines.append("")
        lines.append("")

    lines.append("=" * 80)
    lines.append(f"Total runs: {len(runs)}")
    lines.append("END OF REPORT")

    from starlette.responses import Response
    return Response(
        content="\n".join(lines),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=autofix_audit_trail.txt"}
    )
