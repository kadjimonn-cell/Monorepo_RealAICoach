"""AI Panel Insights — GPT-4o powered intelligence for admin panels.

Provides AI-driven analysis endpoints for:
1. SLA Breach Prediction
2. Conversion Optimization
3. Onboarding Drop-off Analysis
4. Newsletter Content Suggestions
5. Security Narrative
6. Churn Prediction
7. Performance Forecasting
8. Fraud Risk Narrative
"""

import json
import uuid
import logging
import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ai-insights", tags=["ai-panel-insights"])


async def _get_db():
    from routes.db import db
    return db


async def _require_admin(request: Request):
    from routes.db import require_admin
    await require_admin(request)


async def _call_gpt(prompt: str, session_tag: str) -> dict:
    """Call GPT-4o via Emergent LLM Key and parse JSON response."""
    from routes.db import EMERGENT_LLM_KEY
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"{session_tag}-{uuid.uuid4().hex[:8]}",
        system_message="You are a precise analytics AI. Always return valid JSON only. No markdown, no backticks.",
    ).with_model("openai", "gpt-4o")

    response = await chat.send_message(UserMessage(text=prompt))
    text = response.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


async def _get_cached(db, cache_key: str, max_age_seconds: int = 3600):
    """Return cached analysis if fresh enough."""
    cached = await db.ai_panel_insights.find_one(
        {"cache_key": cache_key}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if cached:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached["created_at"])).total_seconds()
        if age < max_age_seconds:
            return cached
    return None


