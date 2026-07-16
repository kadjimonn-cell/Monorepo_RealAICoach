"""LLM-Powered AI Recommendations — Uses GPT-4o to generate contextual platform recommendations.

Endpoints:
- POST /api/admin/ai-insights/generate-recommendations — Generate AI recommendations from platform data
"""

import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


async def generate_llm_recommendations(db) -> dict:
    """Use GPT-4o to generate contextual platform recommendations based on real metrics."""
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY not configured", "recommendations": []}

    now = datetime.now(timezone.utc)

    # Gather platform data
    total_users = await db.users.count_documents({})
    active_7d = await db.users.count_documents({"last_login": {"$gte": now - timedelta(days=7)}})
    active_30d = await db.users.count_documents({"last_login": {"$gte": now - timedelta(days=30)}})
    total_features = await db.feature_registry.count_documents({"enabled": True})
    disabled_features = await db.feature_registry.count_documents({"enabled": False})
    open_tickets = await db.support_tickets.count_documents({"status": {"$in": ["open", "pending"]}})
    total_tickets = await db.support_tickets.count_documents({})
    total_incidents = await db.automation_incidents.count_documents({})
    open_incidents = await db.automation_incidents.count_documents({"status": "open"})
    push_subs = await db.push_subscriptions.count_documents({"active": True})

    engagement_rate = round((active_7d / max(total_users, 1)) * 100, 1)
    retention_rate = round((active_30d / max(total_users, 1)) * 100, 1)
    ticket_ratio = round((open_tickets / max(total_tickets, 1)) * 100, 1)

    platform_context = f"""
Platform: RealAICoach — AI-powered coaching platform
Current Metrics (as of {now.strftime('%Y-%m-%d %H:%M UTC')}):
- Total Users: {total_users}
- Active Users (7d): {active_7d} ({engagement_rate}% engagement)
- Active Users (30d): {active_30d} ({retention_rate}% retention)
- Features Enabled: {total_features} (Disabled: {disabled_features})
- Support Tickets: {open_tickets} open / {total_tickets} total ({ticket_ratio}% open rate)
- Automation Incidents: {open_incidents} open / {total_incidents} total
- Push Notification Subscribers: {push_subs}
"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=api_key,
            session_id=f"ai-recs-{now.strftime('%Y%m%d%H%M')}",
            system_message=(
                "You are an expert SaaS growth strategist and platform optimization advisor. "
                "Analyze the provided platform metrics and generate 5-7 specific, actionable recommendations. "
                "Each recommendation should have: category (Growth/Engagement/Product/Support/Performance/Security/Revenue), "
                "priority (critical/high/medium/low), title, description (2-3 sentences max), impact estimate, and a concrete action step. "
                "Output ONLY valid JSON array. No markdown, no code blocks, no explanation outside the JSON."
            ),
        ).with_model("openai", "gpt-4o")

        prompt = f"""{platform_context}

Generate 5-7 actionable recommendations as a JSON array. Each object must have:
{{"category": "string", "priority": "string", "title": "string", "description": "string", "impact": "string", "action": "string"}}

Output ONLY the JSON array, nothing else."""

        response = await chat.send_message(UserMessage(text=prompt))

        # Parse the JSON response
        import json
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()

        recs = json.loads(clean)

        # Add IDs
        for i, rec in enumerate(recs):
            rec["id"] = f"llm_rec_{i}"
            rec["generated_by"] = "gpt-4o"
            rec["generated_at"] = now.isoformat()

        return {
            "recommendations": recs,
            "model": "gpt-4o",
            "generated_at": now.isoformat(),
            "context_summary": f"{total_users} users, {engagement_rate}% engagement, {total_features} features",
        }

    except Exception as e:
        logger.error(f"LLM recommendation generation failed: {e}")
        return {
            "error": str(e)[:200],
            "recommendations": [],
            "model": "gpt-4o",
            "generated_at": now.isoformat(),
        }
