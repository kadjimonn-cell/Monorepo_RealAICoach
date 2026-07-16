"""Health Guide - Enterprise-Grade Health Tracking & AI Insights Platform

AI-powered health companion with symptom checking, wearable data integration,
personalized health insights, and comprehensive health tracking.

Tier Limits:
- Free: 10 health checks/month, 5 symptom checks/month, 20 wearable logs/day
- Basic: 50 health checks/month, 20 symptom checks/month, 100 wearable logs/day
- Premium: Unlimited health checks, symptom checks, wearable logs, AI coaching

Endpoints:
- GET  /api/health-guide/bootstrap                    Bootstrap with tier + usage
- POST /api/health-guide/profile                      Create/update health profile
- GET  /api/health-guide/profile                      Get health profile
- PUT  /api/health-guide/profile                      Update health profile
- DELETE /api/health-guide/profile                    Delete health profile & data
- POST /api/health-guide/wearable-data                Log wearable device data
- GET  /api/health-guide/wearable-data                Get wearable data history
- DELETE /api/health-guide/wearable-data/{log_id}     Delete wearable log
- POST /api/health-guide/insights                     Get AI health insights
- GET  /api/health-guide/insights-history             Get insights history
- POST /api/health-guide/symptom-check                AI symptom analysis
- GET  /api/health-guide/symptom-checks-history       Get symptom check history
- GET  /api/health-guide/dashboard                    Health dashboard stats
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

logger = logging.getLogger("routes.health_guide")
router = APIRouter(prefix="/health-guide", tags=["health-guide"])
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

# ══════════ TIER LIMITS ══════════

TIER_LIMITS = {
    "free": {
        "health_checks_per_month": 10,
        "symptom_checks_per_month": 5,
        "wearable_logs_per_day": 20,
        "insights_per_month": 5,
        "active_medications": 2,
        "active_goals": 2,
        "features": ["basic_tracking", "simple_insights"],
    },
    "basic": {
        "health_checks_per_month": 50,
        "symptom_checks_per_month": 20,
        "wearable_logs_per_day": 100,
        "insights_per_month": 25,
        "active_medications": 10,
        "active_goals": 5,
        "features": ["wearable_sync", "advanced_insights", "symptom_checker", "medication_tracking"],
    },
    "premium": {
        "health_checks_per_month": -1,  # unlimited
        "symptom_checks_per_month": -1,
        "wearable_logs_per_day": -1,
        "insights_per_month": -1,
        "active_medications": -1,  # unlimited
        "active_goals": -1,  # unlimited
        "features": ["ai_coaching", "health_goals", "data_export", "proactive_nudges", "medication_interactions", "advanced_analytics"],
    },
}

# ══════════ MODELS ══════════

class HealthProfileRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    medical_conditions: List[str] = []
    medications: List[str] = []
    allergies: List[str] = []
    lifestyle: Optional[Dict[str, Any]] = None  # smoking, alcohol, exercise level


class WearableDataRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    data_type: str  # heart_rate, sleep, steps, activity, blood_oxygen
    readings: List[Dict[str, Any]]  # timestamp, value pairs
    device: Optional[str] = None


class HealthInsightRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    concern: Optional[str] = None
    include_recommendations: bool = True


class SymptomCheckRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    symptoms: List[str]
    duration: str  # how long symptoms have been present
    severity: str = "moderate"  # mild, moderate, severe


# ══════════ PHASE 2: MEDICATION MANAGEMENT MODELS ══════════

class MedicationRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    name: str
    dosage: str  # "10mg", "2 tablets", etc.
    frequency: str  # "daily", "twice_daily", "weekly", "as_needed"
    schedule_times: List[str] = []  # ["08:00", "20:00"]
    instructions: Optional[str] = None
    prescribing_doctor: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None  # For limited-duration medications
    refill_reminder_days: int = 7


class LogDoseRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    status: str  # "taken", "missed", "skipped"
    taken_at: Optional[str] = None  # ISO timestamp
    notes: Optional[str] = None


# ══════════ PHASE 2: HEALTH GOALS MODELS ══════════

class HealthGoalRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    goal_type: str  # "weight_loss", "weight_gain", "fitness", "nutrition", "sleep", "stress"
    title: str
    target_value: Optional[float] = None
    target_unit: Optional[str] = None  # "kg", "lbs", "hours", "steps"
    current_value: Optional[float] = None
    deadline: Optional[str] = None  # ISO date
    milestones: List[Dict[str, Any]] = []


class GoalProgressRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    current_value: float
    notes: Optional[str] = None


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
                    "error_code": "health_guide_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "health_guide_auth_required",
            "message": "Login required or provide fallback_user_id for guest workspace",
        },
    )


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


async def _check_health_check_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can perform more health checks this month."""
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    count = await db.health_insights_history.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    limit = TIER_LIMITS[tier]["health_checks_per_month"]
    can_check = limit == -1 or count < limit
    
    return {
        "can_check": can_check,
        "checks_used": count,
        "monthly_limit": limit if limit != -1 else "unlimited"
    }


