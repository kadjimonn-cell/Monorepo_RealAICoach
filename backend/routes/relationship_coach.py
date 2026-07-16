"""
Feature 12: Relationship Coach - Enterprise-Grade Relationship Advisor

Comprehensive relationship coaching platform with AI-powered advice, date ideas,
gift recommendations, important date reminders, conversation starters, and health assessments.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import os

from .db import db, get_current_user
from emergentintegrations.llm.chat import LlmChat, UserMessage
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/relationship-coach", tags=["relationship-coach"])

EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY")

# ── Tier Limits ──

TIER_LIMITS = {
    "free": {
        "ai_sessions_per_month": 10,
        "important_dates": 3,
        "assessments_per_month": 2,
    },
    "basic": {
        "ai_sessions_per_month": 50,
        "important_dates": 20,
        "assessments_per_month": 10,
    },
    "premium": {
        "ai_sessions_per_month": -1,  # unlimited
        "important_dates": -1,
        "assessments_per_month": -1,
    },
}


import re

GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")


# ── Helper Functions ──


def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    """Resolve user ID from authenticated user or fallback."""
    if user and hasattr(user, "user_id"):
        return f"auth:{user.user_id}"

    if not fallback_user_id:
        raise HTTPException(
            status_code=401,
            detail={"error": "auth_required", "message": "Login required or provide fallback_user_id"},
        )

    if not GUEST_ID_RE.match(fallback_user_id):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_guest_id", "message": "fallback_user_id must match ^user_[a-zA-Z0-9_-]{12,80}$"},
        )

    return f"guest:{fallback_user_id}"


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
    effective = compute_effective_plan(user_doc or {})
    return effective if effective in TIER_LIMITS else "free"


async def _check_ai_usage(owner_id: str, tier: str) -> dict:
    """Check AI usage against tier limits."""
    limit = TIER_LIMITS[tier]["ai_sessions_per_month"]
    
    if limit == -1:
        return {"used": 0, "limit": -1, "remaining": -1}
    
    # Count usage this month
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    used = await db.relationship_ai_usage.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": month_start.isoformat()},
    })
    
    if used >= limit:
        raise HTTPException(
            status_code=403,
            detail=f"AI session limit reached for {tier} tier ({used}/{limit}). Upgrade for more."
        )
    
    return {"used": used, "limit": limit, "remaining": limit - used}


async def _log_ai_usage(owner_id: str, session_type: str):
    """Log AI usage for tier enforcement."""
    await db.relationship_ai_usage.insert_one({
        "usage_id": str(uuid4()),
        "owner_id": owner_id,
        "session_type": session_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ── Pydantic Models ──


class RelationshipProfile(BaseModel):
    relationship_status: str
    partner_name: Optional[str] = None
    anniversary_date: Optional[str] = None
    challenges: Optional[List[str]] = None
    goals: Optional[List[str]] = None
    fallback_user_id: Optional[str] = None


class AdviceRequest(BaseModel):
    situation: str
    context: Optional[str] = None
    relationship_stage: Optional[str] = "established"
    fallback_user_id: Optional[str] = None


class DateIdeasRequest(BaseModel):
    budget: Optional[str] = "medium"
    preferences: Optional[List[str]] = None
    location: Optional[str] = None
    mood: Optional[str] = "romantic"
    fallback_user_id: Optional[str] = None


class GiftIdeasRequest(BaseModel):
    occasion: str
    budget: Optional[str] = "medium"
    partner_interests: Optional[List[str]] = None
    personality: Optional[str] = None
    fallback_user_id: Optional[str] = None


class ImportantDate(BaseModel):
    title: str
    date: str
    category: str  # anniversary, birthday, special_occasion
    reminder_days: Optional[int] = 7
    notes: Optional[str] = None
    fallback_user_id: Optional[str] = None


class ConversationStartersRequest(BaseModel):
    relationship_stage: Optional[str] = "established"
    mood: Optional[str] = "deep"
    topic_preference: Optional[str] = None
    fallback_user_id: Optional[str] = None


class AssessmentRequest(BaseModel):
    communication_score: int = Field(ge=1, le=10)
    trust_score: int = Field(ge=1, le=10)
    intimacy_score: int = Field(ge=1, le=10)
    conflict_resolution_score: int = Field(ge=1, le=10)
    shared_goals_score: int = Field(ge=1, le=10)
    notes: Optional[str] = None
    fallback_user_id: Optional[str] = None


class CommunicationTipsRequest(BaseModel):
    scenario: str  # difficult_conversation, expressing_needs, active_listening
    context: Optional[str] = None
    fallback_user_id: Optional[str] = None


# ── API Endpoints ──


@router.get("/bootstrap")
async def bootstrap(request: Request, fallback_user_id: Optional[str] = None):
    """Get initial data: tier, limits, usage, profile status."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_tier(owner_id)
    
    # Get usage stats
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ai_usage = await db.relationship_ai_usage.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": month_start.isoformat()},
    })
    
    important_dates_count = await db.relationship_important_dates.count_documents({"owner_id": owner_id})
    
    # Check if profile exists
    profile = await db.relationship_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    return {
        "owner_id": owner_id,
        "tier": tier,
        "limits": TIER_LIMITS[tier],
        "usage": {
            "ai_sessions_this_month": ai_usage,
            "important_dates": important_dates_count,
        },
        "profile_exists": profile is not None,
    }


