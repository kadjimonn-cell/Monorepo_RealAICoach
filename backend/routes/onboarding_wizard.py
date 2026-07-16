"""AI Onboarding Wizard API - Recommends top 5 AI copilots based on user goals."""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from .db import db, require_auth

router = APIRouter(prefix="/onboarding-wizard", tags=["Onboarding Wizard"])

# Goal → Feature scoring map
GOAL_SCORES = {
    "career": {
        "ai-writer": 3,
        "ai-enterprise": 3,
        "ai-chatbot": 2,
        "ai-search": 2,
        "ai-cognitive": 1,
    },
    "health": {"fitness": 3, "medimate": 3, "ai-chatbot": 1, "ai-search": 1},
    "finance": {"pennypilot": 3, "smartbuy": 2, "ai-chatbot": 1},
    "learning": {"school-tutor": 3, "ai-search": 3, "ai-chatbot": 2, "ai-cognitive": 2, "ai-writer": 1},
    "creative": {"ai-writer": 3, "ai-photo": 3, "ai-video": 2, "ai-speech": 2},
    "relationships": {"ai-found-love": 3, "ai-chatbot": 2, "ai-writer": 1, "travelpal": 1},
}

NEED_SCORES = {
    "writing": {"ai-writer": 3, "ai-chatbot": 1, "ai-cognitive": 1},
    "planning": {"ai-automations": 3, "travelpal": 2, "fitness": 1, "pennypilot": 1},
    "research": {"ai-search": 3, "ai-cognitive": 2, "ai-chatbot": 1},
    "creativity": {"ai-photo": 3, "ai-video": 2, "ai-speech": 2, "ai-writer": 1},
    "wellness": {"fitness": 3, "medimate": 3, "ai-chatbot": 1},
    "communication": {"ai-speech": 3, "ai-writer": 2, "ai-chatbot": 1, "ai-found-love": 1},
}

STYLE_SCORES = {
    "quick": {"ai-chatbot": 2, "ai-search": 2, "smartbuy": 1},
    "deep": {"ai-cognitive": 2, "ai-search": 2, "school-tutor": 1, "ai-writer": 1},
    "stepbystep": {"fitness": 2, "pennypilot": 2, "school-tutor": 2, "ai-automations": 1},
    "visual": {"ai-photo": 2, "ai-video": 2, "ai-vision": 1},
    "voice": {"ai-speech": 3, "ai-chatbot": 1},
}

FEATURE_META = {
    "ai-writer": {
        "title": "AI Writer Pro",
        "icon": "create",
        "color": "#10B981",
        "desc": "Articles, marketing copy, ads, social posts, and stories",
    },
    "ai-chatbot": {
        "title": "AI Chatbot",
        "icon": "chatbubbles",
        "color": "#3B82F6",
        "desc": "Your general-purpose AI assistant",
    },
    "ai-search": {
        "title": "AI Search",
        "icon": "search",
        "color": "#0EA5E9",
        "desc": "Deep research and answers from the web",
    },
    "ai-automations": {
        "title": "Automations",
        "icon": "flash",
        "color": "#F59E0B",
        "desc": "Create workflows and automate tasks",
    },
    "ai-cognitive": {
        "title": "Cognitive",
        "icon": "bulb",
        "color": "#7C3AED",
        "desc": "Analyze text, sentiment, and patterns",
    },
    "medimate": {
        "title": "Health Companion",
        "icon": "medkit",
        "color": "#EF4444",
        "desc": "Symptom checker and vital metrics tracking",
    },
    "fitness": {
        "title": "Fitness & Nutrition",
        "icon": "barbell",
        "color": "#F97316",
        "desc": "Workout plans, meal planning, and nutrition",
    },
    "pennypilot": {
        "title": "Financial Hub",
        "icon": "wallet",
        "color": "#6366F1",
        "desc": "Budget coaching and financial forecasting",
    },
    "smartbuy": {"title": "SmartBuy", "icon": "cart", "color": "#F59E0B", "desc": "Find the best deals and products"},
    "travelpal": {
        "title": "TravelPal",
        "icon": "airplane",
        "color": "#0EA5E9",
        "desc": "Plan trips, flights, and itineraries",
    },
    "ai-found-love": {
        "title": "Dating Coach",
        "icon": "heart",
        "color": "#E11D48",
        "desc": "Relationship advice and profile tips",
    },
    "smart-cars": {
        "title": "Smart Cars",
        "icon": "car",
        "color": "#DC2626",
        "desc": "Car buying, selling, and maintenance",
    },
    "buy-smart-home": {
        "title": "Real Estate",
        "icon": "home",
        "color": "#2563EB",
        "desc": "Property search and market analysis",
    },
    "ai-video": {
        "title": "Video Hub",
        "icon": "videocam",
        "color": "#E50914",
        "desc": "AI-generated videos and entertainment",
    },
    "ai-photo": {
        "title": "AI Visual Studio",
        "icon": "image",
        "color": "#D946EF",
        "desc": "Generate, edit, and analyze images",
    },
    "ai-speech": {"title": "AI Speech", "icon": "mic", "color": "#06B6D4", "desc": "Text-to-speech and voice cloning"},
    "ai-enterprise": {
        "title": "Enterprise",
        "icon": "business",
        "color": "#0F766E",
        "desc": "Business tools and analytics",
    },
    "school-tutor": {
        "title": "School Tutor",
        "icon": "school",
        "color": "#F59E0B",
        "desc": "Help with homework and learning",
    },
}


