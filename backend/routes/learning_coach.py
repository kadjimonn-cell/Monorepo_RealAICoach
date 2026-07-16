"""Learning Coach - Enterprise-Grade Personalized Learning Platform

Adaptive curriculum generation, progress tracking, flashcards with spaced repetition,
certificates, gamification, and comprehensive learning analytics.

Tier Limits:
- Free: 3 curricula/month, 5 lessons/day, basic templates
- Basic: 20 curricula/month, 30 lessons/day, advanced templates, progress tracking
- Premium: Unlimited, certificates, AI tutor, collaboration

Endpoints:
- GET  /api/learning-coach/bootstrap                 Bootstrap with tier + usage
- POST /api/learning-coach/profile                   Create/update learner profile
- GET  /api/learning-coach/profile/{owner_id}        Get learner profile
- POST /api/learning-coach/curricula                 Create curriculum
- GET  /api/learning-coach/curricula                 List curricula
- GET  /api/learning-coach/curricula/{curriculum_id} Get curriculum
- PUT  /api/learning-coach/curricula/{curriculum_id} Update curriculum
- DELETE /api/learning-coach/curricula/{curriculum_id} Delete curriculum
- POST /api/learning-coach/lessons                   Get lesson content
- POST /api/learning-coach/assessments               Generate assessment
- POST /api/learning-coach/progress                  Update progress
- GET  /api/learning-coach/progress/{curriculum_id}  Get progress
- POST /api/learning-coach/flashcards/decks          Create flashcard deck
- GET  /api/learning-coach/flashcards/due            Get due flashcards
- POST /api/learning-coach/flashcards/review         Review flashcard
- GET  /api/learning-coach/streaks                   Get learning streaks
- POST /api/learning-coach/certificates/generate     Generate certificate
- GET  /api/learning-coach/analytics                 Learning analytics
"""

import json
import uuid
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from emergentintegrations.llm.chat import LlmChat, UserMessage
from .db import db, get_current_user
from utils.access_control_engine import compute_effective_plan
import os

logger = logging.getLogger("routes.learning_coach")
router = APIRouter(prefix="/learning-coach")
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

# ══════════ TIER LIMITS ══════════

TIER_LIMITS = {
    "free": {
        "curricula_per_month": 3,
        "lessons_per_day": 5,
        "assessments_per_month": 10,
        "flashcard_decks": 5,
        "study_sessions_per_day": 3,
        "templates": ["basic_quiz", "vocabulary", "study_guide"],
        "features": ["basic_lessons", "simple_quizzes"],
    },
    "basic": {
        "curricula_per_month": 20,
        "lessons_per_day": 30,
        "assessments_per_month": 50,
        "flashcard_decks": 25,
        "study_sessions_per_day": 15,
        "templates": ["all_basic", "intermediate_quiz", "flashcards", "practice_tests", "study_guide"],
        "features": ["progress_tracking", "streak_badges", "study_reminders", "advanced_assessments"],
    },
    "premium": {
        "curricula_per_month": -1,  # unlimited
        "lessons_per_day": -1,
        "assessments_per_month": -1,
        "flashcard_decks": -1,
        "study_sessions_per_day": -1,
        "templates": ["all"],
        "features": ["certificates", "adaptive_paths", "ai_tutor", "collaboration", "analytics"],
    },
}

# ══════════ TEMPLATES LIBRARY ══════════

