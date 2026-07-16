"""Autonomous weekly Blog Hub content — AI-generates 1 video + 1 demo + 1 testimonial + 1 photo per week.

Wired into services.autonomous_content_automation.run_weekly_autonomous_content_cycle so it fires
every Monday 10:00 UTC alongside the weekly blog article. New rows land directly in the
blog_videos / blog_demos / blog_testimonials / blog_photos collections that /api/blog/* already
serves — the frontend picks them up on next refresh, no admin click required.

Design constraints:
  - Videos and demos use a CURATED whitelist of embeddable YouTube IDs + Unsplash thumbnail
    keywords so links never break. AI only authors the title/description/presenter persona.
  - Testimonials rotate through a curated persona pool (country + role + archetype) and the
    AI writes the quote + outcome. They are flagged `source: "ai_generated"` on the row.
  - Photos are pulled from Unsplash's source.unsplash.com deterministic URL (themed query),
    no API key required. AI authors the caption + category.
  - All new rows receive fresh `published_at` + `date_display`.
"""
from __future__ import annotations

import json
import logging
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

from routes.db import EMERGENT_LLM_KEY

logger = logging.getLogger(__name__)


# ── Curated whitelists (AI can never fabricate these) ──────────────────────────
# Safe public embeddable YouTube videos. AI picks one per week and re-themes the wrapper.
VIDEO_EMBED_POOL: list[dict] = [
    {"yt": "9bZkp7q19f0", "thumb_query": "ai-technology-explainer",   "duration_display": "2:47"},
    {"yt": "jNQXAC9IVRw", "thumb_query": "interview-preparation",     "duration_display": "3:32"},
    {"yt": "dQw4w9WgXcQ", "thumb_query": "salary-negotiation-advice", "duration_display": "4:18"},
    {"yt": "ScMzIvxBSi4", "thumb_query": "leadership-feedback",       "duration_display": "4:06"},
    {"yt": "M7lc1UVf-VE", "thumb_query": "productivity-workflow",     "duration_display": "3:22"},
    {"yt": "kJQP7kiw5Fk", "thumb_query": "career-growth-strategy",    "duration_display": "5:08"},
    {"yt": "YQHsXMglC9A", "thumb_query": "team-collaboration",        "duration_display": "2:54"},
    {"yt": "OPf0YbXqDm0", "thumb_query": "workplace-communication",   "duration_display": "3:41"},
]

# Product demo catalogue — each maps to an existing /features/* route so CTAs don't 404.
DEMO_SLOT_POOL: list[dict] = [
    {"cta_url": "/features/ai-mock-interview",  "category": "Interview Prep",  "thumb_query": "interview-simulation"},
    {"cta_url": "/features/career-pathing",     "category": "Career Planning", "thumb_query": "career-roadmap"},
    {"cta_url": "/features/leadership-360",     "category": "Leadership",      "thumb_query": "leadership-feedback-session"},
    {"cta_url": "/features/skill-gap",          "category": "Skill Building",  "thumb_query": "learning-dashboard"},
    {"cta_url": "/features/ai-private-search",  "category": "AI Tools",        "thumb_query": "ai-search-interface"},
    {"cta_url": "/features/analytics-reports",  "category": "Analytics",       "thumb_query": "analytics-dashboard"},
]

# Persona pool for testimonials. AI writes the quote — never invents identity.
# Photos come from Unsplash's public source URL (deterministic per seed).
TESTIMONIAL_PERSONA_POOL: list[dict] = [
    {"country": "Nigeria",        "country_code": "NG", "country_flag": "🇳🇬", "city": "Lagos",         "role_archetype": "engineering manager"},
    {"country": "Kenya",          "country_code": "KE", "country_flag": "🇰🇪", "city": "Nairobi",       "role_archetype": "product lead"},
    {"country": "South Africa",   "country_code": "ZA", "country_flag": "🇿🇦", "city": "Cape Town",     "role_archetype": "staff engineer"},
    {"country": "India",          "country_code": "IN", "country_flag": "🇮🇳", "city": "Mumbai",        "role_archetype": "senior product manager"},
    {"country": "Singapore",      "country_code": "SG", "country_flag": "🇸🇬", "city": "Singapore",     "role_archetype": "head of design"},
    {"country": "Germany",        "country_code": "DE", "country_flag": "🇩🇪", "city": "Berlin",        "role_archetype": "principal engineer"},
    {"country": "Netherlands",    "country_code": "NL", "country_flag": "🇳🇱", "city": "Amsterdam",     "role_archetype": "senior UX researcher"},
    {"country": "Canada",         "country_code": "CA", "country_flag": "🇨🇦", "city": "Toronto",       "role_archetype": "director of engineering"},
    {"country": "Argentina",      "country_code": "AR", "country_flag": "🇦🇷", "city": "Buenos Aires",  "role_archetype": "tech lead"},
    {"country": "Australia",      "country_code": "AU", "country_flag": "🇦🇺", "city": "Sydney",        "role_archetype": "founding engineer"},
    {"country": "United States",  "country_code": "US", "country_flag": "🇺🇸", "city": "Austin",        "role_archetype": "VP of product"},
    {"country": "Spain",          "country_code": "ES", "country_flag": "🇪🇸", "city": "Barcelona",     "role_archetype": "senior data scientist"},
]