async def _check_symptom_check_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can perform more symptom checks this month."""
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    count = await db.symptom_checks_history.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    limit = TIER_LIMITS[tier]["symptom_checks_per_month"]
    can_check = limit == -1 or count < limit
    
    return {
        "can_check": can_check,
        "checks_used": count,
        "monthly_limit": limit if limit != -1 else "unlimited"
    }


async def _check_wearable_log_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can log more wearable data today."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    count = await db.wearable_data.count_documents({
        "owner_id": owner_id,
        "logged_at": {"$gte": start_of_day}
    })
    
    limit = TIER_LIMITS[tier]["wearable_logs_per_day"]
    can_log = limit == -1 or count < limit
    
    return {
        "can_log": can_log,
        "logs_today": count,
        "daily_limit": limit if limit != -1 else "unlimited"
    }


# ══════════ ROUTES ══════════

@router.get("/bootstrap")
async def health_guide_bootstrap(request: Request, fallback_user_id: Optional[str] = None):
    """Bootstrap Health Guide with tier, usage, features."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Get health profile
    profile = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    # Get recent wearable data summary
    recent_logs = await db.wearable_data.find(
        {"owner_id": owner_id},
        {"_id": 0, "data_type": 1, "logged_at": 1}
    ).sort("logged_at", -1).limit(5).to_list(5)
    
    # Get usage stats
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    health_checks_this_month = await db.health_insights_history.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    symptom_checks_this_month = await db.symptom_checks_history.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    wearable_logs_today = await db.wearable_data.count_documents({
        "owner_id": owner_id,
        "logged_at": {"$gte": start_of_day}
    })
    
    return {
        "owner_id": owner_id,
        "tier": tier,
        "has_profile": bool(profile),
        "profile_summary": {
            "age": profile.get("age") if profile else None,
            "bmi": profile.get("bmi") if profile else None,
            "bmi_category": profile.get("bmi_category") if profile else None,
        } if profile else None,
        "recent_wearable_logs": recent_logs,
        "usage": {
            "health_checks_this_month": health_checks_this_month,
            "symptom_checks_this_month": symptom_checks_this_month,
            "wearable_logs_today": wearable_logs_today,
            "health_checks_limit": TIER_LIMITS[tier]["health_checks_per_month"] if TIER_LIMITS[tier]["health_checks_per_month"] != -1 else "unlimited",
            "symptom_checks_limit": TIER_LIMITS[tier]["symptom_checks_per_month"] if TIER_LIMITS[tier]["symptom_checks_per_month"] != -1 else "unlimited",
            "wearable_logs_limit": TIER_LIMITS[tier]["wearable_logs_per_day"] if TIER_LIMITS[tier]["wearable_logs_per_day"] != -1 else "unlimited",
        },
        "features": TIER_LIMITS[tier]["features"],
        "tier_limits": TIER_LIMITS[tier],
    }


@router.post("/profile")
async def create_health_profile(payload: HealthProfileRequest, request: Request):
    """Create or update health profile."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    profile_data = {
        "owner_id": owner_id,
        "age": payload.age,
        "gender": payload.gender,
        "height_cm": payload.height_cm,
        "weight_kg": payload.weight_kg,
        "medical_conditions": payload.medical_conditions,
        "medications": payload.medications,
        "allergies": payload.allergies,
        "lifestyle": payload.lifestyle or {},
        "tier_used": tier,
        "updated_at": _now_iso(),
    }
    
    # Calculate BMI if height and weight provided
    if payload.height_cm and payload.weight_kg:
        height_m = payload.height_cm / 100
        bmi = round(payload.weight_kg / (height_m ** 2), 1)
        profile_data["bmi"] = bmi
        if bmi < 18.5:
            profile_data["bmi_category"] = "Underweight"
        elif bmi < 25:
            profile_data["bmi_category"] = "Normal"
        elif bmi < 30:
            profile_data["bmi_category"] = "Overweight"
        else:
            profile_data["bmi_category"] = "Obese"
    
    # Check if profile exists
    existing = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    if not existing:
        profile_data["created_at"] = _now_iso()
    
    await db.health_profiles.update_one(
        {"owner_id": owner_id},
        {"$set": profile_data},
        upsert=True
    )
    
    return {"message": "Health profile saved", "profile": profile_data}


@router.get("/profile")
async def get_health_profile(request: Request, fallback_user_id: Optional[str] = None):
    """Get health profile."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    profile = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    if not profile:
        return {"has_profile": False, "message": "No health profile found"}
    return {"has_profile": True, "profile": profile}


@router.put("/profile")
async def update_health_profile(payload: HealthProfileRequest, request: Request):
    """Update health profile (same as POST but semantically clearer)."""
    return await create_health_profile(payload, request)


@router.delete("/profile")
async def delete_health_profile(request: Request, fallback_user_id: Optional[str] = None):
    """Delete health profile and all associated health data."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Delete profile
    profile_result = await db.health_profiles.delete_one({"owner_id": owner_id})
    
    # Cascade delete all health data
    await db.wearable_data.delete_many({"owner_id": owner_id})
    await db.health_insights_history.delete_many({"owner_id": owner_id})
    await db.symptom_checks_history.delete_many({"owner_id": owner_id})
    
    if profile_result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "profile_not_found", "message": "Health profile not found"}
        )
    
    return {
        "message": "Health profile and all associated data deleted successfully",
        "owner_id": owner_id
    }


@router.post("/wearable-data")
async def log_wearable_data(payload: WearableDataRequest, request: Request):
    """Log data from wearable devices (heart rate, sleep, steps, etc.)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limit
    usage_check = await _check_wearable_log_limit(owner_id, tier)
    if not usage_check["can_log"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "health_guide_wearable_limit_reached",
                "message": f"Daily wearable log limit reached ({usage_check['daily_limit']} for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "logs_today": usage_check["logs_today"],
                "daily_limit": usage_check["daily_limit"],
            },
        )
    
    log_id = f"wlog_{uuid.uuid4().hex[:12]}"
    data_entry = {
        "log_id": log_id,
        "owner_id": owner_id,
        "data_type": payload.data_type,
        "readings": payload.readings,
        "device": payload.device,
        "tier_used": tier,
        "logged_at": _now_iso(),
    }
    
    await db.wearable_data.insert_one(data_entry)
    
    # Calculate basic stats
    values = [r.get("value", 0) for r in payload.readings if r.get("value")]
    stats = {}
    if values:
        stats = {
            "average": round(sum(values) / len(values), 1),
            "min": min(values),
            "max": max(values),
            "count": len(values),
        }
    
    data_entry.pop("_id", None)
    return {"message": "Data logged", "log": data_entry, "stats": stats}


