"""Global AI Marketplace — Discover, compare, and get recommendations for AI services.

AI-powered service discovery with comparisons, recommendations, and usage tracking.

API:
- GET  /api/ai-marketplace/services          — Browse AI services catalog
- GET  /api/ai-marketplace/services/{id}     — Service details + AI review
- POST /api/ai-marketplace/compare           — Compare multiple services
- POST /api/ai-marketplace/recommend         — Get personalized recommendations
- GET  /api/ai-marketplace/trending          — Trending AI tools
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional, List
import logging

from routes.db import db, get_current_user
from services.ai_helpers import ai_generate, ai_generate_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-marketplace")

# Built-in AI service catalog
AI_SERVICES = [
    {
        "service_id": "svc_gpt",
        "name": "GPT-4o",
        "provider": "OpenAI",
        "category": "text-generation",
        "description": "Advanced language model for text generation, analysis, and reasoning.",
        "icon": "chatbubble-ellipses",
        "color": "#10B981",
        "pricing": "Pay-per-token",
        "rating": 4.8,
        "capabilities": ["Text Generation", "Code Writing", "Analysis", "Translation", "Summarization"],
        "use_cases": ["Content creation", "Customer support", "Code assistance", "Research"],
    },
    {
        "service_id": "svc_claude",
        "name": "Claude Sonnet",
        "provider": "Anthropic",
        "category": "text-generation",
        "description": "Balanced AI assistant focused on helpfulness, harmlessness, and honesty.",
        "icon": "sparkles",
        "color": "#8B5CF6",
        "pricing": "Pay-per-token",
        "rating": 4.7,
        "capabilities": ["Long Context", "Analysis", "Creative Writing", "Code", "Safety"],
        "use_cases": ["Document analysis", "Creative writing", "Research", "Tutoring"],
    },
    {
        "service_id": "svc_gemini",
        "name": "Gemini Pro",
        "provider": "Google",
        "category": "multimodal",
        "description": "Multimodal AI model with text, image, and code understanding.",
        "icon": "diamond",
        "color": "#3B82F6",
        "pricing": "Free tier + Pay-per-use",
        "rating": 4.6,
        "capabilities": ["Multimodal", "Code Generation", "Image Understanding", "Search Integration"],
        "use_cases": ["Multimodal tasks", "Search augmentation", "Education", "Development"],
    },
    {
        "service_id": "svc_dall_e",
        "name": "DALL-E 3",
        "provider": "OpenAI",
        "category": "image-generation",
        "description": "Create realistic images and art from natural language descriptions.",
        "icon": "image",
        "color": "#EC4899",
        "pricing": "Per image",
        "rating": 4.5,
        "capabilities": ["Image Generation", "Art Creation", "Photo Editing", "Style Transfer"],
        "use_cases": ["Marketing materials", "Art creation", "Prototyping", "Social media"],
    },
    {
        "service_id": "svc_midjourney",
        "name": "Midjourney",
        "provider": "Midjourney",
        "category": "image-generation",
        "description": "AI art generator known for stunning, artistic image creation.",
        "icon": "brush",
        "color": "#F59E0B",
        "pricing": "Subscription",
        "rating": 4.7,
        "capabilities": ["Artistic Images", "Style Variation", "High Resolution", "Consistency"],
        "use_cases": ["Concept art", "Brand design", "Illustration", "Creative projects"],
    },
    {
        "service_id": "svc_whisper",
        "name": "Whisper",
        "provider": "OpenAI",
        "category": "speech",
        "description": "Robust speech recognition supporting 99 languages.",
        "icon": "mic",
        "color": "#06B6D4",
        "pricing": "Pay-per-minute",
        "rating": 4.6,
        "capabilities": ["Speech-to-Text", "Translation", "Multi-language", "Punctuation"],
        "use_cases": ["Transcription", "Meeting notes", "Accessibility", "Content creation"],
    },
    {
        "service_id": "svc_elevenlabs",
        "name": "ElevenLabs",
        "provider": "ElevenLabs",
        "category": "speech",
        "description": "Premium AI voice synthesis with natural-sounding speech.",
        "icon": "volume-high",
        "color": "#EF4444",
        "pricing": "Subscription + Per character",
        "rating": 4.8,
        "capabilities": ["Text-to-Speech", "Voice Cloning", "Multilingual", "Emotion Control"],
        "use_cases": ["Audiobooks", "Voiceovers", "Podcasts", "Gaming"],
    },
    {
        "service_id": "svc_copilot",
        "name": "GitHub Copilot",
        "provider": "GitHub/Microsoft",
        "category": "code",
        "description": "AI pair programmer that suggests code in real-time.",
        "icon": "code-slash",
        "color": "#1F2937",
        "pricing": "Monthly subscription",
        "rating": 4.5,
        "capabilities": ["Code Completion", "Multi-language", "Test Generation", "Refactoring"],
        "use_cases": ["Software development", "Code review", "Testing", "Documentation"],
    },
    {
        "service_id": "svc_perplexity",
        "name": "Perplexity AI",
        "provider": "Perplexity",
        "category": "search",
        "description": "AI-powered search engine with cited, accurate answers.",
        "icon": "search",
        "color": "#22D3EE",
        "pricing": "Free + Pro",
        "rating": 4.6,
        "capabilities": ["Web Search", "Citations", "Real-time Info", "Follow-up Questions"],
        "use_cases": ["Research", "Fact-checking", "Learning", "News analysis"],
    },
    {
        "service_id": "svc_sora",
        "name": "Sora",
        "provider": "OpenAI",
        "category": "video-generation",
        "description": "AI model that generates realistic videos from text prompts.",
        "icon": "videocam",
        "color": "#D946EF",
        "pricing": "Pay-per-video",
        "rating": 4.4,
        "capabilities": ["Video Generation", "Scene Creation", "Motion", "Long-form"],
        "use_cases": ["Marketing", "Content creation", "Prototyping", "Education"],
    },
]

CATEGORIES = [
    {"id": "all", "name": "All Services"},
    {"id": "text-generation", "name": "Text & Chat"},
    {"id": "image-generation", "name": "Image Generation"},
    {"id": "speech", "name": "Speech & Audio"},
    {"id": "code", "name": "Code & Dev"},
    {"id": "multimodal", "name": "Multimodal"},
    {"id": "search", "name": "Search & Research"},
    {"id": "video-generation", "name": "Video"},
]


class CompareRequest(BaseModel):
    service_ids: List[str]


class RecommendRequest(BaseModel):
    use_case: str
    budget: Optional[str] = None
    requirements: Optional[str] = None


@router.get("/services")
async def list_services(request: Request, category: Optional[str] = None):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    services = AI_SERVICES
    if category and category != "all":
        services = [s for s in services if s["category"] == category]
    return {"services": services, "categories": CATEGORIES}


@router.get("/services/{service_id}")
async def get_service(request: Request, service_id: str):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    service = next((s for s in AI_SERVICES if s["service_id"] == service_id), None)
    if not service:
        raise HTTPException(404, "Service not found")

    # Generate AI-powered detailed review
    try:
        review = await ai_generate(
            "You are an AI technology analyst. Give a concise, balanced review (150 words max).",
            f"Provide a brief expert review of {service['name']} by {service['provider']}. "
            f"Cover: strengths, limitations, best for, pricing value. Be objective and practical.",
            f"review-{service_id}",
        )
    except Exception:
        review = f"{service['name']} is a leading AI service in the {service['category']} space."

    # Track usage
    try:
        await db.usage_analytics.insert_one(
            {
                "user_id": user.user_id,
                "feature_id": "ai-marketplace",
                "tool_id": service_id,
                "action": "view-service",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        pass

    return {"service": service, "ai_review": review}


@router.post("/compare")
async def compare_services(request: Request, body: CompareRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    if len(body.service_ids) < 2 or len(body.service_ids) > 4:
        raise HTTPException(400, "Compare 2-4 services")

    services = [s for s in AI_SERVICES if s["service_id"] in body.service_ids]
    if len(services) < 2:
        raise HTTPException(400, "At least 2 valid services required")

    names = ", ".join([s["name"] for s in services])
    system_msg = """You are an AI technology analyst. Compare AI services objectively.