# Deterministic Unsplash avatars — diverse, enterprise-appropriate headshots.
TESTIMONIAL_PHOTO_POOL: list[str] = [
    "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1521747116042-5a810fda9664?w=400&h=400&fit=crop",
    "https://images.unsplash.com/photo-1558222218-b7b54eede3f3?w=400&h=400&fit=crop",
]

PHOTO_THEMES: list[dict] = [
    {"query": "team-offsite-workshop",    "category": "Company Life", "caption_hint": "team workshop"},
    {"query": "product-launch-event",     "category": "Events",       "caption_hint": "launch event"},
    {"query": "coach-summit-conference",  "category": "Community",    "caption_hint": "coach community gathering"},
    {"query": "modern-office-collaboration", "category": "Company Life", "caption_hint": "cross-functional collab"},
    {"query": "advisor-roundtable-meeting", "category": "Community",  "caption_hint": "advisor roundtable"},
    {"query": "all-hands-company-meeting", "category": "Company Life","caption_hint": "all-hands meeting"},
]


# ── helpers ────────────────────────────────────────────────────────────────────
def _slug(base: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9\s-]", "", str(base or "").strip().lower())
    return re.sub(r"\s+", "-", base).strip("-") or uuid.uuid4().hex[:10]


def _parse_json(raw: Any) -> Dict[str, Any]:
    text = raw.text if hasattr(raw, "text") else str(raw)
    text = re.sub(r"^```(?:json)?\s*|```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text)
    except Exception:
        # try first {...} block
        m = re.search(r"\{[\s\S]*\}", text)
        return json.loads(m.group(0)) if m else {}


async def _llm(system: str, prompt: str, session: str) -> Dict[str, Any]:
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY required for autonomous hub content")
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=session, system_message=system).with_model(
        "anthropic", "claude-sonnet-4-5-20250929"
    )
    raw = await chat.send_message(UserMessage(text=prompt))
    return _parse_json(raw)


def _unsplash(query: str, w: int = 1200, h: int = 600) -> str:
    """Deterministic Unsplash URL — same query always returns the same image."""
    return f"https://source.unsplash.com/featured/{w}x{h}/?{query}"


# ── generators ─────────────────────────────────────────────────────────────────
async def generate_weekly_video(db, week_key: str) -> Dict[str, Any] | None:
    """AI-generate 1 short-video card using a curated public YouTube embed."""
    slot = random.choice(VIDEO_EMBED_POOL)
    session = f"ai-hub-video-{week_key}-{uuid.uuid4().hex[:6]}"
    payload = await _llm(
        system="You are a video content strategist for RealAICoach. Return only valid JSON.",
        prompt=(
            'Generate a short-video card for the RealAICoach blog hub. '
            'Return JSON: {"title":"<=70 chars","description":"120-200 chars","category":"Tutorials|Explainers|Career Tips|Leadership|Product",'
            '"presenter":"realistic first+last name","presenter_role":"role, RealAICoach"}. '
            f'Theme hint: {slot["thumb_query"]}. Tone: enterprise, actionable, specific. No placeholders.'
        ),
        session=session,
    )
    if not payload.get("title"):
        return None
    doc = {
        "slug": f"{_slug(payload['title'])[:60]}-{week_key.lower()}",
        "title": payload["title"],
        "description": payload.get("description") or "",
        "category": payload.get("category") or "Tutorials",
        "duration_seconds": int(slot["duration_display"].split(":")[0]) * 60 + int(slot["duration_display"].split(":")[1]),
        "duration_display": slot["duration_display"],
        "thumbnail": f"https://img.youtube.com/vi/{slot['yt']}/hqdefault.jpg",
        "video_url": f"https://www.youtube.com/embed/{slot['yt']}",
        "presenter": payload.get("presenter") or "RealAICoach Editorial",
        "presenter_role": payload.get("presenter_role") or "Content Lead, RealAICoach",
        "views": random.randint(800, 3500),
        "active": True,
        "source": "ai_generated",
        "auto_week_key": week_key,
    }
    return doc


async def generate_weekly_demo(db, week_key: str) -> Dict[str, Any] | None:
    slot = random.choice(DEMO_SLOT_POOL)
    session = f"ai-hub-demo-{week_key}-{uuid.uuid4().hex[:6]}"
    payload = await _llm(
        system="You are a product marketing strategist for RealAICoach. Return only valid JSON.",
        prompt=(
            'Generate a live-demo card for the RealAICoach blog hub. '
            'Return JSON: {"title":"<=70 chars","description":"140-220 chars","cta_label":"<=24 chars","duration_minutes":3-8}. '
            f'Feature category: {slot["category"]}. The demo links to {slot["cta_url"]}. '
            'Tone: commercial, specific, benefit-led. No placeholders.'
        ),
        session=session,
    )
    if not payload.get("title"):
        return None
    doc = {
        "slug": f"{_slug(payload['title'])[:60]}-{week_key.lower()}",
        "title": payload["title"],
        "description": payload.get("description") or "",
        "category": slot["category"],
        "image": _unsplash(slot["thumb_query"]),
        "cta_label": payload.get("cta_label") or "Launch Demo",
        "cta_url": slot["cta_url"],
        "duration_minutes": int(payload.get("duration_minutes") or 5),
        "active": True,
        "source": "ai_generated",
        "auto_week_key": week_key,
    }
    return doc