async def _enabled_feature_ids() -> set[str]:
    rows = await db.feature_registry.find(
        {"enabled": {"$ne": False}},
        {"_id": 0, "feature_id": 1},
    ).to_list(1000)
    return {
        str(row.get("feature_id") or "").strip()
        for row in rows
        if str(row.get("feature_id") or "").strip()
    }


async def _filter_enabled_recommendations(recommendations: list[dict]) -> list[dict]:
    enabled_ids = await _enabled_feature_ids()
    if not enabled_ids:
        return recommendations
    return [rec for rec in recommendations if str(rec.get("feature_id") or "") in enabled_ids]


class WizardSubmit(BaseModel):
    goal: str
    need: str
    style: str


@router.get("/status")
async def get_wizard_status(request: Request):
    """Check if user has completed the onboarding wizard."""
    user = await require_auth(request)
    doc = await db.onboarding_wizard.find_one({"user_id": user.user_id}, {"_id": 0})
    if doc:
        # Wizard was completed or dismissed — never show again
        return {
            "completed": True,
            "recommendations": await _filter_enabled_recommendations(doc.get("recommendations", [])),
            "answers": doc.get("answers", {}),
        }

    # Only show wizard to brand-new users (created in the last 10 minutes)
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "created_at": 1})
    if user_doc and user_doc.get("created_at"):
        created = user_doc["created_at"]
        now = datetime.now(timezone.utc)
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                return {"completed": True, "recommendations": [], "answers": {}}
        elif not hasattr(created, "tzinfo") or created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (now - created).total_seconds()
        if age > 600:  # older than 10 minutes → returning user, skip wizard
            return {"completed": True, "recommendations": [], "answers": {}}

    return {"completed": False, "recommendations": [], "answers": {}}


@router.post("/submit")
async def submit_wizard(data: WizardSubmit, request: Request):
    """Submit wizard answers and get personalized recommendations."""
    user = await require_auth(request)
    scores: dict = {}

    for mapping, key in [(GOAL_SCORES, data.goal), (NEED_SCORES, data.need), (STYLE_SCORES, data.style)]:
        for fid, pts in mapping.get(key, {}).items():
            scores[fid] = scores.get(fid, 0) + pts

    enabled_ids = await _enabled_feature_ids()
    if enabled_ids:
        scores = {fid: pts for fid, pts in scores.items() if fid in enabled_ids}

    sorted_features = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
    recommendations = []
    for fid, score in sorted_features:
        meta = FEATURE_META.get(fid, {})
        recommendations.append(
            {
                "feature_id": fid,
                "title": meta.get("title", fid),
                "icon": meta.get("icon", "sparkles"),
                "color": meta.get("color", "#3B82F6"),
                "description": meta.get("desc", ""),
                "score": score,
            }
        )

    now = datetime.now(timezone.utc).isoformat()
    await db.onboarding_wizard.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "user_id": user.user_id,
                "answers": {"goal": data.goal, "need": data.need, "style": data.style},
                "recommendations": recommendations,
                "completed_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )

    return {"success": True, "recommendations": recommendations}


@router.post("/reset")
async def reset_wizard(request: Request):
    """Reset wizard so user can retake it."""
    user = await require_auth(request)
    await db.onboarding_wizard.delete_one({"user_id": user.user_id})
    return {"success": True}


@router.post("/dismiss")
async def dismiss_wizard(request: Request):
    """Mark wizard as dismissed so it never shows again."""
    user = await require_auth(request)
    now = datetime.now(timezone.utc).isoformat()
    await db.onboarding_wizard.update_one(
        {"user_id": user.user_id},
        {"$set": {"user_id": user.user_id, "dismissed": True, "dismissed_at": now}},
        upsert=True,
    )
    return {"success": True}
