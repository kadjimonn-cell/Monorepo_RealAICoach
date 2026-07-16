"""Mental Wellness and Legacy routes (Health features moved to health_guide.py)."""

import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes.db import db, EMERGENT_LLM_KEY, get_current_user
from utils.access_control_engine import compute_effective_plan

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Authentication & Owner Resolution ──

def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    """Resolve owner_id from authenticated user or fallback guest ID."""
    if user and hasattr(user, "user_id"):
        return f"auth:{user.user_id}"
    if fallback_user_id:
        return f"guest:{fallback_user_id}"
    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "wellness_auth_required",
            "message": "Login required or provide fallback_user_id for guest wellness tracking",
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


def _extract_user_id(owner_id: str) -> str:
    """Extract raw user_id from owner_id format for DB queries."""
    return owner_id.replace("auth:", "").replace("guest:", "")

# ══════════ MODELS ══════════

# ============== HEALTH COMPANION MODELS ==============
# NOTE: Health Guide (Feature 7) has been moved to /routes/health_guide.py
# All health endpoints now live at /api/health-guide/*
# This file now contains only Mental Wellness features


# ============== MENTAL WELLNESS MODELS ==============


class MoodLogRequest(BaseModel):
    mood: str  # happy, sad, anxious, calm, stressed, etc.
    intensity: int = 5  # 1-10
    triggers: List[str] = []
    notes: Optional[str] = None
    timestamp: Optional[str] = None
    fallback_user_id: Optional[str] = None


class StressCheckRequest(BaseModel):
    current_stress_level: int  # 1-10
    stress_sources: List[str] = []
    physical_symptoms: List[str] = []
    fallback_user_id: Optional[str] = None


class WellnessChatRequest(BaseModel):
    message: str
    chat_type: str = "support"  # support, cbt, mindfulness, journaling
    fallback_user_id: Optional[str] = None


class GuidedPracticeRequest(BaseModel):
    practice_type: str  # breathing, meditation, grounding, gratitude, journaling
    duration_minutes: int = 5
    fallback_user_id: Optional[str] = None


class WellnessInsightRequest(BaseModel):
    period: str = "week"  # day, week, month
    fallback_user_id: Optional[str] = None


# ============== PERSONALIZED LEARNING MODELS ==============
# NOTE: Learning Coach feature (Feature 6) has been moved to /routes/learning_coach.py
# All Learning Coach endpoints now live at /api/learning-coach/*


# ══════════ HEALTH ROUTES ══════════
# NOTE: Health Guide (Feature 7) has been moved to /routes/health_guide.py
# All health endpoints now live at /api/health-guide/*


# ============== PERSONALIZED LEARNING ASSISTANT ==============
# NOTE: Learning Coach feature (Feature 6) has been moved to /routes/learning_coach.py
# All Learning Coach endpoints now live at /api/learning-coach/*


# ══════════ LEARNING ROUTES ══════════
# (Removed - see /routes/learning_coach.py)


# ============== MENTAL & EMOTIONAL WELLNESS PLATFORM ==============
# ══════════ WELLNESS ROUTES ══════════

