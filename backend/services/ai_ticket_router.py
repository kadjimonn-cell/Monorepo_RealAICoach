"""
AI-powered Ticket Router — classifies tickets by topic & priority,
suggests responses, and routes to the right team member.
Uses GPT-4o via Emergent LLM Key.
"""

import os
import json
import logging
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TOPICS = ["billing", "technical", "account", "feature_request", "bug_report", "general"]
PRIORITIES = ["critical", "high", "medium", "low"]
MOODS = ["happy", "neutral", "confused", "frustrated", "angry", "desperate", "disappointed"]

SYSTEM_PROMPT = """You are an expert support ticket classifier for RealAICoach, an enterprise AI coaching platform.

Given a support ticket (subject + message), return a JSON object with:
1. "topic": one of {topics}
2. "priority": one of {priorities}
3. "confidence": float 0.0-1.0 for your classification confidence
4. "reasoning": 1-sentence explanation of why you chose this topic and priority
5. "suggested_response": a professional, empathetic draft reply (2-4 sentences) the support agent can send to the user. Address the user by name if available. Reference their specific issue.
6. "tags": list of 1-3 short keyword tags relevant to the ticket
7. "sentiment": object with:
   - "mood": one of {moods} — the dominant emotional tone of the customer
   - "frustration_level": integer 1-10 (1=calm, 5=mildly frustrated, 8=very frustrated, 10=furious)
   - "tone_indicators": list of 1-3 specific phrases or signals from the ticket that reveal the customer's emotional state
   - "auto_escalate": boolean — true if frustration_level >= 7 or mood is "angry" or "desperate"

Rules:
- "critical" priority: service outage, data loss, security breach, payment failures blocking business
- "high" priority: feature broken, login issues, urgent billing disputes
- "medium" priority: general questions, minor bugs, feature requests
- "low" priority: feedback, suggestions, general inquiries
- For "suggested_response": be warm, professional, and specific to their issue. Do NOT use generic responses.
- Sentiment detection: look for ALL CAPS, exclamation marks, threatening language, urgency words, profanity, repeated complaints, mention of switching to competitors, expressions of helplessness

Return ONLY valid JSON, no markdown fences.""".format(
    topics=", ".join(TOPICS),
    priorities=", ".join(PRIORITIES),
    moods=", ".join(MOODS),
)


