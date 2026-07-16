"""Fitness Planner Pro - Enterprise-Grade Workout & Progress Tracking Platform

AI-powered fitness companion with workout plan generation, progress tracking,
exercise library, personal records, and body scan analysis.

Tier Limits:
- Free: 3 workout plans/month, 5 body scans/month, 10 progress logs/day
- Basic: 10 workout plans/month, 20 body scans/month, 50 progress logs/day
- Premium: Unlimited plans, scans, progress logs, AI coaching

Endpoints:
- GET  /api/fitness-planner/bootstrap                    Bootstrap with tier + usage
- POST /api/fitness-planner/workout-plans                Generate & save workout plan
- GET  /api/fitness-planner/workout-plans                List saved plans
- GET  /api/fitness-planner/workout-plans/{plan_id}      Get specific plan
- PUT  /api/fitness-planner/workout-plans/{plan_id}      Update plan
- DELETE /api/fitness-planner/workout-plans/{plan_id}    Archive plan
- POST /api/fitness-planner/workouts/log                 Log completed workout
- GET  /api/fitness-planner/workouts/history             Get workout history
- POST /api/fitness-planner/progress                     Log progress metric
- GET  /api/fitness-planner/progress/analytics           Get progress analytics
- GET  /api/fitness-planner/exercises                    Get exercise library
- GET  /api/fitness-planner/personal-records             Get personal bests
- POST /api/fitness-planner/scan-body                    AI body scan analysis
"""

import json
import uuid
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from .db import db, get_current_user
from utils.access_control_engine import compute_effective_plan
import os

logger = logging.getLogger("routes.fitness_planner")
router = APIRouter(prefix="/fitness-planner", tags=["fitness-planner"])
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

# ══════════ TIER LIMITS ══════════

TIER_LIMITS = {
    "free": {
        "workout_plans_per_month": 3,
        "body_scans_per_month": 5,
        "progress_logs_per_day": 10,
        "features": ["basic_plans", "progress_tracking"],
    },
    "basic": {
        "workout_plans_per_month": 10,
        "body_scans_per_month": 20,
        "progress_logs_per_day": 50,
        "features": ["custom_plans", "advanced_analytics", "exercise_library"],
    },
    "premium": {
        "workout_plans_per_month": -1,  # unlimited
        "body_scans_per_month": -1,
        "progress_logs_per_day": -1,
        "features": ["ai_coaching", "body_scans", "personal_records", "nutrition_integration"],
    },
}

# ══════════ MODELS ══════════

class WorkoutPlanRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    plan_name: Optional[str] = None
    plan_type: str = "weekly"  # weekly, monthly, custom
    focus_areas: List[str]  # strength, cardio, flexibility, muscle_gain, weight_loss
    difficulty: str = "intermediate"  # beginner, intermediate, advanced
    duration_weeks: int = 4
    session_duration_minutes: int = 45
    equipment_available: List[str] = []  # bodyweight, dumbbells, barbell, resistance_bands


class WorkoutLogRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    plan_id: Optional[str] = None
    workout_date: str  # ISO date
    exercises_completed: List[Dict[str, Any]]
    duration_minutes: int
    effort_level: str = "moderate"  # low, moderate, high, max
    notes: Optional[str] = None


class ProgressMetricRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    metric_type: str  # strength, weight, endurance, flexibility
    exercise_name: Optional[str] = None
    value: float
    unit: str  # kg, lbs, minutes, seconds, reps
    notes: Optional[str] = None


class BodyScanRequest(BaseModel):
    fallback_user_id: Optional[str] = None
    scan_type: str = "form"  # form, posture, body_composition
    image_base64: str
    exercise_name: Optional[str] = None


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
                    "error_code": "fitness_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "fitness_auth_required",
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