# ── Profile Management ──


@router.post("/profile")
async def create_or_update_profile(payload: RelationshipProfile, request: Request):
    """Create or update relationship profile."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    existing = await db.relationship_profiles.find_one({"owner_id": owner_id})
    
    profile_data = {
        "owner_id": owner_id,
        "relationship_status": payload.relationship_status,
        "partner_name": payload.partner_name,
        "anniversary_date": payload.anniversary_date,
        "challenges": payload.challenges or [],
        "goals": payload.goals or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    if existing:
        await db.relationship_profiles.update_one(
            {"owner_id": owner_id},
            {"$set": profile_data}
        )
        return {"message": "Profile updated", "profile": profile_data}
    else:
        profile_data["created_at"] = datetime.now(timezone.utc).isoformat()
        insert_data = {**profile_data}  # copy before insert to prevent ObjectId mutation
        await db.relationship_profiles.insert_one(insert_data)
        return {"message": "Profile created", "profile": profile_data}


@router.get("/profile")
async def get_profile(request: Request, fallback_user_id: Optional[str] = None):
    """Get relationship profile."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    profile = await db.relationship_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {"profile": profile}


# ── AI Relationship Advisor ──


@router.post("/advice")
async def get_relationship_advice(payload: AdviceRequest, request: Request):
    """Get AI-powered relationship advice."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    
    # Check usage limits
    await _check_ai_usage(owner_id, tier)
    
    # Generate advice using AI
    prompt = f"""Situation: {payload.situation}
    
Context: {payload.context or 'Not provided'}
Relationship Stage: {payload.relationship_stage}

Provide empathetic, actionable relationship advice. Include:
1. Understanding of the situation
2. 2-3 specific action items
3. Communication tips
4. Long-term perspective

