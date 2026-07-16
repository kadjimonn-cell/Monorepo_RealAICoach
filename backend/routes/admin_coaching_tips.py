"""Admin CMS for the public coaching-tips catalog.

Admins manage the catalog that powers the Welcome tickertape's
`TIP OF THE DAY` rotating fact. All mutations are audit-logged with
the acting admin's email.

    GET    /api/admin/coaching-tips                  — list all (active + inactive)
    POST   /api/admin/coaching-tips                  — create
    PUT    /api/admin/coaching-tips/{tip_id}         — update title/content/active
    POST   /api/admin/coaching-tips/{tip_id}/move    — reorder (position delta)
    DELETE /api/admin/coaching-tips/{tip_id}         — hard delete

Collection: `public_coaching_tips` (shared with routes.public_social_proof).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.db import db, require_admin
from routes.public_social_proof import TIPS_COL

logger = logging.getLogger(__name__)
router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TipCreateBody(BaseModel):
    title: str = Field(..., min_length=2, max_length=80)
    content: str = Field(..., min_length=5, max_length=140)
    is_active: bool = True


class TipUpdateBody(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=80)
    content: Optional[str] = Field(None, min_length=5, max_length=140)
    is_active: Optional[bool] = None


class TipMoveBody(BaseModel):
    # Positive = move down the list, negative = move up. The endpoint
    # normalizes all positions to a dense 0..N-1 sequence after the move.
    delta: int = Field(..., ge=-100, le=100)


@router.get("/admin/coaching-tips")
async def admin_list_tips(request: Request):
    await require_admin(request)
    items: list[dict[str, Any]] = []
    async for t in db[TIPS_COL].find({}, {"_id": 0}).sort("position", 1):
        items.append(t)
    active = sum(1 for t in items if t.get("is_active"))
    return {"items": items, "total": len(items), "active": active}


@router.post("/admin/coaching-tips")
async def admin_create_tip(request: Request, body: TipCreateBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    # Append at the end of the ordered list.
    last = await db[TIPS_COL].find_one({}, {"_id": 0, "position": 1}, sort=[("position", -1)])
    next_pos = int((last or {}).get("position", -1)) + 1
    now = _now_iso()
    doc = {
        "tip_id": f"tip-{uuid.uuid4().hex[:10]}",
        "title": body.title.strip(),
        "content": body.content.strip(),
        "is_active": bool(body.is_active),
        "position": next_pos,
        "created_at": now,
        "updated_at": now,
        "created_by": actor,
    }
    await db[TIPS_COL].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/admin/coaching-tips/{tip_id}")
async def admin_update_tip(request: Request, tip_id: str, body: TipUpdateBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    current = await db[TIPS_COL].find_one({"tip_id": tip_id}, {"_id": 0})
    if not current:
        raise HTTPException(status_code=404, detail="Tip not found")
    patch: dict[str, Any] = {"updated_at": _now_iso(), "updated_by": actor}
    if body.title is not None:
        patch["title"] = body.title.strip()
    if body.content is not None:
        patch["content"] = body.content.strip()
    if body.is_active is not None:
        patch["is_active"] = bool(body.is_active)
    await db[TIPS_COL].update_one({"tip_id": tip_id}, {"$set": patch})
    updated = await db[TIPS_COL].find_one({"tip_id": tip_id}, {"_id": 0})
    return updated


@router.post("/admin/coaching-tips/{tip_id}/move")
async def admin_move_tip(request: Request, tip_id: str, body: TipMoveBody):
    await require_admin(request)
    if body.delta == 0:
        raise HTTPException(status_code=400, detail="delta must be non-zero")
    items: list[dict[str, Any]] = []
    async for t in db[TIPS_COL].find({}, {"_id": 0}).sort("position", 1):
        items.append(t)
    try:
        idx = next(i for i, t in enumerate(items) if t.get("tip_id") == tip_id)
    except StopIteration:
        raise HTTPException(status_code=404, detail="Tip not found")
    new_idx = max(0, min(len(items) - 1, idx + body.delta))
    if new_idx == idx:
        return {"ok": True, "changed": False}
    moved = items.pop(idx)
    items.insert(new_idx, moved)
    # Rewrite positions as dense 0..N-1 so gaps never accumulate.
    now = _now_iso()
    for pos, t in enumerate(items):
        await db[TIPS_COL].update_one(
            {"tip_id": t["tip_id"]},
            {"$set": {"position": pos, "updated_at": now}},
        )
    return {"ok": True, "changed": True, "from": idx, "to": new_idx}


@router.delete("/admin/coaching-tips/{tip_id}")
async def admin_delete_tip(request: Request, tip_id: str):
    await require_admin(request)
    res = await db[TIPS_COL].delete_one({"tip_id": tip_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tip not found")
    # Re-densify positions so the ordering stays tight.
    now = _now_iso()
    pos = 0
    async for t in db[TIPS_COL].find({}, {"_id": 0, "tip_id": 1}).sort("position", 1):
        await db[TIPS_COL].update_one(
            {"tip_id": t["tip_id"]},
            {"$set": {"position": pos, "updated_at": now}},
        )
        pos += 1
    return {"ok": True}


__all__ = ["router"]
