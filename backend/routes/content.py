from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import re
import hashlib
import time
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
import asyncio
import uuid
import random
from collections import Counter

from .db import db, logger, EMERGENT_LLM_KEY, require_admin
from .auth import get_current_user
from utils.access_control_engine import compute_effective_plan
from utils.pdf_v15_filename import build_pdf_v15_filename
from services.content_library_service import build_library_affinity_profile, merge_library_items_for_page

router = APIRouter()

FEATURE33_ROLLOUT_FLAG_KEY = "feature33_library_enterprise_rollout"


def _stable_rollout_bucket(value: str, salt: str = FEATURE33_ROLLOUT_FLAG_KEY) -> int:
    payload = f"{salt}:{value or ''}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(digest[:8], 16) % 100


def _safe_iso_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _compute_feed_freshness_lag_hours(items: list[dict]) -> Optional[float]:
    if not items:
        return None
    newest = None
    for item in items:
        parsed = _safe_iso_datetime(item.get("added_date"))
        if not parsed:
            continue
        if newest is None or parsed > newest:
            newest = parsed
    if newest is None:
        return None
    lag_hours = max((datetime.now(timezone.utc) - newest).total_seconds() / 3600.0, 0.0)
    return round(lag_hours, 4)


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _derive_adaptive_library_mission_target(
    *,
    mission_daily_stats: dict[str, dict[str, int]],
    today_iso: str,
) -> dict[str, Any]:
    baseline_target = {"opens": 2, "bookmarks": 1}
    baseline = {
        "opens": baseline_target["opens"],
        "bookmarks": baseline_target["bookmarks"],
        "mode": "baseline",
        "history_days_used": 0,
        "active_days": 0,
        "consistency_ratio": 0.0,
        "weighted_avg": {"opens": 0.0, "bookmarks": 0.0},
        "baseline_target": baseline_target,
        "target_delta": {"opens": 0, "bookmarks": 0},
        "change_direction": "stable",
        "change_reason_short": "Goals are using baseline mode until enough activity history is available.",
        "change_reason_detail": [
            "Adaptive mission targets need at least 3 prior activity days.",
            "Keep opening and bookmarking content to unlock personalized goals.",
        ],
    }

    history_days = sorted([day for day in mission_daily_stats.keys() if day < today_iso], reverse=True)[:14]
    if len(history_days) < 3:
        baseline["history_days_used"] = len(history_days)
        return baseline

    active_days = 0
    weighted_open_total = 0.0
    weighted_bookmark_total = 0.0
    weighted_denominator = 0.0

    for index, day_key in enumerate(history_days):
        day_stats = mission_daily_stats.get(day_key) or {}
        opens = max(int(day_stats.get("opens", 0) or 0), 0)
        bookmarks = max(int(day_stats.get("bookmarks", 0) or 0), 0)
        if opens > 0 or bookmarks > 0:
            active_days += 1

        weight = float(max(1, 14 - index))
        weighted_open_total += opens * weight
        weighted_bookmark_total += bookmarks * weight
        weighted_denominator += weight

    if weighted_denominator <= 0:
        baseline["history_days_used"] = len(history_days)
        return baseline

    consistency_ratio = active_days / max(len(history_days), 1)
    weighted_open_avg = weighted_open_total / weighted_denominator
    weighted_bookmark_avg = weighted_bookmark_total / weighted_denominator

    dynamic_opens = _clamp_int(round(weighted_open_avg + 0.4), 1, 6)
    dynamic_bookmarks = _clamp_int(round(weighted_bookmark_avg + 0.2), 0, 3)

    if consistency_ratio >= 0.75:
        dynamic_opens = _clamp_int(dynamic_opens + 1, 1, 6)
    elif consistency_ratio <= 0.35:
        dynamic_opens = _clamp_int(dynamic_opens - 1, 1, 6)
        dynamic_bookmarks = _clamp_int(dynamic_bookmarks - 1, 0, 3)

    if dynamic_bookmarks > dynamic_opens:
        dynamic_bookmarks = dynamic_opens

    delta_opens = int(dynamic_opens - baseline_target["opens"])
    delta_bookmarks = int(dynamic_bookmarks - baseline_target["bookmarks"])
    if delta_opens == 0 and delta_bookmarks == 0:
        change_direction = "stable"
    elif delta_opens >= 0 and delta_bookmarks >= 0 and (delta_opens + delta_bookmarks) > 0:
        change_direction = "increased"
    elif delta_opens <= 0 and delta_bookmarks <= 0 and (delta_opens + delta_bookmarks) < 0:
        change_direction = "decreased"
    else:
        change_direction = "adjusted"

    if change_direction == "increased":
        change_reason_short = (
            "Goals increased because your recent consistency and engagement trend are strong."
            if consistency_ratio >= 0.75
            else "Goals increased based on improving recent open and bookmark activity."
        )
    elif change_direction == "decreased":
        change_reason_short = "Goals decreased to keep momentum achievable while activity recovers."
    elif change_direction == "adjusted":
        change_reason_short = "Goals were rebalanced due to mixed recent activity signals."
    else:
        change_reason_short = "Goals stayed close to baseline because recent activity was stable."

    change_reason_detail = [
        f"Consistency ratio: {round(consistency_ratio * 100, 1)}% active days over {len(history_days)} days.",
        f"Weighted averages — opens: {round(weighted_open_avg, 2)}, bookmarks: {round(weighted_bookmark_avg, 2)}.",
        f"Baseline target was {baseline_target['opens']} opens / {baseline_target['bookmarks']} bookmarks.",
    ]

    return {
        "opens": dynamic_opens,
        "bookmarks": dynamic_bookmarks,
        "mode": "adaptive",
        "history_days_used": len(history_days),
        "active_days": active_days,
        "consistency_ratio": round(consistency_ratio, 4),
        "weighted_avg": {
            "opens": round(weighted_open_avg, 4),
            "bookmarks": round(weighted_bookmark_avg, 4),
        },
        "baseline_target": baseline_target,
        "target_delta": {
            "opens": delta_opens,
            "bookmarks": delta_bookmarks,
        },
        "change_direction": change_direction,
        "change_reason_short": change_reason_short,
        "change_reason_detail": change_reason_detail,
    }


def _build_plan_toned_mission_reason(
    *,
    plan: str,
    change_direction: str,
    history_days_used: int,
    active_days: int,
    consistency_ratio: float,
    weighted_avg: dict[str, float],
    baseline_target: dict[str, int],
) -> dict[str, Any]:
    normalized_plan = str(plan or "free").strip().lower()
    if normalized_plan not in {"free", "basic", "premium"}:
        normalized_plan = "free"

    if normalized_plan == "premium":
        short_map = {
            "increased": "Mission intensity increased to match your strong consistency performance.",
            "decreased": "Mission intensity decreased to protect consistency while engagement stabilizes.",
            "adjusted": "Mission mix was rebalanced from mixed momentum signals in recent sessions.",
            "stable": "Mission intensity remains stable as your recent pattern is balanced.",
        }
    elif normalized_plan == "basic":
        short_map = {
            "increased": "Your goals went up because your recent momentum is improving.",
            "decreased": "Your goals were reduced to keep today realistic while you rebuild rhythm.",
            "adjusted": "Your goals were adjusted because your recent activity trend is mixed.",
            "stable": "Your goals stayed steady because your recent pattern is stable.",
        }
    else:
        short_map = {
            "increased": "Nice progress — your goals increased because you've been consistent lately.",
            "decreased": "No pressure — your goals are lighter today so you can regain momentum.",
            "adjusted": "Your goals changed a bit today based on mixed recent activity.",
            "stable": "You're on a steady path, so today's goals stay close to normal.",
        }

    direction_key = (
        str(change_direction or "stable").strip().lower()
        if str(change_direction or "").strip().lower() in {"increased", "decreased", "adjusted", "stable"}
        else "stable"
    )

    weighted_open = float((weighted_avg or {}).get("opens", 0.0) or 0.0)
    weighted_bookmark = float((weighted_avg or {}).get("bookmarks", 0.0) or 0.0)

    detail = [
        f"Using {int(active_days)} active days from {int(history_days_used)} tracked days.",
        f"Recent weighted behavior — opens: {round(weighted_open, 2)}, bookmarks: {round(weighted_bookmark, 2)}.",
        f"Baseline mission reference: {int((baseline_target or {}).get('opens', 2) or 2)} opens / {int((baseline_target or {}).get('bookmarks', 1) or 1)} bookmarks.",
    ]

    if normalized_plan == "premium":
        detail.append("Premium coaching prioritizes sustained high-output consistency and precision balancing.")
    elif normalized_plan == "basic":
        detail.append("Basic coaching favors practical, maintainable daily progress.")
    else:
        detail.append("Free coaching focuses on easy momentum-building habits.")

    return {
        "tone_profile": normalized_plan,
        "change_reason_short": short_map[direction_key],
        "change_reason_detail": detail,
    }