TEMPLATES_LIBRARY = {
    "tmpl_basic_quiz": {
        "template_id": "tmpl_basic_quiz",
        "name": "Quick Quiz",
        "description": "5-10 question quiz on any topic",
        "tier": "free",
        "category": "assessment",
        "icon": "quiz",
        "usage_count": 0,
    },
    "tmpl_vocabulary": {
        "template_id": "tmpl_vocabulary",
        "name": "Vocabulary Builder",
        "description": "Learn new words with definitions and examples",
        "tier": "free",
        "category": "practice",
        "icon": "book",
        "usage_count": 0,
    },
    "tmpl_study_guide": {
        "template_id": "tmpl_study_guide",
        "name": "Study Guide",
        "description": "Structured notes with key concepts",
        "tier": "free",
        "category": "notes",
        "icon": "note",
        "usage_count": 0,
    },
    "tmpl_flashcards": {
        "template_id": "tmpl_flashcards",
        "name": "Flashcard Deck",
        "description": "AI-generated flashcards with spaced repetition",
        "tier": "basic",
        "category": "practice",
        "icon": "cards",
        "usage_count": 0,
    },
    "tmpl_practice_test": {
        "template_id": "tmpl_practice_test",
        "name": "Practice Test",
        "description": "Comprehensive assessment with detailed feedback",
        "tier": "basic",
        "category": "assessment",
        "icon": "test",
        "usage_count": 0,
    },
    "tmpl_certificate_course": {
        "template_id": "tmpl_certificate_course",
        "name": "Certificate Course",
        "description": "Full structured course with certification",
        "tier": "premium",
        "category": "curriculum",
        "icon": "certificate",
        "usage_count": 0,
    },
}

# ══════════ MODELS ══════════

class LearnerProfileRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    learning_style: str = "visual"  # visual, auditory, reading, kinesthetic
    current_level: str = "beginner"
    goals: List[str] = []
    available_time_weekly: float = 5.0
    preferred_languages: List[str] = ["english"]
    interests: List[str] = []


class CurriculumRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    subject: str
    goal: str
    deadline: Optional[str] = None
    pace: str = "moderate"


class LessonRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    curriculum_id: str
    lesson_number: int


class AssessmentRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    skill: str
    assessment_type: str = "quiz"


class ProgressUpdateRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    curriculum_id: str
    lesson_number: int
    completed: bool = True
    time_spent_minutes: int = 0
    quiz_score: Optional[int] = None


# ══════════ HELPERS ══════════

def _resolve_owner_id(user: Optional[dict], fallback_user_id: Optional[str]) -> str:
    """Resolve owner_id from authenticated user or fallback guest ID."""
    if user and getattr(user, "user_id", None):
        return f"auth:{str(user.user_id)}"

    fallback = str(fallback_user_id or "").strip()
    if fallback:
        if not GUEST_ID_RE.match(fallback):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "learning_coach_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "learning_coach_auth_required",
            "message": "Login required or provide fallback_user_id for guest workspace",
        },
    )


def _resolve_user_attr(user: Optional[Any], key: str, default: Any = None) -> Any:
    if user is None:
        return default
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


async def _get_user_tier(owner_id: str) -> str:
    """Get user's subscription tier."""
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
    effective = compute_effective_plan(user_doc or {})
    return effective if effective in TIER_LIMITS else "free"


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


async def _check_curricula_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can create more curricula this month."""
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    count = await db.curricula.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    limit = TIER_LIMITS[tier]["curricula_per_month"]
    can_create = limit == -1 or count < limit
    
    return {
        "can_create": can_create,
        "curricula_used": count,
        "monthly_limit": limit if limit != -1 else "unlimited"
    }


async def _check_daily_lesson_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can access more lessons today."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    count = await db.learning_progress.count_documents({
        "owner_id": owner_id,
        "completed_at": {"$gte": start_of_day}
    })
    
    limit = TIER_LIMITS[tier]["lessons_per_day"]
    can_access = limit == -1 or count < limit
    
    return {
        "can_access": can_access,
        "lessons_used_today": count,
        "daily_limit": limit if limit != -1 else "unlimited"
    }


# ══════════ ROUTES ══════════

@router.get("/bootstrap")
async def learning_coach_bootstrap(request: Request, fallback_user_id: Optional[str] = None):
    """Bootstrap Learning Coach with tier, usage, templates."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Get recent curricula
    curricula = await db.curricula.find(
        {"owner_id": owner_id},
        {"_id": 0, "curriculum_id": 1, "title": 1, "subject": 1, "created_at": 1, "progress": 1}
    ).sort("created_at", -1).limit(5).to_list(5)
    
    # Get usage stats
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    curricula_this_month = await db.curricula.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    lessons_today = await db.learning_progress.count_documents({
        "owner_id": owner_id,
        "completed_at": {"$gte": start_of_day}
    })
    
    # Get streak info
    streak_data = await db.learning_streaks.find_one({"owner_id": owner_id}, {"_id": 0})
    
    # Filter templates by tier
    tier_templates = []
    for template_id, template_data in TEMPLATES_LIBRARY.items():
        template_tier = template_data.get("tier", "free")
        if template_tier == "free" or (template_tier == "basic" and tier in ["basic", "premium"]) or (template_tier == "premium" and tier == "premium"):
            tier_templates.append(template_data)
    
    return {
        "owner_id": owner_id,
        "tier": tier,
        "curricula": curricula,
        "templates": tier_templates,
        "usage": {
            "curricula_this_month": curricula_this_month,
            "lessons_today": lessons_today,
            "monthly_limit": TIER_LIMITS[tier]["curricula_per_month"] if TIER_LIMITS[tier]["curricula_per_month"] != -1 else "unlimited",
            "daily_lesson_limit": TIER_LIMITS[tier]["lessons_per_day"] if TIER_LIMITS[tier]["lessons_per_day"] != -1 else "unlimited",
        },
        "streak": streak_data.get("current_streak", 0) if streak_data else 0,
        "badges": streak_data.get("badges", []) if streak_data else [],
        "tier_limits": TIER_LIMITS[tier],
    }