Keep advice practical, non-judgmental, and supportive."""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"relationship-advice-{uuid4().hex[:10]}",
                system_message="You are a professional relationship counselor with expertise in communication, conflict resolution, and emotional intelligence. Provide empathetic, actionable advice."
            )
            .with_model("openai", "gpt-4o")
        )
        
        advice = await chat.send_message(UserMessage(text=prompt))
        
        # Log session
        session_id = str(uuid4())
        await db.relationship_advice_sessions.insert_one({
            "session_id": session_id,
            "owner_id": owner_id,
            "situation": payload.situation,
            "advice": advice,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        await _log_ai_usage(owner_id, "advice")
        
        return {
            "session_id": session_id,
            "advice": advice,
            "situation": payload.situation,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI advice generation failed: {str(e)}")


# ── Date Ideas Generator ──


@router.post("/date-ideas")
async def generate_date_ideas(payload: DateIdeasRequest, request: Request):
    """Generate AI-powered date ideas."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    
    await _check_ai_usage(owner_id, tier)
    
    preferences_str = ", ".join(payload.preferences) if payload.preferences else "No specific preferences"
    
    prompt = f"""Generate 4-5 unique, creative date ideas with these parameters:
    
Budget: {payload.budget}
Preferences: {preferences_str}
Location: {payload.location or 'Any'}
Mood: {payload.mood}

For each date idea, provide:
- Title
- Description (2-3 sentences)
- Estimated cost
- Why it's special
- Practical tips

Format as a numbered list. Be creative and thoughtful!"""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"date-ideas-{uuid4().hex[:10]}",
                system_message="You are a creative date planner helping couples create memorable experiences. Suggest unique, thoughtful date ideas."
            )
            .with_model("openai", "gpt-4o")
        )
        
        ideas = await chat.send_message(UserMessage(text=prompt))
        
        # Save to history
        idea_id = str(uuid4())
        await db.relationship_dates.insert_one({
            "idea_id": idea_id,
            "owner_id": owner_id,
            "ideas": ideas,
            "parameters": payload.dict(exclude={"fallback_user_id"}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        await _log_ai_usage(owner_id, "date_ideas")
        
        return {
            "idea_id": idea_id,
            "date_ideas": ideas,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Date idea generation failed: {str(e)}")


@router.get("/date-ideas/history")
async def get_date_ideas_history(request: Request, fallback_user_id: Optional[str] = None):
    """Get past date ideas."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    history = await db.relationship_dates.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)
    
    return {"history": history}


@router.get("/gift-ideas/history")
async def get_gift_ideas_history(request: Request, fallback_user_id: Optional[str] = None):
    """Get past gift idea recommendations."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    history = await db.relationship_gifts.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)

    return {"history": history}


# ── Gift Recommendations ──


@router.post("/gift-ideas")
async def generate_gift_ideas(payload: GiftIdeasRequest, request: Request):
    """Generate AI-powered gift recommendations."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    
    await _check_ai_usage(owner_id, tier)
    
    interests_str = ", ".join(payload.partner_interests) if payload.partner_interests else "General interests"
    
    prompt = f"""Generate 5-6 thoughtful gift recommendations for:

Occasion: {payload.occasion}
Budget: {payload.budget}
Partner Interests: {interests_str}
Personality: {payload.personality or 'Not specified'}

For each gift, provide:
- Gift name
- Description
- Why it's meaningful
- Approximate price range
- Where to find it

Be creative, personal, and thoughtful!"""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"gift-ideas-{uuid4().hex[:10]}",
                system_message="You are a gift expert who understands personality types and relationship dynamics. Suggest meaningful, personalized gifts."
            )
            .with_model("openai", "gpt-4o")
        )
        
        gifts = await chat.send_message(UserMessage(text=prompt))
        
        # Save to history
        gift_id = str(uuid4())
        await db.relationship_gifts.insert_one({
            "gift_id": gift_id,
            "owner_id": owner_id,
            "recommendations": gifts,
            "occasion": payload.occasion,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        await _log_ai_usage(owner_id, "gift_ideas")
        
        return {
            "gift_id": gift_id,
            "gift_ideas": gifts,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gift idea generation failed: {str(e)}")


# ── Important Dates & Reminders ──


@router.post("/important-dates")
async def add_important_date(payload: ImportantDate, request: Request):
    """Add an important date reminder."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    
    # Check limit
    limit = TIER_LIMITS[tier]["important_dates"]
    if limit != -1:
        count = await db.relationship_important_dates.count_documents({"owner_id": owner_id})
        if count >= limit:
            raise HTTPException(
                status_code=403,
                detail=f"Important dates limit reached for {tier} tier ({count}/{limit})"
            )
    
    date_id = str(uuid4())
    date_data = {
        "date_id": date_id,
        "owner_id": owner_id,
        "title": payload.title,
        "date": payload.date,
        "category": payload.category,
        "reminder_days": payload.reminder_days,
        "notes": payload.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.relationship_important_dates.insert_one(date_data)
    
    return {"date_id": date_id, "message": "Important date added"}


@router.get("/important-dates")
async def get_important_dates(request: Request, fallback_user_id: Optional[str] = None):
    """Get all important dates."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    dates = await db.relationship_important_dates.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("date", 1).to_list(100)
    
    return {"dates": dates}


@router.put("/important-dates/{date_id}")
async def update_important_date(date_id: str, payload: ImportantDate, request: Request):
    """Update an important date."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    result = await db.relationship_important_dates.update_one(
        {"date_id": date_id, "owner_id": owner_id},
        {"$set": {
            "title": payload.title,
            "date": payload.date,
            "category": payload.category,
            "reminder_days": payload.reminder_days,
            "notes": payload.notes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Important date not found")
    
    return {"message": "Important date updated"}


@router.delete("/important-dates/{date_id}")
async def delete_important_date(date_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Delete an important date."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.relationship_important_dates.delete_one({"date_id": date_id, "owner_id": owner_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Important date not found")
    
    return {"message": "Important date deleted"}


@router.get("/upcoming-reminders")
async def get_upcoming_reminders(request: Request, fallback_user_id: Optional[str] = None):
    """Get upcoming important dates (next 30 days)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    today = datetime.now(timezone.utc).date()
    thirty_days = (today + timedelta(days=30)).isoformat()
    
    dates = await db.relationship_important_dates.find(
        {
            "owner_id": owner_id,
            "date": {"$lte": thirty_days},
        },
        {"_id": 0}
    ).sort("date", 1).to_list(50)
    
    return {"upcoming_dates": dates}


# ── Conversation Starters ──


@router.post("/conversation-starters")
async def generate_conversation_starters(payload: ConversationStartersRequest, request: Request):
    """Generate conversation starter prompts."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    
    await _check_ai_usage(owner_id, tier)
    
    prompt = f"""Generate 8-10 meaningful conversation starters for a couple:

Relationship Stage: {payload.relationship_stage}
Mood: {payload.mood}
Topic Preference: {payload.topic_preference or 'Mixed topics'}

Mix of:
- Deep/philosophical questions
- Fun/lighthearted prompts
- Future-focused questions
- Reflection/memory prompts

Format as a numbered list. Make them engaging and thought-provoking!"""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"conversation-starters-{uuid4().hex[:10]}",
                system_message="You are a relationship coach helping couples deepen their connection through meaningful conversations."
            )
            .with_model("openai", "gpt-4o")
        )
        
        starters = await chat.send_message(UserMessage(text=prompt))
        
        await _log_ai_usage(owner_id, "conversation_starters")
        
        return {
            "conversation_starters": starters,
            "parameters": payload.dict(exclude={"fallback_user_id"}),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversation starter generation failed: {str(e)}")


# ── Relationship Health Assessment ──


@router.post("/assessment")
async def take_assessment(payload: AssessmentRequest, request: Request):
    """Take a relationship health assessment."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    
    # Check assessment limit
    limit = TIER_LIMITS[tier]["assessments_per_month"]
    if limit != -1:
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = await db.relationship_assessments.count_documents({
            "owner_id": owner_id,
            "created_at": {"$gte": month_start.isoformat()},
        })
        if count >= limit:
            raise HTTPException(
                status_code=403,
                detail=f"Assessment limit reached for {tier} tier ({count}/{limit})"
            )
    
    # Calculate overall health score
    total_score = (
        payload.communication_score +
        payload.trust_score +
        payload.intimacy_score +
        payload.conflict_resolution_score +
        payload.shared_goals_score
    )
    health_score = (total_score / 50) * 100  # Convert to 0-100 scale
    
    # Determine strengths and improvement areas
    scores = {
        "communication": payload.communication_score,
        "trust": payload.trust_score,
        "intimacy": payload.intimacy_score,
        "conflict_resolution": payload.conflict_resolution_score,
        "shared_goals": payload.shared_goals_score,
    }
    
    strengths = [k for k, v in scores.items() if v >= 8]
    improvements = [k for k, v in scores.items() if v <= 5]
    
    assessment_id = str(uuid4())
    assessment_data = {
        "assessment_id": assessment_id,
        "owner_id": owner_id,
        "health_score": round(health_score, 1),
        "scores": scores,
        "strengths": strengths,
        "improvement_areas": improvements,
        "notes": payload.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.relationship_assessments.insert_one(assessment_data)
    
    return {
        "assessment_id": assessment_id,
        "health_score": round(health_score, 1),
        "strengths": strengths,
        "improvement_areas": improvements,
        "message": "Assessment completed",
    }


@router.get("/assessments/history")
async def get_assessment_history(request: Request, fallback_user_id: Optional[str] = None):
    """Get past assessments."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    assessments = await db.relationship_assessments.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)
    
    return {"assessments": assessments}


# ── Communication Tips ──


@router.post("/communication-tips")
async def get_communication_tips(payload: CommunicationTipsRequest, request: Request):
    """Get AI-powered communication tips for specific scenarios."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_tier(owner_id)
    
    await _check_ai_usage(owner_id, tier)
    
    prompt = f"""Provide expert communication coaching for this scenario:

Scenario: {payload.scenario}
Context: {payload.context or 'General situation'}

Include:
1. Overview of the challenge
2. 3-4 specific communication techniques
3. Example phrases to use
4. What to avoid
5. Follow-up actions

Be practical, empathetic, and actionable."""
    
    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"communication-tips-{uuid4().hex[:10]}",
                system_message="You are a communication expert teaching effective relationship skills like active listening, expressing needs, and conflict de-escalation."
            )
            .with_model("openai", "gpt-4o")
        )
        
        tips = await chat.send_message(UserMessage(text=prompt))

        # Save to history
        tip_id = str(uuid4())
        await db.relationship_communication_tips.insert_one({
            "tip_id": tip_id,
            "owner_id": owner_id,
            "scenario": payload.scenario,
            "tips": tips,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        
        await _log_ai_usage(owner_id, "communication_tips")
        
        return {
            "tip_id": tip_id,
            "scenario": payload.scenario,
            "tips": tips,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Communication tips generation failed: {str(e)}")


@router.get("/communication-tips/history")
async def get_communication_tips_history(request: Request, fallback_user_id: Optional[str] = None):
    """Get past communication tips sessions."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    history = await db.relationship_communication_tips.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)

    return {"history": history}


# ── Session History & Analytics ──


@router.get("/sessions")
async def get_session_history(request: Request, fallback_user_id: Optional[str] = None):
    """Get advice session history."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    sessions = await db.relationship_advice_sessions.find(
        {"owner_id": owner_id},
        {"_id": 0, "advice": 0}  # Exclude full advice text for list view
    ).sort("created_at", -1).limit(50).to_list(50)
    
    return {"sessions": sessions}


@router.get("/analytics")
async def get_analytics(request: Request, fallback_user_id: Optional[str] = None):
    """Get usage analytics and trends."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Count various activities
    advice_count = await db.relationship_advice_sessions.count_documents({"owner_id": owner_id})
    date_ideas_count = await db.relationship_dates.count_documents({"owner_id": owner_id})
    assessments_count = await db.relationship_assessments.count_documents({"owner_id": owner_id})
    important_dates_count = await db.relationship_important_dates.count_documents({"owner_id": owner_id})
    
    # Get latest assessment score if exists
    assessments_cursor = db.relationship_assessments.find(
        {"owner_id": owner_id},
        {"_id": 0, "health_score": 1, "created_at": 1}
    ).sort("created_at", -1).limit(1)
    latest_list = await assessments_cursor.to_list(1)
    latest_assessment = latest_list[0] if latest_list else None
    
    return {
        "total_advice_sessions": advice_count,
        "total_date_ideas_generated": date_ideas_count,
        "total_assessments": assessments_count,
        "important_dates_tracked": important_dates_count,
        "latest_health_score": latest_assessment.get("health_score") if latest_assessment else None,
    }
