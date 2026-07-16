"""Video Creator Studio - Enterprise-grade video production planning and workflow management.

Full-stack video creation platform with AI-powered script generation, storyboard building,
platform optimization, and production workflow management.
"""

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Any, Dict
from datetime import datetime, timezone
import uuid
import logging
import re
from emergentintegrations.llm.chat import LlmChat, UserMessage

from .db import db, EMERGENT_LLM_KEY, get_current_user, User
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/video-studio", tags=["Video Creator Studio"])
logger = logging.getLogger("routes.video_creator_studio")
GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")

# ── FEATURE CONSTANTS ──
FEATURE_ID = "ai-video"
FEATURE_NAME = "Video Creator Studio"

# ── MONGODB COLLECTIONS ──
COLL_PROJECTS = "video_creator_projects"
COLL_SCRIPTS = "video_creator_scripts"
COLL_STORYBOARDS = "video_creator_storyboards"
COLL_CHECKLISTS = "video_creator_checklists"
COLL_THUMBNAILS = "video_creator_thumbnails"
COLL_OPTIMIZATIONS = "video_creator_platform_optimizations"
COLL_ANALYTICS = "video_creator_usage_analytics"

# ── TIER LIMITS ──
TIER_LIMITS = {
    "free": {
        "projects_per_month": 2,
        "scripts_per_day": 3,
        "storyboards_per_day": 2,
        "thumbnails_per_day": 3,
        "exports_per_month": 5,
        "ai_requests_per_day": 10,
        "max_script_length": 500,  # words
        "max_storyboard_shots": 10,
        "export_formats": ["pdf"]
    },
    "basic": {
        "projects_per_month": 20,
        "scripts_per_day": 30,
        "storyboards_per_day": 20,
        "thumbnails_per_day": 30,
        "exports_per_month": 100,
        "ai_requests_per_day": 120,
        "max_script_length": 2000,
        "max_storyboard_shots": 50,
        "export_formats": ["pdf", "markdown"]
    },
    "premium": {
        "projects_per_month": -1,  # Unlimited
        "scripts_per_day": -1,
        "storyboards_per_day": -1,
        "thumbnails_per_day": -1,
        "exports_per_month": -1,
        "ai_requests_per_day": -1,
        "max_script_length": -1,
        "max_storyboard_shots": 100,
        "export_formats": ["pdf", "markdown", "notion", "trello", "google_drive"]
    },
    "admin": {
        "projects_per_month": -1,
        "scripts_per_day": -1,
        "storyboards_per_day": -1,
        "thumbnails_per_day": -1,
        "exports_per_month": -1,
        "ai_requests_per_day": -1,
        "max_script_length": -1,
        "max_storyboard_shots": 100,
        "export_formats": ["pdf", "markdown", "notion", "trello", "google_drive"]
    }
}

# ── AUTHENTICATION HELPER ──
def _resolve_owner_id(user: Optional[User], fallback_user_id: Optional[str]) -> str:
    """Resolve owner_id from authenticated user or fallback guest ID."""
    if user and hasattr(user, "user_id"):
        return f"auth:{user.user_id}"

    fallback = str(fallback_user_id or "").strip()
    if fallback:
        if not GUEST_ID_RE.match(fallback):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "video_studio_invalid_guest_id",
                    "message": "fallback_user_id format is invalid",
                },
            )
        return f"guest:{fallback}"

    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "video_studio_auth_required",
            "message": "Login required or provide fallback_user_id for guest access"
        }
    )


def _extract_user_id(owner_id: str) -> str:
    """Extract raw user_id from owner_id format."""
    return owner_id.replace("auth:", "").replace("guest:", "")