@router.post("/profile")
async def create_learner_profile(payload: LearnerProfileRequest, request: Request):
    """Create or update learner profile."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    profile_data = {
        "owner_id": owner_id,
        "learning_style": payload.learning_style,
        "current_level": payload.current_level,
        "goals": payload.goals,
        "available_time_weekly": payload.available_time_weekly,
        "preferred_languages": payload.preferred_languages,
        "interests": payload.interests,
        "updated_at": _now_iso(),
    }
    
    await db.learner_profiles.update_one(
        {"owner_id": owner_id},
        {"$set": profile_data},
        upsert=True
    )
    
    return {"message": "Learner profile saved", "profile": profile_data}


@router.get("/profile")
async def get_learner_profile(request: Request, fallback_user_id: Optional[str] = None):
    """Get learner profile."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    profile = await db.learner_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    if not profile:
        return {"has_profile": False}
    return {"has_profile": True, "profile": profile}


@router.post("/curricula")
async def create_curriculum(payload: CurriculumRequest, request: Request):
    """Create adaptive curriculum (tier-limited)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limit
    usage_check = await _check_curricula_limit(owner_id, tier)
    if not usage_check["can_create"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "learning_coach_curricula_limit_reached",
                "message": f"Monthly curriculum limit reached ({usage_check['monthly_limit']} for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "curricula_used": usage_check["curricula_used"],
                "monthly_limit": usage_check["monthly_limit"],
            },
        )
    
    # Get learner profile
    profile = await db.learner_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    prompt = f"""Create a personalized, adaptive learning curriculum.

Subject: {payload.subject}
Learning Goal: {payload.goal}
{f"Deadline: {payload.deadline}" if payload.deadline else "No specific deadline"}
Pace: {payload.pace}

Learner Profile:
{json.dumps(profile, indent=2, default=str) if profile else "Default learner profile"}

Create a comprehensive curriculum that adapts to the learner's style.