async def _evaluate_feature33_rollout(actor: Any) -> dict[str, Any]:
    actor_user_id = str(getattr(actor, "user_id", "") or "").strip()
    is_admin = bool(getattr(actor, "is_admin", False))
    flag_doc = await db.feature_flags.find_one({"key": FEATURE33_ROLLOUT_FLAG_KEY}, {"_id": 0}) or {}

    enabled = bool(flag_doc.get("enabled", True))
    rollout_percentage = int(flag_doc.get("rollout_percentage", 100) or 100)
    rollout_percentage = max(0, min(rollout_percentage, 100))

    if is_admin:
        return {
            "allowed": True,
            "enabled": enabled,
            "rollout_percentage": rollout_percentage,
            "reason": "admin_override",
            "bucket": _stable_rollout_bucket(actor_user_id),
        }

    if not enabled:
        return {
            "allowed": False,
            "enabled": enabled,
            "rollout_percentage": rollout_percentage,
            "reason": "disabled",
            "bucket": _stable_rollout_bucket(actor_user_id),
        }

    bucket = _stable_rollout_bucket(actor_user_id)
    allowed = bucket < rollout_percentage
    return {
        "allowed": allowed,
        "enabled": enabled,
        "rollout_percentage": rollout_percentage,
        "reason": "holdback" if not allowed else "in_rollout",
        "bucket": bucket,
    }


def _resolve_effective_plan_from_user_context(user_ctx: Any) -> str:
    if not user_ctx:
        return "free"
    if bool(getattr(user_ctx, "is_admin", False)):
        return "premium"

    user_doc = {
        "is_admin": bool(getattr(user_ctx, "is_admin", False)),
        "subscription_plan": str(getattr(user_ctx, "subscription_plan", "free") or "free"),
        "subscription_status": str(getattr(user_ctx, "subscription_status", "active") or "active"),
        "subscription_end_date": getattr(user_ctx, "subscription_end_date", None),
        "pending_subscription_transition": getattr(user_ctx, "pending_subscription_transition", None),
        "payment_verified": bool(getattr(user_ctx, "payment_verified", False)),
    }
    effective = compute_effective_plan(user_doc)
    return effective if effective in {"free", "basic", "premium"} else "free"


def _require_library_plan_access(user_ctx: Any) -> Optional[dict]:
    # POLICY 2026-06.v3: Library (#33) is open to Free with limited access.
    # Daily action limits are auto-enforced by the platform entitlement meter.
    return None


def _resolve_scoped_library_user_id(actor: Any, requested_user_id: Optional[str]) -> str:
    actor_user_id = str(getattr(actor, "user_id", "") or "").strip()
    is_admin = bool(getattr(actor, "is_admin", False))
    candidate = str(requested_user_id or actor_user_id or "").strip()
    if not candidate:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not is_admin and candidate != actor_user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return candidate


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")
    return themed

CONTENT_SEEDS = [
    {
        "title": "AI Productivity Workflow Checklist",
        "url": "https://www.atlassian.com/work-management/project-management/checklists",
        "type": "article",
        "category": "productivity",
    },
    {
        "title": "Weekly Focus Planning Template",
        "url": "https://www.notion.so/templates/weekly-agenda",
        "type": "template",
        "category": "planning",
    },
    {
        "title": "Sleep Hygiene Playbook",
        "url": "https://www.sleepfoundation.org/sleep-hygiene",
        "type": "guide",
        "category": "health",
    },
    {
        "title": "Zero-Based Budgeting Guide",
        "url": "https://www.investopedia.com/terms/z/zbb.asp",
        "type": "guide",
        "category": "finance",
    },
    {
        "title": "Effective Learning Techniques",
        "url": "https://www.learningscientists.org/blog/2016/8/18-1",
        "type": "article",
        "category": "learning",
    },
    {
        "title": "Beginner Strength Training Plan",
        "url": "https://www.acefitness.org/resources/everyone/exercise-library/",
        "type": "workout",
        "category": "fitness",
    },
    {
        "title": "Mindful Breathing Exercises",
        "url": "https://www.mindful.org/mindful-breathing-exercises/",
        "type": "guide",
        "category": "wellness",
    },
    {
        "title": "Home Buying Starter Checklist",
        "url": "https://www.fanniemae.com/education/home-buying-checklist",
        "type": "checklist",
        "category": "real-estate",
    },
    {
        "title": "Negotiation Preparation Framework",
        "url": "https://www.negotiations.com/articles/negotiation-preparation/",
        "type": "article",
        "category": "career",
    },
    {
        "title": "Travel Safety Essentials",
        "url": "https://travel.state.gov/content/travel/en/international-travel/before-you-go.html",
        "type": "guide",
        "category": "travel",
    },
]


class ContentAutomationRequest(BaseModel):
    max_items: int = 3


async def automate_content_items(max_items: int = 3):
    try:
        seeds = CONTENT_SEEDS.copy()
        random.shuffle(seeds)
        inserted = []
        now = datetime.now(timezone.utc).isoformat()

        for item in seeds:
            if len(inserted) >= max_items:
                break
            doc = {
                **item,
                "added_date": now,
                "source": "automation",
            }
            result = await db.content.update_one({"url": item["url"]}, {"$setOnInsert": doc}, upsert=True)
            if result.upserted_id:
                inserted.append(doc)

        return inserted
    except Exception as e:
        logger.error(f"Content automation error: {e}")
        raise


@router.post("/content/automate")
async def automate_content(request: ContentAutomationRequest):
    try:
        items = await automate_content_items(max_items=max(1, min(request.max_items, 10)))
        return {"added": len(items), "items": items}
    except Exception:
        raise HTTPException(status_code=500, detail="Content automation failed")


@router.get("/content/recent")
async def get_recent_content(limit: int = 6):
    items = await db.content.find({}, {"_id": 0}).sort("added_date", -1).limit(limit).to_list(limit)
    return {"items": items}


# Removed manual sleep loop automation in favor of APScheduler in server.py


class SaveGeneratedRequest(BaseModel):
    user_id: str
    content: str
    feature_key: str
    title: Optional[str] = "Generated Result"


VALID_CATEGORIES = [
    "productivity",
    "planning",
    "health",
    "finance",
    "learning",
    "fitness",
    "wellness",
    "real-estate",
    "career",
    "travel",
    "personal",
]
VALID_TYPES = ["article", "guide", "template", "workout", "checklist", "generated"]


async def _ai_categorize(doc_id: str, title: str, content: str, feature_key: str):
    """Background task: use AI to assign category and type to saved content."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        if not EMERGENT_LLM_KEY:
            return

        prompt = f"""Analyze this content and return ONLY a JSON object with "category" and "type" keys.

Title: {title[:200]}
Feature: {feature_key}
Content: {content[:500]}

Valid categories: {", ".join(VALID_CATEGORIES)}
Valid types: {", ".join(VALID_TYPES)}

