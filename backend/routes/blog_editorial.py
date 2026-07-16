"""Blog Phase P2 — Enterprise editorial workflow (Draft -> Review -> Publish -> Schedule)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.blog_v2_service import (
    BLOG_V2_POSTS,
    _normalize_content_blocks,
    _slugify,
    publish_due_scheduled_posts,
)

from .db import db, require_admin

router = APIRouter(prefix="/admin/blog-editorial", tags=["Blog Editorial"])

WORKFLOW_STATUSES = ["draft", "in_review", "scheduled", "published"]

TRANSITIONS: dict[str, dict[str, Any]] = {
    "submit_review": {"from": ["draft"], "to": "in_review"},
    "approve_publish": {"from": ["in_review", "scheduled"], "to": "published"},
    "schedule": {"from": ["in_review"], "to": "scheduled"},
    "revert_draft": {"from": ["in_review", "scheduled"], "to": "draft"},
    "unpublish": {"from": ["published"], "to": "draft"},
}

SUMMARY_PROJECTION = {
    "_id": 0,
    "post_id": 1,
    "slug": 1,
    "title": 1,
    "excerpt": 1,
    "category": 1,
    "status": 1,
    "premium_required": 1,
    "author_name": 1,
    "published_at": 1,
    "scheduled_publish_at": 1,
    "updated_at": 1,
    "workflow_history": 1,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EditorialPostCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    excerpt: str = Field(default="", max_length=600)
    category: str = Field(default="General", max_length=80)
    tags: list[str] = Field(default_factory=list)
    content: str = Field(default="", max_length=60_000)
    cover_image: str = Field(default="", max_length=1000)
    premium_required: bool = False


class EditorialPostUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    excerpt: Optional[str] = Field(default=None, max_length=600)
    category: Optional[str] = Field(default=None, max_length=80)
    tags: Optional[list[str]] = None
    content: Optional[str] = Field(default=None, max_length=60_000)
    cover_image: Optional[str] = Field(default=None, max_length=1000)
    premium_required: Optional[bool] = None


class EditorialTransition(BaseModel):
    action: str
    publish_at: Optional[str] = None


async def _unique_slug(title: str) -> str:
    base = _slugify(title) or f"post-{uuid.uuid4().hex[:6]}"
    slug = base
    suffix = 2
    while await db[BLOG_V2_POSTS].count_documents({"slug": slug}, limit=1):
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


@router.get("/posts")
async def list_editorial_posts(
    request: Request,
    status: str = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=300),
):
    await require_admin(request)
    published = await publish_due_scheduled_posts(db)

    filters: dict[str, Any] = {"active": True}
    if status != "all":
        if status not in WORKFLOW_STATUSES:
            raise HTTPException(status_code=400, detail="Unknown workflow status")
        filters["status"] = status

    rows = (
        await db[BLOG_V2_POSTS]
        .find(filters, SUMMARY_PROJECTION)
        .sort([("updated_at", -1), ("published_at", -1)])
        .to_list(length=limit)
    )

    counts: dict[str, int] = {}
    async for group in db[BLOG_V2_POSTS].aggregate(
        [{"$match": {"active": True}}, {"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    ):
        counts[str(group.get("_id") or "unknown")] = int(group.get("count") or 0)

    return {
        "posts": rows,
        "counts": counts,
        "auto_published_now": published,
        "workflow_statuses": WORKFLOW_STATUSES,
    }


@router.post("/posts")
async def create_editorial_post(request: Request, payload: EditorialPostCreate):
    admin = await require_admin(request)
    now = _now_iso()
    author_name = getattr(admin, "name", None) or getattr(admin, "email", None) or "Editorial Team"

    doc = {
        "post_id": f"blogv2-ed-{uuid.uuid4().hex[:10]}",
        "slug": await _unique_slug(payload.title),
        "title": payload.title.strip(),
        "excerpt": payload.excerpt.strip(),
        "cover_image": payload.cover_image.strip(),
        "category": payload.category.strip() or "General",
        "tags": [str(t).strip() for t in payload.tags if str(t).strip()],
        "author_name": str(author_name),
        "author_slug": _slugify(str(author_name)),
        "author_role": "Editorial",
        "published_at": None,
        "date_display": "",
        "read_time_minutes": max(1, len(payload.content.split()) // 200),
        "content_blocks": _normalize_content_blocks(payload.content, payload.excerpt),
        "premium_sections": [],
        "premium_required": payload.premium_required,
        "metrics": {"views": 0, "bookmarks": 0, "shares": 0},
        "meta": {"source": "editorial_console", "created_at": now},
        "status": "draft",
        "active": True,
        "created_at": now,
        "updated_at": now,
        "scheduled_publish_at": None,
        "workflow_history": [
            {"action": "create_draft", "from": None, "to": "draft", "actor": str(author_name), "at": now}
        ],
    }
    await db[BLOG_V2_POSTS].insert_one(doc)
    doc.pop("_id", None)
    return {"post": doc}


@router.get("/posts/{post_id}")
async def get_editorial_post(request: Request, post_id: str):
    await require_admin(request)
    doc = await db[BLOG_V2_POSTS].find_one({"post_id": post_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"post": doc}


@router.patch("/posts/{post_id}")
async def update_editorial_post(request: Request, post_id: str, payload: EditorialPostUpdate):
    await require_admin(request)
    doc = await db[BLOG_V2_POSTS].find_one({"post_id": post_id}, {"_id": 0, "status": 1, "excerpt": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")

    updates: dict[str, Any] = {"updated_at": _now_iso()}
    if payload.title is not None:
        updates["title"] = payload.title.strip()
    if payload.excerpt is not None:
        updates["excerpt"] = payload.excerpt.strip()
    if payload.category is not None:
        updates["category"] = payload.category.strip() or "General"
    if payload.tags is not None:
        updates["tags"] = [str(t).strip() for t in payload.tags if str(t).strip()]
    if payload.cover_image is not None:
        updates["cover_image"] = payload.cover_image.strip()
    if payload.premium_required is not None:
        updates["premium_required"] = payload.premium_required
    if payload.content is not None:
        excerpt = updates.get("excerpt", str(doc.get("excerpt") or ""))
        updates["content_blocks"] = _normalize_content_blocks(payload.content, excerpt)
        updates["read_time_minutes"] = max(1, len(payload.content.split()) // 200)

    await db[BLOG_V2_POSTS].update_one({"post_id": post_id}, {"$set": updates})
    fresh = await db[BLOG_V2_POSTS].find_one({"post_id": post_id}, {"_id": 0})
    return {"post": fresh}


@router.post("/posts/{post_id}/transition")
async def transition_editorial_post(request: Request, post_id: str, payload: EditorialTransition):
    admin = await require_admin(request)
    rule = TRANSITIONS.get(payload.action)
    if not rule:
        raise HTTPException(status_code=400, detail="Unknown transition action")

    doc = await db[BLOG_V2_POSTS].find_one({"post_id": post_id}, {"_id": 0, "status": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")

    current = str(doc.get("status") or "draft")
    if current not in rule["from"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot apply '{payload.action}' from status '{current}'",
        )

    now = _now_iso()
    target = rule["to"]
    updates: dict[str, Any] = {"status": target, "updated_at": now}

    if payload.action == "schedule":
        if not payload.publish_at:
            raise HTTPException(status_code=400, detail="publish_at is required for schedule")
        try:
            publish_dt = datetime.fromisoformat(payload.publish_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="publish_at must be ISO-8601")
        if publish_dt.tzinfo is None:
            publish_dt = publish_dt.replace(tzinfo=timezone.utc)
        if publish_dt <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="publish_at must be in the future")
        updates["scheduled_publish_at"] = publish_dt.isoformat()
    elif payload.action == "approve_publish":
        updates["published_at"] = now
        updates["scheduled_publish_at"] = None
    elif payload.action in {"revert_draft", "unpublish"}:
        updates["scheduled_publish_at"] = None

    actor = getattr(admin, "email", None) or getattr(admin, "user_id", None) or "admin"
    await db[BLOG_V2_POSTS].update_one(
        {"post_id": post_id},
        {
            "$set": updates,
            "$push": {
                "workflow_history": {
                    "action": payload.action,
                    "from": current,
                    "to": target,
                    "actor": str(actor),
                    "at": now,
                }
            },
        },
    )
    fresh = await db[BLOG_V2_POSTS].find_one({"post_id": post_id}, {"_id": 0})
    return {"post": fresh}