async def _save_cache(db, cache_key: str, result: dict):
    """Save analysis result to cache."""
    record = {
        "cache_key": cache_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    await db.ai_panel_insights.insert_one(record)
    safe_record = dict(record)
    safe_record.pop("_id", None)
    return safe_record


# ── 1. SLA Breach Predictor ──────────────────────────────────────────────────

@router.post("/sla-predictor")
async def sla_breach_predictor(request: Request):
    """AI predicts which tickets are likely to breach SLA and suggests actions."""
    await _require_admin(request)
    db = await _get_db()

    cached = await _get_cached(db, "sla_predictor")
    if cached:
        return cached

    # Gather SLA data
    now = datetime.now(timezone.utc)
    config = await db.app_config.find_one({"key": "sla_config"}, {"_id": 0}) or {}
    escalation_hours = config.get("escalation_hours", 24)

    open_tickets = await db.support_tickets.find(
        {"status": {"$in": ["open", "in_progress", "pending"]}},
        {"_id": 0, "ticket_id": 1, "subject": 1, "status": 1, "priority": 1, "category": 1, "created_at": 1}
    ).sort("created_at", 1).to_list(100)

    resolved_recent = await db.support_tickets.find(
        {"status": {"$in": ["resolved", "closed"]}, "resolved_at": {"$exists": True}},
        {"_id": 0, "category": 1, "priority": 1, "created_at": 1, "resolved_at": 1}
    ).sort("resolved_at", -1).to_list(200)

    # Calculate resolution times by category
    cat_resolution = {}
    for t in resolved_recent:
        cat = t.get("category", "general")
        try:
            created = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")) if isinstance(t["created_at"], str) else t["created_at"]
            resolved = datetime.fromisoformat(t["resolved_at"].replace("Z", "+00:00")) if isinstance(t["resolved_at"], str) else t["resolved_at"]
            hours = (resolved - created).total_seconds() / 3600
            cat_resolution.setdefault(cat, []).append(hours)
        except Exception:
            pass

    cat_avg_hours = {cat: round(sum(h) / len(h), 1) for cat, h in cat_resolution.items() if h}

    # Enrich open tickets with wait time
    enriched = []
    for t in open_tickets:
        try:
            created = datetime.fromisoformat(str(t["created_at"]).replace("Z", "+00:00")) if isinstance(t["created_at"], str) else t["created_at"]
            wait_hours = round((now - created).total_seconds() / 3600, 1)
        except Exception:
            wait_hours = 0
        enriched.append({**t, "wait_hours": wait_hours, "sla_pct": round(wait_hours / escalation_hours * 100, 1)})

    prompt = f"""Analyze these support tickets and predict SLA breaches for a platform with {escalation_hours}h SLA target.

OPEN TICKETS ({len(enriched)}):
{json.dumps(enriched[:30], default=str)}

HISTORICAL RESOLUTION TIMES BY CATEGORY (hours):
{json.dumps(cat_avg_hours)}

Return JSON:
{{
  "risk_score": <0-100>,
  "predicted_breaches": <number of tickets likely to breach>,
  "risk_summary": "<2-3 sentence summary>",
  "at_risk_tickets": [
    {{"ticket_id": "<id>", "subject": "<subject>", "breach_probability": <0-100>, "estimated_hours_left": <hours>, "recommended_action": "<action>"}}
  ],
  "optimization_tips": [
    {{"tip": "<actionable tip>", "impact": "<high|medium|low>", "category": "<category>"}}
  ],
  "category_risks": [
    {{"category": "<name>", "avg_resolution_hours": <hours>, "risk_level": "<high|medium|low>", "suggestion": "<improvement>"}}
  ]
}}

Return max 10 at_risk_tickets, 5 optimization_tips, and all category_risks."""

    try:
        result = await _call_gpt(prompt, "sla-predictor")
    except Exception as e:
        logger.error(f"SLA predictor AI failed: {e}")
        result = {
            "risk_score": 0, "predicted_breaches": 0,
            "risk_summary": "AI analysis unavailable. Check ticket queue manually.",
            "at_risk_tickets": [], "optimization_tips": [], "category_risks": [],
        }

    record = await _save_cache(db, "sla_predictor", result)
    return {k: v for k, v in record.items() if k != "_id"}


# ── 2. Conversion Optimizer ──────────────────────────────────────────────────

@router.post("/conversion-optimizer")
async def conversion_optimizer(request: Request):
    """AI analyzes conversion funnel and suggests optimization strategies."""
    await _require_admin(request)
    db = await _get_db()

    cached = await _get_cached(db, "conversion_optimizer")
    if cached:
        return cached

    # Gather conversion data
    now = datetime.now(timezone.utc)
    thirty_days = (now - timedelta(days=30)).isoformat()

    total_users = await db.users.count_documents({})
    premium_users = await db.users.count_documents({"subscription_plan": {"$in": ["premium", "pro", "enterprise"]}})
    recent_signups = await db.users.count_documents({"created_at": {"$gte": thirty_days}})

    # Modal analytics
    modal_stats = await db.newsletter_modal_analytics.find({}, {"_id": 0}).to_list(1000)
    total_views = sum(m.get("views", 0) for m in modal_stats)
    total_signups = sum(m.get("sign_up_clicks", 0) for m in modal_stats)
    total_dismissals = sum(m.get("dismissals", 0) for m in modal_stats)

    # Trial conversions
    trials = await db.users.count_documents({"subscription_plan": "trial"})

    # Payment data
    payments = await db.payments.find(
        {"created_at": {"$gte": thirty_days}},
        {"_id": 0, "amount": 1, "status": 1, "provider": 1}
    ).to_list(500)
    successful = [p for p in payments if p.get("status") in ["confirmed", "succeeded", "completed"]]
    failed = [p for p in payments if p.get("status") in ["failed", "declined"]]

    prompt = f"""Analyze conversion funnel data for an AI coaching SaaS platform and suggest optimizations.

DATA:
- Total users: {total_users}
- Premium users: {premium_users} ({round(premium_users/max(total_users,1)*100, 1)}%)
- Recent signups (30d): {recent_signups}
- Trial users: {trials}
- Modal views: {total_views}, Sign-up clicks: {total_signups}, Dismissals: {total_dismissals}
- Payments (30d): {len(successful)} successful, {len(failed)} failed
- Conversion rate: {round(premium_users/max(total_users,1)*100, 2)}%

Return JSON:
{{
  "conversion_health": <0-100>,
  "predicted_conversions_next_month": <number>,
  "executive_summary": "<3-4 sentence analysis>",
  "funnel_analysis": [
    {{"stage": "<stage name>", "drop_off_pct": <percentage>, "issue": "<identified issue>", "fix": "<specific fix>"}}
  ],
  "optimization_strategies": [
    {{"strategy": "<name>", "description": "<1-2 sentences>", "expected_lift": "<+X%>", "effort": "<low|medium|high>", "priority": <1-5>}}
  ],
  "quick_wins": [
    {{"action": "<immediate action>", "expected_impact": "<impact description>"}}
  ]
}}

Return 4-6 funnel_analysis, 5-7 optimization_strategies (sorted by priority), and 3-5 quick_wins."""

    try:
        result = await _call_gpt(prompt, "conversion-opt")
    except Exception as e:
        logger.error(f"Conversion optimizer AI failed: {e}")
        result = {
            "conversion_health": 50,
            "predicted_conversions_next_month": 0,
            "executive_summary": "AI analysis unavailable.",
            "funnel_analysis": [], "optimization_strategies": [], "quick_wins": [],
        }

    record = await _save_cache(db, "conversion_optimizer", result)
    return {k: v for k, v in record.items() if k != "_id"}


# ── 3. Onboarding Coach ─────────────────────────────────────────────────────

@router.post("/onboarding-coach")
async def onboarding_coach(request: Request):
    """AI analyzes onboarding data and suggests UX improvements."""
    await _require_admin(request)
    db = await _get_db()

    cached = await _get_cached(db, "onboarding_coach")
    if cached:
        return cached

    # Gather onboarding data
    total = await db.users.count_documents({})
    onboarding_data = await db.onboarding_progress.find({}, {"_id": 0}).to_list(500)
    completed = sum(1 for o in onboarding_data if o.get("completed"))
    dismissed = sum(1 for o in onboarding_data if o.get("dismissed"))
    started = len(onboarding_data)

    # Step completion
    step_counts = {}
    for o in onboarding_data:
        for step in o.get("completed_steps", []):
            step_counts[step] = step_counts.get(step, 0) + 1

    prompt = f"""Analyze onboarding data for an AI coaching platform and suggest improvements.

DATA:
- Total users: {total}
- Onboarding started: {started}
- Completed: {completed} ({round(completed/max(started,1)*100,1)}%)
- Dismissed: {dismissed} ({round(dismissed/max(started,1)*100,1)}%)
- Step completion counts: {json.dumps(step_counts)}

Return JSON:
{{
  "onboarding_health": <0-100>,
  "completion_prediction": "<predicted completion rate next month>",
  "executive_summary": "<3-4 sentences about onboarding health>",
  "drop_off_analysis": [
    {{"step": "<step name>", "drop_off_rate": "<X%>", "likely_cause": "<reason>", "fix": "<specific fix>"}}
  ],
  "ux_improvements": [
    {{"improvement": "<name>", "description": "<1-2 sentences>", "expected_lift": "<+X%>", "effort": "<low|medium|high>", "priority": <1-5>}}
  ],
  "engagement_boosters": [
    {{"booster": "<name>", "description": "<how it helps>", "timeline": "<implementation time>"}}
  ]
}}

Return 3-5 drop_off_analysis, 5-7 ux_improvements, and 3-4 engagement_boosters."""

    try:
        result = await _call_gpt(prompt, "onboarding-coach")
    except Exception as e:
        logger.error(f"Onboarding coach AI failed: {e}")
        result = {
            "onboarding_health": 50, "completion_prediction": "N/A",
            "executive_summary": "AI analysis unavailable.",
            "drop_off_analysis": [], "ux_improvements": [], "engagement_boosters": [],
        }

    record = await _save_cache(db, "onboarding_coach", result)
    return {k: v for k, v in record.items() if k != "_id"}


# ── 4. Newsletter Content Suggestions ────────────────────────────────────────

@router.post("/newsletter-suggestions")
async def newsletter_suggestions(request: Request):
    """AI suggests newsletter content, optimal send times, and subject lines."""
    await _require_admin(request)
    db = await _get_db()

    cached = await _get_cached(db, "newsletter_suggestions")
    if cached:
        return cached

    # Gather newsletter data
    subs = await db.newsletter_subscribers.count_documents({"status": "active"})
    campaigns = await db.newsletter_campaigns.find(
        {}, {"_id": 0, "subject": 1, "sent_at": 1, "stats": 1, "status": 1}
    ).sort("sent_at", -1).to_list(20)

    analytics = await db.newsletter_analytics.find({}, {"_id": 0}).to_list(100)
    total_sent = sum(a.get("sent", 0) for a in analytics)
    total_opens = sum(a.get("opens", 0) for a in analytics)
    total_clicks = sum(a.get("clicks", 0) for a in analytics)

    prompt = f"""Analyze newsletter performance and suggest content strategy for an AI coaching platform.

DATA:
- Active subscribers: {subs}
- Total sent: {total_sent}, Opens: {total_opens} ({round(total_opens/max(total_sent,1)*100,1)}%), Clicks: {total_clicks}
- Recent campaigns: {json.dumps(campaigns[:10], default=str)}

Return JSON:
{{
  "newsletter_health": <0-100>,
  "executive_summary": "<3 sentences about newsletter performance>",
  "content_suggestions": [
    {{"topic": "<topic>", "angle": "<unique angle>", "target_segment": "<audience>", "expected_open_rate": "<X%>"}}
  ],
  "subject_line_ideas": [
    {{"subject": "<subject line>", "style": "<curiosity|urgency|value|personal>", "predicted_open_rate": "<X%>"}}
  ],
  "optimization_tips": [
    {{"tip": "<actionable tip>", "area": "<timing|content|design|segmentation>", "impact": "<high|medium|low>"}}
  ],
  "optimal_send_times": [
    {{"day": "<day>", "time": "<time>", "reason": "<why this works>"}}
  ]
}}

Return 5-6 content_suggestions, 5 subject_line_ideas, 4-5 optimization_tips, 3 optimal_send_times."""

    try:
        result = await _call_gpt(prompt, "newsletter-suggest")
    except Exception as e:
        logger.error(f"Newsletter suggestions AI failed: {e}")
        result = {
            "newsletter_health": 50, "executive_summary": "AI analysis unavailable.",
            "content_suggestions": [], "subject_line_ideas": [],
            "optimization_tips": [], "optimal_send_times": [],
        }

    record = await _save_cache(db, "newsletter_suggestions", result)
    return {k: v for k, v in record.items() if k != "_id"}


# ── 5. Security Narrative ────────────────────────────────────────────────────

@router.post("/security-narrative")
async def security_narrative(request: Request):
    """AI generates a security narrative from audit data."""
    await _require_admin(request)
    db = await _get_db()

    cached = await _get_cached(db, "security_narrative")
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    last_7d = (now - timedelta(days=7)).isoformat()

    events = await db.security_events.find(
        {"timestamp": {"$gte": last_7d}},
        {"_id": 0, "event_type": 1, "risk_level": 1, "timestamp": 1}
    ).to_list(5000)

    event_types = {}
    risk_counts = {}
    for e in events:
        et = e.get("event_type", "unknown")
        event_types[et] = event_types.get(et, 0) + 1
        rl = e.get("risk_level", "info")
        risk_counts[rl] = risk_counts.get(rl, 0) + 1

    blocked = await db.ip_blocklist.count_documents({})
    failed_logins = event_types.get("login_failed", 0)
    total_users = await db.users.count_documents({})

    prompt = f"""Generate a security narrative for an AI coaching platform's last 7 days.

DATA:
- Total security events: {len(events)}
- Event types: {json.dumps(event_types)}
- Risk levels: {json.dumps(risk_counts)}
- Blocked IPs: {blocked}
- Failed logins: {failed_logins}
- Total users: {total_users}

Return JSON:
{{
  "security_score": <0-100>,
  "threat_level": "<safe|guarded|elevated|high|severe>",
  "narrative": "<5-6 sentence security story - what happened, trends, and what it means>",
  "key_findings": [
    {{"finding": "<what was found>", "severity": "<critical|high|medium|low>", "recommendation": "<what to do>"}}
  ],
  "trends": [
    {{"metric": "<metric name>", "direction": "<up|down|stable>", "change": "<description>", "concern_level": "<none|watch|action>"}}
  ],
  "recommended_actions": [
    {{"action": "<specific action>", "priority": <1-5>, "reason": "<why>"}}
  ]
}}

Return 3-5 key_findings, 4-5 trends, 3-5 recommended_actions."""

    try:
        result = await _call_gpt(prompt, "security-narrative")
    except Exception as e:
        logger.error(f"Security narrative AI failed: {e}")
        result = {
            "security_score": 50, "threat_level": "guarded",
            "narrative": "AI analysis unavailable.",
            "key_findings": [], "trends": [], "recommended_actions": [],
        }

    record = await _save_cache(db, "security_narrative", result)
    return {k: v for k, v in record.items() if k != "_id"}


# ── 6. Churn Predictor ──────────────────────────────────────────────────────

@router.post("/churn-predictor")
async def churn_predictor(request: Request):
    """AI predicts which subscribers are likely to churn and suggests retention."""
    await _require_admin(request)
    db = await _get_db()

    cached = await _get_cached(db, "churn_predictor")
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    thirty_days = (now - timedelta(days=30)).isoformat()

    total_subs = await db.users.count_documents({"subscription_plan": {"$nin": [None, "free", ""]}})
    churned = await db.users.count_documents({"subscription_status": "canceled"})
    active = await db.users.count_documents({"subscription_status": "active", "subscription_plan": {"$nin": [None, "free", ""]}})

    # Recent activity
    recent_active = await db.user_sessions.find(
        {"created_at": {"$gte": thirty_days}},
        {"_id": 0, "user_id": 1}
    ).to_list(10000)
    active_user_ids = set(s.get("user_id") for s in recent_active)

    # Get premium users with low activity
    premium_users = await db.users.find(
        {"subscription_plan": {"$nin": [None, "free", ""]}, "subscription_status": "active"},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1, "created_at": 1}
    ).to_list(500)

    at_risk = []
    for u in premium_users:
        if u.get("user_id") not in active_user_ids:
            at_risk.append({"email": u.get("email", ""), "plan": u.get("subscription_plan", ""), "user_id": u.get("user_id", "")})

    churn_rate = round(churned / max(total_subs + churned, 1) * 100, 1)

    prompt = f"""Analyze subscription churn data for an AI coaching platform and predict churn risks.

DATA:
- Total subscribers: {total_subs}
- Active subscribers: {active}
- Churned: {churned}
- Churn rate: {churn_rate}%
- Inactive premium users (no sessions in 30d): {len(at_risk)}
- At-risk users sample: {json.dumps(at_risk[:15], default=str)}

Return JSON:
{{
  "churn_risk_score": <0-100>,
  "predicted_churn_next_30d": <number>,
  "executive_summary": "<3-4 sentence churn analysis>",
  "risk_segments": [
    {{"segment": "<name>", "size": <count>, "churn_probability": "<X%>", "primary_reason": "<reason>"}}
  ],
  "retention_strategies": [
    {{"strategy": "<name>", "description": "<1-2 sentences>", "target_segment": "<segment>", "expected_retention_lift": "<+X%>", "priority": <1-5>}}
  ],
  "early_warning_signals": [
    {{"signal": "<what to watch for>", "threshold": "<when to act>", "action": "<what to do>"}}
  ]
}}

Return 3-4 risk_segments, 5-6 retention_strategies, 3-4 early_warning_signals."""

    try:
        result = await _call_gpt(prompt, "churn-predictor")
    except Exception as e:
        logger.error(f"Churn predictor AI failed: {e}")
        result = {
            "churn_risk_score": 0, "predicted_churn_next_30d": 0,
            "executive_summary": "AI analysis unavailable.",
            "risk_segments": [], "retention_strategies": [], "early_warning_signals": [],
        }

    record = await _save_cache(db, "churn_predictor", result)
    return {k: v for k, v in record.items() if k != "_id"}