Rules:
- Pick the single best category from the valid list
- Pick the single best type from the valid list
- Return ONLY valid JSON like: {{"category": "finance", "type": "guide"}}
"""
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"categorize-{doc_id}",
            system_message="You are a content categorization assistant. Return only valid JSON.",
        ).with_model("openai", "gpt-4o-mini")
        response = await chat.send_message(UserMessage(text=prompt))
        text = response.strip()

        # Extract JSON from response
        import json as json_mod

        # Handle markdown code blocks
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json_mod.loads(text)
        cat = parsed.get("category", "personal")
        typ = parsed.get("type", "generated")

        # Validate
        if cat not in VALID_CATEGORIES:
            cat = "personal"
        if typ not in VALID_TYPES:
            typ = "generated"

        await db.user_content.update_one(
            {"id": doc_id}, {"$set": {"category": cat, "type": typ, "ai_categorized": True}}
        )
        logger.info(f"AI categorized content {doc_id}: {cat}/{typ}")
    except Exception as e:
        logger.error(f"AI categorization failed for {doc_id}: {e}")


@router.post("/content/save-generated")
async def save_generated_content(request: SaveGeneratedRequest):
    try:
        doc_id = str(uuid.uuid4())
        doc = {
            "id": doc_id,
            "user_id": request.user_id,
            "content": request.content,
            "feature_key": request.feature_key,
            "title": request.title,
            "type": "generated",
            "category": "personal",
            "added_date": datetime.now(timezone.utc).isoformat(),
            "url": "",
            "source": "generated",
            "ai_categorized": False,
        }
        await db.user_content.insert_one(doc)

        # Fire-and-forget AI categorization in background
        asyncio.create_task(_ai_categorize(doc_id, request.title or "", request.content, request.feature_key))

        return {"status": "success", "id": doc_id}
    except Exception as e:
        logger.error(f"Error saving generated content: {e}")
        raise HTTPException(status_code=500, detail="Failed to save")


@router.get("/content/user-saved/{user_id}")
async def get_user_saved_content(user_id: str):
    try:
        items = await db.user_content.find({"user_id": user_id}, {"_id": 0}).sort("added_date", -1).to_list(100)
        return {"items": items}
    except Exception as e:
        logger.error(f"Error fetching user content: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch content")


# ── Content Library: Advanced Search, Bookmarks, Export ──

from typing import List


@router.get("/content/library")
async def library_search(
    request: Request,
    q: Optional[str] = None,
    category: Optional[str] = None,
    type: Optional[str] = None,
    source: Optional[str] = None,
    sort: str = "newest",
    page: int = 1,
    per_page: int = 12,
    user_id: Optional[str] = None,
    bookmarked_only: bool = False,
):
    """Advanced content library search with filters, pagination, and bookmarks."""
    request_start = time.perf_counter()
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")

    rollout = await _evaluate_feature33_rollout(actor)
    if not rollout.get("allowed"):
        return JSONResponse(
            status_code=423,
            content={
                "error": "feature_rollout_holdback",
                "message": "Feature 33 is in phased rollout. Please retry shortly.",
                "rollout_percentage": int(rollout.get("rollout_percentage", 0)),
                "bucket": int(rollout.get("bucket", 0)),
                "reason": str(rollout.get("reason") or "holdback"),
            },
        )

    upgrade_payload = _require_library_plan_access(actor)
    if upgrade_payload:
        return JSONResponse(status_code=403, content=upgrade_payload)

    scoped_user_id = _resolve_scoped_library_user_id(actor, user_id)
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 50))
    skip = (page - 1) * per_page
    sort = sort if sort in {"newest", "oldest", "recommended"} else "newest"

    # Build query for curated content
    query: dict = {}
    if q:
        query["$or"] = [
            {"title": {"$regex": re.escape(str(q)), "$options": "i"}},
            {"category": {"$regex": re.escape(str(q)), "$options": "i"}},
            {"type": {"$regex": re.escape(str(q)), "$options": "i"}},
        ]
    if category and category != "all":
        query["category"] = category
    if type and type != "all":
        query["type"] = type
    source = str(source or "all").strip().lower()
    include_curated = source != "generated"
    include_generated = source in {"all", "generated"}
    if include_curated and source not in {"all", "generated", "curated"}:
        query["source"] = source

    db_sort_dir = -1 if sort in {"newest", "recommended"} else 1

    # Get bookmarked content IDs for user
    bookmarked_ids: set = set()
    if scoped_user_id:
        bm_docs = await db.content_bookmarks.find({"user_id": scoped_user_id}, {"_id": 0, "content_id": 1}).to_list(2000)
        bookmarked_ids = {d["content_id"] for d in bm_docs}

    bookmarked_generated_ids = [
        str(entry).split("generated:", 1)[1]
        for entry in bookmarked_ids
        if str(entry).startswith("generated:") and len(str(entry).split("generated:", 1)[1]) > 0
    ]

    if bookmarked_only:
        if not bookmarked_ids:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "per_page": per_page,
                "total_pages": 0,
                "categories": [],
                "types": [],
                "rollout": {
                    "enabled": bool(rollout.get("enabled", True)),
                    "rollout_percentage": int(rollout.get("rollout_percentage", 100)),
                    "bucket": int(rollout.get("bucket", 0)),
                },
            }
        if include_curated:
            query["url"] = {"$in": list(bookmarked_ids)}

    fetch_window = min(skip + per_page + 120, 5000)

    # Fetch from both content and user_content collections using a stable merge strategy
    total = await db.content.count_documents(query) if include_curated else 0
    items_raw = []
    if include_curated:
        items_raw = (
            await db.content.find(query, {"_id": 0})
            .sort("added_date", db_sort_dir)
            .limit(fetch_window)
            .to_list(fetch_window)
        )

    # Also fetch user-saved content if user_id provided and not bookmarked_only
    user_items = []
    user_total = 0
    if include_generated and scoped_user_id:
        uq: dict = {}
        if q:
            uq["$or"] = [
                {"title": {"$regex": re.escape(str(q)), "$options": "i"}},
                {"feature_key": {"$regex": re.escape(str(q)), "$options": "i"}},
            ]
        if category and category != "all":
            uq["category"] = category
        if type and type != "all":
            uq["type"] = type
        uq["user_id"] = scoped_user_id

        if bookmarked_only:
            bookmark_or_filters = []
            if bookmarked_ids:
                bookmark_or_filters.append({"url": {"$in": list(bookmarked_ids)}})
            if bookmarked_generated_ids:
                bookmark_or_filters.append({"id": {"$in": bookmarked_generated_ids}})
            if bookmark_or_filters:
                uq["$or"] = bookmark_or_filters
            else:
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": 0,
                    "categories": [],
                    "types": [],
                    "rollout": {
                        "enabled": bool(rollout.get("enabled", True)),
                        "rollout_percentage": int(rollout.get("rollout_percentage", 100)),
                        "bucket": int(rollout.get("bucket", 0)),
                    },
                }

        user_total = await db.user_content.count_documents(uq)
        if user_total > 0:
            user_items = (
                await db.user_content.find(uq, {"_id": 0})
                .sort("added_date", db_sort_dir)
                .limit(fetch_window)
                .to_list(fetch_window)
            )
            for ui in user_items:
                ui["source"] = "generated"
                if not ui.get("url"):
                    ui["url"] = f"generated:{ui.get('id', '')}"

    combined_total = total + user_total
    total_pages = max(1, (combined_total + per_page - 1) // per_page)

    affinity_profile = (
        await build_library_affinity_profile(db, scoped_user_id, window_days=30)
        if sort == "recommended" and scoped_user_id
        else {"category": {}, "type": {}}
    )
    page_items = merge_library_items_for_page(
        curated_items=items_raw,
        generated_items=user_items,
        sort=sort,
        skip=skip,
        per_page=per_page,
        bookmarked_ids=bookmarked_ids,
        affinity_profile=affinity_profile,
    )

    latency_ms = round((time.perf_counter() - request_start) * 1000.0, 2)
    freshness_lag_hours = _compute_feed_freshness_lag_hours(page_items)
    try:
        await db.content_library_perf_metrics.insert_one(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latency_ms": latency_ms,
                "user_id": str(getattr(actor, "user_id", "") or ""),
                "is_admin": bool(getattr(actor, "is_admin", False)),
                "sort": sort,
                "page": page,
                "per_page": per_page,
                "result_count": len(page_items),
                "total": int(combined_total),
                "freshness_lag_hours": freshness_lag_hours,
                "rollout_percentage": int(rollout.get("rollout_percentage", 100)),
                "rollout_bucket": int(rollout.get("bucket", 0)),
                "bookmarked_only": bool(bookmarked_only),
            }
        )
    except Exception:
        pass

    # Get distinct categories and types for filter UI
    cats = set(await db.content.distinct("category")) if include_curated else set()
    typs = set(await db.content.distinct("type")) if include_curated else set()
    if include_generated and scoped_user_id:
        generated_distinct_query = {"user_id": scoped_user_id}
        if category and category != "all":
            generated_distinct_query["category"] = category
        cats.update(await db.user_content.distinct("category", generated_distinct_query))
        typs.update(await db.user_content.distinct("type", generated_distinct_query))

    return {
        "items": page_items,
        "total": combined_total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "categories": sorted([c for c in cats if c]),
        "types": sorted([t for t in typs if t]),
        "rollout": {
            "enabled": bool(rollout.get("enabled", True)),
            "rollout_percentage": int(rollout.get("rollout_percentage", 100)),
            "bucket": int(rollout.get("bucket", 0)),
        },
        "observability": {
            "latency_ms": latency_ms,
            "feed_freshness_lag_hours": freshness_lag_hours,
        },
    }


class BookmarkToggleRequest(BaseModel):
    user_id: str
    content_id: str
    title: Optional[str] = ""


@router.post("/content/bookmarks/toggle")
async def toggle_bookmark(request: Request, payload: BookmarkToggleRequest):
    """Toggle bookmark on/off for a content item. Server-synced."""
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")

    scoped_user_id = _resolve_scoped_library_user_id(actor, payload.user_id)
    content_id = str(payload.content_id or "").strip()
    if not content_id:
        raise HTTPException(status_code=422, detail="content_id is required")

    existing = await db.content_bookmarks.find_one({"user_id": scoped_user_id, "content_id": content_id})
    if existing:
        await db.content_bookmarks.delete_one({"_id": existing["_id"]})
        return {"bookmarked": False, "content_id": content_id}
    else:
        await db.content_bookmarks.insert_one(
            {
                "user_id": scoped_user_id,
                "content_id": content_id,
                "title": payload.title,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {"bookmarked": True, "content_id": content_id}


@router.get("/content/bookmarks/{user_id}")
async def get_bookmarks(user_id: str, request: Request):
    """Get all bookmarked content_ids for a user."""
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")

    scoped_user_id = _resolve_scoped_library_user_id(actor, user_id)
    docs = await db.content_bookmarks.find({"user_id": scoped_user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"bookmarks": docs, "count": len(docs)}


class LibraryExportRequest(BaseModel):
    items: List[dict]
    format: str = "txt"


@router.post("/content/library/export")
async def export_library(request: Request, payload: LibraryExportRequest):
    """Export selected library items as TXT or CSV."""
    import io
    from fastapi.responses import StreamingResponse

    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")

    upgrade_payload = _require_library_plan_access(actor)
    if upgrade_payload:
        return JSONResponse(status_code=403, content=upgrade_payload)

    export_format = str(payload.format or "txt").strip().lower()
    if export_format not in {"txt", "csv"}:
        raise HTTPException(status_code=422, detail="Unsupported export format")

    sanitized_items = []
    for item in (payload.items or [])[:500]:
        sanitized_items.append(
            {
                "title": str(item.get("title", ""))[:300],
                "type": str(item.get("type", ""))[:60],
                "category": str(item.get("category", ""))[:60],
                "url": str(item.get("url", ""))[:1200],
                "added_date": str(item.get("added_date", ""))[:80],
            }
        )

    if export_format == "csv":
        import csv

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Title", "Type", "Category", "URL", "Date"])
        for item in sanitized_items:
            writer.writerow(
                [
                    item.get("title", ""),
                    item.get("type", ""),
                    item.get("category", ""),
                    item.get("url", ""),
                    item.get("added_date", ""),
                ]
            )
        content_bytes = buf.getvalue().encode("utf-8")
        return StreamingResponse(
            io.BytesIO(content_bytes),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=content_library.csv"},
        )

    # TXT format
    lines = [
        "Content Library Export",
        f"{'=' * 30}",
        f"Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        f"Items: {len(sanitized_items)}",
        "",
    ]
    for item in sanitized_items:
        lines.append(f"  {item.get('title', 'Untitled')}")
        lines.append(f"  Type: {item.get('type', '')} | Category: {item.get('category', '')}")
        lines.append(f"  URL: {item.get('url', '')}")
        lines.append(f"  Date: {item.get('added_date', '')}")
        lines.append("")
    lines.append("--- Generated by RealAICoach ---")
    content_bytes = "\n".join(lines).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(content_bytes),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=content_library.txt"},
    )


@router.get("/content/library/insights/{user_id}")
async def library_usage_insights(user_id: str, request: Request, days: int = 7):
    """Compact Library usage insights from existing platform event collections only."""
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")
    if actor.user_id != user_id and not getattr(actor, "is_admin", False):
        raise HTTPException(status_code=403, detail="Not authorized")

    window_days = max(1, min(days, 30))
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=window_days)
    prev_start = start - timedelta(days=window_days)

    search_events = await db.action_history.find(
        {
            "user_id": user_id,
            "feature_key": "content-library",
            "action": "search",
            "timestamp": {"$gte": start.isoformat()},
        },
        {"_id": 0, "details": 1},
    ).to_list(400)
    topic_counter = Counter()
    for event in search_events:
        details = event.get("details") or {}
        raw_topic = (details.get("query") or "").strip().lower()
        if raw_topic:
            topic_counter[raw_topic] += 1
    top_searched_topics = [{"topic": topic, "count": count} for topic, count in topic_counter.most_common(5)]

    open_events = await db.action_history.find(
        {
            "user_id": user_id,
            "feature_key": "content-library",
            "action": "open",
            "timestamp": {"$gte": start.isoformat()},
        },
        {"_id": 0, "details": 1},
    ).to_list(500)
    opened_type_counter = Counter()
    for event in open_events:
        details = event.get("details") or {}
        raw_type = (details.get("type") or "").strip().lower()
        if raw_type:
            opened_type_counter[raw_type] += 1
    most_opened_type = None
    if opened_type_counter:
        label, count = opened_type_counter.most_common(1)[0]
        most_opened_type = {"type": label, "count": count}

    bookmark_current = await db.content_bookmarks.count_documents(
        {"user_id": user_id, "created_at": {"$gte": start.isoformat()}}
    )
    bookmark_previous = await db.content_bookmarks.count_documents(
        {
            "user_id": user_id,
            "created_at": {"$gte": prev_start.isoformat(), "$lt": start.isoformat()},
        }
    )
    delta = bookmark_current - bookmark_previous
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"

    series = []
    base_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(days=window_days - 1)
    for i in range(window_days):
        day_start = base_day + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_count = await db.content_bookmarks.count_documents(
            {
                "user_id": user_id,
                "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()},
            }
        )
        series.append({"date": day_start.date().isoformat(), "count": day_count})

    return {
        "window_days": window_days,
        "top_searched_topics": top_searched_topics,
        "most_opened_type": most_opened_type,
        "bookmark_trend": {
            "current_count": bookmark_current,
            "previous_count": bookmark_previous,
            "delta": delta,
            "direction": direction,
            "series": series,
        },
        "has_enough_activity": bool(top_searched_topics or most_opened_type or bookmark_current or bookmark_previous),
    }


@router.get("/content/library/engagement-loop/{user_id}")
async def library_engagement_loop(user_id: str, request: Request, days: int = 30):
    """Return continue-rail + daily mission + streak data for content library retention loops."""
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")

    scoped_user_id = _resolve_scoped_library_user_id(actor, user_id)
    effective_plan = _resolve_effective_plan_from_user_context(actor)
    window_days = max(7, min(days, 90))
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=window_days)

    recent_events = await db.action_history.find(
        {
            "user_id": scoped_user_id,
            "feature_key": "content-library",
            "timestamp": {"$gte": start.isoformat()},
        },
        {"_id": 0, "action": 1, "details": 1, "timestamp": 1},
    ).sort("timestamp", -1).to_list(1200)

    continue_item = None
    for event in recent_events:
        if str(event.get("action") or "").lower() != "open":
            continue
        details = event.get("details") or {}
        continue_item = {
            "title": str(details.get("title") or "").strip(),
            "type": str(details.get("type") or "").strip(),
            "category": str(details.get("category") or "").strip(),
            "url": str(details.get("url") or "").strip(),
            "source": str(details.get("source") or "").strip(),
            "last_opened_at": str(event.get("timestamp") or ""),
        }
        break

    def _event_day(timestamp: str) -> Optional[str]:
        raw = str(timestamp or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).date().isoformat()
        except Exception:
            return None

    activity_days = {
        day
        for day in (
            _event_day(event.get("timestamp"))
            for event in recent_events
            if str(event.get("action") or "").lower() in {"open", "bookmark_toggle", "search"}
        )
        if day
    }

    streak_days = 0
    cursor_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc).date()
    for _ in range(window_days):
        if cursor_day.isoformat() in activity_days:
            streak_days += 1
            cursor_day = cursor_day - timedelta(days=1)
            continue
        break

    mission_daily_stats: dict[str, dict[str, int]] = {}
    for event in recent_events:
        day_key = _event_day(event.get("timestamp"))
        if not day_key:
            continue
        if day_key not in mission_daily_stats:
            mission_daily_stats[day_key] = {"opens": 0, "bookmarks": 0}

        action = str(event.get("action") or "").lower()
        if action == "open":
            mission_daily_stats[day_key]["opens"] += 1
        elif action == "bookmark_toggle" and bool((event.get("details") or {}).get("bookmarked")):
            mission_daily_stats[day_key]["bookmarks"] += 1

    today_day_key = datetime(now.year, now.month, now.day, tzinfo=timezone.utc).date().isoformat()
    adaptive_target = _derive_adaptive_library_mission_target(
        mission_daily_stats=mission_daily_stats,
        today_iso=today_day_key,
    )
    plan_tone_reason = _build_plan_toned_mission_reason(
        plan=effective_plan,
        change_direction=str(adaptive_target.get("change_direction") or "stable"),
        history_days_used=int(adaptive_target.get("history_days_used", 0) or 0),
        active_days=int(adaptive_target.get("active_days", 0) or 0),
        consistency_ratio=float(adaptive_target.get("consistency_ratio", 0.0) or 0.0),
        weighted_avg={
            "opens": float(((adaptive_target.get("weighted_avg") or {}).get("opens", 0.0) or 0.0)),
            "bookmarks": float(((adaptive_target.get("weighted_avg") or {}).get("bookmarks", 0.0) or 0.0)),
        },
        baseline_target={
            "opens": int(((adaptive_target.get("baseline_target") or {}).get("opens", 2) or 2)),
            "bookmarks": int(((adaptive_target.get("baseline_target") or {}).get("bookmarks", 1) or 1)),
        },
    )
    mission_target = {
        "opens": int(adaptive_target.get("opens", 2) or 2),
        "bookmarks": int(adaptive_target.get("bookmarks", 1) or 1),
    }
    today_stats = mission_daily_stats.get(today_day_key, {"opens": 0, "bookmarks": 0})
    mission_progress = {
        "opens": int(today_stats.get("opens", 0) or 0),
        "bookmarks": int(today_stats.get("bookmarks", 0) or 0),
    }
    mission_completed = (
        mission_progress["opens"] >= mission_target["opens"]
        and mission_progress["bookmarks"] >= mission_target["bookmarks"]
    )

    weekly_wins = 0
    weekly_misses = 0
    today_date = datetime(now.year, now.month, now.day, tzinfo=timezone.utc).date()
    for i in range(7):
        day = (today_date - timedelta(days=i)).isoformat()
        stats = mission_daily_stats.get(day, {"opens": 0, "bookmarks": 0})
        completed = (
            stats.get("opens", 0) >= mission_target["opens"]
            and stats.get("bookmarks", 0) >= mission_target["bookmarks"]
        )
        if completed:
            weekly_wins += 1
        else:
            weekly_misses += 1

    if streak_days == 0 or weekly_misses >= 5:
        streak_risk = "high"
    elif streak_days <= 2 or weekly_misses >= 3:
        streak_risk = "medium"
    else:
        streak_risk = "low"

    return {
        "window_days": window_days,
        "streak_days": streak_days,
        "continue_item": continue_item,
        "daily_mission": {
            "target": mission_target,
            "progress": mission_progress,
            "completed": mission_completed,
            "adaptive_context": {
                "mode": str(adaptive_target.get("mode") or "baseline"),
                "history_days_used": int(adaptive_target.get("history_days_used", 0) or 0),
                "active_days": int(adaptive_target.get("active_days", 0) or 0),
                "consistency_ratio": float(adaptive_target.get("consistency_ratio", 0.0) or 0.0),
                "weighted_avg": {
                    "opens": float(((adaptive_target.get("weighted_avg") or {}).get("opens", 0.0) or 0.0)),
                    "bookmarks": float(((adaptive_target.get("weighted_avg") or {}).get("bookmarks", 0.0) or 0.0)),
                },
                "baseline_target": {
                    "opens": int(((adaptive_target.get("baseline_target") or {}).get("opens", 2) or 2)),
                    "bookmarks": int(((adaptive_target.get("baseline_target") or {}).get("bookmarks", 1) or 1)),
                },
                "target_delta": {
                    "opens": int(((adaptive_target.get("target_delta") or {}).get("opens", 0) or 0)),
                    "bookmarks": int(((adaptive_target.get("target_delta") or {}).get("bookmarks", 0) or 0)),
                },
                "change_direction": str(adaptive_target.get("change_direction") or "stable"),
                "tone_profile": str(plan_tone_reason.get("tone_profile") or effective_plan),
                "change_reason_short": str(
                    plan_tone_reason.get("change_reason_short")
                    or adaptive_target.get("change_reason_short")
                    or ""
                ),
                "change_reason_detail": [
                    str(item)
                    for item in (
                        plan_tone_reason.get("change_reason_detail")
                        or adaptive_target.get("change_reason_detail")
                        or []
                    )
                    if str(item).strip()
                ][:5],
            },
        },
        "weekly_summary": {
            "wins": weekly_wins,
            "misses": weekly_misses,
            "streak_risk": streak_risk,
            "current_streak": streak_days,
        },
    }


@router.get("/content/library/recommendation-telemetry/{user_id}")
async def library_recommendation_telemetry(user_id: str, request: Request, days: int = 14):
    """Aggregate recommendation engagement telemetry for ranking quality tuning."""
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")

    scoped_user_id = _resolve_scoped_library_user_id(actor, user_id)
    window_days = max(7, min(days, 60))
    start = datetime.now(timezone.utc) - timedelta(days=window_days)

    telemetry_actions = {
        "recommendation_reason_click",
        "open_after_recommendation",
        "bookmark_after_recommendation",
    }
    rows = await db.action_history.find(
        {
            "user_id": scoped_user_id,
            "feature_key": "content-library",
            "action": {"$in": list(telemetry_actions)},
            "timestamp": {"$gte": start.isoformat()},
        },
        {"_id": 0, "action": 1, "details": 1},
    ).to_list(3000)

    event_counter = Counter()
    reason_counter = Counter()
    for row in rows:
        action = str(row.get("action") or "").strip().lower()
        if action:
            event_counter[action] += 1

        details = row.get("details") or {}
        reason = str(details.get("reason") or "").strip().lower()
        if reason:
            reason_counter[reason] += 1
        for reason_item in details.get("reasons") or []:
            normalized = str(reason_item or "").strip().lower()
            if normalized:
                reason_counter[normalized] += 1

    reason_clicks = event_counter.get("recommendation_reason_click", 0)
    open_after = event_counter.get("open_after_recommendation", 0)
    bookmark_after = event_counter.get("bookmark_after_recommendation", 0)

    return {
        "window_days": window_days,
        "events": {
            "recommendation_reason_click": reason_clicks,
            "open_after_recommendation": open_after,
            "bookmark_after_recommendation": bookmark_after,
        },
        "conversion": {
            "open_after_reason_click_rate": round((open_after / reason_clicks), 4) if reason_clicks else 0,
            "bookmark_after_open_rate": round((bookmark_after / open_after), 4) if open_after else 0,
        },
        "top_reasons": [
            {"reason": reason, "count": count}
            for reason, count in reason_counter.most_common(8)
        ],
    }


@router.get("/admin/content-library/recommendation-tuning")
async def admin_recommendation_tuning(request: Request, days: int = 14):
    """Admin-only reason-level conversion analysis by plan tier for ranking tuning."""
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not bool(getattr(actor, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")

    window_days = max(7, min(days, 60))
    start = datetime.now(timezone.utc) - timedelta(days=window_days)
    telemetry_actions = {
        "recommendation_reason_click",
        "open_after_recommendation",
        "bookmark_after_recommendation",
    }

    rows = await db.action_history.find(
        {
            "feature_key": "content-library",
            "action": {"$in": list(telemetry_actions)},
            "timestamp": {"$gte": start.isoformat()},
        },
        {"_id": 0, "user_id": 1, "action": 1, "details": 1},
    ).to_list(5000)

    user_ids = sorted({str(row.get("user_id") or "").strip() for row in rows if str(row.get("user_id") or "").strip()})
    users = await db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "subscription_plan": 1}).to_list(5000)
    user_plan_map = {
        str(row.get("user_id") or "").strip(): str(row.get("subscription_plan") or "free").strip().lower() or "free"
        for row in users
    }

    def _normalize_reason(value: str) -> str:
        normalized = str(value or "").strip().lower()
        return normalized or "unattributed"

    plan_tuning: dict[str, dict[str, Any]] = {}

    def _plan_bucket(plan: str) -> dict[str, Any]:
        if plan not in plan_tuning:
            plan_tuning[plan] = {
                "events": {
                    "recommendation_reason_click": 0,
                    "open_after_recommendation": 0,
                    "bookmark_after_recommendation": 0,
                },
                "reason_breakdown": {},
            }
        return plan_tuning[plan]

    def _reason_bucket(plan_bucket: dict[str, Any], reason: str) -> dict[str, int]:
        reason_breakdown = plan_bucket["reason_breakdown"]
        if reason not in reason_breakdown:
            reason_breakdown[reason] = {"clicks": 0, "opens": 0, "bookmarks": 0}
        return reason_breakdown[reason]

    for row in rows:
        action = str(row.get("action") or "").strip().lower()
        user_id = str(row.get("user_id") or "").strip()
        plan = user_plan_map.get(user_id, "free")
        bucket = _plan_bucket(plan)
        if action in bucket["events"]:
            bucket["events"][action] += 1

        details = row.get("details") or {}
        reasons = []
        direct_reason = str(details.get("reason") or "").strip()
        if direct_reason:
            reasons.append(direct_reason)
        for reason in details.get("reasons") or []:
            normalized_reason = str(reason or "").strip()
            if normalized_reason:
                reasons.append(normalized_reason)

        reasons = reasons or ["unattributed"]
        deduped_reasons = sorted({_normalize_reason(r) for r in reasons})
        for reason in deduped_reasons:
            reason_bucket = _reason_bucket(bucket, reason)
            if action == "recommendation_reason_click":
                reason_bucket["clicks"] += 1
            elif action == "open_after_recommendation":
                reason_bucket["opens"] += 1
            elif action == "bookmark_after_recommendation":
                reason_bucket["bookmarks"] += 1

    by_plan = {}
    for plan, data in plan_tuning.items():
        reason_rows = []
        for reason, metrics in data["reason_breakdown"].items():
            clicks = int(metrics.get("clicks", 0))
            opens = int(metrics.get("opens", 0))
            bookmarks = int(metrics.get("bookmarks", 0))
            reason_rows.append(
                {
                    "reason": reason,
                    "clicks": clicks,
                    "opens": opens,
                    "bookmarks": bookmarks,
                    "open_after_click_rate": round((opens / clicks), 4) if clicks else 0,
                    "bookmark_after_open_rate": round((bookmarks / opens), 4) if opens else 0,
                }
            )

        by_plan[plan] = {
            "events": data["events"],
            "reason_level_conversion": sorted(reason_rows, key=lambda row: row["clicks"], reverse=True),
        }

    return {
        "window_days": window_days,
        "by_plan": by_plan,
        "plans_covered": sorted(list(by_plan.keys())),
    }


@router.get("/admin/content-library/observability")
async def admin_content_library_observability(request: Request, hours: int = 24):
    """Admin-only Feature 33 observability snapshot (latency, freshness, bookmark conversion, recommendation conversion)."""
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not bool(getattr(actor, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")

    lookback_hours = max(1, min(hours, 168))
    start = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    perf_rows = await db.content_library_perf_metrics.find(
        {"timestamp": {"$gte": start.isoformat()}},
        {"_id": 0, "latency_ms": 1, "freshness_lag_hours": 1},
    ).to_list(5000)
    latencies = sorted([float(row.get("latency_ms", 0.0)) for row in perf_rows if float(row.get("latency_ms", 0.0)) > 0])
    freshness = [float(row.get("freshness_lag_hours", 0.0)) for row in perf_rows if row.get("freshness_lag_hours") is not None]

    p95_latency_ms = 0.0
    p50_latency_ms = 0.0
    if latencies:
        p95_idx = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
        p50_idx = max(0, min(len(latencies) - 1, int(len(latencies) * 0.50) - 1))
        p95_latency_ms = round(float(latencies[p95_idx]), 2)
        p50_latency_ms = round(float(latencies[p50_idx]), 2)

    avg_freshness_lag_hours = round((sum(freshness) / len(freshness)), 4) if freshness else 0.0

    telemetry_rows = await db.action_history.find(
        {
            "feature_key": "content-library",
            "action": {
                "$in": [
                    "recommendation_reason_click",
                    "open_after_recommendation",
                    "bookmark_after_recommendation",
                    "bookmark_toggle",
                ]
            },
            "timestamp": {"$gte": start.isoformat()},
        },
        {"_id": 0, "action": 1, "details": 1},
    ).to_list(8000)

    event_counter = Counter()
    bookmark_success_events = 0
    bookmark_toggle_events = 0
    for row in telemetry_rows:
        action = str(row.get("action") or "").strip().lower()
        if action:
            event_counter[action] += 1
        if action == "bookmark_toggle":
            bookmark_toggle_events += 1
            if bool((row.get("details") or {}).get("bookmarked")):
                bookmark_success_events += 1

    reason_clicks = int(event_counter.get("recommendation_reason_click", 0))
    open_after = int(event_counter.get("open_after_recommendation", 0))
    bookmark_after = int(event_counter.get("bookmark_after_recommendation", 0))

    recommendation_open_rate = round((open_after / reason_clicks), 4) if reason_clicks else 0.0
    bookmark_after_open_rate = round((bookmark_after / open_after), 4) if open_after else 0.0
    bookmark_success_rate = round((bookmark_success_events / bookmark_toggle_events), 4) if bookmark_toggle_events else 0.0

    return {
        "lookback_hours": lookback_hours,
        "volume": {
            "perf_samples": len(perf_rows),
            "telemetry_events": len(telemetry_rows),
        },
        "latency": {
            "p95_ms": p95_latency_ms,
            "p50_ms": p50_latency_ms,
        },
        "freshness": {
            "avg_feed_lag_hours": avg_freshness_lag_hours,
        },
        "conversion": {
            "bookmark_success_rate": bookmark_success_rate,
            "recommendation_open_after_click_rate": recommendation_open_rate,
            "bookmark_after_open_rate": bookmark_after_open_rate,
        },
        "events": {
            "recommendation_reason_click": reason_clicks,
            "open_after_recommendation": open_after,
            "bookmark_after_recommendation": bookmark_after,
            "bookmark_toggle": bookmark_toggle_events,
        },
    }


@router.get("/admin/content-library/release-gate")
async def admin_content_library_release_gate(request: Request):
    """Admin-only release gate verdict for Feature 33 launch hardening."""
    actor = await get_current_user(request)
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not bool(getattr(actor, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")

    rollout_doc = await db.feature_flags.find_one({"key": FEATURE33_ROLLOUT_FLAG_KEY}, {"_id": 0}) or {
        "key": FEATURE33_ROLLOUT_FLAG_KEY,
        "enabled": True,
        "rollout_percentage": 100,
    }
    obs = await admin_content_library_observability(request, hours=24)

    events = obs.get("events") or {}
    conversion = obs.get("conversion") or {}
    bookmark_toggle_events = int(events.get("bookmark_toggle", 0) or 0)
    recommendation_reason_click_events = int(events.get("recommendation_reason_click", 0) or 0)
    bookmark_success_rate = float(conversion.get("bookmark_success_rate", 0.0) or 0.0)
    recommendation_open_after_click_rate = float(
        conversion.get("recommendation_open_after_click_rate", 0.0) or 0.0
    )

    min_bookmark_sample = 30
    min_recommendation_sample = 30
    bookmark_volume_guard_active = bookmark_toggle_events < min_bookmark_sample
    recommendation_volume_guard_active = recommendation_reason_click_events < min_recommendation_sample

    checks = {
        "rollout_flag_defined": bool(rollout_doc.get("key")),
        "latency_p95_under_1500ms": float((obs.get("latency") or {}).get("p95_ms", 0.0)) <= 1500,
        "feed_freshness_lag_under_72h": float((obs.get("freshness") or {}).get("avg_feed_lag_hours", 0.0)) <= 72,
        "bookmark_success_rate_over_15pct_or_low_volume_guard": (
            bookmark_volume_guard_active or bookmark_success_rate >= 0.15
        ),
        "recommendation_open_after_click_rate_over_10pct_or_low_volume_guard": (
            recommendation_volume_guard_active or recommendation_open_after_click_rate >= 0.10
        ),
    }

    failed = [name for name, ok in checks.items() if not bool(ok)]
    verdict = "pass" if not failed else "warn"

    state_key = "feature33_library_release_gate_state"
    previous_state = await db.system_runtime_flags.find_one({"key": state_key}, {"_id": 0}) or {}
    previous_verdict = str(previous_state.get("verdict") or "").strip().lower()
    changed = bool(previous_verdict) and previous_verdict != verdict

    transition_alert = {
        "triggered": False,
        "from": previous_verdict or None,
        "to": verdict,
        "severity": None,
    }

    if changed:
        severity = "info" if verdict == "pass" else "warning"
        now_iso = datetime.now(timezone.utc).isoformat()
        transition_alert = {
            "triggered": True,
            "from": previous_verdict,
            "to": verdict,
            "severity": severity,
        }

        title = "Feature 33 Release Gate State Change"
        message = (
            f"Feature 33 release-gate transitioned {previous_verdict} → {verdict}. "
            f"Failed checks: {', '.join(failed) if failed else 'none'}"
        )

        try:
            await db.admin_push_notifications.insert_one(
                {
                    "type": "feature33_release_gate_state_change",
                    "severity": severity,
                    "title": title,
                    "message": message,
                    "timestamp": now_iso,
                    "read": False,
                }
            )
        except Exception:
            pass

        try:
            admin_users = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(200)
            for admin in admin_users:
                admin_user_id = str(admin.get("user_id") or "").strip()
                if not admin_user_id:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"feature33_release_gate_{admin_user_id}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": admin_user_id,
                        "type": "feature33_release_gate_state_change",
                        "title": title,
                        "message": message,
                        "read": False,
                        "created_at": now_iso,
                        "action_url": "/admin-console?category=operations&tab=automation-engine",
                        "metadata": {
                            "feature": "feature33_library",
                            "from": previous_verdict,
                            "to": verdict,
                            "failed_checks": failed,
                        },
                    }
                )
        except Exception:
            pass

    await db.system_runtime_flags.update_one(
        {"key": state_key},
        {
            "$set": {
                "key": state_key,
                "feature": "feature33_library",
                "verdict": verdict,
                "failed_checks": failed,
                "checks": checks,
                "rollout": {
                    "enabled": bool(rollout_doc.get("enabled", True)),
                    "rollout_percentage": int(rollout_doc.get("rollout_percentage", 100) or 100),
                },
                "volume_context": {
                    "bookmark_toggle_events": bookmark_toggle_events,
                    "recommendation_reason_click_events": recommendation_reason_click_events,
                    "min_bookmark_sample": min_bookmark_sample,
                    "min_recommendation_sample": min_recommendation_sample,
                    "bookmark_volume_guard_active": bookmark_volume_guard_active,
                    "recommendation_volume_guard_active": recommendation_volume_guard_active,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    return {
        "feature": "feature33_library",
        "verdict": verdict,
        "checks": checks,
        "failed_checks": failed,
        "transition_alert": transition_alert,
        "volume_context": {
            "bookmark_toggle_events": bookmark_toggle_events,
            "recommendation_reason_click_events": recommendation_reason_click_events,
            "min_bookmark_sample": min_bookmark_sample,
            "min_recommendation_sample": min_recommendation_sample,
            "bookmark_volume_guard_active": bookmark_volume_guard_active,
            "recommendation_volume_guard_active": recommendation_volume_guard_active,
        },
        "rollout": {
            "enabled": bool(rollout_doc.get("enabled", True)),
            "rollout_percentage": int(rollout_doc.get("rollout_percentage", 100) or 100),
            "flag_key": str(rollout_doc.get("key") or FEATURE33_ROLLOUT_FLAG_KEY),
        },
        "observability_snapshot": obs,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Actions Tab: History, Export, Scheduling ──


class LogActionRequest(BaseModel):
    user_id: str
    feature_key: str
    action: str  # predictions, automation, share, export, print, copy, save
    details: Optional[dict] = None


@router.post("/actions/log")
async def log_action(request: LogActionRequest):
    """Log an action performed in the Actions Tab."""
    entry = {
        "action_id": f"act_{uuid.uuid4().hex[:10]}",
        "user_id": request.user_id,
        "feature_key": request.feature_key,
        "action": request.action,
        "details": request.details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.action_history.insert_one(entry)
    return {"success": True, "action_id": entry["action_id"]}


@router.get("/actions/history/{user_id}")
async def get_action_history(
    user_id: str,
    feature_key: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Get paginated action history for a user with filtering."""
    query: dict = {"user_id": user_id}
    if feature_key:
        query["feature_key"] = feature_key
    if search:
        query["action"] = {"$regex": re.escape(str(search)), "$options": "i"}
    if date_from or date_to:
        date_filter: dict = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        query["timestamp"] = date_filter
    total = await db.action_history.count_documents(query)
    items = await db.action_history.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).to_list(limit)
    return {"history": items, "count": len(items), "total": total, "skip": skip, "limit": limit}


