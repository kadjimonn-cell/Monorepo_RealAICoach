"""AI Content Studio — Template-based content generation with AI.

Provides pre-built templates for common content types:
  - Social Media Posts (LinkedIn, Twitter/X, Instagram)
  - Email Drafts (Cold outreach, Follow-up, Newsletter)
  - Blog Articles (How-to, Listicle, Opinion)
  - Business Documents (Executive summary, Proposal, Meeting notes)
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Request
from routes.db import db, get_current_user, EMERGENT_LLM_KEY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/content-studio", tags=["Content Studio"])


TEMPLATES = {
    "social_linkedin": {
        "id": "social_linkedin", "name": "LinkedIn Post", "category": "social",
        "icon": "logo-linkedin", "color": "#0A66C2",
        "description": "Professional thought leadership post",
        "prompt_prefix": "Write a professional LinkedIn post about:",
        "fields": [{"key": "topic", "label": "Topic/Theme", "placeholder": "e.g. AI in leadership coaching"}],
        "max_length": 3000,
    },
    "social_twitter": {
        "id": "social_twitter", "name": "Twitter/X Thread", "category": "social",
        "icon": "logo-twitter", "color": "#1DA1F2",
        "description": "Engaging tweet thread (5-7 tweets)",
        "prompt_prefix": "Write a Twitter/X thread (5-7 tweets) about:",
        "fields": [{"key": "topic", "label": "Topic", "placeholder": "e.g. productivity tips for remote workers"}],
        "max_length": 2000,
    },
    "social_instagram": {
        "id": "social_instagram", "name": "Instagram Caption", "category": "social",
        "icon": "logo-instagram", "color": "#E4405F",
        "description": "Engaging caption with hashtags",
        "prompt_prefix": "Write an engaging Instagram caption with relevant hashtags about:",
        "fields": [{"key": "topic", "label": "Topic", "placeholder": "e.g. morning routines for success"}],
        "max_length": 2200,
    },
    "email_cold": {
        "id": "email_cold", "name": "Cold Outreach Email", "category": "email",
        "icon": "mail", "color": "#10B981",
        "description": "Professional cold email that gets responses",
        "prompt_prefix": "Write a professional cold outreach email. Context:",
        "fields": [
            {"key": "recipient_role", "label": "Recipient's Role", "placeholder": "e.g. VP of Engineering at a SaaS company"},
            {"key": "goal", "label": "Your Goal", "placeholder": "e.g. schedule a demo of our product"},
        ],
        "max_length": 1500,
    },
    "email_followup": {
        "id": "email_followup", "name": "Follow-up Email", "category": "email",
        "icon": "mail-open", "color": "#6366F1",
        "description": "Polite and effective follow-up",
        "prompt_prefix": "Write a polite follow-up email. Context:",
        "fields": [{"key": "context", "label": "Original Context", "placeholder": "e.g. sent a proposal last week, no response yet"}],
        "max_length": 1000,
    },
    "email_newsletter": {
        "id": "email_newsletter", "name": "Newsletter Issue", "category": "email",
        "icon": "newspaper", "color": "#F59E0B",
        "description": "Engaging newsletter with sections",
        "prompt_prefix": "Write an email newsletter issue with intro, 3 main sections, and a CTA. Topic:",
        "fields": [{"key": "topic", "label": "Newsletter Topic", "placeholder": "e.g. This week in AI coaching"}],
        "max_length": 4000,
    },
    "blog_howto": {
        "id": "blog_howto", "name": "How-To Article", "category": "blog",
        "icon": "document-text", "color": "#0EA5E9",
        "description": "Step-by-step instructional article",
        "prompt_prefix": "Write a detailed how-to article with introduction, step-by-step instructions, and conclusion:",
        "fields": [{"key": "topic", "label": "Article Topic", "placeholder": "e.g. How to prepare for a salary negotiation"}],
        "max_length": 6000,
    },
    "blog_listicle": {
        "id": "blog_listicle", "name": "Listicle Article", "category": "blog",
        "icon": "list", "color": "#8B5CF6",
        "description": "Numbered list article (10 items)",
        "prompt_prefix": "Write a listicle article with 10 items, each with a brief explanation:",
        "fields": [{"key": "topic", "label": "List Topic", "placeholder": "e.g. 10 habits of highly effective managers"}],
        "max_length": 5000,
    },
    "doc_exec_summary": {
        "id": "doc_exec_summary", "name": "Executive Summary", "category": "business",
        "icon": "briefcase", "color": "#EF4444",
        "description": "Concise executive summary document",
        "prompt_prefix": "Write a professional executive summary document for:",
        "fields": [{"key": "project", "label": "Project/Topic", "placeholder": "e.g. Q1 2026 AI coaching platform expansion"}],
        "max_length": 3000,
    },
    "doc_meeting_notes": {
        "id": "doc_meeting_notes", "name": "Meeting Notes", "category": "business",
        "icon": "clipboard", "color": "#14B8A6",
        "description": "Structured meeting notes with action items",
        "prompt_prefix": "Write structured meeting notes with attendees, agenda, discussion points, decisions, and action items. Meeting context:",
        "fields": [{"key": "context", "label": "Meeting Context", "placeholder": "e.g. Weekly team sync about product launch timeline"}],
        "max_length": 3000,
    },
}

TEMPLATE_CATEGORIES = [
    {"id": "social", "name": "Social Media", "icon": "share-social", "color": "#3B82F6"},
    {"id": "email", "name": "Emails", "icon": "mail", "color": "#10B981"},
    {"id": "blog", "name": "Blog Articles", "icon": "document-text", "color": "#8B5CF6"},
    {"id": "business", "name": "Business Docs", "icon": "briefcase", "color": "#EF4444"},
]


class GenerateContentRequest(BaseModel):
    template_id: str
    fields: dict
    tone: Optional[str] = "professional"
    language: Optional[str] = "en"


@router.get("/templates")
async def get_templates():
    """Return all available content generation templates grouped by category."""
    return {
        "categories": TEMPLATE_CATEGORIES,
        "templates": list(TEMPLATES.values()),
    }


@router.post("/generate")
async def generate_content(req: GenerateContentRequest, request: Request):
    """Generate content using AI based on the selected template and user inputs."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    template = TEMPLATES.get(req.template_id)
    if not template:
        raise HTTPException(status_code=400, detail="Invalid template_id")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI service unavailable")

    # Build prompt from template and fields
    field_text = "\n".join(f"- {k}: {v}" for k, v in req.fields.items() if v)
    prompt = f"""{template['prompt_prefix']}

{field_text}

Requirements:
- Tone: {req.tone}
- Language: {req.language}
- Maximum length: ~{template['max_length']} characters
- Make it engaging, specific, and actionable
- Include a clear call-to-action where appropriate"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"studio-{uuid.uuid4().hex[:8]}",
            system_message=f"You are an expert content writer for {template['name']} content. Write high-quality, engaging content that's ready to publish. Do not include meta-commentary about the content.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))

        # Save to history
        doc_id = f"studio_{uuid.uuid4().hex[:12]}"
        word_count = len(response.split())
        await db.content_studio_history.insert_one({
            "doc_id": doc_id,
            "user_id": user.user_id,
            "template_id": req.template_id,
            "template_name": template["name"],
            "category": template["category"],
            "fields": req.fields,
            "tone": req.tone,
            "language": req.language,
            "content": response,
            "word_count": word_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "doc_id": doc_id,
            "template_id": req.template_id,
            "template_name": template["name"],
            "content": response,
            "word_count": word_count,
            "char_count": len(response),
        }

    except Exception as e:
        logger.error(f"Content generation failed: {e}")
        raise HTTPException(status_code=500, detail="Content generation failed")


@router.get("/history")
async def get_generation_history(request: Request, limit: int = 20, category: Optional[str] = None):
    """Return user's content generation history."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    query = {"user_id": user.user_id}
    if category:
        query["category"] = category

    items = await db.content_studio_history.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    return {"items": items, "total": len(items)}


@router.delete("/history/{doc_id}")
async def delete_history_item(doc_id: str, request: Request):
    """Delete a content generation history item."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.content_studio_history.delete_one({"doc_id": doc_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True}
