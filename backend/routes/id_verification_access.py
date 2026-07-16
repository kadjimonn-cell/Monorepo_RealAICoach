"""KYC access and IDV token helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from fastapi import HTTPException, Request

from .db import db, require_auth


def decrypt_kyc_doc(doc: dict | None, *, pii_fields: tuple[str, ...], decrypt_field, is_encrypted, normalize_workflow_state_in_doc):
    if not doc:
        return doc
    for field in pii_fields:
        val = doc.get(field)
        if val and is_encrypted(val):
            doc[field] = decrypt_field(val)
    return normalize_workflow_state_in_doc(doc)


async def kyc_find_one(filter_: dict, *, projection: dict | None, pii_fields: tuple[str, ...], decrypt_field, encrypt_field, is_encrypted, normalize_workflow_state_in_doc, logger) -> dict | None:
    doc = await db.afrikpay_kyc.find_one(filter_, projection or {"_id": 0})
    if not doc:
        return None
    doc.pop("_id", None)
    updates = {}
    for field in pii_fields:
        val = doc.get(field)
        if val and isinstance(val, str) and not is_encrypted(val):
            updates[field] = encrypt_field(val)
    if updates and doc.get("user_id"):
        try:
            await db.afrikpay_kyc.update_one({"user_id": doc["user_id"]}, {"$set": updates})
        except Exception as exc:
            logger.warning("KYC lazy encryption migration failed for %s: %s", doc.get("user_id"), exc)
    return decrypt_kyc_doc(doc, pii_fields=pii_fields, decrypt_field=decrypt_field, is_encrypted=is_encrypted, normalize_workflow_state_in_doc=normalize_workflow_state_in_doc)


async def kyc_find_many(filter_: dict, *, projection: dict | None, sort, limit: int, pii_fields: tuple[str, ...], decrypt_field, is_encrypted, normalize_workflow_state_in_doc) -> list:
    cursor = db.afrikpay_kyc.find(filter_, projection or {"_id": 0})
    if sort:
        cursor = cursor.sort(*sort)
    docs = await cursor.to_list(limit)
    return [
        decrypt_kyc_doc(d, pii_fields=pii_fields, decrypt_field=decrypt_field, is_encrypted=is_encrypted, normalize_workflow_state_in_doc=normalize_workflow_state_in_doc)
        for d in docs
    ]


async def resolve_user_for_idv(request: Request):
    try:
        return await require_auth(request)
    except HTTPException as auth_exc:
        if auth_exc.status_code not in (401, 403):
            raise
    token = request.query_params.get("idv_token") or request.headers.get("X-IDV-Access-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    access_doc = await db.idv_access_tokens.find_one({"token": token, "revoked": {"$ne": True}}, {"_id": 0})
    if not access_doc:
        raise HTTPException(status_code=401, detail="Invalid or expired ID Checker access")
    expires_at = access_doc.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if not expires_at:
        raise HTTPException(status_code=401, detail="Invalid ID Checker access token")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="ID Checker access token expired")
    user_doc = await db.users.find_one({"user_id": access_doc.get("user_id")}, {"_id": 0, "user_id": 1, "email": 1, "is_admin": 1})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    await db.idv_access_tokens.update_one({"token": token}, {"$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}})
    return SimpleNamespace(
        user_id=user_doc.get("user_id"),
        email=user_doc.get("email"),
        is_admin=bool(user_doc.get("is_admin", False)),
        idv_access_token=token,
    )


async def revoke_idv_access_token(token: Optional[str], reason: str = "completed") -> bool:
    if not token:
        return False
    result = await db.idv_access_tokens.update_one(
        {"token": token, "revoked": {"$ne": True}},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat(), "revoked_reason": reason}},
    )
    return bool(getattr(result, "modified_count", 0))