"""AI Service tool routes: HealthHalo, CareConnect, FinWise, SmartBuy, HomeMate, AutoGenie,
DisasterGuard, AssetPilot, TimeSaver, TravelPal, GlobeCoach, AI Chat."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import List, Optional, Any
import uuid
from emergentintegrations.llm.chat import LlmChat, UserMessage
from openai import AsyncOpenAI
from .db import db, EMERGENT_LLM_KEY, logger, get_current_user
from routes.payments_catalog import get_subscription_plan_from_gps, get_subscription_plans_from_gps
from utils.access_control_engine import build_session_entitlements, compute_effective_plan
from utils.llm_helper import generate_verified_text

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
            "error_code": "ai_services_auth_required",
            "message": "Login required or provide fallback_user_id for guest access",
        },
    )


async def _get_user_plan_and_limits(owner_id: str) -> dict:
    """Get user's subscription plan and entitlements."""
    if owner_id.startswith("guest:"):
        return {
            "plan": "free",
            "is_admin": False,
            "daily_limit": 3,
            "user_id": owner_id.replace("guest:", "")
        }
    
    user_id = owner_id.replace("auth:", "")
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
            "roles": 1,
        }
    )
    
    if not user_doc:
        return {"plan": "free", "is_admin": False, "daily_limit": 3, "user_id": user_id}
    
    plan = compute_effective_plan(user_doc or {})
    
    # Get plan limits
    plan_doc = await get_subscription_plan_from_gps(plan, default_plan_id="free") or {}
    entitlement_ctx = build_session_entitlements(user_doc)
    entitlement_daily_limit = (entitlement_ctx.get("feature_entitlements") or {}).get("coaching_team_daily_messages")
    
    if isinstance(entitlement_daily_limit, int):
        daily_limit = entitlement_daily_limit
    else:
        daily_limit = int(plan_doc.get("daily_conversation_limit", 3) or 3)
    
    return {
        "plan": plan,
        "is_admin": user_doc.get("is_admin", False),
        "daily_limit": daily_limit,
        "user_id": user_id
    }


def _extract_user_id(owner_id: str) -> str:
    """Extract raw user_id from owner_id format for DB queries."""
    return owner_id.replace("auth:", "").replace("guest:", "")

# ── PRO PERSONAS ──
PRO_PERSONAS = {
    "HealthHalo": """You are HealthHalo, a compassionate and knowledgeable medical wellness companion. 
    Role: Provide evidence-based health information, wellness tips, and symptom guidance.
    Tone: Professional, empathetic, clear, and reassuring.
    Format: Use Markdown. Use bullet points for steps.
    Critical: ALWAYS state that you are an AI and not a doctor. For serious symptoms, advise seeking professional care immediately.""",
    "CareConnect": """You are CareConnect, a specialized assistant for caregivers of the elderly.
    Role: Offer practical advice on daily care, safety, medication management, and emotional support.
    Tone: Patient, supportive, and practical.
    Format: Structured advice with clear headings.""",
    "FinWise": """You are FinWise, a senior financial literacy coach.
    Role: Explain complex financial concepts, budgeting strategies, and investment basics in simple terms.
    Tone: Objective, educational, and prudent.
    Format: Use tables for budget breakdowns. Use bold for key terms.
    Disclaimer: Always clarify this is for educational purposes, not professional financial advice.""",
    "SmartBuy": """You are SmartBuy, an expert product researcher and shopping assistant.
    Role: Compare products, find deals, and analyze specs to find the best value.
    Tone: Unbiased, analytical, and consumer-focused.
    Format: Pros/Cons lists, comparison tables, and value verdicts.""",
    "HomeMate": """You are HomeMate, a professional home consultant specializing in interior design, maintenance, and real estate.
    Role: Provide renovation ideas, decor tips, and property maintenance advice.
    Tone: Creative, practical, and stylish.
    Format: Step-by-step guides, style suggestions.""",
    "AutoGenie": """You are AutoGenie, a veteran automotive specialist.
    Role: Assist with car buying advice, maintenance troubleshooting, and model comparisons.
    Tone: Knowledgeable, direct, and technical but accessible.
    Format: Diagnostic checklists, feature comparisons.""",
    "DisasterGuard": """You are DisasterGuard, an emergency preparedness expert.
    Role: Provide survival guides, safety checklists, and risk assessments.
    Tone: Calm, authoritative, and urgent when necessary.
    Format: Actionable checklists, priority lists.""",
    "AssetPilot": """You are AssetPilot, a wealth strategy educator.
    Role: Discuss asset allocation, market trends, and investment principles.
    Tone: Sophisticated, data-driven, and risk-aware.
    Format: Strategic insights, risk analysis.""",
    "TimeSaver": """You are TimeSaver, an elite productivity coach.
    Role: Optimize schedules, streamline workflows, and teach time management techniques.
    Tone: Energetic, efficient, and motivating.
    Format: Optimized schedules, bulleted action plans.""",
    "TravelPal": """You are TravelPal, a luxury travel concierge.
    Role: Plan detailed itineraries, suggest hidden gems, and provide cultural insights.
    Tone: Enthusiastic, worldly, and sophisticated.
    Format: Day-by-day itineraries, 'Don't Miss' highlights.""",
}