async def _get_user_plan(user: Optional[User]) -> str:
    """Get user's subscription plan."""
    if not user:
        return "free"
    user_id = str(getattr(user, "user_id", "") or "").replace("auth:", "").replace("guest:", "")
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

    merged_doc = {
        "is_admin": bool(getattr(user, "is_admin", False)) or bool(user_doc.get("is_admin") if user_doc else False),
        "subscription_plan": (user_doc or {}).get("subscription_plan", getattr(user, "subscription_plan", "free")),
        "subscription_status": (user_doc or {}).get("subscription_status", getattr(user, "subscription_status", "active")),
        "subscription_end_date": (user_doc or {}).get("subscription_end_date", getattr(user, "subscription_end_date", None)),
        "pending_subscription_transition": (user_doc or {}).get(
            "pending_subscription_transition",
            getattr(user, "pending_subscription_transition", None),
        ),
        "payment_verified": bool((user_doc or {}).get("payment_verified", getattr(user, "payment_verified", False))),
    }

    plan = compute_effective_plan(merged_doc)
    return plan if plan in TIER_LIMITS else "free"


def _now_iso() -> str:
    """Return current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def _today_key() -> str:
    """Return today's date as YYYY-MM-DD key."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _month_key() -> str:
    """Return current month as YYYY-MM key."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ── PYDANTIC MODELS ──

class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    platform: Literal["youtube", "tiktok", "instagram", "linkedin", "multi"] = "youtube"
    video_type: Literal["tutorial", "vlog", "promotional", "educational", "entertainment", "review"] = "educational"
    target_duration_seconds: int = Field(default=600, ge=10, le=7200)
    target_audience: Optional[str] = Field(default=None, max_length=200)
    production_deadline: Optional[str] = None
    fallback_user_id: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[Literal["draft", "script_ready", "production", "editing", "published"]] = None
    platform: Optional[Literal["youtube", "tiktok", "instagram", "linkedin", "multi"]] = None
    target_duration_seconds: Optional[int] = Field(default=None, ge=10, le=7200)
    production_deadline: Optional[str] = None


class ScriptGenerateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=10, max_length=2000)
    tone: Literal["professional", "casual", "energetic", "educational", "inspirational"] = "professional"
    include_hook: bool = True
    include_cta: bool = True
    target_duration_seconds: Optional[int] = Field(default=600, ge=30, le=7200)
    fallback_user_id: Optional[str] = None


class StoryboardGenerateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=100)
    script_id: str = Field(min_length=1, max_length=100)
    shot_count_target: int = Field(default=10, ge=3, le=50)
    fallback_user_id: Optional[str] = None


class ThumbnailGenerateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=100)
    video_title: str = Field(min_length=1, max_length=200)
    concept_count: int = Field(default=3, ge=1, le=5)
    style: Literal["bold", "minimal", "professional", "playful", "cinematic"] = "bold"
    text_overlay: Optional[str] = Field(default=None, max_length=50)
    fallback_user_id: Optional[str] = None


class PlatformOptimizeRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=100)
    script_id: str = Field(min_length=1, max_length=100)
    platform: Literal["youtube", "tiktok", "instagram", "linkedin"]
    fallback_user_id: Optional[str] = None


# ── USAGE TRACKING ──

async def _track_usage(owner_id: str, action: str, plan: str) -> None:
    """Track user action for analytics."""
    day_key = _today_key()
    user_id = _extract_user_id(owner_id)
    
    await db[COLL_ANALYTICS].update_one(
        {"owner_id": owner_id, "day_key": day_key},
        {
            "$set": {
                "owner_id": owner_id,
                "user_id": user_id,
                "day_key": day_key,
                "plan": plan,
                "updated_at": _now_iso()
            },
            "$inc": {f"usage.{action}": 1},
            "$setOnInsert": {"created_at": _now_iso()}
        },
        upsert=True
    )


async def _get_usage(owner_id: str) -> Dict[str, int]:
    """Get today's usage for owner."""
    day_key = _today_key()
    doc = await db[COLL_ANALYTICS].find_one(
        {"owner_id": owner_id, "day_key": day_key},
        {"_id": 0, "usage": 1}
    )
    return doc.get("usage", {}) if doc else {}


