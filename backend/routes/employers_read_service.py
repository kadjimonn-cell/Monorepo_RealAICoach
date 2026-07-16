"""Feature 26 employers legacy read services (phase-safe decomposition)."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from fastapi import HTTPException, Response

from .db import db
from utils.object_storage_service import get_bytes

RE_VERIFICATION_COOLDOWN_DAYS = 14


def _safe_filename(filename: str, fallback: str = "document") -> str:
    import re

    base = str(filename or "").strip() or fallback
    base = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    return base[:120]


def _legacy_local_doc_path(employer_id: str, filename: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "media",
        "employer_docs",
        employer_id,
        filename,
    )


async def get_my_application_read(user_id: str) -> Dict[str, Any]:
    application = await db.employer_applications.find_one({"user_id": user_id}, {"_id": 0})
    return {"application": application}


async def download_employer_document_read(
    *,
    employer_id: str,
    doc_id: str,
    user_id: str,
    is_admin: bool,
) -> Response:
    # Support both legacy doc collection and embedded docs in application record.
    legacy_doc = await db.employer_documents.find_one({"employer_id": employer_id, "doc_id": doc_id}, {"_id": 0})
    if legacy_doc:
        if not is_admin and user_id != employer_id:
            raise HTTPException(status_code=403, detail="Access denied")
        storage_key = legacy_doc.get("storage_key") or f"employer_docs/{employer_id}/{doc_id}"
        obj = get_bytes(storage_key)
        if not obj:
            raise HTTPException(status_code=404, detail="Document file not found")
        payload_bytes, payload_type = obj
        filename = _safe_filename(str(legacy_doc.get("filename") or f"{doc_id}.bin"))
        return Response(
            content=payload_bytes,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Original-Content-Type": str(payload_type or "application/octet-stream"),
            },
        )

    application = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    owns_doc = application.get("user_id") == user_id
    if not owns_doc and not is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    document = None
    for item in application.get("documents") or []:
        if str(item.get("doc_id") or "") == str(doc_id):
            document = item
            break
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    payload_bytes: Optional[bytes] = None
    payload_type = str(document.get("content_type") or "application/octet-stream")

    storage_path = str(document.get("storage_path") or "").strip()
    if storage_path:
        obj = get_bytes(storage_path)
        if obj:
            payload_bytes, payload_type = obj

    if payload_bytes is None:
        filename = str(document.get("filename") or "").strip()
        if filename:
            local_path = _legacy_local_doc_path(employer_id, filename)
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    payload_bytes = f.read()

    if payload_bytes is None:
        raise HTTPException(status_code=404, detail="Document content unavailable")

    download_name = _safe_filename(str(document.get("original_filename") or document.get("filename") or f"{doc_id}.bin"))
    return Response(
        content=payload_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "X-Original-Content-Type": payload_type,
        },
    )


async def get_my_permissions_read(user_id: str) -> Dict[str, Any]:
    application = await db.employer_applications.find_one({"user_id": user_id}, {"_id": 0})
    permissions = {
        "can_post_jobs": application.get("status") == "approved" if application else False,
        "can_view_candidates": application.get("status") == "approved" if application else False,
        "employer_status": application.get("status") if application else None,
    }
    return {"permissions": permissions}


async def admin_get_application_read(employer_id: str) -> Dict[str, Any]:
    application = await db.employer_applications.find_one({"employer_id": employer_id}, {"_id": 0})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"application": application}


async def admin_employer_communications_read(employer_id: str) -> Dict[str, Any]:
    messages = await db.employer_messages.find({"employer_id": employer_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"messages": messages, "total": len(messages)}


async def get_employer_messages_read(*, employer_id: str, user_id: str, is_admin: bool) -> Dict[str, Any]:
    is_owner = user_id == employer_id
    application = await db.employer_applications.find_one({"user_id": user_id, "employer_id": employer_id}, {"_id": 0})
    if not is_admin and not is_owner and not application:
        raise HTTPException(status_code=403, detail="Access denied")
    messages = await db.employer_messages.find({"employer_id": employer_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"messages": messages, "total": len(messages)}


async def check_reverify_status_read(user_id: str) -> Dict[str, Any]:
    application = await db.employer_applications.find_one({"user_id": user_id, "status": "rejected"}, {"_id": 0})
    if not application:
        return {"can_reverify": False, "reason": "No rejected application found"}

    rejected_at = application.get("rejected_at") or application.get("updated_at")
    if not rejected_at:
        return {"can_reverify": True, "reason": "Cooldown period passed"}

    try:
        rejected_dt = datetime.fromisoformat(str(rejected_at).replace("Z", "+00:00"))
        cooldown_end = rejected_dt + timedelta(days=RE_VERIFICATION_COOLDOWN_DAYS)
        now = datetime.now(timezone.utc)
        if now >= cooldown_end:
            return {"can_reverify": True, "reason": "Cooldown period passed"}
        days_left = (cooldown_end - now).days
        return {"can_reverify": False, "reason": f"Cooldown period: {days_left} days remaining"}
    except Exception:
        return {"can_reverify": True, "reason": "Unable to parse rejection date"}