# ── Request Models ──


class HealthHaloRequest(BaseModel):
    query: str
    health_context: Optional[str] = None
    fallback_user_id: Optional[str] = None


class FinWiseRequest(BaseModel):
    question: str
    financial_goal: Optional[str] = None
    fallback_user_id: Optional[str] = None


class SmartBuyRequest(BaseModel):
    query: str
    budget: Optional[float] = None
    category: Optional[str] = None
    fallback_user_id: Optional[str] = None


class HomeMateRequest(BaseModel):
    query: str
    property_type: Optional[str] = None
    location: Optional[str] = None
    fallback_user_id: Optional[str] = None


class AutoGenieRequest(BaseModel):
    query: str
    vehicle_type: Optional[str] = None
    budget: Optional[float] = None
    fallback_user_id: Optional[str] = None


class DisasterGuardRequest(BaseModel):
    query: str
    location: Optional[str] = None
    disaster_type: Optional[str] = None
    fallback_user_id: Optional[str] = None


class AssetPilotRequest(BaseModel):
    query: str
    investment_type: Optional[str] = None
    risk_tolerance: Optional[str] = "moderate"
    fallback_user_id: Optional[str] = None


class TimeSaverRequest(BaseModel):
    query: str
    task_type: Optional[str] = None
    fallback_user_id: Optional[str] = None


class TravelPalTripRequest(BaseModel):
    destination: str
    duration: Optional[str] = "7 days"
    interests: Optional[List[str]] = []
    budget: Optional[str] = "moderate"
    fallback_user_id: Optional[str] = None


class TravelPalTranslateRequest(BaseModel):
    text: str
    target_language: str
    fallback_user_id: Optional[str] = None


class TravelPalCultureRequest(BaseModel):
    country: str
    fallback_user_id: Optional[str] = None


class GlobeCoachLifestyleRequest(BaseModel):
    current_location: str
    goals: List[str] = []
    areas: List[str] = ["health", "productivity", "finance"]
    fallback_user_id: Optional[str] = None


class GlobeCoachLanguageRequest(BaseModel):
    target_language: str
    proficiency: str = "beginner"
    practice_text: Optional[str] = None
    fallback_user_id: Optional[str] = None


class GlobeCoachRelocationRequest(BaseModel):
    current_location: str
    target_location: str
    reason: str = "work"
    family_size: int = 1
    fallback_user_id: Optional[str] = None


class GlobeCoachEQRequest(BaseModel):
    situation: str
    emotion: Optional[str] = None
    context: str = "personal"
    fallback_user_id: Optional[str] = None