@router.get("/wearable-data")
async def get_wearable_data(
    request: Request,
    fallback_user_id: Optional[str] = None,
    data_type: Optional[str] = None,
    days: int = 7,
    limit: int = 100
):
    """Get wearable data history."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if data_type:
        query["data_type"] = data_type
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query["logged_at"] = {"$gte": cutoff.isoformat()}
    
    data = await db.wearable_data.find(query, {"_id": 0}).sort("logged_at", -1).limit(limit).to_list(limit)
    return {"data": data, "period_days": days, "count": len(data)}


@router.delete("/wearable-data/{log_id}")
async def delete_wearable_log(log_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Delete specific wearable data log."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.wearable_data.delete_one({"log_id": log_id, "owner_id": owner_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "log_not_found", "message": "Wearable log not found"}
        )
    
    return {"message": "Wearable log deleted successfully", "log_id": log_id}


@router.post("/insights")
async def get_health_insights(payload: HealthInsightRequest, request: Request):
    """Get AI-powered health insights based on profile and wearable data."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limit
    usage_check = await _check_health_check_limit(owner_id, tier)
    if not usage_check["can_check"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "health_guide_check_limit_reached",
                "message": f"Monthly health check limit reached ({usage_check['monthly_limit']} for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "checks_used": usage_check["checks_used"],
                "monthly_limit": usage_check["monthly_limit"],
            },
        )
    
    # Get user's health data
    profile = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    wearable_data = await db.wearable_data.find(
        {"owner_id": owner_id}
    ).sort("logged_at", -1).limit(50).to_list(50)
    
    # Summarize wearable data
    data_summary = {}
    for d in wearable_data:
        dtype = d.get("data_type")
        if dtype not in data_summary:
            data_summary[dtype] = {"readings": [], "count": 0}
        data_summary[dtype]["readings"].extend(d.get("readings", []))
        data_summary[dtype]["count"] += len(d.get("readings", []))
    
    prompt = f"""Analyze this user's health data and provide personalized insights.

Health Profile:
{json.dumps(profile, indent=2, default=str) if profile else "No profile set up"}

Recent Health Data:
{json.dumps({k: {"count": v["count"], "sample": v["readings"][:5]} for k, v in data_summary.items()}, indent=2)}

{f"Specific Concern: {payload.concern}" if payload.concern else ""}

Provide health insights. IMPORTANT: You are NOT a doctor. Always recommend consulting healthcare professionals for medical decisions.

Return JSON:
{{
    "overall_health_score": 75,
    "key_insights": [
        {{
            "area": "Heart Health/Sleep/Activity/etc",
            "finding": "What the data shows",
            "significance": "What it means",
            "recommendation": "What to consider"
        }}
    ],
    "positive_patterns": ["Good patterns observed"],
    "areas_of_attention": [
        {{
            "area": "Area needing attention",
            "concern_level": "low/medium/high",
            "suggestion": "What to do"
        }}
    ],
    "lifestyle_recommendations": [
        {{
            "category": "sleep/exercise/nutrition/stress",
            "recommendation": "Specific recommendation",
            "expected_benefit": "How it helps"
        }}
    ],
    "early_warnings": ["Any patterns that should be discussed with a doctor"],
    "disclaimer": "This is informational only. Consult healthcare professionals for medical advice."
}}"""
    
    chat = LlmChat(
        api_key=EMERGENT_KEY,
        session_id=f"health-insights-{uuid.uuid4()}",
        system_message="You are a health insights AI. Analyze data patterns and provide helpful insights. Always recommend consulting healthcare professionals. Never diagnose conditions. Return valid JSON.",
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
            "overall_health_score": 50,
            "key_insights": [{"area": "General", "finding": "Need more data for detailed insights"}],
            "disclaimer": "This is informational only. Consult healthcare professionals for medical advice.",
        }
    
    # Save to history
    insight_record = {
        "insight_id": f"ins_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "tier_used": tier,
        "concern": payload.concern,
        "insights": insights,
        "created_at": _now_iso(),
    }
    await db.health_insights_history.insert_one(insight_record)
    insight_record.pop("_id", None)
    
    return insights


@router.get("/insights-history")
async def get_insights_history(
    request: Request,
    fallback_user_id: Optional[str] = None,
    limit: int = 20
):
    """Get health insights history."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    history = await db.health_insights_history.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {"insights_history": history, "count": len(history)}


@router.post("/symptom-check")
async def check_symptoms(payload: SymptomCheckRequest, request: Request):
    """AI-assisted symptom analysis (NOT diagnosis - always recommend seeing a doctor)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limit
    usage_check = await _check_symptom_check_limit(owner_id, tier)
    if not usage_check["can_check"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "health_guide_symptom_limit_reached",
                "message": f"Monthly symptom check limit reached ({usage_check['monthly_limit']} for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "checks_used": usage_check["checks_used"],
                "monthly_limit": usage_check["monthly_limit"],
            },
        )
    
    profile = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    prompt = f"""A user is reporting symptoms. Provide helpful information (NOT diagnosis).

User Profile:
- Age: {profile.get("age", "Unknown") if profile else "Unknown"}
- Medical Conditions: {profile.get("medical_conditions", []) if profile else []}
- Medications: {profile.get("medications", []) if profile else []}

Reported Symptoms:
- Symptoms: {", ".join(payload.symptoms)}
- Duration: {payload.duration}
- Severity: {payload.severity}

IMPORTANT: You are NOT a doctor. Do NOT diagnose. Provide general information only.

Return JSON:
{{
    "symptom_summary": "Brief summary of reported symptoms",
    "general_information": [
        {{
            "symptom": "Symptom name",
            "common_causes": ["Possible cause 1", "Possible cause 2"],
            "general_info": "General information about this symptom"
        }}
    ],
    "self_care_suggestions": ["General self-care that might help"],
    "when_to_seek_care": {{
        "urgency_level": "routine/soon/urgent/emergency",
        "indicators": ["Signs that indicate need for professional care"],
        "recommended_action": "What type of care to consider"
    }},
    "questions_for_doctor": ["Questions to ask if you see a healthcare provider"],
    "important_disclaimer": "This is NOT medical advice. If you're concerned about your symptoms, please consult a healthcare professional."
}}"""
    
    chat = LlmChat(
        api_key=EMERGENT_KEY,
        session_id=f"symptom-{uuid.uuid4()}",
        system_message="You are a health information assistant. Provide general health information only. NEVER diagnose conditions. Always recommend consulting healthcare professionals. Return valid JSON.",
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
            "symptom_summary": "Unable to analyze symptoms",
            "important_disclaimer": "Please consult a healthcare professional for proper evaluation.",
        }
    
    # Always add legal disclaimer
    result["legal_disclaimer"] = (
        "This information is for educational purposes only and is not intended as medical advice, diagnosis, or treatment. "
        "Always seek the advice of your physician or other qualified health provider."
    )
    
    # Save to history
    symptom_record = {
        "check_id": f"symp_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "tier_used": tier,
        "symptoms": payload.symptoms,
        "duration": payload.duration,
        "severity": payload.severity,
        "result": result,
        "created_at": _now_iso(),
    }
    await db.symptom_checks_history.insert_one(symptom_record)
    symptom_record.pop("_id", None)
    
    return result


