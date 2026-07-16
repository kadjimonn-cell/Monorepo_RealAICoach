"""Shared workflow helpers for ID verification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import HTTPException

from .db import db

ID_CHECKER_NOT_SUBMITTED = "NOT_SUBMITTED"
ID_CHECKER_PENDING = "PENDING"
ID_CHECKER_AI_REVIEW = "AI_REVIEW"
ID_CHECKER_ADMIN_REVIEW = "ADMIN_REVIEW"
ID_CHECKER_APPROVED = "APPROVED"
ID_CHECKER_REJECTED = "REJECTED"
ID_CHECKER_MORE_INFO_REQUIRED = "MORE_INFO_REQUIRED"

ID_CHECKER_ALLOWED_TRANSITIONS = {
    ID_CHECKER_NOT_SUBMITTED: {ID_CHECKER_PENDING},
    ID_CHECKER_PENDING: {ID_CHECKER_AI_REVIEW},
    ID_CHECKER_AI_REVIEW: {ID_CHECKER_ADMIN_REVIEW},
    ID_CHECKER_ADMIN_REVIEW: {
        ID_CHECKER_APPROVED,
        ID_CHECKER_REJECTED,
        ID_CHECKER_MORE_INFO_REQUIRED,
    },
    ID_CHECKER_MORE_INFO_REQUIRED: {ID_CHECKER_PENDING},
    ID_CHECKER_REJECTED: {ID_CHECKER_PENDING},
    ID_CHECKER_APPROVED: {ID_CHECKER_PENDING},
}

REQUIRED_IDV_DOCUMENT_TYPES = {"id_front", "id_back", "selfie"}


def workflow_state_from_legacy_status(status: Optional[str]) -> str:
    s = str(status or "").strip().lower()
    if s == "verified":
        return ID_CHECKER_APPROVED
    if s in {"rejected", "banned"}:
        return ID_CHECKER_REJECTED
    if s == "pending_review":
        return ID_CHECKER_ADMIN_REVIEW
    return ID_CHECKER_NOT_SUBMITTED


def legacy_status_from_workflow_state(workflow_state: str) -> str:
    if workflow_state == ID_CHECKER_APPROVED:
        return "verified"
    if workflow_state == ID_CHECKER_REJECTED:
        return "rejected"
    if workflow_state == ID_CHECKER_MORE_INFO_REQUIRED:
        return "pending_review"
    if workflow_state in {ID_CHECKER_PENDING, ID_CHECKER_AI_REVIEW, ID_CHECKER_ADMIN_REVIEW}:
        return "pending_review"
    return "pending_review"


def normalize_workflow_state_in_doc(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    wf = str(doc.get("workflow_state") or "").strip().upper()
    if not wf:
        wf = workflow_state_from_legacy_status(doc.get("status"))
    doc["workflow_state"] = wf
    if not doc.get("status"):
        doc["status"] = legacy_status_from_workflow_state(wf)
    return doc


async def create_idv_notification(
    user_id: str,
    notif_type: str,
    title: str,
    message: str,
    *,
    metadata: Optional[dict] = None,
    now_iso: Optional[str] = None,
):
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    notif_id = f"notif_idv_{uuid.uuid4().hex[:10]}"
    await db.notifications.insert_one(
        {
            "id": notif_id,
            "notification_id": notif_id,
            "user_id": user_id,
            "type": notif_type,
            "title": title,
            "message": message,
            "body": message,
            "read": False,
            "created_at": ts,
            "metadata": metadata or {},
        }
    )


async def emit_state_transition(
    user_id: str,
    from_state: str,
    to_state: str,
    *,
    actor: str,
    reason: str,
    metadata: Optional[dict] = None,
):
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.id_checker_state_transitions.insert_one(
        {
            "event_id": f"idc_st_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "from_state": from_state,
            "to_state": to_state,
            "actor": actor,
            "reason": reason,
            "metadata": metadata or {},
            "created_at": now_iso,
        }
    )
    try:
        await create_idv_notification(
            user_id=user_id,
            notif_type="id_checker_status_update",
            title="ID Checker Status Updated",
            message=f"Status changed: {from_state} → {to_state}",
            metadata={"from": from_state, "to": to_state, "reason": reason, **(metadata or {})},
            now_iso=now_iso,
        )
    except Exception:
        pass


async def transition_id_checker_state(
    *,
    user_id: str,
    current_state: str,
    target_state: str,
    actor: str,
    reason: str,
    metadata: Optional[dict] = None,
) -> dict:
    from_state = str(current_state or ID_CHECKER_NOT_SUBMITTED).upper()
    to_state = str(target_state or from_state).upper()
    if from_state == to_state:
        return {"workflow_state": to_state, "status": legacy_status_from_workflow_state(to_state)}
    allowed = ID_CHECKER_ALLOWED_TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid ID Checker state transition: {from_state} -> {to_state}")
    await emit_state_transition(
        user_id=user_id,
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        reason=reason,
        metadata=metadata,
    )
    return {"workflow_state": to_state, "status": legacy_status_from_workflow_state(to_state)}


def has_required_idv_documents(kyc: dict | None) -> bool:
    docs = (kyc or {}).get("documents") or []
    doc_types = {str(d.get("type") or "").lower() for d in docs}
    return REQUIRED_IDV_DOCUMENT_TYPES.issubset(doc_types)


def mask_id(id_number: str) -> str:
    if len(id_number) <= 4:
        return "***" + id_number[-2:]
    return "*" * (len(id_number) - 4) + id_number[-4:]


def calc_account_age(user: dict) -> int:
    if not user or not user.get("created_at"):
        return 0
    created = user["created_at"]
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created)
        except (ValueError, TypeError):
            return 0
    if hasattr(created, "tzinfo") and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    try:
        return (datetime.now(timezone.utc) - created).days
    except Exception:
        return 0