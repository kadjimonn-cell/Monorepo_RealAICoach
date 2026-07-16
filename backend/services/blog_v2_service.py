"""Enterprise Blog V2 domain service.

Builds on top of existing blog seed/content, adds:
- Unified home/list/detail search models
- Author profiles
- Reading history + bookmarks
- Premium insight gating
- AI summaries/recommendation ranking (GPT-5.2 with deterministic fallbacks)
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.blog_service import BLOG_SEED_POSTS, generate_fresh_dates
from services.blog_v2_engagement_service import (
    build_public_engagement_preview,
    record_owner_read_event,
    get_owner_engagement_loop,
    get_owner_unlocked_post_ids,
)
from utils.llm_helper import generate_verified_json


BLOG_V2_POSTS = "blog_v2_posts"
BLOG_V2_AUTHORS = "blog_v2_authors"
BLOG_V2_HISTORY = "blog_v2_history"
BLOG_V2_BOOKMARKS = "blog_v2_bookmarks"
BLOG_V2_AI_CACHE = "blog_v2_ai_cache"

MEMBER_PLANS = {"basic", "premium", "admin"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\s-]", "", str(value or "")).strip().lower()
    return re.sub(r"[-\s]+", "-", normalized).strip("-") or "unknown"


def _is_member(plan: str) -> bool:
    return str(plan or "free").lower() in MEMBER_PLANS


def _read_minutes(read_time: str) -> int:
    if not read_time:
        return 6
    m = re.search(r"(\d+)", str(read_time))
    if not m:
        return 6
    try:
        return max(2, int(m.group(1)))
    except Exception:
        return 6


def _author_avatar(author_name: str) -> str:
    seed = _slugify(author_name)
    return f"https://api.dicebear.com/9.x/initials/svg?seed={seed}"


def _premium_sections_for_post(post: Dict[str, Any]) -> List[Dict[str, Any]]:
    tags = [str(tag).strip() for tag in (post.get("tags") or []) if str(tag).strip()]
    cat = str(post.get("category") or "General")
    excerpt = str(post.get("excerpt") or "").strip()
    title = str(post.get("title") or "").strip()

    return [
        {
            "heading": "Strategic Breakdown",
            "content": f"Framework-level analysis for '{title}' with measurable outcomes and operational risks.",
        },
        {
            "heading": "Implementation Playbook",
            "content": f"7-day rollout checklist tuned for {cat.lower()} teams using guardrailed execution steps.",
        },
        {
            "heading": "Signal Watchlist",
            "content": f"Early success/failure indicators from themes: {', '.join(tags[:4]) or 'execution, quality, retention'}.",
        },
        {
            "heading": "Executive Summary",
            "content": excerpt[:240] or "Action-oriented summary focused on adoption, activation, and retention impact.",
        },
    ]


def _normalize_content_blocks(raw: Any, excerpt: str) -> List[Dict[str, str]]:
    if isinstance(raw, list) and raw:
        blocks: List[Dict[str, str]] = []
        for row in raw:
            if isinstance(row, dict):
                block_type = str(row.get("type") or "paragraph")
                text = str(row.get("content") or row.get("text") or "").strip()
                if text:
                    blocks.append({"type": block_type, "text": text})
            elif isinstance(row, str) and row.strip():
                blocks.append({"type": "paragraph", "text": row.strip()})
        if blocks:
            return blocks

    fallback = [
        {"type": "paragraph", "text": excerpt or "Detailed insight from the RealAICoach editorial team."},
        {
            "type": "paragraph",
            "text": "This article explains practical implementation steps with realistic benchmarks and operating guardrails.",
        },
        {
            "type": "paragraph",
            "text": "Use this blueprint to execute quickly while maintaining trust, quality, and long-term retention signals.",
        },
    ]
    return fallback


def _post_card(doc: Dict[str, Any], viewer_plan: str, bookmarked: bool = False) -> Dict[str, Any]:
    premium_required = bool(doc.get("premium_required"))
    return {
        "post_id": doc.get("post_id"),
        "slug": doc.get("slug"),
        "title": doc.get("title"),
        "excerpt": doc.get("excerpt"),
        "cover_image": doc.get("cover_image"),
        "category": doc.get("category"),
        "tags": doc.get("tags") or [],
        "author_name": doc.get("author_name"),
        "author_slug": doc.get("author_slug"),
        "author_role": doc.get("author_role"),
        "published_at": doc.get("published_at"),
        "date_display": doc.get("date_display"),
        "read_time_minutes": int(doc.get("read_time_minutes") or 6),
        "metrics": doc.get("metrics") or {},
        "premium_required": premium_required,
        "premium_locked": premium_required and not _is_member(viewer_plan),
        "bookmarked": bookmarked,
    }


def _detail_payload(doc: Dict[str, Any], viewer_plan: str, bookmarked: bool = False) -> Dict[str, Any]:
    base = _post_card(doc, viewer_plan, bookmarked=bookmarked)
    full_blocks = doc.get("content_blocks") or []
    premium_sections = doc.get("premium_sections") or []
    premium_required = bool(doc.get("premium_required"))
    can_unlock = _is_member(viewer_plan)
    preview_blocks = full_blocks[:3] if len(full_blocks) > 3 else full_blocks

    base.update(
        {
            "content_blocks": full_blocks,
            "preview_blocks": preview_blocks,
            "premium_sections": premium_sections if can_unlock else [],
            "premium_preview": premium_sections[:1],
            "premium_gate": {
                "required": premium_required,
                "unlocked": (not premium_required) or can_unlock,
                "cta": "Upgrade to access full premium insights and action playbooks.",
            },
            "meta": doc.get("meta") or {},
        }
    )
    return base


def _author_payload(author_doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "author_slug": author_doc.get("author_slug"),
        "name": author_doc.get("name"),
        "role": author_doc.get("role"),
        "bio": author_doc.get("bio"),
        "avatar_url": author_doc.get("avatar_url"),
        "focus_areas": author_doc.get("focus_areas") or [],
        "stats": author_doc.get("stats") or {},
        "social": author_doc.get("social") or {},
    }


def _source_posts_for_seed() -> List[Dict[str, Any]]:
    return generate_fresh_dates(BLOG_SEED_POSTS)


def _normalized_seed_posts() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, post in enumerate(_source_posts_for_seed(), start=1):
        author_name = str(post.get("author") or "RealAICoach Editorial")
        author_slug = _slugify(author_name)
        title = str(post.get("title") or f"Blog Post {idx}")
        excerpt = str(post.get("excerpt") or "")
        category = str(post.get("category") or "General")
        premium_required = idx % 3 == 0 or category.lower() in {"business", "career"}

        out.append(
            {
                "post_id": f"blogv2-{idx:04d}",
                "slug": str(post.get("slug") or _slugify(title)),
                "title": title,
                "excerpt": excerpt,
                "cover_image": str(post.get("image") or "").strip(),
                "category": category,
                "tags": [str(tag).strip() for tag in (post.get("tags") or []) if str(tag).strip()],
                "author_name": author_name,
                "author_slug": author_slug,
                "author_role": str(post.get("author_role") or "Senior Analyst"),
                "published_at": post.get("published_at") or _now_iso(),
                "date_display": str(post.get("date_display") or ""),
                "read_time_minutes": _read_minutes(post.get("read_time") or "6 min read"),
                "content_blocks": _normalize_content_blocks(post.get("content"), excerpt),
                "premium_sections": _premium_sections_for_post(post),
                "premium_required": premium_required,
                "metrics": {
                    "views": int(post.get("views") or 0),
                    "bookmarks": int(post.get("bookmarks") or 0),
                    "shares": int(post.get("shares") or 0),
                },
                "meta": {
                    "source": "blog_service_seed",
                    "seed_version": "v2-enterprise",
                    "created_at": _now_iso(),
                },
                "status": "published",
                "active": True,
            }
        )
    return out


async def ensure_blog_v2_seed(db) -> None:
    post_coll = db[BLOG_V2_POSTS]
    author_coll = db[BLOG_V2_AUTHORS]

    await post_coll.create_index("post_id", unique=True)
    await post_coll.create_index("slug", unique=True)
    await post_coll.create_index("published_at")
    await post_coll.create_index("category")
    await post_coll.create_index("author_slug")
    await post_coll.create_index([("title", "text"), ("excerpt", "text"), ("tags", "text")])

    await author_coll.create_index("author_slug", unique=True)

    await db[BLOG_V2_HISTORY].create_index([("owner_id", 1), ("post_id", 1)], unique=True)
    await db[BLOG_V2_BOOKMARKS].create_index([("owner_id", 1), ("post_id", 1)], unique=True)
    await db[BLOG_V2_AI_CACHE].create_index("cache_key", unique=True)
    await db[BLOG_V2_AI_CACHE].create_index("expires_at")

    existing = await post_coll.count_documents({})
    if existing == 0:
        await post_coll.insert_many(_normalized_seed_posts())

    author_count = await author_coll.count_documents({})
    if author_count > 0:
        return

    posts = await post_coll.find({"active": True}, {"_id": 0}).to_list(length=500)
    by_author: Dict[str, Dict[str, Any]] = {}
    for row in posts:
        slug = str(row.get("author_slug") or _slugify(row.get("author_name") or "editorial"))
        bucket = by_author.setdefault(
            slug,
            {
                "author_slug": slug,
                "name": str(row.get("author_name") or "RealAICoach Editorial"),
                "role": str(row.get("author_role") or "Senior Analyst"),
                "bio": "Writes practical, experiment-backed guides for high-impact execution.",
                "avatar_url": _author_avatar(str(row.get("author_name") or slug)),
                "focus_areas": [],
                "stats": {"posts": 0, "total_views": 0},
                "social": {
                    "linkedin": f"https://www.linkedin.com/in/{slug}",
                    "x": f"https://x.com/{slug.replace('-', '')}",
                },
            },
        )

        bucket["stats"]["posts"] += 1
        bucket["stats"]["total_views"] += int((row.get("metrics") or {}).get("views") or 0)

        category = str(row.get("category") or "General")
        if category not in bucket["focus_areas"] and len(bucket["focus_areas"]) < 5:
            bucket["focus_areas"].append(category)

    for author in by_author.values():
        await author_coll.update_one(
            {"author_slug": author["author_slug"]},
            {"$set": author, "$setOnInsert": {"created_at": _now_iso()}},
            upsert=True,
        )


async def publish_due_scheduled_posts(db) -> int:
    """Auto-publish scheduled posts whose publish time has passed."""
    now = _now_iso()
    result = await db[BLOG_V2_POSTS].update_many(
        {"status": "scheduled", "scheduled_publish_at": {"$ne": None, "$lte": now}},
        [{"$set": {"status": "published", "published_at": "$scheduled_publish_at", "updated_at": now}}],
    )
    return int(result.modified_count or 0)


async def _bookmarked_post_ids(db, owner_id: Optional[str]) -> set[str]:
    if not owner_id:
        return set()
    rows = await db[BLOG_V2_BOOKMARKS].find({"owner_id": owner_id}, {"_id": 0, "post_id": 1}).to_list(length=1000)
    return {str(r.get("post_id")) for r in rows if r.get("post_id")}


async def list_posts(
    db,
    *,
    viewer_plan: str,
    owner_id: Optional[str] = None,
    query: str = "",
    category: str = "",
    tag: str = "",
    author_slug: str = "",
    page: int = 1,
    page_size: int = 12,
    sort: str = "latest",
) -> Dict[str, Any]:
    await ensure_blog_v2_seed(db)

    filters: Dict[str, Any] = {"active": True, "status": "published"}
    await publish_due_scheduled_posts(db)
    if category and category.lower() != "all":
        filters["category"] = category
    if author_slug:
        filters["author_slug"] = author_slug
    if tag:
        filters["tags"] = tag

    q = str(query or "").strip()
    if q:
        safe = re.escape(q)
        regex = {"$regex": safe, "$options": "i"}
        filters["$or"] = [
            {"title": regex},
            {"excerpt": regex},
            {"category": regex},
            {"tags": regex},
            {"author_name": regex},
        ]

    page = max(1, int(page or 1))
    page_size = max(1, min(24, int(page_size or 12)))
    skip = (page - 1) * page_size

    sort_spec = [("published_at", -1)]
    if sort == "popular":
        sort_spec = [("metrics.views", -1), ("published_at", -1)]
    elif sort == "bookmarked":
        sort_spec = [("metrics.bookmarks", -1), ("published_at", -1)]

    total = await db[BLOG_V2_POSTS].count_documents(filters)
    rows = (
        await db[BLOG_V2_POSTS]
        .find(filters, {"_id": 0})
        .sort(sort_spec)
        .skip(skip)
        .limit(page_size)
        .to_list(length=page_size)
    )

    bookmarked_ids = await _bookmarked_post_ids(db, owner_id)
    cards = [_post_card(r, viewer_plan, bookmarked=str(r.get("post_id")) in bookmarked_ids) for r in rows]

    return {
        "items": cards,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (skip + len(cards)) < total,
    }


async def get_post_detail(
    db,
    *,
    slug: str,
    viewer_plan: str,
    owner_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    await ensure_blog_v2_seed(db)
    doc = await db[BLOG_V2_POSTS].find_one({"slug": slug, "active": True}, {"_id": 0})
    if not doc:
        return None

    bookmarked = False
    if owner_id:
        bookmarked = (
            await db[BLOG_V2_BOOKMARKS].count_documents({"owner_id": owner_id, "post_id": doc.get("post_id")}) > 0
        )

    detail = _detail_payload(doc, viewer_plan=viewer_plan, bookmarked=bookmarked)

    unlocked_ids: set[str] = set()
    if owner_id:
        unlocked_ids = await get_owner_unlocked_post_ids(db, owner_id)

    if owner_id and bool(doc.get("premium_required")):
        if str(doc.get("post_id") or "") in unlocked_ids:
            detail["premium_gate"] = {
                "required": True,
                "unlocked": True,
                "cta": "Unlocked via token",
            }
            detail["premium_sections"] = doc.get("premium_sections") or []

    if owner_id:
        detail["token_unlocked"] = str(doc.get("post_id") or "") in unlocked_ids
    else:
        detail["token_unlocked"] = False

    author_doc = await db[BLOG_V2_AUTHORS].find_one({"author_slug": detail.get("author_slug")}, {"_id": 0})
    if author_doc:
        detail["author"] = _author_payload(author_doc)

    related = await db[BLOG_V2_POSTS].find(
        {
            "active": True,
            "slug": {"$ne": slug},
            "$or": [
                {"category": detail.get("category")},
                {"tags": {"$in": detail.get("tags") or []}},
            ],
        },
        {"_id": 0},
    ).sort("published_at", -1).limit(4).to_list(length=4)
    detail["related_posts"] = [_post_card(r, viewer_plan, bookmarked=False) for r in related]

    await db[BLOG_V2_POSTS].update_one(
        {"post_id": doc.get("post_id")},
        {
            "$inc": {"metrics.views": 1},
            "$set": {"meta.last_viewed_at": _now_iso()},
        },
    )

    return detail


async def get_author_profile(db, *, author_slug: str, viewer_plan: str) -> Optional[Dict[str, Any]]:
    await ensure_blog_v2_seed(db)
    author = await db[BLOG_V2_AUTHORS].find_one({"author_slug": author_slug}, {"_id": 0})
    if not author:
        return None

    posts = await db[BLOG_V2_POSTS].find(
        {"active": True, "author_slug": author_slug}, {"_id": 0}
    ).sort("published_at", -1).limit(24).to_list(length=24)

    return {
        "author": _author_payload(author),
        "posts": [_post_card(p, viewer_plan=viewer_plan, bookmarked=False) for p in posts],
    }


async def get_home_payload(db, *, viewer_plan: str, owner_id: Optional[str]) -> Dict[str, Any]:
    await publish_due_scheduled_posts(db)
    await ensure_blog_v2_seed(db)

    featured_doc = await db[BLOG_V2_POSTS].find_one({"active": True}, {"_id": 0}, sort=[("published_at", -1)])
    trending_docs = (
        await db[BLOG_V2_POSTS]
        .find({"active": True}, {"_id": 0})
        .sort([("metrics.views", -1), ("published_at", -1)])
        .limit(6)
        .to_list(length=6)
    )
    latest_docs = (
        await db[BLOG_V2_POSTS]
        .find({"active": True}, {"_id": 0})
        .sort("published_at", -1)
        .limit(12)
        .to_list(length=12)
    )
    authors = await db[BLOG_V2_AUTHORS].find({}, {"_id": 0}).sort("stats.posts", -1).limit(8).to_list(length=8)

    bookmarked_ids = await _bookmarked_post_ids(db, owner_id)
    featured = _post_card(featured_doc, viewer_plan, bookmarked=featured_doc.get("post_id") in bookmarked_ids) if featured_doc else None
    trending = [_post_card(r, viewer_plan, bookmarked=r.get("post_id") in bookmarked_ids) for r in trending_docs]
    latest = [_post_card(r, viewer_plan, bookmarked=r.get("post_id") in bookmarked_ids) for r in latest_docs]

    categories = await db[BLOG_V2_POSTS].aggregate(
        [
            {"$match": {"active": True}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1, "_id": 1}},
        ]
    ).to_list(length=40)

    total_views = sum(int((x.get("metrics") or {}).get("views") or 0) for x in latest_docs)
    total_bookmarks = sum(int((x.get("metrics") or {}).get("bookmarks") or 0) for x in latest_docs)

    engagement_loop = (
        await get_owner_engagement_loop(db, owner_id, viewer_plan)
        if owner_id
        else build_public_engagement_preview()
    )

    return {
        "featured": featured,
        "trending": trending,
        "latest": latest,
        "categories": [{"name": c.get("_id") or "General", "count": int(c.get("count") or 0)} for c in categories],
        "authors": [_author_payload(a) for a in authors],
        "stats": {
            "total_posts": await db[BLOG_V2_POSTS].count_documents({"active": True}),
            "total_views": total_views,
            "total_bookmarks": total_bookmarks,
            "last_refreshed_at": _now_iso(),
        },
        "engagement_loop": engagement_loop,
    }


async def write_history(
    db,
    *,
    owner_id: str,
    viewer_plan: str,
    post_id: str,
    progress_percent: int,
    dwell_seconds: int,
) -> Dict[str, Any]:
    await ensure_blog_v2_seed(db)

    progress = max(0, min(100, int(progress_percent or 0)))
    dwell = max(0, min(36000, int(dwell_seconds or 0)))

    await db[BLOG_V2_HISTORY].update_one(
        {"owner_id": owner_id, "post_id": post_id},
        {
            "$set": {
                "owner_id": owner_id,
                "post_id": post_id,
                "progress_percent": progress,
                "dwell_seconds": dwell,
                "updated_at": _now_iso(),
            },
            "$setOnInsert": {"created_at": _now_iso()},
        },
        upsert=True,
    )
    loop = await record_owner_read_event(db, owner_id, viewer_plan)
    return {
        "ok": True,
        "post_id": post_id,
        "progress_percent": progress,
        "engagement_loop": loop,
    }


async def get_history(db, *, owner_id: str, viewer_plan: str) -> List[Dict[str, Any]]:
    await ensure_blog_v2_seed(db)

    rows = await db[BLOG_V2_HISTORY].find(
        {"owner_id": owner_id}, {"_id": 0}
    ).sort("updated_at", -1).limit(24).to_list(length=24)
    if not rows:
        return []

    post_ids = [str(r.get("post_id")) for r in rows if r.get("post_id")]
    post_docs = await db[BLOG_V2_POSTS].find({"post_id": {"$in": post_ids}, "active": True}, {"_id": 0}).to_list(length=64)
    post_map = {str(doc.get("post_id")): doc for doc in post_docs}

    ordered: List[Dict[str, Any]] = []
    for row in rows:
        doc = post_map.get(str(row.get("post_id")))
        if not doc:
            continue
        card = _post_card(doc, viewer_plan=viewer_plan, bookmarked=False)
        card["history"] = {
            "progress_percent": int(row.get("progress_percent") or 0),
            "dwell_seconds": int(row.get("dwell_seconds") or 0),
            "updated_at": row.get("updated_at"),
        }
        ordered.append(card)
    return ordered


async def add_bookmark(db, *, owner_id: str, post_id: str) -> Dict[str, Any]:
    await ensure_blog_v2_seed(db)

    post = await db[BLOG_V2_POSTS].find_one({"post_id": post_id, "active": True}, {"_id": 0, "post_id": 1})
    if not post:
        return {"ok": False, "error": "post_not_found"}

    await db[BLOG_V2_BOOKMARKS].update_one(
        {"owner_id": owner_id, "post_id": post_id},
        {
            "$set": {"owner_id": owner_id, "post_id": post_id, "updated_at": _now_iso()},
            "$setOnInsert": {"created_at": _now_iso()},
        },
        upsert=True,
    )

    await db[BLOG_V2_POSTS].update_one({"post_id": post_id}, {"$inc": {"metrics.bookmarks": 1}})
    return {"ok": True, "post_id": post_id, "bookmarked": True}


async def remove_bookmark(db, *, owner_id: str, post_id: str) -> Dict[str, Any]:
    await ensure_blog_v2_seed(db)
    deleted = await db[BLOG_V2_BOOKMARKS].delete_one({"owner_id": owner_id, "post_id": post_id})
    if deleted.deleted_count > 0:
        await db[BLOG_V2_POSTS].update_one({"post_id": post_id}, {"$inc": {"metrics.bookmarks": -1}})
    return {"ok": True, "post_id": post_id, "bookmarked": False}


async def get_bookmarks(db, *, owner_id: str, viewer_plan: str) -> List[Dict[str, Any]]:
    await ensure_blog_v2_seed(db)

    rows = await db[BLOG_V2_BOOKMARKS].find(
        {"owner_id": owner_id}, {"_id": 0}
    ).sort("updated_at", -1).limit(48).to_list(length=48)

    post_ids = [str(r.get("post_id")) for r in rows if r.get("post_id")]
    if not post_ids:
        return []

    docs = await db[BLOG_V2_POSTS].find({"post_id": {"$in": post_ids}, "active": True}, {"_id": 0}).to_list(length=96)
    by_id = {str(d.get("post_id")): d for d in docs}

    out: List[Dict[str, Any]] = []
    for row in rows:
        doc = by_id.get(str(row.get("post_id")))
        if not doc:
            continue
        out.append(_post_card(doc, viewer_plan=viewer_plan, bookmarked=True))
    return out


def _recommendation_score(doc: Dict[str, Any], category_hits: Dict[str, int], tag_hits: Dict[str, int]) -> int:
    score = 0
    category = str(doc.get("category") or "")
    score += int(category_hits.get(category, 0)) * 4
    tags = [str(t) for t in (doc.get("tags") or [])]
    for tag in tags:
        score += int(tag_hits.get(tag, 0)) * 2
    score += int((doc.get("metrics") or {}).get("views") or 0) // 100
    return score


async def get_recommendations(
    db,
    *,
    owner_id: Optional[str],
    viewer_plan: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    await ensure_blog_v2_seed(db)
    limit = max(1, min(12, int(limit or 8)))

    history = []
    bookmarks = []
    if owner_id:
        history = await db[BLOG_V2_HISTORY].find({"owner_id": owner_id}, {"_id": 0}).limit(24).to_list(length=24)
        bookmarks = await db[BLOG_V2_BOOKMARKS].find({"owner_id": owner_id}, {"_id": 0}).limit(24).to_list(length=24)

    seed_post_ids = {str(x.get("post_id")) for x in history + bookmarks if x.get("post_id")}
    docs = await db[BLOG_V2_POSTS].find({"active": True}, {"_id": 0}).limit(200).to_list(length=200)

    category_hits: Dict[str, int] = {}
    tag_hits: Dict[str, int] = {}
    for seed_id in seed_post_ids:
        doc = next((d for d in docs if str(d.get("post_id")) == seed_id), None)
        if not doc:
            continue
        category = str(doc.get("category") or "")
        if category:
            category_hits[category] = category_hits.get(category, 0) + 1
        for tag in doc.get("tags") or []:
            t = str(tag)
            tag_hits[t] = tag_hits.get(t, 0) + 1

    candidates = [doc for doc in docs if str(doc.get("post_id")) not in seed_post_ids]
    candidates.sort(key=lambda d: _recommendation_score(d, category_hits, tag_hits), reverse=True)
    chosen = candidates[:limit] if candidates else docs[:limit]
    return [_post_card(c, viewer_plan=viewer_plan, bookmarked=False) for c in chosen]


async def get_ai_summary(
    db,
    *,
    slug: str,
    viewer_plan: str,
    owner_id: Optional[str],
) -> Dict[str, Any]:
    await ensure_blog_v2_seed(db)
    post = await db[BLOG_V2_POSTS].find_one({"slug": slug, "active": True}, {"_id": 0})
    if not post:
        return {"ok": False, "error": "post_not_found"}

    post_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "slug": post.get("slug"),
                "title": post.get("title"),
                "excerpt": post.get("excerpt"),
                "content_blocks": (post.get("content_blocks") or [])[:6],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    plan_bucket = "member" if _is_member(viewer_plan) else "free"
    cache_key = f"summary::{slug}::{plan_bucket}::{post_fingerprint}"
    cached = await db[BLOG_V2_AI_CACHE].find_one({"cache_key": cache_key}, {"_id": 0})
    if cached and str(cached.get("expires_at") or "") > _now_iso():
        return {
            "ok": True,
            "cached": True,
            "model": cached.get("model") or "gpt-5.2",
            "summary": cached.get("summary") or "",
            "key_takeaways": cached.get("key_takeaways") or [],
        }

    system_message = (
        "You are a principal content strategist. Produce concise, actionable summaries for professionals. "
        "Return strict JSON with keys: summary, key_takeaways (array of 3-5 strings), and action_plan (array of 3 strings)."
    )
    prompt = (
        f"Title: {post.get('title')}\n"
        f"Excerpt: {post.get('excerpt')}\n"
        f"Category: {post.get('category')}\n"
        f"Tags: {', '.join(post.get('tags') or [])}\n"
        f"Content: {json.dumps((post.get('content_blocks') or [])[:6], ensure_ascii=False)}\n"
        "Audience: subscription users looking for implementation clarity and business outcomes."
    )

    session_id = f"blog-v2-summary-{slug}-{(owner_id or 'anon')[:32]}"
    fallback_takeaways = [
        "Use the featured framework as a weekly execution checklist.",
        "Track adoption and retention signals before scaling.",
        "Prioritize low-friction rollout steps to de-risk implementation.",
    ]
    payload: Dict[str, Any]

    try:
        llm_json = await generate_verified_json(
            prompt=prompt,
            system_message=system_message,
            session_id=session_id,
            model="gpt-5.2",
            feature="blog_v2_ai_summary",
            user_id=owner_id,
        )
        payload = {
            "summary": str(llm_json.get("summary") or "").strip(),
            "key_takeaways": [str(x).strip() for x in (llm_json.get("key_takeaways") or []) if str(x).strip()][:5],
            "action_plan": [str(x).strip() for x in (llm_json.get("action_plan") or []) if str(x).strip()][:3],
        }
    except Exception:
        payload = {
            "summary": (
                f"{post.get('title')}: high-signal execution guidance focused on measurable outcomes, "
                "risk controls, and practical rollout sequencing."
            ),
            "key_takeaways": fallback_takeaways,
            "action_plan": [
                "Pick one section and convert it into a same-week experiment.",
                "Define success metrics before implementation.",
                "Review result signals and iterate within 7 days.",
            ],
        }

    if not _is_member(viewer_plan):
        payload["summary"] = payload["summary"][:260].rstrip() + "…"
        payload["key_takeaways"] = payload["key_takeaways"][:2]

    expires_at = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    await db[BLOG_V2_AI_CACHE].update_one(
        {"cache_key": cache_key},
        {
            "$set": {
                "cache_key": cache_key,
                "slug": slug,
                "summary": payload.get("summary") or "",
                "key_takeaways": payload.get("key_takeaways") or [],
                "action_plan": payload.get("action_plan") or [],
                "model": "gpt-5.2",
                "expires_at": expires_at,
                "updated_at": _now_iso(),
            },
            "$setOnInsert": {"created_at": _now_iso()},
        },
        upsert=True,
    )

    return {
        "ok": True,
        "cached": False,
        "model": "gpt-5.2",
        "summary": payload.get("summary") or "",
        "key_takeaways": payload.get("key_takeaways") or [],
        "action_plan": payload.get("action_plan") or [],
        "upgrade_required": not _is_member(viewer_plan),
    }
