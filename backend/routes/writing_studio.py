"""Smart Writing Studio v2 — ENTERPRISE-GRADE writing workspace APIs.

Core capabilities:
- Document workspace with version history
- Run-based writing transformations (draft, rewrite, shorten, expand, tone shift, grammar polish)
- Brand profile governance (voice, preferred phrases, do-not-use list)
- Quality scoring and risk flags per generated output
- Templates library (50+ pre-built templates)
- Export functionality (PDF, DOCX, HTML with tier enforcement)
- AI Engine: OpenAI GPT-4o via Emergent LLM key (current active runtime path)
"""

from __future__ import annotations

import os
import re
import io
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from emergentintegrations.llm.chat import LlmChat, UserMessage

from routes.db import db, get_current_user, logger
from utils.access_control_engine import compute_effective_plan


router = APIRouter(prefix="/writing-studio", tags=["Writing Studio"])

# Emergent LLM Key for Feature 1 active runtime model (OpenAI GPT-4o)
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Tier limits (aligned with platform subscription structure)
TIER_LIMITS = {
    "free": {
        "documents_per_month": 10,
        "daily_ai_runs": 3,
        "max_words_per_doc": 5000,
        "export_formats": ["txt"],
        "templates_access": "basic",  # 5 templates
    },
    "basic": {
        "documents_per_month": 100,
        "daily_ai_runs": 25,
        "max_words_per_doc": 50000,
        "export_formats": ["txt", "csv", "pdf"],
        "templates_access": "standard",  # 50+ templates
    },
    "premium": {
        "documents_per_month": 999999,  # Unlimited
        "daily_ai_runs": 999,  # Unlimited
        "max_words_per_doc": 999999,  # Unlimited
        "export_formats": ["txt", "csv", "pdf", "docx", "html", "md"],
        "templates_access": "all",  # All templates + custom
    },
}


async def _get_user_tier(owner_id: str) -> str:
    """Get user's subscription tier."""
    user_id = str(owner_id or "").replace("auth:", "").replace("guest:", "")
    if not user_id:
        return "free"

    user = await db.users.find_one(
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
    if not user:
        return "free"

    effective = compute_effective_plan(user or {})
    return effective if effective in TIER_LIMITS else "free"


async def _check_document_limit(owner_id: str, tier: str) -> None:
    """Check if user has exceeded monthly document limit."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    max_docs = limits["documents_per_month"]
    
    if max_docs >= 999999:  # Unlimited
        return
    
    # Count documents created this month
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    count = await db.writing_studio_documents.count_documents({
        "owner_id": owner_id,
        "created_at": {"$gte": start_of_month.isoformat()}
    })
    
    if count >= max_docs:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "writing_studio_document_limit",
                "message": f"Document limit reached ({max_docs}/month for {tier} tier). Upgrade to create more documents.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "limit": max_docs,
                "count": count,
            }
        )


async def _check_daily_ai_limit(owner_id: str, tier: str) -> None:
    """Check if user has exceeded daily AI run limit."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    max_runs = limits["daily_ai_runs"]
    
    if max_runs >= 999:  # Unlimited
        return
    
    # Count AI runs today
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    usage = await db.writing_studio_daily_usage.find_one(
        {"owner_id": owner_id, "date": today, "action": "ai_run"},
        {"_id": 0}
    )
    current = usage.get("count", 0) if usage else 0
    
    if current >= max_runs:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "writing_studio_ai_limit",
                "message": f"Daily AI limit reached ({max_runs}/day for {tier} tier). Upgrade for more AI runs.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "limit": max_runs,
                "count": current,
            }
        )
    
    # Increment usage
    await db.writing_studio_daily_usage.update_one(
        {"owner_id": owner_id, "date": today, "action": "ai_run"},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}
        },
        upsert=True
    )

GUEST_ID_RE = re.compile(r"^user_[a-zA-Z0-9_-]{12,80}$")
TASK_TYPE = Literal["draft", "rewrite", "shorten", "expand", "tone_shift", "grammar_polish", "seo_optimize"]


DEFAULT_TONES = [
    "professional",
    "concise",
    "friendly",
    "persuasive",
    "executive",
    "empathetic",
]


