"""Lifestyle services: Ecosystem, Health Assistant, Sustainability, Automation."""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from emergentintegrations.llm.chat import LlmChat, UserMessage
from routes.db import db, EMERGENT_LLM_KEY

logger = logging.getLogger(__name__)
router = APIRouter()

# ══════════ MODELS ══════════

# ============== AI PERSONAL ECOSYSTEM MANAGER MODELS ==============


class EcosystemProfileRequest(BaseModel):
    user_id: str
    timezone: str = "UTC"
    work_hours: Dict[str, str] = {"start": "09:00", "end": "17:00"}
    commute_time_minutes: int = 30
    priorities: List[str] = ["health", "work", "family"]
    connected_services: List[str] = []  # calendar, fitness, finance


class DailyBriefingRequest(BaseModel):
    user_id: str
    date: Optional[str] = None
    include_weather: bool = True
    include_finances: bool = True
    include_health: bool = True


class SmartScheduleRequest(BaseModel):
    user_id: str
    date: str
    optimization_focus: str = "balance"  # productivity, balance, health, social


class TravelPlanRequest(BaseModel):
    user_id: str
    destination: str
    departure_date: str
    return_date: Optional[str] = None
    purpose: str = "leisure"  # business, leisure, family


class FinancialOverviewRequest(BaseModel):
    user_id: str
    period: str = "month"
    categories: List[str] = []


# ============== AI HEALTH ASSISTANT (MEDICATION) MODELS ==============


class MedicationRequest(BaseModel):
    user_id: str
    medication_name: str
    dosage: str
    frequency: str  # daily, twice_daily, weekly, as_needed
    times: List[str] = []  # ["08:00", "20:00"]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class MedicationReminderRequest(BaseModel):
    user_id: str
    medication_id: Optional[str] = None  # specific or all


class AppointmentRequest(BaseModel):
    user_id: str
    appointment_type: str  # doctor, dentist, therapy, checkup
    provider_name: Optional[str] = None
    date: str
    time: str
    notes: Optional[str] = None


class HealthRecordRequest(BaseModel):
    user_id: str
    record_type: str  # lab_result, prescription, visit_summary
    date: str
    data: Dict[str, Any]
    source: Optional[str] = None  # clinic name, wearable


# ============== AI SUSTAINABILITY TRACKER MODELS ==============


class CarbonActivityRequest(BaseModel):
    user_id: str
    activity_type: str  # transport, energy, food, purchase, waste
    details: Dict[str, Any]  # e.g., {"distance_km": 50, "vehicle": "car"}
    date: Optional[str] = None


class SustainabilityGoalRequest(BaseModel):
    user_id: str
    goal_type: str  # reduce_driving, eat_less_meat, reduce_energy
    target_reduction_percent: int = 20
    timeframe_days: int = 30


class EcoChallenge(BaseModel):
    user_id: str
    challenge_type: str  # meatless_week, public_transport, zero_waste_day
    participants: List[str] = []  # user IDs of friends


# ============== AI SMART AUTOMATION MODELS ==============


class AutomationRuleRequest(BaseModel):
    user_id: str
    trigger: str  # time, location, event, behavior
    trigger_details: Dict[str, Any]
    action: str  # reminder, suggestion, automation
    action_details: Dict[str, Any]
    enabled: bool = True


class BehaviorAnalysisRequest(BaseModel):
    user_id: str
    analysis_type: str = "patterns"  # patterns, predictions, optimizations


class VoiceCommandRequest(BaseModel):
    user_id: str
    audio_base64: Optional[str] = None
    text_command: Optional[str] = None


# ══════════ ROUTES ══════════