class AIChatRequest(BaseModel):
    message: str
    feature: str
    tool_id: Optional[str] = None
    language: str = "English"
    session_id: Optional[str] = None
    fallback_user_id: Optional[str] = None


FEATURE_ALIASES = {
    "grammarly": "ai-writer",
    "jasper": "ai-copywriter",
    "picsart": "ai-photo",
    "bemyai": "ai-vision",
    "zapier": "ai-automations",
    "chatgpt": "ai-chatbot",
    "cognitive": "ai-cognitive",
    "enterprise": "ai-enterprise",
    "privatesearch": "ai-search",
    "speech": "ai-speech",
}


BATCH3_CHAT_LIMITS = {
    "ai-video": {"free": 4, "basic": 120, "premium": -1, "admin": -1, "enterprise": -1},
    "ai-photo": {"free": 4, "basic": 120, "premium": -1, "admin": -1, "enterprise": -1},
    "ai-speech": {"free": 4, "basic": 120, "premium": -1, "admin": -1, "enterprise": -1},
    "ai-enterprise": {"free": 2, "basic": 80, "premium": -1, "admin": -1, "enterprise": -1},
    "bill-generator": {"free": 3, "basic": 120, "premium": -1, "admin": -1, "enterprise": -1},
}


# ── Helper for generic AI chat ──


def _resp_text(response):
    return response.text if hasattr(response, "text") else str(response)