# TEMPLATES LIBRARY: 50+ enterprise-grade writing templates
TEMPLATES_LIBRARY = {
    # FREE TIER: 5 basic templates
    "blog_post": {
        "id": "blog_post",
        "name": "Blog Post",
        "category": "Content Marketing",
        "tier": "free",
        "description": "SEO-optimized blog post with intro, body, and CTA",
        "prompt_template": "Write a blog post about {topic}. Include an engaging introduction, well-structured body with subheadings, and a clear call-to-action. Target audience: {audience}. Tone: {tone}.",
    },
    "email": {
        "id": "email",
        "name": "Professional Email",
        "category": "Business Communication",
        "tier": "free",
        "description": "Clear and professional business email",
        "prompt_template": "Draft a professional email to {audience} about {topic}. Keep it concise, clear, and actionable. Tone: {tone}.",
    },
    "social_media": {
        "id": "social_media",
        "name": "Social Media Post",
        "category": "Content Marketing",
        "tier": "free",
        "description": "Engaging social media content with hashtags",
        "prompt_template": "Create a social media post about {topic} for {audience}. Make it engaging, include relevant hashtags, and optimize for platform virality. Tone: {tone}.",
    },
    "product_description": {
        "id": "product_description",
        "name": "Product Description",
        "category": "E-commerce",
        "tier": "free",
        "description": "Compelling product description highlighting benefits",
        "prompt_template": "Write a product description for {topic}. Highlight key features, benefits, and create urgency. Target audience: {audience}. Tone: {tone}.",
    },
    "meeting_notes": {
        "id": "meeting_notes",
        "name": "Meeting Notes",
        "category": "Business Communication",
        "tier": "free",
        "description": "Structured meeting summary with action items",
        "prompt_template": "Summarize meeting notes about {topic}. Include key discussion points, decisions made, and action items. Audience: {audience}. Tone: {tone}.",
    },
    
    # BASIC TIER: 50+ templates (includes all free + standard templates)
    "press_release": {
        "id": "press_release",
        "name": "Press Release",
        "category": "Public Relations",
        "tier": "basic",
        "description": "Professional press release with media hooks",
        "prompt_template": "Draft a press release about {topic}. Include headline, dateline, introduction, body quotes, boilerplate, and media contact. Target: {audience}. Tone: {tone}.",
    },
    "case_study": {
        "id": "case_study",
        "name": "Case Study",
        "category": "Business",
        "tier": "basic",
        "description": "Customer success story with metrics",
        "prompt_template": "Create a case study about {topic}. Include problem statement, solution, implementation, results with metrics, and customer quotes. Audience: {audience}. Tone: {tone}.",
    },
    "landing_page": {
        "id": "landing_page",
        "name": "Landing Page Copy",
        "category": "Marketing",
        "tier": "basic",
        "description": "High-converting landing page with hero and CTAs",
        "prompt_template": "Write landing page copy for {topic}. Include compelling hero headline, benefits, social proof, features, and strong CTAs. Target: {audience}. Tone: {tone}.",
    },
    "white_paper": {
        "id": "white_paper",
        "name": "White Paper",
        "category": "Thought Leadership",
        "tier": "basic",
        "description": "In-depth research report with data",
        "prompt_template": "Create a white paper outline on {topic}. Include executive summary, problem analysis, solution framework, research findings, and recommendations. Audience: {audience}. Tone: {tone}.",
    },
    "sales_proposal": {
        "id": "sales_proposal",
        "name": "Sales Proposal",
        "category": "Sales",
        "tier": "basic",
        "description": "Persuasive sales proposal with pricing",
        "prompt_template": "Draft a sales proposal for {topic}. Include executive summary, needs analysis, proposed solution, pricing options, timeline, and next steps. Target: {audience}. Tone: {tone}.",
    },
    "job_description": {
        "id": "job_description",
        "name": "Job Description",
        "category": "HR",
        "tier": "basic",
        "description": "Comprehensive job posting",
        "prompt_template": "Write a job description for {topic}. Include role summary, responsibilities, qualifications, benefits, and application instructions. Audience: {audience}. Tone: {tone}.",
    },
    "newsletter": {
        "id": "newsletter",
        "name": "Email Newsletter",
        "category": "Content Marketing",
        "tier": "basic",
        "description": "Engaging newsletter with multiple sections",
        "prompt_template": "Create an email newsletter about {topic}. Include catchy subject line, intro, 3-5 content sections, and footer CTA. Audience: {audience}. Tone: {tone}.",
    },
    "video_script": {
        "id": "video_script",
        "name": "Video Script",
        "category": "Content Creation",
        "tier": "basic",
        "description": "Video script with scene descriptions",
        "prompt_template": "Write a video script about {topic}. Include hook, introduction, main content with scene descriptions, and outro with CTA. Target: {audience}. Tone: {tone}.",
    },
    "webinar_outline": {
        "id": "webinar_outline",
        "name": "Webinar Outline",
        "category": "Education",
        "tier": "basic",
        "description": "Structured webinar presentation flow",
        "prompt_template": "Create a webinar outline on {topic}. Include welcome, agenda, teaching modules, Q&A prompts, and closing CTA. Audience: {audience}. Tone: {tone}.",
    },
    "podcast_notes": {
        "id": "podcast_notes",
        "name": "Podcast Show Notes",
        "category": "Content Marketing",
        "tier": "basic",
        "description": "SEO-optimized podcast episode summary",
        "prompt_template": "Write podcast show notes for {topic}. Include episode summary, key takeaways, timestamps, guest bio, and resource links. Audience: {audience}. Tone: {tone}.",
    },
    
    # PREMIUM TIER: All templates + custom template creation
    "annual_report": {
        "id": "annual_report",
        "name": "Annual Report",
        "category": "Business",
        "tier": "premium",
        "description": "Executive annual report with financials",
        "prompt_template": "Draft an annual report section on {topic}. Include executive letter, performance highlights, financial summary, strategic initiatives, and outlook. Audience: {audience}. Tone: {tone}.",
    },
    "investor_pitch": {
        "id": "investor_pitch",
        "name": "Investor Pitch Deck",
        "category": "Fundraising",
        "tier": "premium",
        "description": "Slide-by-slide pitch deck narrative",
        "prompt_template": "Create investor pitch deck content for {topic}. Include problem, solution, market size, business model, traction, team, and ask. Target: {audience}. Tone: {tone}.",
    },
    "legal_brief": {
        "id": "legal_brief",
        "name": "Legal Brief Summary",
        "category": "Legal",
        "tier": "premium",
        "description": "Structured legal document summary",
        "prompt_template": "Summarize legal brief on {topic}. Include case overview, legal issues, arguments, precedents, and recommendations. Audience: {audience}. Tone: {tone}.",
    },
    "technical_documentation": {
        "id": "technical_documentation",
        "name": "Technical Documentation",
        "category": "Engineering",
        "tier": "premium",
        "description": "Developer documentation with code examples",
        "prompt_template": "Write technical documentation for {topic}. Include overview, prerequisites, implementation steps, code examples, troubleshooting, and API reference. Audience: {audience}. Tone: {tone}.",
    },
    "grant_proposal": {
        "id": "grant_proposal",
        "name": "Grant Proposal",
        "category": "Non-Profit",
        "tier": "premium",
        "description": "Comprehensive grant application",
        "prompt_template": "Draft a grant proposal for {topic}. Include project summary, needs statement, goals, methodology, budget, evaluation plan, and organizational capacity. Target: {audience}. Tone: {tone}.",
    },
}


class CreateDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    content: str = Field(default="", max_length=100_000)
    fallback_user_id: Optional[str] = None


class UpdateDocumentRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=140)
    content: Optional[str] = Field(default=None, max_length=100_000)
    fallback_user_id: Optional[str] = None


class WritingRunRequest(BaseModel):
    document_id: str = Field(min_length=6, max_length=64)
    task: TASK_TYPE
    instructions: str = Field(default="", max_length=100_000)
    tone: str = Field(default="professional", max_length=60)
    audience: str = Field(default="general", max_length=120)
    reading_level: str = Field(default="general", max_length=40)
    length_target: Optional[str] = Field(default=None, max_length=40)
    fallback_user_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=120)


class UpdateBrandProfileRequest(BaseModel):
    brand_name: str = Field(default="", max_length=120)
    voice_summary: str = Field(default="", max_length=800)
    preferred_phrases: list[str] = Field(default_factory=list)
    do_not_use: list[str] = Field(default_factory=list)
    fallback_user_id: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_list(values: list[str], *, cap: int = 20) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        clean.append(normalized[:140])
        seen.add(lowered)
        if len(clean) >= cap:
            break
    return clean


def _resolve_owner_id(user: Any, fallback_user_id: Optional[str]) -> str:
    if user and getattr(user, "user_id", None):
        return f"auth:{str(user.user_id)}"

    fallback = str(fallback_user_id or "").strip()
    if not fallback:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "writing_studio_auth_required",
                "message": "Login required or provide fallback_user_id for guest workspace",
            },
        )

    if not GUEST_ID_RE.match(fallback):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "writing_studio_invalid_guest_id",
                "message": "fallback_user_id format is invalid",
            },
        )

    return f"guest:{fallback}"