async def _check_daily_limit(owner_id: str, plan: str, action: str) -> None:
    """Check if user has exceeded daily limit for action."""
    limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
    limit_key = f"{action}_per_day"
    
    if limit_key not in limits:
        return  # No limit for this action
    
    limit = limits[limit_key]
    if limit == -1:  # Unlimited
        return
    
    usage = await _get_usage(owner_id)
    current = usage.get(action, 0)
    
    if current >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily {action.replace('_', ' ')} limit reached ({limit}). Upgrade for more."
        )


async def _check_monthly_limit(owner_id: str, plan: str, action: str) -> None:
    """Check if user has exceeded monthly limit for action."""
    limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
    limit_key = f"{action}_per_month"
    
    if limit_key not in limits:
        return
    
    limit = limits[limit_key]
    if limit == -1:  # Unlimited
        return
    
    month_key = _month_key()
    count = await db[COLL_PROJECTS].count_documents({
        "owner_id": owner_id,
        "created_at": {"$regex": f"^{month_key}"}
    })
    
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly {action.replace('_', ' ')} limit reached ({limit}). Upgrade for more."
        )


# ── AI GENERATION HELPERS ──

async def _generate_script_with_ai(
    prompt: str,
    platform: str,
    video_type: str,
    tone: str,
    target_duration_seconds: int,
    include_hook: bool,
    include_cta: bool
) -> Dict[str, Any]:
    """Generate video script using GPT-4o."""
    
    system_prompt = f"""You are an expert video script writer specializing in {platform} content.
Generate a {video_type} video script with the following requirements:

Platform: {platform}
Target Duration: {target_duration_seconds} seconds (~{target_duration_seconds // 60} minutes)
Tone: {tone}
Include Hook: {include_hook}
Include CTA: {include_cta}

Format your response as a structured script with:
1. HOOK (5-10 seconds) - Attention-grabbing opening
2. INTRO (10-20 seconds) - Who you are and what the video is about
3. MAIN CONTENT (split into 3-5 sections with clear headings)
4. OUTRO (10-15 seconds) - Recap and thank you
5. CTA (5-10 seconds) - Call to action

For each section, provide:
- Section title
- Content (what to say)
- Estimated duration in seconds
- Visual suggestions (what to show on screen)

Make it engaging, platform-appropriate, and optimized for {platform} best practices.
Use clear, conversational language appropriate for the {tone} tone.
"""

    user_prompt = f"""Create a video script for: {prompt}

Make it professional, engaging, and ready to film."""

    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"video-script-{uuid.uuid4().hex[:10]}",
                system_message=system_prompt
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(
            UserMessage(text=user_prompt)
        )
        
        script_content = response.text if hasattr(response, 'text') else str(response)
        
        # Estimate word count and duration
        word_count = len(script_content.split())
        estimated_duration = int(word_count / 2.5)  # ~150 words per minute = 2.5 words/sec
        
        return {
            "content": script_content,
            "word_count": word_count,
            "estimated_duration_seconds": estimated_duration,
            "ai_model": "gpt-4o",
            "generation_context": f"Generated for {platform} {video_type} video"
        }
        
    except Exception as e:
        logger.error(f"Script generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI script generation failed: {str(e)}"
        )