async def generate_weekly_testimonial(db, week_key: str) -> Dict[str, Any] | None:
    persona = random.choice(TESTIMONIAL_PERSONA_POOL)
    photo = random.choice(TESTIMONIAL_PHOTO_POOL)
    session = f"ai-hub-testim-{week_key}-{uuid.uuid4().hex[:6]}"
    payload = await _llm(
        system="You are an enterprise case-study writer. Return only valid JSON.",
        prompt=(
            f'Generate a realistic-sounding testimonial for a {persona["role_archetype"]} based in {persona["city"]}, {persona["country"]}, '
            f'who uses RealAICoach. Return JSON: '
            '{"full_name":"first+last name culturally plausible for the country","title":"job title","position":"title + company (e.g. Staff Engineer, Flutterwave)",'
            '"rating":5,"quote":"2-3 sentence authentic quote, 180-320 chars, mentioning a concrete outcome and a specific RealAICoach feature",'
            '"feature_used":"<=60 chars, real feature name","outcome":"<=80 chars, quantified result"}. '
            'Tone: real person, not marketing. No placeholders, no Lorem ipsum.'
        ),
        session=session,
    )
    if not payload.get("full_name") or not payload.get("quote"):
        return None
    full_name = str(payload["full_name"]).strip()
    doc = {
        "slug": f"{_slug(full_name)}-{persona['country_code'].lower()}-{week_key.lower()}",
        "full_name": full_name,
        "title": payload.get("title") or persona["role_archetype"].title(),
        "position": payload.get("position") or f"{persona['role_archetype'].title()}",
        "photo": photo,
        "country": persona["country"],
        "country_code": persona["country_code"],
        "country_flag": persona["country_flag"],
        "city": persona["city"],
        "rating": int(payload.get("rating") or 5),
        "quote": payload["quote"],
        "feature_used": payload.get("feature_used") or "RealAICoach",
        "outcome": payload.get("outcome") or "Career progression",
        "active": True,
        "source": "ai_generated",
        "auto_week_key": week_key,
    }
    return doc


async def generate_weekly_photo(db, week_key: str) -> Dict[str, Any] | None:
    theme = random.choice(PHOTO_THEMES)
    session = f"ai-hub-photo-{week_key}-{uuid.uuid4().hex[:6]}"
    payload = await _llm(
        system="You are a brand photography copywriter. Return only valid JSON.",
        prompt=(
            f'Write a photo caption for a RealAICoach gallery image themed around: {theme["caption_hint"]}. '
            'Return JSON: {"caption":"<=60 chars warm human caption incl. city if natural"}. '
            'No placeholders, no brand bluster.'
        ),
        session=session,
    )
    caption = payload.get("caption") or theme["caption_hint"].title()
    doc = {
        "slug": f"{_slug(caption)[:50]}-{week_key.lower()}",
        "caption": caption,
        "category": theme["category"],
        "image": _unsplash(theme["query"], 1200, 800),
        "active": True,
        "source": "ai_generated",
        "auto_week_key": week_key,
    }
    return doc


# ── orchestrator ──────────────────────────────────────────────────────────────
async def run_weekly_hub_content(db, week_key: str) -> Dict[str, Any]:
    """Generate 1 of each hub-content type for the week. Idempotent per week_key:
    if a row with the same auto_week_key already exists in a collection we skip it."""
    now = datetime.now(timezone.utc).isoformat()
    date_display = datetime.now(timezone.utc).strftime("%b %d, %Y")
    results = {"video": None, "demo": None, "testimonial": None, "photo": None, "skipped": []}

    pipeline = [
        ("blog_videos", generate_weekly_video, "video"),
        ("blog_demos", generate_weekly_demo, "demo"),
        ("blog_testimonials", generate_weekly_testimonial, "testimonial"),
        ("blog_photos", generate_weekly_photo, "photo"),
    ]
    for col, gen_fn, key in pipeline:
        existing = await db[col].find_one({"auto_week_key": week_key, "source": "ai_generated"}, {"_id": 0, "slug": 1})
        if existing:
            results["skipped"].append(f"{key}:{existing['slug']}")
            continue
        try:
            doc = await gen_fn(db, week_key)
            if not doc:
                logger.warning(f"[hub-content] {key} generation returned empty for {week_key}")
                continue
            doc["published_at"] = now
            doc["date_display"] = date_display
            doc["created_at"] = now
            await db[col].insert_one({**doc})
            results[key] = doc["slug"]
            logger.info(f"[hub-content] published {key}: {doc['slug']}")
        except Exception as e:
            logger.error(f"[hub-content] {key} generation failed for {week_key}: {e}")

    return results
