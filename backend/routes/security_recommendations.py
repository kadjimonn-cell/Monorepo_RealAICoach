"""AI-Powered Security Recommendations — analyze SIEM/UBA data and suggest improvements."""

from fastapi import APIRouter, Query, Request
from datetime import datetime, timezone, timedelta
from routes.db import db, require_admin, EMERGENT_LLM_KEY
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/security-recommendations", tags=["Security Recommendations"])


async def _gather_security_context(days: int = 7) -> dict:
    """Gather recent security and UBA data for AI analysis."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).isoformat()

    # SIEM metrics
    total_events = await db.security_events.count_documents({"timestamp": {"$gte": cutoff}})
    critical_events = await db.security_events.count_documents(
        {"timestamp": {"$gte": cutoff}, "risk_level": "critical"}
    )
    high_events = await db.security_events.count_documents({"timestamp": {"$gte": cutoff}, "risk_level": "high"})

    # Event type breakdown
    event_types = []
    async for doc in db.security_events.aggregate(
        [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
    ):
        event_types.append({"type": doc["_id"], "count": doc["count"]})

    # Active alerts
    active_alerts = await db.siem_triggered_alerts.count_documents({"status": "active"})

    # UBA metrics
    total_users = await db.users.count_documents({})
    mfa_enabled = await db.user_mfa.count_documents({"enabled": True})

    # Failed logins
    failed_logins = await db.security_events.count_documents(
        {"timestamp": {"$gte": cutoff}, "event_type": "login_failed"}
    )

    # Suspicious IPs (multiple failed logins)
    suspicious_ips = []
    async for doc in db.security_events.aggregate(
        [
            {"$match": {"timestamp": {"$gte": cutoff}, "event_type": "login_failed"}},
            {"$group": {"_id": "$ip_address", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gte": 3}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
    ):
        suspicious_ips.append({"ip": doc["_id"], "attempts": doc["count"]})

    return {
        "period_days": days,
        "total_security_events": total_events,
        "critical_events": critical_events,
        "high_events": high_events,
        "event_types": event_types,
        "active_alerts": active_alerts,
        "total_users": total_users,
        "mfa_adoption": round(mfa_enabled / max(total_users, 1) * 100, 1),
        "failed_logins": failed_logins,
        "suspicious_ips": suspicious_ips,
    }


@router.get("/analyze")
async def get_ai_recommendations(req: Request, days: int = Query(7, ge=1, le=30)):
    """Generate AI-powered security recommendations based on recent data."""
    await require_admin(req)

    context = await _gather_security_context(days)

    # Check for cached recent analysis (within last hour)
    cache = await db.security_recommendations_cache.find_one(
        {"created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}},
        {"_id": 0},
    )
    if cache:
        return cache

    recommendations = []
    risk_score = 100  # Start at 100 and deduct

    # Rule-based analysis (fast, always available)
    if context["mfa_adoption"] < 50:
        deduction = min(20, int((50 - context["mfa_adoption"]) / 2.5))
        risk_score -= deduction
        recommendations.append(
            {
                "id": "mfa_adoption",
                "severity": "high",
                "category": "Authentication",
                "title": "Low MFA Adoption Rate",
                "description": f"Only {context['mfa_adoption']}% of users have MFA enabled. This significantly increases the risk of account compromise.",
                "action": "Enforce MFA for all admin accounts and encourage adoption for regular users via in-app prompts.",
                "impact": "high",
            }
        )

    if context["failed_logins"] > 50:
        risk_score -= 15
        recommendations.append(
            {
                "id": "brute_force",
                "severity": "high",
                "category": "Threat Detection",
                "title": "High Volume of Failed Login Attempts",
                "description": f"{context['failed_logins']} failed login attempts detected in the last {days} days. This may indicate brute-force attacks.",
                "action": "Review IP blocklist, consider implementing progressive delays on login failures, and verify rate limiting is active.",
                "impact": "high",
            }
        )

    if context["critical_events"] > 0:
        risk_score -= min(25, context["critical_events"] * 5)
        recommendations.append(
            {
                "id": "critical_events",
                "severity": "critical",
                "category": "Incident Response",
                "title": f"{context['critical_events']} Critical Security Events",
                "description": f"There are {context['critical_events']} critical security events in the last {days} days that require immediate investigation.",
                "action": "Review the SIEM critical events log immediately and assess if any data breach or unauthorized access occurred.",
                "impact": "critical",
            }
        )

    if context["active_alerts"] > 5:
        risk_score -= 10
        recommendations.append(
            {
                "id": "unresolved_alerts",
                "severity": "medium",
                "category": "Alert Management",
                "title": f"{context['active_alerts']} Unresolved Security Alerts",
                "description": "Multiple security alerts remain unresolved. Delayed response increases exposure window.",
                "action": "Assign alerts to security team members and establish SLAs for alert resolution.",
                "impact": "medium",
            }
        )

    if len(context["suspicious_ips"]) > 0:
        risk_score -= 10
        ip_list = ", ".join([f"{ip['ip']} ({ip['attempts']}x)" for ip in context["suspicious_ips"][:3]])
        recommendations.append(
            {
                "id": "suspicious_ips",
                "severity": "high",
                "category": "Network Security",
                "title": "Suspicious IP Activity Detected",
                "description": f"Multiple failed login attempts from: {ip_list}",
                "action": "Consider blocking these IPs or adding them to the monitoring watchlist.",
                "impact": "high",
            }
        )

    # General best practices
    if context["total_security_events"] == 0:
        recommendations.append(
            {
                "id": "no_monitoring",
                "severity": "medium",
                "category": "Monitoring",
                "title": "Limited Security Event Data",
                "description": "No security events recorded in the analysis period. Ensure security event logging is properly configured.",
                "action": "Verify that all authentication, access, and system events are being properly logged.",
                "impact": "medium",
            }
        )

    # Try AI-enhanced analysis if LLM key available
    ai_insights = None
    if EMERGENT_LLM_KEY:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage

            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"security-rec-{uuid.uuid4().hex[:8]}",
                system_message="You are a cybersecurity analyst. Analyze the security data and provide 2-3 concise, actionable insights. Return as JSON array with fields: insight (string), priority (high/medium/low), action (string). No markdown.",
            ).with_model("openai", "gpt-4o")

            prompt = f"Security data for last {days} days: {context}. Provide security insights."
            resp = await chat.send_message(UserMessage(text=prompt))
            text = resp.text if hasattr(resp, "text") else str(resp)
            clean = text.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            import json

            ai_insights = json.loads(clean.strip())
        except Exception as e:
            logger.warning(f"AI analysis failed (non-blocking): {e}")

    risk_score = max(0, risk_score)
    grade = (
        "A"
        if risk_score >= 90
        else "B"
        if risk_score >= 75
        else "C"
        if risk_score >= 60
        else "D"
        if risk_score >= 40
        else "F"
    )

    result = {
        "risk_score": risk_score,
        "grade": grade,
        "recommendations": recommendations,
        "ai_insights": ai_insights,
        "context_summary": {
            "period_days": days,
            "total_events": context["total_security_events"],
            "critical_events": context["critical_events"],
            "mfa_adoption": context["mfa_adoption"],
            "active_alerts": context["active_alerts"],
        },
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache the result
    await db.security_recommendations_cache.delete_many({})
    await db.security_recommendations_cache.insert_one({**result})
    result.pop("_id", None)

    return result


@router.get("/history")
async def recommendation_history(req: Request, limit: int = Query(10, ge=1, le=50)):
    """Get history of past security analyses."""
    await require_admin(req)
    history = []
    async for doc in db.security_recommendations_history.find({}, {"_id": 0}).sort("analyzed_at", -1).limit(limit):
        history.append(doc)
    return {"history": history}
