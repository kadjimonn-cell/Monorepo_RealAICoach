from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import secrets

from .db import db

router = APIRouter()


class CreateShareLinkRequest(BaseModel):
    user_id: str
    feature_key: str
    content: str
    title: Optional[str] = "Shared Content"
    expires_in_hours: Optional[int] = 72


@router.post("/share/create")
async def create_share_link(request: CreateShareLinkRequest):
    """Generate a secure share link with token and expiration."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=request.expires_in_hours)

    doc = {
        "share_id": f"share_{uuid.uuid4().hex[:12]}",
        "token": token,
        "user_id": request.user_id,
        "feature_key": request.feature_key,
        "content": request.content,
        "title": request.title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "view_count": 0,
        "is_active": True,
    }
    await db.shared_links.insert_one(doc)
    return {
        "success": True,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "share_id": doc["share_id"],
    }


@router.get("/share/{token}")
async def get_shared_content(token: str):
    """Resolve a share link by token. Validates expiration."""
    doc = await db.shared_links.find_one({"token": token, "is_active": True}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Share link not found or has been revoked")

    expires_at = datetime.fromisoformat(doc["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        await db.shared_links.update_one({"token": token}, {"$set": {"is_active": False}})
        raise HTTPException(status_code=410, detail="Share link has expired")

    await db.shared_links.update_one({"token": token}, {"$inc": {"view_count": 1}})

    return {
        "title": doc.get("title", "Shared Content"),
        "content": doc.get("content", ""),
        "feature_key": doc.get("feature_key", ""),
        "created_at": doc.get("created_at", ""),
        "expires_at": doc.get("expires_at", ""),
        "view_count": doc.get("view_count", 0) + 1,
    }


@router.delete("/share/{share_id}/revoke")
async def revoke_share_link(share_id: str):
    """Revoke/deactivate a share link."""
    result = await db.shared_links.update_one({"share_id": share_id, "is_active": True}, {"$set": {"is_active": False}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Share link not found or already revoked")
    return {"success": True}


@router.get("/share/user/{user_id}")
async def get_user_shares(user_id: str, limit: int = 20):
    """Get all share links created by a user."""
    items = await db.shared_links.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"shares": items, "total": len(items)}