@router.get("/symptom-checks-history")
async def get_symptom_checks_history(
    request: Request,
    fallback_user_id: Optional[str] = None,
    limit: int = 20
):
    """Get symptom check history."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    history = await db.symptom_checks_history.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {"symptom_checks_history": history, "count": len(history)}




# ══════════ PHASE 2: MEDICATION MANAGEMENT ROUTES ══════════

@router.post("/medications")
async def add_medication(payload: MedicationRequest, request: Request):
    """Add a new medication to track."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limit
    active_count = await db.medications.count_documents({
        "owner_id": owner_id,
        "status": "active"
    })
    
    limit = TIER_LIMITS[tier]["active_medications"]
    if limit != -1 and active_count >= limit:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "medication_limit_reached",
                "message": f"Active medication limit reached ({limit} for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "active_medications": active_count,
                "limit": limit,
            },
        )
    
    med_id = f"med_{uuid.uuid4().hex[:12]}"
    medication = {
        "medication_id": med_id,
        "owner_id": owner_id,
        "name": payload.name,
        "dosage": payload.dosage,
        "frequency": payload.frequency,
        "schedule_times": payload.schedule_times,
        "instructions": payload.instructions,
        "prescribing_doctor": payload.prescribing_doctor,
        "start_date": payload.start_date or _now_iso(),
        "end_date": payload.end_date,
        "refill_reminder_days": payload.refill_reminder_days,
        "status": "active",
        "tier_used": tier,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    
    await db.medications.insert_one(medication)
    medication.pop("_id", None)
    
    return {"message": "Medication added successfully", "medication": medication}


@router.get("/medications")
async def get_medications(
    request: Request,
    fallback_user_id: Optional[str] = None,
    status: Optional[str] = "active",  # active, inactive, all
    limit: int = 50
):
    """Get list of medications."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if status and status != "all":
        query["status"] = status
    
    medications = await db.medications.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {"medications": medications, "count": len(medications)}


@router.put("/medications/{medication_id}")
async def update_medication(
    medication_id: str,
    payload: MedicationRequest,
    request: Request
):
    """Update medication details."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    update_data = {
        "name": payload.name,
        "dosage": payload.dosage,
        "frequency": payload.frequency,
        "schedule_times": payload.schedule_times,
        "instructions": payload.instructions,
        "prescribing_doctor": payload.prescribing_doctor,
        "end_date": payload.end_date,
        "refill_reminder_days": payload.refill_reminder_days,
        "updated_at": _now_iso(),
    }
    
    result = await db.medications.update_one(
        {"medication_id": medication_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "medication_not_found", "message": "Medication not found"}
        )
    
    return {"message": "Medication updated successfully", "medication_id": medication_id}