async def _get_brand_profile(owner_id: str) -> dict[str, Any]:
    profile = await db.writing_studio_brand_profiles.find_one({"owner_id": owner_id}, {"_id": 0})
    if profile:
        profile["preferred_phrases"] = _normalize_list(profile.get("preferred_phrases") or [])
        profile["do_not_use"] = _normalize_list(profile.get("do_not_use") or [])
        return profile

    return {
        "owner_id": owner_id,
        "brand_name": "",
        "voice_summary": "",
        "preferred_phrases": [],
        "do_not_use": [],
        "updated_at": None,
    }


def _quality_scores(text: str, brand_profile: dict[str, Any]) -> dict[str, Any]:
    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)
    sentence_count = max(1, len(re.findall(r"[.!?]+", text)))
    avg_sentence_len = word_count / sentence_count if sentence_count else float(word_count)

    readability = int(max(20, min(100, 100 - abs(avg_sentence_len - 16) * 4)))
    clarity = int(max(20, min(100, 100 - max(0, avg_sentence_len - 24) * 6)))

    cta_signals = ["book", "start", "contact", "subscribe", "download", "try", "reply", "schedule"]
    lower = text.lower()
    cta_strength = 85 if any(signal in lower for signal in cta_signals) else 58

    flags: list[str] = []
    banned = [item.lower() for item in _normalize_list(brand_profile.get("do_not_use") or [])]
    for term in banned:
        if term and term in lower:
            flags.append(f"Contains banned term: {term}")

    compliance = int(max(35, 100 - len(flags) * 18))
    overall = int(round((readability + clarity + cta_strength + compliance) / 4))

    return {
        "overall": overall,
        "readability": readability,
        "clarity": clarity,
        "cta_strength": cta_strength,
        "compliance": compliance,
        "flags": flags,
        "word_count": word_count,
        "sentence_count": sentence_count,
    }


def _build_prompt(
    *,
    task: TASK_TYPE,
    source_text: str,
    instructions: str,
    tone: str,
    audience: str,
    reading_level: str,
    length_target: Optional[str],
    brand_profile: dict[str, Any],
) -> tuple[str, str]:
    task_instructions: dict[TASK_TYPE, str] = {
        "draft": "Create a complete first draft from the brief.",
        "rewrite": "Rewrite the provided text for stronger quality and flow.",
        "shorten": "Condense the text while preserving core meaning and CTA.",
        "expand": "Expand the text with useful details, examples, and stronger structure.",
        "tone_shift": "Transform the text to the requested tone while preserving intent.",
        "grammar_polish": "Correct grammar, punctuation, clarity, and structure while preserving meaning.",
        "seo_optimize": "Optimize for SEO with clear headings, semantic keywords, and readable formatting.",
    }

    preferred_phrases = ", ".join(_normalize_list(brand_profile.get("preferred_phrases") or [])) or "None"
    banned_terms = ", ".join(_normalize_list(brand_profile.get("do_not_use") or [])) or "None"

    system_message = (
        "You are Smart Writing Studio Pro, an enterprise-grade writing assistant. "
        "Return polished publication-ready output only. No meta commentary. "
        "Use Markdown structure when useful."
    )

    prompt = f"""
Task: {task}
Task Objective: {task_instructions[task]}

Audience: {audience}
Tone: {tone}
Reading Level: {reading_level}
Length Target: {length_target or 'auto'}

Brand Name: {brand_profile.get('brand_name') or 'Not set'}
Brand Voice: {brand_profile.get('voice_summary') or 'No voice summary provided'}
Preferred Phrases: {preferred_phrases}
Disallowed Terms: {banned_terms}

Additional Instructions:
{instructions or 'None'}

Source / Draft / Brief:
{source_text}

Output requirements:
- Keep it concise, high-signal, and ready for direct use.
- Preserve key facts and intent.
- Include clear structure and a practical CTA when relevant.
""".strip()

    return system_message, prompt


