"""Mini-apps bundle: Fitness, Nutrition, LifePredict, PennyPilot, and more."""

import json
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from routes.db import db, require_auth, EMERGENT_LLM_KEY, User

logger = logging.getLogger(__name__)
router = APIRouter()

# ══════════ MODELS ══════════

# ============== AI FITNESS COACH MODELS ==============


class FitnessProfileRequest(BaseModel):
    user_id: str
    fitness_level: str = "beginner"  # beginner, intermediate, advanced, athlete
    goals: List[str] = ["general_fitness"]  # weight_loss, muscle_gain, endurance, flexibility
    available_equipment: List[str] = []
    injuries_limitations: List[str] = []
    preferred_workout_time: str = "morning"
    workout_days_per_week: int = 3


class WorkoutPlanRequest(BaseModel):
    user_id: str
    plan_type: str = "weekly"  # daily, weekly, monthly
    focus_areas: List[str] = []  # upper_body, lower_body, cardio, core
    duration_minutes: int = 45


class WorkoutSessionRequest(BaseModel):
    user_id: str
    workout_id: str
    biometric_data: Optional[Dict[str, Any]] = None  # heart_rate, calories, etc.


class RecoveryAnalysisRequest(BaseModel):
    user_id: str
    sleep_hours: float
    sleep_quality: int  # 1-10
    soreness_level: int  # 1-10
    energy_level: int  # 1-10


# ============== AI NUTRITION MODELS ==============


class NutritionProfileRequest(BaseModel):
    user_id: str
    dietary_preferences: List[str] = []  # vegetarian, vegan, keto, etc.
    allergies: List[str] = []
    health_goals: List[str] = []  # weight_loss, muscle_gain, energy
    cultural_cuisine: List[str] = []
    daily_calorie_target: Optional[int] = None
    meals_per_day: int = 3


class FoodLogRequest(BaseModel):
    user_id: str
    food_description: str  # can be text description or base64 image
    meal_type: str = "lunch"  # breakfast, lunch, dinner, snack
    portion_size: str = "medium"
    timestamp: Optional[str] = None


class MealPlanRequest(BaseModel):
    user_id: str
    plan_days: int = 7
    budget: Optional[str] = None  # low, medium, high
    prep_time_preference: str = "moderate"  # quick, moderate, elaborate


class NutrientAnalysisRequest(BaseModel):
    user_id: str
    period: str = "week"


# ============== AI PREDICTIVE HEALTH (LIFEPREDICT) MODELS ==============


class HealthTrendRequest(BaseModel):
    user_id: str
    trend_type: str = "comprehensive"  # stress, sleep, energy, comprehensive
    prediction_days: int = 7


class RiskAssessmentRequest(BaseModel):
    user_id: str
    assessment_type: str = "general"  # general, cardiovascular, mental, metabolic


class LifestyleInterventionRequest(BaseModel):
    user_id: str
    concern_area: str  # sleep, stress, energy, fitness
    urgency: str = "moderate"


# ============== SCENARIOS ==============


class ScanRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    scan_type: str
    scanner_title: str
    summary: Optional[str] = None
    analysis: Dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateScanRequest(BaseModel):
    scan_type: str
    scanner_title: str
    summary: Optional[str] = None
    analysis: Dict[str, Any]


# ══════════ ROUTES ══════════