# ── 7. Performance Forecaster ────────────────────────────────────────────────

@router.post("/performance-forecast")
async def performance_forecast(request: Request):
    """AI forecasts performance trends and predicts degradation."""
    await _require_admin(request)
    db = await _get_db()

    cached = await _get_cached(db, "performance_forecast")
    if cached:
        return cached

    perf_data = await db.page_performance_metrics.find(
        {}, {"_id": 0, "page": 1, "avg_load_ms": 1, "p95_load_ms": 1, "timestamp": 1}
    ).sort("timestamp", -1).to_list(500)

    # Group by page
    page_stats = {}
    for p in perf_data:
        pg = p.get("page", "unknown")
        page_stats.setdefault(pg, []).append({
            "avg_ms": p.get("avg_load_ms", 0),
            "p95_ms": p.get("p95_load_ms", 0),
            "ts": str(p.get("timestamp", ""))[:16]
        })

    # System metrics
    sys_metrics = await db.system_performance_history.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).to_list(50)

    prompt = f"""Analyze platform performance data and forecast potential degradation.

PAGE PERFORMANCE (last measurements per page):
{json.dumps({pg: stats[:5] for pg, stats in list(page_stats.items())[:10]}, default=str)}

SYSTEM METRICS (recent):
{json.dumps(sys_metrics[:10], default=str)}

Return JSON:
{{
  "performance_score": <0-100>,
  "forecast_summary": "<3-4 sentence performance forecast>",
  "degradation_risks": [
    {{"component": "<page or service>", "risk_level": "<high|medium|low>", "trend": "<degrading|stable|improving>", "predicted_impact": "<description>", "mitigation": "<action>"}}
  ],
  "optimization_opportunities": [
    {{"area": "<what to optimize>", "current_metric": "<current value>", "target_metric": "<target>", "approach": "<how to fix>", "priority": <1-5>}}
  ],
  "capacity_forecast": {{
    "current_load": "<description>",
    "projected_bottleneck": "<what will slow down first>",
    "timeline": "<when to expect issues>",
    "recommendation": "<what to do>"
  }}
}}

Return 4-6 degradation_risks and 4-6 optimization_opportunities."""

    try:
        result = await _call_gpt(prompt, "perf-forecast")
    except Exception as e:
        logger.error(f"Performance forecast AI failed: {e}")
        result = {
            "performance_score": 80, "forecast_summary": "AI analysis unavailable.",
            "degradation_risks": [], "optimization_opportunities": [],
            "capacity_forecast": {"current_load": "N/A", "projected_bottleneck": "N/A", "timeline": "N/A", "recommendation": "N/A"},
        }

    record = await _save_cache(db, "performance_forecast", result)
    return {k: v for k, v in record.items() if k != "_id"}