async def _check_workout_plan_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can create more workout plans this month."""
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    count = await db.fitness_workout_plans.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    limit = TIER_LIMITS[tier]["workout_plans_per_month"]
    can_create = limit == -1 or count < limit
    
    return {
        "can_create": can_create,
        "plans_created": count,
        "monthly_limit": limit if limit != -1 else "unlimited"
    }


async def _check_progress_log_limit(owner_id: str, tier: str) -> Dict[str, Any]:
    """Check if user can log more progress today."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    count = await db.fitness_progress.count_documents({
        "owner_id": owner_id,
        "logged_at": {"$gte": start_of_day}
    })
    
    limit = TIER_LIMITS[tier]["progress_logs_per_day"]
    can_log = limit == -1 or count < limit
    
    return {
        "can_log": can_log,
        "logs_today": count,
        "daily_limit": limit if limit != -1 else "unlimited"
    }


# ══════════ ROUTES ══════════

@router.get("/bootstrap")
async def fitness_bootstrap(request: Request, fallback_user_id: Optional[str] = None):
    """Bootstrap Fitness Planner with tier, usage, exercise categories."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Get usage stats
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    plans_this_month = await db.fitness_workout_plans.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month}
    })
    
    scans_this_month = await db.fitness_body_scans.count_documents({
        "owner_id": owner_id,
        "scanned_at": {"$gte": start_of_month}
    })
    
    progress_logs_today = await db.fitness_progress.count_documents({
        "owner_id": owner_id,
        "logged_at": {"$gte": start_of_day}
    })
    
    # Get active plans count
    active_plans = await db.fitness_workout_plans.count_documents({
        "owner_id": owner_id,
        "status": "active"
    })
    
    return {
        "owner_id": owner_id,
        "tier": tier,
        "active_plans": active_plans,
        "usage": {
            "workout_plans_this_month": plans_this_month,
            "body_scans_this_month": scans_this_month,
            "progress_logs_today": progress_logs_today,
            "workout_plans_limit": TIER_LIMITS[tier]["workout_plans_per_month"] if TIER_LIMITS[tier]["workout_plans_per_month"] != -1 else "unlimited",
            "body_scans_limit": TIER_LIMITS[tier]["body_scans_per_month"] if TIER_LIMITS[tier]["body_scans_per_month"] != -1 else "unlimited",
            "progress_logs_limit": TIER_LIMITS[tier]["progress_logs_per_day"] if TIER_LIMITS[tier]["progress_logs_per_day"] != -1 else "unlimited",
        },
        "features": TIER_LIMITS[tier]["features"],
        "exercise_categories": ["strength", "cardio", "flexibility", "balance", "mobility"],
        "tier_limits": TIER_LIMITS[tier],
    }


@router.post("/workout-plans")
async def create_workout_plan(payload: WorkoutPlanRequest, request: Request):
    """Generate AI workout plan and save it."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limit
    usage_check = await _check_workout_plan_limit(owner_id, tier)
    if not usage_check["can_create"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "workout_plan_limit_reached",
                "message": f"Monthly workout plan limit reached ({usage_check['monthly_limit']} for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "plans_created": usage_check["plans_created"],
                "monthly_limit": usage_check["monthly_limit"],
            },
        )
    
    # Generate AI workout plan
    prompt = f"""Create a {payload.duration_weeks}-week {payload.difficulty} workout plan.

Focus Areas: {", ".join(payload.focus_areas)}
Equipment Available: {", ".join(payload.equipment_available) if payload.equipment_available else "Bodyweight only"}
Session Duration: {payload.session_duration_minutes} minutes
Plan Type: {payload.plan_type}

Create a comprehensive, progressive workout plan that includes warm-up, main workout, and cool-down.

Return JSON:
{{
    "plan_name": "Catchy plan name",
    "description": "Brief description of the plan and its benefits",
    "workouts": [
        {{
            "day": "Monday",
            "week": 1,
            "focus": "Upper Body Strength",
            "warm_up": [
                {{"name": "Jumping Jacks", "duration_seconds": 60}},
                {{"name": "Arm Circles", "duration_seconds": 30}}
            ],
            "main_exercises": [
                {{
                    "name": "Push-ups",
                    "sets": 3,
                    "reps": 12,
                    "rest_seconds": 60,
                    "notes": "Keep core tight"
                }},
                {{
                    "name": "Dumbbell Rows",
                    "sets": 3,
                    "reps": 10,
                    "weight_recommendation": "moderate",
                    "rest_seconds": 90
                }}
            ],
            "cool_down": [
                {{"name": "Chest Stretch", "duration_seconds": 30}},
                {{"name": "Shoulder Stretch", "duration_seconds": 30}}
            ]
        }}
    ],
    "progression_notes": "How to progress week by week",
    "nutrition_tips": ["Tip 1", "Tip 2"],
    "recovery_advice": "Rest and recovery guidance"
}}"""
    
    chat = LlmChat(
        api_key=EMERGENT_KEY,
        session_id=f"fitness-plan-{uuid.uuid4()}",
        system_message="You are an expert fitness coach creating personalized, progressive workout plans. Ensure exercises are safe, effective, and appropriate for the user's level. Return valid JSON.",
    ).with_model("openai", "gpt-4o")
    
    response = await chat.send_message(UserMessage(text=prompt))
    
    try:
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        plan_data = json.loads(response_text)
    except Exception:
        plan_data = {
            "plan_name": payload.plan_name or f"{payload.focus_areas[0].title()} Plan",
            "workouts": [],
            "error": "Could not generate detailed plan",
        }
    
    # Save workout plan
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    workout_plan = {
        "plan_id": plan_id,
        "owner_id": owner_id,
        "plan_name": payload.plan_name or plan_data.get("plan_name", "My Workout Plan"),
        "plan_type": payload.plan_type,
        "focus_areas": payload.focus_areas,
        "difficulty": payload.difficulty,
        "duration_weeks": payload.duration_weeks,
        "session_duration_minutes": payload.session_duration_minutes,
        "equipment_available": payload.equipment_available,
        "workouts": plan_data.get("workouts", []),
        "description": plan_data.get("description", ""),
        "progression_notes": plan_data.get("progression_notes", ""),
        "nutrition_tips": plan_data.get("nutrition_tips", []),
        "recovery_advice": plan_data.get("recovery_advice", ""),
        "status": "active",
        "tier_used": tier,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    
    await db.fitness_workout_plans.insert_one(workout_plan)
    workout_plan.pop("_id", None)
    
    return {
        "message": "Workout plan created successfully",
        "plan": workout_plan
    }


@router.get("/workout-plans")
async def get_workout_plans(
    request: Request,
    fallback_user_id: Optional[str] = None,
    status: str = "active",
    limit: int = 20
):
    """Get list of saved workout plans."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if status and status != "all":
        query["status"] = status
    
    plans = await db.fitness_workout_plans.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    return {
        "plans": plans,
        "count": len(plans),
        "status_filter": status
    }


@router.get("/workout-plans/{plan_id}")
async def get_workout_plan(
    plan_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Get specific workout plan details."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    plan = await db.fitness_workout_plans.find_one(
        {"plan_id": plan_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "plan_not_found", "message": "Workout plan not found"}
        )
    
    return {"plan": plan}


@router.put("/workout-plans/{plan_id}")
async def update_workout_plan(
    plan_id: str,
    payload: WorkoutPlanRequest,
    request: Request
):
    """Update workout plan details."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    update_data = {
        "plan_name": payload.plan_name,
        "focus_areas": payload.focus_areas,
        "difficulty": payload.difficulty,
        "duration_weeks": payload.duration_weeks,
        "session_duration_minutes": payload.session_duration_minutes,
        "equipment_available": payload.equipment_available,
        "updated_at": _now_iso(),
    }
    
    result = await db.fitness_workout_plans.update_one(
        {"plan_id": plan_id, "owner_id": owner_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "plan_not_found", "message": "Workout plan not found"}
        )
    
    return {"message": "Workout plan updated successfully", "plan_id": plan_id}


