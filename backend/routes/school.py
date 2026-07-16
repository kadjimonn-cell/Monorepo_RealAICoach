"""Feature 6: School Tutor - Learning Coach (Enterprise-Grade)

AI-powered tutoring across multiple subjects with personalized learning paths.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Any
import uuid
from datetime import datetime, timezone
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from .db import db, EMERGENT_LLM_KEY, logger, get_current_user
from utils.access_control_engine import compute_effective_plan

router = APIRouter()

SCHOOL_DAILY_LIMITS = {
    "chat": {"free": 6, "basic": 80, "premium": -1},
    "scan": {"free": 2, "basic": 20, "premium": -1},
}


# ── Authentication & Tier Helpers ──


def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    """Resolve owner_id from authenticated user or fallback guest ID."""
    if user and hasattr(user, "user_id"):
        return f"auth:{user.user_id}"
    if fallback_user_id:
        return f"guest:{fallback_user_id}"
    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "school_auth_required",
            "message": "Login required or provide fallback_user_id for guest learning",
        },
    )


async def _get_tier(owner_id: str) -> str:
    """Get user's subscription tier."""
    if str(owner_id or "").startswith("guest:"):
        return "free"

    user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")
    if not user_id:
        return "free"

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
    if user_doc:
        effective = compute_effective_plan(user_doc or {})
        return effective if effective in ["free", "basic", "premium"] else "free"
    return "free"


async def _enforce_learning_limit(owner_id: str, action: str, plan: str) -> tuple[int, int]:
    """Enforce daily learning limits based on tier."""
    limit = int((SCHOOL_DAILY_LIMITS.get(action) or SCHOOL_DAILY_LIMITS["chat"]).get(plan, 0))
    if limit < 0:
        return 0, -1

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = await db.school_usage_log.count_documents({
        "owner_id": owner_id,
        "action": action,
        "created_at": {"$gte": today_start},
    })
    
    if used >= limit:
        scope = "Limited access" if plan == "free" else "Almost unlimited" if plan == "basic" else "Full unlimited"
        raise HTTPException(
            status_code=429,
            detail=f"{scope}: daily {action} limit reached ({limit}). Upgrade for higher capacity.",
        )
    return int(used), limit