async def _generate_thumbnail_concepts(
    video_title: str,
    style: str,
    text_overlay: Optional[str],
    concept_count: int
) -> List[Dict[str, Any]]:
    """Generate thumbnail concepts using GPT-4o descriptions (placeholder for DALL-E)."""
    
    system_prompt = f"""You are a thumbnail design expert. Generate {concept_count} thumbnail concepts for a video.
Each concept should include:
1. Visual description (what the thumbnail shows)
2. Text overlay suggestion (if not provided)
3. Color scheme (3-5 hex colors)
4. Composition tips

Style: {style}
Video Title: {video_title}
"""

    user_prompt = f"""Generate {concept_count} unique thumbnail concepts for: "{video_title}"
Text overlay: {text_overlay or "Suggest effective text"}

Each concept should be distinct and optimized for high click-through rates."""

    try:
        chat = (
            LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"video-thumb-{uuid.uuid4().hex[:10]}",
                system_message=system_prompt
            )
            .with_model("openai", "gpt-4o")
        )
        response = await chat.send_message(
            UserMessage(text=user_prompt)
        )
        
        concepts_text = response.text if hasattr(response, 'text') else str(response)
        
        # Parse into structured concepts (simplified for now)
        concepts = []
        for i in range(concept_count):
            concepts.append({
                "concept_id": f"con_{uuid.uuid4().hex[:8]}",
                "title": f"Concept {i+1}",
                "description": concepts_text,  # In production, parse individual concepts
                "text_overlay": text_overlay or video_title[:30],
                "color_scheme": ["#FF6B6B", "#4ECDC4", "#1A535C"],  # Default colors
                "style": style,
                "ai_generated_preview_url": None,  # Would use DALL-E in production
                "selected": i == 0
            })
        
        return concepts
        
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI thumbnail generation failed: {str(e)}"
        )


# ── ENDPOINTS ──

@router.get("/bootstrap")
async def video_studio_bootstrap(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
):
    """Initialize Video Creator Studio with user's projects, limits, and features."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    plan = await _get_user_plan(user)
    
    # Fetch user's projects
    projects = await db[COLL_PROJECTS].find(
        {"owner_id": owner_id},
        {"_id": 0}
    ).sort("updated_at", -1).limit(50).to_list(50)
    
    # Get usage stats
    usage = await _get_usage(owner_id)
    
    # Get limits for plan
    limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
    
    # Platform presets
    platform_presets = [
        {
            "id": "youtube",
            "name": "YouTube",
            "description": "Long-form content, tutorials, vlogs",
            "optimal_duration": "8-15 minutes",
            "aspect_ratio": "16:9"
        },
        {
            "id": "tiktok",
            "name": "TikTok",
            "description": "Short-form viral content",
            "optimal_duration": "15-60 seconds",
            "aspect_ratio": "9:16"
        },
        {
            "id": "instagram",
            "name": "Instagram Reels",
            "description": "Short engaging clips",
            "optimal_duration": "15-90 seconds",
            "aspect_ratio": "9:16"
        },
        {
            "id": "linkedin",
            "name": "LinkedIn",
            "description": "Professional insights, thought leadership",
            "optimal_duration": "1-3 minutes",
            "aspect_ratio": "16:9 or 1:1"
        }
    ]
    
    # Script templates
    templates = [
        {"id": "tutorial", "name": "Tutorial / How-To", "description": "Step-by-step instructional content"},
        {"id": "vlog", "name": "Vlog", "description": "Personal narrative and storytelling"},
        {"id": "review", "name": "Product Review", "description": "Detailed product analysis"},
        {"id": "educational", "name": "Educational", "description": "Informative deep-dive content"},
        {"id": "promotional", "name": "Promotional", "description": "Marketing and sales content"}
    ]
    
    return {
        "success": True,
        "plan": plan,
        "limits": limits,
        "usage": usage,
        "projects": projects,
        "project_count": len(projects),
        "platform_presets": platform_presets,
        "templates": templates,
        "features": {
            "script_generation": True,
            "storyboard_builder": plan in ["basic", "premium", "admin"],
            "thumbnail_designer": plan in ["basic", "premium", "admin"],
            "platform_optimizer": plan in ["basic", "premium", "admin"],
            "export_pdf": True,
            "export_markdown": plan in ["basic", "premium", "admin"],
            "export_notion": plan in ["premium", "admin"],
            "ab_testing": plan in ["premium", "admin"],
            "analytics": plan in ["premium", "admin"]
        }
    }


@router.post("/projects/create")
async def create_project(payload: ProjectCreateRequest, request: Request):
    """Create a new video project."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    
    # Check monthly project limit
    await _check_monthly_limit(owner_id, plan, "projects")
    
    project_id = f"vcp_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    
    project = {
        "project_id": project_id,
        "owner_id": owner_id,
        "title": payload.title,
        "description": payload.description,
        "platform": payload.platform,
        "video_type": payload.video_type,
        "status": "draft",
        "target_duration_seconds": payload.target_duration_seconds,
        "target_audience": payload.target_audience,
        "production_deadline": payload.production_deadline,
        "script_id": None,
        "storyboard_id": None,
        "checklist_id": None,
        "thumbnail_id": None,
        "optimization_id": None,
        "metadata": {},
        "created_at": now,
        "updated_at": now
    }
    
    await db[COLL_PROJECTS].insert_one(project)
    await _track_usage(owner_id, "projects_created", plan)
    
    # Remove MongoDB _id from response
    project.pop("_id", None)
    
    return {
        "success": True,
        "project": project,
        "message": f"Project '{payload.title}' created successfully"
    }