@router.delete("/medications/{medication_id}")
async def delete_medication(
    medication_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Delete (deactivate) a medication."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Mark as inactive instead of deleting (preserve history)
    result = await db.medications.update_one(
        {"medication_id": medication_id, "owner_id": owner_id},
        {"$set": {"status": "inactive", "updated_at": _now_iso()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "medication_not_found", "message": "Medication not found"}
        )
    
    return {"message": "Medication deleted successfully", "medication_id": medication_id}


@router.post("/medications/{medication_id}/log-dose")
async def log_dose(
    medication_id: str,
    payload: LogDoseRequest,
    request: Request
):
    """Log a dose (taken, missed, or skipped)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Verify medication exists
    medication = await db.medications.find_one(
        {"medication_id": medication_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not medication:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "medication_not_found", "message": "Medication not found"}
        )
    
    log_id = f"dose_{uuid.uuid4().hex[:12]}"
    dose_log = {
        "log_id": log_id,
        "medication_id": medication_id,
        "owner_id": owner_id,
        "status": payload.status,
        "taken_at": payload.taken_at or _now_iso(),
        "notes": payload.notes,
        "medication_name": medication.get("name"),
        "dosage": medication.get("dosage"),
        "logged_at": _now_iso(),
    }
    
    await db.medication_logs.insert_one(dose_log)
    dose_log.pop("_id", None)
    
    return {"message": "Dose logged successfully", "log": dose_log}


@router.get("/medications/reminders")
async def get_medication_reminders(
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Get upcoming medication reminders for today."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Get active medications with schedules
    medications = await db.medications.find(
        {"owner_id": owner_id, "status": "active"},
        {"_id": 0}
    ).to_list(100)
    
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    
    reminders = []
    for med in medications:
        # Get today's logs
        today_logs = await db.medication_logs.find({
            "medication_id": med["medication_id"],
            "taken_at": {"$gte": f"{today}T00:00:00Z"}
        }, {"_id": 0}).to_list(100)
        
        logged_times = {log["taken_at"][:5] for log in today_logs if log.get("status") == "taken"}
        
        for schedule_time in med.get("schedule_times", []):
            if schedule_time not in logged_times:
                reminders.append({
                    "medication_id": med["medication_id"],
                    "name": med["name"],
                    "dosage": med["dosage"],
                    "scheduled_time": schedule_time,
                    "status": "pending",
                })
    
    return {"reminders": reminders, "count": len(reminders), "date": today}


# ══════════ PHASE 2: HEALTH GOALS ROUTES ══════════

@router.post("/goals")
async def create_health_goal(payload: HealthGoalRequest, request: Request):
    """Create a new health goal."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limit
    active_count = await db.health_goals.count_documents({
        "owner_id": owner_id,
        "status": "active"
    })
    
    limit = TIER_LIMITS[tier]["active_goals"]
    if limit != -1 and active_count >= limit:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "goal_limit_reached",
                "message": f"Active goal limit reached ({limit} for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "active_goals": active_count,
                "limit": limit,
            },
        )
    
    goal_id = f"goal_{uuid.uuid4().hex[:12]}"
    goal = {
        "goal_id": goal_id,
        "owner_id": owner_id,
        "goal_type": payload.goal_type,
        "title": payload.title,
        "target_value": payload.target_value,
        "target_unit": payload.target_unit,
        "current_value": payload.current_value,
        "deadline": payload.deadline,
        "milestones": payload.milestones,
        "status": "active",
        "progress_percentage": 0,
        "start_value": payload.current_value,  # Store starting value for weight loss calculations
        "tier_used": tier,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    
    # Calculate initial progress based on goal type
    if payload.current_value and payload.target_value:
        if payload.goal_type in ["weight_loss"]:
            # For weight loss: progress = how much lost / total to lose
            # Start at 0% when current_value = start_value
            if payload.current_value != payload.target_value:
                goal["progress_percentage"] = 0  # No progress yet at start
            else:
                goal["progress_percentage"] = 100  # Already at target
        else:
            # For weight_gain, fitness, etc.: progress = current / target
            goal["progress_percentage"] = min(100, int((payload.current_value / payload.target_value) * 100))
    
    await db.health_goals.insert_one(goal)
    goal.pop("_id", None)
    
    return {"message": "Health goal created successfully", "goal": goal}


@router.get("/goals")
async def get_health_goals(
    request: Request,
    fallback_user_id: Optional[str] = None,
    status: Optional[str] = "active",
    limit: int = 50
):
    """Get list of health goals."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if status and status != "all":
        query["status"] = status
    
    goals = await db.health_goals.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {"goals": goals, "count": len(goals)}


@router.put("/goals/{goal_id}")
async def update_health_goal(
    goal_id: str,
    payload: HealthGoalRequest,
    request: Request
):
    """Update goal details."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    update_data = {
        "title": payload.title,
        "target_value": payload.target_value,
        "target_unit": payload.target_unit,
        "deadline": payload.deadline,
        "milestones": payload.milestones,
        "updated_at": _now_iso(),
    }
    
    result = await db.health_goals.update_one(
        {"goal_id": goal_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "goal_not_found", "message": "Goal not found"}
        )
    
    return {"message": "Goal updated successfully", "goal_id": goal_id}