Return ONLY valid JSON:
{
  "comparison_summary": "Brief overall comparison",
  "winner_for": {
    "best_overall": "service name",
    "best_value": "service name",
    "best_for_beginners": "service name",
    "most_powerful": "service name"
  },
  "detailed_comparison": [
    {"criteria": "Performance", "scores": {"service1": 9, "service2": 8}, "notes": "..."},
    {"criteria": "Ease of Use", "scores": {"service1": 8, "service2": 9}, "notes": "..."},
    {"criteria": "Pricing", "scores": {"service1": 7, "service2": 8}, "notes": "..."},
    {"criteria": "Capabilities", "scores": {"service1": 9, "service2": 8}, "notes": "..."}
  ],
  "recommendation": "Overall recommendation text"
}"""
    prompt = f"Compare these AI services: {names}. Service details: {str([{k: v for k, v in s.items() if k != 'service_id'} for s in services])[:2000]}"

    try:
        comparison = await ai_generate_json(system_msg, prompt, "compare")
    except Exception as e:
        logger.error(f"Compare error: {e}")
        comparison = {
            "comparison_summary": f"Comparison of {names}",
            "winner_for": {"best_overall": services[0]["name"]},
            "detailed_comparison": [
                {
                    "criteria": "Overall",
                    "scores": {s["name"]: int(s.get("rating", 4) * 2) for s in services},
                    "notes": "Based on general ratings",
                }
            ],
            "recommendation": "Choose based on your specific use case requirements.",
        }

    return {"services": services, "comparison": comparison}


@router.post("/recommend")
async def recommend_services(request: Request, body: RecommendRequest):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")

    budget_text = f"\nBudget: {body.budget}" if body.budget else ""
    reqs_text = f"\nRequirements: {body.requirements}" if body.requirements else ""

    system_msg = """You are an AI advisor helping users find the best AI tools.
