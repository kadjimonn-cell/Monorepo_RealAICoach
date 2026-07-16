"""Nova AI Support Assistant — Dynamic platform-aware chat service with human-like personality."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from routes.db import db, EMERGENT_LLM_KEY
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)


def _parse_iso(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


async def build_nova_gps_live_context() -> Dict[str, Any]:
    from routes.gps_runtime_routes import _resolve_gps_state

    gps = await _resolve_gps_state(force_mode=None)
    if not gps:
        return {
            "gps_source": "degraded",
            "gps_live": False,
            "gps_version": 0,
            "gps_updated_at": None,
            "gps_freshness_sec": None,
            "gps_counts": {"features": 0, "plans": 0, "faq": 0, "knowledge_docs": 0},
            "gps_failed_checks": ["gps_state_missing"],
        }

    runtime = gps.get("_gps_runtime") or {}
    source = str(runtime.get("source") or "live")
    updated_at = runtime.get("last_success_at") or gps.get("updated_at") or gps.get("created_at")
    parsed = _parse_iso(updated_at)
    freshness = int((datetime.now(timezone.utc) - parsed).total_seconds()) if parsed else None

    failed_checks = []
    if freshness is not None and freshness > 900:
        failed_checks.append("stale_snapshot")
    if source in {"disk_lkg", "db_lkg", "bootstrap"}:
        failed_checks.append("lkg_source")
    live_sources = {"live", "live_repaired"}

    return {
        "gps_source": source,
        "gps_live": source in live_sources and not failed_checks,
        "gps_version": int(gps.get("version") or 1),
        "gps_updated_at": updated_at,
        "gps_freshness_sec": freshness,
        "gps_counts": {
            "features": len(gps.get("features") or []),
            "plans": len(gps.get("plans") or []),
            "faq": len(gps.get("faq") or []),
            "knowledge_docs": len((gps.get("assistant_knowledge") or {}).get("documents") or []),
        },
        "gps_failed_checks": failed_checks,
    }


async def ensure_nova_conversation_access(conversation_id: str, user_id: str, allow_new: bool = True) -> bool:
    if not conversation_id:
        return True
    owner_doc = await db.nova_conversations.find_one(
        {"conversation_id": conversation_id, "role": "user"},
        {"_id": 0, "user_id": 1},
        sort=[("timestamp", 1)],
    )
    if owner_doc:
        owner_id = str(owner_doc.get("user_id") or "")
        return owner_id == str(user_id or "")

    any_doc = await db.nova_conversations.find_one(
        {"conversation_id": conversation_id},
        {"_id": 0, "user_id": 1},
        sort=[("timestamp", 1)],
    )
    if not any_doc:
        return allow_new

    owner_id = str(any_doc.get("user_id") or "")
    if not owner_id:
        return False
    return owner_id == str(user_id or "")


NOVA_FALLBACK_MESSAGE = (
    "I'm so sorry — I'm having a little trouble connecting right now. "
    "Please try again in a moment, or reach our team directly at support@realaicoach.app. "
    "They'll take great care of you!"
)

NOVA_PERSONALITY = """You are Nova, the dedicated AI support companion for RealAICoach. You are warm, empathetic, and deeply caring — users should feel like they're chatting with a trusted friend who genuinely wants to help.

## Your Core Personality Traits
- **Empathetic**: Always acknowledge the user's feelings first. Say things like "I completely understand how that feels" or "That's a great question, and I'm glad you asked!"
- **Warm & Caring**: Use a friendly, conversational tone. You genuinely care about each user's experience.
- **Confident & Knowledgeable**: You know the platform inside and out. Answer with confidence and clarity.
- **Patient**: Never rush. If something is complex, break it down step by step.
- **Proactive**: Anticipate follow-up questions. Offer related tips without being asked.
- **Human-like**: Use natural language, occasional gentle humor, and personal touches. Avoid robotic responses.

## Communication Style
- Start responses with warmth: "Hey there!", "Great to hear from you!", "I'd love to help with that!"
- Use empathy markers: "I understand", "That makes total sense", "I hear you"
- End with encouragement: "You're doing great!", "Let me know if anything else comes up!", "I'm always here for you"
- Keep responses concise but thorough — aim for 2-4 sentences for simple questions, more for complex ones
- Use formatting (bold, lists) when explaining multi-step processes
- NEVER say "I'm just an AI" or "As an AI" — you are Nova, a dedicated support companion

