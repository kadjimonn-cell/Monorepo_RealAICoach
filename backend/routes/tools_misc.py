"""Miscellaneous tool routes: Security, AI Search, Fitness Planner, Tools, Voice AI, Session History."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import uuid
from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, EMERGENT_LLM_KEY, logger, has_basic_access, User


def _resp_text(response: object) -> str:
    return response.text if hasattr(response, "text") else str(response)


router = APIRouter()


# ── Security Settings ──


class SecuritySettingsRequest(BaseModel):
    two_factor_enabled: Optional[bool] = None
    biometric_enabled: Optional[bool] = None
    login_alerts: Optional[bool] = None
    profile_visible: Optional[bool] = None
    activity_visible: Optional[bool] = None
    data_collection: Optional[bool] = None


SECURITY_DEFAULTS = {
    "two_factor_enabled": False,
    "biometric_enabled": False,
    "login_alerts": True,
    "profile_visible": True,
    "activity_visible": False,
    "data_collection": True,
}


@router.get("/security/settings/{user_id}")
async def get_security_settings(user_id: str):
    settings = await db.security_settings.find_one({"user_id": user_id}, {"_id": 0})
    if not settings:
        settings = {"user_id": user_id, **SECURITY_DEFAULTS}
        await db.security_settings.insert_one({**settings})
    return settings


@router.put("/security/settings/{user_id}")
async def update_security_settings(user_id: str, request: SecuritySettingsRequest):
    update_data = {k: v for k, v in request.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    existing = await db.security_settings.find_one({"user_id": user_id})
    if existing:
        await db.security_settings.update_one({"user_id": user_id}, {"$set": update_data})
    else:
        defaults = {"user_id": user_id, **SECURITY_DEFAULTS}
        defaults.update(update_data)
        await db.security_settings.insert_one(defaults)

    return await db.security_settings.find_one({"user_id": user_id}, {"_id": 0})


# ── AI Search ──


class AISearchRequest(BaseModel):
    user_id: str
    query: str
    search_type: str = "comprehensive"


import json


@router.post("/ai-search")
async def ai_search(request: AISearchRequest):
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"search-{uuid.uuid4().hex[:8]}",
            system_message="You are a comprehensive AI research assistant. Respond in pure JSON format with the following fields: 'answer' (detailed analysis with markdown), 'keywords' (list of 5 relevant tag strings), 'follow_up_questions' (list of 3 strings).",
        ).with_model("openai", "gpt-4o-mini")
        response = await chat.send_message(UserMessage(text=request.query))

        try:
            clean_resp = _resp_text(response).strip()
            if clean_resp.startswith("```json"):
                clean_resp = clean_resp[7:]
            elif clean_resp.startswith("```"):
                clean_resp = clean_resp[3:]
            if clean_resp.endswith("```"):
                clean_resp = clean_resp[:-3]
            data = json.loads(clean_resp.strip())
        except Exception:
            data = {"answer": _resp_text(response).strip(), "keywords": ["Research", "AI"], "follow_up_questions": []}

        results = {
            "researcher": {"role": "Research & Analysis", "content": data.get("answer", ""), "status": "complete"}
        }

        search_record = {
            "user_id": request.user_id,
            "query": request.query,
            "search_type": request.search_type,
            "results": results,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.ai_searches.insert_one(search_record)

        return {
            "query": request.query,
            "agents": results,
            "keywords": data.get("keywords", []),
            "follow_up_questions": data.get("follow_up_questions", []),
            "search_id": str(uuid.uuid4().hex[:12]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"AI Search error: {e}")
        raise HTTPException(status_code=500, detail="AI Search failed")


@router.get("/ai-search/history/{user_id}")
async def get_search_history(user_id: str, limit: int = 20):
    searches = (
        await db.ai_searches.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    )
    return {"searches": searches}


# ── Fitness Planner ──


class FitnessPlanGenerateRequest(BaseModel):
    user_id: str
    fitness_level: str = "beginner"
    goal: str = "general_fitness"
    available_days: int = 3
    session_duration: int = 45
    equipment: List[str] = []
    injuries: List[str] = []
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None


@router.post("/fitness-planner/generate")
async def generate_fitness_plan(request: FitnessPlanGenerateRequest):
    try:
        equipment_str = ", ".join(request.equipment) if request.equipment else "no equipment (bodyweight only)"
        injuries_str = ", ".join(request.injuries) if request.injuries else "none"
        personal_info = ""
        if request.age:
            personal_info += f"Age: {request.age}. "
        if request.weight:
            personal_info += f"Weight: {request.weight}kg. "
        if request.height:
            personal_info += f"Height: {request.height}cm. "

        prompt = f"""Create a detailed {request.available_days}-day weekly fitness plan:
- Fitness Level: {request.fitness_level}
- Goal: {request.goal}
- Session Duration: {request.session_duration} minutes
- Equipment: {equipment_str}
- Injuries: {injuries_str}
{personal_info}

For EACH workout day: warm-up, main workout (exercises, sets, reps, rest), cool-down, estimated calories.
Also: weekly nutrition tips, recovery recommendations, progressive overload for weeks 2-4."""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"fitness-{uuid.uuid4().hex[:8]}",
            system_message="You are an expert fitness coach. Create detailed, safe, and effective workout plans.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        plan_record = {
            "plan_id": str(uuid.uuid4().hex[:12]),
            "user_id": request.user_id,
            "fitness_level": request.fitness_level,
            "goal": request.goal,
            "available_days": request.available_days,
            "session_duration": request.session_duration,
            "equipment": request.equipment,
            "plan_content": _resp_text(response).strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.fitness_plans.insert_one(plan_record)
        plan_record.pop("_id", None)

        return {
            "plan_id": plan_record["plan_id"],
            "plan": _resp_text(response).strip(),
            "parameters": {
                "fitness_level": request.fitness_level,
                "goal": request.goal,
                "days": request.available_days,
                "duration": request.session_duration,
            },
            "created_at": plan_record["created_at"],
        }
    except Exception as e:
        logger.error(f"Fitness plan error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate fitness plan")


@router.get("/fitness-planner/plans/{user_id}")
async def get_fitness_plans(user_id: str, limit: int = 10):
    plans = (
        await db.fitness_plans.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    )
    return {"plans": plans}


# ── Tool Capabilities ──


class ToolPredictionRequest(BaseModel):
    user_id: str
    feature: str
    tool_id: str
    context: str
    language: str = "English"


@router.post("/tools/predict")
async def tool_predictions(request: ToolPredictionRequest):
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"predict-{uuid.uuid4().hex[:8]}",
            system_message="You are a predictive analytics expert.",
        ).with_model("openai", "gpt-4o")

        prompt = f"Based on this analysis context:\n\n{request.context}\n\nProvide 3-5 predictions (short/medium/long-term) with confidence levels.\nRespond in {request.language}."
        response = await chat.send_message(UserMessage(text=prompt))
        return {"predictions": _resp_text(response).strip(), "feature": request.feature, "tool_id": request.tool_id}
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate predictions")


class ToolAutomationRequest(BaseModel):
    user_id: str
    feature: str
    tool_id: str
    schedule: str = "weekly"


@router.post("/tools/automation")
async def setup_tool_automation(request: ToolAutomationRequest):
    automation = {
        "automation_id": str(uuid.uuid4().hex[:12]),
        "user_id": request.user_id,
        "feature": request.feature,
        "tool_id": request.tool_id,
        "schedule": request.schedule,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "next_run": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    await db.tool_automations.insert_one(automation)
    automation.pop("_id", None)
    return automation


@router.post("/tools/export")
async def export_tool_result(request: Request):
    body = await request.json()
    user_id = body.get("user_id")
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    user = User(**user_doc) if user_doc else None
    if not has_basic_access(user):
        raise HTTPException(status_code=403, detail="Export requires Basic or Premium subscription")
    return {
        "allowed": True,
        "format": body.get("format", "csv"),
        "content": body.get("content", ""),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Voice AI Chat ──

VOICE_COACHING_SCENARIOS = [
    {
        "id": "interview_prep",
        "name": "Interview Prep",
        "icon": "briefcase-outline",
        "color": "#3B82F6",
        "description": "Practice job interviews with AI feedback",
        "system_prompt": "You are a professional interview coach. Conduct a realistic job interview. Ask one question at a time, give feedback on the response, then ask the next. Focus on STAR method, confidence, and clarity. Keep responses under 3 sentences.",
    },
    {
        "id": "public_speaking",
        "name": "Public Speaking",
        "icon": "mic-outline",
        "color": "#8B5CF6",
        "description": "Improve presentation and speech delivery",
        "system_prompt": "You are a public speaking coach. Help the user practice speeches. Give feedback on structure, pacing, engagement. Suggest techniques like pausing, storytelling, and audience connection. Keep responses under 3 sentences.",
    },
    {
        "id": "conflict_resolution",
        "name": "Conflict Resolution",
        "icon": "people-outline",
        "color": "#EF4444",
        "description": "Navigate difficult conversations effectively",
        "system_prompt": "You are a conflict resolution coach. Role-play difficult conversations (with coworkers, family, etc.). Teach active listening, I-statements, and de-escalation. Give feedback on tone and approach. Keep responses under 3 sentences.",
    },
    {
        "id": "sales_pitch",
        "name": "Sales Pitch",
        "icon": "trending-up-outline",
        "color": "#10B981",
        "description": "Sharpen your persuasion and closing skills",
        "system_prompt": "You are a sales coaching expert. Help practice elevator pitches, cold calls, and closing techniques. Give feedback on value proposition, objection handling, and confidence. Keep responses under 3 sentences.",
    },
    {
        "id": "small_talk",
        "name": "Small Talk",
        "icon": "chatbubbles-outline",
        "color": "#F59E0B",
        "description": "Build confidence in casual conversations",
        "system_prompt": "You are a social skills coach. Help practice casual conversations at networking events, parties, or meetups. Teach how to start, maintain, and gracefully exit conversations. Keep responses under 3 sentences.",
    },
    {
        "id": "negotiation",
        "name": "Negotiation",
        "icon": "swap-horizontal-outline",
        "color": "#06B6D4",
        "description": "Master the art of negotiation",
        "system_prompt": "You are a negotiation coach. Role-play salary negotiations, business deals, or everyday negotiations. Teach BATNA, anchoring, and win-win strategies. Give actionable feedback. Keep responses under 3 sentences.",
    },
    {
        "id": "dating",
        "name": "Dating Confidence",
        "icon": "heart-outline",
        "color": "#EC4899",
        "description": "Build confidence for dating conversations",
        "system_prompt": "You are a dating confidence coach. Help practice first-date conversations, flirting, and building genuine connection. Focus on authenticity, humor, and active listening. Keep responses under 3 sentences.",
    },
    {
        "id": "leadership",
        "name": "Leadership Talk",
        "icon": "shield-outline",
        "color": "#6366F1",
        "description": "Practice giving direction and feedback",
        "system_prompt": "You are a leadership communication coach. Help practice giving feedback, running meetings, motivating teams, and handling difficult employee conversations. Keep responses under 3 sentences.",
    },
    {
        "id": "storytelling",
        "name": "Storytelling",
        "icon": "book-outline",
        "color": "#F97316",
        "description": "Learn to tell captivating stories",
        "system_prompt": "You are a storytelling coach. Help craft and deliver compelling personal and professional stories. Teach structure (hook, tension, resolution), emotional beats, and vivid details. Keep responses under 3 sentences.",
    },
    {
        "id": "debate",
        "name": "Debate Practice",
        "icon": "flash-outline",
        "color": "#14B8A6",
        "description": "Sharpen critical thinking and argumentation",
        "system_prompt": "You are a debate coach. Present opposing viewpoints and help build logical arguments. Teach rhetoric, evidence-based reasoning, and rebuttal techniques. Keep responses under 3 sentences.",
    },
    {
        "id": "accent_reduction",
        "name": "Pronunciation",
        "icon": "language-outline",
        "color": "#84CC16",
        "description": "Improve clarity and pronunciation",
        "system_prompt": "You are a pronunciation and diction coach. Help improve clarity, reduce filler words (um, uh), and practice difficult phrases. Give specific phonetic feedback. Keep responses under 3 sentences.",
    },
    {
        "id": "customer_service",
        "name": "Customer Service",
        "icon": "headset-outline",
        "color": "#A855F7",
        "description": "Handle customer interactions professionally",
        "system_prompt": "You are a customer service training coach. Role-play customer complaints, difficult requests, and escalations. Teach empathy, active listening, and resolution skills. Keep responses under 3 sentences.",
    },
]


class VoiceAIChatRequest(BaseModel):
    user_id: str
    text: str
    session_id: Optional[str] = None
    feature: Optional[str] = None
    scenario_id: Optional[str] = None


@router.get("/voice/scenarios")
async def get_voice_scenarios():
    """Return available coaching scenarios."""
    return {"scenarios": [{k: v for k, v in s.items() if k != "system_prompt"} for s in VOICE_COACHING_SCENARIOS]}


@router.post("/voice/chat")
async def voice_ai_chat(request: VoiceAIChatRequest):
    try:
        session = request.session_id or f"voice-{uuid.uuid4().hex[:8]}"

        # Find scenario-specific system prompt
        system_msg = "You are RealAICoach, a helpful AI voice assistant. Provide concise, conversational responses (2-3 sentences)."
        if request.scenario_id:
            scenario = next((s for s in VOICE_COACHING_SCENARIOS if s["id"] == request.scenario_id), None)
            if scenario:
                system_msg = scenario["system_prompt"]
        elif request.feature:
            system_msg = f"You are RealAICoach, an AI voice coach specializing in {request.feature}. Give concise, actionable voice coaching responses."

        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session, system_message=system_msg).with_model(
            "openai", "gpt-4o"
        )

        response = await chat.send_message(UserMessage(text=request.text))

        # Save to voice session history
        await db.voice_sessions.update_one(
            {"session_id": session},
            {
                "$set": {
                    "user_id": request.user_id,
                    "scenario_id": request.scenario_id,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                "$push": {
                    "messages": {"role": "user", "text": request.text, "ts": datetime.now(timezone.utc).isoformat()}
                },
                "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
            },
            upsert=True,
        )
        await db.voice_sessions.update_one(
            {"session_id": session},
            {
                "$push": {
                    "messages": {
                        "role": "assistant",
                        "text": _resp_text(response).strip(),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                }
            },
        )

        return {
            "response": _resp_text(response).strip(),
            "session_id": session,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Voice AI chat error: {e}")
        raise HTTPException(status_code=500, detail="Voice AI processing failed")


@router.get("/voice/sessions/{user_id}")
async def get_voice_sessions(user_id: str, limit: int = 20):
    """Get user's voice coaching session history."""
    sessions = (
        await db.voice_sessions.find({"user_id": user_id}, {"_id": 0})
        .sort("updated_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    return {"sessions": sessions}


# ── Session History ──


@router.get("/session-history/{user_id}")
async def get_session_history(user_id: str, limit: int = 50):
    sessions = []

    convos = (
        await db.conversations.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    )
    for c in convos:
        sessions.append(
            {
                "id": c.get("conversation_id", c.get("id", "")),
                "type": "practice",
                "title": c.get("scenario_title", "Practice Session"),
                "category": c.get("category", "general"),
                "status": c.get("status", "completed"),
                "score": c.get("score", 0),
                "created_at": c.get("created_at", ""),
            }
        )

    searches = await db.ai_searches.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    for s in searches:
        sessions.append(
            {
                "id": s.get("search_id", ""),
                "type": "ai_search",
                "title": f"AI Search: {s.get('query', 'Search')[:60]}",
                "category": "search",
                "status": "completed",
                "score": None,
                "created_at": s.get("created_at", ""),
            }
        )

    plans = await db.fitness_plans.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    for p in plans:
        sessions.append(
            {
                "id": p.get("plan_id", ""),
                "type": "fitness",
                "title": f"Fitness Plan: {p.get('goal', 'Workout')}",
                "category": "fitness",
                "status": "completed",
                "score": None,
                "created_at": p.get("created_at", ""),
            }
        )

    # Sort sessions by created_at, handling both datetime and string types
    def get_sort_key(x):
        created = x.get("created_at", "")
        if isinstance(created, datetime):
            return created.isoformat()
        return str(created) if created else ""

    sessions.sort(key=get_sort_key, reverse=True)
    return {"sessions": sessions[:limit], "total": len(sessions)}