@router.delete("/goals/{goal_id}")
async def delete_health_goal(
    goal_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Delete (complete/archive) a goal."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.health_goals.update_one(
        {"goal_id": goal_id, "owner_id": owner_id},
        {"$set": {"status": "archived", "updated_at": _now_iso()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "goal_not_found", "message": "Goal not found"}
        )
    
    return {"message": "Goal archived successfully", "goal_id": goal_id}


@router.post("/goals/{goal_id}/progress")
async def log_goal_progress(
    goal_id: str,
    payload: GoalProgressRequest,
    request: Request
):
    """Log progress update for a goal."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # Get goal
    goal = await db.health_goals.find_one(
        {"goal_id": goal_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not goal:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "goal_not_found", "message": "Goal not found"}
        )
    
    # Log progress entry
    progress_id = f"prog_{uuid.uuid4().hex[:12]}"
    progress_entry = {
        "progress_id": progress_id,
        "goal_id": goal_id,
        "owner_id": owner_id,
        "current_value": payload.current_value,
        "notes": payload.notes,
        "logged_at": _now_iso(),
    }
    
    await db.goal_progress.insert_one(progress_entry)
    
    # Update goal with latest progress - handle different goal types
    progress_percentage = 0
    if goal.get("target_value") and goal.get("start_value"):
        goal_type = goal.get("goal_type")
        if goal_type in ["weight_loss"]:
            # For weight loss: progress = (start - current) / (start - target) * 100
            start_val = goal["start_value"]
            target_val = goal["target_value"]
            current_val = payload.current_value
            
            if start_val != target_val:
                progress_percentage = min(100, max(0, int(((start_val - current_val) / (start_val - target_val)) * 100)))
            else:
                progress_percentage = 100
        else:
            # For weight_gain, fitness, etc.: progress = current / target * 100
            progress_percentage = min(100, int((payload.current_value / goal["target_value"]) * 100))
    
    await db.health_goals.update_one(
        {"goal_id": goal_id},
        {
            "$set": {
                "current_value": payload.current_value,
                "progress_percentage": progress_percentage,
                "updated_at": _now_iso(),
            }
        }
    )
    
    progress_entry.pop("_id", None)
    return {
        "message": "Progress logged successfully",
        "progress": progress_entry,
        "progress_percentage": progress_percentage
    }


@router.get("/goals/{goal_id}/analytics")
async def get_goal_analytics(
    goal_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Get analytics for a specific goal."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Get goal
    goal = await db.health_goals.find_one(
        {"goal_id": goal_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not goal:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "goal_not_found", "message": "Goal not found"}
        )
    
    # Get progress history
    progress_history = await db.goal_progress.find(
        {"goal_id": goal_id},
        {"_id": 0}
    ).sort("logged_at", 1).to_list(100)
    
    # Calculate stats
    values = [p["current_value"] for p in progress_history]
    analytics = {
        "goal": goal,
        "progress_entries": len(progress_history),
        "progress_history": progress_history[-10:],  # Last 10 entries
        "trend": "improving" if len(values) >= 2 and values[-1] > values[0] else "stable",
        "average_value": round(sum(values) / len(values), 2) if values else 0,
        "current_progress_percentage": goal.get("progress_percentage", 0),
    }
    
    return analytics


# ══════════ PHASE 2: ADVANCED ANALYTICS ROUTES ══════════

@router.get("/analytics/trends")
async def get_health_trends(
    request: Request,
    fallback_user_id: Optional[str] = None,
    metric: Optional[str] = None,  # weight, activity, sleep, mood
    days: int = 30
):
    """Get health trends analysis."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Tier check for analytics
    if tier == "free" and days > 7:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "analytics_tier_limit",
                "message": "Free tier limited to 7-day trends. Upgrade for extended history.",
                "upgrade_prompt": True,
            },
        )
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()
    
    # Get wearable data for trend analysis
    wearable_data = await db.wearable_data.find(
        {"owner_id": owner_id, "logged_at": {"$gte": cutoff_iso}},
        {"_id": 0}
    ).sort("logged_at", 1).to_list(1000)
    
    # Get goal progress for trends
    await db.goal_progress.find(
        {"owner_id": owner_id, "logged_at": {"$gte": cutoff_iso}},
        {"_id": 0}
    ).sort("logged_at", 1).to_list(1000)
    
    # Group data by metric type
    trends = {}
    for data in wearable_data:
        dtype = data.get("data_type")
        if dtype not in trends:
            trends[dtype] = []
        trends[dtype].extend(data.get("readings", []))
    
    # Calculate trend statistics
    trend_summary = {}
    for dtype, readings in trends.items():
        if readings:
            values = [r.get("value", 0) for r in readings if r.get("value")]
            if values:
                trend_summary[dtype] = {
                    "average": round(sum(values) / len(values), 2),
                    "min": min(values),
                    "max": max(values),
                    "data_points": len(values),
                    "trend": "increasing" if len(values) >= 2 and values[-1] > values[0] else "stable",
                }
    
    return {
        "period_days": days,
        "trends": trend_summary,
        "raw_data_summary": {k: len(v) for k, v in trends.items()},
    }


@router.get("/reports/weekly")
async def get_weekly_health_report(
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Generate weekly health report."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Tier check
    if tier == "free":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "reports_tier_limit",
                "message": "Weekly reports available for Basic and Premium tiers. Upgrade to access.",
                "upgrade_prompt": True,
            },
        )
    
    # Get last 7 days of data
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    cutoff_iso = cutoff.isoformat()
    
    # Aggregate data
    wearable_count = await db.wearable_data.count_documents({
        "owner_id": owner_id,
        "logged_at": {"$gte": cutoff_iso}
    })
    
    insights_count = await db.health_insights_history.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": cutoff_iso}
    })
    
    medications_taken = await db.medication_logs.count_documents({
        "owner_id": owner_id,
        "status": "taken",
        "taken_at": {"$gte": cutoff_iso}
    })
    
    goals_progress = await db.goal_progress.count_documents({
        "owner_id": owner_id,
        "logged_at": {"$gte": cutoff_iso}
    })
    
    return {
        "report_type": "weekly",
        "period_start": cutoff_iso,
        "period_end": _now_iso(),
        "summary": {
            "wearable_logs": wearable_count,
            "health_insights_generated": insights_count,
            "medications_taken": medications_taken,
            "goal_progress_updates": goals_progress,
        },
        "message": "Weekly health report generated",
    }




# ══════════ PHASE 2: HEALTH DATA EXPORT ROUTES ══════════