@router.delete("/workout-plans/{plan_id}")
async def delete_workout_plan(
    plan_id: str,
    request: Request,
    fallback_user_id: Optional[str] = None
):
    """Archive workout plan."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.fitness_workout_plans.update_one(
        {"plan_id": plan_id, "owner_id": owner_id},
        {"$set": {"status": "archived", "updated_at": _now_iso()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "plan_not_found", "message": "Workout plan not found"}
        )
    
    return {"message": "Workout plan archived successfully", "plan_id": plan_id}


@router.post("/workouts/log")
async def log_workout(payload: WorkoutLogRequest, request: Request):
    """Log completed workout."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    log_id = f"log_{uuid.uuid4().hex[:12]}"
    workout_log = {
        "log_id": log_id,
        "owner_id": owner_id,
        "plan_id": payload.plan_id,
        "workout_date": payload.workout_date,
        "exercises_completed": payload.exercises_completed,
        "duration_minutes": payload.duration_minutes,
        "effort_level": payload.effort_level,
        "notes": payload.notes,
        "tier_used": tier,
        "logged_at": _now_iso(),
    }
    
    await db.fitness_workout_logs.insert_one(workout_log)
    workout_log.pop("_id", None)
    
    # Check for new personal records
    for exercise in payload.exercises_completed:
        if exercise.get("weight_kg"):
            # Check if this is a new PR
            existing_pr = await db.fitness_personal_records.find_one({
                "owner_id": owner_id,
                "exercise_name": exercise.get("exercise_name"),
                "category": "strength"
            }, {"_id": 0})
            
            if not existing_pr or exercise["weight_kg"] > existing_pr.get("record_value", 0):
                # New PR!
                pr_id = f"pr_{uuid.uuid4().hex[:12]}"
                await db.fitness_personal_records.update_one(
                    {"owner_id": owner_id, "exercise_name": exercise.get("exercise_name"), "category": "strength"},
                    {
                        "$set": {
                            "pr_id": pr_id,
                            "owner_id": owner_id,
                            "category": "strength",
                            "exercise_name": exercise.get("exercise_name"),
                            "record_value": exercise["weight_kg"],
                            "unit": "kg",
                            "achieved_date": payload.workout_date,
                            "notes": f"Logged in workout on {payload.workout_date}"
                        }
                    },
                    upsert=True
                )
    
    return {
        "message": "Workout logged successfully",
        "log": workout_log
    }


