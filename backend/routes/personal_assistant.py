"""Personal AI Assistant v2 — enterprise-grade assistant workspace APIs."""

from __future__ import annotations

import re
import uuid
import os
from datetime import datetime, timezone
from typing import Any, Optional, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from emergentintegrations.llm.chat import LlmChat, UserMessage
from utils.access_control_engine import compute_effective_plan

from routes.db import db, get_current_user, logger


router = APIRouter(prefix="/personal-assistant", tags=["Personal AI Assistant"])

GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")
ASSISTANT_MODES = ["planner", "executor", "coach", "critic"]
MESSAGE_ROLE = Literal["user", "assistant", "system"]

# Chat models available in the assistant model picker (Emergent LLM key)
CHAT_MODELS = {
    "gpt-4o": {"provider": "openai", "model": "gpt-4o", "label": "GPT-4o", "description": "OpenAI flagship — fast, versatile"},
    "claude-sonnet-4-6": {"provider": "anthropic", "model": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6", "description": "Anthropic balanced — deep reasoning"},
    "claude-haiku-4-5": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5", "description": "Anthropic fast — quick answers"},
}
DEFAULT_CHAT_MODEL = "gpt-4o"

# TIER LIMITS: Message quotas per day
TIER_LIMITS = {
    "free": {
        "messages_per_day": 50,
        "modes": ["planner", "executor", "coach", "critic"],  # All modes available
        "memory_notes": 5,
        "actions": 10,
    },
    "basic": {
        "messages_per_day": 200,
        "modes": ["planner", "executor", "coach", "critic"],
        "memory_notes": 50,
        "actions": 50,
        "daily_briefing": True,
    },
    "premium": {
        "messages_per_day": -1,  # Unlimited
        "modes": ["planner", "executor", "coach", "critic"],
        "memory_notes": -1,  # Unlimited
        "actions": -1,  # Unlimited
        "daily_briefing": True,
        "priority_response": True,
    },
}


class CreateSessionRequest(BaseModel):
    title: str = Field(default="New Assistant Session", min_length=1, max_length=140)
    fallback_user_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    mode: str = Field(default="planner", max_length=40)
    model: Optional[str] = Field(default=None, max_length=60)
    fallback_user_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=120)


class UpsertMemoryRequest(BaseModel):
    note: str = Field(min_length=2, max_length=600)
    fallback_user_id: Optional[str] = None


class CreateActionRequest(BaseModel):
    title: str = Field(min_length=2, max_length=220)
    due_hint: str = Field(default="", max_length=120)
    fallback_user_id: Optional[str] = None


class UpdateActionRequest(BaseModel):
    done: bool
    fallback_user_id: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    if user and getattr(user, "user_id", None):
        return f"auth:{str(user.user_id)}"

    fallback = str(fallback_user_id or "").strip()
    if not fallback:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "assistant_auth_required",
                "message": "Login required or provide fallback_user_id for guest assistant session",
            },
        )
    if not GUEST_ID_RE.match(fallback):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "assistant_invalid_guest_id",
                "message": "fallback_user_id format is invalid",
            },
        )
    return f"guest:{fallback}"


async def _get_user_tier(owner_id: str) -> str:
    """Determine user's subscription tier (free, basic, premium)."""
    if not owner_id.startswith("auth:"):
        return "free"  # Guest users are always free tier
    
    try:
        user_id = owner_id.replace("auth:", "")
        user_doc = await db.users.find_one(
            {"user_id": user_id},
            {
                "_id": 0,
                "subscription_plan": 1,
                "subscription_status": 1,
                "subscription_end_date": 1,
                "pending_subscription_transition": 1,
                "payment_verified": 1,
                "is_admin": 1,
            },
        )
        if not user_doc:
            return "free"

        effective = compute_effective_plan(user_doc or {})
        return effective if effective in TIER_LIMITS else "free"
    except Exception as e:
        logger.warning(f"Failed to fetch tier for {owner_id}: {e}")
        return "free"


async def _get_daily_message_count(owner_id: str) -> int:
    """Get number of messages sent today by user."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = await db.personal_assistant_messages.count_documents({
        "owner_id": owner_id,
        "role": "user",
        "created_at": {"$gte": today_start.isoformat()},
    })
    return count


async def _check_message_limit(owner_id: str, tier: str) -> dict[str, Any]:
    """Check if user can send more messages today. Returns usage info."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    daily_limit = limits["messages_per_day"]
    
    # Premium has unlimited (-1)
    if daily_limit == -1:
        return {
            "can_send": True,
            "messages_used_today": 0,
            "daily_limit": -1,
            "tier": tier,
            "limit_reached": False,
        }
    
    messages_used = await _get_daily_message_count(owner_id)
    can_send = messages_used < daily_limit
    
    return {
        "can_send": can_send,
        "messages_used_today": messages_used,
        "daily_limit": daily_limit,
        "tier": tier,
        "limit_reached": not can_send,
    }