@router.post("/ecosystem/profile")
async def create_ecosystem_profile(request: EcosystemProfileRequest):
    """Create ecosystem management profile"""
    try:
        profile = {
            "user_id": request.user_id,
            "timezone": request.timezone,
            "work_hours": request.work_hours,
            "commute_time_minutes": request.commute_time_minutes,
            "priorities": request.priorities,
            "connected_services": request.connected_services,
            "updated_at": datetime.utcnow(),
        }
        await db.ecosystem_profiles.update_one({"user_id": request.user_id}, {"$set": profile}, upsert=True)
        return {"message": "Ecosystem profile saved", "profile": profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ecosystem/daily-briefing")
async def get_daily_briefing(request: DailyBriefingRequest):
    """Get comprehensive AI-powered daily briefing"""
    try:
        date = request.date or datetime.utcnow().strftime("%Y-%m-%d")

        # Gather all user data
        tasks = await db.tasks.find({"user_id": request.user_id, "completed": False}).to_list(20)
        events = await db.schedule_events.find({"user_id": request.user_id, "date": date}).to_list(20)
        health_data = (
            await db.wearable_data.find({"user_id": request.user_id}).sort("logged_at", -1).limit(10).to_list(10)
        )
        moods = await db.mood_logs.find({"user_id": request.user_id}).sort("timestamp", -1).limit(5).to_list(5)
        ecosystem = await db.ecosystem_profiles.find_one({"user_id": request.user_id})

        prompt = f"""Create a comprehensive, personalized daily briefing.

Date: {date}
User Priorities: {ecosystem.get("priorities", ["health", "work"]) if ecosystem else ["health", "work"]}

Today's Schedule:
{json.dumps([{"title": e.get("title"), "time": e.get("start_time")} for e in events], indent=2)}

Pending Tasks ({len(tasks)}):
{json.dumps([{"title": t.get("title"), "priority": t.get("priority"), "due": t.get("due_date")} for t in tasks[:10]], indent=2)}

Recent Health Data:
{json.dumps([{"type": h.get("data_type"), "latest": h.get("readings", [{}])[-1] if h.get("readings") else {}} for h in health_data[:5]], indent=2)}

Recent Mood Trend: {[m.get("mood") for m in moods]}

Create a warm, helpful daily briefing.

Return JSON:
{{
    "greeting": "Personalized morning greeting",
    "date_info": "{date}",
    "day_overview": "Brief summary of what's ahead",
    "schedule_highlights": [
        {{"time": "09:00", "event": "Event name", "preparation_tip": "How to prepare"}}
    ],
    "priority_tasks": [
        {{"task": "Task name", "why_important": "Why to prioritize", "suggested_time": "Best time to do it"}}
    ],
    "health_insights": {{
        "status": "How they're doing health-wise",
        "recommendation": "Health suggestion for today"
    }},
    "smart_suggestions": [
        {{"suggestion": "AI prediction or suggestion", "reason": "Why this matters"}}
    ],
    "weather_advisory": "Weather-related advice",
    "optimal_schedule": [
        {{"time_block": "09:00-10:00", "activity": "Suggested activity", "reason": "Why this timing"}}
    ],
    "evening_preview": "What to wind down with",
    "motivational_note": "Encouraging message for the day"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"briefing-{uuid.uuid4()}",
            system_message="You are a personal AI ecosystem manager creating comprehensive daily briefings. Be warm, helpful, and predictive. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            briefing = json.loads(response_text)
        except Exception:
            briefing = {
                "greeting": f"Good morning! Here's your briefing for {date}",
                "day_overview": "You have a productive day ahead",
                "smart_suggestions": [],
            }

        return briefing

    except Exception as e:
        logger.error(f"Daily briefing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ecosystem/smart-schedule")
async def generate_smart_schedule(request: SmartScheduleRequest):
    """Generate AI-optimized schedule considering all life factors"""
    try:
        # Get all relevant data
        tasks = await db.tasks.find({"user_id": request.user_id, "completed": False}).to_list(30)
        events = await db.schedule_events.find({"user_id": request.user_id, "date": request.date}).to_list(20)
        health = await db.health_profiles.find_one({"user_id": request.user_id})
        wearable = await db.wearable_data.find({"user_id": request.user_id}).sort("logged_at", -1).limit(5).to_list(5)
        ecosystem = await db.ecosystem_profiles.find_one({"user_id": request.user_id})

        prompt = f"""Create an optimally balanced schedule for {request.date}.

Optimization Focus: {request.optimization_focus}
Work Hours: {ecosystem.get("work_hours", {"start": "09:00", "end": "17:00"}) if ecosystem else {"start": "09:00", "end": "17:00"}}

Fixed Events:
{json.dumps([{"title": e.get("title"), "start": e.get("start_time"), "end": e.get("end_time")} for e in events], indent=2)}

Tasks to Schedule:
{json.dumps([{"title": t.get("title"), "priority": t.get("priority"), "category": t.get("category")} for t in tasks[:15]], indent=2)}

Health Context:
- Recent sleep/energy data: {wearable[:2] if wearable else "No data"}
- Health profile: {health if health else "Not set"}

Create an intelligent, balanced schedule.

Return JSON:
{{
    "date": "{request.date}",
    "optimization_applied": "{request.optimization_focus}",
    "schedule": [
        {{
            "time_slot": "07:00-07:30",
            "activity": "Activity name",
            "type": "fixed/task/health/buffer",
            "energy_requirement": "low/medium/high",
            "notes": "Tips for this block"
        }}
    ],
    "energy_management": {{
        "peak_hours": ["10:00-12:00"],
        "low_energy_periods": ["14:00-15:00"],
        "strategy": "How schedule accounts for energy"
    }},
    "balance_score": 85,
    "balance_breakdown": {{
        "work": 40,
        "health": 20,
        "personal": 25,
        "rest": 15
    }},
    "smart_insights": ["AI insight about the schedule"],
    "flexibility_zones": ["Times that can be adjusted if needed"]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"smart-schedule-{uuid.uuid4()}",
            system_message="You are an AI schedule optimizer. Create balanced, realistic schedules that account for human energy and needs. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            schedule = json.loads(response_text)
        except Exception:
            schedule = {"date": request.date, "schedule": [], "error": "Could not generate schedule"}

        return schedule

    except Exception as e:
        logger.error(f"Smart schedule failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ecosystem/travel-plan")
async def create_travel_plan(request: TravelPlanRequest):
    """Create comprehensive AI travel plan"""
    try:
        prompt = f"""Create a comprehensive travel plan.

Destination: {request.destination}
Departure: {request.departure_date}
Return: {request.return_date or "One-way"}
Purpose: {request.purpose}

Create a detailed travel plan with smart predictions.

Return JSON:
{{
    "destination": "{request.destination}",
    "trip_summary": "Brief trip overview",
    "pre_departure": {{
        "days_before": [
            {{"days": 7, "tasks": ["Task 1", "Task 2"]}},
            {{"days": 1, "tasks": ["Final preparations"]}}
        ],
        "packing_checklist": ["Essential items"],
        "documents_needed": ["Required documents"]
    }},
    "travel_day": {{
        "suggested_departure_time": "Account for delays",
        "buffer_recommendations": "How much buffer to add",
        "weather_considerations": "Weather-related advice"
    }},
    "itinerary_suggestions": [
        {{"day": 1, "activities": ["Activity 1"], "tips": "Local tips"}}
    ],
    "smart_alerts": [
        {{"alert": "Weather or travel advisory", "action": "What to do"}}
    ],
    "health_travel_tips": ["Health advice for the destination"],
    "budget_estimate": {{
        "accommodation": "Estimate",
        "food": "Estimate",
        "activities": "Estimate",
        "transport": "Estimate"
    }},
    "emergency_info": {{
        "embassy": "Embassy contact",
        "emergency_numbers": "Local emergency numbers"
    }}
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"travel-{uuid.uuid4()}",
            system_message="You are an AI travel planner. Create comprehensive, practical travel plans. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            plan = json.loads(response_text)
        except Exception:
            plan = {"destination": request.destination, "error": "Could not generate plan"}

        return plan

    except Exception as e:
        logger.error(f"Travel plan failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== AI HEALTH ASSISTANT (MEDICATION MANAGEMENT) ==============


@router.post("/health-assistant/medication/add")
async def add_medication(request: MedicationRequest):
    """Add a medication to track"""
    try:
        med_id = f"med_{str(uuid.uuid4())[:8]}"
        medication = {
            "id": med_id,
            "user_id": request.user_id,
            "medication_name": request.medication_name,
            "dosage": request.dosage,
            "frequency": request.frequency,
            "times": request.times,
            "start_date": request.start_date or datetime.utcnow().strftime("%Y-%m-%d"),
            "end_date": request.end_date,
            "notes": request.notes,
            "active": True,
            "created_at": datetime.utcnow(),
        }
        await db.medications.insert_one(medication)
        return {"message": "Medication added", "medication": medication}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health-assistant/medications/{user_id}")
async def get_medications(user_id: str, active_only: bool = True):
    """Get all medications for a user"""
    query = {"user_id": user_id}
    if active_only:
        query["active"] = True
    meds = await db.medications.find(query, {"_id": 0}).to_list(50)
    return {"medications": meds}


@router.post("/health-assistant/medication/log")
async def log_medication_taken(user_id: str, medication_id: str, taken: bool = True, notes: Optional[str] = None):
    """Log that a medication was taken"""
    try:
        log_entry = {
            "user_id": user_id,
            "medication_id": medication_id,
            "taken": taken,
            "notes": notes,
            "timestamp": datetime.utcnow(),
        }
        await db.medication_logs.insert_one(log_entry)

        # Calculate adherence
        week_ago = datetime.utcnow() - timedelta(days=7)
        logs = await db.medication_logs.find(
            {"user_id": user_id, "medication_id": medication_id, "timestamp": {"$gte": week_ago}}
        ).to_list(100)

        taken_count = sum(1 for log_entry in logs if log_entry.get("taken"))
        adherence = (taken_count / len(logs) * 100) if logs else 100

        return {"message": "Medication logged", "weekly_adherence": round(adherence, 1), "streak": taken_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/health-assistant/reminders")
async def get_medication_reminders(request: MedicationReminderRequest):
    """Get smart medication reminders clustered by urgency"""
    try:
        # Get medications
        query = {"user_id": request.user_id, "active": True}
        if request.medication_id:
            query["id"] = request.medication_id

        meds = await db.medications.find(query, {"_id": 0}).to_list(50)

        # Get appointments
        today = datetime.utcnow().strftime("%Y-%m-%d")
        appointments = (
            await db.appointments.find({"user_id": request.user_id, "date": {"$gte": today}}, {"_id": 0})
            .sort("date", 1)
            .to_list(10)
        )

        current_hour = datetime.utcnow().hour

        reminders = {"urgent": [], "upcoming": [], "later_today": [], "future": []}

        for med in meds:
            for time in med.get("times", []):
                hour = int(time.split(":")[0])
                reminder = {"type": "medication", "name": med["medication_name"], "dosage": med["dosage"], "time": time}
                if hour <= current_hour and hour >= current_hour - 1:
                    reminders["urgent"].append(reminder)
                elif hour > current_hour and hour <= current_hour + 2:
                    reminders["upcoming"].append(reminder)
                elif hour > current_hour:
                    reminders["later_today"].append(reminder)

        for apt in appointments:
            reminder = {
                "type": "appointment",
                "name": apt.get("appointment_type"),
                "provider": apt.get("provider_name"),
                "date": apt.get("date"),
                "time": apt.get("time"),
            }
            if apt.get("date") == today:
                reminders["upcoming"].append(reminder)
            else:
                reminders["future"].append(reminder)

        return {"reminders": reminders, "total_medications": len(meds), "upcoming_appointments": len(appointments)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/health-assistant/appointment/add")
async def add_appointment(request: AppointmentRequest):
    """Add a medical appointment"""
    try:
        apt_id = f"apt_{str(uuid.uuid4())[:8]}"
        appointment = {
            "id": apt_id,
            "user_id": request.user_id,
            "appointment_type": request.appointment_type,
            "provider_name": request.provider_name,
            "date": request.date,
            "time": request.time,
            "notes": request.notes,
            "created_at": datetime.utcnow(),
        }
        await db.appointments.insert_one(appointment)
        return {"message": "Appointment added", "appointment": appointment}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/health-assistant/symptom-triage")
async def symptom_triage(user_id: str, symptoms: List[str], severity: str = "moderate"):
    """AI-assisted symptom triage with escalation recommendations"""
    try:
        # Get health context
        health_profile = await db.health_profiles.find_one({"user_id": user_id}, {"_id": 0})
        medications = await db.medications.find({"user_id": user_id, "active": True}, {"_id": 0}).to_list(20)

        prompt = f"""Perform a symptom triage assessment. NOT A DIAGNOSIS.

Symptoms: {", ".join(symptoms)}
Severity Reported: {severity}
Health Profile: {json.dumps(health_profile, default=str) if health_profile else "Not available"}
Current Medications: {[m.get("medication_name") for m in medications]}

Provide triage guidance (NOT diagnosis).

Return JSON:
{{
    "triage_level": "self_care/schedule_appointment/urgent_care/emergency",
    "triage_explanation": "Why this level",
    "immediate_actions": ["What to do right now"],
    "symptom_assessment": [
        {{"symptom": "Symptom", "concern_level": "low/medium/high", "notes": "Information"}}
    ],
    "medication_considerations": ["Any medication interactions to be aware of"],
    "when_to_escalate": ["Signs that require immediate care"],
    "self_care_options": ["Safe self-care measures"],
    "questions_for_provider": ["Questions to ask if seeing a doctor"],
    "telehealth_appropriate": true,
    "disclaimer": "This is not medical advice. Seek professional care for proper evaluation."
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"triage-{uuid.uuid4()}",
            system_message="You are a symptom triage assistant. Provide guidance on care level needed. NEVER diagnose. Always recommend professional care for serious concerns. Return valid JSON.",
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=prompt))

        try:
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            triage = json.loads(response_text)
        except Exception:
            triage = {
                "triage_level": "schedule_appointment",
                "disclaimer": "Please consult a healthcare professional for proper evaluation.",
            }

        return triage

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== AI SUSTAINABILITY TRACKER ==============

# Carbon emission factors (kg CO2 per unit)
CARBON_FACTORS = {
    "car_km": 0.21,
    "bus_km": 0.089,
    "train_km": 0.041,
    "plane_km": 0.255,
    "electricity_kwh": 0.5,
    "natural_gas_kwh": 0.185,
    "beef_kg": 27.0,
    "chicken_kg": 6.9,
    "vegetables_kg": 2.0,
    "dairy_kg": 3.2,
}


@router.post("/sustainability/log-activity")
async def log_carbon_activity(request: CarbonActivityRequest):
    """Log an activity and calculate carbon footprint"""
    try:
        date = request.date or datetime.utcnow().strftime("%Y-%m-%d")

        # Calculate carbon
        carbon_kg = 0
        details = request.details

        if request.activity_type == "transport":
            distance = details.get("distance_km", 0)
            mode = details.get("mode", "car")
            factor_key = f"{mode}_km"
            carbon_kg = distance * CARBON_FACTORS.get(factor_key, 0.21)
        elif request.activity_type == "energy":
            kwh = details.get("kwh", 0)
            energy_type = details.get("type", "electricity")
            factor_key = f"{energy_type}_kwh"
            carbon_kg = kwh * CARBON_FACTORS.get(factor_key, 0.5)
        elif request.activity_type == "food":
            food_type = details.get("food_type", "vegetables")
            weight = details.get("weight_kg", 1)
            factor_key = f"{food_type}_kg"
            carbon_kg = weight * CARBON_FACTORS.get(factor_key, 2.0)

        activity_log = {
            "user_id": request.user_id,
            "activity_type": request.activity_type,
            "details": details,
            "carbon_kg": round(carbon_kg, 2),
            "date": date,
            "created_at": datetime.utcnow(),
        }

        await db.carbon_logs.insert_one(activity_log)

        # Get daily total
        day_logs = await db.carbon_logs.find({"user_id": request.user_id, "date": date}).to_list(100)

        daily_total = sum(day_log.get("carbon_kg", 0) for day_log in day_logs)

        return {
            "activity_logged": activity_log,
            "carbon_kg": round(carbon_kg, 2),
            "daily_total_kg": round(daily_total, 2),
            "daily_target_kg": 10.0,  # Average sustainable daily target
            "status": "on_track" if daily_total < 10 else "over_target",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sustainability/footprint/{user_id}")
async def get_carbon_footprint(user_id: str, period: str = "week"):
    """Get carbon footprint summary"""
    try:
        days = {"day": 1, "week": 7, "month": 30}.get(period, 7)
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        logs = await db.carbon_logs.find({"user_id": user_id, "date": {"$gte": cutoff_str}}, {"_id": 0}).to_list(500)

        total_carbon = sum(log_entry.get("carbon_kg", 0) for log_entry in logs)

        # Group by type
        by_type = {}
        for log in logs:
            atype = log.get("activity_type", "other")
            by_type[atype] = by_type.get(atype, 0) + log.get("carbon_kg", 0)

        # Daily breakdown
        by_day = {}
        for log in logs:
            day = log.get("date", "unknown")
            by_day[day] = by_day.get(day, 0) + log.get("carbon_kg", 0)

        return {
            "period": period,
            "total_carbon_kg": round(total_carbon, 2),
            "daily_average_kg": round(total_carbon / days, 2) if days > 0 else 0,
            "by_category": {k: round(v, 2) for k, v in by_type.items()},
            "daily_breakdown": {k: round(v, 2) for k, v in sorted(by_day.items())},
            "comparison": {
                "average_person_daily": 16.0,
                "sustainable_target_daily": 10.0,
                "your_daily_average": round(total_carbon / days, 2) if days > 0 else 0,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sustainability/suggestions")
async def get_sustainability_suggestions(user_id: str):
    """Get AI-powered sustainability suggestions"""
    try:
        # Get recent carbon data
        week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        logs = await db.carbon_logs.find({"user_id": user_id, "date": {"$gte": week_ago}}, {"_id": 0}).to_list(100)

        by_type = {}
        for log in logs:
            atype = log.get("activity_type", "other")
            by_type[atype] = by_type.get(atype, 0) + log.get("carbon_kg", 0)

        prompt = f"""Analyze this user's carbon footprint and provide personalized sustainability suggestions.

Weekly Carbon Footprint by Category:
{json.dumps(by_type, indent=2)}

Total Weekly: {sum(by_type.values()):.2f} kg CO2

Provide practical, personalized suggestions.

Return JSON:
{{
    "footprint_assessment": "How they're doing compared to averages",
    "biggest_impact_area": "Category with most emissions",
    "personalized_tips": [
        {{
            "category": "transport/energy/food",
            "tip": "Specific actionable tip",
            "potential_savings_kg": 5.0,
            "difficulty": "easy/medium/hard",
            "implementation": "How to implement"
        }}
    ],
    "quick_wins": ["Easy changes they can make today"],
    "long_term_goals": ["Bigger changes to work toward"],
    "eco_challenge_suggestions": [
        {{"challenge": "Challenge name", "duration_days": 7, "impact": "Expected impact"}}
    ],
    "resources": ["Helpful resources or apps"],
    "encouragement": "Positive message about their efforts"
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"eco-{uuid.uuid4()}",
            system_message="You are an environmental sustainability coach. Provide practical, encouraging advice. Return valid JSON.",
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
                "personalized_tips": [{"tip": "Track your activities to get personalized suggestions"}],
                "encouragement": "Every small action counts!",
            }

        return suggestions

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sustainability/challenge/create")
async def create_eco_challenge(request: EcoChallenge):
    """Create a sustainability challenge"""
    try:
        challenge_id = f"eco_{str(uuid.uuid4())[:8]}"
        challenge = {
            "id": challenge_id,
            "user_id": request.user_id,
            "challenge_type": request.challenge_type,
            "participants": [request.user_id] + request.participants,
            "start_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "status": "active",
            "leaderboard": {},
            "created_at": datetime.utcnow(),
        }
        await db.eco_challenges.insert_one(challenge)
        return {"message": "Challenge created!", "challenge": challenge}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== AI SMART AUTOMATION ==============


@router.post("/automation/rules/create")
async def create_automation_rule(request: AutomationRuleRequest):
    """Create a smart automation rule"""
    try:
        rule_id = f"rule_{str(uuid.uuid4())[:8]}"
        rule = {
            "id": rule_id,
            "user_id": request.user_id,
            "trigger": request.trigger,
            "trigger_details": request.trigger_details,
            "action": request.action,
            "action_details": request.action_details,
            "enabled": request.enabled,
            "times_triggered": 0,
            "created_at": datetime.utcnow(),
        }
        await db.automation_rules.insert_one(rule)
        return {"message": "Automation rule created", "rule": rule}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/automation/rules/{user_id}")
async def get_automation_rules(user_id: str):
    """Get all automation rules"""
    rules = await db.automation_rules.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    return {"rules": rules}


@router.post("/automation/behavior-analysis")
async def analyze_behavior(request: BehaviorAnalysisRequest):
    """Analyze user behavior patterns and suggest automations"""
    try:
        # Get user activity data
        tasks = await db.tasks.find({"user_id": request.user_id}).sort("created_at", -1).limit(50).to_list(50)
        events = await db.schedule_events.find({"user_id": request.user_id}).sort("date", -1).limit(30).to_list(30)
        habits = await db.habits.find({"user_id": request.user_id}).sort("date", -1).limit(50).to_list(50)

        prompt = f"""Analyze this user's behavior patterns and suggest smart automations.

Task Patterns: {len(tasks)} tasks, categories: {list(set(t.get("category", "general") for t in tasks))}
Event Patterns: {len(events)} events
Habit Tracking: {list(set(h.get("habit_name") for h in habits))}

Identify patterns and suggest automations.

Return JSON:
{{
    "patterns_identified": [
        {{
            "pattern": "Pattern description",
            "confidence": 85,
            "data_points": 10
        }}
    ],
    "predictions": [
        {{
            "prediction": "What the user likely needs/wants",
            "timing": "When this typically happens",
            "confidence": 80
        }}
    ],
    "suggested_automations": [
        {{
            "name": "Automation name",
            "trigger": "What triggers it",
            "action": "What it does",
            "benefit": "How it helps",
            "implementation": "How to set it up"
        }}
    ],
    "time_saving_opportunities": [
        {{"opportunity": "Description", "estimated_time_saved_weekly": "X minutes"}}
    ],
    "routine_optimizations": [
        {{"current": "Current behavior", "suggested": "Optimized version", "benefit": "Why it's better"}}
    ]
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"behavior-{uuid.uuid4()}",
            system_message="You are an AI behavior analyst identifying patterns and suggesting automations. Be insightful and practical. Return valid JSON.",
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
            analysis = {"patterns_identified": [], "suggested_automations": []}

        return analysis

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/automation/voice-command")
async def process_voice_command(request: VoiceCommandRequest):
    """Process voice commands for hands-free automation"""
    try:
        command_text = request.text_command

        # If audio provided, transcribe
        if request.audio_base64 and not command_text:
            import base64
            import tempfile

            audio_data = base64.b64decode(request.audio_base64)
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(audio_data)
                temp_path = f.name

            import litellm

            with open(temp_path, "rb") as audio_file:
                transcript = await litellm.atranscription(
                    model="whisper-1", file=audio_file, api_key=EMERGENT_LLM_KEY, api_base="https://llm.emergentagi.com"
                )
            os.unlink(temp_path)
            command_text = transcript.text

        if not command_text:
            raise HTTPException(status_code=400, detail="No command provided")

        prompt = f"""Parse this voice command and determine the intended action.

Command: "{command_text}"

Determine what the user wants to do.

Return JSON:
{{
    "understood_intent": "What user wants",
    "action_type": "task/reminder/event/query/automation",
    "parsed_details": {{
        "title": "If creating something",
        "time": "If time mentioned",
        "date": "If date mentioned",
        "priority": "If priority mentioned"
    }},
    "confidence": 90,
    "confirmation_message": "What to say back to user",
    "follow_up_questions": ["Any clarifying questions needed"],
    "ready_to_execute": true
}}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"voice-{uuid.uuid4()}",
            system_message="You are a voice command processor. Parse natural language commands accurately. Return valid JSON.",
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
            result = {"understood_intent": command_text, "action_type": "query"}

        result["original_command"] = command_text
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