Return ONLY valid JSON:
{
  "recommendations": [
    {"service_name": "...", "match_score": 95, "reason": "Why this is recommended"},
    {"service_name": "...", "match_score": 85, "reason": "Why this is recommended"}
  ],
  "advice": "General advice for this use case",
  "workflow_suggestion": "How to combine these tools effectively"
}"""
    catalog_summary = str(
        [
            {"name": s["name"], "category": s["category"], "capabilities": s["capabilities"], "pricing": s["pricing"]}
            for s in AI_SERVICES
        ]
    )
    prompt = f"Use case: {body.use_case}{budget_text}{reqs_text}\n\nAvailable services:\n{catalog_summary[:2000]}\n\nRecommend the best AI tools (top 3-4):"

    try:
        recs = await ai_generate_json(system_msg, prompt, "recommend")
    except Exception as e:
        logger.error(f"Recommend error: {e}")
        recs = {
            "recommendations": [
                {"service_name": "GPT-4o", "match_score": 90, "reason": "Versatile and powerful for most use cases"}
            ],
            "advice": "Start with a general-purpose model and specialize as needed.",
            "workflow_suggestion": "Use GPT-4o for text tasks and add specialized tools as your needs grow.",
        }

    return recs


@router.get("/trending")
async def trending_services(request: Request):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Unauthorized")
    # Return top services by rating
    sorted_services = sorted(AI_SERVICES, key=lambda s: s.get("rating", 0), reverse=True)
    return {"trending": sorted_services[:6], "total_services": len(AI_SERVICES)}