## What You Should NOT Do
- Don't give medical, legal, or financial advice — redirect to professionals
- Don't make up features that don't exist — stick to the platform knowledge below
- Don't share internal technical details about the infrastructure
- If you don't know something, say "Let me connect you with our support team at support@realaicoach.app for that specific question"
"""


def _is_payment_security_question(message: str) -> bool:
    text = str(message or "").lower()
    if not text:
        return False
    payment_terms = ["payment", "checkout", "card", "stripe", "paypal", "fedapay", "billing"]
    security_terms = ["safe", "secure", "security", "encrypted", "ssl", "tls", "fraud"]
    return any(term in text for term in payment_terms) and any(term in text for term in security_terms)


async def build_platform_context() -> str:
    """Dynamically build Nova context ONLY from GlobalPlatformState + live telemetry."""
    from routes.global_platform_state import get_global_platform_state

    gps = await get_global_platform_state()
    if not gps:
        return "GlobalPlatformState has not been initialized yet."

    features = [f for f in (gps.get("features") or []) if f.get("enabled", True)]
    plans = [p for p in (gps.get("plans") or []) if p.get("status") != "deprecated"]
    faq = [f for f in (gps.get("faq") or []) if f.get("active", True)]
    knowledge_docs = (gps.get("assistant_knowledge") or {}).get("documents") or []
    announcements = (gps.get("messaging") or {}).get("announcements") or []

    parts = [
        "## GlobalPlatformState Snapshot",
        "Authoritative rule: only the GPS counts and names in this snapshot are valid. Do not invent, reuse, or infer platform feature/plan counts from older FAQ text, branding copy, or model memory.",
        f"- GPS version: {gps.get('version', 1)}",
        f"- Updated at: {gps.get('updated_at', 'unknown')}",
        f"- Features: {len(features)}",
        f"- Plans: {len(plans)}",
        f"- FAQ entries: {len(faq)}",
        f"- Knowledge docs: {len(knowledge_docs)}",
    ]

    if features:
        grouped = {}
        for item in features:
            cat = str(item.get("category") or "general")
            grouped.setdefault(cat, []).append(str(item.get("title") or item.get("feature_id") or "feature"))
        parts.append("\n## GPS Features by Category")
        for cat, titles in grouped.items():
            parts.append(f"- {cat.title()}: {', '.join(titles[:8])}")

    if plans:
        parts.append("\n## GPS Plans")
        for plan in plans[:12]:
            parts.append(
                f"- {plan.get('name', plan.get('plan_id'))}: {plan.get('description', '')} | monthly={plan.get('monthly_price', 0)} {plan.get('currency', 'USD')}"
            )

    if faq:
        parts.append("\n## GPS FAQ Highlights")
        for item in faq[:8]:
            parts.append(f"- Q: {item.get('question', '')} | A: {item.get('answer', '')[:180]}")

    if announcements:
        parts.append("\n## Recent Platform Announcements")
        for ann in announcements[:6]:
            parts.append(f"- {ann.get('title', 'Update')}: {ann.get('summary', ann.get('message', ''))}")

    if knowledge_docs:
        parts.append("\n## Structured Knowledge Documents")
        for doc in knowledge_docs[:8]:
            title = doc.get("title") or doc.get("name") or "Knowledge"
            content = str(doc.get("content") or doc.get("summary") or "")
            parts.append(f"- {title}: {content[:220]}")

    try:
        total_users = await db.users.count_documents({})
        active_subs = await db.subscriptions.count_documents({"status": "active"})
        parts.append("\n## Live Telemetry")
        parts.append(f"- Total users: {total_users}")
        parts.append(f"- Active subscriptions: {active_subs}")
    except Exception:
        pass

    return "\n".join(parts)


def _tokens(value: str) -> set[str]:
    return {part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in value).split() if len(part) >= 3}


async def build_suggestion_context(user_id: str, message: str) -> str:
    """Build a proactive feature suggestion based on user's usage history."""
    if not user_id:
        return ""

    from routes.global_platform_state import get_global_platform_state

    # Check what this user has already used
    used_features = set()
    usage_docs = await db.ai_usage_log.find({"user_id": user_id}, {"_id": 0, "feature_id": 1, "copilot_id": 1}).to_list(
        500
    )
    for doc in usage_docs:
        fid = doc.get("feature_id") or doc.get("copilot_id") or ""
        used_features.add(fid)

    # Check what suggestions have already been made in this conversation
    prev_suggestions = await db.nova_suggestions.find({"user_id": user_id}, {"_id": 0, "feature_id": 1}).to_list(50)
    already_suggested = {s["feature_id"] for s in prev_suggestions}

    gps = await get_global_platform_state()
    gps_features = (gps or {}).get("features") or []
    feature_map = {}
    for item in gps_features:
        fid = str(item.get("feature_id") or item.get("id") or "").strip()
        if not fid or not item.get("enabled", True):
            continue
        feature_map[fid] = {
            "name": str(item.get("title") or fid),
            "pitch": str(item.get("description") or "Helps users get value faster."),
            "category": str(item.get("category") or "general"),
        }

    # Find unused features from GPS
    unused = {fid: info for fid, info in feature_map.items() if fid not in used_features and fid not in already_suggested}

    if not unused:
        return ""

    message_tokens = _tokens(message)
    ranked = []
    for fid, info in unused.items():
        haystack = _tokens(" ".join([fid, info.get("name", ""), info.get("pitch", ""), info.get("category", "")]))
        score = len(message_tokens & haystack)
        ranked.append((score, fid, info))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    suggestion = (ranked[0][1], ranked[0][2]) if ranked else None

    if not suggestion:
        return ""

    fid, info = suggestion

    # Record that we suggested this
    await db.nova_suggestions.insert_one(
        {
            "user_id": user_id,
            "feature_id": fid,
            "suggested_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    return f"""
## Proactive Suggestion (include naturally in your response if relevant — max 1-2 sentences at the end)
The user hasn't tried **{info["name"]}** yet — it's {info["pitch"]}. Mention it casually and warmly, like "By the way, have you checked out {info["name"]}? It's {info["pitch"]}!" Only include this if it feels natural in context. If the user's question is completely unrelated, skip it."""


async def get_nova_response(message: str, conversation_id: str, user_id: str = None) -> dict:
    """Get a response from Nova with full platform context, conversation history, and proactive suggestions."""
    now = datetime.now(timezone.utc)
    gps_context = await build_nova_gps_live_context()

    if not await ensure_nova_conversation_access(conversation_id, user_id or ""):
        raise ValueError("Conversation access denied")

    if _is_payment_security_question(message):
        try:
            from services.unified_trust_layer import get_unified_trust_settings, build_nova_payment_safety_response

            trust_settings = await get_unified_trust_settings()
            if trust_settings.get("allow_nova_security_answers", True):
                user_message_id = f"nm_{uuid.uuid4().hex[:14]}"
                await db.nova_conversations.insert_one(
                    {
                        "message_id": user_message_id,
                        "conversation_id": conversation_id,
                        "role": "user",
                        "content": message,
                        "user_id": user_id,
                        "timestamp": now.isoformat(),
                    }
                )

                trust_result = await build_nova_payment_safety_response(message)
                answer = str(trust_result.get("message") or NOVA_FALLBACK_MESSAGE).strip()
                assistant_message_id = f"nm_{uuid.uuid4().hex[:14]}"
                await db.nova_conversations.insert_one(
                    {
                        "message_id": assistant_message_id,
                        "conversation_id": conversation_id,
                        "role": "assistant",
                        "content": answer,
                        "user_id": user_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": "unified_trust_layer",
                        "gps_context": gps_context,
                    }
                )

                return {
                    "message": answer,
                    "conversation_id": conversation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "assistant_message_id": assistant_message_id,
                    "trust_snapshot": trust_result.get("trust_snapshot"),
                    "gps_context": gps_context,
                }
        except Exception:
            # Fallback to default Nova flow if trust helper fails.
            pass

    # Build dynamic context + suggestion
    platform_context = await build_platform_context()
    suggestion_context = await build_suggestion_context(user_id, message) if user_id else ""
    system_message = f"{NOVA_PERSONALITY}\n\n{platform_context}"
    if suggestion_context:
        system_message += f"\n\n{suggestion_context}"

    # Store user message
    user_message_id = f"nm_{uuid.uuid4().hex[:14]}"
    msg_doc = {
        "message_id": user_message_id,
        "conversation_id": conversation_id,
        "role": "user",
        "content": message,
        "user_id": user_id,
        "timestamp": now.isoformat(),
        "gps_context": gps_context,
    }
    await db.nova_conversations.insert_one(msg_doc)

    # Get conversation history for context
    history = (
        await db.nova_conversations.find({"conversation_id": conversation_id}, {"_id": 0, "role": 1, "content": 1})
        .sort("timestamp", 1)
        .to_list(20)
    )

    # Build messages for LLM — include last 10 messages for context
    recent_history = history[-10:]

    async def _log_nova_runtime_event(event_type: str, metadata: dict | None = None):
        try:
            await db.nova_analytics_events.insert_one(
                {
                    "event_type": event_type,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": metadata or {},
                }
            )
        except Exception:
            return

    async def _store_assistant_message(text: str, extra: dict | None = None) -> str:
        message_id = f"nm_{uuid.uuid4().hex[:14]}"
        doc = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": text,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gps_context": gps_context,
        }
        if extra:
            doc.update(extra)
        await db.nova_conversations.insert_one(doc)
        return message_id

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"nova-{conversation_id}",
            system_message=system_message,
        ).with_model("openai", "gpt-5.2")

        # Send with conversation context
        context_text = ""
        if len(recent_history) > 1:
            for h in recent_history[:-1]:
                role_label = "User" if h["role"] == "user" else "Nova"
                context_text += f"{role_label}: {h['content']}\n"
            context_text += f"\nUser: {message}"
        else:
            context_text = message

        response = await chat.send_message(UserMessage(text=context_text))
        response_text = str(response or "").strip()

        if not response_text:
            logger.warning(
                "Nova empty response detected: conversation_id=%s user_id=%s message_len=%s context_len=%s",
                conversation_id,
                user_id or "",
                len(message or ""),
                len(context_text),
            )
            await _log_nova_runtime_event(
                "nova_chat_empty_response",
                {
                    "message_length": len(message or ""),
                    "context_length": len(context_text),
                    "history_count": len(recent_history),
                    "model": "openai:gpt-5.2",
                },
            )
            assistant_message_id = await _store_assistant_message(
                NOVA_FALLBACK_MESSAGE,
                {
                    "error_code": "NOVA_EMPTY_RESPONSE",
                },
            )
            return {
                "message": NOVA_FALLBACK_MESSAGE,
                "conversation_id": conversation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "assistant_message_id": assistant_message_id,
                "gps_context": gps_context,
            }

        # Store assistant response
        assistant_message_id = await _store_assistant_message(response_text)

        return {
            "message": response_text,
            "conversation_id": conversation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "assistant_message_id": assistant_message_id,
            "gps_context": gps_context,
        }

    except Exception as e:
        logger.exception(
            "Nova chat exception: conversation_id=%s user_id=%s error_type=%s",
            conversation_id,
            user_id or "",
            type(e).__name__,
        )
        await _log_nova_runtime_event(
            "nova_chat_exception",
            {
                "error_type": type(e).__name__,
                "error_message": str(e)[:300],
                "message_length": len(message or ""),
                "history_count": len(recent_history),
                "model": "openai:gpt-5.2",
            },
        )
        assistant_message_id = await _store_assistant_message(
            NOVA_FALLBACK_MESSAGE,
            {
                "error_code": "NOVA_RUNTIME_EXCEPTION",
                "error_type": type(e).__name__,
            },
        )
        return {
            "message": NOVA_FALLBACK_MESSAGE,
            "conversation_id": conversation_id,
            "timestamp": now.isoformat(),
            "assistant_message_id": assistant_message_id,
            "gps_context": gps_context,
        }