class ScheduleActionRequest(BaseModel):
    user_id: str
    feature_key: str
    action: str
    schedule_type: str = "once"  # once, daily, weekly, monthly
    scheduled_at: str  # ISO datetime
    details: Optional[dict] = None


@router.post("/actions/schedule")
async def schedule_action(request: ScheduleActionRequest):
    """Schedule an action for later execution."""
    entry = {
        "schedule_id": f"sched_{uuid.uuid4().hex[:10]}",
        "user_id": request.user_id,
        "feature_key": request.feature_key,
        "action": request.action,
        "schedule_type": request.schedule_type,
        "scheduled_at": request.scheduled_at,
        "status": "pending",
        "details": request.details or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.scheduled_actions.insert_one(entry)
    return {"success": True, "schedule": {k: v for k, v in entry.items() if k != "_id"}}


@router.get("/actions/scheduled/{user_id}")
async def get_scheduled_actions(user_id: str):
    """Get user's scheduled actions."""
    items = (
        await db.scheduled_actions.find({"user_id": user_id, "status": "pending"}, {"_id": 0})
        .sort("scheduled_at", 1)
        .to_list(50)
    )
    return {"scheduled": items}


@router.delete("/actions/schedule/{schedule_id}")
async def cancel_scheduled_action(schedule_id: str):
    """Cancel a scheduled action."""
    result = await db.scheduled_actions.update_one(
        {"schedule_id": schedule_id, "status": "pending"}, {"$set": {"status": "cancelled"}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Schedule not found or already processed")
    return {"success": True}


@router.post("/actions/export")
async def export_content(request: Request):
    """Generate export file (CSV or PDF) from content."""
    body = await request.json()
    content = body.get("content", "")
    format_type = body.get("format", "csv")
    title = body.get("title", "Export")
    feature_key = body.get("feature_key", "")

    if format_type == "txt":
        import io
        from fastapi.responses import StreamingResponse

        text_content = f"{title}\n{'=' * len(title)}\n\nFeature: {feature_key}\nExported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC\n\n{content}\n\n--- Generated by RealAICoach ---"
        return StreamingResponse(
            io.BytesIO(text_content.encode("utf-8")),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={feature_key}_export.txt"},
        )

    if format_type == "docx":
        import io
        from fastapi.responses import StreamingResponse
        from docx import Document
        from docx.shared import Pt, RGBColor

        doc = Document()
        style = doc.styles["Title"]
        style.font.color.rgb = RGBColor(0x1D, 0x4E, 0xD8)
        doc.add_heading(title or "AI Feature Export", level=0)
        meta = doc.add_paragraph(
            f"Feature: {feature_key} | Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
        )
        meta.style.font.size = Pt(9)
        meta.style.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
        for para in content.split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())
        doc.add_paragraph("--- Generated by RealAICoach ---")
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={feature_key}_export.docx"},
        )

    if format_type == "csv":
        import csv
        import io
        from fastapi.responses import StreamingResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Feature", "Title", "Content", "Exported At"])
        # Split content by lines for multi-row export
        lines = content.split("\n")
        for line in lines:
            if line.strip():
                writer.writerow([feature_key, title, line.strip(), datetime.now(timezone.utc).isoformat()])
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={feature_key}_export.csv"},
        )

    elif format_type == "pdf":
        import io
        from fastapi.responses import StreamingResponse
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title2", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#1D4ED8")
        )
        body_style = ParagraphStyle("Body2", parent=styles["Normal"], fontSize=11, leading=16)
        meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, textColor=colors.gray)

        elements = []
        elements.append(Paragraph(title or "AI Feature Export", title_style))
        elements.append(
            Paragraph(
                f"Feature: {feature_key} | Exported: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
                meta_style,
            )
        )
        elements.append(Spacer(1, 20))

        for para in content.split("\n"):
            if para.strip():
                safe_para = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                elements.append(Paragraph(safe_para, body_style))
                elements.append(Spacer(1, 6))

        elements.append(Spacer(1, 30))
        elements.append(Paragraph("--- Generated by RealAICoach ---", meta_style))

        doc.build(elements)
        composed_pdf = compose_pdf_v15_helper_layout(
            buf.getvalue(),
            title="Content Feature Export",
            subtitle="AI content governance artifact",
            right_primary=f"Feature: {feature_key}",
            right_secondary=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            badge_text="CONTENT STUDIO EXPORT",
            badge_status="INFO",
            footer_text="RealAICoach Content Studio • Enterprise profile",
            summary_title="Export Metadata",
            summary_rows=[
                ("Title", title or "AI Feature Export"),
                ("Paragraphs", str(sum(1 for p in content.split('\n') if p.strip()))),
                ("Mode", "Manual export"),
            ],
            callout_title="Usage",
            callout_subtitle="Content portability",
            callout_detail="This artifact is suitable for review, approval, and external sharing under content governance.",
            callout_status="INFO",
        )
        pdf_bytes = _enforce_pdf_v15_enterprise(composed_pdf, f"content_export_{feature_key}")
        buf = io.BytesIO(pdf_bytes)
        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("content-export", feature_key)}"'},
        )

    raise HTTPException(status_code=400, detail="Format must be 'txt', 'csv', 'docx', or 'pdf'")