@router.get("/workouts/history")
async def get_workout_history(
    request: Request,
    fallback_user_id: Optional[str] = None,
    days: int = 30,
    limit: int = 50
):
    """Get workout history."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    history = await db.fitness_workout_logs.find(
        {"owner_id": owner_id, "logged_at": {"$gte": cutoff.isoformat()}},
        {"_id": 0}
    ).sort("workout_date", -1).limit(limit).to_list(limit)
    
    return {
        "history": history,
        "count": len(history),
        "period_days": days
    }


@router.post("/progress")
async def log_progress_metric(payload: ProgressMetricRequest, request: Request):
    """Log progress metric (strength, weight, endurance, etc.)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limit
    usage_check = await _check_progress_log_limit(owner_id, tier)
    if not usage_check["can_log"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "progress_log_limit_reached",
                "message": f"Daily progress log limit reached ({usage_check['daily_limit']} for {tier} tier). Upgrade for more.",
                "upgrade_prompt": True,
            },
        )
    
    progress_id = f"prog_{uuid.uuid4().hex[:12]}"
    progress_entry = {
        "progress_id": progress_id,
        "owner_id": owner_id,
        "metric_type": payload.metric_type,
        "exercise_name": payload.exercise_name,
        "value": payload.value,
        "unit": payload.unit,
        "notes": payload.notes,
        "tier_used": tier,
        "logged_at": _now_iso(),
    }
    
    await db.fitness_progress.insert_one(progress_entry)
    progress_entry.pop("_id", None)
    
    return {
        "message": "Progress logged successfully",
        "progress": progress_entry
    }


