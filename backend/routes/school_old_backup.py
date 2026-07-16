from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid
import json
import re
from datetime import datetime, timezone
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from .db import db, EMERGENT_LLM_KEY, logger, User, resolve_user_role

router = APIRouter()

SCHOOL_DAILY_LIMITS = {
    "chat": {"free": 6, "basic": 80, "premium": -1},
    "scan": {"free": 2, "basic": 20, "premium": -1},
}


def _resolve_learning_plan(user: User | None) -> str:
    if not user:
        return "free"
    role = resolve_user_role(user)
    if role in {"admin", "full_users", "premium"}:
        return "premium"
    if role == "basic":
        return "basic"
    return "free"


async def _enforce_learning_limit(user_id: str, action: str, plan: str) -> tuple[int, int]:
    limit = int((SCHOOL_DAILY_LIMITS.get(action) or SCHOOL_DAILY_LIMITS["chat"]).get(plan, 0))
    if limit < 0:
        return 0, -1

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = await db.school_usage_log.count_documents(
        {
            "user_id": user_id,
            "action": action,
            "created_at": {"$gte": today_start},
        }
    )
    if used >= limit:
        scope = "Limited access" if plan == "free" else "Almost unlimited" if plan == "basic" else "Full unlimited"
        raise HTTPException(
            status_code=429,
            detail=f"{scope}: daily {action} limit reached ({limit}). Upgrade for higher capacity.",
        )
    return int(used), limit


async def _log_learning_usage(user_id: str, action: str, plan: str) -> None:
    await db.school_usage_log.insert_one(
        {
            "user_id": user_id,
            "action": action,
            "plan": plan,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

# ── Models ──


class ChatRequest(BaseModel):
    user_id: str
    message: str
    subject: str = "general"
    mode: str = "socratic"  # socratic, direct, roleplay


class RoleplayRequest(BaseModel):
    user_id: str
    scenario: str  # e.g. "Order food in French"
    language: str


class ScanRequest(BaseModel):
    user_id: str
    image_base64: str
    subject: str = "math"


# ── Routes ──


@router.get("/school/curriculum")
async def get_curriculum():
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
async def school_chat(request: ChatRequest):
    try:
        user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
        user = User(**user_doc) if user_doc else None
        plan = _resolve_learning_plan(user)
        await _enforce_learning_limit(request.user_id, "chat", plan)

        system_prompt = ""
        if request.mode == "socratic":
            system_prompt = """You are an AI Tutor using the Socratic Method.
            DO NOT give the direct answer.
            Instead, ask guiding questions to help the student figure it out.
            Be patient, encouraging, and break problems down into small steps.
            If the user is stuck, give a small hint, but never the full solution immediately.
            Subject: {request.subject}."""
        elif request.mode == "roleplay":
            system_prompt = f"You are a roleplay partner for learning. Immerse the user in a scenario about {request.subject}. Correct mistakes gently at the end of the exchange."
        else:
            system_prompt = "You are a helpful Tutor. Explain concepts clearly with examples."

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"school-{request.user_id}-{uuid.uuid4().hex[:8]}",
            system_message=system_prompt,
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=request.message))

        # Mock gamification - award XP
        xp_gained = 10
        await db.users.update_one({"user_id": request.user_id}, {"$inc": {"xp": xp_gained}})
        await _log_learning_usage(request.user_id, "chat", plan)

        return {
            "response": (response.text if hasattr(response, "text") else str(response)).strip(),
            "xp_gained": xp_gained,
            "mode": request.mode,
            "plan": plan,
        }
    except Exception as e:
        logger.error(f"School chat error: {e}")
        raise HTTPException(status_code=500, detail="Tutor is busy.")