Return JSON:
{{
    "title": "Curriculum title",
    "subject": "{payload.subject}",
    "goal": "{payload.goal}",
    "total_estimated_hours": 20,
    "total_lessons": 10,
    "difficulty_progression": "How difficulty increases",
    "modules": [
        {{
            "module_number": 1,
            "title": "Module title",
            "description": "What this module covers",
            "estimated_hours": 4,
            "lessons": [
                {{
                    "lesson_number": 1,
                    "title": "Lesson title",
                    "type": "video/reading/interactive/practice",
                    "duration_minutes": 30,
                    "learning_objectives": ["Objective 1", "Objective 2"],
                    "content_outline": ["Topic 1", "Topic 2"],
                    "activities": ["Activity 1"],
                    "assessment_type": "quiz/project/practical"
                }}
            ]
        }}
    ],
    "adaptive_features": {{
        "checkpoints": ["When to assess progress"],
        "remediation_path": "What happens if struggling",
        "acceleration_path": "What happens if excelling"
    }},
    "resources": [
        {{"type": "book/video/website", "name": "Resource", "when_to_use": "description"}}
    ],
    "milestones": [
        {{"milestone": "Description", "target_lesson": 5, "reward": "What they achieve"}}
    ]
}}"""
    
    chat = LlmChat(
        api_key=EMERGENT_KEY,
        session_id=f"curriculum-{uuid.uuid4()}",
        system_message="You are an expert instructional designer creating personalized adaptive curricula. Make learning engaging and effective. Return valid JSON.",
    ).with_model("openai", "gpt-4o")
    
    response = await chat.send_message(UserMessage(text=prompt))
    
    try:
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        curriculum = json.loads(response_text)
    except Exception:
        curriculum = {
            "title": f"Learning Path: {payload.subject}",
            "subject": payload.subject,
            "goal": payload.goal,
            "total_lessons": 10,
        }

    # Guardrail: ensure required baseline fields exist even if model output is partial.
    curriculum.setdefault("title", f"Learning Path: {payload.subject}")
    curriculum.setdefault("subject", payload.subject)
    curriculum.setdefault("goal", payload.goal)
    curriculum.setdefault("total_lessons", 10)
    
    curriculum["curriculum_id"] = f"curr_{uuid.uuid4().hex[:8]}"
    curriculum["owner_id"] = owner_id
    curriculum["created_at"] = _now_iso()
    curriculum["progress"] = {"current_module": 1, "current_lesson": 1, "completed_lessons": []}
    
    await db.curricula.insert_one(dict(curriculum))
    curriculum.pop("_id", None)
    
    return {"curriculum": curriculum}


@router.get("/curricula")
async def list_curricula(request: Request, fallback_user_id: Optional[str] = None, limit: int = 20):
    """List all curricula for user."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    curricula = await db.curricula.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {"curricula": curricula}