async def _log_learning_usage(owner_id: str, action: str, plan: str) -> None:
    """Log learning activity for analytics and tier enforcement."""
    await db.school_usage_log.insert_one({
        "owner_id": owner_id,
        "action": action,
        "plan": plan,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ── Models ──


class ChatRequest(BaseModel):
    message: str
    subject: str = "general"
    mode: str = "socratic"  # socratic, direct, roleplay
    fallback_user_id: Optional[str] = None


class RoleplayRequest(BaseModel):
    scenario: str  # e.g. "Order food in French"
    language: str
    fallback_user_id: Optional[str] = None


class ScanRequest(BaseModel):
    image_base64: str
    subject: str = "math"
    fallback_user_id: Optional[str] = None


# ── Routes ──


@router.get("/school/curriculum")
async def get_curriculum():
    """Get available subjects and topics."""
    return {
        "subjects": [
            {"id": "math", "name": "Mathematics", "icon": "calculator", "topics": ["Algebra", "Calculus", "Geometry"]},
            {"id": "science", "name": "Science", "icon": "flask", "topics": ["Physics", "Chemistry", "Biology"]},
            {"id": "coding", "name": "Coding", "icon": "code-slash", "topics": ["Python", "JavaScript", "Web Dev"]},
            {"id": "language", "name": "Languages", "icon": "language", "topics": ["Spanish", "French", "Mandarin"]},
            {"id": "history", "name": "History", "icon": "book", "topics": ["World History", "US History"]},
        ]
    }


@router.post("/school/chat")
async def school_chat(request: Request, payload: ChatRequest):
    """AI-powered tutoring chat with Socratic method."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    used, limit = await _enforce_learning_limit(owner_id, "chat", tier)

    try:
        session_id = f"school-chat-{uuid.uuid4().hex[:8]}"
        
        mode_prompts = {
            "socratic": "Use the Socratic method: guide with questions, don't give direct answers. Encourage critical thinking.",
            "direct": "Provide clear, direct explanations with examples. Be thorough but concise.",
            "roleplay": "Act as a subject-matter expert. Use analogies and storytelling to explain concepts.",
        }
        
        system_msg = f"You are a patient, encouraging tutor specializing in {payload.subject}. {mode_prompts.get(payload.mode, mode_prompts['socratic'])}"
        
        llm = LlmChat(model="gpt-4o", api_key=EMERGENT_LLM_KEY, session_id=session_id)
        llm.add_message(UserMessage(content=payload.message))
        response = await llm.send_async(system_message=system_msg)
        
        await _log_learning_usage(owner_id, "chat", tier)
        
        return {
            "response": response,
            "subject": payload.subject,
            "mode": payload.mode,
            "session_id": session_id,
            "owner_id": owner_id,
            "tier": tier,
            "daily_limit": limit,
            "used_today": used + 1,
        }
    
    except Exception as e:
        logger.error(f"School chat failed: {e}")
        raise HTTPException(status_code=500, detail="Tutoring session failed. Please try again.")


@router.post("/school/roleplay")
async def school_roleplay(request: Request, payload: RoleplayRequest):
    """Interactive language/scenario roleplay."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    used, limit = await _enforce_learning_limit(owner_id, "chat", tier)

    try:
        session_id = f"roleplay-{uuid.uuid4().hex[:8]}"
        system_msg = f"You are a native {payload.language} speaker. Roleplay the scenario: '{payload.scenario}'. Respond naturally in {payload.language}, then provide English translations in parentheses."
        
        llm = LlmChat(model="gpt-4o", api_key=EMERGENT_LLM_KEY, session_id=session_id)
        llm.add_message(UserMessage(content=f"Let's practice: {payload.scenario}"))
        response = await llm.send_async(system_message=system_msg)
        
        await _log_learning_usage(owner_id, "chat", tier)
        
        return {
            "response": response,
            "scenario": payload.scenario,
            "language": payload.language,
            "session_id": session_id,
            "owner_id": owner_id,
            "tier": tier,
        }
    
    except Exception as e:
        logger.error(f"Roleplay failed: {e}")
        raise HTTPException(status_code=500, detail="Roleplay session failed. Please try again.")


@router.post("/school/scan")
async def scan_homework(request: Request, payload: ScanRequest):
    """Scan and solve homework problems using AI vision."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    used, limit = await _enforce_learning_limit(owner_id, "scan", tier)

    try:
        session_id = f"scan-{uuid.uuid4().hex[:8]}"
        
        # Validate base64 image
        if not payload.image_base64 or len(payload.image_base64) < 100:
            raise HTTPException(status_code=400, detail="Invalid or missing image data")
        
        system_msg = f"You are a {payload.subject} tutor. Analyze the problem in the image. Provide: 1) Problem identification, 2) Step-by-step solution, 3) Key concepts, 4) Practice tip."
        
        llm = LlmChat(model="gpt-4o", api_key=EMERGENT_LLM_KEY, session_id=session_id)
        llm.add_message(UserMessage(content=[
            "Analyze and solve this problem:",
            ImageContent(image=payload.image_base64, detail="high")
        ]))
        response = await llm.send_async(system_message=system_msg)
        
        await _log_learning_usage(owner_id, "scan", tier)
        
        return {
            "solution": response,
            "subject": payload.subject,
            "session_id": session_id,
            "owner_id": owner_id,
            "tier": tier,
            "daily_limit": limit,
            "used_today": used + 1,
        }
    
    except Exception as e:
        logger.error(f"Homework scan failed: {e}")
        raise HTTPException(status_code=500, detail="Problem scanning failed. Please try again.")
