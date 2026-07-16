"""AI-Powered Auto-Remediation Service — Uses GPT-4o to diagnose issues and generate multi-step fix plans.
Supports single-service and multi-service cascading failure analysis."""
import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def ai_diagnose_and_fix(rule: dict, metric_value: float, db, related_alerts: list = None) -> dict:
    """Use GPT-4o to diagnose a triggered alert and generate a remediation plan.
    Supports multi-service cascading failure analysis when related_alerts are provided."""
    try:
        from emergentintegrations.llm import chat, ChatMessage

        metric = rule.get("metric", "unknown")
        threshold = rule.get("threshold", 0)
        condition = rule.get("condition", "gt")
        action = rule.get("action", "alert")
        rule_name = rule.get("name", "Unknown Rule")

        # Build context for multi-service analysis
        multi_service_context = ""
        if related_alerts:
            multi_service_context = "\n\nRelated active alerts (potential cascading failure):\n"
            for alert in related_alerts[:5]:
                multi_service_context += f"- {alert.get('rule_name', 'Unknown')}: {alert.get('metric', '?')} = {alert.get('metric_value', '?')} (triggered {alert.get('triggered_at', 'recently')})\n"
            multi_service_context += "\nAnalyze whether these alerts are related (cascading failure) and identify the root service causing the chain.\n"

        context_msg = (
            f"System alert triggered:\n"
            f"- Rule: {rule_name}\n"
            f"- Metric: {metric} = {metric_value}\n"
            f"- Condition: {condition} {threshold}\n"
            f"- Configured action: {action}\n"
            f"{multi_service_context}\n"
            f"As a DevOps AI, analyze this alert and provide:\n"
            f"1. Root cause diagnosis (what likely caused this)\n"
            f"2. Immediate fix steps (2-3 concrete actions, ordered by priority)\n"
            f"3. Prevention strategy (how to prevent recurrence)\n"
            f"4. Risk assessment (low/medium/high/critical)\n"
            f"5. Affected services (list all services that may be impacted)\n"
            f"6. Cascading risk (probability that this will affect other services, 0-100)\n"
            f"7. Estimated recovery time (in minutes)\n\n"
            f"Respond in valid JSON with keys: diagnosis, immediate_steps (array), prevention, risk_level, affected_services (array), cascading_risk_percent, estimated_recovery_minutes, confidence_percent"
        )

        import os
        api_key = os.environ.get("EMERGENT_LLM_KEY", "")

        response = await chat(
            api_key=api_key,
            model="gpt-4o",
            messages=[
                ChatMessage(role="system", content="You are an expert DevOps AI that diagnoses system alerts, identifies cascading failures across services, and generates remediation plans. Always respond with valid JSON."),
                ChatMessage(role="user", content=context_msg),
            ],
            temperature=0.3,
        )

        content = response.message
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            plan = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            plan = {
                "diagnosis": content[:500],
                "immediate_steps": ["Review system metrics", "Check service logs", "Restart if needed"],
                "prevention": "Set up proactive monitoring",
                "risk_level": "medium",
                "affected_services": [metric],
                "cascading_risk_percent": 30,
                "estimated_recovery_minutes": 15,
                "confidence_percent": 60,
            }

        # Store remediation record
        remediation_doc = {
            "rule_name": rule_name,
            "metric": metric,
            "metric_value": metric_value,
            "threshold": threshold,
            "diagnosis": plan.get("diagnosis", ""),
            "immediate_steps": plan.get("immediate_steps", []),
            "prevention": plan.get("prevention", ""),
            "risk_level": plan.get("risk_level", "medium"),
            "affected_services": plan.get("affected_services", []),
            "cascading_risk_percent": plan.get("cascading_risk_percent", 0),
            "estimated_recovery_minutes": plan.get("estimated_recovery_minutes", 15),
            "confidence": plan.get("confidence_percent", 0),
            "is_multi_service": bool(related_alerts),
            "related_alerts_count": len(related_alerts) if related_alerts else 0,
            "model": "gpt-4o",
            "status": "generated",
            "created_at": datetime.now(timezone.utc),
        }
        await db.ai_remediations.insert_one(remediation_doc)
        remediation_doc.pop("_id", None)
        if hasattr(remediation_doc.get("created_at"), "isoformat"):
            remediation_doc["created_at"] = remediation_doc["created_at"].isoformat()

        # Execute safe fixes based on the plan
        fix_description = await _execute_safe_fixes(plan, rule, db)

        return {
            "success": True,
            "fix_description": fix_description,
            "plan": plan,
            "remediation": remediation_doc,
        }

    except Exception as e:
        logger.error(f"AI remediation failed: {e}")
        return {
            "success": False,
            "fix_description": f"AI diagnosis failed: {str(e)[:100]}. Falling back to standard fix.",
            "plan": None,
        }


async def _execute_safe_fixes(plan: dict, rule: dict, db) -> str:
    """Execute safe automated fixes based on the AI's remediation plan."""
    action = rule.get("action", "alert")
    metric = rule.get("metric", "")
    fixes_applied = []

    risk_level = plan.get("risk_level", "medium")

    # Only auto-execute fixes for low and medium risk
    if risk_level in ("low", "medium"):
        if action == "clear_cache" or "cache" in str(plan.get("immediate_steps", [])).lower():
            try:
                deleted = await db.session_cache.delete_many(
                    {"expires_at": {"$lt": datetime.now(timezone.utc)}}
                )
                fixes_applied.append(f"Cleared {deleted.deleted_count} expired cache entries")
            except Exception as e:
                fixes_applied.append(f"Cache clear attempted (error: {str(e)[:60]})")

        if action == "restart" or "restart" in str(plan.get("immediate_steps", [])).lower():
            if "db" in metric.lower():
                try:
                    await db.command("ping")
                    fixes_applied.append("DB connection verified healthy")
                except Exception:
                    fixes_applied.append("DB connection issue - escalated to ops team")
            else:
                try:
                    from datetime import timedelta
                    deleted = await db.stale_sessions.delete_many(
                        {"last_active": {"$lt": datetime.now(timezone.utc) - timedelta(hours=24)}}
                    )
                    fixes_applied.append(f"Cleaned {deleted.deleted_count} stale sessions")
                except Exception as e:
                    fixes_applied.append(f"Session cleanup attempted (error: {str(e)[:60]})")

        if "scale" in action or "scale" in str(plan.get("immediate_steps", [])).lower():
            fixes_applied.append("Scale-up recommendation logged for infrastructure team")

    else:
        fixes_applied.append(f"High-risk alert ({risk_level}) — manual review required. AI diagnosis available.")

    if not fixes_applied:
        fixes_applied.append("Alert notification sent with AI diagnosis attached")

    return " | ".join(fixes_applied)