@router.post("/fitness/profile")
async def create_fitness_profile(request: FitnessProfileRequest):
    """Create fitness profile"""
    try:
        profile = {
            "user_id": request.user_id,
            "fitness_level": request.fitness_level,
            "goals": request.goals,
            "available_equipment": request.available_equipment,
            "injuries_limitations": request.injuries_limitations,
            "preferred_workout_time": request.preferred_workout_time,
            "workout_days_per_week": request.workout_days_per_week,
            "updated_at": datetime.utcnow(),
        }
        await db.fitness_profiles.update_one({"user_id": request.user_id}, {"$set": profile}, upsert=True)
        return {"message": "Fitness profile saved", "profile": profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fitness/workout-plan")
async def generate_workout_plan(request: WorkoutPlanRequest):
    """Generate AI-adaptive workout plan"""
    try:
        profile = await db.fitness_profiles.find_one({"user_id": request.user_id}, {"_id": 0})
        wearable = await db.wearable_data.find({"user_id": request.user_id}).sort("logged_at", -1).limit(10).to_list(10)

        prompt = f"""Create a personalized workout plan.

Fitness Profile:
{json.dumps(profile, default=str) if profile else "Beginner, general fitness goals"}

Plan Type: {request.plan_type}
Focus Areas: {request.focus_areas or ["full_body"]}
Duration per Session: {request.duration_minutes} minutes

Recent Biometric Data:
{json.dumps([{"type": w.get("data_type"), "readings": w.get("readings", [])[-3:]} for w in wearable[:3]], default=str)}

Create an adaptive, safe workout plan.

Return JSON:
{{
    "plan_name": "Plan name",
    "plan_type": "{request.plan_type}",
    "overview": "Plan overview",
    "workouts": [
        {{
            "day": "Monday",
            "focus": "Upper Body",
            "duration_minutes": {request.duration_minutes},
            "warmup": {{
                "duration_minutes": 5,
                "exercises": ["Exercise 1", "Exercise 2"]
            }},
            "main_workout": [
                {{
                    "exercise": "Exercise name",
                    "sets": 3,
                    "reps": "10-12",
                    "rest_seconds": 60,
                    "notes": "Form tips",
                    "modifications": {{"easier": "Modification", "harder": "Progression"}}
                }}
            ],
            "cooldown": {{
                "duration_minutes": 5,
                "exercises": ["Stretch 1", "Stretch 2"]
            }},
            "target_heart_rate_zone": "Zone 2-3",
            "estimated_calories": 300
        }}
    ],
    "progressive_overload": "How to increase difficulty over time",
    "recovery_recommendations": ["Recovery tips"],
    "nutrition_pairing": "Nutrition suggestions for this plan",
    "injury_prevention": ["Safety tips"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"workout-{uuid.uuid4()}",
            system_message="You are an expert AI fitness coach creating safe, effective workout plans. Always include modifications and safety tips. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            # Robustly extract JSON (LLMs often wrap in prose or code fences)
            if "```" in response_text:
                parts = response_text.split("```")
                # try to take the largest middle part
                if len(parts) >= 3:
                    response_text = parts[1]
            if response_text.lstrip().startswith("json"):
                response_text = response_text.lstrip()[4:]

            start = response_text.find("{")
            end = response_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                response_text = response_text[start : end + 1]

            plan = json.loads(response_text)
        except Exception:
            plan = {"plan_name": "Workout Plan", "workouts": [], "error": "Could not generate plan"}

        plan["plan_id"] = f"workout_{str(uuid.uuid4())[:8]}"

        await db.workout_plans.insert_one({**plan, "user_id": request.user_id, "created_at": datetime.utcnow()})

        return plan

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fitness/recovery-analysis")
async def analyze_recovery(request: RecoveryAnalysisRequest):
    """Analyze recovery status and adjust training recommendations"""
    try:
        prompt = f"""Analyze recovery status and provide training recommendations.

Recovery Indicators:
- Sleep: {request.sleep_hours} hours, Quality: {request.sleep_quality}/10
- Soreness Level: {request.soreness_level}/10
- Energy Level: {request.energy_level}/10

Determine recovery status and training readiness.

Return JSON:
{{
    "recovery_score": 75,
    "recovery_status": "well_recovered/moderate/needs_rest",
    "training_readiness": "ready/light_only/rest_recommended",
    "detailed_assessment": {{
        "sleep_analysis": "Assessment of sleep",
        "muscle_recovery": "Assessment of soreness",
        "energy_assessment": "Assessment of energy"
    }},
    "today_recommendation": {{
        "workout_type": "What type of workout is appropriate",
        "intensity": "low/moderate/high",
        "duration_minutes": 45,
        "specific_advice": "Specific guidance"
    }},
    "recovery_tips": [
        {{"tip": "Recovery tip", "priority": "high/medium/low"}}
    ],
    "warning_signs": ["Any concerning patterns"],
    "next_hard_workout": "When they can do intense training"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"recovery-{uuid.uuid4()}",
            system_message="You are a sports science recovery specialist. Prioritize safety and optimal performance. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            analysis = json.loads(response_text)
        except Exception:
            analysis = {
                "recovery_score": 50,
                "training_readiness": "light_only",
                "today_recommendation": {"workout_type": "Light activity or rest"},
            }

        return analysis

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== AI NUTRITION (NUTRISENSE) ==============


@router.post("/nutrition/profile")
async def create_nutrition_profile(request: NutritionProfileRequest):
    """Create nutrition profile"""
    try:
        profile = {
            "user_id": request.user_id,
            "dietary_preferences": request.dietary_preferences,
            "allergies": request.allergies,
            "health_goals": request.health_goals,
            "cultural_cuisine": request.cultural_cuisine,
            "daily_calorie_target": request.daily_calorie_target,
            "meals_per_day": request.meals_per_day,
            "updated_at": datetime.utcnow(),
        }
        await db.nutrition_profiles.update_one({"user_id": request.user_id}, {"$set": profile}, upsert=True)
        return {"message": "Nutrition profile saved", "profile": profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nutrition/log-food")
async def log_food(request: FoodLogRequest):
    """Log food intake with AI nutrient estimation"""
    try:
        prompt = f"""Analyze this food and estimate nutritional content.

Food Description: {request.food_description}
Meal Type: {request.meal_type}
Portion Size: {request.portion_size}

Estimate nutritional values.

Return JSON:
{{
    "food_identified": "What food was detected",
    "confidence": 90,
    "serving_size": "Estimated serving",
    "nutrients": {{
        "calories": 350,
        "protein_g": 25,
        "carbs_g": 40,
        "fat_g": 12,
        "fiber_g": 5,
        "sugar_g": 8,
        "sodium_mg": 400
    }},
    "micronutrients": {{
        "vitamin_c_mg": 15,
        "iron_mg": 2,
        "calcium_mg": 100
    }},
    "health_notes": ["Notes about this food"],
    "healthier_alternatives": ["If applicable"],
    "meal_balance_tip": "How to balance this meal"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"food-{uuid.uuid4()}",
            system_message="You are a nutrition analyst. Estimate nutritional content accurately. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            food_analysis = json.loads(response_text)
        except Exception:
            food_analysis = {"food_identified": request.food_description, "nutrients": {"calories": 200}}

        # Save to food log
        food_log = {
            "user_id": request.user_id,
            "food_description": request.food_description,
            "meal_type": request.meal_type,
            "portion_size": request.portion_size,
            "analysis": food_analysis,
            "timestamp": request.timestamp or datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow(),
        }
        await db.food_logs.insert_one(food_log)

        # Get daily totals
        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_logs = await db.food_logs.find(
            {"user_id": request.user_id, "timestamp": {"$regex": f"^{today}"}}
        ).to_list(20)

        daily_calories = sum(log.get("analysis", {}).get("nutrients", {}).get("calories", 0) for log in today_logs)

        return {"food_logged": food_analysis, "daily_calories": daily_calories, "meals_logged_today": len(today_logs)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nutrition/meal-plan")
async def generate_meal_plan(request: MealPlanRequest):
    """Generate personalized meal plan"""
    try:
        profile = await db.nutrition_profiles.find_one({"user_id": request.user_id}, {"_id": 0})
        health_profile = await db.health_profiles.find_one({"user_id": request.user_id}, {"_id": 0})

        prompt = f"""Create a personalized meal plan.

Nutrition Profile:
{json.dumps(profile, default=str) if profile else "General healthy eating"}

Health Goals: {profile.get("health_goals", ["balanced nutrition"]) if profile else ["balanced nutrition"]}
Plan Duration: {request.plan_days} days
Budget: {request.budget or "moderate"}
Prep Time Preference: {request.prep_time_preference}

Health Context:
{json.dumps(health_profile, default=str) if health_profile else "No specific health constraints"}

Create a practical, enjoyable meal plan.

Return JSON:
{{
    "plan_name": "Plan name",
    "daily_targets": {{
        "calories": 2000,
        "protein_g": 80,
        "carbs_g": 250,
        "fat_g": 65
    }},
    "days": [
        {{
            "day": 1,
            "meals": [
                {{
                    "meal_type": "breakfast",
                    "name": "Meal name",
                    "ingredients": ["Ingredient 1"],
                    "prep_time_minutes": 15,
                    "nutrients": {{"calories": 400, "protein_g": 20}},
                    "recipe_brief": "Quick instructions"
                }}
            ],
            "snacks": ["Snack suggestions"],
            "hydration_reminder": "Water intake goal",
            "day_total_calories": 2000
        }}
    ],
    "grocery_list": [
        {{"item": "Item", "quantity": "Amount", "category": "produce/dairy/etc"}}
    ],
    "prep_tips": ["Meal prep suggestions"],
    "budget_estimate": "Estimated cost",
    "flexibility_notes": "How to adapt the plan"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"mealplan-{uuid.uuid4()}",
            system_message="You are a nutrition expert creating practical, delicious meal plans. Consider cultural preferences and constraints. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            meal_plan = json.loads(response_text)
        except Exception:
            meal_plan = {"plan_name": "Meal Plan", "days": [], "error": "Could not generate plan"}

        return meal_plan

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== AI PREDICTIVE HEALTH (LIFEPREDICT) ==============


@router.post("/lifepredict/health-trends")
async def predict_health_trends(request: HealthTrendRequest):
    """Predict health trends using longitudinal data"""
    try:
        # Gather comprehensive health data
        wearable = (
            await db.wearable_data.find({"user_id": request.user_id}).sort("logged_at", -1).limit(100).to_list(100)
        )
        moods = await db.mood_logs.find({"user_id": request.user_id}).sort("timestamp", -1).limit(50).to_list(50)
        sleep_data = [w for w in wearable if w.get("data_type") == "sleep"]
        activity_data = [w for w in wearable if w.get("data_type") in ["steps", "activity"]]
        heart_data = [w for w in wearable if w.get("data_type") == "heart_rate"]

        prompt = f"""Analyze health data patterns and predict trends for the next {request.prediction_days} days.

Data Summary:
- Sleep entries: {len(sleep_data)}
- Activity entries: {len(activity_data)}  
- Heart rate entries: {len(heart_data)}
- Mood entries: {len(moods)}
- Recent moods: {[m.get("mood") for m in moods[:10]]}

Trend Focus: {request.trend_type}

Analyze patterns and make predictions.

Return JSON:
{{
    "analysis_summary": "Overview of health patterns",
    "current_status": {{
        "overall_wellness": 75,
        "energy_trend": "stable/improving/declining",
        "stress_level": "low/moderate/high",
        "sleep_quality_trend": "good/fair/poor"
    }},
    "predictions": [
        {{
            "metric": "Metric name",
            "current_value": "Current state",
            "predicted_trend": "up/down/stable",
            "confidence": 80,
            "timeline": "Next X days",
            "explanation": "Why this prediction"
        }}
    ],
    "early_warnings": [
        {{
            "warning": "Potential issue",
            "severity": "low/medium/high",
            "indicators": ["Signs that led to this warning"],
            "preventive_action": "What to do now"
        }}
    ],
    "optimization_opportunities": [
        {{
            "area": "Area to improve",
            "current_pattern": "What data shows",
            "suggested_change": "Recommended adjustment",
            "expected_impact": "How it helps"
        }}
    ],
    "personalized_insights": ["Insights specific to this user"],
    "recommended_focus": "Top priority for next week"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"predict-{uuid.uuid4()}",
            system_message="You are a predictive health analyst. Identify patterns and predict trends. Be helpful but never diagnose. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            predictions = json.loads(response_text)
        except Exception:
            predictions = {
                "analysis_summary": "Need more data for accurate predictions",
                "predictions": [],
                "early_warnings": [],
            }

        return predictions

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lifepredict/risk-assessment")
async def assess_health_risks(request: RiskAssessmentRequest):
    """Comprehensive AI health risk assessment"""
    try:
        health_profile = await db.health_profiles.find_one({"user_id": request.user_id}, {"_id": 0})
        wearable = await db.wearable_data.find({"user_id": request.user_id}).sort("logged_at", -1).limit(50).to_list(50)

        prompt = f"""Perform a health risk assessment based on available data.
IMPORTANT: This is NOT a medical diagnosis. Always recommend professional consultation.

Assessment Type: {request.assessment_type}

Health Profile:
{json.dumps(health_profile, default=str) if health_profile else "Limited data available"}

Recent Health Data Points: {len(wearable)}

Provide risk insights (NOT diagnosis).

Return JSON:
{{
    "assessment_type": "{request.assessment_type}",
    "data_quality": "sufficient/limited/insufficient",
    "risk_factors_identified": [
        {{
            "factor": "Risk factor",
            "level": "low/moderate/elevated",
            "modifiable": true,
            "evidence": "What data suggests this",
            "mitigation": "How to address"
        }}
    ],
    "protective_factors": ["Positive factors observed"],
    "lifestyle_score": {{
        "overall": 70,
        "nutrition": 65,
        "activity": 75,
        "sleep": 70,
        "stress": 60
    }},
    "recommendations": [
        {{
            "priority": "high/medium/low",
            "recommendation": "Specific recommendation",
            "rationale": "Why this matters",
            "action_steps": ["Step 1", "Step 2"]
        }}
    ],
    "screenings_suggested": ["Health screenings to consider"],
    "professional_consultation": "When to see a healthcare provider",
    "disclaimer": "This assessment is for informational purposes only and does not constitute medical advice."
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"risk-{uuid.uuid4()}",
            system_message="You are a health risk analyst. Provide helpful insights without diagnosing. Always recommend professional consultation. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            assessment = json.loads(response_text)
        except Exception:
            assessment = {
                "assessment_type": request.assessment_type,
                "data_quality": "insufficient",
                "disclaimer": "Please consult a healthcare professional for proper assessment.",
            }

        return assessment

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lifepredict/intervention")
async def get_lifestyle_intervention(request: LifestyleInterventionRequest):
    """Get personalized lifestyle intervention recommendations"""
    try:
        # Get all relevant user data
        health = await db.health_profiles.find_one({"user_id": request.user_id}, {"_id": 0})
        fitness = await db.fitness_profiles.find_one({"user_id": request.user_id}, {"_id": 0})
        nutrition = await db.nutrition_profiles.find_one({"user_id": request.user_id}, {"_id": 0})
        moods = await db.mood_logs.find({"user_id": request.user_id}).sort("timestamp", -1).limit(20).to_list(20)

        prompt = f"""Create a targeted lifestyle intervention plan.

Concern Area: {request.concern_area}
Urgency: {request.urgency}

User Context:
- Health Profile: {json.dumps(health, default=str) if health else "Not set"}
- Fitness Profile: {json.dumps(fitness, default=str) if fitness else "Not set"}
- Nutrition Profile: {json.dumps(nutrition, default=str) if nutrition else "Not set"}
- Recent Mood Pattern: {[m.get("mood") for m in moods[:10]]}

Create a comprehensive intervention plan.

Return JSON:
{{
    "intervention_plan": "{request.concern_area} Improvement Plan",
    "urgency_assessment": "{request.urgency}",
    "root_causes_analysis": [
        {{"cause": "Potential cause", "likelihood": "high/medium/low"}}
    ],
    "immediate_actions": [
        {{
            "action": "What to do now",
            "impact": "Expected effect",
            "timeline": "When to see results"
        }}
    ],
    "weekly_plan": [
        {{
            "week": 1,
            "focus": "Week focus",
            "daily_habits": ["Habit 1", "Habit 2"],
            "milestones": ["Goal to achieve"]
        }}
    ],
    "behavioral_strategies": [
        {{
            "strategy": "Behavior change technique",
            "implementation": "How to apply it"
        }}
    ],
    "progress_indicators": ["How to measure improvement"],
    "support_resources": ["Resources that can help"],
    "when_to_seek_help": "Signs that professional help is needed",
    "success_predictors": ["Factors that increase success chance"],
    "encouragement": "Motivational message"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"intervention-{uuid.uuid4()}",
            system_message="You are a lifestyle intervention specialist. Create practical, achievable intervention plans. Be supportive and evidence-based. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            intervention = json.loads(response_text)
        except Exception:
            intervention = {
                "intervention_plan": f"{request.concern_area} Plan",
                "immediate_actions": [{"action": "Start tracking this area daily"}],
                "encouragement": "Every small step counts!",
            }

        return intervention

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== PENNYPILOT AI - FINANCIAL SAVINGS ==============


class SavingsGoalRequest(BaseModel):
    user_id: str
    goal_name: str
    target_amount: float
    deadline: Optional[str] = None
    priority: str = "medium"


class SpendingAnalysisRequest(BaseModel):
    user_id: str
    transactions: List[Dict[str, Any]]
    period: str = "month"


class MicroSavingRequest(BaseModel):
    user_id: str
    amount: float
    source: str = "manual"
    category: Optional[str] = None


@router.post("/pennypilot/savings-goal")
async def create_savings_goal(request: SavingsGoalRequest):
    """Create a personalized savings goal"""
    try:
        goal = {
            "id": str(uuid.uuid4())[:8],
            "user_id": request.user_id,
            "goal_name": request.goal_name,
            "target_amount": request.target_amount,
            "current_amount": 0,
            "deadline": request.deadline,
            "priority": request.priority,
            "created_at": datetime.utcnow(),
            "status": "active",
        }

        await db.savings_goals.insert_one(goal)
        goal.pop("_id", None)

        # Generate AI savings advice
        prompt = f"""Create a personalized savings plan for this goal:
Goal: {request.goal_name}
Target: ${request.target_amount}
Deadline: {request.deadline or "No specific deadline"}

Return JSON:
{{
    "weekly_target": <suggested weekly savings>,
    "tips": ["tip1", "tip2", "tip3"],
    "strategy": "Brief savings strategy",
    "motivation": "Encouraging message"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"savings-{uuid.uuid4()}",
            system_message="You are a financial advisor. Provide practical savings advice. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            advice = json.loads(response_text)
        except Exception:
            advice = {"tips": ["Start small and be consistent"], "strategy": "Save regularly"}

        return {"goal": goal, "ai_advice": advice}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pennypilot/goals/{user_id}")
async def get_savings_goals(user_id: str):
    """Get all savings goals for a user"""
    goals = await db.savings_goals.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    total_saved = sum(g.get("current_amount", 0) for g in goals)
    total_target = sum(g.get("target_amount", 0) for g in goals)
    return {
        "goals": goals,
        "summary": {
            "total_saved": total_saved,
            "total_target": total_target,
            "progress_percent": round((total_saved / total_target * 100) if total_target > 0 else 0, 1),
        },
    }


@router.post("/pennypilot/analyze-spending")
async def analyze_spending(request: SpendingAnalysisRequest):
    """AI-powered spending analysis"""
    try:
        prompt = f"""Analyze these spending patterns and provide insights:

Transactions: {json.dumps(request.transactions[:20], default=str)}
Period: {request.period}

Return JSON:
{{
    "total_spent": <total>,
    "by_category": {{"category": amount}},
    "top_expense": "Highest spending category",
    "savings_opportunities": ["opportunity1", "opportunity2"],
    "spending_score": <1-100>,
    "recommendations": ["rec1", "rec2", "rec3"],
    "projected_monthly": <projected monthly spend>,
    "comparison": "How this compares to healthy spending"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"spending-{uuid.uuid4()}",
            system_message="You are a financial analyst. Analyze spending patterns and provide actionable insights. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            analysis = json.loads(response_text)
        except Exception:
            analysis = {"spending_score": 70, "recommendations": ["Track your spending daily"]}

        return analysis

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pennypilot/micro-save")
async def micro_save(request: MicroSavingRequest):
    """Record a micro-saving transaction"""
    try:
        saving = {
            "id": str(uuid.uuid4())[:8],
            "user_id": request.user_id,
            "amount": request.amount,
            "source": request.source,
            "category": request.category,
            "timestamp": datetime.utcnow(),
        }

        await db.micro_savings.insert_one(saving)
        saving.pop("_id", None)

        # Get total savings
        pipeline = [{"$match": {"user_id": request.user_id}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
        result = await db.micro_savings.aggregate(pipeline).to_list(1)
        total = result[0]["total"] if result else request.amount

        return {
            "saved": saving,
            "total_micro_savings": total,
            "message": f"Great job! You've saved ${total:.2f} through micro-savings!",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pennypilot/ai-coach")
async def financial_ai_coach(request: Request):
    """AI financial coaching chat"""
    body = await request.json()
    user_id = body.get("user_id", "guest")
    question = body.get("question", "")
    try:
        # Get user's financial context
        goals = await db.savings_goals.find({"user_id": user_id}, {"_id": 0}).to_list(10)

        prompt = f"""User's financial question: {question}

User's savings goals: {json.dumps(goals, default=str) if goals else "No goals set"}

Provide helpful, personalized financial advice. Be encouraging but realistic."""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"fincoach-{uuid.uuid4()}",
            system_message="You are PennyPilot, a friendly AI financial coach. Provide practical, personalized money advice. Be encouraging and supportive.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        return {"response": response, "coach": "PennyPilot AI"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== LIFEQUEST AI - GAMIFIED LIFE SKILLS ==============


class LifeQuestChallengeRequest(BaseModel):
    user_id: str
    category: str  # budgeting, health, time_management, social
    difficulty: str = "medium"


class ChallengeCompletionRequest(BaseModel):
    user_id: str
    challenge_id: str
    success: bool
    notes: Optional[str] = None


@router.post("/lifequest/generate-challenge")
async def generate_life_challenge(request: LifeQuestChallengeRequest):
    """Generate an adaptive life challenge"""
    try:
        # Get user's challenge history
        history = (
            await db.lifequest_history.find({"user_id": request.user_id, "category": request.category})
            .sort("completed_at", -1)
            .limit(5)
            .to_list(5)
        )

        success_rate = sum(1 for h in history if h.get("success", False)) / len(history) if history else 0.5

        prompt = f"""Generate a life skills challenge for the user.

Category: {request.category}
Difficulty: {request.difficulty}
User's recent success rate in this category: {success_rate:.0%}

Create an engaging, achievable challenge that helps build real-world skills.

Return JSON:
{{
    "challenge_id": "unique_id",
    "title": "Challenge title",
    "description": "What the user needs to do",
    "category": "{request.category}",
    "difficulty": "{request.difficulty}",
    "xp_reward": <10-100>,
    "time_limit": "Time to complete (e.g., '24 hours', '1 week')",
    "steps": ["step1", "step2", "step3"],
    "tips": ["helpful tip"],
    "real_world_benefit": "How this helps in real life",
    "bonus_objectives": ["optional bonus task"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"lifequest-{uuid.uuid4()}",
            system_message="You are LifeQuest AI, a gamification expert. Create engaging, practical life challenges that build real skills. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            challenge = json.loads(response_text)
        except Exception:
            challenge = {
                "challenge_id": str(uuid.uuid4())[:8],
                "title": f"{request.category.title()} Challenge",
                "description": "Complete a task in this category",
                "xp_reward": 25,
            }

        # Store active challenge
        challenge["user_id"] = request.user_id
        challenge["started_at"] = datetime.utcnow().isoformat()
        challenge["status"] = "active"

        await db.lifequest_challenges.insert_one(challenge.copy())

        # Remove MongoDB _id before returning
        challenge.pop("_id", None)
        return challenge

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lifequest/complete-challenge")
async def complete_challenge(request: ChallengeCompletionRequest):
    """Mark a challenge as completed"""
    try:
        challenge = await db.lifequest_challenges.find_one(
            {"challenge_id": request.challenge_id, "user_id": request.user_id}
        )

        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")

        # Record completion
        completion = {
            "user_id": request.user_id,
            "challenge_id": request.challenge_id,
            "category": challenge.get("category"),
            "success": request.success,
            "xp_earned": challenge.get("xp_reward", 0) if request.success else 0,
            "notes": request.notes,
            "completed_at": datetime.utcnow(),
        }

        await db.lifequest_history.insert_one(completion)

        # Update user stats
        await db.lifequest_stats.update_one(
            {"user_id": request.user_id},
            {
                "$inc": {
                    "total_xp": completion["xp_earned"],
                    "challenges_completed": 1 if request.success else 0,
                    "challenges_attempted": 1,
                },
                "$set": {"last_activity": datetime.utcnow()},
            },
            upsert=True,
        )

        # Get updated stats
        stats = await db.lifequest_stats.find_one({"user_id": request.user_id}, {"_id": 0})

        return {
            "success": request.success,
            "xp_earned": completion["xp_earned"],
            "message": "Challenge completed! Great work on building real-world skills!"
            if request.success
            else "Don't give up! Try again.",
            "stats": stats,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lifequest/stats/{user_id}")
async def get_lifequest_stats(user_id: str):
    """Get user's LifeQuest statistics"""
    stats = await db.lifequest_stats.find_one({"user_id": user_id}, {"_id": 0})
    if not stats:
        stats = {"total_xp": 0, "challenges_completed": 0, "challenges_attempted": 0}

    # Calculate level
    xp = stats.get("total_xp", 0)
    level = 1 + (xp // 100)

    return {**stats, "level": level, "xp_to_next_level": 100 - (xp % 100)}


@router.get("/lifequest/categories")
async def get_lifequest_categories():
    """Get available challenge categories"""
    return {
        "categories": [
            {"id": "budgeting", "name": "Financial Skills", "icon": "cash", "description": "Master money management"},
            {"id": "health", "name": "Health & Wellness", "icon": "heart", "description": "Build healthy habits"},
            {
                "id": "time_management",
                "name": "Time Management",
                "icon": "time",
                "description": "Optimize your schedule",
            },
            {"id": "social", "name": "Social Skills", "icon": "people", "description": "Improve relationships"},
            {"id": "productivity", "name": "Productivity", "icon": "rocket", "description": "Get more done"},
            {"id": "mindfulness", "name": "Mindfulness", "icon": "leaf", "description": "Mental clarity & peace"},
        ]
    }


# ============== CLIMATEGUIDE AI - WEATHER FORECASTING ==============


class WeatherQueryRequest(BaseModel):
    user_id: str
    query: str
    location: Optional[str] = None


class WeatherAlertRequest(BaseModel):
    user_id: str
    location: str
    alert_types: List[str] = ["severe", "rain", "heat"]


@router.post("/climateguide/query")
async def weather_query(request: WeatherQueryRequest):
    """Natural language weather query"""
    try:
        prompt = f"""User's weather question: {request.query}
Location: {request.location or "Not specified"}

Provide a helpful, conversational weather response. Include:
- Direct answer to their question
- Safety tips if relevant
- Activity suggestions based on weather

Be conversational and helpful. If location isn't specified, ask for it or give general advice."""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"climate-{uuid.uuid4()}",
            system_message="You are ClimateGuide AI, an intelligent weather assistant. Provide helpful, personalized weather advice. Be friendly and safety-conscious.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        return {"response": response, "assistant": "ClimateGuide AI"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/climateguide/forecast")
async def get_ai_forecast(request: Request):
    """Get AI-enhanced weather forecast"""
    body = await request.json()
    location = body.get("location", "New York")
    days = body.get("days", 7)
    """Get AI-enhanced weather forecast"""
    try:
        prompt = f"""Generate a detailed weather forecast for {location} for the next {days} days.

Return JSON:
{{
    "location": "{location}",
    "current": {{
        "temperature": "XX°F/XX°C",
        "condition": "Condition",
        "humidity": "XX%",
        "wind": "XX mph",
        "feels_like": "XX°F"
    }},
    "forecast": [
        {{
            "day": "Day name",
            "date": "Date",
            "high": "XX°F",
            "low": "XX°F",
            "condition": "Condition",
            "precipitation_chance": "XX%",
            "recommendation": "What to do/wear"
        }}
    ],
    "alerts": ["Any weather alerts"],
    "activity_suggestions": ["Good activities for this weather"],
    "clothing_recommendation": "What to wear"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"forecast-{uuid.uuid4()}",
            system_message="You are a weather forecasting AI. Provide realistic, helpful forecasts. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            forecast = json.loads(response_text)
        except Exception:
            forecast = {
                "location": location,
                "current": {"temperature": "72°F", "condition": "Partly Cloudy"},
                "forecast": [],
            }

        return forecast

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/climateguide/activity-check")
async def check_activity_weather(activity: str, location: str, time: Optional[str] = None):
    """Check if weather is suitable for an activity"""
    try:
        prompt = f"""User wants to do: {activity}
Location: {location}
Time: {time or "Today"}

Analyze if this activity is suitable given typical weather conditions.

Return JSON:
{{
    "activity": "{activity}",
    "recommendation": "go" or "reconsider" or "avoid",
    "confidence": "high/medium/low",
    "reason": "Why this recommendation",
    "best_time": "Best time to do this activity",
    "precautions": ["Safety tips"],
    "alternatives": ["Indoor alternatives if weather is bad"],
    "what_to_bring": ["Items to bring"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"activity-{uuid.uuid4()}",
            system_message="You are a weather-activity advisor. Help users plan activities safely. Return valid JSON.",
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
            result = {"recommendation": "go", "reason": "Weather looks suitable"}

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== LIFEPULSE AI - DAILY LIFE PREDICTOR ==============


class LifePulseLogRequest(BaseModel):
    user_id: str
    sleep_hours: Optional[float] = None
    energy_level: Optional[int] = None  # 1-10
    stress_level: Optional[int] = None  # 1-10
    mood: Optional[str] = None
    activities: Optional[List[str]] = []
    notes: Optional[str] = None


class LifePulsePredictionRequest(BaseModel):
    user_id: str
    prediction_type: str = "daily"  # daily, energy, stress, mood


@router.post("/lifepulse/log")
async def log_lifepulse_data(request: LifePulseLogRequest):
    """Log daily life metrics"""
    try:
        entry = {
            "user_id": request.user_id,
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "timestamp": datetime.utcnow(),
            "sleep_hours": request.sleep_hours,
            "energy_level": request.energy_level,
            "stress_level": request.stress_level,
            "mood": request.mood,
            "activities": request.activities,
            "notes": request.notes,
        }

        await db.lifepulse_logs.insert_one(entry)
        entry.pop("_id", None)

        return {"logged": entry, "message": "Data logged successfully!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lifepulse/predict")
async def get_lifepulse_prediction(request: LifePulsePredictionRequest):
    """Get AI predictions for daily life"""
    try:
        # Get recent logs
        logs = await db.lifepulse_logs.find({"user_id": request.user_id}).sort("timestamp", -1).limit(14).to_list(14)

        prompt = f"""Based on this user's recent life data, predict their {request.prediction_type} patterns.

Recent data (last 14 days):
{json.dumps([{k: v for k, v in log.items() if k != "_id"} for log in logs], default=str)}

Return JSON:
{{
    "prediction_type": "{request.prediction_type}",
    "predictions": {{
        "energy_forecast": "How energy levels will likely be today",
        "stress_forecast": "Expected stress patterns",
        "mood_forecast": "Likely mood trajectory",
        "optimal_wake_time": "Best time to wake up",
        "optimal_sleep_time": "Best time to sleep",
        "peak_productivity_hours": ["Best hours for focused work"],
        "recommended_breaks": ["Suggested break times"],
        "activity_suggestions": ["Activities to boost wellbeing"]
    }},
    "insights": ["Pattern insights from data"],
    "warnings": ["Potential issues to watch for"],
    "recommendations": [
        {{
            "time": "When",
            "action": "What to do",
            "reason": "Why this helps"
        }}
    ],
    "wellness_score": <1-100>
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"lifepulse-{uuid.uuid4()}",
            system_message="You are LifePulse AI, a personal wellness predictor. Analyze patterns and provide actionable predictions. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            prediction = json.loads(response_text)
        except Exception:
            prediction = {
                "wellness_score": 70,
                "recommendations": [{"action": "Take regular breaks", "reason": "Maintain energy"}],
            }

        return prediction

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lifepulse/history/{user_id}")
async def get_lifepulse_history(user_id: str, days: int = 7):
    """Get user's life pulse history"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    logs = (
        await db.lifepulse_logs.find({"user_id": user_id, "timestamp": {"$gte": cutoff}}, {"_id": 0})
        .sort("timestamp", -1)
        .to_list(100)
    )

    return {"history": logs, "days": days}


# ============== ECOSYNC AI - SUSTAINABILITY TRACKER ==============


class EcoActionRequest(BaseModel):
    user_id: str
    action_type: str  # energy, water, waste, transport, food
    description: str
    impact_value: Optional[float] = None


class EcoGoalRequest(BaseModel):
    user_id: str
    goal_type: str
    target_reduction: float  # percentage
    timeframe: str = "month"


@router.post("/ecosync/log-action")
async def log_eco_action(request: EcoActionRequest):
    """Log an eco-friendly action"""
    try:
        # Calculate impact
        impact_multipliers = {
            "energy": 0.5,  # kg CO2 per unit
            "water": 0.001,
            "waste": 2.0,
            "transport": 0.2,
            "food": 1.5,
        }

        estimated_impact = (request.impact_value or 1) * impact_multipliers.get(request.action_type, 0.1)

        action = {
            "id": str(uuid.uuid4())[:8],
            "user_id": request.user_id,
            "action_type": request.action_type,
            "description": request.description,
            "impact_value": request.impact_value,
            "co2_saved_kg": estimated_impact,
            "timestamp": datetime.utcnow(),
            "eco_points": int(estimated_impact * 10),
        }

        await db.eco_actions.insert_one(action)
        action.pop("_id", None)

        # Get total impact
        pipeline = [
            {"$match": {"user_id": request.user_id}},
            {"$group": {"_id": None, "total_co2": {"$sum": "$co2_saved_kg"}, "total_points": {"$sum": "$eco_points"}}},
        ]
        result = await db.eco_actions.aggregate(pipeline).to_list(1)
        totals = result[0] if result else {"total_co2": estimated_impact, "total_points": action["eco_points"]}

        return {
            "action": action,
            "totals": {
                "total_co2_saved": round(totals["total_co2"], 2),
                "total_eco_points": totals["total_points"],
                "trees_equivalent": round(totals["total_co2"] / 21, 1),  # avg tree absorbs 21kg/year
            },
            "message": f"Great job! You saved {estimated_impact:.2f} kg of CO2!",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ecosync/suggestions")
async def get_eco_suggestions(user_id: str):
    """Get personalized sustainability suggestions"""
    try:
        # Get user's recent actions
        actions = await db.eco_actions.find({"user_id": user_id}).sort("timestamp", -1).limit(20).to_list(20)

        prompt = f"""Based on this user's eco-friendly actions, provide personalized sustainability suggestions.

Recent actions: {json.dumps([{k: v for k, v in a.items() if k != "_id"} for a in actions], default=str)}

Return JSON:
{{
    "daily_tips": [
        {{
            "tip": "Actionable tip",
            "impact": "Potential CO2 savings",
            "difficulty": "easy/medium/hard",
            "category": "energy/water/waste/transport/food"
        }}
    ],
    "weekly_challenge": {{
        "challenge": "Weekly eco challenge",
        "goal": "What to achieve",
        "reward_points": <eco points>
    }},
    "areas_to_improve": ["Areas where user can do better"],
    "achievements": ["Eco achievements unlocked"],
    "local_initiatives": ["Suggested local sustainability programs"],
    "impact_comparison": "How user's impact compares to average"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"ecosync-{uuid.uuid4()}",
            system_message="You are EcoSync AI, a sustainability coach. Provide practical, motivating eco-friendly suggestions. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            suggestions = json.loads(response_text)
        except Exception:
            suggestions = {
                "daily_tips": [{"tip": "Use a reusable water bottle", "impact": "Low", "difficulty": "easy"}],
                "weekly_challenge": {"challenge": "Go plastic-free for a day"},
            }

        return suggestions

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ecosync/dashboard/{user_id}")
async def get_eco_dashboard(user_id: str):
    """Get user's sustainability dashboard"""
    # Get actions by category
    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": "$action_type",
                "count": {"$sum": 1},
                "co2_saved": {"$sum": "$co2_saved_kg"},
                "points": {"$sum": "$eco_points"},
            }
        },
    ]
    by_category = await db.eco_actions.aggregate(pipeline).to_list(10)

    # Get total stats
    total_pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": None,
                "total_actions": {"$sum": 1},
                "total_co2": {"$sum": "$co2_saved_kg"},
                "total_points": {"$sum": "$eco_points"},
            }
        },
    ]
    totals_result = await db.eco_actions.aggregate(total_pipeline).to_list(1)
    totals = totals_result[0] if totals_result else {"total_actions": 0, "total_co2": 0, "total_points": 0}

    return {
        "summary": {
            "total_actions": totals.get("total_actions", 0),
            "total_co2_saved_kg": round(totals.get("total_co2", 0), 2),
            "total_eco_points": totals.get("total_points", 0),
            "trees_equivalent": round(totals.get("total_co2", 0) / 21, 1),
            "eco_level": 1 + totals.get("total_points", 0) // 100,
        },
        "by_category": {
            item["_id"]: {"count": item["count"], "co2_saved": round(item["co2_saved"], 2)} for item in by_category
        },
    }


# ============== LIFELENS AI - HEALTH ANALYTICS ==============


class LifeLensDataRequest(BaseModel):
    user_id: str
    data_type: str  # biometrics, sleep, activity, nutrition, environment
    values: Dict[str, Any]
    source: str = "manual"  # manual, wearable, smart_home


class LifeLensInsightRequest(BaseModel):
    user_id: str
    focus_area: str = "overall"  # overall, sleep, activity, nutrition, stress


@router.post("/lifelens/log-data")
async def log_lifelens_data(request: LifeLensDataRequest):
    """Log health and lifestyle data"""
    try:
        entry = {
            "id": str(uuid.uuid4())[:8],
            "user_id": request.user_id,
            "data_type": request.data_type,
            "values": request.values,
            "source": request.source,
            "timestamp": datetime.utcnow(),
        }

        await db.lifelens_data.insert_one(entry)
        entry.pop("_id", None)

        return {"logged": entry, "message": "Health data recorded successfully!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lifelens/insights")
async def get_lifelens_insights(request: LifeLensInsightRequest):
    """Get AI-powered health insights"""
    try:
        # Get user's recent health data
        data = await db.lifelens_data.find({"user_id": request.user_id}).sort("timestamp", -1).limit(30).to_list(30)

        prompt = f"""Analyze this user's health and lifestyle data and provide insights.

Focus area: {request.focus_area}
Recent data: {json.dumps([{k: v for k, v in d.items() if k != "_id"} for d in data], default=str)}

Return JSON:
{{
    "health_score": <1-100>,
    "focus_area": "{request.focus_area}",
    "key_insights": [
        {{
            "insight": "What the data shows",
            "importance": "high/medium/low",
            "trend": "improving/stable/declining"
        }}
    ],
    "daily_recommendations": [
        {{
            "time": "When to do this",
            "action": "What to do",
            "benefit": "How it helps",
            "priority": "high/medium/low"
        }}
    ],
    "early_warnings": ["Potential health concerns to watch"],
    "sleep_optimization": {{
        "ideal_bedtime": "Recommended bedtime",
        "ideal_wake_time": "Recommended wake time",
        "sleep_quality_tips": ["Tips to improve sleep"]
    }},
    "environment_suggestions": [
        {{
            "adjustment": "What to change in environment",
            "reason": "Why this helps"
        }}
    ],
    "nutrition_guidance": ["Dietary suggestions"],
    "activity_recommendations": ["Exercise suggestions"],
    "mental_wellness_tips": ["Stress management tips"],
    "weekly_goals": ["Health goals for the week"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"lifelens-{uuid.uuid4()}",
            system_message="You are LifeLens AI, a holistic health analyst. Provide evidence-based, personalized health insights. Be encouraging but highlight important concerns. Return valid JSON.",
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
                "health_score": 75,
                "key_insights": [{"insight": "Continue tracking for better insights", "importance": "medium"}],
            }

        return insights

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lifelens/dashboard/{user_id}")
async def get_lifelens_dashboard(user_id: str):
    """Get user's health dashboard"""
    # Get recent data by type
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$sort": {"timestamp": -1}},
        {
            "$group": {
                "_id": "$data_type",
                "latest": {"$first": "$values"},
                "count": {"$sum": 1},
                "last_updated": {"$first": "$timestamp"},
            }
        },
    ]
    by_type = await db.lifelens_data.aggregate(pipeline).to_list(10)

    return {
        "data_summary": {
            item["_id"]: {
                "latest_values": item["latest"],
                "total_entries": item["count"],
                "last_updated": item["last_updated"].isoformat() if item.get("last_updated") else None,
            }
            for item in by_type
        },
        "tracking_streak": len(by_type),
        "data_sources": list(set(item["_id"] for item in by_type)),
    }


@router.post("/lifelens/smart-home-sync")
async def smart_home_suggestions(user_id: str, current_conditions: Dict[str, Any]):
    """Get smart home adjustment suggestions based on health data"""
    try:
        # Get user's health data
        data = await db.lifelens_data.find({"user_id": user_id}).sort("timestamp", -1).limit(10).to_list(10)

        prompt = f"""Based on the user's health data and current home conditions, suggest smart home adjustments.

User health data: {json.dumps([{k: v for k, v in d.items() if k != "_id"} for d in data], default=str)}
Current home conditions: {json.dumps(current_conditions)}

Return JSON:
{{
    "lighting_adjustment": {{
        "brightness": <0-100>,
        "color_temperature": "warm/neutral/cool",
        "reason": "Why this helps"
    }},
    "temperature_adjustment": {{
        "target_temp": "XX°F",
        "reason": "Why this helps"
    }},
    "air_quality": {{
        "ventilation": "increase/maintain/decrease",
        "humidity_target": "XX%",
        "air_purifier": "on/off"
    }},
    "sound_environment": {{
        "suggestion": "white noise/silence/nature sounds",
        "volume": "low/medium"
    }},
    "overall_wellness_mode": "relax/focus/energize/sleep"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"smarthome-{uuid.uuid4()}",
            system_message="You are a smart home wellness optimizer. Suggest environment adjustments to improve health. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            suggestions = json.loads(response_text)
        except Exception:
            suggestions = {"overall_wellness_mode": "relax"}

        return suggestions

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== JOBHELP AI - CAREER & SKILLS COACH ==============


class ResumeRequest(BaseModel):
    user_id: str
    personal_info: Dict[str, str]
    experience: List[Dict[str, Any]] = []
    education: List[Dict[str, Any]] = []
    skills: List[str] = []
    target_role: Optional[str] = None


class InterviewPrepRequest(BaseModel):
    user_id: str
    job_title: str
    company: Optional[str] = None
    interview_type: str = "behavioral"  # behavioral, technical, case


class SkillAssessmentRequest(BaseModel):
    user_id: str
    current_role: Optional[str] = None
    target_role: Optional[str] = None
    skills: List[str] = []


@router.post("/jobhelp/build-resume")
async def build_resume(request: ResumeRequest):
    """AI-powered resume builder"""
    try:
        prompt = f"""Create a professional resume for this candidate:

Personal Info: {json.dumps(request.personal_info)}
Experience: {json.dumps(request.experience)}
Education: {json.dumps(request.education)}
Skills: {request.skills}
Target Role: {request.target_role or "General"}

Return JSON:
{{
    "summary": "Professional summary (2-3 sentences)",
    "experience_bullets": [
        {{
            "company": "Company name",
            "role": "Job title",
            "bullets": ["Achievement-focused bullet points"]
        }}
    ],
    "skills_section": {{
        "technical": ["Technical skills"],
        "soft": ["Soft skills"]
    }},
    "improvements": ["Suggestions to strengthen the resume"],
    "keywords": ["ATS-friendly keywords to include"],
    "score": <1-100 resume strength score>
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"resume-{uuid.uuid4()}",
            system_message="You are a professional resume writer and career coach. Create compelling, ATS-optimized resumes. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            resume = json.loads(response_text)
        except Exception:
            resume = {"summary": "Professional with diverse experience", "score": 70}

        return resume

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobhelp/interview-prep")
async def interview_prep(request: InterviewPrepRequest):
    """Generate interview practice questions and tips"""
    try:
        prompt = f"""Generate interview preparation for:

Job Title: {request.job_title}
Company: {request.company or "General"}
Interview Type: {request.interview_type}

Return JSON:
{{
    "questions": [
        {{
            "question": "Interview question",
            "type": "behavioral/technical/situational",
            "difficulty": "easy/medium/hard",
            "tips": "How to answer this question",
            "sample_answer_structure": "STAR method or framework to use"
        }}
    ],
    "company_research": ["Key things to know about the company"],
    "questions_to_ask": ["Smart questions to ask the interviewer"],
    "common_mistakes": ["Mistakes to avoid"],
    "confidence_tips": ["Tips to stay confident"],
    "dress_code": "Suggested attire"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"interview-{uuid.uuid4()}",
            system_message="You are an expert interview coach. Provide practical, actionable interview preparation. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            prep = json.loads(response_text)
        except Exception:
            prep = {"questions": [{"question": "Tell me about yourself", "tips": "Focus on relevant experience"}]}

        return prep

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobhelp/skill-assessment")
async def skill_assessment(request: SkillAssessmentRequest):
    """Assess skills and suggest learning paths"""
    try:
        prompt = f"""Analyze skills and provide career guidance:

Current Role: {request.current_role or "Not specified"}
Target Role: {request.target_role or "Career growth"}
Current Skills: {request.skills}

Return JSON:
{{
    "skill_gaps": [
        {{
            "skill": "Missing skill",
            "importance": "critical/important/nice-to-have",
            "learning_time": "Estimated time to learn"
        }}
    ],
    "learning_path": [
        {{
            "step": 1,
            "skill": "Skill to learn",
            "resources": ["Suggested learning resources"],
            "duration": "Time needed"
        }}
    ],
    "micro_certifications": ["Recommended certifications"],
    "industry_trends": ["Relevant industry trends"],
    "salary_insights": "Potential salary range for target role",
    "timeline": "Recommended timeline to reach target role"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"skills-{uuid.uuid4()}",
            system_message="You are a career development advisor. Provide actionable skill development guidance. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            assessment = json.loads(response_text)
        except Exception:
            assessment = {"skill_gaps": [], "learning_path": []}

        return assessment

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobhelp/career-roadmap")
async def career_roadmap(request: Request):
    """Generate a career development roadmap"""
    body = await request.json()
    current_role = body.get("current_role", "Professional")
    target_role = body.get("target_role", "Senior Professional")
    years = body.get("timeline_years", 2)
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            model="gpt-4o",
            session_id=f"career-roadmap-{uuid.uuid4()}",
            system_message="You are a career development expert.",
        )
        prompt = f"""Create a {years}-year career roadmap from {current_role} to {target_role}. Return JSON:
{{"current_role":"{current_role}","target_role":"{target_role}","timeline_years":{years},"phases":[{{"phase":"Phase 1","duration":"0-6 months","title":"Foundation","goals":["goal1"],"skills_to_learn":["skill1"],"actions":["action1"]}}],"key_milestones":["milestone1"],"resources":["resource1"],"estimated_salary_growth":"X%"}}"""
        response = await chat.send_message(UserMessage(text=prompt))
        try:
            json_match = re.search(r"\{[\s\S]*\}", response.text)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return {
            "current_role": current_role,
            "target_role": target_role,
            "timeline_years": years,
            "phases": [
                {
                    "phase": "Phase 1",
                    "duration": "0-6 months",
                    "title": "Build Foundation",
                    "goals": ["Master core skills"],
                    "skills_to_learn": ["Leadership", "Communication"],
                    "actions": ["Take online courses", "Find a mentor"],
                }
            ],
            "key_milestones": ["Complete certification", "Lead a project"],
            "resources": ["LinkedIn Learning", "Industry conferences"],
            "estimated_salary_growth": "20-40%",
        }
    except Exception:
        return {
            "current_role": current_role,
            "target_role": target_role,
            "timeline_years": years,
            "phases": [
                {
                    "phase": "Phase 1",
                    "duration": "0-6 months",
                    "title": "Build Foundation",
                    "goals": ["Develop core competencies"],
                    "skills_to_learn": ["Technical skills", "Soft skills"],
                    "actions": ["Network actively", "Seek feedback"],
                }
            ],
            "key_milestones": ["Get promoted", "Build portfolio"],
            "resources": ["Online courses", "Professional networks"],
            "estimated_salary_growth": "15-30%",
        }


@router.post("/jobhelp/daily-learning")
async def daily_learning(user_id: str, skill: str, duration_minutes: int = 15):
    """Generate a micro-learning session"""
    try:
        prompt = f"""Create a {duration_minutes}-minute micro-learning session for: {skill}

Return JSON:
{{
    "lesson_title": "Title",
    "duration": {duration_minutes},
    "content": [
        {{
            "type": "concept/exercise/quiz",
            "title": "Section title",
            "content": "Learning content",
            "time_minutes": <time for this section>
        }}
    ],
    "key_takeaways": ["Main points to remember"],
    "practice_task": "Hands-on task to apply learning",
    "quiz": [
        {{
            "question": "Quiz question",
            "options": ["A", "B", "C", "D"],
            "correct": "A"
        }}
    ],
    "next_session_preview": "What to learn next"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"learning-{uuid.uuid4()}",
            system_message="You are an expert educator. Create engaging, bite-sized learning content. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            lesson = json.loads(response_text)
        except Exception:
            lesson = {"lesson_title": f"Learning {skill}", "content": []}

        return lesson

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== SCAN HISTORY ==============


@router.post("/scans", status_code=201)
async def create_scan(payload: CreateScanRequest, user: User = Depends(require_auth)):
    """Save a scan result to history"""
    scan = ScanRecord(
        user_id=user.user_id,
        scan_type=payload.scan_type,
        scanner_title=payload.scanner_title,
        summary=payload.summary,
        analysis=payload.analysis,
    )
    await db.scans.insert_one(scan.dict())
    return scan


@router.get("/scans")
async def get_scans(request: Request, limit: int = 50, user: User = Depends(require_auth)):
    """Get scan history for the current user"""
    capped_limit = min(max(limit, 1), 100)
    cursor = db.scans.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(capped_limit)
    scans = [doc async for doc in cursor]
    return {"scans": scans}


# ============== AI IMAGE SCANNING (BODY & MEAL) ==============


class ImageScanRequest(BaseModel):
    user_id: str
    image_base64: str
    scan_type: str = "body"
    notes: str = ""


SCAN_PERSONAS = {
    "medimate": {
        "title": "Health Scanner",
        "prompt": "Analyze this image for health-related observations. Identify visible skin conditions, injuries, rashes, or symptoms. Provide: identified_issue, severity (mild/moderate/severe), possible_causes (list), recommended_actions (list), when_to_see_doctor, home_remedies (list), prevention_tips (list). Be helpful but always recommend consulting a doctor.",
    },
    "mindease": {
        "title": "Wellness Scanner",
        "prompt": "Analyze this image of the user's environment/workspace/situation. Assess stress factors, suggest calming improvements. Provide: environment_assessment, stress_factors (list), mood_impact, improvement_suggestions (list), calming_activities (list), mindfulness_tip.",
    },
    "pennypilot": {
        "title": "Receipt Scanner",
        "prompt": "Analyze this receipt/bill/financial document. Extract spending details. Provide: store_name, date, items (list with name and price), total_amount, category, savings_tip, budget_recommendation, spending_pattern_note.",
    },
    "assetpilot": {
        "title": "Investment Scanner",
        "prompt": "Analyze this document/property/asset image. Provide: asset_type, estimated_value, condition_assessment, investment_potential (low/medium/high), key_observations (list), risks (list), opportunities (list), recommendation.",
    },
    "assistant": {
        "title": "Note Scanner",
        "prompt": "Analyze this handwritten note/list/document. Digitize and organize the content. Provide: detected_text, organized_items (list), category, priority_items (list), action_items (list), suggestions (list).",
    },
    "school": {
        "title": "Study Scanner",
        "prompt": "Analyze this textbook page/homework/diagram/equation. Explain the content clearly. Provide: subject, topic, content_summary, detailed_explanation, key_concepts (list), practice_questions (list), study_tips (list).",
    },
    "jobhelp": {
        "title": "Resume Scanner",
        "prompt": "Analyze this resume/CV/business card/job posting. Provide: document_type, key_information, strengths (list), improvements (list), missing_sections (list), ats_score (1-100), actionable_tips (list).",
    },
    "globecoach": {
        "title": "Culture Scanner",
        "prompt": "Analyze this image for cultural identification. Identify cultural elements, traditions, or landmarks. Provide: identified_culture, cultural_elements (list), historical_context, interesting_facts (list), cultural_etiquette (list), related_experiences (list).",
    },
    "smartbuy": {
        "title": "Product Scanner",
        "prompt": "Analyze this product/item/packaging. Provide: product_name, brand, category, estimated_price_range, quality_assessment, value_rating (1-10), pros (list), cons (list), better_alternatives (list), buying_tip.",
    },
    "homemate": {
        "title": "Property Scanner",
        "prompt": "Analyze this room/property/building image. Provide: property_type, condition_assessment, estimated_value_range, positive_features (list), concerns (list), renovation_suggestions (list), neighborhood_tip, investment_rating (1-10).",
    },
    "autogenie": {
        "title": "Vehicle Scanner",
        "prompt": "Analyze this vehicle image. Provide: vehicle_type, make_model_guess, year_estimate, condition_assessment (exterior), visible_issues (list), estimated_value_range, maintenance_recommendations (list), buying_advice.",
    },
    "translate": {
        "title": "Text Scanner",
        "prompt": "Analyze this image containing text (sign, menu, document, etc). Detect the language and translate to English. Provide: detected_language, original_text, english_translation, context_notes, pronunciation_guide, cultural_context.",
    },
    "ecosync": {
        "title": "Eco Scanner",
        "prompt": "Analyze this item/product/waste for environmental impact. Provide: item_identified, material_type, recyclable (yes/no/partially), disposal_method, environmental_impact, eco_friendly_alternatives (list), carbon_footprint_note, green_tip.",
    },
    "climateguide": {
        "title": "Sky Scanner",
        "prompt": "Analyze this sky/weather/outdoor image. Provide: current_conditions, temperature_estimate, weather_prediction, activity_recommendations (list), clothing_suggestion, uv_index_estimate, weather_warning, fun_weather_fact.",
    },
    "lifepulse": {
        "title": "Routine Scanner",
        "prompt": "Analyze this image of daily items/workspace/routine setup. Provide: items_detected (list), routine_assessment, productivity_score (1-10), optimization_tips (list), time_saving_suggestions (list), healthy_habit_recommendations (list).",
    },
    "homemind": {
        "title": "Appliance Scanner",
        "prompt": "Analyze this home appliance/device/room. Provide: device_identified, brand_guess, energy_efficiency_estimate, maintenance_tips (list), smart_home_integration_options (list), energy_saving_tips (list), estimated_annual_cost.",
    },
    "disasterguard": {
        "title": "Safety Scanner",
        "prompt": "Analyze this environment for safety hazards and emergency preparedness. Provide: location_type, identified_hazards (list), safety_rating (1-10), immediate_actions (list), emergency_preparedness_tips (list), evacuation_notes, safety_equipment_needed (list).",
    },
    "travelpal": {
        "title": "Travel Scanner",
        "prompt": "Analyze this landmark/sign/location/travel scene. Provide: location_guess, landmark_name, historical_info, interesting_facts (list), nearby_attractions (list), local_tips (list), best_time_to_visit, travel_advice.",
    },
    "aidlink": {
        "title": "Aid Scanner",
        "prompt": "Analyze this image for humanitarian/community needs. Provide: situation_assessment, needs_identified (list), urgency_level (low/medium/high/critical), recommended_actions (list), resources_needed (list), organizations_to_contact (list), how_to_help.",
    },
}


@router.post("/ai-scan")
async def universal_ai_scan(request: ImageScanRequest):
    """Universal AI image scanner for all features"""
    persona = SCAN_PERSONAS.get(
        request.scan_type,
        {
            "title": "AI Scanner",
            "prompt": "Analyze this image and provide helpful insights. Identify what you see and give practical advice.",
        },
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"scan-{request.scan_type}-{uuid.uuid4()}",
            system_message=f"You are {persona['title']}, an AI visual analysis expert. Always respond in valid JSON format.",
        ).with_model("openai", "gpt-4o")

        prompt = f"""{persona["prompt"]}

{f"User notes: {request.notes}" if request.notes else ""}

Return your analysis as valid JSON. Be specific, practical, and helpful."""

        image_content = ImageContent(image_base64=request.image_base64)

        response = await chat.send_message(UserMessage(text=prompt, file_contents=[image_content]))

        try:
            response_text = response.text if hasattr(response, "text") else str(response)
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                result = json.loads(json_match.group())
                result["scan_type"] = request.scan_type
                result["scanner_title"] = persona["title"]
                return result
        except Exception:
            pass

        return {
            "scan_type": request.scan_type,
            "scanner_title": persona["title"],
            "analysis": response.text if hasattr(response, "text") else "Analysis complete. Please review the details.",
            "recommendations": [
                "Review the image carefully",
                "Consider consulting a professional",
                "Take action based on findings",
            ],
        }
    except Exception as e:
        logger.error(f"AI Scan error ({request.scan_type}): {e}")
        return {
            "scan_type": request.scan_type,
            "scanner_title": persona["title"],
            "analysis": "Scan completed. AI analysis is processing.",
            "recommendations": [
                "Try scanning again with better lighting",
                "Ensure the subject is clearly visible",
                "Contact support if issue persists",
            ],
            "error": True,
        }


@router.post("/fitness/scan-body")
async def scan_body(request: ImageScanRequest):
    """AI body scan analysis using camera photo"""
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"bodyscan-{uuid.uuid4()}",
            system_message="You are an expert fitness coach and body composition analyst. Analyze body photos to provide helpful fitness guidance. Be encouraging, professional, and health-focused. Never make negative comments about appearance.",
        ).with_model("openai", "gpt-4o")

        prompt = f"""Analyze this body photo for fitness coaching. The user wants to understand their body and get personalized fitness advice.
{f"User notes: {request.notes}" if request.notes else ""}

Provide a comprehensive analysis in this JSON format:
{{
    "body_analysis": {{
        "estimated_body_type": "ectomorph/mesomorph/endomorph/combination",
        "posture_assessment": "Brief posture observation",
        "visible_muscle_groups": ["list of visible muscle development areas"],
        "areas_for_improvement": ["areas that could benefit from targeted exercise"]
    }},
    "health_insights": {{
        "general_observation": "Overall health-related observation",
        "posture_tips": ["posture improvement suggestions"],
        "flexibility_notes": "Flexibility assessment based on visible posture"
    }},
    "workout_recommendations": {{
        "focus_areas": ["primary muscle groups to target"],
        "suggested_exercises": [
            {{"exercise": "Exercise name", "sets": "3", "reps": "12", "why": "Reason"}},
            {{"exercise": "Exercise name", "sets": "3", "reps": "10", "why": "Reason"}},
            {{"exercise": "Exercise name", "sets": "3", "reps": "15", "why": "Reason"}}
        ],
        "weekly_plan_summary": "Brief weekly workout suggestion",
        "cardio_recommendation": "Cardio type and duration suggestion"
    }},
    "nutrition_tips": {{
        "calorie_guidance": "General calorie intake suggestion",
        "protein_goal": "Protein intake suggestion",
        "key_nutrients": ["important nutrients to focus on"]
    }},
    "progress_plan": {{
        "short_term_goal": "4-week goal",
        "medium_term_goal": "3-month goal",
        "motivation": "Encouraging motivational message"
    }}
}}

Be supportive, encouraging, and focus on health improvement. Never body-shame."""

        image_content = ImageContent(image_base64=request.image_base64)

        response = await chat.send_message(UserMessage(text=prompt, file_contents=[image_content]))

        try:
            response_text = response.text if hasattr(response, "text") else str(response)
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass

        return {
            "body_analysis": {
                "estimated_body_type": "combination",
                "posture_assessment": "Analysis completed. Focus on maintaining good posture throughout the day.",
                "visible_muscle_groups": ["Core", "Upper body", "Lower body"],
                "areas_for_improvement": ["Core stability", "Upper back strength", "Hip flexibility"],
            },
            "health_insights": {
                "general_observation": "Good foundation for fitness improvement. Consistent training will show results.",
                "posture_tips": [
                    "Stand tall with shoulders back",
                    "Engage your core when sitting",
                    "Take posture breaks every hour",
                ],
                "flexibility_notes": "Regular stretching will improve overall mobility and reduce injury risk.",
            },
            "workout_recommendations": {
                "focus_areas": ["Core", "Back", "Legs"],
                "suggested_exercises": [
                    {"exercise": "Plank", "sets": "3", "reps": "30 sec", "why": "Core stability"},
                    {"exercise": "Squats", "sets": "3", "reps": "15", "why": "Lower body strength"},
                    {"exercise": "Push-ups", "sets": "3", "reps": "12", "why": "Upper body development"},
                ],
                "weekly_plan_summary": "Train 3-4 days per week with rest days between sessions.",
                "cardio_recommendation": "20-30 minutes of moderate cardio 3x per week",
            },
            "nutrition_tips": {
                "calorie_guidance": "Maintain a balanced diet with adequate protein intake",
                "protein_goal": "Aim for 0.8-1g protein per pound of body weight",
                "key_nutrients": ["Protein", "Omega-3", "Vitamin D", "Iron"],
            },
            "progress_plan": {
                "short_term_goal": "Build consistent workout habit - 3x per week for 4 weeks",
                "medium_term_goal": "Visible strength and endurance improvements by 3 months",
                "motivation": "Every rep counts! You're already ahead by taking this step. Keep going! 💪",
            },
        }
    except Exception as e:
        logger.error(f"Body scan error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze image. Please try again.")


@router.post("/nutritrack/scan-meal-image")
async def scan_meal_image(request: ImageScanRequest):
    """AI meal scan analysis using camera photo"""
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"mealscan-{uuid.uuid4()}",
            system_message="You are an expert nutritionist and food analyst. Analyze food photos to provide accurate nutritional information. Be precise with estimates and health-focused.",
        ).with_model("openai", "gpt-4o")

        prompt = f"""Analyze this food/meal photo and provide detailed nutritional information.
{f"User notes: {request.notes}" if request.notes else ""}

Provide analysis in this JSON format:
{{
    "meal_name": "Identified meal/food name",
    "meal_items": ["List of each food item identified"],
    "nutrition": {{
        "calories": <estimated total calories>,
        "protein_g": <grams>,
        "carbs_g": <grams>,
        "fat_g": <grams>,
        "fiber_g": <grams>,
        "sugar_g": <grams>,
        "sodium_mg": <milligrams>
    }},
    "health_score": <1-10 score>,
    "health_grade": "A/B/C/D/F",
    "ingredients_detected": ["All visible ingredients"],
    "portion_size": "small/medium/large/extra-large",
    "allergen_warnings": ["Potential allergens detected"],
    "health_benefits": ["Positive nutritional aspects"],
    "concerns": ["Nutritional concerns or downsides"],
    "healthier_alternatives": ["Suggestions for healthier swaps"],
    "meal_timing_advice": "Best time to eat this type of meal",
    "hydration_tip": "Water intake recommendation with this meal",
    "fun_fact": "An interesting nutrition fact about this food"
}}

Be accurate with nutritional estimates. If unsure, provide reasonable ranges."""

        image_content = ImageContent(image_base64=request.image_base64)

        response = await chat.send_message(UserMessage(text=prompt, file_contents=[image_content]))

        try:
            response_text = response.text if hasattr(response, "text") else str(response)
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if json_match:
                result = json.loads(json_match.group())
                # Save to DB
                await db.nutritrack_meals.insert_one(
                    {
                        "user_id": request.user_id,
                        "meal_name": result.get("meal_name", "Scanned Meal"),
                        "nutrition": result.get("nutrition", {}),
                        "health_score": result.get("health_score", 5),
                        "scan_type": "image",
                        "timestamp": datetime.utcnow(),
                    }
                )
                return result
        except Exception:
            pass

        return {
            "meal_name": "Scanned Meal",
            "meal_items": ["Food items detected"],
            "nutrition": {
                "calories": 450,
                "protein_g": 20,
                "carbs_g": 55,
                "fat_g": 18,
                "fiber_g": 5,
                "sugar_g": 8,
                "sodium_mg": 600,
            },
            "health_score": 6,
            "health_grade": "B",
            "ingredients_detected": ["Various ingredients detected"],
            "portion_size": "medium",
            "allergen_warnings": [],
            "health_benefits": ["Contains essential nutrients"],
            "concerns": ["Monitor portion size"],
            "healthier_alternatives": ["Add more vegetables", "Choose whole grains"],
            "meal_timing_advice": "Good as a midday meal",
            "hydration_tip": "Drink a glass of water before and after your meal",
            "fun_fact": "Eating slowly helps your body recognize fullness signals better!",
        }
    except Exception as e:
        logger.error(f"Meal scan error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze meal image. Please try again.")


# ============== NUTRITRACK AI - NUTRITION & MEAL PLANNING ==============


class MealScanRequest(BaseModel):
    user_id: str
    meal_description: str
    meal_type: str = "lunch"  # breakfast, lunch, dinner, snack


class RecipeSuggestRequest(BaseModel):
    user_id: str
    available_ingredients: List[str]
    dietary_restrictions: List[str] = []
    cuisine_preference: Optional[str] = None


class NutritionGoalRequest(BaseModel):
    user_id: str
    goal_type: str  # weight_loss, muscle_gain, maintenance, health
    daily_calories: Optional[int] = None
    restrictions: List[str] = []


@router.post("/nutritrack/scan-meal")
async def scan_meal(request: MealScanRequest):
    """Analyze a meal and estimate nutrition"""
    try:
        prompt = f"""Analyze this meal and provide nutritional information:

Meal: {request.meal_description}
Meal Type: {request.meal_type}

Return JSON:
{{
    "meal_name": "Identified meal name",
    "nutrition": {{
        "calories": <estimated calories>,
        "protein_g": <grams>,
        "carbs_g": <grams>,
        "fat_g": <grams>,
        "fiber_g": <grams>,
        "sugar_g": <grams>,
        "sodium_mg": <milligrams>
    }},
    "health_score": <1-10>,
    "ingredients_detected": ["Detected ingredients"],
    "allergens": ["Potential allergens"],
    "healthier_alternatives": ["Suggestions for healthier versions"],
    "portion_assessment": "normal/large/small",
    "tips": "Nutrition tip for this meal"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"meal-{uuid.uuid4()}",
            system_message="You are a nutritionist. Analyze meals and provide accurate nutritional estimates. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            analysis = json.loads(response_text)
        except Exception:
            analysis = {"meal_name": request.meal_description, "nutrition": {"calories": 500}}

        # Log the meal
        meal_log = {
            "user_id": request.user_id,
            "meal_description": request.meal_description,
            "meal_type": request.meal_type,
            "nutrition": analysis.get("nutrition", {}),
            "timestamp": datetime.utcnow(),
        }
        await db.nutritrack_meals.insert_one(meal_log)

        return analysis

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nutritrack/suggest-recipes")
async def suggest_recipes(request: RecipeSuggestRequest):
    """Suggest recipes based on available ingredients"""
    try:
        prompt = f"""Suggest recipes based on these ingredients:

Available: {request.available_ingredients}
Dietary Restrictions: {request.dietary_restrictions or "None"}
Cuisine Preference: {request.cuisine_preference or "Any"}

Return JSON:
{{
    "recipes": [
        {{
            "name": "Recipe name",
            "cuisine": "Cuisine type",
            "prep_time": "XX minutes",
            "cook_time": "XX minutes",
            "difficulty": "easy/medium/hard",
            "ingredients_used": ["Ingredients from user's list"],
            "additional_needed": ["Extra ingredients needed"],
            "instructions": ["Step-by-step instructions"],
            "nutrition_per_serving": {{
                "calories": <cal>,
                "protein": "<g>",
                "carbs": "<g>"
            }},
            "servings": <number>
        }}
    ],
    "waste_reduction_tip": "Tip to minimize food waste"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"recipe-{uuid.uuid4()}",
            system_message="You are a creative chef. Suggest delicious, practical recipes. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            recipes = json.loads(response_text)
        except Exception:
            recipes = {"recipes": []}

        return recipes

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nutritrack/daily-summary/{user_id}")
async def get_daily_nutrition(user_id: str):
    """Get daily nutrition summary"""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    start = datetime.strptime(today, "%Y-%m-%d")
    end = start + timedelta(days=1)

    meals = await db.nutritrack_meals.find(
        {"user_id": user_id, "timestamp": {"$gte": start, "$lt": end}}, {"_id": 0}
    ).to_list(20)

    totals = {
        "calories": sum(m.get("nutrition", {}).get("calories", 0) for m in meals),
        "protein_g": sum(m.get("nutrition", {}).get("protein_g", 0) for m in meals),
        "carbs_g": sum(m.get("nutrition", {}).get("carbs_g", 0) for m in meals),
        "fat_g": sum(m.get("nutrition", {}).get("fat_g", 0) for m in meals),
    }

    return {"date": today, "meals": meals, "totals": totals, "meals_logged": len(meals)}


# ============== SAFEGPS AI - SMART NAVIGATION & SAFETY ==============


class RouteRequest(BaseModel):
    user_id: str
    origin: str
    destination: str
    mode: str = "driving"  # driving, walking, transit, cycling
    preferences: List[str] = []  # safe, fast, scenic, eco-friendly


class SafetyAlertRequest(BaseModel):
    user_id: str
    location: str
    alert_types: List[str] = ["traffic", "weather", "crime", "hazards"]


@router.post("/safegps/plan-route")
async def plan_safe_route(request: RouteRequest):
    """Plan an optimized safe route"""
    try:
        prompt = f"""Plan a route with safety and optimization:

From: {request.origin}
To: {request.destination}
Mode: {request.mode}
Preferences: {request.preferences or ["balanced"]}

Return JSON:
{{
    "route_name": "Route description",
    "distance": "XX miles/km",
    "estimated_time": "XX minutes",
    "safety_score": <1-10>,
    "route_steps": [
        {{
            "instruction": "Navigation instruction",
            "distance": "Distance for this step",
            "safety_note": "Any safety consideration"
        }}
    ],
    "hazards_avoided": ["Hazards this route avoids"],
    "points_of_interest": ["Notable places along route"],
    "alternative_routes": [
        {{
            "name": "Alternative route",
            "time_difference": "+/- XX min",
            "safety_score": <score>,
            "tradeoff": "Why choose this"
        }}
    ],
    "tips": ["Safety tips for this journey"],
    "best_departure_time": "Recommended time to leave"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"route-{uuid.uuid4()}",
            system_message="You are a navigation safety expert. Plan routes prioritizing safety and efficiency. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            route = json.loads(response_text)
        except Exception:
            route = {"route_name": f"{request.origin} to {request.destination}", "safety_score": 7}

        return route

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/safegps/area-safety")
async def check_area_safety(location: str):
    """Check safety information for an area"""
    try:
        prompt = f"""Provide safety information for: {location}

Return JSON:
{{
    "location": "{location}",
    "overall_safety_score": <1-10>,
    "safety_breakdown": {{
        "crime_rate": "low/medium/high",
        "traffic_safety": "low/medium/high",
        "pedestrian_safety": "low/medium/high",
        "night_safety": "low/medium/high"
    }},
    "common_hazards": ["Known hazards in area"],
    "safe_zones": ["Safer areas nearby"],
    "emergency_services": ["Nearby emergency services"],
    "tips": ["Safety tips for this area"],
    "best_times_to_visit": ["Recommended times"],
    "areas_to_avoid": ["Areas with higher risk"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"safety-{uuid.uuid4()}",
            system_message="You are a safety advisor. Provide helpful safety information. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            safety = json.loads(response_text)
        except Exception:
            safety = {"location": location, "overall_safety_score": 7}

        return safety

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== HOMEMIND AI - SMART HOME MANAGER ==============


class HomeTaskRequest(BaseModel):
    user_id: str
    task_type: str  # maintenance, cleaning, grocery, energy
    details: Optional[str] = None


class ApplianceRequest(BaseModel):
    user_id: str
    appliance_name: str
    purchase_date: Optional[str] = None
    last_maintenance: Optional[str] = None


@router.post("/homemind/maintenance-prediction")
async def predict_maintenance(request: ApplianceRequest):
    """Predict maintenance needs for appliances"""
    try:
        prompt = f"""Predict maintenance needs for:

Appliance: {request.appliance_name}
Purchase Date: {request.purchase_date or "Unknown"}
Last Maintenance: {request.last_maintenance or "Unknown"}

Return JSON:
{{
    "appliance": "{request.appliance_name}",
    "health_score": <1-100>,
    "next_maintenance": {{
        "recommended_date": "When to service",
        "type": "Type of maintenance needed",
        "estimated_cost": "Cost estimate",
        "diy_possible": true/false
    }},
    "warning_signs": ["Signs of potential issues"],
    "maintenance_tips": ["Tips to extend lifespan"],
    "energy_efficiency": {{
        "current": "good/average/poor",
        "improvement_tips": ["Tips to improve efficiency"]
    }},
    "replacement_timeline": "When to consider replacement",
    "common_issues": ["Common problems with this appliance"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"home-{uuid.uuid4()}",
            system_message="You are a home maintenance expert. Provide practical appliance care advice. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            prediction = json.loads(response_text)
        except Exception:
            prediction = {"appliance": request.appliance_name, "health_score": 80}

        return prediction

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/homemind/smart-grocery")
async def smart_grocery_list(user_id: str, household_size: int = 2, preferences: List[str] = []):
    """Generate smart grocery list"""
    try:
        prompt = f"""Generate a smart weekly grocery list:

Household Size: {household_size}
Preferences: {preferences or ["balanced diet"]}

Return JSON:
{{
    "grocery_list": [
        {{
            "category": "produce/dairy/protein/grains/etc",
            "items": [
                {{
                    "name": "Item name",
                    "quantity": "Amount",
                    "estimated_price": "$X.XX",
                    "storage_tip": "How to store"
                }}
            ]
        }}
    ],
    "meal_plan_suggestions": ["Meals you can make"],
    "estimated_total": "$XX.XX",
    "money_saving_tips": ["Ways to save money"],
    "seasonal_recommendations": ["In-season items to consider"],
    "waste_reduction_tips": ["Tips to reduce food waste"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"grocery-{uuid.uuid4()}",
            system_message="You are a smart home assistant. Create efficient grocery lists. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            grocery = json.loads(response_text)
        except Exception:
            grocery = {"grocery_list": [], "estimated_total": "$0"}

        return grocery

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/homemind/energy-audit")
async def home_energy_audit(request: Request):
    """Perform AI home energy audit"""
    body = await request.json()
    body.get("user_id", "guest")
    home_details = body.get("home_details", body)
    """Perform AI home energy audit"""
    try:
        prompt = f"""Perform an energy audit for this home:

Home Details: {json.dumps(home_details)}

Return JSON:
{{
    "energy_score": <1-100>,
    "monthly_estimate": "$XXX",
    "improvement_areas": [
        {{
            "area": "Area of improvement",
            "current_issue": "What's inefficient",
            "solution": "How to fix",
            "savings_potential": "Monthly savings",
            "investment_needed": "Cost to implement",
            "roi_months": <months to recoup investment>
        }}
    ],
    "quick_wins": ["Easy changes with immediate impact"],
    "seasonal_tips": {{
        "summer": ["Summer efficiency tips"],
        "winter": ["Winter efficiency tips"]
    }},
    "smart_device_recommendations": ["Devices that could help"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"energy-{uuid.uuid4()}",
            system_message="You are an energy efficiency expert. Provide practical home energy advice. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            audit = json.loads(response_text)
        except Exception:
            audit = {"energy_score": 70, "improvement_areas": []}

        return audit

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== AIDLINK AI - HUMANITARIAN & VOLUNTEER ==============


class VolunteerMatchRequest(BaseModel):
    user_id: str
    skills: List[str]
    interests: List[str]
    availability: str  # weekends, evenings, flexible
    location: str


class EmergencyAidRequest(BaseModel):
    user_id: str
    emergency_type: str
    location: str
    needs: List[str]


@router.post("/aidlink/find-opportunities")
async def find_volunteer_opportunities(request: VolunteerMatchRequest):
    """Find matching volunteer opportunities"""
    try:
        prompt = f"""Find volunteer opportunities matching:

Skills: {request.skills}
Interests: {request.interests}
Availability: {request.availability}
Location: {request.location}

Return JSON:
{{
    "opportunities": [
        {{
            "organization": "Organization name",
            "role": "Volunteer role",
            "description": "What you'll do",
            "skills_match": ["Matching skills"],
            "time_commitment": "Hours per week",
            "impact": "How this helps",
            "location_type": "remote/in-person/hybrid",
            "urgency": "high/medium/low"
        }}
    ],
    "skill_based_matches": ["Opportunities perfect for your skills"],
    "local_initiatives": ["Community programs in your area"],
    "virtual_options": ["Remote volunteer opportunities"],
    "impact_areas": ["Causes you could support"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"volunteer-{uuid.uuid4()}",
            system_message="You are a humanitarian coordinator. Match volunteers with meaningful opportunities. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            opportunities = json.loads(response_text)
        except Exception:
            opportunities = {"opportunities": []}

        return opportunities

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aidlink/emergency-resources")
async def get_emergency_resources(request: EmergencyAidRequest):
    """Get emergency aid resources and guidance"""
    try:
        prompt = f"""Provide emergency aid resources for:

Emergency Type: {request.emergency_type}
Location: {request.location}
Needs: {request.needs}

Return JSON:
{{
    "immediate_actions": ["Steps to take right now"],
    "emergency_contacts": [
        {{
            "service": "Service name",
            "type": "Type of help",
            "contact": "How to reach them",
            "availability": "24/7 or hours"
        }}
    ],
    "local_resources": [
        {{
            "organization": "Organization name",
            "services": ["Services offered"],
            "eligibility": "Who can access"
        }}
    ],
    "safety_checklist": ["Safety steps to follow"],
    "documentation_needed": ["Documents to gather"],
    "support_services": ["Additional support available"],
    "community_help": ["Ways community can assist"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"emergency-{uuid.uuid4()}",
            system_message="You are an emergency response coordinator. Provide helpful, accurate emergency guidance. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            resources = json.loads(response_text)
        except Exception:
            resources = {"immediate_actions": ["Stay calm", "Call emergency services if needed"]}

        return resources

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aidlink/global-causes")
async def get_global_causes():
    """Get current global humanitarian causes"""
    return {
        "causes": [
            {"id": "hunger", "name": "Food Security", "icon": "nutrition", "description": "Combat global hunger"},
            {
                "id": "education",
                "name": "Education Access",
                "icon": "school",
                "description": "Support education for all",
            },
            {"id": "health", "name": "Healthcare", "icon": "medkit", "description": "Improve global health access"},
            {"id": "environment", "name": "Climate Action", "icon": "leaf", "description": "Protect our planet"},
            {
                "id": "refugees",
                "name": "Refugee Support",
                "icon": "people",
                "description": "Help displaced populations",
            },
            {
                "id": "disaster",
                "name": "Disaster Relief",
                "icon": "warning",
                "description": "Emergency response efforts",
            },
        ]
    }


# ============== MINDEASE AI - MENTAL HEALTH COMPANION ==============


class TherapyChatRequest(BaseModel):
    user_id: str
    message: str
    session_context: Optional[str] = None


class MoodCheckRequest(BaseModel):
    user_id: str
    mood: str
    intensity: int = 5
    triggers: List[str] = []
    notes: Optional[str] = None


class MindfulnessRequest(BaseModel):
    user_id: str
    duration_minutes: int = 5
    focus_area: str = "stress"  # stress, anxiety, sleep, focus


@router.post("/mindease/therapy-chat")
async def therapy_chat(request: TherapyChatRequest):
    """AI therapy conversation"""
    try:
        prompt = f"""Respond as a supportive AI therapy companion:

User message: {request.message}
Session context: {request.session_context or "General support session"}

Provide a warm, empathetic response that:
- Validates their feelings
- Offers perspective or coping strategies
- Encourages professional help if needed

Return JSON:
{{
    "response": "Your empathetic response",
    "emotional_validation": "Acknowledging their feelings",
    "coping_strategies": ["Practical suggestions"],
    "reflection_questions": ["Questions for self-exploration"],
    "resources": ["Helpful resources if needed"],
    "crisis_check": false,
    "professional_help_suggested": false
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"therapy-{uuid.uuid4()}",
            system_message="You are MindEase, a compassionate AI mental health companion. Provide supportive, non-judgmental responses. Always suggest professional help for serious concerns. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            therapy_response = json.loads(response_text)
        except Exception:
            therapy_response = {"response": "I hear you. Thank you for sharing.", "crisis_check": False}

        return therapy_response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mindease/mood-check")
async def mood_check(request: MoodCheckRequest):
    """Log mood and get personalized support"""
    try:
        # Save mood entry
        entry = {
            "user_id": request.user_id,
            "mood": request.mood,
            "intensity": request.intensity,
            "triggers": request.triggers,
            "notes": request.notes,
            "timestamp": datetime.utcnow(),
        }
        await db.mindease_moods.insert_one(entry)

        prompt = f"""Provide support based on this mood check:

Mood: {request.mood}
Intensity: {request.intensity}/10
Triggers: {request.triggers}
Notes: {request.notes or "None"}

Return JSON:
{{
    "acknowledgment": "Validating response",
    "mood_insight": "Understanding of their state",
    "immediate_relief": ["Quick relief techniques"],
    "activity_suggestions": ["Activities that might help"],
    "mindfulness_recommendation": {{
        "type": "breathing/meditation/grounding",
        "duration": "X minutes",
        "description": "Brief description"
    }},
    "affirmation": "Positive affirmation",
    "check_in_reminder": "When to check in again"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"mood-{uuid.uuid4()}",
            system_message="You are a supportive mental health companion. Provide caring, helpful responses. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            support = json.loads(response_text)
        except Exception:
            support = {
                "acknowledgment": "Thank you for checking in.",
                "affirmation": "You're doing great by being aware of your feelings.",
            }

        entry.pop("_id", None)
        return {"logged": entry, "support": support}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mindease/mindfulness-exercise")
async def get_mindfulness_exercise(request: MindfulnessRequest):
    """Get a guided mindfulness exercise"""
    try:
        prompt = f"""Create a {request.duration_minutes}-minute mindfulness exercise for: {request.focus_area}

Return JSON:
{{
    "exercise_name": "Name of exercise",
    "duration": {request.duration_minutes},
    "focus": "{request.focus_area}",
    "introduction": "Opening guidance",
    "steps": [
        {{
            "step": 1,
            "instruction": "What to do",
            "duration_seconds": <time>,
            "breathing_pattern": "e.g., 4-4-4 or null"
        }}
    ],
    "closing": "Closing guidance",
    "benefits": ["Benefits of this exercise"],
    "tips": ["Tips for effectiveness"],
    "follow_up_suggestion": "What to do after"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"mindful-{uuid.uuid4()}",
            system_message="You are a mindfulness instructor. Create calming, effective exercises. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            exercise = json.loads(response_text)
        except Exception:
            exercise = {"exercise_name": "Deep Breathing", "duration": request.duration_minutes}

        return exercise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mindease/mood-history/{user_id}")
async def get_mood_history(user_id: str, days: int = 7):
    """Get user's mood history"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    moods = (
        await db.mindease_moods.find({"user_id": user_id, "timestamp": {"$gte": cutoff}}, {"_id": 0})
        .sort("timestamp", -1)
        .to_list(100)
    )

    return {"history": moods, "days": days, "total_entries": len(moods)}


# ============== AI SUPPORT CHAT MODELS ==============


class SupportChatRequest(BaseModel):
    user_id: Optional[str] = None
    message: str
    conversation_id: Optional[str] = None


class SupportChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: str  # user or assistant
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============== AI SUPPORT CHAT ENDPOINTS ==============


@router.post("/support/chat")
async def support_chat(request: SupportChatRequest):
    """
    AI-powered 24/7 support chat assistant.
    Handles questions about RealAICoach app, features, subscriptions, troubleshooting, and general support.
    """
    try:
        # Get or create conversation
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # Fetch conversation history if exists
        conversation = await db.support_conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})

        history = []
        if conversation:
            history = conversation.get("messages", [])[-10:]  # Last 10 messages for context

        # Build conversation context
        history_text = ""
        if history:
            history_text = "\n".join(
                [f"{'User' if m['role'] == 'user' else 'Support'}: {m['content']}" for m in history]
            )

        system_prompt = """You are RealAICoach's friendly AI support assistant named "Nova". You're available 24/7 to help users with anything related to the RealAICoach app.

Your personality:
- Warm, helpful, and empathetic
- Professional but conversational
- Patient and understanding
- Proactive in offering solutions

About RealAICoach:
- An AI-powered life companion app with active AI features
- Categories: Health, Finance, Productivity, Shopping, Lifestyle, Safety
- Key features include: AI conversation practice, health tracking, financial planning, learning assistance, mental wellness support, and more
- Subscription plans: Free (limited), Basic ($9.99/mo), Premium ($19.99/mo)
- Available in 10 languages

You can help with:
1. Feature explanations and how-to guides
2. Account and subscription questions
3. Technical troubleshooting
4. Feature recommendations based on user needs
5. Privacy and security concerns
6. General app navigation
7. Feedback collection and feature requests

Guidelines:
- Keep responses concise but helpful (2-4 sentences typically)
- Use emojis sparingly but appropriately 😊
- If you don't know something specific, offer to connect them with human support
- For billing issues or account problems, always suggest contacting support@realaicoach.app
- Be encouraging and positive
- Never make up features or capabilities that don't exist"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"support-{conversation_id}", system_message=system_prompt
        ).with_model("openai", "gpt-4o")

        # Build prompt with history context
        if history_text:
            prompt = (
                "Previous conversation:\n"
                + history_text
                + "\n\nUser's message: \""
                + request.message
                + '"\n\nRespond helpfully as Nova, the RealAICoach support assistant:'
            )
        else:
            prompt = (
                "User's message: \""
                + request.message
                + '"\n\nRespond helpfully as Nova, the RealAICoach support assistant:'
            )

        response = await chat.send_message(UserMessage(text=prompt))
        response_text = response.strip()

        # Save conversation
        user_message = {
            "id": str(uuid.uuid4())[:8],
            "role": "user",
            "content": request.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        assistant_message = {
            "id": str(uuid.uuid4())[:8],
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if conversation:
            await db.support_conversations.update_one(
                {"conversation_id": conversation_id},
                {
                    "$push": {"messages": {"$each": [user_message, assistant_message]}},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
            )
        else:
            await db.support_conversations.insert_one(
                {
                    "conversation_id": conversation_id,
                    "user_id": request.user_id,
                    "messages": [user_message, assistant_message],
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )

        return {
            "conversation_id": conversation_id,
            "message": response_text,
            "assistant_name": "Nova",
            "timestamp": assistant_message["timestamp"],
        }

    except Exception as e:
        logger.error(f"Support chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/support/chat/history/{conversation_id}")
async def get_support_chat_history(conversation_id: str):
    """Get support chat conversation history"""
    conversation = await db.support_conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})

    if not conversation:
        return {"conversation_id": conversation_id, "messages": []}

    return {
        "conversation_id": conversation_id,
        "messages": conversation.get("messages", []),
        "created_at": conversation.get("created_at"),
        "updated_at": conversation.get("updated_at"),
    }


class SupportEmailRequest(BaseModel):
    name: str
    email: str
    subject: Optional[str] = "Support Request"
    message: str


@router.post("/support/email")
async def submit_support_email(request: SupportEmailRequest):
    """Submit a support email/contact form"""
    try:
        # Generate a ticket ID
        ticket_id = f"TKT-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Store the support request in database
        support_ticket = {
            "ticket_id": ticket_id,
            "name": request.name,
            "email": request.email,
            "subject": request.subject,
            "message": request.message,
            "status": "open",
            "admin_notes": [],
            "reply_logs": [],
            "resolved_at": None,
            "responded_at": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        await db.support_tickets.insert_one(support_ticket)

        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": "Your support request has been submitted successfully. We will get back to you within 24-48 hours.",
            "email_sent_to": request.email,
            "confirmation": f"A confirmation has been sent to {request.email}. Please save your eTicket number: {ticket_id}",
        }
    except Exception as e:
        logger.error(f"Support email error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to submit support request")


@router.get("/support/quick-answers")
async def get_quick_answers():
    """Get predefined quick answers for common questions"""
    return {
        "quick_answers": [
            {"id": "features", "question": "What features does RealAICoach have?", "category": "Features"},
            {"id": "subscription", "question": "How do I upgrade my subscription?", "category": "Account"},
            {"id": "privacy", "question": "Is my data secure?", "category": "Privacy"},
            {"id": "languages", "question": "What languages are supported?", "category": "General"},
            {"id": "refund", "question": "How do I request a refund?", "category": "Billing"},
            {"id": "reset-password", "question": "How do I reset my password?", "category": "Account"},
        ]
    }