# ── 8. Fraud Risk Narrative ──────────────────────────────────────────────────

@router.post("/fraud-narrative")
async def fraud_narrative(request: Request):
    """AI generates a fraud risk assessment narrative."""
    await _require_admin(request)
    db = await _get_db()

    cached = await _get_cached(db, "fraud_narrative")
    if cached:
        return cached

    # Get latest fraud scan
    scan = await db.fraud_scans.find_one({}, {"_id": 0}, sort=[("scan_time", -1)])
    flagged = await db.fraud_flags.find({}, {"_id": 0}).to_list(100)

    # Security events
    now = datetime.now(timezone.utc)
    last_7d = (now - timedelta(days=7)).isoformat()
    events = await db.security_events.find(
        {"timestamp": {"$gte": last_7d}},
        {"_id": 0, "event_type": 1, "risk_level": 1}
    ).to_list(5000)

    event_summary = {}
    for e in events:
        et = e.get("event_type", "unknown")
        event_summary[et] = event_summary.get(et, 0) + 1

    total_users = await db.users.count_documents({})

    prompt = f"""Generate a fraud risk narrative for an AI coaching platform.

DATA:
- Latest scan: {json.dumps(scan, default=str) if scan else 'No scan data'}
- Flagged accounts: {len(flagged)}
- Security events (7d): {json.dumps(event_summary)}
- Total users: {total_users}

Return JSON:
{{
  "fraud_risk_score": <0-100>,
  "risk_level": "<minimal|low|moderate|elevated|high>",
  "narrative": "<5-6 sentence fraud risk story>",
  "risk_factors": [
    {{"factor": "<risk factor>", "severity": "<critical|high|medium|low>", "evidence": "<data point>", "mitigation": "<action>"}}
  ],
  "anomalies_detected": [
    {{"anomaly": "<what was found>", "significance": "<description>", "action_required": true|false}}
  ],
  "recommendations": [
    {{"recommendation": "<action>", "priority": <1-5>, "category": "<prevention|detection|response>"}}
  ]
}}

Return 3-5 risk_factors, 2-4 anomalies_detected, 3-5 recommendations."""

    try:
        result = await _call_gpt(prompt, "fraud-narrative")
    except Exception as e:
        logger.error(f"Fraud narrative AI failed: {e}")
        result = {
            "fraud_risk_score": 10, "risk_level": "low",
            "narrative": "AI analysis unavailable.",
            "risk_factors": [], "anomalies_detected": [], "recommendations": [],
        }

    record = await _save_cache(db, "fraud_narrative", result)
    return {k: v for k, v in record.items() if k != "_id"}