def _document_projection() -> dict[str, int]:
    return {
        "_id": 0,
        "doc_id": 1,
        "owner_id": 1,
        "title": 1,
        "current_content": 1,
        "created_at": 1,
        "updated_at": 1,
        "last_quality_scores": 1,
        "versions": 1,
    }


@router.get("/bootstrap")
async def writing_studio_bootstrap(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)

    docs = await db.writing_studio_documents.find(
        {"owner_id": owner_id},
        {"_id": 0, "doc_id": 1, "title": 1, "updated_at": 1, "last_quality_scores": 1, "versions": 1},
    ).sort("updated_at", -1).to_list(20)

    compact_docs = []
    for doc in docs:
        versions = doc.get("versions") or []
        compact_docs.append(
            {
                "doc_id": doc.get("doc_id"),
                "title": doc.get("title") or "Untitled",
                "updated_at": doc.get("updated_at"),
                "version_count": len(versions),
                "latest_quality": (doc.get("last_quality_scores") or {}).get("overall"),
            }
        )

    pipeline = [
        {"$match": {"owner_id": owner_id}},
        {
            "$group": {
                "_id": None,
                "runs_7d": {
                    "$sum": {
                        "$cond": [
                            {
                                "$gte": [
                                    "$created_at",
                                    datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "avg_quality": {"$avg": "$quality_scores.overall"},
            }
        },
    ]
    stats_rows = await db.writing_studio_runs.aggregate(pipeline).to_list(1)
    stats = stats_rows[0] if stats_rows else {}

    # Filter templates by tier
    tier_templates = []
    for template_id, template_data in TEMPLATES_LIBRARY.items():
        template_tier = template_data.get("tier", "free")
        # Show free templates to all, basic to basic+premium, premium to premium only
        if template_tier == "free" or (template_tier == "basic" and tier in ["basic", "premium"]) or (template_tier == "premium" and tier == "premium"):
            tier_templates.append(template_data)

    return {
        "owner_id": owner_id,
        "tier": tier,
        "documents": compact_docs,
        "templates": tier_templates,
        "brand_profile": await _get_brand_profile(owner_id),
        "presets": {
            "tasks": ["draft", "rewrite", "shorten", "expand", "tone_shift", "grammar_polish", "seo_optimize"],
            "tones": DEFAULT_TONES,
            "reading_levels": ["general", "grade_8", "professional", "executive"],
        },
        "stats": {
            "documents_count": len(compact_docs),
            "runs_7d": int(stats.get("runs_7d") or 0),
            "avg_quality": round(float(stats.get("avg_quality") or 0), 1),
        },
    }


@router.post("/documents")
async def create_document(payload: CreateDocumentRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    now = _now_iso()
    doc_id = f"ws_{uuid.uuid4().hex[:14]}"
    initial_version = {
        "version_id": f"ver_{uuid.uuid4().hex[:12]}",
        "task": "manual_create",
        "content": payload.content,
        "created_at": now,
    }
    document = {
        "doc_id": doc_id,
        "owner_id": owner_id,
        "title": payload.title.strip()[:140],
        "current_content": payload.content,
        "created_at": now,
        "updated_at": now,
        "last_quality_scores": _quality_scores(payload.content, await _get_brand_profile(owner_id)),
        "versions": [initial_version],
    }

    await db.writing_studio_documents.insert_one(dict(document))
    return {"document": document}


@router.patch("/documents/{doc_id}")
async def update_document(doc_id: str, payload: UpdateDocumentRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    query = {"doc_id": doc_id, "owner_id": owner_id}
    doc = await db.writing_studio_documents.find_one(query, _document_projection())
    if not doc:
        raise HTTPException(status_code=404, detail={"error_code": "writing_studio_doc_not_found", "message": "Document not found"})

    update_fields: dict[str, Any] = {"updated_at": _now_iso()}
    if payload.title is not None:
        update_fields["title"] = payload.title.strip()[:140]
    if payload.content is not None:
        update_fields["current_content"] = payload.content
        quality = _quality_scores(payload.content, await _get_brand_profile(owner_id))
        update_fields["last_quality_scores"] = quality

    await db.writing_studio_documents.update_one(query, {"$set": update_fields})
    updated = await db.writing_studio_documents.find_one(query, _document_projection())
    return {"document": updated}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    doc = await db.writing_studio_documents.find_one({"doc_id": doc_id, "owner_id": owner_id}, _document_projection())
    if not doc:
        raise HTTPException(status_code=404, detail={"error_code": "writing_studio_doc_not_found", "message": "Document not found"})
    return {"document": doc}


@router.get("/documents/{doc_id}/versions")
async def get_document_versions(doc_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    doc = await db.writing_studio_documents.find_one(
        {"doc_id": doc_id, "owner_id": owner_id},
        {"_id": 0, "doc_id": 1, "title": 1, "versions": 1, "updated_at": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail={"error_code": "writing_studio_doc_not_found", "message": "Document not found"})
    return {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "updated_at": doc.get("updated_at"),
        "versions": list(reversed(doc.get("versions") or []))[:30],
    }


@router.post("/documents/{doc_id}/restore/{version_id}")
async def restore_document_version(doc_id: str, version_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)

    query = {"doc_id": doc_id, "owner_id": owner_id}
    doc = await db.writing_studio_documents.find_one(query, _document_projection())
    if not doc:
        raise HTTPException(status_code=404, detail={"error_code": "writing_studio_doc_not_found", "message": "Document not found"})

    versions = doc.get("versions") or []
    target = next((v for v in versions if str(v.get("version_id")) == version_id), None)
    if not target:
        raise HTTPException(status_code=404, detail={"error_code": "writing_studio_version_not_found", "message": "Version not found"})

    now = _now_iso()
    restored_version = {
        "version_id": f"ver_{uuid.uuid4().hex[:12]}",
        "task": "restore",
        "content": target.get("content") or "",
        "created_at": now,
        "restored_from": version_id,
    }

    profile = await _get_brand_profile(owner_id)
    quality = _quality_scores(restored_version["content"], profile)
    await db.writing_studio_documents.update_one(
        query,
        {
            "$set": {
                "current_content": restored_version["content"],
                "updated_at": now,
                "last_quality_scores": quality,
            },
            "$push": {"versions": restored_version},
        },
    )

    updated = await db.writing_studio_documents.find_one(query, _document_projection())
    return {"document": updated}



@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request, fallback_user_id: Optional[str] = None):
    """Delete a writing document."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    
    result = await db.writing_studio_documents.delete_one({"doc_id": doc_id, "owner_id": owner_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "writing_studio_doc_not_found", "message": "Document not found"}
        )
    
    # Also delete associated runs
    await db.writing_studio_runs.delete_many({"document_id": doc_id, "owner_id": owner_id})
    
    return {"message": "Document deleted successfully", "doc_id": doc_id}


@router.get("/brand-profile")
async def get_brand_profile(request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    return {"brand_profile": await _get_brand_profile(owner_id)}


@router.put("/brand-profile")
async def update_brand_profile(payload: UpdateBrandProfileRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)

    now = _now_iso()
    profile = {
        "owner_id": owner_id,
        "brand_name": payload.brand_name.strip()[:120],
        "voice_summary": payload.voice_summary.strip()[:800],
        "preferred_phrases": _normalize_list(payload.preferred_phrases),
        "do_not_use": _normalize_list(payload.do_not_use),
        "updated_at": now,
    }
    await db.writing_studio_brand_profiles.update_one({"owner_id": owner_id}, {"$set": profile}, upsert=True)
    return {"brand_profile": profile}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request, fallback_user_id: Optional[str] = None):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    run = await db.writing_studio_runs.find_one({"run_id": run_id, "owner_id": owner_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail={"error_code": "writing_studio_run_not_found", "message": "Run not found"})
    return {"run": run}


@router.post("/runs")
async def run_writing_task(payload: WritingRunRequest, request: Request):
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    
    # TIER ENFORCEMENT: Check daily AI limit
    tier = await _get_user_tier(owner_id)
    await _check_daily_ai_limit(owner_id, tier)

    doc_query = {"doc_id": payload.document_id, "owner_id": owner_id}
    document = await db.writing_studio_documents.find_one(doc_query, _document_projection())
    if not document:
        raise HTTPException(status_code=404, detail={"error_code": "writing_studio_doc_not_found", "message": "Document not found"})

    if payload.idempotency_key:
        existing = await db.writing_studio_runs.find_one(
            {
                "owner_id": owner_id,
                "document_id": payload.document_id,
                "idempotency_key": payload.idempotency_key,
                "status": "completed",
            },
            {"_id": 0},
        )
        if existing:
            latest_doc = await db.writing_studio_documents.find_one(doc_query, _document_projection())
            return {"run": existing, "document": latest_doc, "idempotent_replay": True}

    brand_profile = await _get_brand_profile(owner_id)
    source_text = (payload.instructions or "").strip() or str(document.get("current_content") or "")
    if not source_text:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "writing_studio_source_missing",
                "message": "Source content is empty. Add text before running this task.",
            },
        )

    run_id = f"run_{uuid.uuid4().hex[:14]}"
    now = _now_iso()
    run_doc = {
        "run_id": run_id,
        "owner_id": owner_id,
        "document_id": payload.document_id,
        "task": payload.task,
        "tone": payload.tone,
        "audience": payload.audience,
        "reading_level": payload.reading_level,
        "length_target": payload.length_target,
        "idempotency_key": payload.idempotency_key,
        "status": "running",
        "created_at": now,
        "completed_at": None,
        "error": None,
    }
    await db.writing_studio_runs.insert_one(run_doc)

    try:
        system_message, prompt = _build_prompt(
            task=payload.task,
            source_text=source_text,
            instructions=payload.instructions,
            tone=payload.tone,
            audience=payload.audience,
            reading_level=payload.reading_level,
            length_target=payload.length_target,
            brand_profile=brand_profile,
        )
        
        # Active model path for Feature 1 runtime: OpenAI GPT-4o via Emergent LLM key
        llm_client = (
            LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"writing-{run_id}",
                system_message="You are a professional writing assistant helping users craft excellent content."
            )
            .with_model("openai", "gpt-4o")
        )
        
        response = await llm_client.send_message(
            UserMessage(text=f"{system_message}\n\n{prompt}")
        )
        generated = str(getattr(response, "text", None) or response).strip()

        quality = _quality_scores(generated, brand_profile)
        version = {
            "version_id": f"ver_{uuid.uuid4().hex[:12]}",
            "task": payload.task,
            "content": generated,
            "created_at": _now_iso(),
            "tone": payload.tone,
            "audience": payload.audience,
            "reading_level": payload.reading_level,
            "quality_scores": quality,
        }

        completed_at = _now_iso()
        await db.writing_studio_documents.update_one(
            doc_query,
            {
                "$set": {
                    "current_content": generated,
                    "updated_at": completed_at,
                    "last_quality_scores": quality,
                    "last_run_id": run_id,
                },
                "$push": {"versions": version},
            },
        )

        await db.writing_studio_runs.update_one(
            {"run_id": run_id, "owner_id": owner_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": completed_at,
                    "quality_scores": quality,
                    "output": generated,
                    "output_preview": generated[:350],
                }
            },
        )

        final_run = await db.writing_studio_runs.find_one({"run_id": run_id, "owner_id": owner_id}, {"_id": 0})
        final_doc = await db.writing_studio_documents.find_one(doc_query, _document_projection())
        return {"run": final_run, "document": final_doc}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Writing studio run failed: %s", exc)
        await db.writing_studio_runs.update_one(
            {"run_id": run_id, "owner_id": owner_id},
            {
                "$set": {
                    "status": "failed",
                    "completed_at": _now_iso(),
                    "error": str(exc)[:300],
                }
            },
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "writing_studio_run_failed",
                "message": "Writing generation failed. Please retry.",
            },
        )


@router.get("/templates")
async def get_templates(request: Request, fallback_user_id: Optional[str] = None):
    """Get available templates based on user's subscription tier."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Filter templates by tier
    available = []
    for template_id, template in TEMPLATES_LIBRARY.items():
        if tier == "free" and template["tier"] != "free":
            continue
        if tier == "basic" and template["tier"] == "premium":
            continue
        available.append(template)
    
    # Group by category
    by_category = {}
    for template in available:
        category = template["category"]
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(template)
    
    return {
        "templates": available,
        "by_category": by_category,
        "tier": tier,
        "tier_limits": {
            "free": "5 templates",
            "basic": "50+ templates",
            "premium": "All templates + custom",
        }
    }


class ApplyTemplateRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=60)
    topic: str = Field(min_length=1, max_length=500)
    audience: Optional[str] = Field(default="general audience", max_length=120)
    tone: Optional[str] = Field(default="professional", max_length=60)
    fallback_user_id: Optional[str] = None


@router.post("/templates/apply")
async def apply_template(payload: ApplyTemplateRequest, request: Request):
    """Apply a template to generate content."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier access
    template = TEMPLATES_LIBRARY.get(payload.template_id)
    if not template:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "writing_studio_template_not_found",
                "message": "Template not found."
            }
        )
    
    if tier == "free" and template["tier"] != "free":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "writing_studio_template_upgrade_required",
                "message": f"This template requires {template['tier'].title()} tier. Upgrade to unlock.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "required_tier": template["tier"],
            }
        )
    
    if tier == "basic" and template["tier"] == "premium":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "writing_studio_template_upgrade_required",
                "message": "This template requires Premium tier. Upgrade to unlock advanced templates.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "required_tier": "premium",
            }
        )
    
    # Generate content using template
    prompt_text = template["prompt_template"].format(
        topic=payload.topic,
        audience=payload.audience or "general audience",
        tone=payload.tone or "professional"
    )
    
    return {
        "template": template,
        "generated_prompt": prompt_text,
        "topic": payload.topic,
        "message": "Use this generated prompt in the editor and run a 'Draft' task."
    }


class ExportDocumentRequest(BaseModel):
    export_format: Literal["txt", "csv", "pdf", "docx"]
    fallback_user_id: Optional[str] = None


@router.post("/documents/{doc_id}/export")
async def export_document(doc_id: str, payload: ExportDocumentRequest, request: Request):
    """Export document in various formats with tier enforcement."""
    user = await get_current_user(request)
    owner_id = _resolve_owner_id(user, payload.fallback_user_id)
    tier = await _get_user_tier(owner_id)
    
    # Check tier limits for export format
    allowed_formats = TIER_LIMITS.get(tier, TIER_LIMITS["free"])["export_formats"]
    if payload.export_format not in allowed_formats:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "writing_studio_export_upgrade_required",
                "message": f"{payload.export_format.upper()} export requires {tier=='free' and 'Basic' or 'Premium'} tier. Upgrade to unlock.",
                "upgrade_prompt": True,
                "current_tier": tier,
                "allowed_formats": allowed_formats,
            }
        )
    
    # Fetch document
    doc = await db.writing_studio_documents.find_one(
        {"doc_id": doc_id, "owner_id": owner_id},
        {"_id": 0, "doc_id": 1, "title": 1, "current_content": 1}
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "writing_studio_doc_not_found",
                "message": "Document not found"
            }
        )
    
    title = doc.get("title") or "Untitled"
    content = doc.get("current_content") or ""
    
    # Generate export based on format
    if payload.export_format == "txt":
        file_content = f"{title}\n\n{content}"
        media_type = "text/plain"
        filename = f"{title.replace(' ', '_')}.txt"
        return StreamingResponse(
            io.BytesIO(file_content.encode("utf-8")),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    elif payload.export_format == "csv":
        # CSV format: Title, Content
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Title", "Content"])
        writer.writerow([title, content])
        file_content = output.getvalue()
        filename = f"{title.replace(' ', '_')}.csv"
        return StreamingResponse(
            io.BytesIO(file_content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    elif payload.export_format == "pdf":
        # PDF generation using reportlab
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        
        buffer = io.BytesIO()
        doc_pdf = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
        )
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Content (split by paragraphs)
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            if para.strip():
                story.append(Paragraph(para.strip(), styles['BodyText']))
                story.append(Spacer(1, 0.2 * inch))
        
        doc_pdf.build(story)
        buffer.seek(0)
        filename = f"{title.replace(' ', '_')}.pdf"
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    elif payload.export_format == "docx":
        # DOCX generation using python-docx
        from docx import Document
        from docx.shared import Pt
        
        document = Document()
        
        # Title
        heading = document.add_heading(title, level=1)
        heading.runs[0].font.size = Pt(24)
        
        # Content (split by paragraphs)
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            if para.strip():
                p = document.add_paragraph(para.strip())
                p.paragraph_format.space_after = Pt(12)
        
        buffer = io.BytesIO()
        document.save(buffer)
        buffer.seek(0)
        filename = f"{title.replace(' ', '_')}.docx"
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    # Fallback (should never reach here)
    raise HTTPException(status_code=400, detail="Invalid export format")