@router.post("/wellness/mood/log")
async def log_mood(request_obj: Request, payload: MoodLogRequest):
    """Log a mood entry"""
    try:
        # Authenticate and resolve owner
        user = await get_current_user(request_obj)
        owner_id = _resolve_owner_id(user, payload.fallback_user_id)
        tier = await _get_tier(owner_id)
        user_id = _extract_user_id(owner_id)
        
        timestamp = payload.timestamp or datetime.utcnow().isoformat()

        mood_entry = {
            "user_id": user_id,
            "mood": payload.mood,
            "intensity": payload.intensity,
            "triggers": payload.triggers,
            "notes": payload.notes,
            "timestamp": timestamp,
            "date": timestamp[:10],
            "created_at": datetime.utcnow(),
        }

        await db.mood_logs.insert_one(mood_entry)

        # Remove MongoDB _id from response
        mood_entry.pop("_id", None)

        # Get recent mood patterns
        recent_moods = await db.mood_logs.find({"user_id": user_id}).sort("timestamp", -1).limit(7).to_list(7)

        mood_trend = "stable"
        if len(recent_moods) >= 3:
            recent_intensities = [m.get("intensity", 5) for m in recent_moods[:3]]
            older_intensities = (
                [m.get("intensity", 5) for m in recent_moods[3:]] if len(recent_moods) > 3 else recent_intensities
            )
            if sum(recent_intensities) / len(recent_intensities) > sum(older_intensities) / len(older_intensities) + 1:
                mood_trend = "improving"
            elif (
                sum(recent_intensities) / len(recent_intensities) < sum(older_intensities) / len(older_intensities) - 1
            ):
                mood_trend = "declining"

        return {"message": "Mood logged", "entry": mood_entry, "mood_trend": mood_trend, "streak": len(recent_moods), "owner_id": owner_id, "tier": tier}

    except Exception as e:
        logger.error(f"Mood logging failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wellness/mood/{user_id}")
async def get_mood_history(request_obj: Request, user_id: str, days: int = 30):
    """Get mood history"""
    # Authenticate first
    user = await get_current_user(request_obj)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Security: Ensure user can only access their own data
    if user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot access other users' mood history")
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    moods = (
        await db.mood_logs.find({"user_id": user_id, "created_at": {"$gte": cutoff}}, {"_id": 0})
        .sort("timestamp", -1)
        .to_list(100)
    )

    # Calculate stats
    if moods:
        avg_intensity = sum(m.get("intensity", 5) for m in moods) / len(moods)
        mood_counts = {}
        for m in moods:
            mood = m.get("mood", "unknown")
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
        most_common = max(mood_counts, key=mood_counts.get) if mood_counts else "unknown"
    else:
        avg_intensity = 5
        mood_counts = {}
        most_common = "unknown"

    return {
        "moods": moods,
        "period_days": days,
        "stats": {
            "total_entries": len(moods),
            "average_intensity": round(avg_intensity, 1),
            "mood_distribution": mood_counts,
            "most_common_mood": most_common,
        },
    }


