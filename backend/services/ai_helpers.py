"""Shared AI helper functions and services used across multiple route modules."""

import os
import json
import uuid
import logging
from typing import Dict, Any
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


async def ai_generate(system_message: str, prompt: str, session_prefix: str = "ai") -> str:
    """Generic AI text generation helper."""
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"{session_prefix}-{uuid.uuid4()}",
        system_message=system_message,
    ).with_model("openai", "gpt-4o")
    response = await chat.send_message(UserMessage(text=prompt))
    return response.strip()


async def ai_generate_json(system_message: str, prompt: str, session_prefix: str = "ai") -> Dict[str, Any]:
    """AI generation that returns parsed JSON."""
    response = await ai_generate(system_message, prompt, session_prefix)
    text = response
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


async def analyze_message_with_ai(message: str, context: str, scenario: dict) -> Dict[str, Any]:
    """Analyze a user message for communication skills."""
    try:
        system_msg = """You are an expert communication coach analyzing messages for emotional intelligence and communication skills.

Analyze the user's message and provide scores (0-100) and brief feedback for:
- empathy: How well they show understanding of others' feelings
- clarity: How clear and understandable their message is
- confidence: How confident and assertive they sound
- active_listening: How well they reference and respond to what was said
- emotional_intelligence: Overall EQ in the response

Respond ONLY with valid JSON in this exact format:
{
    "scores": {"empathy": 75, "clarity": 80, "confidence": 70, "active_listening": 65, "emotional_intelligence": 72},
    "overall_score": 72,
    "tone": "friendly and open",
    "strengths": ["Shows genuine interest", "Clear communication"],
    "suggestions": ["Could ask more follow-up questions"]
}"""
        prompt = f"""Context: {context}
Scenario: {scenario.get("title", "")} - {scenario.get("description", "")}
User's message: "{message}"

Analyze this message for communication quality."""
        return await ai_generate_json(system_msg, prompt, "analyzer")
    except Exception as e:
        logger.error(f"Error analyzing message: {e}")
        return {
            "scores": {
                "empathy": 70,
                "clarity": 70,
                "confidence": 70,
                "active_listening": 70,
                "emotional_intelligence": 70,
            },
            "overall_score": 70,
            "tone": "neutral",
            "strengths": ["Good effort"],
            "suggestions": ["Keep practicing"],
        }


async def get_ai_response(conversation_id: str, messages: list, user_message: str, scenario: dict) -> str:
    """Get an AI response in a practice conversation."""
    try:
        history = "\n".join(
            [
                f"{'User' if m.get('role') == 'user' else scenario['persona_name']}: {m.get('content', '')}"
                for m in messages[-10:]
            ]
        )
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"convo-{conversation_id}",
            system_message=f"""You are {scenario["persona_name"]}, {scenario["persona_description"]}

Your personality: {scenario["persona_personality"]}

This is a practice conversation for the user to improve their social skills. Stay in character as {scenario["persona_name"]} and respond naturally.

Guidelines:
- Be realistic and natural in your responses
- React appropriately to their communication style
- Keep responses concise (2-4 sentences typically)
- Never break character""",
        ).with_model("openai", "gpt-4o")

        prompt = f"""Previous conversation:
{history}

User just said: "{user_message}"

Respond as {scenario["persona_name"]}:"""
        response = await chat.send_message(UserMessage(text=prompt))
        return response.strip()
    except Exception as e:
        logger.error(f"Error getting AI response: {e}")
        return "I'm sorry, I got distracted for a moment. Could you repeat that?"
