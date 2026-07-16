"""GPS admin governance routes: versions, change approvals, import/export, and outbox."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from routes.db import db, require_admin
from routes.global_platform_state import (
    GPS_STATE_ID,
    _can_publish_changes,
    _compute_state_diff,
    _create_change_request,
    _now_iso,
    _persist_and_emit,
    _sanitize_faq,
    _sanitize_features,
    _sanitize_plans,
    get_global_platform_state,
    process_gps_notification_outbox,
    reconcile_gps_notification_outbox,
)
from services.gps_change_application import apply_change_to_state as service_apply_change_to_state
from services.gps_governance import is_high_impact_change
from services.gps_import_export import apply_import_to_state, parse_import_content, render_csv, select_export_data
from services.gps_outbox import outbox_stats


router = APIRouter(prefix="/gps", tags=["Global Platform State"])


class GpsWorkerRunPayload(BaseModel):
    batch_size: int = 250


class GpsChangeRequestPayload(BaseModel):
    entity_type: str
    operation: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    workflow_mode: str = "draft"


class GpsImportPayload(BaseModel):
    section: str
    format: str = "json"
    content: str
    workflow_mode: str = "draft"
    reason: str = ""


def _apply_change_to_state(state: Dict[str, Any], entity_type: str, operation: str, payload: Dict[str, Any]):
    try:
        return service_apply_change_to_state(
            state,
            entity_type,
            operation,
            payload,
            sanitize_features=_sanitize_features,
            sanitize_plans=_sanitize_plans,
            sanitize_faq=_sanitize_faq,
            now_iso=_now_iso,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/admin/versions")
async def list_versions(request: Request, limit: int = 40):
    await require_admin(request)
    rows = await db.gps_state_versions.find({}, {"_id": 0, "state": 0}).sort("created_at", -1).limit(max(1, min(limit, 200))).to_list(max(1, min(limit, 200)))
    return {"versions": rows, "total": len(rows)}


@router.get("/admin/versions/{version_id}/diff")
async def get_version_diff(version_id: str, request: Request, against: str = "previous"):
    await require_admin(request)
    current = await db.gps_state_versions.find_one({"version_id": version_id}, {"_id": 0})
    if not current:
        raise HTTPException(status_code=404, detail="Version not found")

    if against == "previous":
        previous = await db.gps_state_versions.find_one(
            {"version": {"$lt": current.get("version", 0)}},
            {"_id": 0},
            sort=[("version", -1)],
        )
    else:
        previous = await db.gps_state_versions.find_one({"version_id": against}, {"_id": 0})

    previous_state = (previous or {}).get("state") or {"features": [], "plans": [], "faq": [], "ui_labels": {}}
    current_state = current.get("state") or {"features": [], "plans": [], "faq": [], "ui_labels": {}}
    return {
        "current_version": current.get("version"),
        "against_version": (previous or {}).get("version"),
        "diff": _compute_state_diff(current_state, previous_state),
    }


@router.post("/admin/versions/{version_id}/rollback")
async def rollback_to_version(version_id: str, request: Request, reason: str = ""):
    user = await require_admin(request)
    if not _can_publish_changes(user):
        raise HTTPException(status_code=403, detail="Publishing permission required for rollback")
    target = await db.gps_state_versions.find_one({"version_id": version_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Version not found")

    change = await _create_change_request(
        user=user,
        entity_type="rollback",
        operation="rollback_to_version",
        payload={"version_id": version_id, "target_version": target.get("version"), "state": target.get("state") or {}},
        reason=reason or "Rollback requested",
        workflow_mode="review",
        requires_peer_review=True,
    )
    return {"status": "queued_for_approval", "change_request": change, "rolled_back_from": target.get("version")}


@router.get("/admin/changes")
async def list_change_requests(request: Request, status: str = ""):
    await require_admin(request)
    query = {"status": status} if status else {}
    rows = await db.gps_change_requests.find(query, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)
    return {"changes": rows, "total": len(rows)}


@router.post("/admin/changes")
async def create_change_request(payload: GpsChangeRequestPayload, request: Request):
    user = await require_admin(request)
    requires_peer_review = is_high_impact_change(payload.entity_type, payload.operation, payload.payload)
    change = await _create_change_request(
        user=user,
        entity_type=payload.entity_type,
        operation=payload.operation,
        payload=payload.payload,
        reason=payload.reason,
        workflow_mode="review" if payload.workflow_mode == "publish" and requires_peer_review else payload.workflow_mode,
        requires_peer_review=requires_peer_review,
    )
    return {"status": "queued_for_approval", "change_request": change}


@router.post("/admin/changes/{request_id}/submit-review")
async def submit_change_for_review(request_id: str, request: Request):
    user = await require_admin(request)
    change = await db.gps_change_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not change:
        raise HTTPException(status_code=404, detail="Change request not found")
    await db.gps_change_requests.update_one(
        {"request_id": request_id},
        {"$set": {"status": "review", "updated_at": _now_iso(), "submitted_by": user.user_id}},
    )
    return {"status": "review", "request_id": request_id}


@router.post("/admin/changes/{request_id}/approve-publish")
async def approve_and_publish_change(request_id: str, request: Request):
    user = await require_admin(request)
    if not _can_publish_changes(user):
        raise HTTPException(status_code=403, detail="Publishing permission required")
    change = await db.gps_change_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not change:
        raise HTTPException(status_code=404, detail="Change request not found")
    if change.get("status") in {"published", "rejected"}:
        raise HTTPException(status_code=400, detail=f"Request already {change.get('status')}")
    if change.get("status") != "review":
        raise HTTPException(status_code=400, detail="Change request must be submitted for review before publishing")
    if change.get("requires_peer_review"):
        blocked_publishers = {str(v) for v in (change.get("cannot_be_published_by") or []) if v}
        blocked_publishers.add(str(change.get("created_by") or ""))
        if str(user.user_id) in blocked_publishers:
            raise HTTPException(status_code=403, detail="Two-person publish control requires a different admin to approve this high-impact GPS change")

    state = await get_global_platform_state()
    event_type, change_text = _apply_change_to_state(
        state,
        change.get("entity_type", ""),
        change.get("operation", ""),
        change.get("payload") or {},
    )
    state = await _persist_and_emit(
        state=state,
        event_type=event_type,
        what_changed=f"Approved change request {request_id}: {change_text}",
        why_changed=change.get("reason") or "Approved by publisher",
        impact="GPS content has been published after review workflow.",
        actor_user_id=user.user_id,
    )
    await db.gps_change_requests.update_one(
        {"request_id": request_id},
        {"$set": {"status": "published", "published_at": _now_iso(), "published_by": user.user_id, "updated_at": _now_iso(), "published_version": state.get("version")}},
    )
    return {"status": "published", "request_id": request_id, "state_version": state.get("version")}


@router.post("/admin/changes/{request_id}/reject")
async def reject_change_request(request_id: str, request: Request, reason: str = ""):
    user = await require_admin(request)
    change = await db.gps_change_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not change:
        raise HTTPException(status_code=404, detail="Change request not found")
    await db.gps_change_requests.update_one(
        {"request_id": request_id},
        {"$set": {"status": "rejected", "rejected_at": _now_iso(), "rejected_by": user.user_id, "reject_reason": reason or "Rejected by reviewer", "updated_at": _now_iso()}},
    )
    return {"status": "rejected", "request_id": request_id}


@router.get("/admin/export")
async def export_gps(request: Request, section: str = "full", format: str = "json"):
    await require_admin(request)
    state = await get_global_platform_state()

    section = section.lower()
    format = format.lower()
    try:
        data = select_export_data(state, section)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported section")

    if format == "json":
        return {"section": section, "format": "json", "data": data}

    if format != "csv":
        raise HTTPException(status_code=400, detail="Unsupported format")

    return {"section": section, "format": "csv", "content": render_csv(data)}


@router.post("/admin/import")
async def import_gps(payload: GpsImportPayload, request: Request):
    user = await require_admin(request)
    section = payload.section.lower()
    fmt = payload.format.lower()

    try:
        parsed = parse_import_content(payload.content, fmt)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported import format")

    requires_peer_review = is_high_impact_change(section, "bulk_import", {"section": section, "format": fmt})
    if payload.workflow_mode != "publish" or not _can_publish_changes(user) or requires_peer_review:
        change = await _create_change_request(
            user=user,
            entity_type=section,
            operation="bulk_import",
            payload={"section": section, "parsed": parsed},
            reason=payload.reason or f"Bulk import ({fmt})",
            workflow_mode="review" if payload.workflow_mode == "publish" and requires_peer_review else payload.workflow_mode,
            requires_peer_review=requires_peer_review,
        )
        return {"status": "queued_for_approval", "change_request": change}

    state = await get_global_platform_state()
    try:
        state = apply_import_to_state(
            state=state,
            section=section,
            parsed=parsed,
            gps_state_id=GPS_STATE_ID,
            sanitize_features=_sanitize_features,
            sanitize_plans=_sanitize_plans,
            sanitize_faq=_sanitize_faq,
            now_iso=_now_iso,
        )
    except ValueError as exc:
        if str(exc) == "Full JSON import requires object":
            raise HTTPException(status_code=400, detail=str(exc))
        raise HTTPException(status_code=400, detail="Unsupported import section")

    state = await _persist_and_emit(
        state=state,
        event_type="ContentUpdated",
        what_changed=f"Bulk import published for `{section}`",
        why_changed=payload.reason or f"Bulk import ({fmt})",
        impact="GPS content updated via bulk import and propagated to all dependent surfaces.",
        actor_user_id=user.user_id,
    )
    return {"status": "imported", "state": state}


@router.get("/admin/outbox/stats")
async def get_outbox_stats(request: Request):
    await require_admin(request)
    return await outbox_stats(db, _now_iso)


@router.post("/admin/outbox/replay")
async def replay_outbox(payload: GpsWorkerRunPayload, request: Request):
    await require_admin(request)
    result = await process_gps_notification_outbox(batch_size=payload.batch_size)
    return {"status": "ok", "result": result}


@router.post("/admin/outbox/reconcile")
async def reconcile_outbox(payload: GpsWorkerRunPayload, request: Request):
    await require_admin(request)
    result = await reconcile_gps_notification_outbox(limit_events=max(5, min(payload.batch_size, 100)))
    return {"status": "ok", "result": result}