async def _generate_visual_aid(prompt_context: str):
    """Generates a visual aid image using OpenAI DALL-E via Emergent Key."""
    try:
        client = AsyncOpenAI(api_key=EMERGENT_LLM_KEY, base_url="https://llm.emergentagent.com/v1")

        # Create a visual prompt summary
        image_prompt = f"Create a clear, educational diagram, chart, or illustration that explains or visualizes: {prompt_context[:400]}. Style: Clean, modern, infographics style."

        response = await client.images.generate(
            model="dall-e-3",  # or gpt-image-1 if available, but standardizing
            prompt=image_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        return response.data[0].url
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return None


async def _ai_tool_chat(
    name: str, system_prompt: str, user_prompt: str, session_prefix: str, generate_image: bool = True
):
    try:
        # Use PRO_PERSONAS if available, otherwise fallback to provided system_prompt
        final_system_prompt = PRO_PERSONAS.get(name, system_prompt)

        # Use Verified Text Generation (with critique loop)
        session_id = f"{session_prefix}-{uuid.uuid4()}"
        text_response = await generate_verified_text(user_prompt, final_system_prompt, session_id)

        # 2. Generate Image (if applicable)
        # We only generate if the response is substantive
        image_url = None
        if generate_image and len(text_response) > 50:
            try:
                image_url = await _generate_visual_aid(user_prompt)
                if image_url:
                    text_response += f"\n\n![Visual Explanation]({image_url})"
            except Exception:
                pass

        return {"response": text_response, "assistant": name}
    except Exception as e:
        logger.error(f"{name} error: {e}")
        return {
            "response": "I'm encountering a temporary connection issue. Please try again in a moment.",
            "assistant": name,
        }


# ── HealthHalo ──
@router.post("/healthhalo/consult")
async def healthhalo_consult(request_obj: Request, payload: HealthHaloRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    _resolve_owner_id(user, payload.fallback_user_id)
    
    prompt = f"User query: {payload.query}\nContext: {payload.health_context or 'General wellness inquiry'}"
    result = await _ai_tool_chat("HealthHalo", "", prompt, "healthhalo_consult")
    result["disclaimer"] = "General wellness info only. Consult a doctor for medical advice."
    return result


# ── CareConnect ──
@router.post("/careconnect/assist")
async def careconnect_assist(request: HealthHaloRequest):
    prompt = f"Caregiver Query: {request.query}"
    return await _ai_tool_chat("CareConnect", "", prompt, "careconnect_assist")


# ── FinWise ──
@router.post("/finwise/advise")
async def finwise_advise(request_obj: Request, payload: FinWiseRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    prompt = f"Financial Question: {payload.question}\nUser Goal: {payload.financial_goal or 'Financial health'}"
    result = await _ai_tool_chat("FinWise", "", prompt, "finwise_advise")
    result["disclaimer"] = "Educational content only. Not professional financial advice."
    result["owner_id"] = owner_id
    return result


# ── SmartBuy ──
@router.post("/smartbuy/search")
async def smartbuy_search(request_obj: Request, payload: SmartBuyRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    budget_info = f"Budget: ${payload.budget}" if payload.budget else "No specific budget"
    prompt = f"Product Search: {payload.query}\n{budget_info}\nCategory: {payload.category or 'General'}"
    result = await _ai_tool_chat("SmartBuy", "", prompt, "smartbuy_search")
    result["recommendations"] = []
    result["owner_id"] = owner_id
    return result


# ── HomeMate ──
@router.post("/homemate/consult")
async def homemate_consult(request_obj: Request, payload: HomeMateRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    prompt = f"Home Query: {payload.query}\nProperty Type: {payload.property_type or 'Any'}\nLocation: {payload.location or 'Not specified'}"
    result = await _ai_tool_chat("HomeMate", "", prompt, "homemate_consult")
    result["owner_id"] = owner_id
    return result


# ── AutoGenie ──
@router.post("/autogenie/consult")
async def autogenie_consult(request_obj: Request, payload: AutoGenieRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    budget_info = f"Budget: ${payload.budget}" if payload.budget else "No specific budget"
    prompt = f"Car Query: {payload.query}\nVehicle Preference: {payload.vehicle_type or 'Any'}\n{budget_info}"
    result = await _ai_tool_chat("AutoGenie", "", prompt, "autogenie_consult")
    result["owner_id"] = owner_id
    return result


# ── DisasterGuard ──
@router.post("/disasterguard/prepare")
async def disasterguard_prepare(request_obj: Request, payload: DisasterGuardRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    prompt = f"Emergency Query: {payload.query}\nLocation: {payload.location or 'General'}\nDisaster Context: {payload.disaster_type or 'General preparedness'}"
    result = await _ai_tool_chat("DisasterGuard", "", prompt, "disasterguard_prepare")
    result["safety_tips"] = []
    result["owner_id"] = owner_id
    return result


# ── AssetPilot ──
@router.post("/assetpilot/advise")
async def assetpilot_advise(request_obj: Request, payload: AssetPilotRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    prompt = f"Investment Query: {payload.query}\nType: {payload.investment_type or 'General'}\nRisk Tolerance: {payload.risk_tolerance}"
    result = await _ai_tool_chat("AssetPilot", "", prompt, "assetpilot_advise")
    result["disclaimer"] = "Educational content only. Not investment advice."
    result["owner_id"] = owner_id
    return result


# ── TimeSaver ──
@router.post("/timesaver/optimize")
async def timesaver_optimize(request_obj: Request, payload: TimeSaverRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    prompt = f"Productivity Challenge: {payload.query}\nTask Type: {payload.task_type or 'General productivity'}"
    result = await _ai_tool_chat("TimeSaver", "", prompt, "timesaver_optimize")
    result["tips"] = []
    result["owner_id"] = owner_id
    return result


# ── TravelPal ──
@router.post("/travelpal/plan-trip")
async def travelpal_plan_trip(request_obj: Request, payload: TravelPalTripRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    interests_str = ", ".join(payload.interests) if payload.interests else "general sightseeing"
    user_prompt = f"""Plan a {payload.duration} trip to {payload.destination}.
    Budget: {payload.budget}
    Interests: {interests_str}
    
    Please provide a detailed, day-by-day itinerary with specific restaurant and activity recommendations."""

    result = await _ai_tool_chat("TravelPal", "", user_prompt, "travelpal_trip")
    return {
        "itinerary": result["response"],
        "destination": payload.destination,
        "duration": payload.duration,
        "assistant": "TravelPal",
        "owner_id": owner_id,
    }


@router.post("/travelpal/translate")
async def travelpal_translate(request_obj: Request, payload: TravelPalTranslateRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"travelpal-translate-{uuid.uuid4()}",
            system_message="You are a professional translator and cultural linguist. Provide the translation, phonetic pronunciation, and context.",
        ).with_model("openai", "gpt-4o")
        prompt = f"""Translate to {payload.target_language}:
        "{payload.text}" """

        response = await chat.send_message(UserMessage(text=prompt))
        return {
            "translation": _resp_text(response),
            "target_language": payload.target_language,
            "original": payload.text,
            "assistant": "TravelPal",
            "owner_id": owner_id,
        }
    except Exception as e:
        logger.error(f"TravelPal translate error: {e}")
        raise HTTPException(status_code=500, detail="Translation failed")


@router.post("/travelpal/cultural-tips")
async def travelpal_cultural_tips(request_obj: Request, payload: TravelPalCultureRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    prompt = f"I am visiting {payload.country}. What should I know about the culture, etiquette, and customs to be respectful?"
    result = await _ai_tool_chat("TravelPal", "", prompt, "travelpal_culture")
    return {"tips": result["response"], "country": payload.country, "assistant": "TravelPal", "owner_id": owner_id}


# ── GlobeCoach ──
@router.post("/globecoach/lifestyle-optimize")
async def globecoach_lifestyle(request: GlobeCoachLifestyleRequest):
    areas_str = ", ".join(request.areas)
    goals_str = ", ".join(request.goals) if request.goals else "general improvement"

    system = """You are GlobeCoach, a holistic lifestyle architect.
    Role: Design optimized lifestyle plans based on location and goals.
    Tone: Strategic, motivating, and culturally aware."""

    prompt = f"""Location: {request.current_location}
    Focus Areas: {areas_str}
    Goals: {goals_str}
    
    Create a lifestyle optimization plan."""

    result = await _ai_tool_chat("GlobeCoach", system, prompt, "globecoach_lifestyle")
    return {"plan": result["response"], "areas": request.areas, "assistant": "GlobeCoach"}


@router.post("/globecoach/language-coach")
async def globecoach_language(request_obj: Request, payload: GlobeCoachLanguageRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    system = "You are an expert Language Coach. Teach with clarity and cultural nuance."
    prompt = f"Teach me {payload.target_language}. Level: {payload.proficiency}. {f'Critique this text: {payload.practice_text}' if payload.practice_text else 'Give me a mini-lesson.'}"

    result = await _ai_tool_chat("GlobeCoach", system, prompt, "globecoach_language")
    return {
        "lesson": result["response"],
        "language": payload.target_language,
        "level": payload.proficiency,
        "assistant": "GlobeCoach",
        "owner_id": owner_id,
    }


@router.post("/globecoach/relocation-guide")
async def globecoach_relocation(request_obj: Request, payload: GlobeCoachRelocationRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    system = "You are a Global Relocation Expert. Provide detailed logistics, legal, and cultural advice."
    prompt = f"Moving from {payload.current_location} to {payload.target_location}. Reason: {payload.reason}. Family: {payload.family_size}."

    result = await _ai_tool_chat("GlobeCoach", system, prompt, "globecoach_relocation")
    return {
        "guide": result["response"],
        "from": payload.current_location,
        "to": payload.target_location,
        "assistant": "GlobeCoach",
        "owner_id": owner_id,
    }


@router.post("/globecoach/eq-coaching")
async def globecoach_eq(request_obj: Request, payload: GlobeCoachEQRequest):
    # Authenticate
    user = await get_current_user(request_obj)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    system = "You are an EQ (Emotional Intelligence) Coach. Help the user navigate emotions and social dynamics."
    prompt = f"Situation: {payload.situation}. Context: {payload.context}. Emotion: {payload.emotion or 'Unsure'}."

    result = await _ai_tool_chat("GlobeCoach", system, prompt, "globecoach_eq")
    return {"coaching": result["response"], "context": payload.context, "assistant": "GlobeCoach", "owner_id": owner_id}


# ── Universal AI Chat ──

@router.post("/ai-chat")
async def universal_ai_chat(request_obj: Request, payload: AIChatRequest):
    """Universal AI chat endpoint for platform AI features."""
    try:
        # AUTHENTICATION FIRST
        user = await get_current_user(request_obj)
        owner_id = _resolve_owner_id(user, payload.fallback_user_id)
        
        # Get plan and limits using helper
        user_plan_info = await _get_user_plan_and_limits(owner_id)
        user_id = user_plan_info["user_id"]
        plan = user_plan_info["plan"]
        daily_limit = user_plan_info["daily_limit"]
        
        canonical_feature = FEATURE_ALIASES.get(payload.feature, payload.feature)
        
        # Tier enforcement for specific features
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
        
        if canonical_feature in BATCH3_CHAT_LIMITS:
            feature_limit = int((BATCH3_CHAT_LIMITS[canonical_feature] or {}).get(plan, 0))
            if feature_limit >= 0:
                feature_usage_count = await db.usage_analytics.count_documents(
                    {
                        "user_id": user_id,
                        "timestamp": {"$gte": today_start},
                        "$or": [
                            {"feature_id": canonical_feature},
                            {"feature_id": payload.feature},
                            {"canonical_feature": canonical_feature},
                        ],
                    }
                )
                if feature_usage_count >= feature_limit:
                    upgrade_plan = "basic" if plan == "free" else "premium"
                    return {
                        "response": f"You've reached your daily {canonical_feature} limit ({feature_limit} requests for {plan} plan). Upgrade for more capacity.",
                        "feature": payload.feature,
                        "canonical_feature": canonical_feature,
                            "limit_reached": True,
                            "feature_limit_reached": True,
                            "usage": feature_usage_count,
                            "limit": feature_limit,
                            "plan": plan,
                            "required_plan": upgrade_plan,
                            "scope_label": "Limited access" if plan == "free" else "Almost unlimited" if plan == "basic" else "Full unlimited access",
                        }

            usage_count = await db.usage_analytics.count_documents(
                {
                    "user_id": user_id,
                    "timestamp": {"$gte": today_start},
                }
            )
            if isinstance(daily_limit, int) and daily_limit >= 0 and usage_count >= daily_limit:
                # Build upgrade suggestion
                upgrade_plans = []
                gps_plans = await get_subscription_plans_from_gps()
                plan_order = list(gps_plans.keys())
                current_idx = plan_order.index(plan) if plan in plan_order else 0
                for up_plan_id in plan_order[current_idx + 1 :]:
                    up = gps_plans.get(up_plan_id, {})
                    if up:
                        upgrade_plans.append(
                            {
                                "id": up["id"],
                                "name": up["name"],
                                "monthly_price": up["monthly_price"],
                                "daily_limit": up.get("daily_conversation_limit", -1),
                                "features_highlight": up.get("features", [])[:4],
                            }
                        )

                return {
                    "response": f"You've reached your daily AI usage limit ({daily_limit} requests for {plan} plan). Upgrade your plan for more access.",
                    "feature": payload.feature,
                    "limit_reached": True,
                    "usage": usage_count,
                    "limit": daily_limit,
                    "plan": plan,
                    "upgrade_options": upgrade_plans,
                    "usage_percent": min(100, int((usage_count / max(daily_limit, 1)) * 100)),
                }

        session = payload.session_id or f"ai-chat-{payload.feature}-{user_id}-{uuid.uuid4().hex[:8]}"

        # Enhanced Personas for standard features
        feature_contexts = {
            "medimate": PRO_PERSONAS["HealthHalo"],  # Reuse HealthHalo persona
            "pennypilot": PRO_PERSONAS["FinWise"],  # Reuse FinWise persona
            "fitness": "You are FitnessCoach Pro. Create workout plans, nutrition guides, and recovery strategies. Be motivating and scientific.",
            "travelpal": PRO_PERSONAS["TravelPal"],
            "ai-writer": "You are a Professional Editor and Copywriter. Improve grammar, style, and flow. Suggest creative angles. Output polished, publication-ready text.",
            "ai-copywriter": "You are a Marketing Copywriting Expert. Write persuasive, high-conversion copy for ads, emails, and landing pages. Focus on hooks and CTAs.",
            "ai-photo": "You are an AI Art Director. Help the user craft detailed image generation prompts. Explain photography concepts (lighting, composition, style).",
            "ai-vision": "You are AI Vision Analyst. Analyze images in extreme detail. Identify objects, text, emotions, and context.",
            "ai-automations": "You are an Automation Architect. Help design workflows using Zapier, Make, and APIs. Write code snippets for automation scripts.",
            "ai-chatbot": "You are a Knowledge Engine. Provide accurate, encyclopedic answers on any topic. Be helpful and conversational.",
            "ai-cognitive": "You are a Cognitive Performance Coach. Provide brain training exercises, focus techniques, and mental models for problem-solving.",
            "ai-enterprise": "You are a Business Strategy Consultant. Analyze market trends, operational efficiency, and growth strategies. Use professional business terminology.",
            "ai-speech": "You are a Communication Coach. Analyze speech patterns, suggest improvements for public speaking, and help structure presentations.",
            "bill-generator": "You are a billing operations strategist. Help users create accurate bill terms, tax-safe line items, payment follow-up wording, and cashflow-friendly billing workflows.",
            "smartbuy": PRO_PERSONAS["SmartBuy"],
            "ai-search": "You are a Deep Research Agent. Provide comprehensive answers with sources, key takeaways, and follow-up implications.",
            "ai-video": "You are a Video Content Strategist. Analyze video trends, suggest scripts, and help with video production planning.",
        }

        # Aliases
        for alias, target in FEATURE_ALIASES.items():
            feature_contexts[alias] = feature_contexts[target]

        system_msg = feature_contexts.get(payload.feature, "You are RealAICoach, a helpful AI life assistant.")

        if payload.tool_id:
            system_msg += f"\n\nThe user is using the '{payload.tool_id}' tool. Focus on this context."

        if payload.language != "English":
            system_msg += f"\n\nRespond in {payload.language}."

        # Add global markdown instruction
        system_msg += "\n\nFormat your response using Markdown (bold, lists, headers) for readability."

        # 1. Get Text Response (Verified)
        text_response = await generate_verified_text(payload.message, system_msg, session)

        # 2. Generate Image (Visual Aid)
        # Automatically generate visual aid for explanation
        if len(text_response) > 50:  # Only if substantial answer
            try:
                image_url = await _generate_visual_aid(payload.message + " " + text_response[:200])
                if image_url:
                    text_response += f"\n\n![Visual Explanation]({image_url})"
            except Exception:
                pass  # Fail silently on image gen to not break chat

        # Track usage
        try:
            await db.usage_analytics.insert_one(
                {
                    "user_id": user_id,
                    "feature_id": canonical_feature,
                    "feature_alias": payload.feature,
                    "canonical_feature": canonical_feature,
                    "tool_id": payload.tool_id or "general",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception:
            pass

        persona = f"{canonical_feature.replace('-', ' ').title()} Expert"
        return {
            "response": text_response,
            "feature": payload.feature,
            "canonical_feature": canonical_feature,
            "tool_id": payload.tool_id,
            "session_id": session,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "persona": persona,
            "icon": "sparkles",
            "owner_id": owner_id,
            "plan": plan,
        }
    except Exception as e:
        logger.error(f"AI Chat error for {payload.feature}: {e}")
        raise HTTPException(status_code=500, detail=f"AI processing failed for {payload.feature}")
