from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import uuid
import json
import re
from datetime import datetime, timezone
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from .db import logger, db, User, resolve_user_role, EMERGENT_LLM_KEY
from utils.llm_helper import generate_verified_json

router = APIRouter()

FITNESS_DAILY_LIMITS = {
    "workout": {"free": 3, "basic": 60, "premium": -1},
    "scan": {"free": 1, "basic": 20, "premium": -1},
}


class WorkoutRequest(BaseModel):
    user_id: str
    plan_type: str = "weekly"
    focus_areas: List[str]
    duration_minutes: int = 45


class ScanBodyRequest(BaseModel):
    user_id: str
    image_base64: str
    scan_type: str = "body"


def _resolve_fitness_plan(user: User | None) -> str:
    if not user:
        return "free"
    role = resolve_user_role(user)
    if role in {"admin", "full_users", "premium"}:
        return "premium"
    if role == "basic":
        return "basic"
    return "free"


async def _enforce_fitness_limit(user_id: str, action: str, plan: str) -> None:
    limit = int((FITNESS_DAILY_LIMITS.get(action) or FITNESS_DAILY_LIMITS["workout"]).get(plan, 0))
    if limit < 0:
        return
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    used = await db.fitness_usage_log.count_documents(
        {"user_id": user_id, "action": action, "created_at": {"$gte": start}}
    )
    if used >= limit:
        scope = "Limited access" if plan == "free" else "Almost unlimited" if plan == "basic" else "Full unlimited"
        raise HTTPException(status_code=429, detail=f"{scope}: daily {action} limit reached ({limit}).")


async def _log_fitness_usage(user_id: str, action: str, plan: str) -> None:
    await db.fitness_usage_log.insert_one(
        {
            "user_id": user_id,
            "action": action,
            "plan": plan,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.post("/fitness/workout-plan")
async def generate_workout_plan(request: WorkoutRequest):
    try:
        user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
        user = User(**user_doc) if user_doc else None
        plan = _resolve_fitness_plan(user)
        await _enforce_fitness_limit(request.user_id, "workout", plan)

        session_id = f"fitness-{uuid.uuid4().hex[:8]}"
        system_message = "You are an elite fitness coach. Generate a structured workout plan."
        prompt = f"""Create a {request.plan_type} workout plan focusing on {", ".join(request.focus_areas)}.
Duration: {request.duration_minutes} minutes per session.

Return ONLY valid JSON with this structure:
{{
  "plan_name": "Name of Plan",
  "workouts": [
    {{
      "day": "Day 1",
      "focus": "Focus Area",
      "main_workout": [
        {{ "name": "Exercise Name", "sets": 3, "reps": 12 }}
      ]
    }}
  ]
}}"""

        plan_data = await generate_verified_json(prompt, system_message, session_id)
        await _log_fitness_usage(request.user_id, "workout", plan)
        plan_data["plan_scope"] = plan
        plan_data["daily_limit"] = FITNESS_DAILY_LIMITS["workout"][plan]
        return plan_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workout Gen Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate workout plan")


@router.post("/fitness/scan-body")
async def scan_body(request: ScanBodyRequest):
    plan = "free"
    try:
        user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
        user = User(**user_doc) if user_doc else None
        plan = _resolve_fitness_plan(user)
        await _enforce_fitness_limit(request.user_id, "scan", plan)

        parsed = None
        analysis_mode = "vision"
        prompt = """Analyze this fitness posture image.
Return ONLY valid JSON:
{
  "posture_assessment": "short posture summary",
  "suggested_exercises": [
    {"exercise": "name", "sets": 3, "reps": 12, "why": "reason"}
  ],
  "motivation": "short motivational summary"
}"""

        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"fitness-scan-{request.user_id}-{uuid.uuid4().hex[:8]}",
                system_message="You are an elite fitness posture coach. Return valid JSON only.",
            ).with_model("openai", "gpt-4o")
            response = await chat.send_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=request.image_base64)]))
            text = response.text if hasattr(response, "text") else str(response)
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                parsed = json.loads(match.group())
        except Exception as vision_error:
            logger.warning(f"Fitness scan vision fallback: {vision_error}")
            analysis_mode = "text_fallback"
            fallback_chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"fitness-scan-fallback-{request.user_id}-{uuid.uuid4().hex[:8]}",
                system_message="You are an elite fitness coach. Give practical fallback guidance in valid JSON.",
            ).with_model("openai", "gpt-4o-mini")
            fallback_resp = await fallback_chat.send_message(
                UserMessage(text="Image parsing failed. Provide generic posture recommendations as JSON with posture_assessment, suggested_exercises, motivation.")
            )
            fallback_text = fallback_resp.text if hasattr(fallback_resp, "text") else str(fallback_resp)
            match = re.search(r"\{[\s\S]*\}", fallback_text)
            if match:
                parsed = json.loads(match.group())

        if not parsed:
            analysis_mode = "degraded"
            parsed = {
                "posture_assessment": "Unable to parse full posture image. Re-upload with better lighting and full body framing.",
                "suggested_exercises": [
                    {"exercise": "Chin Tucks", "sets": 3, "reps": 10, "why": "Supports neck posture alignment"},
                    {"exercise": "Face Pulls", "sets": 3, "reps": 15, "why": "Strengthens upper back stability"},
                ],
                "motivation": "Great consistency. Improving capture quality will unlock sharper coaching insights.",
            }

        await _log_fitness_usage(request.user_id, "scan", plan)
        return {
            "body_analysis": {
                "posture_assessment": parsed.get("posture_assessment", "Posture guidance generated."),
            },
            "workout_recommendations": {
                "suggested_exercises": parsed.get("suggested_exercises") if isinstance(parsed.get("suggested_exercises"), list) else [],
            },
            "progress_plan": {
                "motivation": parsed.get("motivation", "Keep progressing with consistent form and mobility work."),
            },
            "plan_scope": plan,
            "analysis_mode": analysis_mode,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fitness scan error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze body scan")