@router.post("/wellness/stress-check")
async def stress_check(request_obj: Request, payload: StressCheckRequest):
    """Get stress analysis and coping suggestions"""
    try:
        # Authenticate and resolve owner
        user = await get_current_user(request_obj)
        owner_id = _resolve_owner_id(user, payload.fallback_user_id)
        await _get_tier(owner_id)
        user_id = _extract_user_id(owner_id)
        
        # Get recent mood data
        recent_moods = await db.mood_logs.find({"user_id": user_id}).sort("timestamp", -1).limit(10).to_list(10)

        prompt = f"""Provide compassionate stress support and coping strategies.

Current Stress Level: {payload.current_stress_level}/10
Stress Sources: {", ".join(payload.stress_sources) if payload.stress_sources else "Not specified"}
Physical Symptoms: {", ".join(payload.physical_symptoms) if payload.physical_symptoms else "None reported"}

Recent Mood Pattern: {[m.get("mood") for m in recent_moods[:5]]}

Provide supportive, evidence-based stress management guidance.

Return JSON:
{{
    "stress_assessment": {{
        "level": "{payload.current_stress_level}/10",
        "severity": "mild/moderate/high/severe",
        "interpretation": "What this stress level means"
    }},
    "validation": "Empathetic acknowledgment of their stress",
    "immediate_relief": [
        {{
            "technique": "Quick relief technique",
            "time_required": "2-5 minutes",
            "instructions": "Step by step"
        }}
    ],
    "coping_strategies": [
        {{
            "strategy": "Coping strategy name",
            "why_it_helps": "How it reduces stress",
            "how_to_implement": "Practical steps"
        }}
    ],
    "stress_source_specific": [
        {{
            "source": "Specific stressor",
            "targeted_advice": "Advice for this stressor"
        }}
    ],
    "physical_symptom_relief": ["Ways to address physical symptoms"],
    "when_to_seek_help": "Signs that professional support would be beneficial",
    "encouraging_message": "Supportive closing message"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"stress-{uuid.uuid4()}",
            system_message="You are a compassionate wellness companion providing evidence-based stress support. Be warm, supportive, and practical. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            result = json.loads(response_text)
        except Exception:
            result = {
                "validation": "It's okay to feel stressed. You're taking a positive step by checking in.",
                "immediate_relief": [{"technique": "Deep breathing", "instructions": "Take 5 slow, deep breaths"}],
                "encouraging_message": "Remember, this feeling is temporary. You've got this.",
            }

        # Log stress check
        await db.stress_checks.insert_one(
            {
                "user_id": user_id,
                "stress_level": payload.current_stress_level,
                "sources": payload.stress_sources,
                "symptoms": payload.physical_symptoms,
                "timestamp": datetime.utcnow(),
            }
        )

        return result

    except Exception as e:
        logger.error(f"Stress check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wellness/chat")
async def wellness_chat(request_obj: Request, payload: WellnessChatRequest):
    """Chat with the AI wellness companion"""
    try:
        # Authenticate and resolve owner
        user = await get_current_user(request_obj)
        owner_id = _resolve_owner_id(user, payload.fallback_user_id)
        tier = await _get_tier(owner_id)
        user_id = _extract_user_id(owner_id)
        
        # Get user's recent mood/wellness data
        recent_moods = await db.mood_logs.find({"user_id": user_id}).sort("timestamp", -1).limit(5).to_list(5)

        mood_context = ""
        if recent_moods:
            mood_context = f"Recent moods: {[m.get('mood') for m in recent_moods]}"

        system_prompts = {
            "support": f"""You are a compassionate AI wellness companion. Provide emotional support, active listening, and helpful coping strategies.
{mood_context}
Be warm, empathetic, and non-judgmental. Help the user process their feelings.""",
            "cbt": f"""You are a CBT (Cognitive Behavioral Therapy) informed wellness assistant. Help users identify thought patterns and reframe negative thinking.
{mood_context}
Guide users through CBT techniques like thought records, cognitive restructuring, and behavioral experiments.""",
            "mindfulness": f"""You are a mindfulness and meditation guide. Help users practice present-moment awareness and acceptance.
{mood_context}
Guide breathing exercises, body scans, and mindful awareness practices.""",
            "journaling": f"""You are a reflective journaling companion. Help users explore their thoughts and feelings through guided prompts.
{mood_context}
Ask thoughtful questions that encourage self-reflection and insight.""",
        }

        system_prompt = system_prompts.get(payload.chat_type, system_prompts["support"])

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"wellness-{user_id}", system_message=system_prompt
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=payload.message))

        return {"response": response, "chat_type": payload.chat_type, "supportive": True, "owner_id": owner_id, "tier": tier}

    except Exception as e:
        logger.error(f"Wellness chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wellness/guided-practice")
async def get_guided_practice(request_obj: Request, payload: GuidedPracticeRequest):
    """Get a guided wellness practice (breathing, meditation, etc.)"""
    try:
        # Authenticate and resolve owner (validates access even though we don't store practice requests)
        user = await get_current_user(request_obj)
        owner_id = _resolve_owner_id(user, payload.fallback_user_id)
        await _get_tier(owner_id)
        
        practices = {
            "breathing": "a calming breathing exercise",
            "meditation": "a guided meditation",
            "grounding": "a grounding exercise for anxiety",
            "gratitude": "a gratitude practice",
            "journaling": "guided journaling prompts",
            "body_scan": "a body scan relaxation",
            "visualization": "a peaceful visualization",
        }

        practice_desc = practices.get(payload.practice_type, "a wellness practice")

        prompt = f"""Create {practice_desc} that takes about {payload.duration_minutes} minutes.

Practice Type: {payload.practice_type}
Duration: {payload.duration_minutes} minutes

Create a calming, effective guided practice.

