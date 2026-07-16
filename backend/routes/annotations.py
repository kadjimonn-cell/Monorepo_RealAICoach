"""PDF Annotation API — CRUD for per-user document annotations."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import uuid

from routes.db import db, require_auth

router = APIRouter(prefix="/annotations", tags=["Annotations"])


class Annotation(BaseModel):
    id: str = Field(default_factory=lambda: f"ann_{uuid.uuid4().hex[:12]}")
    type: str  # "highlight", "note", "draw"
    x: float
    y: float
    width: Optional[float] = None
    height: Optional[float] = None
    color: str = "#FACC15"
    text: Optional[str] = None
    page: int = 1
    points: Optional[List[dict]] = None  # For freehand draw [{x, y}, ...]


class SaveAnnotationsRequest(BaseModel):
    annotations: List[Annotation]


@router.get("/{document_id}")
async def get_annotations(document_id: str, request: Request):
    user = await require_auth(request)
    doc = await db.pdf_annotations.find_one({"document_id": document_id, "user_id": user.user_id}, {"_id": 0})
    return {
        "document_id": document_id,
        "annotations": doc.get("annotations", []) if doc else [],
        "updated_at": doc.get("updated_at") if doc else None,
    }


@router.post("/{document_id}")
async def save_annotations(document_id: str, body: SaveAnnotationsRequest, request: Request):
    user = await require_auth(request)
    now = datetime.now(timezone.utc).isoformat()
    annotations = [a.dict() for a in body.annotations]

    await db.pdf_annotations.update_one(
        {"document_id": document_id, "user_id": user.user_id},
        {
            "$set": {
                "annotations": annotations,
                "updated_at": now,
            },
            "$setOnInsert": {
                "document_id": document_id,
                "user_id": user.user_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return {"success": True, "count": len(annotations), "updated_at": now}


@router.delete("/{document_id}")
async def clear_annotations(document_id: str, request: Request):
    user = await require_auth(request)
    result = await db.pdf_annotations.delete_one({"document_id": document_id, "user_id": user.user_id})
    return {"success": True, "deleted": result.deleted_count > 0}


@router.delete("/{document_id}/{annotation_id}")
async def delete_annotation(document_id: str, annotation_id: str, request: Request):
    user = await require_auth(request)
    result = await db.pdf_annotations.update_one(
        {"document_id": document_id, "user_id": user.user_id},
        {
            "$pull": {"annotations": {"id": annotation_id}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
        },
    )
    return {"success": True, "modified": result.modified_count > 0}