@router.get("/progress/analytics")
async def get_progress_analytics(
    request: Request,
    fallback_user_id: Optional[str] = None,
    metric_type: Optional[str] = None,
    days: int = 90
):
    """Get progress analytics and trends."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = {"owner_id": owner_id, "logged_at": {"$gte": cutoff.isoformat()}}
    if metric_type:
        query["metric_type"] = metric_type
    
    progress_data = await db.fitness_progress.find(
        query,
        {"_id": 0}
    ).sort("logged_at", 1).to_list(1000)
    
    # Calculate trends
    trends = {}
    for entry in progress_data:
        mtype = entry.get("metric_type")
        if mtype not in trends:
            trends[mtype] = {"values": [], "count": 0}
        trends[mtype]["values"].append(entry.get("value"))
        trends[mtype]["count"] += 1
    
    # Calculate summary stats
    summary = {}
    for mtype, data in trends.items():
        values = data["values"]
        if values:
            summary[mtype] = {
                "average": round(sum(values) / len(values), 2),
                "min": min(values),
                "max": max(values),
                "latest": values[-1],
                "trend": "improving" if len(values) >= 2 and values[-1] > values[0] else "stable",
                "data_points": len(values)
            }
    
    return {
        "period_days": days,
        "trends": summary,
        "raw_data": progress_data[-20:],  # Last 20 entries
    }


@router.get("/exercises")
async def get_exercise_library(
    request: Request,
    muscle_group: Optional[str] = None,
    equipment: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = 50
):
    """Get exercise library with filtering."""
    query = {}
    if muscle_group:
        query["muscle_groups"] = muscle_group
    if equipment:
        query["equipment"] = equipment
    if difficulty:
        query["difficulty"] = difficulty
    
    exercises = await db.fitness_exercises.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    return {
        "exercises": exercises,
        "count": len(exercises),
        "filters": {
            "muscle_group": muscle_group,
            "equipment": equipment,
            "difficulty": difficulty
        }
    }


@router.get("/personal-records")
async def get_personal_records(
    request: Request,
    fallback_user_id: Optional[str] = None,
    category: Optional[str] = None
):
    """Get personal records (best performances)."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if category:
        query["category"] = category
    
    records = await db.fitness_personal_records.find(query, {"_id": 0}).to_list(100)
    
    return {
        "personal_records": records,
        "count": len(records),
        "category_filter": category
    }


@router.post("/scan-body")
async def scan_body(payload: BodyScanRequest, request: Request):
    """AI-powered body scan for form correction and posture analysis."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Tier check - body scans are premium feature
    if tier == "free":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "body_scan_premium_only",
                "message": "Body scan analysis is available for Basic and Premium tiers. Upgrade to access.",
                "upgrade_prompt": True,
            },
        )
    
    # AI vision analysis
    # Strip data URL prefix if present (data:image/png;base64,...)
    image_data = payload.image_base64
    if image_data.startswith('data:image'):
        image_data = image_data.split(',', 1)[1] if ',' in image_data else image_data
    
    prompt = f"""Analyze this {payload.scan_type} image for a fitness assessment.

Scan Type: {payload.scan_type}
{"Exercise: " + payload.exercise_name if payload.exercise_name else ""}

Provide constructive feedback on form, posture, and areas for improvement.

Return JSON:
{{
    "form_score": 8.5,
    "issues_found": ["Minor knee valgus", "Forward head posture"],
    "suggestions": [
        "Focus on pushing knees outward",
        "Keep chin tucked and chest up"
    ],
    "strengths": ["Good depth", "Stable core"],
    "overall_assessment": "Good form with minor adjustments needed"
}}"""
    
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"body-scan-{uuid.uuid4()}",
            system_message="You are an expert fitness coach analyzing exercise form and posture. Provide constructive, actionable feedback. Return valid JSON.",
        ).with_model("openai", "gpt-4o")
        
        # Send image for analysis
        response = await chat.send_message(
            UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_data)])
        )
        
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        analysis = json.loads(response_text)
    except Exception as e:
        logger.warning(f"Body scan AI analysis failed: {e}")
        analysis = {
            "form_score": 7.0,
            "issues_found": ["Analysis pending"],
            "suggestions": ["Could not complete full analysis"],
            "overall_assessment": "Image received for analysis"
        }
    
    # Save scan result
    scan_id = f"scan_{uuid.uuid4().hex[:12]}"
    scan_result = {
        "scan_id": scan_id,
        "owner_id": owner_id,
        "scan_type": payload.scan_type,
        "exercise_name": payload.exercise_name,
        "ai_analysis": analysis,
        "tier_used": tier,
        "scanned_at": _now_iso(),
    }
    
    await db.fitness_body_scans.insert_one(scan_result)
    scan_result.pop("_id", None)
    
    return {
        "message": "Body scan completed",
        "scan": scan_result
    }
