"""
Email Health + Email Guardrail Control APIs.

Provides:
- Existing summary endpoint used by admin dashboard.
- Guardrail control-center endpoints for cap events, blocklist review,
  and template-wise cap policy management.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from collections import Counter
from typing import Optional, Any

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field

from routes.db import db, require_admin
from utils.email_service import canonicalize_recipient_email, clear_template_cap_policy_cache

router = APIRouter(prefix="/admin/email-health", tags=["Admin: Email Health"])


CAP_COLLECTION = "email_notification_send_caps"
EVENTS_COLLECTION = "email_notification_guardrail_events"
BLOCKLIST_COLLECTION = "email_recipient_blocklist"
POLICY_COLLECTION = "email_notification_template_policies"


class GuardrailBlocklistUpsertRequest(BaseModel):
    recipient_email: str
    active: bool = True
    apply_to_canonical: bool = False
    reason: str = Field(default="manual_review", max_length=300)


class GuardrailTemplatePolicyUpsertRequest(BaseModel):
    max_per_fingerprint: int = Field(ge=1, le=20)
    active: bool = True
    note: str = Field(default="", max_length=300)


@router.get("/summary")
async def email_health_summary(request: Request, window_hours: int = 24):
    """Rolled-up window of email activity for admin dashboard."""
    await require_admin(request)
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=max(1, window_hours))
    since_iso = since.isoformat()

    sent_cursor = db.email_logs.find(
        {"created_at": {"$gte": since_iso}, "status": {"$in": ["sent", "success"]}},
        {"_id": 0, "email_type": 1},
    )
    template_counter: Counter = Counter()
    sent = 0
    async for row in sent_cursor:
        sent += 1
        template_counter[row.get("email_type") or "(unknown)"] += 1
    top_templates = [
        {"template": k, "count": v}
        for k, v in template_counter.most_common(6)
    ]

    delivered = await db.email_delivery_events.count_documents(
        {"created_at": {"$gte": since_iso}, "internal_status": "delivered"}
    )
    bounced = await db.email_delivery_events.count_documents(
        {"created_at": {"$gte": since_iso}, "internal_status": "bounced"}
    )
    complained = await db.email_delivery_events.count_documents(
        {"created_at": {"$gte": since_iso}, "internal_status": "complained"}
    )

    violations_count = await db.v7_violations.count_documents({"created_at": {"$gte": since_iso}})
    recent_violations = await db.v7_violations.find(
        {"created_at": {"$gte": since_iso}}, {"_id": 0}
    ).sort("created_at", -1).limit(5).to_list(5)

    denom = max(sent, 1)
    return {
        "window_hours": window_hours,
        "window_start_utc": since_iso,
        "window_end_utc": now.isoformat(),
        "sent": sent,
        "delivered": delivered,
        "bounced": bounced,
        "complained": complained,
        "template_key_violations": violations_count,
        "delivery_rate": round((delivered / denom) * 100, 1),
        "bounce_rate": round((bounced / denom) * 100, 1),
        "top_templates": top_templates,
        "recent_violations": recent_violations,
    }


@router.get("/guardrail/overview")
async def email_guardrail_overview(request: Request, window_hours: int = 24):
    await require_admin(request)
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=max(1, window_hours))
    since_iso = since.isoformat()

    blocked_events = await db[EVENTS_COLLECTION].count_documents({"created_at": {"$gte": since_iso}})
    active_blocklist = await db[BLOCKLIST_COLLECTION].count_documents({"active": {"$ne": False}})
    active_policies = await db[POLICY_COLLECTION].count_documents({"active": {"$ne": False}})

    top_templates = await db[EVENTS_COLLECTION].aggregate([
        {"$match": {"created_at": {"$gte": since_iso}}},
        {"$group": {"_id": "$template_key", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]).to_list(8)

    cap_rows = await db[CAP_COLLECTION].find({}, {"_id": 0, "send_count": 1}).to_list(5000)
    capped_keys = sum(1 for row in cap_rows if int(row.get("send_count") or 0) >= 2)

    return {
        "window_hours": window_hours,
        "window_start_utc": since_iso,
        "window_end_utc": now.isoformat(),
        "blocked_events": blocked_events,
        "active_blocklist_entries": active_blocklist,
        "active_template_policies": active_policies,
        "capped_fingerprint_keys": capped_keys,
        "top_blocked_templates": [
            {"template_key": row.get("_id") or "(unknown)", "count": int(row.get("count") or 0)}
            for row in top_templates
        ],
    }


@router.get("/guardrail/events")
async def list_email_guardrail_events(
    request: Request,
    hours: int = Query(default=72, ge=1, le=720),
    template_key: Optional[str] = Query(default=None),
    recipient: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
):
    await require_admin(request)
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query: dict[str, Any] = {"created_at": {"$gte": since_iso}}
    if template_key:
        query["template_key"] = template_key
    if recipient:
        query["canonical_recipient"] = recipient.strip().lower()

    rows = await db[EVENTS_COLLECTION].find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"window_hours": hours, "count": len(rows), "items": rows}


@router.get("/guardrail/blocklist")
async def list_email_guardrail_blocklist(
    request: Request,
    active_only: bool = Query(default=True),
    search: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=2000),
):
    await require_admin(request)
    query: dict[str, Any] = {}
    if active_only:
        query["active"] = {"$ne": False}
    if search.strip():
        query["recipient_email"] = {"$regex": search.strip(), "$options": "i"}

    rows = await db[BLOCKLIST_COLLECTION].find(query, {"_id": 0}).sort("updated_at", -1).limit(limit).to_list(limit)
    return {"count": len(rows), "items": rows}


@router.put("/guardrail/blocklist")
async def upsert_email_guardrail_blocklist(request: Request, body: GuardrailBlocklistUpsertRequest):
    admin = await require_admin(request)
    recipient_email = body.recipient_email.strip().lower()
    if not recipient_email or "@" not in recipient_email:
        raise HTTPException(status_code=400, detail="Valid recipient_email is required")

    now_iso = datetime.now(timezone.utc).isoformat()
    canonical = canonicalize_recipient_email(recipient_email)
    await db[BLOCKLIST_COLLECTION].update_one(
        {"recipient_email": recipient_email},
        {
            "$set": {
                "recipient_email": recipient_email,
                "canonical_recipient": canonical,
                "active": body.active,
                "apply_to_canonical": body.apply_to_canonical,
                "reason": body.reason,
                "source": "email_guardrail_control_center",
                "updated_at": now_iso,
                "updated_by": getattr(admin, "user_id", "admin"),
            },
            "$setOnInsert": {
                "created_at": now_iso,
                "created_by": getattr(admin, "user_id", "admin"),
            },
        },
        upsert=True,
    )
    row = await db[BLOCKLIST_COLLECTION].find_one({"recipient_email": recipient_email}, {"_id": 0})
    return {"success": True, "item": row}


@router.post("/guardrail/blocklist/{recipient_email}/unblock")
async def unblock_email_guardrail_recipient(request: Request, recipient_email: str):
    admin = await require_admin(request)
    email_value = recipient_email.strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db[BLOCKLIST_COLLECTION].update_one(
        {"recipient_email": email_value},
        {
            "$set": {
                "active": False,
                "updated_at": now_iso,
                "updated_by": getattr(admin, "user_id", "admin"),
                "unblocked_at": now_iso,
                "unblocked_by": getattr(admin, "user_id", "admin"),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Recipient not found in blocklist")
    row = await db[BLOCKLIST_COLLECTION].find_one({"recipient_email": email_value}, {"_id": 0})
    return {"success": True, "item": row}


@router.get("/guardrail/template-policies")
async def list_email_guardrail_template_policies(request: Request, active_only: bool = Query(default=False)):
    await require_admin(request)
    query: dict[str, Any] = {}
    if active_only:
        query["active"] = {"$ne": False}
    rows = await db[POLICY_COLLECTION].find(query, {"_id": 0}).sort("template_key", 1).limit(2000).to_list(2000)
    return {
        "default_max_per_fingerprint": 2,
        "count": len(rows),
        "items": rows,
    }


@router.put("/guardrail/template-policies/{template_key}")
async def upsert_email_guardrail_template_policy(
    request: Request,
    template_key: str,
    body: GuardrailTemplatePolicyUpsertRequest,
):
    admin = await require_admin(request)
    normalized = template_key.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="template_key is required")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db[POLICY_COLLECTION].update_one(
        {"template_key": normalized},
        {
            "$set": {
                "template_key": normalized,
                "max_per_fingerprint": int(body.max_per_fingerprint),
                "active": bool(body.active),
                "note": body.note,
                "updated_at": now_iso,
                "updated_by": getattr(admin, "user_id", "admin"),
            },
            "$setOnInsert": {
                "created_at": now_iso,
                "created_by": getattr(admin, "user_id", "admin"),
            },
        },
        upsert=True,
    )
    clear_template_cap_policy_cache(normalized)
    row = await db[POLICY_COLLECTION].find_one({"template_key": normalized}, {"_id": 0})
    return {"success": True, "item": row}


@router.delete("/guardrail/template-policies/{template_key}")
async def delete_email_guardrail_template_policy(request: Request, template_key: str):
    await require_admin(request)
    normalized = template_key.strip().lower()
    result = await db[POLICY_COLLECTION].delete_one({"template_key": normalized})
    clear_template_cap_policy_cache(normalized)
    return {"success": True, "deleted": int(result.deleted_count or 0)}