@router.delete("/actions/history/{action_id}")
async def delete_action_history(action_id: str):
    """Delete a single action from history."""
    result = await db.action_history.delete_one({"action_id": action_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Action not found")
    return {"success": True}


@router.post("/actions/export-history")
async def export_action_history(request: Request):
    """Export user's action history as CSV."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    body = await request.json()
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    items = await db.action_history.find({"user_id": user_id}, {"_id": 0}).sort("timestamp", -1).to_list(500)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Action", "Feature", "Timestamp", "Details"])
    for item in items:
        writer.writerow(
            [
                item.get("action", ""),
                item.get("feature_key", ""),
                item.get("timestamp", ""),
                str(item.get("details", {})),
            ]
        )
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=action_history.csv"},
    )


# ── Admin Mini-App Management Dashboard ──


@router.get("/actions/admin/mini-apps")
async def admin_mini_apps_dashboard(request: Request):
    """Admin dashboard for Mini-Apps management: usage stats, health, enable/disable."""
    from .db import require_admin

    await require_admin(request)
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    seven_days = (now - timedelta(days=7)).isoformat()

    MINI_APPS = [
        {"id": "platform", "name": "Platform", "category": "Finance", "status": "active"},
        {"id": "job-platform", "name": "Global AI Job Platform", "category": "Employment", "status": "active"},
        {"id": "mobile-money", "name": "Mobile Money", "category": "Finance", "status": "active"},
        {"id": "marketplace", "name": "Marketplace", "category": "Commerce", "status": "active"},
        {"id": "digital-bank", "name": "Digital Bank", "category": "Finance", "status": "active"},
        {"id": "creator-exchange", "name": "Creator Exchange & VC", "category": "Investment", "status": "active"},
        {"id": "film-production", "name": "AI Film Production", "category": "Media", "status": "active"},
        {"id": "video-generator", "name": "AI Video Generator", "category": "Media", "status": "active"},
        {"id": "ai-accounting", "name": "AI Accounting", "category": "Finance", "status": "active"},
        {"id": "drama-box", "name": "AI Drama Box", "category": "Entertainment", "status": "active"},
        {"id": "music-streaming", "name": "AI Music Streaming", "category": "Entertainment", "status": "active"},
        {"id": "local-music", "name": "AI Local Music Player", "category": "Entertainment", "status": "active"},
        {"id": "invoice-generator", "name": "AI Invoice Generator", "category": "Business", "status": "active"},
    ]

    # Check admin config for disabled apps
    config = await db.mini_app_config.find({}, {"_id": 0}).to_list(50)
    config_map = {c["app_id"]: c for c in config}

    # Enrich with usage stats
    for app in MINI_APPS:
        cfg = config_map.get(app["id"], {})
        app["status"] = cfg.get("status", "active")
        app["enabled"] = app["status"] == "active"

        # Usage from action_history
        usage = await db.action_history.count_documents({"feature_key": {"$regex": app["id"], "$options": "i"}})
        recent_usage = await db.action_history.count_documents(
            {"feature_key": {"$regex": app["id"], "$options": "i"}, "timestamp": {"$gte": seven_days}}
        )
        app["total_actions"] = usage
        app["recent_actions_7d"] = recent_usage

    # Overall stats
    total_actions = await db.action_history.count_documents({})
    recent_total = await db.action_history.count_documents({"timestamp": {"$gte": seven_days}})

    # Most used apps
    usage_pipe = [
        {"$group": {"_id": "$feature_key", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    most_used = await db.action_history.aggregate(usage_pipe).to_list(10)

    return {
        "mini_apps": MINI_APPS,
        "stats": {"total_apps": len(MINI_APPS), "total_actions": total_actions, "recent_actions_7d": recent_total},
        "most_used": most_used,
    }


@router.post("/actions/admin/mini-apps/toggle")
async def admin_toggle_mini_app(request: Request):
    """Admin: Enable or disable a Mini-App."""
    from .db import require_admin

    await require_admin(request)

    body = await request.json()
    app_id = body.get("app_id")
    enabled = body.get("enabled", True)

    if not app_id:
        raise HTTPException(status_code=400, detail="app_id required")

    await db.mini_app_config.update_one(
        {"app_id": app_id},
        {
            "$set": {
                "app_id": app_id,
                "status": "active" if enabled else "disabled",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    return {"success": True, "app_id": app_id, "enabled": enabled}


# ── AI Actions Dashboard (Admin Analytics) ──


@router.get("/actions/admin/dashboard")
async def actions_admin_dashboard(request: Request):
    """Admin dashboard showing usage analytics across all AI features."""
    from .db import require_admin

    await require_admin(request)

    from datetime import timedelta

    now = datetime.now(timezone.utc)
    seven_days = (now - timedelta(days=7)).isoformat()
    thirty_days = (now - timedelta(days=30)).isoformat()

    # Total actions
    total_actions = await db.action_history.count_documents({})

    # Actions by type
    action_type_pipe = [
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    action_types = await db.action_history.aggregate(action_type_pipe).to_list(20)

    # Most popular features (by action count)
    feature_pipe = [
        {"$group": {"_id": "$feature_key", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    popular_features = await db.action_history.aggregate(feature_pipe).to_list(20)

    # Daily action trend (last 7 days)
    daily_pipe = [
        {"$match": {"timestamp": {"$gte": seven_days}}},
        {"$addFields": {"date": {"$substr": ["$timestamp", 0, 10]}}},
        {"$group": {"_id": "$date", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    daily_trend = await db.action_history.aggregate(daily_pipe).to_list(7)

    # Export counts (CSV vs PDF)
    export_pipe = [
        {"$match": {"action": "export"}},
        {"$group": {"_id": "$details.format", "count": {"$sum": 1}}},
    ]
    export_stats = await db.action_history.aggregate(export_pipe).to_list(5)

    # Active users (unique users with actions in last 7 days)
    active_users_pipe = [
        {"$match": {"timestamp": {"$gte": seven_days}}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "total"},
    ]
    active_users = await db.action_history.aggregate(active_users_pipe).to_list(1)

    # Scheduled actions stats
    total_scheduled = await db.scheduled_actions.count_documents({})
    pending_scheduled = await db.scheduled_actions.count_documents({"status": "pending"})

    # Saved content stats
    total_saved = await db.user_content.count_documents({"type": "generated"})

    # Top users by action count (last 30 days)
    top_users_pipe = [
        {"$match": {"timestamp": {"$gte": thirty_days}}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_users = await db.action_history.aggregate(top_users_pipe).to_list(10)

    # Enrich top users with email
    for u in top_users:
        user_doc = await db.users.find_one({"user_id": u["_id"]}, {"_id": 0, "email": 1, "name": 1})
        if user_doc:
            u["email"] = user_doc.get("email", "")
            u["name"] = user_doc.get("name", "")

    return {
        "summary": {
            "total_actions": total_actions,
            "active_users_7d": active_users[0]["total"] if active_users else 0,
            "total_scheduled": total_scheduled,
            "pending_scheduled": pending_scheduled,
            "total_saved_content": total_saved,
        },
        "action_types": action_types,
        "popular_features": popular_features,
        "daily_trend": daily_trend,
        "export_stats": export_stats,
        "top_users": top_users,
    }


# ── Admin: Batch Re-categorization ──

# In-memory job state for batch re-categorization
_batch_jobs: dict = {}


@router.get("/admin/batch-categorize/stats")
async def batch_categorize_stats(req: Request):
    """Get stats on uncategorized vs categorized content. Admin-only."""
    await require_admin(req)
    total = await db.user_content.count_documents({})
    uncategorized = await db.user_content.count_documents(
        {"$or": [{"ai_categorized": {"$ne": True}}, {"ai_categorized": {"$exists": False}}]}
    )
    categorized = total - uncategorized

    # Category distribution
    pipeline = [
        {"$match": {"ai_categorized": True}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    cat_dist = await db.user_content.aggregate(pipeline).to_list(20)
    type_pipeline = [
        {"$match": {"ai_categorized": True}},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    type_dist = await db.user_content.aggregate(type_pipeline).to_list(20)

    # Check for running job
    running_job = None
    for jid, j in _batch_jobs.items():
        if j.get("status") == "running":
            running_job = j
            break

    return {
        "total": total,
        "uncategorized": uncategorized,
        "categorized": categorized,
        "category_distribution": [{"category": c["_id"] or "unknown", "count": c["count"]} for c in cat_dist],
        "type_distribution": [{"type": t["_id"] or "unknown", "count": t["count"]} for t in type_dist],
        "running_job": running_job,
    }


@router.post("/admin/batch-categorize/start")
async def start_batch_categorize(req: Request):
    """Start batch re-categorization of all uncategorized content. Admin-only."""
    await require_admin(req)

    # Check if already running
    for jid, j in _batch_jobs.items():
        if j.get("status") == "running":
            return {"error": "A batch job is already running", "job": j}

    job_id = f"batch_{uuid.uuid4().hex[:8]}"
    uncategorized = await db.user_content.count_documents(
        {"$or": [{"ai_categorized": {"$ne": True}}, {"ai_categorized": {"$exists": False}}]}
    )

    job = {
        "job_id": job_id,
        "status": "running",
        "total": uncategorized,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    _batch_jobs[job_id] = job

    # Start background processing
    asyncio.create_task(_run_batch_categorization(job_id))

    return {"success": True, "job": job}


async def _run_batch_categorization(job_id: str):
    """Background task that processes all uncategorized content."""
    job = _batch_jobs.get(job_id)
    if not job:
        return

    try:
        cursor = db.user_content.find(
            {"$or": [{"ai_categorized": {"$ne": True}}, {"ai_categorized": {"$exists": False}}]},
            {"_id": 0, "id": 1, "title": 1, "content": 1, "feature_key": 1},
        )

        async for doc in cursor:
            doc_id = doc.get("id", "")
            title = doc.get("title", "")
            content = doc.get("content", "")
            feature_key = doc.get("feature_key", "")

            if not doc_id:
                job["failed"] += 1
                job["processed"] += 1
                continue

            try:
                await _ai_categorize(doc_id, title, content, feature_key)
                job["succeeded"] += 1
            except Exception as e:
                logger.error(f"Batch categorize failed for {doc_id}: {e}")
                job["failed"] += 1

            job["processed"] += 1

            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"Batch job {job_id} error: {e}")
    finally:
        job["status"] = "completed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"Batch job {job_id} completed: {job['succeeded']}/{job['total']} succeeded, {job['failed']} failed"
        )

        # Notify all admin users
        try:
            admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}).to_list(50)
            now_iso = datetime.now(timezone.utc).isoformat()
            for adm in admins:
                await db.notifications.insert_one(
                    {
                        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                        "user_id": adm["user_id"],
                        "type": "batch_categorization",
                        "title": "Batch Re-categorization Complete",
                        "body": f"{job['succeeded']}/{job['total']} items categorized, {job['failed']} failed.",
                        "message": f"{job['succeeded']}/{job['total']} items categorized, {job['failed']} failed.",
                        "action_url": "/admin-console",
                        "read": False,
                        "created_at": now_iso,
                    }
                )
        except Exception as e:
            logger.error(f"Failed to notify admins about batch job: {e}")


@router.get("/admin/batch-categorize/status/{job_id}")
async def batch_categorize_status(job_id: str, req: Request):
    """Get status of a batch re-categorization job. Admin-only."""
    await require_admin(req)
    job = _batch_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


# ── Nightly Auto-Categorization Schedule ──

SCHEDULE_COLLECTION = "system_settings"
SCHEDULE_KEY = "nightly_auto_categorization"


async def _get_schedule_config():
    """Get nightly auto-categorization config from DB."""
    doc = await db[SCHEDULE_COLLECTION].find_one({"key": SCHEDULE_KEY}, {"_id": 0})
    if not doc:
        # Default: enabled at 2:00 AM UTC
        default = {
            "key": SCHEDULE_KEY,
            "enabled": True,
            "hour": 2,
            "minute": 0,
            "last_run_at": None,
            "last_run_result": None,
        }
        await db[SCHEDULE_COLLECTION].insert_one(default)
        return {k: v for k, v in default.items() if k != "_id"}
    return doc


async def _save_schedule_config(config: dict):
    """Persist schedule config."""
    await db[SCHEDULE_COLLECTION].update_one(
        {"key": SCHEDULE_KEY},
        {"$set": config},
        upsert=True,
    )


@router.get("/admin/auto-categorize/config")
async def get_auto_categorize_config(req: Request):
    """Get nightly auto-categorization schedule config. Admin-only."""
    await require_admin(req)
    config = await _get_schedule_config()
    return config


@router.put("/admin/auto-categorize/config")
async def update_auto_categorize_config(req: Request):
    """Update nightly auto-categorization schedule. Admin-only."""
    await require_admin(req)
    body = await req.json()
    config = await _get_schedule_config()

    if "enabled" in body:
        config["enabled"] = bool(body["enabled"])
    if "hour" in body:
        config["hour"] = max(0, min(23, int(body["hour"])))
    if "minute" in body:
        config["minute"] = max(0, min(59, int(body["minute"])))

    config.pop("_id", None)
    await _save_schedule_config(config)

    return config


async def run_nightly_auto_categorization():
    """Scheduled task: auto-categorize all uncategorized content."""
    config = await _get_schedule_config()
    if not config.get("enabled"):
        logger.info("Nightly auto-categorization is disabled, skipping.")
        return

    query = {"$or": [{"ai_categorized": {"$ne": True}}, {"ai_categorized": {"$exists": False}}]}
    uncategorized = await db.user_content.count_documents(query)

    if uncategorized == 0:
        logger.info("Nightly auto-categorization skipped: no uncategorized items.")
        return

    docs = await db.user_content.find(
        query,
        {"_id": 0, "id": 1, "title": 1, "content": 1, "feature_key": 1},
    ).limit(500).to_list(500)

    processed = 0
    failed = 0
    for doc in docs:
        doc_id = str(doc.get("id") or "").strip()
        if not doc_id:
            continue
        try:
            await _ai_categorize(
                doc_id,
                str(doc.get("title") or ""),
                str(doc.get("content") or ""),
                str(doc.get("feature_key") or "content-library"),
            )
            processed += 1
        except Exception:
            failed += 1

    logger.info(
        "Nightly auto-categorization completed processed=%s failed=%s total_uncategorized=%s",
        processed,
        failed,
        uncategorized,
    )