Return JSON:
{{
    "practice_title": "Practice name",
    "type": "{payload.practice_type}",
    "duration_minutes": {payload.duration_minutes},
    "introduction": "Calming introduction to set the scene",
    "steps": [
        {{
            "step_number": 1,
            "instruction": "What to do",
            "duration_seconds": 30,
            "guidance_text": "Words to read or think",
            "cues": ["Timing or transition cues"]
        }}
    ],
    "closing": "Gentle closing to end the practice",
    "benefits": ["Benefits of this practice"],
    "tips_for_beginners": ["Helpful tips"],
    "variations": ["Ways to modify the practice"],
    "follow_up_suggestion": "What to do after"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"practice-{uuid.uuid4()}",
            system_message="You are a calming wellness guide creating soothing, effective practices. Use gentle, peaceful language. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            practice = json.loads(response_text)
        except Exception:
            practice = {
                "practice_title": f"Guided {payload.practice_type.title()}",
                "duration_minutes": payload.duration_minutes,
                "steps": [{"instruction": "Take a moment to breathe and relax"}],
            }

        return practice

    except Exception as e:
        logger.error(f"Guided practice generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wellness/insights")
async def get_wellness_insights(request_obj: Request, payload: WellnessInsightRequest):
    """Get AI-powered emotional wellness insights"""
    try:
        # Authenticate and resolve owner
        user = await get_current_user(request_obj)
        owner_id = _resolve_owner_id(user, payload.fallback_user_id)
        tier = await _get_tier(owner_id)
        user_id = _extract_user_id(owner_id)
        
        days = {"day": 1, "week": 7, "month": 30}.get(payload.period, 7)
        cutoff = datetime.utcnow() - timedelta(days=days)

        moods = await db.mood_logs.find(
            {"user_id": user_id, "created_at": {"$gte": cutoff}}, {"_id": 0}
        ).to_list(100)

        stress_checks = await db.stress_checks.find(
            {"user_id": user_id, "timestamp": {"$gte": cutoff}}, {"_id": 0}
        ).to_list(50)

        prompt = f"""Analyze this user's emotional wellness data and provide supportive insights.

Period: Last {days} days

Mood Logs ({len(moods)} entries):
{json.dumps([{"mood": m.get("mood"), "intensity": m.get("intensity"), "triggers": m.get("triggers", [])} for m in moods[:20]], indent=2)}

Stress Checks ({len(stress_checks)} entries):
{json.dumps([{"level": s.get("stress_level"), "sources": s.get("sources", [])} for s in stress_checks[:10]], indent=2)}

Provide compassionate, helpful insights.

Return JSON:
{{
    "wellness_score": 75,
    "period_summary": "Compassionate summary of their emotional state",
    "mood_patterns": {{
        "dominant_mood": "Most common mood",
        "mood_stability": "stable/fluctuating/improving/declining",
        "pattern_insight": "What patterns reveal"
    }},
    "triggers_analysis": [
        {{
            "trigger": "Common trigger",
            "frequency": "How often",
            "coping_suggestion": "How to handle"
        }}
    ],
    "strengths_observed": ["Positive patterns or resilience shown"],
    "areas_for_support": [
        {{
            "area": "Area that could use attention",
            "gentle_suggestion": "Supportive suggestion"
        }}
    ],
    "recommended_practices": [
        {{
            "practice": "Wellness practice",
            "why": "Why it would help them specifically"
        }}
    ],
    "affirmation": "Personalized encouraging affirmation",
    "professional_support_note": "Gentle note about when professional support might help"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"wellness-insights-{uuid.uuid4()}",
            system_message="You are a compassionate wellness analyst. Provide supportive, non-judgmental insights. Always be encouraging while gently noting areas for growth. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            insights = json.loads(response_text)
        except Exception:
            insights = {
                "wellness_score": 50,
                "period_summary": "Continue tracking your moods to unlock personalized insights.",
                "affirmation": "Every step you take toward self-awareness is valuable. Keep going!",
            }

        insights["period"] = payload.period
        insights["data_points"] = len(moods) + len(stress_checks)
        insights["owner_id"] = owner_id
        insights["tier"] = tier

        return insights

    except Exception as e:
        logger.error(f"Wellness insights failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== AI PERSONAL ECOSYSTEM MANAGER ==============