# ── Fetch latest cached insight (GET endpoints) ─────────────────────────────

@router.get("/latest/{insight_type}")
async def get_latest_insight(insight_type: str, request: Request):
    """Get the latest cached AI insight for a given type."""
    await _require_admin(request)
    db = await _get_db()

    valid_types = [
        "sla_predictor", "conversion_optimizer", "onboarding_coach",
        "newsletter_suggestions", "security_narrative", "churn_predictor",
        "performance_forecast", "fraud_narrative",
    ]
    if insight_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid insight type. Valid: {valid_types}")

    cached = await db.ai_panel_insights.find_one(
        {"cache_key": insight_type}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if cached:
        return cached
    return {"cache_key": insight_type, "status": "no_data", "message": "Run the analysis first."}


# ── Weekly AI Health Digest Email ────────────────────────────────────────────

INSIGHT_META = [
    {"key": "sla_predictor", "label": "SLA Breach Risk", "score_key": "risk_score", "invert": True, "icon": "timer"},
    {"key": "conversion_optimizer", "label": "Conversion Health", "score_key": "conversion_health", "invert": False, "icon": "funnel"},
    {"key": "onboarding_coach", "label": "Onboarding Health", "score_key": "onboarding_health", "invert": False, "icon": "rocket"},
    {"key": "newsletter_suggestions", "label": "Newsletter Health", "score_key": "newsletter_health", "invert": False, "icon": "newspaper"},
    {"key": "security_narrative", "label": "Security Score", "score_key": "security_score", "invert": False, "icon": "shield"},
    {"key": "churn_predictor", "label": "Churn Risk", "score_key": "churn_risk_score", "invert": True, "icon": "people"},
    {"key": "performance_forecast", "label": "Performance Score", "score_key": "performance_score", "invert": False, "icon": "speedometer"},
    {"key": "fraud_narrative", "label": "Fraud Risk", "score_key": "fraud_risk_score", "invert": True, "icon": "warning"},
]


@router.get("/health-digest/config")
async def get_health_digest_config(request: Request):
    """Get weekly AI health digest email configuration."""
    await _require_admin(request)
    db = await _get_db()
    config = await db.system_config.find_one({"key": "ai_health_digest"}, {"_id": 0})
    if not config:
        config = {"key": "ai_health_digest", "enabled": True, "day": "monday", "hour": 8}
    return {
        "enabled": config.get("enabled", True),
        "day": config.get("day", "monday"),
        "hour": config.get("hour", 8),
        "last_sent": config.get("last_sent"),
    }


@router.put("/health-digest/config")
async def update_health_digest_config(request: Request):
    """Update weekly AI health digest email settings."""
    await _require_admin(request)
    db = await _get_db()
    body = await request.json()
    enabled = body.get("enabled", True)
    day = body.get("day", "monday")
    valid_days = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    if day not in valid_days:
        raise HTTPException(status_code=400, detail="Invalid day")
    hour = max(0, min(23, int(body.get("hour", 8))))
    await db.system_config.update_one(
        {"key": "ai_health_digest"},
        {"$set": {"enabled": enabled, "day": day, "hour": hour, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "enabled": enabled, "day": day, "hour": hour}


@router.post("/health-digest/send-now")
async def send_health_digest_now(request: Request):
    """Manually trigger the AI Health Digest email."""
    await _require_admin(request)
    result = await generate_and_send_ai_health_digest(force=True)
    return result


async def generate_and_send_ai_health_digest(force: bool = False):
    """Generate and send the weekly AI Platform Health Digest email."""
    from routes.db import db
    from utils.email_service import send_email, render_email_header_panel, ops_alert_template_enforcer

    @ops_alert_template_enforcer("capacity", "capacity_ai_health_digest")
    async def _send_capacity_digest_email(**kwargs):
        return await send_email(**kwargs)

    config = await db.system_config.find_one({"key": "ai_health_digest"}, {"_id": 0})
    if not config:
        config = {"enabled": True}
    if not config.get("enabled", True) and not force:
        return {"sent": False, "reason": "AI health digest emails disabled"}

    now = datetime.now(timezone.utc)

    # Fetch all cached insights
    insights = {}
    for meta in INSIGHT_META:
        cached = await db.ai_panel_insights.find_one(
            {"cache_key": meta["key"]}, {"_id": 0}, sort=[("created_at", -1)]
        )
        if cached and not cached.get("status"):
            insights[meta["key"]] = cached

    if not insights:
        return {"sent": False, "reason": "No AI analyses available. Run analyses first."}

    # Fetch previous digest scores for trend comparison
    prev_digest = await db.ai_health_digest_history.find_one({}, {"_id": 0}, sort=[("sent_at", -1)])
    prev_scores = prev_digest.get("scores", {}) if prev_digest else {}

    # Calculate scores
    scores = {}
    health_scores = []
    for meta in INSIGHT_META:
        data = insights.get(meta["key"])
        if data:
            raw = data.get(meta["score_key"], 0)
            health = (100 - raw) if meta["invert"] else raw
            scores[meta["key"]] = {"raw": raw, "health": health, "label": meta["label"]}
            health_scores.append(health)

    platform_score = round(sum(health_scores) / len(health_scores)) if health_scores else 0
    platform_color = "#22c55e" if platform_score >= 70 else "#eab308" if platform_score >= 40 else "#ef4444"
    platform_label = "Healthy" if platform_score >= 70 else "Attention Needed" if platform_score >= 40 else "Critical"
    analyzed = len(health_scores)

    # Previous platform score for delta
    prev_platform = prev_digest.get("platform_score") if prev_digest else None
    delta_html = ""
    if prev_platform is not None:
        delta = platform_score - prev_platform
        delta_color = "#22c55e" if delta > 0 else "#ef4444" if delta < 0 else "#8B9DC3"
        delta_arrow = "+" if delta > 0 else ""
        delta_html = f'<div style="color:{delta_color};font-size:12px;font-weight:700;margin-top:2px;">{delta_arrow}{delta} vs last week</div>'

    # Build email HTML
    header = render_email_header_panel(
        title="Weekly AI Platform Health Digest",
        subtitle=f"Platform Score: {platform_score}/100 ({platform_label}) | {analyzed}/8 engines analyzed",
        variant="report",
        accent="#A855F7",
        meta_label="AI Engines",
        meta_value=f"{analyzed}/8",
    )

    # Score cards HTML
    cards_html = ""
    for meta in INSIGHT_META:
        sc = scores.get(meta["key"])
        if not sc:
            cards_html += f'''<td width="25%" style="padding:4px;">
                <div style="background:#1E293B;border-radius:12px;padding:12px;text-align:center;border:1px solid #334155;">
                    <div style="color:#8B9DC3;font-size:10px;font-weight:700;">{meta["label"]}</div>
                    <div style="color:#5B6F92;font-size:24px;font-weight:900;margin:4px 0;">--</div>
                    <div style="color:#5B6F92;font-size:10px;">Not analyzed</div>
                </div>
            </td>'''
            continue

        raw = sc["raw"]
        health = sc["health"]
        card_color = "#22c55e" if health >= 70 else "#eab308" if health >= 40 else "#ef4444"

        # Trend arrow
        prev_raw = prev_scores.get(meta["key"], {}).get("raw")
        trend_html = ""
        if prev_raw is not None:
            prev_health = (100 - prev_raw) if meta["invert"] else prev_raw
            diff = health - prev_health
            t_color = "#22c55e" if diff > 0 else "#ef4444" if diff < 0 else "#8B9DC3"
            t_arrow = "+" if diff > 0 else ""
            trend_html = f'<div style="color:{t_color};font-size:10px;font-weight:700;">{t_arrow}{diff}</div>'

        cards_html += f'''<td width="25%" style="padding:4px;">
            <div style="background:#1E293B;border-radius:12px;padding:12px;text-align:center;border:2px solid {card_color}30;">
                <div style="color:#8B9DC3;font-size:10px;font-weight:700;">{meta["label"]}</div>
                <div style="color:{card_color};font-size:24px;font-weight:900;margin:4px 0;">{raw}</div>
                {trend_html}
            </div>
        </td>'''

    # Wrap cards in 2 rows of 4
    cards_row1 = '<tr>' + ''.join(cards_html.split('</td>')[:4]) + '</td></tr>' if '</td>' in cards_html else ''
    cards_row2 = '<tr>' + ''.join(cards_html.split('</td>')[4:8]) + '</td></tr>' if cards_html.count('</td>') > 4 else ''

    # Collect top 3 action items across all insights
    all_actions = []
    for meta in INSIGHT_META:
        data = insights.get(meta["key"], {})
        for key in ["optimization_tips", "optimization_strategies", "retention_strategies", "ux_improvements",
                     "recommended_actions", "recommendations", "quick_wins"]:
            for item in (data.get(key) or [])[:2]:
                text = item.get("strategy") or item.get("action") or item.get("tip") or item.get("recommendation") or item.get("improvement") or ""
                impact = item.get("expected_lift") or item.get("expected_impact") or item.get("impact") or ""
                priority = item.get("priority", 5)
                if text:
                    all_actions.append({"text": text, "impact": impact, "priority": priority, "source": meta["label"]})

    all_actions.sort(key=lambda x: x.get("priority", 5))
    top_actions = all_actions[:3]

    actions_html = ""
    for i, a in enumerate(top_actions):
        pc = "#ef4444" if a["priority"] <= 2 else "#f97316" if a["priority"] <= 3 else "#3b82f6"
        actions_html += f'''<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #1E2D4A;">
            <div style="width:28px;height:28px;border-radius:14px;background:{pc}20;text-align:center;line-height:28px;color:{pc};font-weight:800;font-size:14px;flex-shrink:0;">{i+1}</div>
            <div><strong style="color:#E8ECF4;font-size:12px;">{a["text"]}</strong><br/>
            <span style="color:#A855F7;font-size:10px;font-weight:700;">Source: {a["source"]}</span>
            {f'<span style="color:#22c55e;font-size:10px;margin-left:8px;">{a["impact"]}</span>' if a["impact"] else ''}</div>
        </div>'''

    dashboard_url = f"{(os.environ.get('FRONTEND_BASE_URL') or '').rstrip('/')}/executive-dashboard"

    f"""{header}
<div style="background-color:#0F172A;padding:24px 28px;border-radius:0 0 20px 20px;">

  <!-- Platform Health Score -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
    <tr>
      <td width="40%" style="padding:6px;">
        <div style="background:#1E293B;border-radius:16px;padding:24px;text-align:center;border:3px solid {platform_color};">
          <div style="color:#8B9DC3;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">Platform Health Score</div>
          <div style="color:{platform_color};font-size:56px;font-weight:900;margin:8px 0;">{platform_score}</div>
          <div style="color:{platform_color};font-size:14px;font-weight:700;">{platform_label}</div>
          {delta_html}
        </div>
      </td>
      <td width="60%" style="padding:6px;vertical-align:top;">
        <div style="background:#1E293B;border-radius:16px;padding:20px;border:1px solid #334155;height:100%;">
          <div style="color:#A855F7;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">AI Engines Summary</div>
          <div style="color:#E8ECF4;font-size:13px;line-height:20px;margin-bottom:12px;">
            {analyzed} of 8 AI engines have been analyzed.
            {'All engines are producing live insights.' if analyzed == 8 else f'{8 - analyzed} engines have not been run yet.'}
          </div>
          <div style="color:#8B9DC3;font-size:11px;">
            Combined from: SLA, Conversion, Onboarding, Newsletter, Security, Churn, Performance, and Fraud analysis engines — all powered by GPT-4o.
          </div>
        </div>
      </td>
    </tr>
  </table>

  <!-- Score Grid (2 rows of 4) -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
    {cards_row1}
    {cards_row2}
  </table>

  <!-- Top 3 Actions -->
  <div style="background:#1E293B;border-radius:12px;padding:16px;border:1px solid #A855F720;margin-bottom:16px;">
    <div style="color:#A855F7;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Top 3 AI-Recommended Actions</div>
    {actions_html or '<div style="color:#8B9DC3;font-size:12px;">No actions recommended. All systems look healthy.</div>'}
  </div>

  <!-- CTA -->
  <div style="text-align:center;margin-top:24px;">
    <a href="{dashboard_url}" style="display:inline-block;background:#A855F7;color:#fff;font-size:14px;font-weight:700;text-decoration:none;padding:12px 28px;border-radius:10px;">Open AI Command Center</a>
  </div>
  <div style="color:#5B6F92;font-size:11px;text-align:center;margin-top:20px;">
    Powered by 8 GPT-4o AI Engines | RealAICoach Platform Intelligence<br/>
    <a href="{dashboard_url}" style="color:#A855F7;text-decoration:none;">Manage digest settings</a>
  </div>
</div>
<!-- BRANDED_FOOTER_V2 -->"""

    # Send to all admins
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "name": 1}).to_list(20)
    if not admins:
        return {"sent": False, "reason": "No admin users found"}

    sent_to = []
    for admin in admins:
        try:
            from utils.email_service import send_catalog_template

            # Build scores summary and actions for the v7 template
            scores_parts = []
            for key, s in scores.items():
                scores_parts.append(f"{s['label']}: {s['health']}/100")
            scores_summary = "; ".join(scores_parts[:8])

            # Extract top actions from insights
            action_parts = []
            for meta in INSIGHT_META:
                data = insights.get(meta["key"])
                if data:
                    for rec in (data.get("recommendations") or data.get("actions") or [])[:1]:
                        if isinstance(rec, dict):
                            action_parts.append(rec.get("action", rec.get("title", "")))
                        elif isinstance(rec, str):
                            action_parts.append(rec)
            top_actions_str = "; ".join(a for a in action_parts[:3] if a) or "All systems healthy"

            delta_str = ""
            if prev_platform is not None:
                d = platform_score - prev_platform
                delta_str = f"{'+' if d > 0 else ''}{d} vs last week"

            await send_catalog_template(
                recipient_email=admin["email"],
                template_key="ai_health_digest_v7",
                recipient_name=admin.get("name", ""),
                platform_score=platform_score,
                platform_label=platform_label,
                analyzed=analyzed,
                scores_summary=scores_summary,
                top_actions=top_actions_str,
                delta=delta_str,
            )
            sent_to.append(admin["email"])
        except Exception as e:
            logger.error(f"Failed to send AI health digest to {admin['email']}: {e}")

    # Save history for trend comparison
    await db.ai_health_digest_history.insert_one({
        "sent_at": now.isoformat(),
        "platform_score": platform_score,
        "scores": scores,
        "recipients": sent_to,
    })

    await db.system_config.update_one(
        {"key": "ai_health_digest"},
        {"$set": {"last_sent": now.isoformat()}},
        upsert=True,
    )

    logger.info(f"AI health digest sent to {len(sent_to)} admins, platform score: {platform_score}")
    return {"sent": True, "recipients": sent_to, "platform_score": platform_score, "status": platform_label}