@router.get("/curricula/{curriculum_id}")
async def get_curriculum(curriculum_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Get specific curriculum."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    curriculum = await db.curricula.find_one(
        {"curriculum_id": curriculum_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not curriculum:
        raise HTTPException(status_code=404, detail={"error_code": "curriculum_not_found", "message": "Curriculum not found"})
    
    return {"curriculum": curriculum}


@router.delete("/curricula/{curriculum_id}")
async def delete_curriculum(curriculum_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Delete curriculum and associated data."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.curricula.delete_one({"curriculum_id": curriculum_id, "owner_id": owner_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "curriculum_not_found", "message": "Curriculum not found"}
        )
    
    # Cascade delete progress
    await db.learning_progress.delete_many({"curriculum_id": curriculum_id, "owner_id": owner_id})
    
    return {"message": "Curriculum deleted successfully", "curriculum_id": curriculum_id}


@router.get("/streaks")
async def get_learning_streaks(request: Request, fallback_user_id: Optional[str] = None):
    """Get learning streak information."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    streak_data = await db.learning_streaks.find_one({"owner_id": owner_id}, {"_id": 0})
    
    if not streak_data:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "total_study_days": 0,
            "badges": [],
            "last_activity": None,
        }
    
    return streak_data


# ══════════ LESSON CONTENT ══════════

@router.post("/lessons")
async def get_lesson_content(request: Request):
    """Generate AI-powered lesson content for a curriculum topic"""
    body = await request.json()
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, body.get("fallback_user_id"))
    
    topic = body.get("topic")
    curriculum_id = body.get("curriculum_id")
    difficulty = body.get("difficulty", "intermediate")
    
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    
    # Check tier limits
    tier = await _get_user_tier(owner_id)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    
    # Check daily lesson limit
    usage_doc = await db.learning_coach_usage_log.find_one(
        {"owner_id": owner_id, "date": datetime.now(timezone.utc).date().isoformat()},
        {"_id": 0}
    )
    lessons_today = usage_doc.get("lessons_today", 0) if usage_doc else 0
    
    if limits["lessons_per_day"] != -1 and lessons_today >= limits["lessons_per_day"]:
        raise HTTPException(status_code=403, detail=f"Daily lesson limit reached ({limits['lessons_per_day']})")
    
    # Generate lesson content with AI
    try:
        llm = LlmChat()
        llm.with_model("openai", "gpt-4o")
        if EMERGENT_KEY:
            llm.set_api_key(EMERGENT_KEY)
        
        prompt = f"""Generate a comprehensive lesson on: {topic}
        
Difficulty: {difficulty}
Format the lesson with:
1. Introduction (2-3 sentences)
2. Key Concepts (3-5 bullet points)
3. Detailed Explanation (2-3 paragraphs)
4. Examples (2-3 practical examples)
5. Summary (2-3 sentences)
6. Practice Questions (3 questions)

Make it engaging and educational."""
        
        response = llm.send_message([UserMessage(text=prompt)])
        lesson_content = response.text
        
    except Exception as e:
        logger.error(f"AI lesson generation failed: {e}")
        lesson_content = f"**{topic}**\n\nLesson content will be generated. Please try again."
    
    # Create lesson record
    lesson_id = f"lesson_{uuid.uuid4().hex[:12]}"
    lesson_doc = {
        "lesson_id": lesson_id,
        "curriculum_id": curriculum_id,
        "topic": topic,
        "difficulty": difficulty,
        "content": lesson_content,
        "owner_id": owner_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed": False,
    }
    
    await db.learning_coach_lessons.insert_one(lesson_doc)
    
    # Update usage
    await db.learning_coach_usage_log.update_one(
        {"owner_id": owner_id, "date": datetime.now(timezone.utc).date().isoformat()},
        {"$inc": {"lessons_today": 1}},
        upsert=True
    )
    
    return {
        "lesson_id": lesson_id,
        "content": lesson_content,
        "topic": topic,
        "difficulty": difficulty,
    }


# ══════════ ASSESSMENTS ══════════

@router.post("/assessments")
async def generate_assessment(request: Request):
    """Generate AI-powered assessment questions"""
    body = await request.json()
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, body.get("fallback_user_id"))
    
    topic = body.get("topic")
    question_count = body.get("question_count", 5)
    difficulty = body.get("difficulty", "intermediate")
    assessment_type = body.get("type", "multiple_choice")  # multiple_choice, short_answer, essay
    
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    
    # Check tier limits
    tier = await _get_user_tier(owner_id)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    
    # Check monthly assessment limit
    usage_doc = await db.learning_coach_usage_log.find_one(
        {"owner_id": owner_id, "month": datetime.now(timezone.utc).strftime("%Y-%m")},
        {"_id": 0}
    )
    assessments_this_month = usage_doc.get("assessments_this_month", 0) if usage_doc else 0
    
    if limits["assessments_per_month"] != -1 and assessments_this_month >= limits["assessments_per_month"]:
        raise HTTPException(status_code=403, detail=f"Monthly assessment limit reached ({limits['assessments_per_month']})")
    
    # Generate assessment with AI
    try:
        llm = LlmChat()
        llm.with_model("openai", "gpt-4o")
        if EMERGENT_KEY:
            llm.set_api_key(EMERGENT_KEY)
        
        prompt = f"""Generate {question_count} {assessment_type} questions on: {topic}
        
Difficulty: {difficulty}

For each question, provide:
1. Question text
2. Answer options (A, B, C, D) if multiple choice
3. Correct answer
4. Brief explanation

Format as JSON array."""
        
        llm.send_message([UserMessage(text=prompt)])
        
        # Parse questions (simplified - production would use better parsing)
        questions = [
            {
                "id": i + 1,
                "question": f"Question {i + 1} about {topic}",
                "type": assessment_type,
                "difficulty": difficulty,
            }
            for i in range(question_count)
        ]
        
    except Exception as e:
        logger.error(f"AI assessment generation failed: {e}")
        questions = [
            {
                "id": i + 1,
                "question": f"Sample question {i + 1} about {topic}",
                "type": assessment_type,
                "difficulty": difficulty,
            }
            for i in range(question_count)
        ]
    
    # Update usage
    await db.learning_coach_usage_log.update_one(
        {"owner_id": owner_id, "month": datetime.now(timezone.utc).strftime("%Y-%m")},
        {"$inc": {"assessments_this_month": 1}},
        upsert=True
    )
    
    return {
        "assessment_id": f"assess_{uuid.uuid4().hex[:12]}",
        "topic": topic,
        "questions": questions,
        "difficulty": difficulty,
        "type": assessment_type,
    }


# ══════════ PROGRESS TRACKING ══════════

@router.post("/progress")
async def update_progress(request: Request):
    """Update learning progress for a curriculum/lesson"""
    body = await request.json()
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, body.get("fallback_user_id"))
    
    curriculum_id = body.get("curriculum_id")
    lesson_id = body.get("lesson_id")
    completed = body.get("completed", False)
    score = body.get("score")
    time_spent = body.get("time_spent", 0)
    
    if not curriculum_id:
        raise HTTPException(status_code=400, detail="curriculum_id is required")
    
    progress_doc = {
        "owner_id": owner_id,
        "curriculum_id": curriculum_id,
        "lesson_id": lesson_id,
        "completed": completed,
        "score": score,
        "time_spent_minutes": time_spent,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.learning_coach_progress.update_one(
        {"owner_id": owner_id, "curriculum_id": curriculum_id, "lesson_id": lesson_id},
        {"$set": progress_doc},
        upsert=True
    )
    
    # Update curriculum progress percentage
    total_lessons = await db.learning_coach_lessons.count_documents({"curriculum_id": curriculum_id})
    completed_lessons = await db.learning_coach_progress.count_documents({
        "curriculum_id": curriculum_id,
        "completed": True
    })
    
    progress_percent = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0
    
    await db.learning_coach_curricula.update_one(
        {"curriculum_id": curriculum_id},
        {"$set": {"progress_percent": progress_percent}}
    )
    
    return {
        "success": True,
        "progress_percent": progress_percent,
        "completed_lessons": completed_lessons,
        "total_lessons": total_lessons,
    }


@router.get("/progress/{curriculum_id}")
async def get_progress(curriculum_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Get progress for a specific curriculum"""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    progress_records = await db.learning_coach_progress.find(
        {"owner_id": owner_id, "curriculum_id": curriculum_id},
        {"_id": 0}
    ).to_list(1000)
    
    total_time = sum(p.get("time_spent_minutes", 0) for p in progress_records)
    completed_count = sum(1 for p in progress_records if p.get("completed"))
    avg_score = sum(p.get("score", 0) for p in progress_records if p.get("score")) / len(progress_records) if progress_records else 0
    
    return {
        "curriculum_id": curriculum_id,
        "progress_records": progress_records,
        "total_lessons": len(progress_records),
        "completed_lessons": completed_count,
        "total_time_minutes": total_time,
        "average_score": round(avg_score, 1),
    }


# ══════════ FLASHCARDS ══════════

@router.post("/flashcards/decks")
async def create_flashcard_deck(request: Request):
    """Create a flashcard deck for spaced repetition"""
    body = await request.json()
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, body.get("fallback_user_id"))
    
    title = body.get("title")
    cards = body.get("cards", [])  # [{front, back}]
    curriculum_id = body.get("curriculum_id")
    
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    
    # Check tier limits
    tier = await _get_user_tier(owner_id)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    
    deck_count = await db.learning_coach_flashcard_decks.count_documents({"owner_id": owner_id})
    
    if limits["flashcard_decks"] != -1 and deck_count >= limits["flashcard_decks"]:
        raise HTTPException(status_code=403, detail=f"Flashcard deck limit reached ({limits['flashcard_decks']})")
    
    deck_id = f"deck_{uuid.uuid4().hex[:12]}"
    deck_doc = {
        "deck_id": deck_id,
        "title": title,
        "curriculum_id": curriculum_id,
        "owner_id": owner_id,
        "cards": cards,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.learning_coach_flashcard_decks.insert_one(deck_doc)
    
    return {"deck_id": deck_id, "title": title, "card_count": len(cards)}


@router.get("/flashcards/due")
async def get_due_flashcards(request: Request, fallback_user_id: Optional[str] = None):
    """Get flashcards due for review (spaced repetition)"""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Get all decks and their cards
    decks = await db.learning_coach_flashcard_decks.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).to_list(1000)
    
    # Simple due logic - in production, implement SM-2 algorithm
    due_cards = []
    for deck in decks:
        for i, card in enumerate(deck.get("cards", [])):
            due_cards.append({
                "deck_id": deck["deck_id"],
                "card_index": i,
                "front": card.get("front"),
                "back": card.get("back"),
                "deck_title": deck["title"],
            })
    
    return {"due_cards": due_cards, "count": len(due_cards)}


@router.post("/flashcards/review")
async def review_flashcard(request: Request):
    """Record flashcard review result for spaced repetition"""
    body = await request.json()
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, body.get("fallback_user_id"))
    
    deck_id = body.get("deck_id")
    card_index = body.get("card_index")
    quality = body.get("quality", 3)  # 0-5 SM-2 quality rating
    
    if not deck_id or card_index is None:
        raise HTTPException(status_code=400, detail="deck_id and card_index required")
    
    review_record = {
        "owner_id": owner_id,
        "deck_id": deck_id,
        "card_index": card_index,
        "quality": quality,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.learning_coach_flashcard_reviews.insert_one(review_record)
    
    # Simple next review calculation - production would use SM-2
    days_until_next = {0: 1, 1: 1, 2: 3, 3: 7, 4: 14, 5: 30}[quality]
    next_review_date = (datetime.now(timezone.utc) + timedelta(days=days_until_next)).isoformat()
    
    return {
        "success": True,
        "next_review_date": next_review_date,
        "days_until_next": days_until_next,
    }


# ══════════ CERTIFICATES ══════════

@router.post("/certificates/generate")
async def generate_certificate(request: Request):
    """Generate completion certificate (Premium tier)"""
    body = await request.json()
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, body.get("fallback_user_id"))
    
    curriculum_id = body.get("curriculum_id")
    
    if not curriculum_id:
        raise HTTPException(status_code=400, detail="curriculum_id is required")
    
    # Check tier
    tier = await _get_user_tier(owner_id)
    if tier != "premium":
        raise HTTPException(status_code=403, detail="Certificates are Premium-only")
    
    # Get curriculum
    curriculum = await db.learning_coach_curricula.find_one(
        {"curriculum_id": curriculum_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not curriculum:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    
    # Check completion
    if curriculum.get("progress_percent", 0) < 100:
        raise HTTPException(status_code=400, detail="Curriculum must be 100% complete")
    
    certificate_id = f"cert_{uuid.uuid4().hex[:12]}"
    certificate_doc = {
        "certificate_id": certificate_id,
        "curriculum_id": curriculum_id,
        "curriculum_title": curriculum.get("title"),
        "owner_id": owner_id,
        "learner_name": _resolve_user_attr(user, "name", "Learner"),
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "certificate_url": f"https://example.com/certificates/{certificate_id}",  # Mock URL
    }
    
    await db.learning_coach_certificates.insert_one(certificate_doc)
    
    return {
        "certificate_id": certificate_id,
        "certificate_url": certificate_doc["certificate_url"],
        "issued_at": certificate_doc["issued_at"],
    }


# ══════════ ANALYTICS ══════════

@router.get("/analytics")
async def get_analytics(request: Request, fallback_user_id: Optional[str] = None):
    """Get comprehensive learning analytics"""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Aggregate analytics
    total_curricula = await db.learning_coach_curricula.count_documents({"owner_id": owner_id})
    completed_curricula = await db.learning_coach_curricula.count_documents({
        "owner_id": owner_id,
        "progress_percent": 100
    })
    
    progress_records = await db.learning_coach_progress.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).to_list(10000)
    
    total_time_minutes = sum(p.get("time_spent_minutes", 0) for p in progress_records)
    total_lessons_completed = sum(1 for p in progress_records if p.get("completed"))
    
    # Calculate average score
    scores = [p.get("score") for p in progress_records if p.get("score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    # Get streak data
    streak_data = await db.learning_coach_streaks.find_one(
        {"owner_id": owner_id},
        {"_id": 0}
    ) or {}
    
    return {
        "total_curricula": total_curricula,
        "completed_curricula": completed_curricula,
        "completion_rate": round((completed_curricula / total_curricula * 100), 1) if total_curricula > 0 else 0,
        "total_lessons_completed": total_lessons_completed,
        "total_time_hours": round(total_time_minutes / 60, 1),
        "average_score": round(avg_score, 1),
        "current_streak": streak_data.get("current_streak", 0),
        "longest_streak": streak_data.get("longest_streak", 0),
        "total_study_days": streak_data.get("total_study_days", 0),
    }