@router.post("/school/scan")
async def scan_homework(request: ScanRequest):
    plan = "free"
    try:
        user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
        user = User(**user_doc) if user_doc else None
        plan = _resolve_learning_plan(user)
        await _enforce_learning_limit(request.user_id, "scan", plan)

        prompt = f"""Analyze this student homework image for subject: {request.subject}.
Return ONLY valid JSON:
{{
  "solution": "short direct answer",
  "steps": ["step 1", "step 2", "step 3"],
  "explanation": "clear explanation suitable for student",
  "graph_data": null
}}"""

        parsed = None
        analysis_mode = "vision"
        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"school-scan-{request.user_id}-{uuid.uuid4().hex[:8]}",
                system_message="You are an expert school tutor. Analyze homework images and provide accurate, step-by-step educational guidance. Return valid JSON only.",
            ).with_model("openai", "gpt-4o")

            image_content = ImageContent(image_base64=request.image_base64)
            response = await chat.send_message(UserMessage(text=prompt, file_contents=[image_content]))
            response_text = response.text if hasattr(response, "text") else str(response)

            match = re.search(r"\{[\s\S]*\}", response_text)
            if match:
                parsed = json.loads(match.group())
            elif response_text.strip():
                parsed = {
                    "solution": response_text[:220].strip() or "Analysis completed.",
                    "steps": [response_text[:500].strip() or "Review the problem statement carefully."],
                    "explanation": "AI visual analysis completed.",
                    "graph_data": None,
                }
        except Exception as vision_error:
            logger.warning(f"School scan vision failed, using text fallback: {vision_error}")
            analysis_mode = "text_fallback"

            fallback_prompt = f"""A student submitted a {request.subject} homework image but extraction failed.
Return ONLY valid JSON with practical guidance:
{{
  "solution": "next best action for student",
  "steps": ["step 1", "step 2", "step 3"],
  "explanation": "how to solve this type of problem",
  "graph_data": null
}}"""
            fallback_chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"school-scan-fallback-{request.user_id}-{uuid.uuid4().hex[:8]}",
                system_message="You are an expert school tutor. Provide structured help even when image OCR fails.",
            ).with_model("openai", "gpt-4o-mini")
            fallback_resp = await fallback_chat.send_message(UserMessage(text=fallback_prompt))
            fallback_text = fallback_resp.text if hasattr(fallback_resp, "text") else str(fallback_resp)

            match = re.search(r"\{[\s\S]*\}", fallback_text)
            if match:
                parsed = json.loads(match.group())
            else:
                parsed = {
                    "solution": fallback_text[:220].strip() or "Retake the image with clear lighting and full question visibility.",
                    "steps": [fallback_text[:500].strip() or "Read the full question, identify known values, and solve step-by-step."],
                    "explanation": "Fallback tutoring guidance generated.",
                    "graph_data": None,
                }

        await _log_learning_usage(request.user_id, "scan", plan)
        return {
            "solution": parsed.get("solution") or "Analysis completed.",
            "steps": parsed.get("steps") if isinstance(parsed.get("steps"), list) else ["Review detected steps in the explanation."],
            "explanation": parsed.get("explanation") or "AI visual analysis completed.",
            "graph_data": parsed.get("graph_data"),
            "plan": plan,
            "analysis_mode": analysis_mode,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scan error: {e}")
        return {
            "solution": "Image analysis is temporarily degraded. Please retry with a clearer image or use Tutor Chat.",
            "steps": [
                "Retake a clear image including the full problem statement.",
                "Avoid blur and shadows.",
                "Use Tutor Chat mode if scan continues failing.",
            ],
            "explanation": "Degraded fallback response served to preserve user flow.",
            "graph_data": None,
            "plan": plan,
            "analysis_mode": "degraded",
        }


@router.get("/school/progress/{user_id}")
async def get_progress(user_id: str):
    user = await db.users.find_one({"user_id": user_id})
    return {
        "xp": user.get("xp", 0) if user else 0,
        "streak": 5,  # Mock streak
        "subjects_mastered": ["Algebra I"],
    }
