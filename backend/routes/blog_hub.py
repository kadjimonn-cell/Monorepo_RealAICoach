"""Blog Hub API routes — /api/blog/{videos,demos,testimonials,photos,stats,feed,live}.

Companion to services/blog_service.py (articles). Public, cached-friendly endpoints.
Real-time updates delivered via SSE /api/blog/live.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from routes.db import db
from services.blog_hub_service import (
    get_blog_videos, get_blog_demos, get_blog_testimonials, get_blog_photos,
    get_blog_stats, seed_blog_hub_if_empty,
)
from services.blog_service import get_blog_posts

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/blog/videos")
async def list_videos(category: str = Query("All")):
    items = await get_blog_videos(db, category if category != "All" else None)
    return JSONResponse({"items": items, "count": len(items),
                         "served_at": datetime.now(timezone.utc).isoformat()})


@router.get("/blog/demos")
async def list_demos(category: str = Query("All")):
    items = await get_blog_demos(db, category if category != "All" else None)
    return JSONResponse({"items": items, "count": len(items),
                         "served_at": datetime.now(timezone.utc).isoformat()})


@router.get("/blog/testimonials")
async def list_testimonials(country: str = Query("All")):
    items = await get_blog_testimonials(db, country if country != "All" else None)
    return JSONResponse({"items": items, "count": len(items),
                         "served_at": datetime.now(timezone.utc).isoformat()})


@router.get("/blog/photos")
async def list_photos(category: str = Query("All")):
    items = await get_blog_photos(db, category if category != "All" else None)
    return JSONResponse({"items": items, "count": len(items),
                         "served_at": datetime.now(timezone.utc).isoformat()})


@router.get("/blog/stats")
async def blog_stats():
    return JSONResponse(await get_blog_stats(db))


# ── Latest AI-generated hub drop (badge source) ───────────────────────────────
# Surfaces the most recent `source: "ai_generated"` row across the 4 hub
# collections, sorted by published_at desc. Powers the "Fresh AI drop" badge
# on /blog and is also pushed over the SSE stream as `latest_drop`.
_DROP_KIND_MAP = {
    "blog_videos": "video",
    "blog_demos": "demo",
    "blog_testimonials": "testimonial",
    "blog_photos": "photo",
}


async def _fetch_latest_drop(database=None) -> Optional[dict]:
    """Return the newest AI-generated hub row across the 4 collections.

    `database` defaults to the module-level `db`, but can be overridden so
    tests can pass in a fresh Motor client bound to their own event loop.
    """
    _db = database if database is not None else db
    best: Optional[dict] = None
    for col, kind in _DROP_KIND_MAP.items():
        doc = await _db[col].find_one(
            {"source": "ai_generated"},
            {"_id": 0},
            sort=[("published_at", -1)],
        )
        if not doc:
            continue
        published_at = doc.get("published_at") or ""
        if best and (best.get("published_at") or "") >= published_at:
            continue
        # Per-kind display normalization so the frontend pill can render any type.
        if kind == "testimonial":
            title = doc.get("full_name") or doc.get("title") or "New success story"
            image = doc.get("photo")
            category = doc.get("country") or "Testimonials"
            href = "/blog?tab=testimonials"
        elif kind == "photo":
            title = doc.get("caption") or "Hub photo drop"
            image = doc.get("image")
            category = doc.get("category") or "Photos"
            href = "/blog?tab=photos"
        elif kind == "demo":
            title = doc.get("title") or "New product demo"
            image = doc.get("image")
            category = doc.get("category") or "Demos"
            href = doc.get("cta_url") or "/blog?tab=demos"
        else:  # video
            title = doc.get("title") or "New video"
            image = doc.get("thumbnail")
            category = doc.get("category") or "Videos"
            href = "/blog?tab=videos"
        best = {
            "kind": kind,
            "slug": doc.get("slug"),
            "title": title,
            "image": image,
            "category": category,
            "href": href,
            "published_at": published_at,
            "date_display": doc.get("date_display"),
            "source": "ai_generated",
            "auto_week_key": doc.get("auto_week_key"),
        }
    return best


@router.get("/blog/latest-drop")
async def blog_latest_drop():
    drop = await _fetch_latest_drop()
    return JSONResponse({
        "drop": drop,
        "served_at": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/blog/feed")
async def unified_feed(
    tab: str = Query("all", description="all|articles|videos|demos|testimonials|photos"),
    limit: int = Query(24, ge=1, le=100),
):
    """Unified feed that merges all content types sorted by recency."""
    await seed_blog_hub_if_empty(db)
    out: list[dict] = []
    if tab in ("all", "articles"):
        for p in await get_blog_posts(db):
            out.append({"kind": "article", "data": p,
                        "published_at": p.get("published_at", "")})
    if tab in ("all", "videos"):
        for v in await get_blog_videos(db):
            out.append({"kind": "video", "data": v,
                        "published_at": v.get("published_at", "")})
    if tab in ("all", "demos"):
        for d in await get_blog_demos(db):
            out.append({"kind": "demo", "data": d,
                        "published_at": d.get("published_at", "")})
    if tab in ("all", "testimonials"):
        for t in await get_blog_testimonials(db):
            out.append({"kind": "testimonial", "data": t,
                        "published_at": t.get("published_at", "")})
    if tab in ("all", "photos"):
        for ph in await get_blog_photos(db):
            out.append({"kind": "photo", "data": ph,
                        "published_at": ph.get("published_at", "")})
    out.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return JSONResponse({"items": out[:limit], "count": len(out),
                         "served_at": datetime.now(timezone.utc).isoformat()})


@router.get("/blog/live")
async def live_stream(request: Request):
    """SSE real-time feed. Pushes a `stats` event every 30s and a `ping` every 10s.
    Clients listen for `new_item` to know when to re-fetch the feed, and for
    `latest_drop` to render the "Fresh AI drop" badge without extra polling."""
    async def event_gen():
        last_total = -1
        last_drop_slug: Optional[str] = None
        while True:
            if await request.is_disconnected():
                break
            stats = await get_blog_stats(db)
            total = (stats["articles"] + stats["videos"] + stats["demos"]
                     + stats["testimonials"] + stats["photos"])
            if last_total != -1 and total != last_total:
                yield f"event: new_item\ndata: {json.dumps(stats)}\n\n"
            last_total = total
            yield f"event: stats\ndata: {json.dumps(stats)}\n\n"
            drop = await _fetch_latest_drop()
            if drop and drop.get("slug") != last_drop_slug:
                last_drop_slug = drop.get("slug")
                yield f"event: latest_drop\ndata: {json.dumps(drop)}\n\n"
            for _ in range(3):
                if await request.is_disconnected():
                    break
                await asyncio.sleep(10)
                yield "event: ping\ndata: {}\n\n"
    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