def _mode_instruction(mode: str) -> str:
    normalized = (mode or "").strip().lower()
    if normalized not in ASSISTANT_MODES:
        normalized = "planner"
    mode_map = {
        "planner": "Break goals into practical step-by-step plan with sequencing.",
        "executor": "Provide direct, tactical, action-first output with clear next actions.",
        "coach": "Use supportive tone and behavior-change framing with accountability prompts.",
        "critic": "Analyze risks, assumptions, and blind spots and offer stronger alternatives.",
    }
    return mode_map[normalized]


def _response_quality(text: str) -> dict[str, Any]:
    words = re.findall(r"\b\w+\b", text)
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    word_count = len(words)
    avg_sentence = word_count / sentences if sentences else word_count

    structure = 90 if any(marker in text for marker in ["1.", "- ", "##", "•"]) else 58
    clarity = int(max(30, min(100, 100 - max(0, avg_sentence - 24) * 6)))
    actionability = 88 if any(term in text.lower() for term in ["next step", "action", "today", "deadline", "checklist"]) else 55
    overall = int(round((structure + clarity + actionability) / 3))

    return {
        "overall": overall,
        "structure": structure,
        "clarity": clarity,
        "actionability": actionability,
        "word_count": word_count,
    }


def _extract_action_suggestions(text: str) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if lowered.startswith("-") or lowered.startswith("*") or re.match(r"^\d+\.", lowered):
            title = re.sub(r"^[-*\d\.\s]+", "", line).strip()[:220]
            if title:
                suggestions.append({"title": title, "due_hint": ""})
        if len(suggestions) >= 5:
            break
    return suggestions


async def _session_exists(owner_id: str, session_id: str) -> bool:
    found = await db.personal_assistant_sessions.find_one({"owner_id": owner_id, "session_id": session_id}, {"_id": 0, "session_id": 1})
    return bool(found)