@router.get("/export/profile")
async def export_health_profile(
    request: Request,
    fallback_user_id: Optional[str] = None,
    format: str = "json"  # json, csv
):
    """Export health profile data."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Tier check for exports
    if tier == "free":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "export_tier_limit",
                "message": "Data export available for Basic and Premium tiers. Upgrade to access.",
                "upgrade_prompt": True,
            },
        )
    
    profile = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    if not profile:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "profile_not_found", "message": "No health profile found"}
        )
    
    if format == "csv":
        # Simple CSV representation
        csv_data = "field,value\n"
        for key, value in profile.items():
            csv_data += f"{key},{value}\n"
        
        return {
            "format": "csv",
            "data": csv_data,
            "filename": f"health_profile_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
        }
    
    # JSON format (default)
    return {
        "format": "json",
        "data": profile,
        "exported_at": _now_iso(),
        "filename": f"health_profile_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    }


@router.get("/export/wearable-data")
async def export_wearable_data(
    request: Request,
    fallback_user_id: Optional[str] = None,
    days: int = 30,
    format: str = "csv"  # csv, json
):
    """Export wearable data history."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    if tier == "free":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "export_tier_limit",
                "message": "Data export available for Basic and Premium tiers. Upgrade to access.",
                "upgrade_prompt": True,
            },
        )
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    wearable_data = await db.wearable_data.find(
        {"owner_id": owner_id, "logged_at": {"$gte": cutoff.isoformat()}},
        {"_id": 0}
    ).sort("logged_at", 1).to_list(10000)
    
    if format == "csv":
        # CSV format with flattened readings
        csv_data = "log_id,data_type,device,logged_at,reading_timestamp,reading_value\n"
        for log in wearable_data:
            log_id = log.get("log_id", "")
            data_type = log.get("data_type", "")
            device = log.get("device", "")
            logged_at = log.get("logged_at", "")
            
            for reading in log.get("readings", []):
                timestamp = reading.get("timestamp", "")
                value = reading.get("value", "")
                csv_data += f"{log_id},{data_type},{device},{logged_at},{timestamp},{value}\n"
        
        return {
            "format": "csv",
            "data": csv_data,
            "records": len(wearable_data),
            "filename": f"wearable_data_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
        }
    
    # JSON format
    return {
        "format": "json",
        "data": wearable_data,
        "records": len(wearable_data),
        "period_days": days,
        "exported_at": _now_iso(),
        "filename": f"wearable_data_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    }


@router.get("/export/insights")
async def export_insights_history(
    request: Request,
    fallback_user_id: Optional[str] = None,
    days: int = 90,
    format: str = "json"
):
    """Export health insights history."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    if tier == "free":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "export_tier_limit",
                "message": "Insights export available for Basic and Premium tiers. Upgrade to access.",
                "upgrade_prompt": True,
            },
        )
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    insights = await db.health_insights_history.find(
        {"owner_id": owner_id, "created_at": {"$gte": cutoff.isoformat()}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(1000)
    
    return {
        "format": format,
        "data": insights,
        "records": len(insights),
        "period_days": days,
        "exported_at": _now_iso(),
        "filename": f"health_insights_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    }


@router.get("/export/comprehensive")
async def export_comprehensive_report(
    request: Request,
    fallback_user_id: Optional[str] = None,
    days: int = 30
):
    """Export comprehensive health report (all data combined)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Premium only feature
    if tier != "premium":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "comprehensive_export_premium_only",
                "message": "Comprehensive health reports are available for Premium tier only. Upgrade to access.",
                "upgrade_prompt": True,
                "current_tier": tier,
            },
        )
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()
    
    # Gather all health data
    profile = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    wearable_data = await db.wearable_data.find(
        {"owner_id": owner_id, "logged_at": {"$gte": cutoff_iso}},
        {"_id": 0}
    ).sort("logged_at", 1).to_list(5000)
    
    medications = await db.medications.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).to_list(100)
    
    medication_logs = await db.medication_logs.find(
        {"owner_id": owner_id, "taken_at": {"$gte": cutoff_iso}},
        {"_id": 0}
    ).sort("taken_at", 1).to_list(1000)
    
    goals = await db.health_goals.find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).to_list(100)
    
    goal_progress = await db.goal_progress.find(
        {"owner_id": owner_id, "logged_at": {"$gte": cutoff_iso}},
        {"_id": 0}
    ).sort("logged_at", 1).to_list(1000)
    
    insights = await db.health_insights_history.find(
        {"owner_id": owner_id, "created_at": {"$gte": cutoff_iso}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    
    symptom_checks = await db.symptom_checks_history.find(
        {"owner_id": owner_id, "created_at": {"$gte": cutoff_iso}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    
    # Compile comprehensive report
    report = {
        "report_type": "comprehensive_health_report",
        "generated_at": _now_iso(),
        "period_days": days,
        "period_start": cutoff_iso,
        "period_end": _now_iso(),
        "owner_id": owner_id,
        "tier": tier,
        
        "profile": profile,
        
        "summary": {
            "wearable_logs": len(wearable_data),
            "active_medications": len([m for m in medications if m.get("status") == "active"]),
            "medication_doses_logged": len(medication_logs),
            "active_goals": len([g for g in goals if g.get("status") == "active"]),
            "goal_progress_entries": len(goal_progress),
            "health_insights_generated": len(insights),
            "symptom_checks_performed": len(symptom_checks),
        },
        
        "wearable_data": wearable_data,
        "medications": medications,
        "medication_logs": medication_logs,
        "health_goals": goals,
        "goal_progress": goal_progress,
        "health_insights": insights,
        "symptom_checks": symptom_checks,
    }
    
    return {
        "format": "json",
        "report": report,
        "exported_at": _now_iso(),
        "filename": f"comprehensive_health_report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    }


# ══════════ PHASE 2: PROACTIVE HEALTH NUDGES ROUTES ══════════

@router.post("/nudges/generate")
async def generate_health_nudges(request: Request, fallback_user_id: Optional[str] = None):
    """Generate personalized proactive health nudges using AI."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Get recent health data for context
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    
    profile = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    # Recent activity
    recent_wearable = await db.wearable_data.find(
        {"owner_id": owner_id, "logged_at": {"$gte": yesterday.isoformat()}},
        {"_id": 0}
    ).to_list(50)
    
    # Medications due today
    medications = await db.medications.find(
        {"owner_id": owner_id, "status": "active"},
        {"_id": 0}
    ).to_list(100)
    
    # Active goals
    goals = await db.health_goals.find(
        {"owner_id": owner_id, "status": "active"},
        {"_id": 0}
    ).to_list(50)
    
    # Recent progress
    recent_progress = await db.goal_progress.find(
        {"owner_id": owner_id, "logged_at": {"$gte": week_ago.isoformat()}},
        {"_id": 0}
    ).sort("logged_at", -1).to_list(20)
    
    # Generate AI-powered nudges
    prompt = f"""Generate 3-5 personalized, actionable health nudges for this user.

User Context:
- Profile: {json.dumps(profile, default=str) if profile else "No profile"}
- Recent Activity (24h): {len(recent_wearable)} wearable logs
- Active Medications: {len(medications)}
- Active Goals: {len(goals)}
- Recent Progress Updates (7d): {len(recent_progress)}

Current Time: {now.strftime('%A, %I:%M %p')}

Generate proactive, encouraging health nudges. Focus on:
1. Medication reminders if applicable
2. Activity encouragement
3. Goal progress motivation
4. Hydration/movement if sedentary
5. Sleep quality tips

Return JSON:
{{
    "nudges": [
        {{
            "nudge_id": "unique_id",
            "type": "medication/activity/hydration/sleep/goal",
            "priority": "high/medium/low",
            "title": "Short catchy title",
            "message": "Encouraging actionable message",
            "action_button": "Take Action text",
            "context": "Why this nudge matters",
            "timing": "When to act (e.g., 'in next 30 minutes')"
        }}
    ],
    "personalization_factors": ["What data influenced these nudges"]
}}"""
    
    chat = LlmChat(
        api_key=EMERGENT_KEY,
        session_id=f"nudges-{uuid.uuid4()}",
        system_message="You are a motivational health coach generating personalized, actionable health nudges. Be encouraging, specific, and contextually relevant. Return valid JSON.",
    ).with_model("openai", "gpt-4o")
    
    response = await chat.send_message(UserMessage(text=prompt))
    
    try:
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        result = json.loads(response_text)
        nudges = result.get("nudges", [])
    except Exception:
        # Fallback nudges
        nudges = [
            {
                "nudge_id": f"nudge_{uuid.uuid4().hex[:8]}",
                "type": "activity",
                "priority": "medium",
                "title": "Time to Move!",
                "message": "You've been inactive for a while. A short 5-minute walk can boost your energy.",
                "action_button": "Start Activity",
                "context": "Regular movement improves circulation and mood",
                "timing": "Now"
            }
        ]
    
    # Save nudges to database
    for nudge in nudges:
        nudge["owner_id"] = owner_id
        nudge["status"] = "active"
        nudge["generated_at"] = _now_iso()
        nudge["tier_used"] = tier
        if "nudge_id" not in nudge:
            nudge["nudge_id"] = f"nudge_{uuid.uuid4().hex[:8]}"
    
    await db.health_nudges.insert_many(nudges)
    
    # Remove MongoDB _id field before returning (ObjectId not JSON serializable)
    for nudge in nudges:
        nudge.pop("_id", None)
    
    return {
        "message": f"Generated {len(nudges)} personalized health nudges",
        "nudges": nudges,
        "tier": tier
    }


@router.get("/nudges")
async def get_active_nudges(
    request: Request,
    fallback_user_id: Optional[str] = None,
    status: str = "active",
    limit: int = 10
):
    """Get active health nudges."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if status:
        query["status"] = status
    
    nudges = await db.health_nudges.find(
        query,
        {"_id": 0}
    ).sort("generated_at", -1).limit(limit).to_list(limit)
    
    return {
        "nudges": nudges,
        "count": len(nudges),
        "status_filter": status
    }


@router.post("/nudges/{nudge_id}/action")
async def mark_nudge_action_taken(
    nudge_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Mark a nudge as actioned (user took the suggested action)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.health_nudges.update_one(
        {"nudge_id": nudge_id, "owner_id": owner_id},
        {
            "$set": {
                "status": "completed",
                "completed_at": _now_iso()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "nudge_not_found", "message": "Nudge not found"}
        )
    
    return {
        "message": "Great job! Action completed.",
        "nudge_id": nudge_id
    }


@router.put("/nudges/preferences")
async def update_nudge_preferences(
    request: Request,
    fallback_user_id: Optional[str] = None,
    enabled_types: List[str] = [],
    frequency: str = "normal",  # low, normal, high
    quiet_hours_start: Optional[str] = None,  # "22:00"
    quiet_hours_end: Optional[str] = None  # "08:00"
):
    """Update nudge preferences."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    preferences = {
        "owner_id": owner_id,
        "enabled_types": enabled_types or ["medication", "activity", "hydration", "sleep", "goal"],
        "frequency": frequency,
        "quiet_hours_start": quiet_hours_start,
        "quiet_hours_end": quiet_hours_end,
        "updated_at": _now_iso()
    }
    
    await db.nudge_preferences.update_one(
        {"owner_id": owner_id},
        {"$set": preferences},
        upsert=True
    )
    
    return {
        "message": "Nudge preferences updated",
        "preferences": preferences
    }




@router.get("/dashboard")
async def get_health_dashboard(request: Request, fallback_user_id: Optional[str] = None):
    """Get health dashboard with overview stats."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Get profile
    profile = await db.health_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    
    # Get usage stats
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    start_of_week = (now - timedelta(days=7)).isoformat()
    
    # Wearable data summary
    wearable_count = await db.wearable_data.count_documents({
        "owner_id": owner_id,
        "logged_at": {"$gte": start_of_week}
    })
    
    # Recent data types
    recent_logs = await db.wearable_data.find(
        {"owner_id": owner_id},
        {"_id": 0, "data_type": 1}
    ).sort("logged_at", -1).limit(20).to_list(20)
    
    data_types_tracked = list(set([log.get("data_type") for log in recent_logs]))
    
    # Insights & checks
    insights_count = await db.health_insights_history.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    symptom_checks_count = await db.symptom_checks_history.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    # Get most recent insight
    latest_insight = await db.health_insights_history.find_one(
        {"owner_id": owner_id},
        {"_id": 0, "insights.overall_health_score": 1, "created_at": 1}
    )
    
    return {
        "owner_id": owner_id,
        "tier": tier,
        "profile": {
            "exists": bool(profile),
            "bmi": profile.get("bmi") if profile else None,
            "bmi_category": profile.get("bmi_category") if profile else None,
            "age": profile.get("age") if profile else None,
        },
        "activity_summary": {
            "wearable_logs_this_week": wearable_count,
            "data_types_tracked": data_types_tracked,
            "health_insights_this_month": insights_count,
            "symptom_checks_this_month": symptom_checks_count,
        },
        "latest_health_score": latest_insight.get("insights", {}).get("overall_health_score") if latest_insight else None,
        "last_check": latest_insight.get("created_at") if latest_insight else None,
    }