async def classify_ticket(subject: str, message: str, user_name: str = "User") -> dict:
    """Classify a ticket using GPT-4o and return structured results."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        api_key = os.environ.get("EMERGENT_LLM_KEY", "")
        if not api_key:
            logger.warning("EMERGENT_LLM_KEY not set, skipping AI classification")
            return _fallback_classification(subject, message)

        chat = LlmChat(
            api_key=api_key,
            session_id=f"ticket-classify-{uuid.uuid4().hex[:8]}",
            system_message=SYSTEM_PROMPT,
        )
        chat.with_model("openai", "gpt-4o")

        prompt = f"Classify this support ticket:\n\nUser Name: {user_name}\nSubject: {subject}\nMessage: {message}"
        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)

        # Parse JSON from response
        result = _parse_ai_response(response)
        result["classified_by"] = "ai"
        result["model"] = "gpt-4o"
        result["classified_at"] = datetime.now(timezone.utc).isoformat()
        return result

    except Exception as e:
        logger.error(f"AI ticket classification failed: {e}")
        return _fallback_classification(subject, message)


def _parse_ai_response(response: str) -> dict:
    """Parse the AI response, handling potential JSON formatting issues."""
    text = response.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:]

    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
        else:
            raise ValueError(f"No JSON found in AI response: {text[:200]}")

    # Validate and sanitize
    topic = data.get("topic", "general")
    if topic not in TOPICS:
        topic = "general"
    priority = data.get("priority", "medium")
    if priority not in PRIORITIES:
        priority = "medium"

    return {
        "topic": topic,
        "priority": priority,
        "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
        "reasoning": str(data.get("reasoning", ""))[:500],
        "suggested_response": str(data.get("suggested_response", ""))[:2000],
        "tags": [str(t)[:30] for t in (data.get("tags") or [])[:5]],
        "sentiment": _parse_sentiment(data.get("sentiment", {})),
    }


def _parse_sentiment(raw: dict) -> dict:
    """Validate and sanitize sentiment data."""
    if not isinstance(raw, dict):
        return {"mood": "neutral", "frustration_level": 3, "tone_indicators": [], "auto_escalate": False}
    mood = str(raw.get("mood", "neutral")).lower()
    # Map common AI-returned moods to our defined set
    mood_aliases = {
        "furious": "angry",
        "livid": "angry",
        "outraged": "angry",
        "irate": "angry",
        "upset": "frustrated",
        "annoyed": "frustrated",
        "irritated": "frustrated",
        "anxious": "confused",
        "worried": "confused",
        "concerned": "confused",
        "sad": "disappointed",
        "unhappy": "disappointed",
        "dissatisfied": "disappointed",
        "helpless": "desperate",
        "panicked": "desperate",
        "hopeless": "desperate",
        "satisfied": "happy",
        "grateful": "happy",
        "pleased": "happy",
    }
    mood = mood_aliases.get(mood, mood)
    if mood not in MOODS:
        mood = "neutral"
    frustration = max(1, min(10, int(raw.get("frustration_level", 3))))
    auto_escalate = bool(raw.get("auto_escalate", False)) or frustration >= 7 or mood in ("angry", "desperate")
    return {
        "mood": mood,
        "frustration_level": frustration,
        "tone_indicators": [str(t)[:100] for t in (raw.get("tone_indicators") or [])[:3]],
        "auto_escalate": auto_escalate,
    }


def _fallback_classification(subject: str, message: str) -> dict:
    """Keyword-based fallback when AI is unavailable."""
    text = f"{subject} {message}".lower()

    topic = "general"
    priority = "medium"

    if any(w in text for w in ["pay", "bill", "invoice", "charge", "refund", "subscription", "plan", "price"]):
        topic = "billing"
    elif any(w in text for w in ["bug", "crash", "error", "broken", "not working", "fail"]):
        topic = "bug_report"
    elif any(w in text for w in ["feature", "request", "suggest", "would be nice", "wish"]):
        topic = "feature_request"
    elif any(w in text for w in ["login", "password", "account", "profile", "email", "2fa", "access"]):
        topic = "account"
    elif any(w in text for w in ["api", "integration", "deploy", "server", "database", "code"]):
        topic = "technical"

    if any(w in text for w in ["urgent", "critical", "emergency", "outage", "down", "data loss", "security"]):
        priority = "critical"
    elif any(w in text for w in ["important", "asap", "broken", "can't login", "blocked"]):
        priority = "high"
    elif any(w in text for w in ["minor", "suggestion", "feedback", "question"]):
        priority = "low"

    # Sentiment fallback
    frustration = 3
    mood = "neutral"
    indicators = []
    if any(
        w in text
        for w in ["!!!", "urgent", "asap", "frustrated", "angry", "furious", "terrible", "worst", "unacceptable"]
    ):
        frustration = 7
        mood = "frustrated"
        indicators = ["urgency language detected"]
    elif any(w in text for w in ["please help", "desperate", "can't", "unable", "stuck"]):
        frustration = 5
        mood = "confused"
        indicators = ["helplessness expressions"]

    return {
        "topic": topic,
        "priority": priority,
        "confidence": 0.3,
        "reasoning": "Classified by keyword matching (AI unavailable)",
        "suggested_response": "",
        "tags": [topic],
        "sentiment": {
            "mood": mood,
            "frustration_level": frustration,
            "tone_indicators": indicators,
            "auto_escalate": frustration >= 7 or mood in ("angry", "desperate"),
        },
        "classified_by": "fallback",
        "model": "keyword",
        "classified_at": datetime.now(timezone.utc).isoformat(),
    }


async def route_ticket(topic: str, routing_rules: dict) -> dict:
    """Determine where to route a ticket based on topic and configured rules."""
    default_route = {
        "assigned_to": "support@realaicoach.app",
        "team": "Support Team",
        "escalation_contact": "",
    }

    if not routing_rules:
        return default_route

    rule = routing_rules.get(topic, routing_rules.get("general", {}))
    return {
        "assigned_to": rule.get("assigned_to", default_route["assigned_to"]),
        "team": rule.get("team", default_route["team"]),
        "escalation_contact": rule.get("escalation_contact", ""),
    }