async def _fetch_recent_messages(owner_id: str, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = await db.personal_assistant_messages.find(
        {"owner_id": owner_id, "session_id": session_id},
        {"_id": 0, "message_id": 1, "role": 1, "content": 1, "created_at": 1, "quality": 1, "model": 1, "model_label": 1},
    ).sort("created_at", -1).to_list(limit)
    rows.reverse()
    return rows


@router.get("/bootstrap")
async def assistant_bootstrap(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    usage_info = await _check_message_limit(owner_id, tier)

    sessions = await db.personal_assistant_sessions.find(
        {"owner_id": owner_id},
        {"_id": 0, "session_id": 1, "title": 1, "updated_at": 1, "last_mode": 1, "message_count": 1},
    ).sort("updated_at", -1).to_list(20)

    actions = await db.personal_assistant_actions.find(
        {"owner_id": owner_id},
        {"_id": 0, "action_id": 1, "title": 1, "due_hint": 1, "done": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(15)

    memory_notes = await db.personal_assistant_memory.find(
        {"owner_id": owner_id},
        {"_id": 0, "note_id": 1, "note": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(12)

    pending_actions = len([a for a in actions if not a.get("done")])
    return {
        "owner_id": owner_id,
        "tier": tier,
        "sessions": sessions,
        "actions": actions,
        "memory_notes": memory_notes,
        "modes": ASSISTANT_MODES,
        "stats": {
            "sessions_count": len(sessions),
            "pending_actions": pending_actions,
            "memory_count": len(memory_notes),
        },
        "usage": usage_info,
        "tier_limits": TIER_LIMITS.get(tier, TIER_LIMITS["free"]),
    }


@router.get("/usage")
async def get_usage(request: Request, fallback_user_id: Optional[str] = None):
    """Get current usage and tier limits for the user."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    usage_info = await _check_message_limit(owner_id, tier)
    
    return {
        **usage_info,
        "tier_limits": TIER_LIMITS.get(tier, TIER_LIMITS["free"]),
    }


@router.post("/sessions")
async def create_session(payload: CreateSessionRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    now = _now_iso()
    session = {
        "session_id": f"pas_{uuid.uuid4().hex[:14]}",
        "owner_id": owner_id,
        "title": payload.title.strip()[:140],
        "created_at": now,
        "updated_at": now,
        "last_mode": "planner",
        "message_count": 0,
    }
    await db.personal_assistant_sessions.insert_one(dict(session))
    return {"session": session}


@router.get("/sessions")
async def list_sessions(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    sessions = await db.personal_assistant_sessions.find(
        {"owner_id": owner_id},
        {"_id": 0, "session_id": 1, "title": 1, "updated_at": 1, "last_mode": 1, "message_count": 1},
    ).sort("updated_at", -1).to_list(30)
    return {"sessions": sessions}


@router.get("/models")
async def list_chat_models():
    """Available chat models for the assistant model picker."""
    return {
        "default": DEFAULT_CHAT_MODEL,
        "models": [{"key": key, **{k: v for k, v in cfg.items() if k != "model"}} for key, cfg in CHAT_MODELS.items()],
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    session = await db.personal_assistant_sessions.find_one(
        {"owner_id": owner_id, "session_id": session_id},
        {"_id": 0},
    )
    if not session:
        raise HTTPException(status_code=404, detail={"error_code": "assistant_session_not_found", "message": "Session not found"})

    messages = await _fetch_recent_messages(owner_id, session_id, 80)
    return {"session": session, "messages": messages}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, payload: SendMessageRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Check tier and message limits
    tier = await _get_user_tier(owner_id)
    usage_check = await _check_message_limit(owner_id, tier)
    
    if not usage_check["can_send"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "assistant_message_limit_reached",
                "message": f"Daily message limit reached ({usage_check['daily_limit']} messages). Upgrade to {tier=='free' and 'Basic' or 'Premium'} for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "messages_used_today": usage_check["messages_used_today"],
                "daily_limit": usage_check["daily_limit"],
            },
        )

    if not await _session_exists(owner_id, session_id):
        raise HTTPException(status_code=404, detail={"error_code": "assistant_session_not_found", "message": "Session not found"})

    idempotency_key = (payload.idempotency_key or "").strip()
    if idempotency_key:
        existing = await db.personal_assistant_messages.find_one(
            {
                "owner_id": owner_id,
                "session_id": session_id,
                "idempotency_key": idempotency_key,
                "role": "assistant",
            },
            {"_id": 0},
        )
        if existing:
            return {"assistant_message": existing, "idempotent_replay": True}

    now = _now_iso()
    user_message = {
        "message_id": f"msg_{uuid.uuid4().hex[:14]}",
        "owner_id": owner_id,
        "session_id": session_id,
        "role": "user",
        "content": payload.content.strip(),
        "mode": payload.mode,
        "created_at": now,
        "idempotency_key": idempotency_key or None,
    }
    await db.personal_assistant_messages.insert_one(dict(user_message))

    recent_messages = await _fetch_recent_messages(owner_id, session_id, 10)
    memory_notes = await db.personal_assistant_memory.find(
        {"owner_id": owner_id},
        {"_id": 0, "note": 1},
    ).sort("created_at", -1).to_list(6)

    conversation_context = "\n".join([f"{m.get('role')}: {m.get('content')}" for m in recent_messages[-8:]])
    memory_context = "\n".join([f"- {note.get('note')}" for note in memory_notes]) or "- none"

    mode = (payload.mode or "planner").strip().lower()
    if mode not in ASSISTANT_MODES:
        mode = "planner"

    model_key = (payload.model or DEFAULT_CHAT_MODEL).strip().lower()
    if model_key not in CHAT_MODELS:
        model_key = DEFAULT_CHAT_MODEL
    model_cfg = CHAT_MODELS[model_key]

    system_prompt = (
        f"You are Personal AI Assistant Pro, powered by {model_cfg['label']}. "
        "You are practical, insightful, and action-oriented. "
        "Your goal is to help users accomplish their goals with clear guidance and concrete steps. "
        "Be conversational yet professional. Always end with a follow-up question to maintain engagement."
    )

    mode_instruction = _mode_instruction(mode)

    prompt = f"""
Mode: {mode}
Mode Goal: {mode_instruction}

Pinned Memory Notes:
{memory_context}

Recent Conversation Context:
{conversation_context}

User Message:
{payload.content.strip()}

Response requirements:
- Start with a short, direct answer
- Provide actionable next steps (numbered or bulleted)
- End with 1 engaging follow-up question
- Be concise but thorough
""".strip()

    assistant_message_id = f"msg_{uuid.uuid4().hex[:14]}"
    try:
        api_key = os.environ.get("EMERGENT_LLM_KEY", "")
        if not api_key:
            raise ValueError("EMERGENT_LLM_KEY not configured")

        session_key = f"personal-assistant-{owner_id}-{session_id}"
        llm = (
            LlmChat(
                api_key=api_key,
                session_id=session_key,
                system_message=system_prompt,
            )
            .with_model(model_cfg["provider"], model_cfg["model"])
        )

        response_text = await llm.send_message(UserMessage(text=prompt))

        quality = _response_quality(response_text)
        action_suggestions = _extract_action_suggestions(response_text)
        assistant_message = {
            "message_id": assistant_message_id,
            "owner_id": owner_id,
            "session_id": session_id,
            "role": "assistant",
            "content": response_text,
            "mode": mode,
            "created_at": _now_iso(),
            "quality": quality,
            "action_suggestions": action_suggestions,
            "idempotency_key": idempotency_key or None,
            "model": model_key,
            "model_label": model_cfg["label"],
            "provider": model_cfg["provider"],
            "tier": tier,
        }
        await db.personal_assistant_messages.insert_one(dict(assistant_message))
        await db.personal_assistant_sessions.update_one(
            {"owner_id": owner_id, "session_id": session_id},
            {"$set": {"updated_at": _now_iso(), "last_mode": mode}, "$inc": {"message_count": 2}},
        )
        return {"user_message": user_message, "assistant_message": assistant_message}
    except Exception as exc:
        logger.exception("Personal assistant response failed: %s", exc)
        await db.personal_assistant_sessions.update_one(
            {"owner_id": owner_id, "session_id": session_id},
            {"$set": {"updated_at": _now_iso(), "last_mode": mode}, "$inc": {"message_count": 1}},
        )
        raise HTTPException(
            status_code=500,
            detail={"error_code": "assistant_generation_failed", "message": "Assistant response failed. Please retry."},
        )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Delete an assistant session and all its messages."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.assistant_sessions.delete_one({"session_id": session_id, "owner_id": owner_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "personal_assistant_session_not_found", "message": "Session not found"}
        )
    
    # Also delete associated messages
    await db.assistant_messages.delete_many({"session_id": session_id, "owner_id": owner_id})
    
    return {"message": "Session deleted successfully", "session_id": session_id}


@router.post("/memory")
async def add_memory_note(payload: UpsertMemoryRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    note = {
        "note_id": f"mem_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "note": payload.note.strip()[:600],
        "created_at": _now_iso(),
    }
    await db.personal_assistant_memory.insert_one(dict(note))
    return {"note": note}


@router.post("/actions")
async def create_action(payload: CreateActionRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    action = {
        "action_id": f"act_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "title": payload.title.strip()[:220],
        "due_hint": payload.due_hint.strip()[:120],
        "done": False,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.personal_assistant_actions.insert_one(dict(action))
    return {"action": action}


@router.patch("/actions/{action_id}")
async def update_action(action_id: str, payload: UpdateActionRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    query = {"owner_id": owner_id, "action_id": action_id}
    exists = await db.personal_assistant_actions.find_one(query, {"_id": 0, "action_id": 1})
    if not exists:
        raise HTTPException(status_code=404, detail={"error_code": "assistant_action_not_found", "message": "Action not found"})

    await db.personal_assistant_actions.update_one(
        query,
        {"$set": {"done": bool(payload.done), "updated_at": _now_iso()}},
    )
    action = await db.personal_assistant_actions.find_one(query, {"_id": 0})
    return {"action": action}


@router.get("/actions")
async def list_actions(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    actions = await db.personal_assistant_actions.find({"owner_id": owner_id}, {"_id": 0}).sort("created_at", -1).to_list(80)
    return {"actions": actions}


@router.post("/daily-brief")
async def generate_daily_brief(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    recent_messages = await db.personal_assistant_messages.find(
        {"owner_id": owner_id, "role": {"$in": ["user", "assistant"]}},
        {"_id": 0, "role": 1, "content": 1},
    ).sort("created_at", -1).to_list(10)
    pending_actions = await db.personal_assistant_actions.find(
        {"owner_id": owner_id, "done": False},
        {"_id": 0, "title": 1, "due_hint": 1},
    ).sort("created_at", -1).to_list(8)

    conversation = "\n".join([f"{item.get('role')}: {item.get('content')}" for item in reversed(recent_messages)]) or "No recent messages"
    actions_context = "\n".join([f"- {item.get('title')} ({item.get('due_hint') or 'no due hint'})" for item in pending_actions]) or "- No pending actions"

    prompt = f"""
Create a concise daily brief for this assistant user.

Recent conversation:
{conversation}

Pending actions:
{actions_context}

Return in this format:
1) Today's focus
2) Top 3 priorities
3) Biggest risk
4) One momentum action for next 30 minutes
""".strip()

    api_key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="LLM service not configured")

    chat = (
        LlmChat(
            api_key=api_key,
            session_id=f"personal-assistant-brief-{owner_id}-{uuid.uuid4().hex[:8]}",
            system_message="You are a high-performance executive assistant. Be concise and practical.",
        )
        .with_model("openai", "gpt-4o")
    )
    brief_text = await chat.send_message(UserMessage(text=prompt))

    brief = {
        "brief_id": f"brief_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "content": brief_text,
        "created_at": _now_iso(),
    }
    await db.personal_assistant_daily_briefs.insert_one(dict(brief))
    return {"daily_brief": brief}