@router.get("/projects")
async def list_projects(
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None)
):
    """List user's video projects."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    query = {"owner_id": owner_id}
    if status:
        query["status"] = status
    
    projects = await db[COLL_PROJECTS].find(
        query,
        {"_id": 0}
    ).sort("updated_at", -1).skip(offset).limit(limit).to_list(limit)
    
    total = await db[COLL_PROJECTS].count_documents(query)
    
    return {
        "success": True,
        "projects": projects,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
):
    """Get single project details."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    project = await db[COLL_PROJECTS].find_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Fetch associated script if exists
    script = None
    if project.get("script_id"):
        script = await db[COLL_SCRIPTS].find_one(
            {"script_id": project["script_id"]},
            {"_id": 0}
        )
    
    # Fetch storyboard if exists
    storyboard = None
    if project.get("storyboard_id"):
        storyboard = await db[COLL_STORYBOARDS].find_one(
            {"storyboard_id": project["storyboard_id"]},
            {"_id": 0}
        )
    
    # Fetch thumbnails if exists
    thumbnails = None
    if project.get("thumbnail_id"):
        thumbnails = await db[COLL_THUMBNAILS].find_one(
            {"thumbnail_id": project["thumbnail_id"]},
            {"_id": 0}
        )
    
    return {
        "success": True,
        "project": project,
        "script": script,
        "storyboard": storyboard,
        "thumbnails": thumbnails
    }


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
):
    """Update project details."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify ownership
    existing = await db[COLL_PROJECTS].find_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"_id": 0, "project_id": 1}
    )
    
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Build update dict
    update_data = {"updated_at": _now_iso()}
    if payload.title:
        update_data["title"] = payload.title
    if payload.description is not None:
        update_data["description"] = payload.description
    if payload.status:
        update_data["status"] = payload.status
    if payload.platform:
        update_data["platform"] = payload.platform
    if payload.target_duration_seconds:
        update_data["target_duration_seconds"] = payload.target_duration_seconds
    if payload.production_deadline is not None:
        update_data["production_deadline"] = payload.production_deadline
    
    await db[COLL_PROJECTS].update_one(
        {"project_id": project_id},
        {"$set": update_data}
    )
    
    return {
        "success": True,
        "message": "Project updated successfully"
    }


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    request: Request,
    fallback_user_id: Optional[str] = Query(default=None),
):
    """Delete a project and all associated data."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    # Verify ownership
    project = await db[COLL_PROJECTS].find_one(
        {"project_id": project_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Delete project and associated data
    await db[COLL_PROJECTS].delete_one({"project_id": project_id})
    
    if project.get("script_id"):
        await db[COLL_SCRIPTS].delete_many({"project_id": project_id})
    if project.get("storyboard_id"):
        await db[COLL_STORYBOARDS].delete_many({"project_id": project_id})
    if project.get("thumbnail_id"):
        await db[COLL_THUMBNAILS].delete_many({"project_id": project_id})
    
    return {
        "success": True,
        "message": f"Project '{project['title']}' deleted successfully"
    }


@router.post("/scripts/generate")
async def generate_script(payload: ScriptGenerateRequest, request: Request):
    """Generate AI-powered video script using GPT-4o."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    
    # Check daily script generation limit
    await _check_daily_limit(owner_id, plan, "scripts")
    
    # Verify project ownership
    project = await db[COLL_PROJECTS].find_one(
        {"project_id": payload.project_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Generate script using AI
    script_data = await _generate_script_with_ai(
        prompt=payload.prompt,
        platform=project["platform"],
        video_type=project["video_type"],
        tone=payload.tone,
        target_duration_seconds=payload.target_duration_seconds or project["target_duration_seconds"],
        include_hook=payload.include_hook,
        include_cta=payload.include_cta
    )
    
    # Check word count limit for plan
    limits = TIER_LIMITS.get(plan, TIER_LIMITS["free"])
    max_length = limits.get("max_script_length", 500)
    if max_length != -1 and script_data["word_count"] > max_length:
        script_data["content"] = " ".join(script_data["content"].split()[:max_length])
        script_data["word_count"] = max_length
        script_data["truncated"] = True
    
    script_id = f"vcs_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    
    script = {
        "script_id": script_id,
        "project_id": payload.project_id,
        "owner_id": owner_id,
        "version": 1,
        "status": "draft",
        "platform": project["platform"],
        "content": script_data["content"],
        "word_count": script_data["word_count"],
        "estimated_duration_seconds": script_data["estimated_duration_seconds"],
        "tone": payload.tone,
        "include_hook": payload.include_hook,
        "include_cta": payload.include_cta,
        "ai_generation_context": script_data.get("generation_context", ""),
        "ai_model": script_data.get("ai_model", "gpt-4o"),
        "created_at": now,
        "updated_at": now
    }
    
    await db[COLL_SCRIPTS].insert_one(script)
    
    # Remove MongoDB _id from response
    script.pop("_id", None)
    
    # Link script to project
    await db[COLL_PROJECTS].update_one(
        {"project_id": payload.project_id},
        {"$set": {"script_id": script_id, "updated_at": now}}
    )
    
    await _track_usage(owner_id, "scripts_generated", plan)
    
    return {
        "success": True,
        "script": script,
        "message": "Script generated successfully"
    }


@router.post("/thumbnails/generate")
async def generate_thumbnails(payload: ThumbnailGenerateRequest, request: Request):
    """Generate thumbnail concepts using AI."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    plan = await _get_user_plan(user)
    
    # Check daily thumbnail generation limit
    await _check_daily_limit(owner_id, plan, "thumbnails")
    
    # Verify project ownership
    project = await db[COLL_PROJECTS].find_one(
        {"project_id": payload.project_id, "owner_id": owner_id},
        {"_id": 0}
    )
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Generate thumbnail concepts
    concepts = await _generate_thumbnail_concepts(
        video_title=payload.video_title,
        style=payload.style,
        text_overlay=payload.text_overlay,
        concept_count=payload.concept_count
    )
    
    thumbnail_id = f"vct_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    
    thumbnail_doc = {
        "thumbnail_id": thumbnail_id,
        "project_id": payload.project_id,
        "owner_id": owner_id,
        "video_title": payload.video_title,
        "style": payload.style,
        "concepts": concepts,
        "created_at": now,
        "updated_at": now
    }
    
    await db[COLL_THUMBNAILS].insert_one(thumbnail_doc)
    
    # Remove MongoDB _id from response
    thumbnail_doc.pop("_id", None)
    
    # Link to project
    await db[COLL_PROJECTS].update_one(
        {"project_id": payload.project_id},
        {"$set": {"thumbnail_id": thumbnail_id, "updated_at": now}}
    )
    
    await _track_usage(owner_id, "thumbnails_generated", plan)
    
    return {
        "success": True,
        "thumbnails": thumbnail_doc,
        "message": f"{len(concepts)} thumbnail concepts generated"
    }


@router.get("/health")
async def video_studio_health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "feature": FEATURE_NAME,
        "feature_id": FEATURE_ID
    }
